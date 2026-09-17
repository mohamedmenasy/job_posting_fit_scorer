from app.semantic.fake_evaluator import FakeJobSemanticEvaluator
from app.semantic.fake_fixtures import FIXTURES, sc
from tests.conftest import make_job, make_profile


async def test_picks_fixture_by_external_id_and_uses_real_segmentation():
    job = make_job(**FIXTURES["clearance_required"]["posting"], external_id="fixture:clearance_required")
    ev = await FakeJobSemanticEvaluator().evaluate(make_profile(), job)
    assert ev.security_clearance_required.probability >= 0.8
    line = ev.evidence["security_clearance_required"]
    assert line.line_id in ev.all_lines and "clearance" in line.text.lower()


async def test_default_fixture_and_dropped_missing_lines():
    job = make_job(description="Tiny posting about Android work.\nAnother line for the fake evaluator.")
    ev = await FakeJobSemanticEvaluator().evaluate(make_profile(preferred_roles=["Staff Android"]), job)
    assert ev.role_family.value == "android_native"
    assert all(e.line_id is None or e.line_id in ev.all_lines for e in ev.evidence.values())
    assert ev.role_preference_fit is not None and ev.location_match is None


async def test_requirement_lines_mapped_by_substring():
    job = make_job(**FIXTURES["android_staff_perfect"]["posting"], external_id="fixture:android_staff_perfect")
    ev = await FakeJobSemanticEvaluator().evaluate(make_profile(), job)
    kmp = next(line for line in ev.lines if "Multiplatform" in line.text)
    assert (kmp.kind.value, kmp.skill.value) == ("preferred_qualification", "kmp")


async def test_every_fixture_builds():
    for name, fx in FIXTURES.items():
        job = make_job(**fx["posting"], external_id=f"fixture:{name}")
        ev = await FakeJobSemanticEvaluator().evaluate(make_profile(required_technologies=["Kotlin", "Rust"]), job)
        assert set(ev.technologies) == {"kotlin", "rust"}


def test_score_helper_weighted_mean():
    s = sc(2.7, 4)
    assert abs(sum(k * v for k, v in s.probabilities.items()) - 2.7) < 1e-9 and s.normalized == 0.9
