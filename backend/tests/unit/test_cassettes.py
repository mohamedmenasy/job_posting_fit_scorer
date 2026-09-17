import httpx2
import pytest

from tests.cassette import CassetteMissing, CassetteTransport


async def test_record_then_replay(tmp_path):
    inner = httpx2.MockTransport(lambda r: httpx2.Response(200, json={"ok": True}, headers={"x-typesafe-request-id": "r1"}))
    body = {"model": "m", "state": {"a": 1}, "questions": {}}
    async with httpx2.AsyncClient(transport=CassetteTransport(tmp_path, record=True, inner=inner)) as c:
        assert (await c.post("https://x/v1/systemone", json=body)).json() == {"ok": True}
    async with httpx2.AsyncClient(transport=CassetteTransport(tmp_path, record=False)) as c:
        r = await c.post("https://x/v1/systemone", json={"questions": {}, "state": {"a": 1}, "model": "m"})
        assert r.json() == {"ok": True} and r.headers["x-typesafe-request-id"] == "r1"
        with pytest.raises(CassetteMissing):
            await c.post("https://x/v1/systemone", json={**body, "model": "other"})


async def test_evaluator_round_trip_through_cassettes(tmp_path):
    import asyncio
    import json

    from app.semantic.typesafe_evaluator import TypeSafeJobSemanticEvaluator
    from tests.conftest import fake_answers_for_bodies, make_job, make_profile

    def handler(request):
        body = json.loads(request.content)
        return httpx2.Response(200, headers={"x-typesafe-request-id": "rid"}, json={
            "model": body["model"], "usage": {"input_tokens": 5, "output_tokens": 1},
            "answers": fake_answers_for_bodies(body["questions"])})

    profile, job = make_profile(), make_job()
    recorder = CassetteTransport(tmp_path, record=True, inner=httpx2.MockTransport(handler))
    first = await TypeSafeJobSemanticEvaluator("k", "m", 24000, asyncio.Semaphore(2), transport=recorder).evaluate(profile, job)
    replayer = CassetteTransport(tmp_path, record=False)
    second = await TypeSafeJobSemanticEvaluator("k", "m", 24000, asyncio.Semaphore(2), transport=replayer).evaluate(profile, job)
    assert second.model_dump(exclude={"requests"}) == first.model_dump(exclude={"requests"})
    assert {r.request_id for r in second.requests} == {"rid"}
