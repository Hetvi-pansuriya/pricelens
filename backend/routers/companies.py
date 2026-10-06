"""
routers/companies.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: REST API endpoints for managing companies, pricing tiers, and features.

Endpoints:
  POST   /companies                              → create a new company
  GET    /companies                              → list all user's companies
  GET    /companies/{id}                         → get company with tiers+features+competitors
  PUT    /companies/{id}                         → update company name/industry/description
  DELETE /companies/{id}                         → delete company + all related data
  POST   /companies/{id}/tiers                   → add a new pricing tier
  PUT    /companies/{id}/tiers/{tid}             → update an existing tier
  DELETE /companies/{id}/tiers/{tid}             → delete a tier
  POST   /companies/{id}/tiers/{tid}/features    → add a feature to a tier
  DELETE /companies/{id}/tiers/{tid}/features/{fid} → delete a feature

CONNECTED TO:
  - main.py      → registers this router with prefix="/companies"
  - models.py    → Company, PricingTier, Feature database models
  - schemas.py   → Pydantic validation schemas for requests/responses
  - auth.py      → get_current_user dependency for authentication
  - database.py  → get_db dependency for DB sessions
─────────────────────────────────────────────────────────────────────────────
"""

import uuid

from datetime import datetime

from typing import List, Optional
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.future import select

from sqlalchemy.orm import selectinload

from sqlalchemy import func

from database import get_db

from models import Company, PricingTier, Feature, Competitor, User

from schemas import (
    CompanyCreate, CompanyResponse, CompanyDetailResponse,  # company-level schemas
    TierCreate, TierResponse,                                # tier-level schemas
    FeatureCreate, FeatureResponse,                          # feature-level schemas
    BulkFeaturesRequest, BulkFeaturesResponse,
    FeatureSuggestionsResponse,
)

from routers.auth import get_current_user
from industry_features import get_industry_features
from engine.groq_utils import call_groq_with_retry

router = APIRouter()

MAX_COMPETITORS = 5



async def get_company_or_404(company_id: uuid.UUID, user: User, db: AsyncSession) -> Company:
    """Fetch a company by ID and user ownership, with all tiers/features/competitors eager-loaded.
    Raises 404 if the company doesn't exist or belongs to a different user."""
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id, Company.user_id == user.id)
        .options(
            selectinload(Company.tiers).selectinload(PricingTier.features),  # tiers + their features
            selectinload(Company.competitors),  # all competitor entries for this company
        )
    )
    company = result.scalar_one_or_none()  # returns Company or None

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return company  # the Company model object with tiers/features/competitors loaded


async def get_tier_or_404(tier_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession) -> PricingTier:
    """Fetch a tier by ID and company ownership. Raises 404 if not found."""
    result = await db.execute(
        select(PricingTier)
        .where(PricingTier.id == tier_id, PricingTier.company_id == company_id)
        .options(selectinload(PricingTier.features))  # also load features for response
    )
    tier = result.scalar_one_or_none()

    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")

    return tier  # the PricingTier model object with features loaded


async def verify_company_ownership(company_id: uuid.UUID, user: User, db: AsyncSession) -> Company:
    """Lightweight ownership check without loading related data. Raises 404 if not found."""
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.user_id == user.id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return company  # returns Company model (no tiers/competitors loaded)



@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate,                           # validated request body
    current_user: User = Depends(get_current_user),  # authenticated user
    db: AsyncSession = Depends(get_db),            # database session
):
    company = Company(
        id=uuid.uuid4(),          # generate a new random UUID
        user_id=current_user.id,  # link to the authenticated user
        name=body.name,           # company name from request body (1–100 chars)
        industry=body.industry,   # industry type (e.g., "saas_b2b")
        currency=body.currency or "USD", # currency (default USD)
        description=body.description,  # optional description
        created_at=datetime.utcnow(),   # record creation timestamp
    )
    db.add(company)       # stage for INSERT
    await db.commit()     # execute INSERT to PostgreSQL
    await db.refresh(company)  # reload from DB to get any DB-generated fields
    return company  # FastAPI converts this to JSON using CompanyResponse schema


@router.get("", response_model=List[CompanyResponse])
async def list_companies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Company).where(Company.user_id == current_user.id)
    )
    return result.scalars().all()  # returns list of Company objects (serialized as CompanyResponse)


@router.get("/{company_id}", response_model=CompanyDetailResponse)
async def get_company(
    company_id: uuid.UUID,  # parsed from URL path parameter (FastAPI auto-converts string → UUID)
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_company_or_404(company_id, current_user, db)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.user_id == current_user.id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    await db.delete(company)  # marks the row for deletion
    await db.commit()         # executes DELETE (CASCADE handles all related rows)


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyCreate,  # reuse CompanyCreate schema for update (same fields)
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Company).where(
            Company.id == company_id,
            Company.user_id == current_user.id,  # ownership check
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.name = body.name
    company.industry = body.industry
    if body.currency:
        company.currency = body.currency
    company.description = body.description

    await db.commit()         # executes UPDATE
    await db.refresh(company) # reload from DB to confirm saved values
    return company



@router.post("/{company_id}/tiers", response_model=TierResponse, status_code=status.HTTP_201_CREATED)
async def add_tier(
    company_id: uuid.UUID,
    body: TierCreate,  # tier name, price, billing_cycle, user_count, churn_rate
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_company_ownership(company_id, current_user, db)

    tier = PricingTier(
        id=uuid.uuid4(),                       # new UUID
        company_id=company_id,                 # link to the parent company
        name=body.name,                        # e.g., "Basic"
        price=body.price,                      # e.g., 49.0
        billing_cycle=body.billing_cycle,      # "monthly" or "annual"
        user_count=body.user_count,            # e.g., 200
        churn_rate=body.churn_rate,            # e.g., 0.05 (optional)
        created_at=datetime.utcnow(),          # creation timestamp
    )
    db.add(tier)      # stage for INSERT
    await db.commit() # execute INSERT

    result2 = await db.execute(
        select(PricingTier)
        .where(PricingTier.id == tier.id)
        .options(selectinload(PricingTier.features))  # load features (empty for new tier)
    )
    return result2.scalar_one()  # return the re-fetched tier (includes features=[])


@router.put("/{company_id}/tiers/{tier_id}", response_model=TierResponse)
async def update_tier(
    company_id: uuid.UUID,
    tier_id: uuid.UUID,
    body: TierCreate,  # same schema as create (all fields required for PUT)
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_company_ownership(company_id, current_user, db)  # check user owns the company
    tier = await get_tier_or_404(tier_id, company_id, db)         # get tier or 404

    tier.name = body.name
    tier.price = body.price
    tier.billing_cycle = body.billing_cycle
    tier.user_count = body.user_count
    tier.churn_rate = body.churn_rate

    await db.commit()     # execute UPDATE
    await db.refresh(tier) # reload from DB

    result = await db.execute(
        select(PricingTier)
        .where(PricingTier.id == tier_id)
        .options(selectinload(PricingTier.features))
    )
    return result.scalar_one()


@router.delete("/{company_id}/tiers/{tier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tier(
    company_id: uuid.UUID,
    tier_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_company_ownership(company_id, current_user, db)  # ownership check
    tier = await get_tier_or_404(tier_id, company_id, db)          # get tier or 404

    await db.delete(tier)  # delete the tier (CASCADE deletes all its features)
    await db.commit()      # execute DELETE



@router.post(
    "/{company_id}/tiers/{tier_id}/features",
    response_model=FeatureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_feature(
    company_id: uuid.UUID,
    tier_id: uuid.UUID,
    body: FeatureCreate,  # feature_name (required), description (optional)
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_company_ownership(company_id, current_user, db)  # check user owns company

    result2 = await db.execute(
        select(PricingTier).where(PricingTier.id == tier_id, PricingTier.company_id == company_id)
    )
    if not result2.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tier not found")

    dup = await db.execute(
        select(Feature).where(
            Feature.tier_id == tier_id,
            func.lower(Feature.feature_name) == func.lower(body.feature_name)  # case-insensitive
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=409,  # 409 Conflict — resource already exists
            detail=f"Feature '{body.feature_name}' already exists in this tier"
        )

    feature = Feature(
        id=uuid.uuid4(),               # new UUID
        tier_id=tier_id,               # link to the parent tier
        feature_name=body.feature_name,  # e.g., "API Access"
        description=body.description,  # optional description (may be None)
    )
    db.add(feature)         # stage for INSERT
    await db.commit()       # execute INSERT
    await db.refresh(feature)  # reload from DB
    return feature  # serialized as FeatureResponse (id, feature_name, description)


@router.delete(
    "/{company_id}/tiers/{tier_id}/features/{feature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_feature(
    company_id: uuid.UUID,
    tier_id: uuid.UUID,
    feature_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await verify_company_ownership(company_id, current_user, db)  # ownership check

    result = await db.execute(
        select(Feature).where(Feature.id == feature_id, Feature.tier_id == tier_id)
    )
    feature = result.scalar_one_or_none()

    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    await db.delete(feature)  # delete the feature row
    await db.commit()         # execute DELETE


@router.post("/{company_id}/duplicate", response_model=CompanyDetailResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_company(
    company_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Duplicate a company: copies tiers, features, and competitor URLs.
    Does NOT copy scraped competitor text or previous reports.
    New name = '<old name> (copy)'
    """
    old_company = await get_company_or_404(company_id, current_user, db)

    new_company = Company(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=f"{old_company.name} (copy)",
        industry=old_company.industry,
        currency=getattr(old_company, "currency", "USD"),
        description=old_company.description,
        created_at=datetime.utcnow(),
    )
    db.add(new_company)

    # Copy tiers and features
    for old_tier in old_company.tiers:
        new_tier = PricingTier(
            id=uuid.uuid4(),
            company_id=new_company.id,
            name=old_tier.name,
            price=old_tier.price,
            billing_cycle=old_tier.billing_cycle,
            user_count=old_tier.user_count,
            churn_rate=old_tier.churn_rate,
            created_at=datetime.utcnow(),
        )
        db.add(new_tier)
        for old_feat in old_tier.features:
            new_feat = Feature(
                id=uuid.uuid4(),
                tier_id=new_tier.id,
                feature_name=old_feat.feature_name,
                description=old_feat.description,
            )
            db.add(new_feat)

    # Copy competitor URLs (pending state, not text)
    for old_comp in old_company.competitors:
        new_comp = Competitor(
            id=uuid.uuid4(),
            company_id=new_company.id,
            name=old_comp.name,
            url=old_comp.url,
            raw_scraped_text=None,
            clean_scraped_text=None,
            scrape_status="pending",
            last_scraped_at=None,
            created_at=datetime.utcnow(),
        )
        db.add(new_comp)

    await db.commit()

    return await get_company_or_404(new_company.id, current_user, db)


@router.post(
    "/{company_id}/tiers/{tier_id}/features/bulk",
    response_model=BulkFeaturesResponse,
    status_code=status.HTTP_200_OK,
)
async def add_features_bulk(
    company_id: uuid.UUID,
    tier_id: uuid.UUID,
    body: BulkFeaturesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk adds features to a tier. Strips whitespace, ignores duplicates within the tier,
    and returns lists of added and skipped features.
    """
    await verify_company_ownership(company_id, current_user, db)
    tier = await get_tier_or_404(tier_id, company_id, db)

    existing_features = {f.feature_name.lower().strip() for f in tier.features}

    added = []
    skipped = []

    for raw_name in body.features:
        name = str(raw_name).strip()
        if not name:
            continue

        if name.lower() in existing_features:
            skipped.append(name)
        else:
            feat = Feature(
                id=uuid.uuid4(),
                tier_id=tier_id,
                feature_name=name,
            )
            db.add(feat)
            existing_features.add(name.lower())
            added.append(feat)

    if added:
        await db.commit()
        for f in added:
            await db.refresh(f)

    return BulkFeaturesResponse(added=added, skipped=skipped)


@router.post(
    "/{company_id}/tiers/{tier_id}/features/suggest",
    response_model=FeatureSuggestionsResponse,
)
async def suggest_features(
    request: Request,
    company_id: uuid.UUID,
    tier_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Suggests up to 8 relevant features for a tier based on company industry, description,
    tier name and price, excluding features already present in the tier.
    Falls back to industryFeatures.js catalog on AI unavailability.
    """
    company = await get_company_or_404(company_id, current_user, db)
    tier = await get_tier_or_404(tier_id, company_id, db)

    existing_names = {f.feature_name.lower().strip() for f in tier.features}
    static_pool = [
        f for f in get_industry_features(company.industry)
        if f.lower().strip() not in existing_names
    ]

    groq_client = getattr(request.app.state, "groq_client", None)
    if not groq_client:
        return FeatureSuggestionsResponse(suggestions=static_pool[:8])

    prompt = f"""You are a SaaS product manager. Suggest up to 8 compelling features to add to this specific pricing tier.
Do NOT suggest any features that are already in the tier.

COMPANY: {company.name}
INDUSTRY: {company.industry}
DESCRIPTION: {company.description or 'N/A'}
TIER: {tier.name} (${tier.price}/{tier.billing_cycle})
EXISTING FEATURES IN THIS TIER: {json.dumps([f.feature_name for f in tier.features])}

Respond ONLY with a JSON object matching this schema:
{{
  "suggestions": ["Feature 1", "Feature 2", "Feature 3"]
}}
Return ONLY valid JSON. No markdown fences."""

    try:
        raw_res = await call_groq_with_retry(groq_client, prompt)
        suggestions = raw_res.get("suggestions", [])
        filtered = [
            str(s).strip() for s in suggestions
            if str(s).strip() and str(s).strip().lower() not in existing_names
        ][:8]
        if filtered:
            return FeatureSuggestionsResponse(suggestions=filtered)
    except Exception as e:
        print(f"[Feature Suggestion] AI fallback due to: {e}")

    return FeatureSuggestionsResponse(suggestions=static_pool[:8])

