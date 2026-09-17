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


def fake_answers_for_bodies(questions: dict[str, dict]) -> dict[str, dict]:
    """A valid answer for every raw question body: first option / level 0 / noul 0.1."""
    out = {}
    for qid, body in questions.items():
        if body["type"] == "choice":
            first = next(iter(body["criteria"]))
            out[qid] = {"type": "choice", "choice": first, "confidence": 0.9,
                        "probabilities": {k: (1.0 if k == first else 0.0) for k in body["criteria"]}}
        elif body["type"] == "score":
            n = len(body["criteria"])
            out[qid] = {"type": "score", "score": 0.0, "confidence": 0.9,
                        "legend": {str(i): c for i, c in enumerate(body["criteria"])},
                        "probabilities": {str(i): (1.0 if i == 0 else 0.0) for i in range(n)}}
        else:
            out[qid] = {"type": "noul", "noul": 0.1}
    return out


def fake_answers(questions) -> dict[str, dict]:
    return fake_answers_for_bodies({q.id: q.body for q in questions})
