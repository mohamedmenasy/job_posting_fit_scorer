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


def pytest_addoption(parser):
    parser.addoption("--record", action="store_true", help="live tests: call real TypeSafe and refresh cassettes")


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


def make_semantic(**overrides):
    """Neutral baseline SemanticJobEvaluation: mid-level scores, other/unclear choices, low Nouls."""
    from app.domain import SemanticJobEvaluation
    from app.semantic.fake_fixtures import ch, nl, sc
    data = dict(
        role_family=ch("other", 0.9, options="RoleFamily"), android_relevance=sc(2, 5),
        seniority=ch("unclear", 0.9, options="Seniority"), title_level=ch("unclear", 0.9, options="Seniority"),
        staff_ic_signal=nl(0.05), management_intensity=sc(2, 5),
        kmp_requirement=ch("not_mentioned", 0.9, options="RequirementLevel"), cross_platform_intensity=sc(2, 5),
        domain=ch("other", 0.9, options="Domain"), work_arrangement=ch("unclear", 0.9, options="WorkArrangement"),
        requires_relocation=nl(0.05), security_clearance_required=nl(0.05), us_citizenship_required=nl(0.05),
        work_authorization_signal=ch("not_stated", 0.9, options="WorkAuthSignal"),
        min_years_required=ch("not_stated", 0.9, options="YearsBucket"),
        technical_fit=sc(2, 5), seniority_fit=sc(2, 5), domain_fit=sc(2, 5),
        role_preference_fit=None, location_match=None,
        skills={}, technologies={}, lines=[], all_lines={}, evidence={},
        model="fake", evaluator_version="1.0.0", catalog_hash="c", question_set_hash="q", requests=[])
    data.update(overrides)
    return SemanticJobEvaluation(**data)


import time  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def make_settings(tmp_path, **over):
    from app.config import Settings
    return Settings(_env_file=None, database_url=f"sqlite:///{tmp_path}/t.db", evaluator="fake", evaluation_workers=2,
                    typesafe_api_key=None, **over)


@pytest.fixture
def app_client(tmp_path):
    from app.main import create_app
    with TestClient(create_app(make_settings(tmp_path))) as client:
        yield client


def wait_for(client, evaluation_id, timeout=10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/evaluations/{evaluation_id}").json()
        if data["status"] in ("succeeded", "failed"):
            assert data["status"] == "succeeded", data["error"]
            return data
        time.sleep(0.02)
    raise AssertionError(f"evaluation {evaluation_id} did not finish")


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve every test hostname to a public address so URL guard tests never touch DNS."""
    monkeypatch.setattr("app.ingest.fetch.url_guard.resolve_addresses", lambda host: ["93.184.216.34"])
