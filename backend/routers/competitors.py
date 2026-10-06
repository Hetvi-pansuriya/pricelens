"""
routers/competitors.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: REST API endpoints for managing competitor entries and scraping.

Endpoints:
  POST   /companies/{id}/competitors                        → add competitor URL + trigger scrape
  GET    /companies/{id}/competitors                        → list all competitors for a company
  PATCH  /companies/{id}/competitors/{comp_id}/manual      → manually paste competitor pricing text
  DELETE /companies/{id}/competitors/{comp_id}             → delete a competitor entry

WHY PATCH for manual text? PATCH means "partial update" — we're only changing
the scraped text fields, not replacing the entire competitor object (that would be PUT).

CONNECTED TO:
  - main.py      → router mounted at prefix="/companies"
  - models.py    → Competitor model (competitors table)
  - schemas.py   → CompetitorCreate, CompetitorResponse, ManualCompetitorText
  - auth.py      → get_current_user dependency
  - scraper.py   → scrape_competitor() and _clean_pricing_content() used here
  - analysis.py  → reads clean_scraped_text from DB for module3 benchmarking
─────────────────────────────────────────────────────────────────────────────
"""

import uuid

from datetime import datetime

from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, status

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.future import select

from database import get_db

from models import Company, Competitor, User

import json
from schemas import (
    CompetitorCreate,
    CompetitorResponse,
    ManualCompetitorText,
    CompetitorSuggestion,
    CompetitorSuggestionsResponse,
)

from routers.auth import get_current_user

from scraper import _clean_pricing_content, scrape_competitor, _has_pricing_content
from url_safety import (
    validate_url,
    SSRFValidationError,
    ERROR_PRIVATE_OR_UNSUPPORTED,
    is_safe_url,
    safe_requests_get,
)
from engine.groq_utils import call_groq_with_retry
from rate_limiter import limiter, get_user_id_key

router = APIRouter()

MAX_COMPETITORS = 5



async def _assert_company_owner(company_id, user, db):
    """Verify the given user owns the given company. Raises 404 if not found."""
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.user_id == user.id)
    )
    company = result.scalar_one_or_none()  # None if not found or not owned by user
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company  # the Company model object (used by callers if needed)


async def _run_scrape_and_save(competitor_id: uuid.UUID, url: str):
    """Background task: scrape a competitor URL and save the result to the DB.
    
    Called via FastAPI's BackgroundTasks after the 201 response is already sent.
    Uses its own DB session (AsyncSessionLocal) since the request session is closed.
    """
    from database import AsyncSessionLocal

    result = await scrape_competitor(url)

    async with AsyncSessionLocal() as db:
        q = await db.execute(select(Competitor).where(Competitor.id == competitor_id))
        comp = q.scalar_one_or_none()  # None if deleted while scraping was in progress

        if comp:
            comp.raw_scraped_text = result["text"]                    # full raw text (up to 12,000 chars)
            comp.clean_scraped_text = result.get("clean_text", "")   # noise-filtered text (up to 8,000 chars)
            comp.scrape_status = result["status"]                     # e.g., "success_layer1", "manual_required"
            comp.last_scraped_at = datetime.utcnow()
            await db.commit()  # save column updates to PostgreSQL



@router.post("/{company_id}/competitors", response_model=CompetitorResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour", key_func=get_user_id_key)
async def add_competitor(
    company_id: uuid.UUID,                               # company UUID from URL path
    body: CompetitorCreate,                              # contains validated URL (AnyHttpUrl)
    background_tasks: BackgroundTasks,                   # FastAPI background task runner
    request: Request,
    current_user: User = Depends(get_current_user),      # authenticated user
    db: AsyncSession = Depends(get_db),                  # database session
):
    await _assert_company_owner(company_id, current_user, db)

    url_str = str(body.url)
    try:
        validate_url(url_str)
    except SSRFValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_PRIVATE_OR_UNSUPPORTED,
        )

    count_result = await db.execute(
        select(Competitor).where(Competitor.company_id == company_id)
    )
    if len(count_result.scalars().all()) >= MAX_COMPETITORS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_COMPETITORS} competitors allowed per company"
        )

    competitor = Competitor(
        id=uuid.uuid4(),                   # new UUID
        company_id=company_id,             # link to parent company
        url=url_str,                       # the competitor's pricing page URL
        scrape_status="pending",           # initial status before scraping runs
        created_at=datetime.utcnow(),      # creation timestamp
    )
    db.add(competitor)         # stage for INSERT
    await db.commit()          # execute INSERT (competitor now exists in DB)
    await db.refresh(competitor)  # reload to get the generated id

    background_tasks.add_task(_run_scrape_and_save, competitor.id, url_str)

    return competitor


@router.get("/{company_id}/competitors", response_model=List[CompetitorResponse])
async def list_competitors(
    company_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_company_owner(company_id, current_user, db)  # ownership check

    result = await db.execute(
        select(Competitor).where(Competitor.company_id == company_id)
    )
    return result.scalars().all()  # list of Competitor model objects → serialized as CompetitorResponse


@router.patch("/{company_id}/competitors/{competitor_id}/manual", response_model=CompetitorResponse)
async def set_manual_text(
    company_id: uuid.UUID,
    competitor_id: uuid.UUID,
    body: ManualCompetitorText,   # contains the pasted text (min_length=1)
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_company_owner(company_id, current_user, db)  # ownership check

    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.company_id == company_id  # prevents cross-company access
        )
    )
    competitor = result.scalar_one_or_none()

    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")

    competitor.raw_scraped_text = body.text  # full pasted text (no length limit enforced here)

    competitor.clean_scraped_text = _clean_pricing_content(body.text)

    competitor.scrape_status = "manual"  # distinct from "success_layer1" or "success_layer2"

    await db.commit()          # save all 3 fields
    await db.refresh(competitor)  # reload from DB
    return competitor  # serialized as CompetitorResponse


@router.delete("/{company_id}/competitors/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competitor(
    company_id: uuid.UUID,
    competitor_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _assert_company_owner(company_id, current_user, db)  # ownership check

    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.company_id == company_id  # security: company ownership
        )
    )
    comp = result.scalar_one_or_none()

    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")

    await db.delete(comp)  # delete the competitor row
    await db.commit()      # execute DELETE


INDUSTRY_COMPETITOR_DIRECTORY = {
    "hr_software": [
        {"name": "BambooHR", "homepage_url": "https://www.bamboohr.com", "pricing_url": "https://www.bamboohr.com/pricing", "reason": "Leading SMB all-in-one HR and payroll platform", "verified": True},
        {"name": "Gusto", "homepage_url": "https://gusto.com", "pricing_url": "https://gusto.com/pricing", "reason": "Major payroll, benefits, and HR platform", "verified": True},
        {"name": "Rippling", "homepage_url": "https://www.rippling.com", "pricing_url": "https://www.rippling.com/pricing", "reason": "Unified workforce management and employee operations", "verified": True},
        {"name": "Deel", "homepage_url": "https://www.deel.com", "pricing_url": "https://www.deel.com/pricing", "reason": "Global HR and contractor payroll management", "verified": True},
        {"name": "Zenefits", "homepage_url": "https://www.zenefits.com", "pricing_url": "https://www.zenefits.com/pricing", "reason": "Direct competitor for mid-market HR software", "verified": True},
    ],
    "saas_b2b": [
        {"name": "Salesforce", "homepage_url": "https://www.salesforce.com", "pricing_url": "https://www.salesforce.com/editions-pricing/sales-cloud/", "reason": "Enterprise SaaS standard for CRM and customer management", "verified": True},
        {"name": "HubSpot", "homepage_url": "https://www.hubspot.com", "pricing_url": "https://www.hubspot.com/pricing", "reason": "Inbound marketing, CRM, and customer service suite", "verified": True},
        {"name": "Zendesk", "homepage_url": "https://www.zendesk.com", "pricing_url": "https://www.zendesk.com/pricing/", "reason": "Customer support and service engagement leader", "verified": True},
        {"name": "Freshworks", "homepage_url": "https://www.freshworks.com", "pricing_url": "https://www.freshworks.com/freshdesk/pricing/", "reason": "Customer service and IT service management suite", "verified": True},
        {"name": "Zoho One", "homepage_url": "https://www.zoho.com", "pricing_url": "https://www.zoho.com/one/pricing/", "reason": "All-in-one business software suite for growing companies", "verified": True},
    ],
    "project_management": [
        {"name": "Asana", "homepage_url": "https://asana.com", "pricing_url": "https://asana.com/pricing", "reason": "Market leader in enterprise work and task management", "verified": True},
        {"name": "Monday.com", "homepage_url": "https://monday.com", "pricing_url": "https://monday.com/pricing", "reason": "Customizable workflow OS and project tracking", "verified": True},
        {"name": "ClickUp", "homepage_url": "https://clickup.com", "pricing_url": "https://clickup.com/pricing", "reason": "All-in-one productivity and project collaboration platform", "verified": True},
        {"name": "Linear", "homepage_url": "https://linear.app", "pricing_url": "https://linear.app/pricing", "reason": "Streamlined issue tracking for modern product teams", "verified": True},
    ],
    "analytics": [
        {"name": "Mixpanel", "homepage_url": "https://mixpanel.com", "pricing_url": "https://mixpanel.com/pricing/", "reason": "Product analytics and user behavior tracking", "verified": True},
        {"name": "Amplitude", "homepage_url": "https://amplitude.com", "pricing_url": "https://amplitude.com/pricing", "reason": "Digital analytics platform for product optimization", "verified": True},
        {"name": "PostHog", "homepage_url": "https://posthog.com", "pricing_url": "https://posthog.com/pricing", "reason": "Open-source product analytics and session recording suite", "verified": True},
    ],
    "crm": [
        {"name": "Pipedrive", "homepage_url": "https://www.pipedrive.com", "pricing_url": "https://www.pipedrive.com/en/pricing", "reason": "Pipeline-centric CRM designed for sales teams", "verified": True},
        {"name": "Close", "homepage_url": "https://www.close.com", "pricing_url": "https://www.close.com/pricing", "reason": "High-velocity sales CRM with built-in calling and emailing", "verified": True},
    ],
    "ecommerce_tools": [
        {"name": "Shopify", "homepage_url": "https://www.shopify.com", "pricing_url": "https://www.shopify.com/pricing", "reason": "Leading commerce platform for digital store management", "verified": True},
        {"name": "BigCommerce", "homepage_url": "https://www.bigcommerce.com", "pricing_url": "https://www.bigcommerce.com/pricing/", "reason": "Scalable SaaS eCommerce platform for high-growth brands", "verified": True},
    ],
    "payments": [
        {"name": "Stripe", "homepage_url": "https://stripe.com", "pricing_url": "https://stripe.com/pricing", "reason": "Global financial infrastructure and payment processing leader", "verified": True},
        {"name": "Paddle", "homepage_url": "https://paddle.com", "pricing_url": "https://paddle.com/pricing", "reason": "Merchant of record and subscription billing platform", "verified": True},
    ],
}


@router.post("/{company_id}/competitors/suggest", response_model=CompetitorSuggestionsResponse)
async def suggest_competitors(
    request: Request,
    company_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Auto-find competitors: AI suggests competitors or uses fast industry directory fallback.
    """
    company = await _assert_company_owner(company_id, current_user, db)

    raw_suggestions = []
    groq_client = getattr(request.app.state, "groq_client", None)
    if groq_client:
        prompt = f"""You are a market intelligence expert. Suggest up to 8 real SaaS direct competitors for this company.

COMPANY NAME: {company.name}
INDUSTRY: {company.industry}
DESCRIPTION: {company.description or 'N/A'}

For each competitor, provide:
1. "name": Competitor company name
2. "homepage_url": Official homepage URL (https://...)
3. "pricing_url": Direct URL to their pricing page (https://.../pricing or best guess)
4. "reason": Exactly one short sentence explaining why they are a direct competitor

Respond ONLY with a JSON object matching this schema:
{{
  "suggestions": [
    {{
      "name": "CompetitorName",
      "homepage_url": "https://competitor.com",
      "pricing_url": "https://competitor.com/pricing",
      "reason": "Direct competitor offering similar core SaaS features."
    }}
  ]
}}
Return ONLY valid JSON. No markdown fences."""

        try:
            raw_res = await call_groq_with_retry(groq_client, prompt)
            raw_suggestions = raw_res.get("suggestions", [])
        except Exception as e:
            print(f"[Competitor Suggestion] AI call skipped/failed: {e}")

    # Fallback to curated industry directory if AI returned nothing
    if not raw_suggestions:
        ind_key = company.industry.lower().strip() if company.industry else "saas_b2b"
        raw_suggestions = (
            INDUSTRY_COMPETITOR_DIRECTORY.get(ind_key)
            or INDUSTRY_COMPETITOR_DIRECTORY.get("saas_b2b", [])
        )

    verified_suggestions = []
    for item in raw_suggestions[:8]:
        name = str(item.get("name") or "").strip()
        homepage_url = str(item.get("homepage_url") or "").strip()
        pricing_url = str(item.get("pricing_url") or "").strip()
        reason = str(item.get("reason") or "Direct competitor in your market segment.").strip()
        verified = bool(item.get("verified", True))

        if not name or not pricing_url:
            continue

        verified_suggestions.append(
            CompetitorSuggestion(
                name=name,
                homepage_url=homepage_url or pricing_url,
                pricing_url=pricing_url,
                reason=reason,
                verified=verified,
            )
        )

    return CompetitorSuggestionsResponse(suggestions=verified_suggestions)



@router.post("/{company_id}/competitors/{competitor_id}/refresh", response_model=CompetitorResponse)
async def refresh_competitor(
    company_id: uuid.UUID,
    competitor_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually refresh/re-scrape a single competitor and update last_scraped_at.
    """
    await _assert_company_owner(company_id, current_user, db)

    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.company_id == company_id,
        )
    )
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")

    scrape_res = await scrape_competitor(competitor.url)

    competitor.raw_scraped_text = scrape_res.get("text", "")
    competitor.clean_scraped_text = scrape_res.get("clean_text", "")
    competitor.scrape_status = scrape_res.get("status", "failed")
    competitor.last_scraped_at = datetime.utcnow()

    await db.commit()
    await db.refresh(competitor)
    return competitor

