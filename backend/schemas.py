"""
schemas.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Defines Pydantic "schemas" — data shapes for API request bodies
         and API response bodies.

WHY Pydantic schemas? Three reasons:
  1. VALIDATION: FastAPI auto-validates incoming JSON against these schemas.
     If the frontend sends an invalid email or missing field, FastAPI returns
     a 422 error before the route function even runs.
  2. SERIALIZATION: Pydantic converts SQLAlchemy model objects into JSON
     for API responses (enabled by model_config = {"from_attributes": True}).
  3. DOCUMENTATION: FastAPI uses these schemas to auto-generate the /docs
     Swagger UI with correct request/response shapes.

DIFFERENCE between schemas.py and models.py:
  - models.py  → defines DATABASE tables (SQLAlchemy, talks to PostgreSQL)
  - schemas.py → defines API contract (Pydantic, talks to the frontend)
  They are separate so DB internals (like password_hash) are never exposed in API.

CONNECTED TO:
  - All 4 routers import from here as parameter/response types.
  - FastAPI uses these for validation and documentation automatically.
─────────────────────────────────────────────────────────────────────────────
"""

from pydantic import BaseModel, EmailStr, Field, field_validator, AnyHttpUrl

from typing import Optional, List, Any

from datetime import datetime

import uuid



class UserCreate(BaseModel):
    email: EmailStr          # must be a valid email format
    password: str = Field(min_length=6)  # password must be at least 6 characters


class LoginRequest(BaseModel):
    email: EmailStr    # validated email format
    password: str      # no min_length — let auth logic handle wrong passwords


class UserResponse(BaseModel):
    id: uuid.UUID           # user's UUID
    email: EmailStr         # user's email
    created_at: datetime    # registration timestamp
    model_config = {"from_attributes": True}  # allows creating from SQLAlchemy User model


class TokenResponse(BaseModel):
    access_token: str           # the JWT token string
    token_type: str = "bearer"  # default value — always "bearer"


class ResetPasswordBody(BaseModel):
    token: str                               # the reset token from the email URL
    new_password: str = Field(min_length=6)  # minimum 6 characters for new password



class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)  # company name (1–100 chars)
    industry: str = Field(min_length=1)               # industry category (required)
    currency: Optional[str] = Field(default="USD", max_length=10) # currency code, e.g. USD, INR, EUR
    description: Optional[str] = Field(default=None, max_length=500)  # optional (up to 500 chars)


class CompanyResponse(BaseModel):
    id: uuid.UUID            # company's UUID
    name: str                # company name
    industry: str            # industry category
    currency: str = "USD"    # currency code
    description: Optional[str]  # optional description (None if not set)
    created_at: datetime     # when company was created
    model_config = {"from_attributes": True}



class TierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)   # tier name (e.g., "Basic")
    price: float = Field(ge=0)                        # price in USD (must be ≥ 0)
    billing_cycle: str = Field(default="monthly", pattern="^(monthly|annual)$")  # only these two values
    user_count: int = Field(ge=0, default=0)          # current subscribers (must be ≥ 0)
    churn_rate: Optional[float] = Field(default=None, ge=0, le=1)  # 0.0–1.0, optional


class FeatureResponse(BaseModel):
    id: uuid.UUID           # feature's UUID
    feature_name: str       # e.g., "API Access"
    description: Optional[str]  # optional description
    model_config = {"from_attributes": True}  # read from SQLAlchemy Feature model


class TierResponse(BaseModel):
    id: uuid.UUID               # tier's UUID
    company_id: uuid.UUID       # which company this tier belongs to
    name: str                   # tier name (e.g., "Growth")
    price: float                # price in USD
    billing_cycle: str          # "monthly" or "annual"
    user_count: int             # current subscriber count
    churn_rate: Optional[float] # monthly churn rate (0.0–1.0) or None
    created_at: datetime        # when tier was created
    features: List[FeatureResponse] = []  # list of features (empty by default)
    model_config = {"from_attributes": True}



class FeatureCreate(BaseModel):
    feature_name: str = Field(min_length=1, max_length=100)  # 1–100 chars
    description: Optional[str] = Field(default=None, max_length=300)  # optional, up to 300 chars

    @field_validator("feature_name")
    @classmethod
    def strip_feature_name(cls, v: str) -> str:
        stripped = v.strip()          # remove leading/trailing whitespace
        if not stripped:              # if only whitespace was given, it's now empty
            raise ValueError("feature_name cannot be blank")  # Pydantic converts this to 422
        return stripped               # return the cleaned value



class CompetitorCreate(BaseModel):
    url: AnyHttpUrl  # must be a valid HTTP/HTTPS URL

    @field_validator("url", mode="before")
    @classmethod
    def ensure_string(cls, v):
        return str(v) if not isinstance(v, str) else v  # convert to str if not already


class ManualCompetitorText(BaseModel):
    text: str = Field(min_length=1)  # the pasted competitor pricing text


class CompetitorResponse(BaseModel):
    id: uuid.UUID           # competitor's UUID
    company_id: uuid.UUID   # which company this competitor belongs to
    name: Optional[str]     # optional competitor name (None if user didn't set it)
    url: str                # competitor's pricing page URL
    scrape_status: str      # current scrape state (pending/success/failed/etc.)
    clean_scraped_text: Optional[str] = None  # cleaned scraped content (may be None)
    last_scraped_at: Optional[datetime] = None  # timestamp of last scrape
    created_at: datetime    # when competitor was added
    model_config = {"from_attributes": True}  # read from SQLAlchemy Competitor model



class AnalysisStartResponse(BaseModel):
    session_id: uuid.UUID   # the UUID of the newly created AnalysisSession


class ProgressUpdate(BaseModel):
    progress: int                        # 0–100 (percentage complete)
    status: str                          # e.g., "running", "m1_m2_complete", "completed"
    report_id: Optional[uuid.UUID] = None  # only present in the final 100% update


class ReportResponse(BaseModel):
    id: uuid.UUID           # report's UUID
    session_id: uuid.UUID   # which analysis session this report belongs to
    json_report: Any        # full analysis dict {company, module1_revenue, ..., module4_recommendations}
    pdf_path: Optional[str] # file path to PDF (None if unavailable)
    created_at: datetime    # when report was saved
    model_config = {"from_attributes": True}  # read from SQLAlchemy Report model


class AnalysisHistoryItem(BaseModel):
    session_id: uuid.UUID        # the session's UUID (used to fetch report)
    status: str                  # "completed", "partial", "failed", "running"
    progress: int                # 0–100
    started_at: datetime         # when analysis was kicked off
    completed_at: Optional[datetime]    # when it finished (None if still running)
    report_id: Optional[uuid.UUID]     # the Report UUID (None if not yet saved)
    mrr: Optional[float] = None        # current MRR from report if available
    currency: Optional[str] = "USD"    # currency code from company/report
    model_config = {"from_attributes": True}



class CompanyDetailResponse(BaseModel):
    id: uuid.UUID                       # company's UUID
    name: str                           # company name
    industry: str                       # industry category
    currency: str = "USD"               # currency code
    description: Optional[str]          # optional description
    created_at: datetime                # creation timestamp
    tiers: List[TierResponse] = []      # all pricing tiers (each with features inside)
    competitors: List[CompetitorResponse] = []  # all competitor entries
    model_config = {"from_attributes": True}    # read from SQLAlchemy Company model


# --- Setup Wizard Schemas ---

class ImportUrlRequest(BaseModel):
    url: str


class DraftTier(BaseModel):
    name: str
    price: Optional[float] = None
    billing_cycle: str = "monthly"
    user_count: Optional[int] = None
    churn_rate: Optional[float] = None
    features: List[str] = []
    custom_pricing: bool = False
    verified_price: bool = True


class DraftCompanyResponse(BaseModel):
    company_name: str
    industry: str
    description: Optional[str] = None
    currency: Optional[str] = "USD"
    tiers: List[DraftTier] = []


class BulkFeaturesRequest(BaseModel):
    features: List[str]


class BulkFeaturesResponse(BaseModel):
    added: List[FeatureResponse]
    skipped: List[str]


class CompetitorSuggestion(BaseModel):
    name: str
    homepage_url: str
    pricing_url: str
    reason: str
    verified: bool = False


class CompetitorSuggestionsResponse(BaseModel):
    suggestions: List[CompetitorSuggestion]


class FeatureSuggestionsResponse(BaseModel):
    suggestions: List[str]


class StripeImportRequest(BaseModel):
    stripe_key: str

