"""Live golden set (spec §13.3). Replays cassettes by default; `make test-live ARGS=--record` refreshes them
(needs TYPESAFE_API_KEY and TYPESAFE_MODEL). Committed cassettes use the synthetic SAMPLE_RESUME only."""

import asyncio
import os
from pathlib import Path

import pytest

from app.semantic.fake_fixtures import DEMO_PREFERENCES, FIXTURES, SAMPLE_RESUME
from app.semantic.typesafe_evaluator import TypeSafeJobSemanticEvaluator
from tests.cassette import CassetteMissing, CassetteTransport
from tests.conftest import make_job, make_profile

pytestmark = pytest.mark.live
CASSETTES = Path(__file__).parent / "cassettes"
MODEL_FILE = CASSETTES / "MODEL"


@pytest.fixture
def evaluate(request):
    record = request.config.getoption("--record")
    if record:
        key, model = os.environ.get("TYPESAFE_API_KEY"), os.environ.get("TYPESAFE_MODEL")
        if not key or not model:
            pytest.fail("--record needs TYPESAFE_API_KEY and TYPESAFE_MODEL")
        CASSETTES.mkdir(exist_ok=True)
        MODEL_FILE.write_text(model)
    else:
        if not MODEL_FILE.exists():
            pytest.skip("no cassettes; run `make test-live ARGS=--record` with TYPESAFE_API_KEY and TYPESAFE_MODEL")
        key, model = "replay", MODEL_FILE.read_text().strip()

    async def run(name: str):
        profile = make_profile(resume_text=SAMPLE_RESUME, **DEMO_PREFERENCES)
        job = make_job(**FIXTURES[name]["posting"])
        evaluator = TypeSafeJobSemanticEvaluator(key, model, 24000, asyncio.Semaphore(4),
                                                 transport=CassetteTransport(CASSETTES, record))
        try:
            sem = await evaluator.evaluate(profile, job)
        except CassetteMissing:
            pytest.skip(f"no cassette for {name}; re-record")
        for r in sem.requests:
            print(f"{name} {r.state_kind}: {r.question_count} questions, {r.input_tokens} input tokens, {r.latency_ms} ms")
        return sem
    return run


async def test_clearance_required(evaluate):
    sem = await evaluate("clearance_required")
    assert sem.security_clearance_required.probability >= 0.8
    assert "clearance" in (sem.evidence["security_clearance_required"].text or "").lower()


async def test_gov_contractor_no_clearance(evaluate):
    assert (await evaluate("gov_contractor_no_clearance")).security_clearance_required.probability <= 0.2


async def test_no_sponsorship_info(evaluate):
    assert (await evaluate("no_sponsorship_info")).work_authorization_signal.value == "not_stated"


async def test_explicit_no_sponsorship(evaluate):
    sem = await evaluate("explicit_no_sponsorship")
    assert sem.work_authorization_signal.value == "explicit_no_sponsorship"
    assert "sponsorship" in (sem.evidence["work_authorization_signal"].text or "").lower()


async def test_flutter_heavy(evaluate):
    assert (await evaluate("flutter_heavy")).cross_platform_intensity.score >= 3


async def test_engineering_manager(evaluate):
    assert (await evaluate("engineering_manager")).management_intensity.score >= 3


async def test_staff_title_senior_scope(evaluate):
    sem = await evaluate("staff_title_senior_scope")
    assert sem.title_level.value == "staff" and sem.seniority.value == "senior"


async def test_android_staff_perfect(evaluate):
    sem = await evaluate("android_staff_perfect")
    assert sem.android_relevance.score >= 3 and sem.role_family.value == "android_native"
