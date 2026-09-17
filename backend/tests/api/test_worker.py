import asyncio
import time

from fastapi.testclient import TestClient

from app.domain import DEFAULT_TRACKED_SKILLS
from app.main import create_app
from app.models import JobEvaluation, JobPostingRow, ProfileVersion
from app.pipeline.worker import create_evaluation
from app.semantic.evaluator import SemanticEvaluationError
from tests.conftest import make_settings


class Exploding:
    model = "fake"

    async def evaluate(self, profile, job):
        raise SemanticEvaluationError("TypeSafeBadRequestError", 400, "req-1")


def seed(session_factory):
    with session_factory() as s:
        p = ProfileVersion(resume_text="Android", preferences={}, blocker_facts={},
                           tracked_skills=[x.model_dump() for x in DEFAULT_TRACKED_SKILLS], semantic_hash="h")
        j = JobPostingRow(company="A", title="B", description="Build Android apps with Kotlin. " * 3, source="manual",
                          content_hash="c")
        s.add_all([p, j])
        s.flush()
        e = create_evaluation(s, j.id, p.id)
        s.commit()
        return e.id


def test_failed_evaluation_is_sanitized(tmp_path):
    app = create_app(make_settings(tmp_path), evaluator=Exploding())
    with TestClient(app):
        eid = seed(app.state.session_factory)
        asyncio.run(app.state.worker.evaluate_job(eid))
        with app.state.session_factory() as s:
            e = s.get(JobEvaluation, eid)
            assert e.status == "failed" and e.finished_at
            assert e.error == "TypeSafeBadRequestError (status=400, request_id=req-1)"


def test_startup_requeues_pending(tmp_path):
    first = create_app(make_settings(tmp_path))
    with TestClient(first):
        pass
    eid = seed(first.state.session_factory)  # pending row written while no app is running
    second = create_app(make_settings(tmp_path))
    with TestClient(second) as client:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with second.state.session_factory() as s:
                if s.get(JobEvaluation, eid).status == "succeeded":
                    break
            client.get("/api/health")
            time.sleep(0.02)
        else:
            raise AssertionError("pending evaluation was not re-queued")
