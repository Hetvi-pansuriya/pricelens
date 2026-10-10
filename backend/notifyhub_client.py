"""
notifyhub_client.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Dispatches analysis-report emails through the NotifyHub HTTP API.

Handles:
  - Formats report metrics into NotifyHub event payload
  - Attaches base64-encoded PDF if within size limits
  - Idempotent request submission with retry on network connection errors
  - Safe fallback to the default email sender on 4xx (except 429), 5xx, or unreachable service
  - Strict privacy: never logs API keys, PDF bytes, report text, or full email addresses
"""

import asyncio
import base64
import datetime
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from email_service import send_analysis_complete_email

ENGLISH_MONTHS = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

CURRENCY_SYMBOLS: Dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "CAD": "CA$",
    "AUD": "AU$",
    "JPY": "¥",
    "CHF": "CHF ",
    "SGD": "S$",
    "AED": "AED ",
    "BRL": "R$",
    "CNY": "¥",
}


def _format_period(date_str: Optional[str]) -> str:
    """Formats date as English month and year (e.g., 'October 2026'), independent of server locale."""
    dt = None
    if date_str:
        try:
            # Handle standard ISO strings (e.g., 2026-10-10T00:15:08.123456 or 2026-10-10)
            cleaned_date = date_str.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(cleaned_date)
        except Exception:
            pass

    if dt is None:
        dt = datetime.datetime.now(datetime.timezone.utc)

    month_name = ENGLISH_MONTHS[dt.month] if 1 <= dt.month <= 12 else "October"
    return f"{month_name} {dt.year}"


def _format_current_mrr(
    mrr_val: Any, currency: str = "USD", symbol: Optional[str] = None
) -> str:
    """Formats current MRR with currency symbol and thousands separators, omitting decimals for whole numbers."""
    sym = symbol or CURRENCY_SYMBOLS.get(str(currency).upper(), "$")
    try:
        val = float(mrr_val)
    except (ValueError, TypeError):
        val = 0.0

    if val.is_integer():
        return f"{sym}{int(val):,}"
    return f"{sym}{val:,.2f}"


def _truncate_headline(text: Optional[str], max_chars: int = 500) -> str:
    """
    Truncates text to at most max_chars.
    Cuts at the last full sentence that fits; if no full sentence fits, cuts at the last full word.
    """
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped

    candidate = stripped[:max_chars]
    sentence_ends = list(re.finditer(r"[\.!?](?:\s|$)", candidate))
    if sentence_ends:
        end_idx = sentence_ends[-1].end()
        cut_sentence = candidate[:end_idx].strip()
        if cut_sentence:
            return cut_sentence

    last_space = candidate.rfind(" ")
    if last_space > 0:
        return candidate[:last_space].strip()

    return candidate


def _clean_and_format_step(raw_step: Optional[str], step_number: int) -> str:
    """
    Removes existing numbering or bullets from step text and formats as '<step_number>. <text>'.
    Shortened to at most 500 characters. Returns '' if input is empty.
    """
    if not raw_step:
        return ""
    text = str(raw_step).strip()
    if not text:
        return ""
    # Strip existing bullets or numbers (e.g. '1.', '1)', '-', '*', '•')
    cleaned = re.sub(r"^\s*(?:\d+[\.\)]|\*|-|•|–|—)\s*", "", text).strip()
    if not cleaned:
        return ""
    return f"{step_number}. {cleaned}"[:500]


def _format_expected_change(val: Any) -> str:
    """Formats expected percentage change with an explicit sign ('+8%', '-3%')."""
    if val is None or val == "":
        return ""
    s = str(val).strip()
    if not s:
        return ""
    # If already formatted with sign and percentage
    if re.match(r"^[+-]\d+(?:\.\d+)?%$", s):
        return s
    cleaned = s.replace("%", "").strip()
    try:
        num = float(cleaned)
        return f"{num:+.0f}%" if num.is_integer() else f"{num:+.1f}%"
    except ValueError:
        return s


def _select_strategy(m4_data: Dict[str, Any]) -> Dict[str, Any]:
    """Selects top/recommended strategy from module 4 data."""
    strategies = m4_data.get("strategies") or []
    if not strategies or not isinstance(strategies, list):
        return {}

    # Check for explicit top/recommended indicator within strategies
    for s in strategies:
        if isinstance(s, dict) and (
            s.get("is_recommended")
            or s.get("recommended")
            or s.get("is_top")
            or s.get("top")
        ):
            return s

    # Check for top/recommended name in module root
    top_name = m4_data.get("recommended_strategy") or m4_data.get("top_strategy")
    if top_name:
        for s in strategies:
            if isinstance(s, dict) and (
                s.get("name") == top_name or s.get("type") == top_name
            ):
                return s

    return strategies[0] if isinstance(strategies[0], dict) else {}


async def send_report_email(
    to_email: str,
    company_name: str,
    company_id: str,
    session_id: str,
    pdf_path: Optional[str] = None,
    full_report: Optional[Dict[str, Any]] = None,
    currency: str = "USD",
    current_mrr: Optional[Any] = None,
    recommended_increase: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> bool:
    """
    Sends the analysis report email through NotifyHub HTTP API with PDF attached.
    Falls back to send_analysis_complete_email on 4xx (except 429), 5xx, or network failure.
    """
    if "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            from pathlib import Path
            from dotenv import load_dotenv
            env_file = Path(__file__).resolve().parent / ".env"
            if env_file.exists():
                load_dotenv(dotenv_path=env_file, override=True)
        except Exception:
            pass

    report = full_report or {}
    report_via_notifyhub = os.getenv("REPORT_VIA_NOTIFYHUB", "").lower() in (
        "true",
        "1",
        "yes",
    )
    notifyhub_url = os.getenv("NOTIFYHUB_URL", "").rstrip("/")
    notifyhub_api_key = os.getenv("NOTIFYHUB_API_KEY", "")

    async def _fallback() -> bool:
        try:
            await send_analysis_complete_email(
                to_email=to_email,
                company_name=company_name,
                company_id=company_id,
                session_id=session_id,
                pdf_path=pdf_path,
                current_mrr=current_mrr if current_mrr is not None else 0,
                recommended_increase=str(recommended_increase or "+20%"),
                currency=currency,
            )
            return True
        except Exception as fb_err:
            print(f"[NotifyHub Fallback] Dispatch notice: {fb_err}")
            return False

    # If flag is disabled or credentials missing, run fallback directly
    if not (report_via_notifyhub and notifyhub_url and notifyhub_api_key):
        return await _fallback()

    # 1. Report link
    frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
    report_url = f"{frontend_url}/reports/{session_id}" if frontend_url else ""

    # 2. PDF attachment processing
    max_attachment_mb = float(os.getenv("NOTIFYHUB_MAX_ATTACHMENT_MB", "5"))
    max_attachment_bytes = int(max_attachment_mb * 1024 * 1024)

    attachments: List[Dict[str, str]] = []
    attachment_note = ""

    if pdf_path and os.path.exists(pdf_path):
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            if len(pdf_bytes) > max_attachment_bytes:
                if report_url:
                    attachment_note = "The report was too large to attach, please open it using the link below."
                else:
                    attachment_note = "The report was too large to attach, but is available directly in the PriceLens app."
            else:
                slug = (
                    re.sub(r"[^a-zA-Z0-9_\-]+", "-", company_name.lower()).strip("-")
                    or "report"
                )
                safe_filename = f"pricelens-report-{slug}.pdf"
                pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
                attachments.append(
                    {
                        "filename": safe_filename,
                        "content_type": "application/pdf",
                        "content_base64": pdf_b64,
                    }
                )
                attachment_note = "The full report is attached to this email as a PDF."
        except Exception:
            attachment_note = (
                "The report is available in the app, please open it using the link below."
                if report_url
                else "The report is available directly in the PriceLens app."
            )
    else:
        attachment_note = (
            "The report is available in the app, please open it using the link below."
            if report_url
            else "The report is available directly in the PriceLens app."
        )

    # 3. Strategy extraction
    m4 = report.get("module4_recommendations", {})
    strat = _select_strategy(m4)
    strat_steps = (
        strat.get("implementation_steps")
        if isinstance(strat.get("implementation_steps"), list)
        else []
    )

    top_strategy = (
        str(strat.get("name", "")).strip()[:500] if strat.get("name") else ""
    )
    predicted_change = strat.get("predicted_mrr_change_pct") or strat.get(
        "expected_mrr_gain_pct"
    )
    if predicted_change is not None:
        expected_change = _format_expected_change(predicted_change)
    else:
        expected_change = _format_expected_change(recommended_increase)

    change_low = str(strat.get("change_low") or strat.get("mrr_change_low") or "")
    change_high = str(strat.get("change_high") or strat.get("mrr_change_high") or "")

    step_1 = (
        _clean_and_format_step(strat_steps[0], 1) if len(strat_steps) > 0 else ""
    )
    step_2 = (
        _clean_and_format_step(strat_steps[1], 2) if len(strat_steps) > 1 else ""
    )
    step_3 = (
        _clean_and_format_step(strat_steps[2], 3) if len(strat_steps) > 2 else ""
    )

    # 4. Headline and revenue metrics
    headline = _truncate_headline(m4.get("executive_summary"))
    m1 = report.get("module1_revenue", {})
    resolved_mrr = current_mrr if current_mrr is not None else m1.get("current_mrr", 0)
    currency_symbol = m1.get("currency_symbol")
    formatted_mrr = _format_current_mrr(
        resolved_mrr, currency=currency, symbol=currency_symbol
    )
    period = _format_period(report.get("generated_at"))

    data_payload: Dict[str, str] = {
        "app_name": "PriceLens",
        "name": "there",
        "company_name": company_name,
        "report_title": "Pricing Analysis Report",
        "period": period,
        "headline": headline,
        "current_mrr": formatted_mrr,
        "top_strategy": top_strategy,
        "expected_change": expected_change,
        "change_low": change_low,
        "change_high": change_high,
        "step_1": step_1,
        "step_2": step_2,
        "step_3": step_3,
        "data_basis": str(
            report.get(
                "data_basis",
                "industry benchmarks and AI estimates, not your own customer survey",
            )
        ),
        "attachment_note": attachment_note,
        "report_url": report_url,
    }

    event_payload = {
        "event_type": "analysis_report",
        "email": to_email,
        "data": data_payload,
        "attachments": attachments,
    }

    active_idempotency_key = idempotency_key or f"analysis-{session_id}-report"
    headers = {
        "X-API-Key": notifyhub_api_key,
        "Content-Type": "application/json",
        "Idempotency-Key": active_idempotency_key,
    }

    timeout_seconds = float(os.getenv("NOTIFYHUB_TIMEOUT_SECONDS", "90"))
    endpoint = f"{notifyhub_url}/api/events"

    # 5. Dispatch with retry and fallback handling
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    endpoint, json=event_payload, headers=headers
                )

            # Success responses
            if response.status_code in (200, 202):
                print(
                    f"[NotifyHub] Report accepted for session {session_id} (status: {response.status_code})"
                )
                return True

            # Rate limited
            if response.status_code == 429:
                print(
                    f"[NotifyHub] Rate limited (429) for session {session_id}. Fallback skipped."
                )
                return False

            # Other 4xx or 5xx: fall back once
            print(
                f"[NotifyHub] Error status {response.status_code} ({response.text}) for session {session_id}. Falling back to default sender."
            )
            return await _fallback()

        except (httpx.ConnectError, httpx.ConnectTimeout) as conn_err:
            if attempt < max_attempts:
                print(
                    f"[NotifyHub] Connection attempt {attempt}/{max_attempts} failed for session {session_id}. Retrying..."
                )
                await asyncio.sleep(0.5)
                continue
            print(
                f"[NotifyHub] All {max_attempts} connection attempts failed for session {session_id}. Falling back to default sender."
            )
            return await _fallback()

        except httpx.ReadTimeout:
            # Do NOT fall back after a read timeout to prevent duplicate emails
            print(
                f"[NotifyHub] Read timeout for session {session_id}. Fallback skipped to prevent duplicates."
            )
            return False

        except Exception as unexp_err:
            print(
                f"[NotifyHub] Unexpected error for session {session_id}: {type(unexp_err).__name__}. Falling back."
            )
            return await _fallback()

    return False
