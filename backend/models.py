
import uuid

from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, Text, DateTime,
    ForeignKey, JSON
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email = Column(String, unique=True, nullable=False, index=True)

    password_hash = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    companies = relationship("Company", back_populates="owner", cascade="all, delete-orphan")

    password_reset_tokens = relationship(
        "PasswordResetToken", cascade="all, delete-orphan"
    )


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name = Column(String, nullable=False)

    industry = Column(String, nullable=False)

    currency = Column(String, nullable=False, default="USD")

    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="companies")

    tiers = relationship("PricingTier", back_populates="company", cascade="all, delete-orphan")

    competitors = relationship("Competitor", back_populates="company", cascade="all, delete-orphan")

    analysis_sessions = relationship("AnalysisSession", back_populates="company", cascade="all, delete-orphan")


class PricingTier(Base):
    __tablename__ = "pricing_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    name = Column(String, nullable=False)

    price = Column(Float, nullable=False)

    billing_cycle = Column(String, nullable=False, default="monthly")

    user_count = Column(Integer, nullable=False, default=0)

    churn_rate = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="tiers")

    features = relationship("Feature", back_populates="tier", cascade="all, delete-orphan")


class Feature(Base):
    __tablename__ = "features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    tier_id = Column(UUID(as_uuid=True), ForeignKey("pricing_tiers.id", ondelete="CASCADE"), nullable=False)

    feature_name = Column(String, nullable=False)

    description = Column(Text, nullable=True)

    tier = relationship("PricingTier", back_populates="features")


class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    name = Column(String, nullable=True)

    url = Column(String, nullable=False)

    raw_scraped_text = Column(Text, nullable=True)

    clean_scraped_text = Column(Text, nullable=True)

    scrape_status = Column(String, nullable=False, default="pending")

    last_scraped_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="competitors")


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    status = Column(String, nullable=False, default="pending")

    progress = Column(Integer, nullable=False, default=0)

    started_at = Column(DateTime, default=datetime.utcnow)

    completed_at = Column(DateTime, nullable=True)

    error_message = Column(Text, nullable=True)

    company = relationship("Company", back_populates="analysis_sessions")

    report = relationship("Report", back_populates="session", uselist=False, cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    session_id = Column(UUID(as_uuid=True), ForeignKey("analysis_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)

    json_report = Column(JSON, nullable=False)

    pdf_path = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("AnalysisSession", back_populates="report")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    token = Column(String, unique=True, nullable=False, index=True)

    expires_at = Column(DateTime, nullable=False)

    used = Column(String, nullable=False, default="no")
