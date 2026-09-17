from datetime import UTC, datetime
from uuid import uuid4

from app.domain import (
    DEFAULT_TRACKED_SKILLS,
    BlockerFacts,
    CandidatePreferences,
    CandidateProfile,
    CandidateProfileIn,
    JobPosting,
    semantic_hash,
)


def make_profile(blocker_facts=None, tracked_skills=None, resume_text="Staff Android engineer, Kotlin, Compose",
                 **prefs) -> CandidateProfile:
    base = CandidateProfileIn(resume_text=resume_text, preferences=CandidatePreferences(**prefs),
                              blocker_facts=BlockerFacts(**(blocker_facts or {})),
                              tracked_skills=DEFAULT_TRACKED_SKILLS if tracked_skills is None else tracked_skills)
    return CandidateProfile(**base.model_dump(), id=uuid4(), created_at=datetime.now(UTC),
                            semantic_hash=semantic_hash(base))


def make_job(**over) -> JobPosting:
    data = dict(company="Acme", title="Staff Android Engineer",
                description="Build Android apps with Kotlin.\nLead architecture across mobile teams.\n" * 2,
                location="Remote (US)", salary_text="$220k", external_id=None)
    data.update(over)
    now = datetime.now(UTC)
    return JobPosting(**data, id=uuid4(), content_hash="h", created_at=now, imported_at=now)
