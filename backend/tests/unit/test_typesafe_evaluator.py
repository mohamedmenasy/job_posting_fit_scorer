import asyncio
import json

import httpx2
import pytest

from app.semantic.evaluator import SemanticEvaluationError
from app.semantic.typesafe_evaluator import TypeSafeJobSemanticEvaluator
from tests.conftest import fake_answers_for_bodies, make_job, make_profile


def transport(calls, status=200):
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if status != 200:
            return httpx2.Response(status, json={"error": "boom"}, headers={"x-typesafe-request-id": "req-err"})
        return httpx2.Response(200, headers={"x-typesafe-request-id": f"req-{len(calls)}"}, json={
            "model": body["model"], "usage": {"input_tokens": 10, "output_tokens": 2},
            "answers": fake_answers_for_bodies(body["questions"])})
    return httpx2.MockTransport(handler)


async def test_sends_job_and_fit_requests_and_parses():
    calls = []
    ev = TypeSafeJobSemanticEvaluator("k", "jev-2026-09", 24000, asyncio.Semaphore(4), transport=transport(calls))
    result = await ev.evaluate(make_profile(blocker_facts={"needs_visa_sponsorship": True}), make_job())
    assert sorted("candidate" in c["state"] for c in calls) == [False, True]
    assert all(c["model"] == "jev-2026-09" for c in calls)
    assert "needs_visa_sponsorship" not in json.dumps(calls)
    assert {r.state_kind for r in result.requests} == {"job", "fit"}
    assert all(r.request_id.startswith("req-") and r.input_tokens == 10 for r in result.requests)
    assert result.model == "jev-2026-09" and result.requests[0].raw_response["answers"]


async def test_small_budget_splits_requests():
    calls = []
    ev = TypeSafeJobSemanticEvaluator("k", "m", 4000, asyncio.Semaphore(4), transport=transport(calls))
    await ev.evaluate(make_profile(), make_job())
    assert len(calls) > 2


async def test_api_error_is_sanitized():
    ev = TypeSafeJobSemanticEvaluator("k", "m", 24000, asyncio.Semaphore(4), transport=transport([], status=400))
    with pytest.raises(SemanticEvaluationError) as err:
        await ev.evaluate(make_profile(resume_text="PRIVATE RESUME"), make_job())
    assert err.value.status == 400 and err.value.request_id == "req-err"
    assert "PRIVATE RESUME" not in err.value.sanitized()
