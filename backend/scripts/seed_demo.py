"""Seed a demo profile and the eight fixture jobs, evaluated with the fake evaluator (no API calls).

Usage: uv run python -m scripts.seed_demo   (uses DATABASE_URL / backend/.env)
"""

import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import DEFAULT_TRACKED_SKILLS
from app.main import create_app
from app.semantic.fake_fixtures import DEMO_PREFERENCES, FIXTURES, SAMPLE_RESUME

SOURCES = ["linkedin", "company_site", "indeed", "recruiter_email", "manual", "company_site", "linkedin", "indeed"]


def seed(database_url: str) -> dict:
    settings = Settings(_env_file=None, evaluator="fake", database_url=database_url, typesafe_api_key=None,
                        log_level="warning")
    with TestClient(create_app(settings)) as client:
        profile_created = client.get("/api/profile").status_code == 404
        if profile_created:
            client.put("/api/profile", json={
                "resume_text": SAMPLE_RESUME, "preferences": DEMO_PREFERENCES,
                "blocker_facts": {"needs_visa_sponsorship": True, "can_meet_clearance_requirement": False},
                "tracked_skills": [s.model_dump() for s in DEFAULT_TRACKED_SKILLS]}).raise_for_status()
        jobs = [{**fx["posting"], "external_id": f"fixture:{name}", "source": source}
                for (name, fx), source in zip(FIXTURES.items(), SOURCES)]
        result = client.post("/api/jobs/batch", json={"jobs": jobs, "auto_evaluate": True})
        result.raise_for_status()
        body = result.json()
        deadline = time.monotonic() + 30
        pending = set(body["evaluation_ids"])
        while pending and time.monotonic() < deadline:
            pending = {e for e in pending if client.get(f"/api/evaluations/{e}").json()["status"] in ("pending", "running")}
            time.sleep(0.05)
    return {"profile_created": profile_created, "created": body["created"], "existing": body["existing"]}


if __name__ == "__main__":
    print(seed(Settings().database_url))
