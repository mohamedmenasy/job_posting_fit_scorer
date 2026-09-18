"""ORM tables (spec §8). Portable column types only."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=_now)


class ProfileVersion(Base):
    __tablename__ = "profile_versions"
    id: Mapped[uuid.UUID] = _id()
    created_at: Mapped[datetime] = _created()
    resume_text: Mapped[str] = mapped_column(Text)
    preferences: Mapped[dict] = mapped_column(JSON)
    blocker_facts: Mapped[dict] = mapped_column(JSON)
    tracked_skills: Mapped[list] = mapped_column(JSON)
    semantic_hash: Mapped[str] = mapped_column(String(64))


class JobPostingRow(Base):
    __tablename__ = "job_postings"
    id: Mapped[uuid.UUID] = _id()
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(32), default="manual")
    source_url: Mapped[str | None] = mapped_column(String(2000))
    external_id: Mapped[str | None] = mapped_column(String(500))
    salary_text: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="ready", server_default="ready", index=True)
    import_source: Mapped[str] = mapped_column(String(16), default="paste", server_default="paste")
    current_fit_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("fit_results.id", ondelete="SET NULL", use_alter=True, name="fk_job_current_fit_result"))
    created_at: Mapped[datetime] = _created()
    imported_at: Mapped[datetime] = _created()

    evaluations: Mapped[list["JobEvaluation"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True, order_by="JobEvaluation.created_at",
        foreign_keys="JobEvaluation.job_id")
    current_fit_result: Mapped["FitResult | None"] = relationship(foreign_keys=[current_fit_result_id], post_update=True)


class JobEvaluation(Base):
    __tablename__ = "job_evaluations"
    id: Mapped[uuid.UUID] = _id()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("job_postings.id", ondelete="CASCADE"), index=True)
    profile_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profile_versions.id"))
    evaluator_version: Mapped[str | None] = mapped_column(String(32))
    catalog_hash: Mapped[str | None] = mapped_column(String(64))
    question_set_hash: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    signals: Mapped[dict | None] = mapped_column(JSON)
    raw_typesafe_response: Mapped[list | None] = mapped_column(JSON)
    # headline columns: Choice → selected value, Score → raw score, Noul → probability
    role_family: Mapped[str | None] = mapped_column(String(32))
    seniority: Mapped[str | None] = mapped_column(String(32))
    domain: Mapped[str | None] = mapped_column(String(32))
    work_arrangement: Mapped[str | None] = mapped_column(String(32))
    kmp_requirement: Mapped[str | None] = mapped_column(String(32))
    work_authorization_signal: Mapped[str | None] = mapped_column(String(64))
    android_relevance: Mapped[float | None] = mapped_column(Float)
    technical_fit: Mapped[float | None] = mapped_column(Float)
    seniority_fit: Mapped[float | None] = mapped_column(Float)
    domain_fit: Mapped[float | None] = mapped_column(Float)
    management_intensity: Mapped[float | None] = mapped_column(Float)
    cross_platform_intensity: Mapped[float | None] = mapped_column(Float)
    staff_ic_signal: Mapped[float | None] = mapped_column(Float)
    requires_relocation: Mapped[float | None] = mapped_column(Float)
    security_clearance_required: Mapped[float | None] = mapped_column(Float)
    us_citizenship_required: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[JobPostingRow] = relationship(back_populates="evaluations", foreign_keys=[job_id])
    profile_version: Mapped[ProfileVersion] = relationship()
    fit_results: Mapped[list["FitResult"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan", passive_deletes=True, order_by="FitResult.created_at")


class ScoringConfigRow(Base):
    __tablename__ = "scoring_configs"
    id: Mapped[uuid.UUID] = _id()
    version: Mapped[int] = mapped_column(Integer, unique=True)
    config: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class FitResult(Base):
    __tablename__ = "fit_results"
    id: Mapped[uuid.UUID] = _id()
    evaluation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("job_evaluations.id", ondelete="CASCADE"), index=True)
    profile_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profile_versions.id"))
    scoring_config_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scoring_configs.id"))
    overall_score: Mapped[float] = mapped_column(Float)
    aggregate_confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))
    needs_review: Mapped[bool] = mapped_column(Boolean)
    stale_semantics: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = _created()

    evaluation: Mapped[JobEvaluation] = relationship(back_populates="fit_results")
    scoring_config: Mapped[ScoringConfigRow] = relationship()
    profile_version: Mapped[ProfileVersion] = relationship()
