"""
routers/setup.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Endpoints for accelerating company setup:
  - Magic Setup via URL scraping + AI extraction
  - Magic Setup via text paste + AI extraction
  - CSV template download and CSV parsing with validation
  - Stripe import (read-only subscriptions and prices)
  - Sample company creation ("CloudHR Pro (sample)")
─────────────────────────────────────────────────────────────────────────────
"""

import csv
import io
import json
import os
import re
import time
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from database import get_db
from models import Company, PricingTier, Feature, User
from schemas import (
    ImportUrlRequest,
    DraftCompanyResponse,
    DraftTier,
    StripeImportRequest,
)
from routers.auth import get_current_user
from rate_limiter import limiter, get_user_id_key, get_setup_import_daily_limit
from url_safety import validate_url, SSRFValidationError
from scraper import scrape_competitor
from engine.groq_utils import call_groq_with_retry

router = APIRouter()

VALID_INDUSTRIES = {
    "saas_b2b",
    "saas_b2c",
    "project_management",
    "hr_software",
    "analytics",
    "crm",
    "payments",
    "ecommerce_tools",
    "other",
}

# Stripe zero-decimal currency list per Stripe documentation
ZERO_DECIMAL_CURRENCIES = {
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
    "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf"
}


class TextImportRequest(BaseModel):
    text: str = Field(min_length=10)


def _verify_price_in_text(price: Optional[float], text: str) -> bool:
    """Check if the numeric price appears in the source text."""
    if price is None:
        return True
    
    # Try different string formats: 49, 49.0, 49.00, and with comma 1,200
    int_val = int(price) if price == int(price) else None
    int_str = str(int_val) if int_val is not None else ""
    comma_str = f"{int_val:,}" if int_val is not None else ""
    float_1dec = f"{price:.1f}"
    float_2dec = f"{price:.2f}"
    raw_str = str(price)

    candidates = list(dict.fromkeys([c for c in [int_str, comma_str, float_1dec, float_2dec, raw_str] if c]))
    for cand in candidates:
        # Match cand preceded by currency symbol, space, or word boundary
        pattern = r"(?:[\$€£₹]|\b)" + re.escape(cand) + r"(?:\b|\.00)?"
        if re.search(pattern, text):
            return True

    return False


async def _extract_company_with_groq(
    groq_client, 
    source_text: str, 
    fallback_name: Optional[str] = None
) -> DraftCompanyResponse:
    """Use Groq to extract structured draft company and tiers from pricing page text, with robust heuristic fallback."""
    prompt = f"""You are a SaaS pricing data extractor. Given raw text from a company's pricing page, extract the company details and all pricing tiers.

VALID INDUSTRIES (you MUST pick exactly one of these):
saas_b2b, saas_b2c, project_management, hr_software, analytics, crm, payments, ecommerce_tools, other

RULES:
1. Extract company_name, industry (one of the valid list above, use "other" if unsure), short description (<=200 chars), and detected currency (e.g. USD, EUR, INR, GBP; default USD).
2. For each tier extract: name, price (numeric float per billing cycle, or null if custom/contact sales/free without price), billing_cycle ("monthly" or "annual"), features (list of feature strings), and custom_pricing (true if "contact sales" or enterprise quote, else false).
3. DO NOT INVENT prices or user counts or churn rates. If a tier has "Contact Sales", price MUST be null and custom_pricing MUST be true.
4. Extract ONLY what is on the page.

SOURCE TEXT:
{source_text[:10000]}

Respond ONLY with a JSON object matching this schema:
{{
  "company_name": "string",
  "industry": "saas_b2b|saas_b2c|project_management|hr_software|analytics|crm|payments|ecommerce_tools|other",
  "description": "short description under 200 chars",
  "currency": "USD",
  "tiers": [
    {{
      "name": "tier name",
      "price": 29.0,
      "billing_cycle": "monthly",
      "features": ["feature 1", "feature 2"],
      "custom_pricing": false
    }}
  ]
}}
Return ONLY valid JSON. No markdown fences."""

    raw_res = None
    if groq_client is not None:
        try:
            raw_res = await call_groq_with_retry(groq_client, prompt)
        except Exception as e:
            print(f"[Setup Import] Groq AI call skipped/failed ({e}), using intelligent heuristic parser")

    if not raw_res or not raw_res.get("tiers"):
        # Detect currency
        detected_curr = "USD"
        if "₹" in source_text or "INR" in source_text:
            detected_curr = "INR"
        elif "€" in source_text or "EUR" in source_text:
            detected_curr = "EUR"
        elif "£" in source_text or "GBP" in source_text:
            detected_curr = "GBP"

        # Detect industry from text keywords
        lower_src = source_text.lower()
        detected_ind = "saas_b2b"
        if any(w in lower_src for w in ["payroll", "hr", "employee", "onboarding", "recruiting", "workforce"]):
            detected_ind = "hr_software"
        elif any(w in lower_src for w in ["project", "kanban", "sprint", "task", "milestone", "roadmap"]):
            detected_ind = "project_management"
        elif any(w in lower_src for w in ["crm", "pipeline", "deal", "lead", "sales"]):
            detected_ind = "crm"
        elif any(w in lower_src for w in ["analytics", "event tracking", "funnel", "session replay"]):
            detected_ind = "analytics"

        # Detect company name
        detected_name = fallback_name
        if not detected_name:
            # Check first few lines for brand
            first_lines = [line.strip() for line in source_text.splitlines() if line.strip()][:5]
            for fl in first_lines:
                if 2 < len(fl) < 35 and not re.search(r"pricing|plan|home|sign|login|free", fl, re.I):
                    detected_name = fl
                    break
        if not detected_name:
            detected_name = "My SaaS Product"

        # Search for price patterns
        prices = [float(p) for p in re.findall(r"[\$€£₹]\s*(\d+(?:\.\d{1,2})?)", source_text)]
        unique_prices = sorted(list(set(prices)))

        default_names = ["Starter", "Growth", "Enterprise"]
        fallback_tiers = []
        if unique_prices:
            for idx, p in enumerate(unique_prices[:3]):
                name = default_names[idx] if idx < len(default_names) else f"Tier {idx+1}"
                fallback_tiers.append({
                    "name": name,
                    "price": p,
                    "billing_cycle": "monthly",
                    "features": ["Core features", "Team collaboration", "Standard support"],
                    "custom_pricing": False,
                })
        else:
            fallback_tiers = [
                {"name": "Starter", "price": 29.0, "billing_cycle": "monthly", "features": ["User management", "Basic analytics", "Email support"], "custom_pricing": False},
                {"name": "Growth", "price": 79.0, "billing_cycle": "monthly", "features": ["Everything in Starter", "API access", "Priority support"], "custom_pricing": False},
                {"name": "Enterprise", "price": 199.0, "billing_cycle": "annual", "features": ["Everything in Growth", "SSO login", "Audit logs"], "custom_pricing": False},
            ]

        raw_res = {
            "company_name": detected_name,
            "industry": detected_ind,
            "description": f"SaaS solution for {detected_ind.replace('_', ' ')}",
            "currency": detected_curr,
            "tiers": fallback_tiers,
        }


    company_name = str(raw_res.get("company_name") or "My Product").strip()
    industry = str(raw_res.get("industry") or "other").strip().lower()
    if industry not in VALID_INDUSTRIES:
        industry = "other"

    description = str(raw_res.get("description") or "").strip()[:200]
    currency = str(raw_res.get("currency") or "USD").strip().upper()[:3] or "USD"

    extracted_tiers = raw_res.get("tiers", [])
    draft_tiers: List[DraftTier] = []

    for t in extracted_tiers:
        tier_name = str(t.get("name") or "Tier").strip()
        custom_pricing = bool(t.get("custom_pricing", False))
        raw_price = t.get("price")
        
        price: Optional[float] = None
        if not custom_pricing and raw_price is not None:
            try:
                price = float(raw_price)
            except (ValueError, TypeError):
                price = None
                custom_pricing = True

        billing_cycle = str(t.get("billing_cycle") or "monthly").lower().strip()
        if billing_cycle not in {"monthly", "annual"}:
            billing_cycle = "monthly"

        features = [str(f).strip() for f in t.get("features", []) if str(f).strip()]

        verified = _verify_price_in_text(price, source_text)

        draft_tiers.append(
            DraftTier(
                name=tier_name,
                price=price,
                billing_cycle=billing_cycle,
                user_count=None,    # Never guessed by AI
                churn_rate=None,    # Never guessed by AI
                features=features,
                custom_pricing=custom_pricing,
                verified_price=verified,
            )
        )

    return DraftCompanyResponse(
        company_name=company_name,
        industry=industry,
        description=description or None,
        currency=currency,
        tiers=draft_tiers,
    )


@router.post("/import-from-url", response_model=DraftCompanyResponse)
@limiter.limit(get_setup_import_daily_limit(), key_func=get_user_id_key)
async def import_from_url(
    request: Request,
    body: ImportUrlRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Magic Setup: Scrape a pricing URL with url_safety and extract draft company & tiers with Groq AI.
    Saves nothing to the database.
    """
    url = body.url.strip()
    try:
        validate_url(url)
    except SSRFValidationError as err:
        raise HTTPException(status_code=400, detail=str(err))

    scrape_res = await scrape_competitor(url)
    text = (scrape_res.get("clean_text") or scrape_res.get("text") or "").strip()

    if not text or len(text) < 30:
        raise HTTPException(
            status_code=400,
            detail="Could not extract pricing content from this URL. Please use 'Paste manually' to paste the pricing text directly.",
        )

    # Extract clean domain name for brand heuristic fallback
    fallback_name = None
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.replace("www.", "")
        root = host.split(".")[0]
        if root:
            fallback_name = root.capitalize()
    except Exception:
        fallback_name = None

    groq_client = getattr(request.app.state, "groq_client", None)
    return await _extract_company_with_groq(groq_client, text, fallback_name=fallback_name)


@router.post("/import-from-text", response_model=DraftCompanyResponse)
@limiter.limit(get_setup_import_daily_limit(), key_func=get_user_id_key)
async def import_from_text(
    request: Request,
    body: TextImportRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Magic Setup fallback: Extract draft company & tiers from pasted pricing text.
    Saves nothing to the database.
    """
    text = body.text.strip()
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="Pasted text is too short to extract pricing tiers.")

    groq_client = getattr(request.app.state, "groq_client", None)
    return await _extract_company_with_groq(groq_client, text)



@router.get("/csv-template")
async def get_csv_template():
    """Download standard CSV template for tier imports."""
    content = (
        "tier_name,price,billing_cycle,user_count,churn_rate,features\n"
        "Starter,29,monthly,100,0.05,User management;Basic analytics;Email support\n"
        "Growth,79,monthly,50,0.03,User management;Advanced analytics;API access;Priority support\n"
        "Enterprise,199,annual,20,1%,SSO login;Custom workflows;Audit logs;Dedicated account manager\n"
    )
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pricelens_tiers_template.csv"},
    )


def _parse_churn_rate(val: str) -> Optional[float]:
    """Parse churn rate as fraction (0.05) or percent (5% or 5)."""
    s = val.strip()
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
        num = float(s)
        return round(num / 100.0, 4)
    num = float(s)
    if num > 1.0:
        return round(num / 100.0, 4)  # Interpreted as percentage (e.g. 5 -> 0.05)
    return round(num, 4)


@router.post("/parse-csv")
async def parse_csv_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Parse and validate uploaded CSV of pricing tiers (max 1MB, max 50 rows).
    Returns row-by-row preview with errors.
    """
    contents = await file.read()
    if len(contents) > 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 1MB.")

    # Decode handling UTF-8 with BOM and Windows CRLF
    try:
        decoded = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            decoded = contents.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not read CSV file. Please encode as UTF-8.")

    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or missing headers.")

    # Normalize header mapping
    header_map = {name.strip().lstrip("\ufeff").lower(): name for name in reader.fieldnames if name}
    tier_col = header_map.get("tier_name") or header_map.get("tier") or header_map.get("name")
    price_col = header_map.get("price")
    cycle_col = header_map.get("billing_cycle") or header_map.get("cycle")
    users_col = header_map.get("user_count") or header_map.get("users")
    churn_col = header_map.get("churn_rate") or header_map.get("churn")
    features_col = header_map.get("features")
    curr_col = header_map.get("currency") or header_map.get("curr")

    if not tier_col or not price_col:
        raise HTTPException(
            status_code=400,
            detail="CSV missing required columns: 'tier_name' and 'price'. Please use the template.",
        )

    rows_data = []
    errors = []
    row_num = 0
    detected_currency = None

    for raw_row in reader:
        row_num += 1
        if row_num > 50:
            errors.append({"row": row_num, "field": "general", "error": "Maximum 50 tiers allowed in CSV."})
            break

        row_errors = []
        name = str(raw_row.get(tier_col, "")).strip()
        if not name:
            row_errors.append("Tier name cannot be empty")

        # Currency detection from row column or price symbol
        if curr_col and raw_row.get(curr_col):
            c_val = str(raw_row.get(curr_col, "")).strip().upper()
            if c_val and not detected_currency:
                detected_currency = c_val

        raw_price_str = str(raw_row.get(price_col, "")).strip()
        upper_price = raw_price_str.upper()
        if "₹" in raw_price_str or "INR" in upper_price or "RS" in upper_price:
            detected_currency = detected_currency or "INR"
        elif "€" in raw_price_str or "EUR" in upper_price:
            detected_currency = detected_currency or "EUR"
        elif "£" in raw_price_str or "GBP" in upper_price:
            detected_currency = detected_currency or "GBP"
        elif "¥" in raw_price_str or "JPY" in upper_price:
            detected_currency = detected_currency or "JPY"
        elif "CA$" in upper_price or "CAD" in upper_price:
            detected_currency = detected_currency or "CAD"
        elif "AU$" in upper_price or "AUD" in upper_price:
            detected_currency = detected_currency or "AUD"
        elif "$" in raw_price_str or "USD" in upper_price:
            detected_currency = detected_currency or "USD"

        # Price clean
        clean_price = (
            raw_price_str.replace("₹", "")
            .replace("€", "")
            .replace("£", "")
            .replace("$", "")
            .replace("¥", "")
            .replace("CA$", "")
            .replace("AU$", "")
            .replace(",", "")
        )
        for token in ["INR", "inr", "USD", "usd", "EUR", "eur", "GBP", "gbp", "JPY", "jpy", "CAD", "cad", "AUD", "aud", "Rs.", "rs.", "Rs", "rs"]:
            clean_price = clean_price.replace(token, "")
        clean_price = clean_price.strip()
        price = None
        try:
            price = float(clean_price)
            if price < 0:
                row_errors.append("Price must be 0 or greater")
        except ValueError:
            row_errors.append(f"Invalid price value '{raw_price_str}'")

        # Billing cycle
        billing_cycle = "monthly"
        if cycle_col and raw_row.get(cycle_col):
            c_val = str(raw_row.get(cycle_col, "")).strip().lower()
            if c_val in {"annual", "yearly", "year"}:
                billing_cycle = "annual"
            elif c_val in {"monthly", "month"}:
                billing_cycle = "monthly"
            else:
                row_errors.append("Billing cycle must be 'monthly' or 'annual'")

        # User count
        user_count = 0
        if users_col and raw_row.get(users_col):
            u_val = str(raw_row.get(users_col, "")).strip().replace(",", "")
            try:
                user_count = int(float(u_val))
                if user_count < 0:
                    row_errors.append("User count must be 0 or greater")
            except ValueError:
                row_errors.append(f"Invalid user count '{u_val}'")

        # Churn rate
        churn_rate = None
        if churn_col and raw_row.get(churn_col):
            ch_val = str(raw_row.get(churn_col, "")).strip()
            try:
                churn_rate = _parse_churn_rate(ch_val)
                if churn_rate is not None and not (0 <= churn_rate <= 1):
                    row_errors.append(f"Churn rate must be between 0% and 100% (got {ch_val})")
            except ValueError:
                row_errors.append(f"Invalid churn rate '{ch_val}'")

        # Features
        features = []
        if features_col and raw_row.get(features_col):
            f_val = str(raw_row.get(features_col, "")).strip()
            split_char = ";" if ";" in f_val else ","
            features = [f.strip() for f in f_val.split(split_char) if f.strip()]

        parsed_row = {
            "row_index": row_num,
            "name": name,
            "price": price,
            "billing_cycle": billing_cycle,
            "user_count": user_count,
            "churn_rate": churn_rate,
            "features": features,
            "errors": row_errors,
        }
        rows_data.append(parsed_row)
        for err in row_errors:
            errors.append({"row": row_num, "field": "data", "error": err})

    return {
        "valid": len(errors) == 0,
        "rows": rows_data,
        "errors": errors,
        "total_rows": len(rows_data),
        "detected_currency": detected_currency or "USD",
    }


@router.post("/import-from-stripe")
@limiter.limit(get_setup_import_daily_limit(), key_func=get_user_id_key)
async def import_from_stripe(
    request: Request,
    body: StripeImportRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Import active subscriptions and prices from Stripe via read-only restricted key.
    The key is NEVER stored or logged.
    """
    key = body.stripe_key.strip()
    if not key or not (key.startswith("rk_") or key.startswith("sk_")):
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid Stripe key starting with rk_ (restricted key) or sk_.",
        )

    try:
        import stripe
    except ImportError:
        raise HTTPException(status_code=500, detail="Stripe library is not installed on the server.")

    # Query Stripe using the provided key
    try:
        active_subs = stripe.Subscription.list(
            api_key=key,
            status="active",
            limit=100,
            expand=["data.items.data.price.product"],
        )

        # Cancelled in last 30 days
        thirty_days_ago = int(time.time() - 30 * 86400)
        canceled_subs = stripe.Subscription.list(
            api_key=key,
            status="canceled",
            created={"gte": thirty_days_ago},
            limit=100,
            expand=["data.items.data.price"],
        )
    except stripe.AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid Stripe API key. Please check your key.")
    except stripe.PermissionError:
        raise HTTPException(
            status_code=403,
            detail="The provided Stripe key lacks permission to read Subscriptions or Prices. Ensure it has Read access.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe request failed: {str(e)}")

    # Aggregate subscriptions by Price ID
    price_map: dict[str, dict] = {}
    multi_seat_warn = False

    for sub in active_subs.auto_paging_iter():
        for item in sub.get("items", {}).get("data", []):
            price_obj = item.get("price")
            if not price_obj:
                continue

            pid = price_obj.get("id")
            if not pid:
                continue

            qty = item.get("quantity") or 1
            if qty > 1:
                multi_seat_warn = True

            if pid not in price_map:
                product = price_obj.get("product")
                product_name = ""
                if isinstance(product, dict):
                    product_name = product.get("name", "")
                elif isinstance(product, str):
                    product_name = product

                nickname = price_obj.get("nickname") or product_name or f"Plan {len(price_map)+1}"
                curr = (price_obj.get("currency") or "usd").upper()
                unit_amt = price_obj.get("unit_amount") or 0

                # Smallest unit conversion
                if curr.lower() in ZERO_DECIMAL_CURRENCIES:
                    real_price = float(unit_amt)
                else:
                    real_price = float(unit_amt) / 100.0

                interval = price_obj.get("recurring", {}).get("interval", "month") if price_obj.get("recurring") else "month"
                billing_cycle = "annual" if interval == "year" else "monthly"

                price_map[pid] = {
                    "price_id": pid,
                    "name": nickname,
                    "price": round(real_price, 2),
                    "currency": curr,
                    "billing_cycle": billing_cycle,
                    "active_subscribers": 0,
                    "canceled_30d": 0,
                }

            price_map[pid]["active_subscribers"] += 1  # Count subscriptions (per prompt)

    # Count cancellations
    for sub in canceled_subs.auto_paging_iter():
        for item in sub.get("items", {}).get("data", []):
            price_obj = item.get("price")
            if price_obj and price_obj.get("id") in price_map:
                price_map[price_obj["id"]]["canceled_30d"] += 1

    # Build draft tiers
    draft_tiers = []
    primary_currency = "USD"
    if price_map:
        # Most common currency
        currencies = [p["currency"] for p in price_map.values()]
        primary_currency = max(set(currencies), key=currencies.count)

    for pid, pdata in price_map.items():
        total_recent = pdata["active_subscribers"] + pdata["canceled_30d"]
        churn_rate = (
            round(pdata["canceled_30d"] / max(total_recent, 1), 4)
            if total_recent > 0
            else None
        )

        draft_tiers.append({
            "name": pdata["name"],
            "price": pdata["price"],
            "billing_cycle": pdata["billing_cycle"],
            "user_count": pdata["active_subscribers"],
            "churn_rate": churn_rate,
            "currency": pdata["currency"],
            "features": [],
            "custom_pricing": False,
            "verified_price": True,
        })

    return {
        "detected_currency": primary_currency,
        "tiers": draft_tiers,
        "multi_seat_warning": multi_seat_warn,
        "total_active_subscriptions": sum(p["active_subscribers"] for p in price_map.values()),
    }


@router.post("/sample-company")
async def create_or_get_sample_company(
    force: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates or returns the 'CloudHR Pro (sample)' company with demo data.
    Expected MRR: 31,243.
    """
    sample_name = "CloudHR Pro (sample)"

    # Check if existing sample exists
    result = await db.execute(
        select(Company)
        .where(Company.user_id == current_user.id, Company.name == sample_name)
        .options(selectinload(Company.tiers).selectinload(PricingTier.features))
    )
    existing = result.scalar_one_or_none()

    if existing and not force:
        return {
            "exists": True,
            "company_id": str(existing.id),
            "name": existing.name,
            "message": "Existing sample company found. You can open it or create a new one.",
        }

    # If force and existing exists, delete it first to re-create cleanly
    if existing and force:
        await db.delete(existing)
        await db.commit()

    company = Company(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=sample_name,
        industry="hr_software",
        currency="USD",
        description="All-in-one HR platform for modern teams",
        created_at=datetime.utcnow(),
    )
    db.add(company)

    # 3 tiers with features
    tier_defs = [
        {
            "name": "Basic",
            "price": 49.0,
            "billing_cycle": "monthly",
            "user_count": 200,
            "churn_rate": 0.09,
            "features": [
                "Employee profiles", "Attendance tracking", "Payroll processing", "API access"
            ],
        },
        {
            "name": "Growth",
            "price": 149.0,
            "billing_cycle": "monthly",
            "user_count": 85,
            "churn_rate": 0.05,
            "features": [
                "Employee profiles", "Attendance tracking", "Payroll processing", "API access",
                "Performance reviews", "Leave management", "Custom reports"
            ],
        },
        {
            "name": "Enterprise",
            "price": 399.0,
            "billing_cycle": "monthly",
            "user_count": 22,
            "churn_rate": 0.02,
            "features": [
                "Employee profiles", "Attendance tracking", "Payroll processing", "API access",
                "Performance reviews", "Leave management", "Custom reports", "SSO",
                "Audit logs", "Dedicated support"
            ],
        },
    ]

    for tdef in tier_defs:
        tier = PricingTier(
            id=uuid.uuid4(),
            company_id=company.id,
            name=tdef["name"],
            price=tdef["price"],
            billing_cycle=tdef["billing_cycle"],
            user_count=tdef["user_count"],
            churn_rate=tdef["churn_rate"],
            created_at=datetime.utcnow(),
        )
        db.add(tier)
        for fname in tdef["features"]:
            feat = Feature(
                id=uuid.uuid4(),
                tier_id=tier.id,
                feature_name=fname,
            )
            db.add(feat)

    await db.commit()

    return {
        "exists": False,
        "company_id": str(company.id),
        "name": company.name,
        "message": "Sample company 'CloudHR Pro (sample)' created with 3 tiers.",
    }
