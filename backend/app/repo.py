"""Row ↔ domain helpers shared by the pipeline and API."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import CandidateProfile, JobPosting, SemanticJobEvaluation
from app.models import JobPostingRow, ProfileVersion, ScoringConfigRow
from app.scoring.config import ScoringConfig


def current_profile(session: Session) -> ProfileVersion | None:
    return session.scalars(select(ProfileVersion).order_by(ProfileVersion.created_at.desc()).limit(1)).first()


def to_domain_profile(row: ProfileVersion) -> CandidateProfile:
    return CandidateProfile(id=row.id, created_at=row.created_at, resume_text=row.resume_text,
                            preferences=row.preferences, blocker_facts=row.blocker_facts,
                            tracked_skills=row.tracked_skills, semantic_hash=row.semantic_hash)


def to_domain_job(row: JobPostingRow) -> JobPosting:
    return JobPosting(id=row.id, company=row.company, title=row.title, description=row.description,
                      location=row.location, source=row.source, source_url=row.source_url,
                      salary_text=row.salary_text, external_id=row.external_id, content_hash=row.content_hash,
                      created_at=row.created_at, imported_at=row.imported_at)


def active_config(session: Session) -> ScoringConfigRow:
    return session.scalars(select(ScoringConfigRow).where(ScoringConfigRow.is_active)).one()


def ensure_default_config(session: Session) -> None:
    if session.scalars(select(ScoringConfigRow).limit(1)).first() is None:
        session.add(ScoringConfigRow(version=1, config=ScoringConfig().model_dump(mode="json"), is_active=True))
        session.commit()


def headline_columns(sem: SemanticJobEvaluation) -> dict:
    choices = ["role_family", "seniority", "domain", "work_arrangement", "kmp_requirement", "work_authorization_signal"]
    scores = ["android_relevance", "technical_fit", "seniority_fit", "domain_fit", "management_intensity",
              "cross_platform_intensity"]
    nouls = ["staff_ic_signal", "requires_relocation", "security_clearance_required", "us_citizenship_required"]
    return ({c: getattr(sem, c).value for c in choices} | {s: getattr(sem, s).score for s in scores}
            | {n: getattr(sem, n).probability for n in nouls})
