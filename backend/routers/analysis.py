import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from database import get_db, AsyncSessionLocal
from models import Company, PricingTier, Competitor, AnalysisSession, Report, User
from schemas import AnalysisStartResponse, ReportResponse, AnalysisHistoryItem
from routers.auth import get_current_user
from engine.module1_revenue import run_module1
from engine.module2_features import run_module2
from engine.module3_benchmark import run_module3
from engine.module4_recommendations import run_module4
from pdf_generator import generate_pdf, WEASYPRINT_AVAILABLE
from email_service import send_analysis_complete_email

from rate_limiter import limiter, get_analysis_daily_limit, get_user_id_key

router = APIRouter()

progress_queues: dict[str, asyncio.Queue] = {}
background_analysis_tasks: set[asyncio.Task] = set()
ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "240"))



async def _load_company_data(company_id: uuid.UUID, db: AsyncSession) -> dict:
    """Load company with all nested data into a plain dict for the engine."""
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.tiers).selectinload(PricingTier.features),
            selectinload(Company.competitors),
            selectinload(Company.owner),
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        raise ValueError(f"Company {company_id} not found")

    tiers = []
    for tier in company.tiers:
        tiers.append({
            "id": str(tier.id),
            "name": tier.name,
            "price": tier.price,
            "billing_cycle": tier.billing_cycle,
            "user_count": tier.user_count,
            "churn_rate": tier.churn_rate,
            "features": [
                {"feature_name": f.feature_name, "description": f.description}
                for f in tier.features
            ],
        })

    competitors = []
    COMPETITOR_REFRESH_DAYS = int(os.getenv("COMPETITOR_REFRESH_DAYS", "7"))
    now = datetime.utcnow()

    for comp in company.competitors:
        is_stale = False
        if comp.last_scraped_at:
            if (now - comp.last_scraped_at).total_seconds() >= COMPETITOR_REFRESH_DAYS * 86400:
                is_stale = True
        else:
            is_stale = True

        competitors.append({
            "id": str(comp.id),
            "name": comp.name or comp.url,
            "url": comp.url,
            "raw_scraped_text": comp.raw_scraped_text or "",
            "clean_scraped_text": comp.clean_scraped_text or "",
            "scrape_status": comp.scrape_status,
            "is_stale": is_stale,
        })

    from scraper import scrape_competitors_concurrent

    retry_candidates = [
        {"id": competitor["id"], "url": competitor["url"]}
        for competitor in competitors
        if (
            competitor.get("scrape_status")
            in {
                "failed",
                "manual_required",
                "pending",
                "too_short_or_no_pricing",
                "no_pricing_content_after_render",
                "playwright_not_installed",
            }
            and not competitor.get("raw_scraped_text")
        )
        or competitor.get("is_stale")
    ]
    if retry_candidates:
        print(
            f"[Scraper] Re-attempting {len(retry_candidates)} "
            "competitor(s) before analysis (pending or stale)."
        )
        retry_results = await scrape_competitors_concurrent(retry_candidates)
        retry_map = {str(result["id"]): result for result in retry_results}
        model_map = {str(model.id): model for model in company.competitors}
        changed = False
        for competitor in competitors:
            retry = retry_map.get(competitor["id"])
            if not retry or not retry["status"].startswith("success"):
                continue
            competitor["raw_scraped_text"] = retry["text"]
            competitor["clean_scraped_text"] = retry.get("clean_text", "")
            competitor["scrape_status"] = retry["status"]
            db_competitor = model_map.get(competitor["id"])
            if db_competitor:
                db_competitor.raw_scraped_text = competitor["raw_scraped_text"]
                db_competitor.clean_scraped_text = competitor[
                    "clean_scraped_text"
                ]
                db_competitor.scrape_status = competitor["scrape_status"]
                db_competitor.last_scraped_at = datetime.utcnow()
                changed = True
        if changed:
            await db.commit()

    return {
        "id": str(company.id),
        "name": company.name,
        "industry": company.industry,
        "currency": company.currency or "USD",
        "description": company.description,
        "tiers": tiers,
        "competitors": competitors,
        "owner_email": company.owner.email if company.owner else None,
    }



async def _execute_analysis(
    session_id: str,
    company_id: uuid.UUID,
    groq_client,
    push,
):
    try:
        async with AsyncSessionLocal() as db:
            company_data = await _load_company_data(company_id, db)
    except Exception as e:
        await push(100, "failed")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AnalysisSession).where(AnalysisSession.id == uuid.UUID(session_id))
            )
            sess = result.scalar_one_or_none()
            if sess:
                sess.error_message = str(e)
                sess.completed_at = datetime.utcnow()
                await db.commit()
        return

    any_module_failed = False

    m1_result: dict = {"error": "not run", "module": "M1"}
    m2_result: dict = {"error": "not run", "module": "M2"}
    try:
        m1_result, m2_result = await asyncio.gather(
            asyncio.to_thread(run_module1, company_data),
            run_module2(company_data, groq_client),
        )
    except Exception as e:
        m1_result = {"error": str(e), "module": "M1/M2"}
        m2_result = {"error": str(e), "module": "M1/M2"}
        any_module_failed = True

    if isinstance(m1_result, dict) and "error" in m1_result:
        any_module_failed = True
    if isinstance(m2_result, dict) and "error" in m2_result:
        any_module_failed = True

    await push(50, "m1_m2_complete")

    try:
        m3_result = await run_module3(
            company_data, m1_result, m2_result,
            company_data.get("competitors", []), groq_client
        )
    except Exception as e:
        m3_result = {"error": str(e), "module": "M3"}
        any_module_failed = True

    if isinstance(m3_result, dict) and "error" in m3_result:
        any_module_failed = True

    await push(75, "m3_complete")

    try:
        m4_result = await run_module4(
            company_data, m1_result, m2_result, m3_result, groq_client
        )
    except Exception as e:
        m4_result = {"error": str(e), "module": "M4"}
        any_module_failed = True

    if isinstance(m4_result, dict) and "error" in m4_result:
        any_module_failed = True

    await push(90, "m4_complete")

    full_report = {
        "company": {
            "id": company_data["id"],
            "name": company_data["name"],
            "industry": company_data["industry"],
            "currency": company_data.get("currency", "USD"),
        },
        "generated_at": datetime.utcnow().isoformat(),
        "module1_revenue": m1_result,
        "module2_features": m2_result,
        "module3_benchmark": m3_result,
        "module4_recommendations": m4_result,
    }

    pdf_path = None
    try:
        pdf_path = await asyncio.to_thread(generate_pdf, full_report, session_id)
    except Exception as pdf_err:
        print(f"PDF ERROR: {pdf_err}")
        pdf_path = None

    final_status = "partial" if any_module_failed else "completed"
    report_id = uuid.uuid4()

    async with AsyncSessionLocal() as db:
        report = Report(
            id=report_id,
            session_id=uuid.UUID(session_id),
            json_report=full_report,
            pdf_path=pdf_path,
            created_at=datetime.utcnow(),
        )
        db.add(report)

        result = await db.execute(
            select(AnalysisSession).where(AnalysisSession.id == uuid.UUID(session_id))
        )
        sess = result.scalar_one_or_none()
        if sess:
            sess.status = final_status
            sess.progress = 100
            sess.completed_at = datetime.utcnow()

        await db.commit()

    await push(100, final_status, report_id=str(report_id))

    # Automatically dispatch report email to registered user
    recipient_email = company_data.get("owner_email")
    if not recipient_email:
        try:
            async with AsyncSessionLocal() as db:
                session_result = await db.execute(
                    select(AnalysisSession)
                    .where(AnalysisSession.id == uuid.UUID(session_id))
                    .options(selectinload(AnalysisSession.company).selectinload(Company.owner))
                )
                sess_obj = session_result.scalar_one_or_none()
                if sess_obj and sess_obj.company and sess_obj.company.owner:
                    recipient_email = sess_obj.company.owner.email
        except Exception:
            pass

    if recipient_email:
        try:
            from email_service import send_analysis_complete_email
            module1 = full_report.get("module1_revenue", {})
            report_via_notifyhub = (
                os.getenv("REPORT_VIA_NOTIFYHUB", "").lower() in ("true", "1", "yes")
                and bool(os.getenv("NOTIFYHUB_URL"))
                and bool(os.getenv("NOTIFYHUB_API_KEY"))
            )
            if report_via_notifyhub:
                from notifyhub_client import send_report_email
                await send_report_email(
                    to_email=recipient_email,
                    company_name=company_data["name"],
                    company_id=str(company_data["id"]),
                    session_id=str(session_id),
                    pdf_path=pdf_path,
                    full_report=full_report,
                    currency=company_data.get("currency", "USD"),
                    current_mrr=module1.get("current_mrr", 0),
                    recommended_increase=str(module1.get("recommended_increase", "+20%")),
                    idempotency_key=f"analysis-{session_id}-report",
                )
            else:
                await send_analysis_complete_email(
                    to_email=recipient_email,
                    company_name=company_data["name"],
                    company_id=str(company_data["id"]),
                    session_id=str(session_id),
                    pdf_path=pdf_path,
                    current_mrr=module1.get("current_mrr", 0),
                    recommended_increase=str(module1.get("recommended_increase", "+20%")),
                    currency=company_data.get("currency", "USD"),
                )
        except Exception as email_error:
            print(f"[Email] Automatic dispatch notice: {email_error}")



async def run_full_analysis(
    session_id: str,
    company_id: uuid.UUID,
    groq_client,
):
    queue = progress_queues.get(session_id)

    async def push(progress: int, status_str: str, **kwargs):
        update = {"progress": progress, "status": status_str, **kwargs}
        if queue:
            await queue.put(update)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AnalysisSession).where(AnalysisSession.id == uuid.UUID(session_id))
            )
            sess = result.scalar_one_or_none()
            if sess:
                sess.progress = progress
                sess.status = status_str
                await db.commit()

    await push(0, "running")

    try:
        await asyncio.wait_for(
            _execute_analysis(session_id, company_id, groq_client, push),
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        timeout_message = (
            f"The analysis timed out after {ANALYSIS_TIMEOUT_SECONDS} seconds. "
            "Please run it again."
        )
        print(f"[Analysis] Session {session_id} timed out after {ANALYSIS_TIMEOUT_SECONDS}s.")
        await push(100, "failed")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AnalysisSession).where(AnalysisSession.id == uuid.UUID(session_id))
            )
            sess = result.scalar_one_or_none()
            if sess:
                sess.status = "failed"
                sess.progress = 100
                sess.error_message = timeout_message
                sess.completed_at = datetime.utcnow()
                await db.commit()
    finally:
        if session_id in progress_queues:
            del progress_queues[session_id]



@router.post(
    "/start/{company_id}",
    response_model=AnalysisStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(get_analysis_daily_limit, key_func=get_user_id_key)
async def start_analysis(
    company_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")

    session_id = uuid.uuid4()
    session = AnalysisSession(
        id=session_id,
        company_id=company_id,
        status="running",
        progress=0,
        started_at=datetime.utcnow(),
    )
    db.add(session)
    await db.commit()

    queue: asyncio.Queue = asyncio.Queue()
    progress_queues[str(session_id)] = queue

    groq_client = getattr(request.app.state, "groq_client", None)
    task = asyncio.create_task(
        run_full_analysis(str(session_id), company_id, groq_client)
    )
    background_analysis_tasks.add(task)
    task.add_done_callback(background_analysis_tasks.discard)

    return AnalysisStartResponse(session_id=session_id)



import secrets
from datetime import timedelta
from jose import jwt, JWTError
from routers.auth import SECRET_KEY, ALGORITHM

_PROGRESS_TICKETS: dict[str, dict] = {}


def _cleanup_expired_tickets():
    now = datetime.utcnow()
    expired = [t for t, data in _PROGRESS_TICKETS.items() if data["expires_at"] < now]
    for t in expired:
        _PROGRESS_TICKETS.pop(t, None)


@router.post("/progress-ticket/{session_id}")
@router.post("/ticket/{session_id}")
async def create_progress_ticket(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a random one-time ticket valid for 60 seconds tied to this user and session."""
    sess_result = await db.execute(
        select(AnalysisSession)
        .where(AnalysisSession.id == session_id)
        .options(selectinload(AnalysisSession.company))
    )
    sess = sess_result.scalar_one_or_none()
    if not sess or sess.company.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Analysis session not found")

    _cleanup_expired_tickets()
    ticket = secrets.token_urlsafe(32)
    _PROGRESS_TICKETS[ticket] = {
        "user_id": str(current_user.id),
        "session_id": str(session_id),
        "expires_at": datetime.utcnow() + timedelta(seconds=60),
    }
    return {"ticket": ticket, "expires_in": 60}


@router.get("/progress/{session_id}")
async def stream_progress(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ticket = request.query_params.get("ticket")
    user_id = None

    if ticket:
        _cleanup_expired_tickets()
        ticket_data = _PROGRESS_TICKETS.pop(ticket, None)
        if not ticket_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired progress ticket",
            )
        if ticket_data["session_id"] != str(session_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ticket does not match session",
            )
        user_id = ticket_data["user_id"]
    else:
        # Fallback to Authorization header if present (e.g. direct API / test clients)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                sub = payload.get("sub")
                if sub:
                    user_id = sub
            except JWTError:
                pass

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide a valid ?ticket= parameter.",
            )

    sess_result = await db.execute(
        select(AnalysisSession)
        .where(AnalysisSession.id == session_id)
        .options(selectinload(AnalysisSession.company))
    )
    sess = sess_result.scalar_one_or_none()
    if not sess or str(sess.company.user_id) != str(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    sid = str(session_id)

    async def event_generator():
        queue = progress_queues.get(sid)
        if not queue:
            async with AsyncSessionLocal() as db_gen:
                result = await db_gen.execute(
                    select(AnalysisSession).where(AnalysisSession.id == session_id)
                )
                session_obj = result.scalar_one_or_none()
                if session_obj:
                    yield {
                        "data": json.dumps(
                            {"progress": session_obj.progress, "status": session_obj.status}
                        )
                    }
                else:
                    yield {"data": json.dumps({"progress": 100, "status": "completed"})}
            return

        while True:
            if await request.is_disconnected():
                break
            try:
                update = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield {"data": json.dumps({"progress": 0, "status": "waiting"})}
                continue

            yield {"data": json.dumps(update)}

            if update.get("progress") == 100 or update.get("status") in ("failed", "partial"):
                break

    return EventSourceResponse(event_generator())



@router.get("/report/{session_id}", response_model=ReportResponse)
async def get_report(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Report)
        .where(Report.session_id == session_id)
        .options(selectinload(Report.session))
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    sess_result = await db.execute(
        select(AnalysisSession)
        .where(AnalysisSession.id == session_id)
        .options(selectinload(AnalysisSession.company))
    )
    sess = sess_result.scalar_one_or_none()
    if not sess or sess.company.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return report


@router.get("/report/{session_id}/pdf")
async def download_pdf(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not WEASYPRINT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "PDF generation is not available. WeasyPrint requires the GTK runtime on Windows. "
                "Install from: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer"
            ),
        )

    # Check session ownership first
    sess_result = await db.execute(
        select(AnalysisSession)
        .where(AnalysisSession.id == session_id)
        .options(selectinload(AnalysisSession.company))
    )
    sess = sess_result.scalar_one_or_none()
    if not sess or sess.company.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(Report).where(Report.session_id == session_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # If PDF is missing on disk (e.g. wiped by Render), regenerate from json_report
    if not report.pdf_path or not os.path.exists(report.pdf_path):
        try:
            report.pdf_path = await asyncio.to_thread(
                generate_pdf, report.json_report, str(session_id)
            )
            await db.commit()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Could not regenerate missing PDF report: {e}",
            )

    return FileResponse(
        report.pdf_path,
        media_type="application/pdf",
        filename=f"pricing-report-{session_id}.pdf",
    )


@router.post("/report/{session_id}/email")
async def email_report(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Email report summary and attached PDF to the authenticated user."""
    sess_result = await db.execute(
        select(AnalysisSession)
        .where(AnalysisSession.id == session_id)
        .options(selectinload(AnalysisSession.company))
    )
    sess = sess_result.scalar_one_or_none()
    if not sess or sess.company.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(Report).where(Report.session_id == session_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    pdf_path = report.pdf_path
    if not pdf_path or not os.path.exists(pdf_path):
        if WEASYPRINT_AVAILABLE:
            try:
                pdf_path = await asyncio.to_thread(generate_pdf, report.json_report, str(session_id))
                report.pdf_path = pdf_path
                await db.commit()
            except Exception:
                pdf_path = None

    current_mrr = report.json_report.get("module1_revenue", {}).get("current_mrr", 0)
    rec_increase = report.json_report.get("module1_revenue", {}).get("recommended_scenario", "+20%")

    try:
        report_via_notifyhub = (
            os.getenv("REPORT_VIA_NOTIFYHUB", "").lower() in ("true", "1", "yes")
            and bool(os.getenv("NOTIFYHUB_URL"))
            and bool(os.getenv("NOTIFYHUB_API_KEY"))
        )
        if report_via_notifyhub:
            from notifyhub_client import send_report_email
            manual_key = f"analysis-{session_id}-report-manual-{uuid.uuid4()}"
            await send_report_email(
                to_email=current_user.email,
                company_name=sess.company.name,
                company_id=str(sess.company.id),
                session_id=str(session_id),
                pdf_path=pdf_path,
                full_report=report.json_report,
                currency=sess.company.currency if hasattr(sess.company, "currency") and sess.company.currency else "USD",
                current_mrr=current_mrr,
                recommended_increase=str(rec_increase),
                idempotency_key=manual_key,
            )
        else:
            await send_analysis_complete_email(
                to_email=current_user.email,
                company_name=sess.company.name,
                company_id=str(sess.company.id),
                session_id=str(session_id),
                pdf_path=pdf_path,
                current_mrr=current_mrr,
                recommended_increase=str(rec_increase),
            )
    except Exception as e:
        print(f"[Analysis Email] Dispatch notice: {e}")

    return {
        "status": "sent",
        "recipient": current_user.email,
        "pdf_attached": bool(pdf_path and os.path.exists(pdf_path)),
        "message": f"Report successfully emailed to {current_user.email}"
    }


@router.get("/history/{company_id}", response_model=List[AnalysisHistoryItem])
async def analysis_history(
    company_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comp_result = await db.execute(
        select(Company).where(Company.id == company_id, Company.user_id == current_user.id)
    )
    if not comp_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Company not found")

    result = await db.execute(
        select(AnalysisSession)
        .where(AnalysisSession.company_id == company_id)
        .options(selectinload(AnalysisSession.report))
        .order_by(AnalysisSession.started_at.desc())
    )
    sessions = result.scalars().all()

    items = []
    for sess in sessions:
        mrr = None
        curr = "USD"
        if sess.report and isinstance(sess.report.json_report, dict):
            mrr = sess.report.json_report.get("module1_revenue", {}).get("current_mrr")
            curr = sess.report.json_report.get("company", {}).get("currency") or "USD"

        items.append(
            AnalysisHistoryItem(
                session_id=sess.id,
                status=sess.status,
                progress=sess.progress,
                started_at=sess.started_at,
                completed_at=sess.completed_at,
                report_id=sess.report.id if sess.report else None,
                mrr=mrr,
                currency=curr,
            )
        )
    return items
