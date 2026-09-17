import pytest

from app.scoring.config import ScoringConfig
from app.scoring.scorer import JobFitScorer, status_for
from app.semantic.fake_evaluator import FakeJobSemanticEvaluator
from app.semantic.fake_fixtures import FIXTURES
from tests.conftest import make_job, make_profile

IC_STAFF = dict(preferred_roles=["Staff Android Engineer"], preferred_levels=["staff", "principal"],
                preferred_role_families=["android_native", "kotlin_multiplatform"], preferred_domains=["fintech"],
                remote_preference="remote", management_preference="ic")


async def score(name, **profile_kw):
    profile = make_profile(**{**IC_STAFF, **profile_kw})
    job = make_job(**FIXTURES[name]["posting"], external_id=f"fixture:{name}")
    sem = await FakeJobSemanticEvaluator().evaluate(profile, job)
    return sem, JobFitScorer().calculate(sem, profile, ScoringConfig())


def concerns(r):
    return [e.text for e in r.explanations if e.section == "concern"]


async def test_android_staff_perfect():
    _, r = await score("android_staff_perfect")
    assert r.status == "STRONG_MATCH" and not r.hard_blockers and r.overall_score >= 85
    assert not r.penalties and r.overall_score == pytest.approx(r.base_score)
    kmp = next(m for m in r.missing_skills if m.skill == "Kotlin Multiplatform")
    assert kmp.importance == "nice_to_have" and kmp.impact == "minor"


async def test_flutter_heavy():
    sem, r = await score("flutter_heavy", avoided_role_families=["flutter"], preferred_role_families=["android_native"])
    assert sem.android_relevance.score <= 1.5 and sem.cross_platform_intensity.score >= 3
    assert "avoided_tech_heavy" in {p.type for p in r.penalties}


async def test_engineering_manager():
    sem, r = await score("engineering_manager")
    assert sem.management_intensity.score >= 3
    assert "management_heavy_for_ic" in {p.type for p in r.penalties}
    assert next(c for c in r.components if c.name == "management").value < 0.3


async def test_clearance_required():
    _, r = await score("clearance_required", blocker_facts={"can_meet_clearance_requirement": False})
    assert r.status == "BLOCKED" and r.hard_blockers[0].evidence
    assert r.overall_score > 0
    _, r = await score("clearance_required")
    assert r.status != "BLOCKED" and any("security clearance" in c for c in concerns(r))


async def test_gov_contractor_no_clearance():
    _, r = await score("gov_contractor_no_clearance", blocker_facts={"can_meet_clearance_requirement": False})
    assert not r.hard_blockers and not r.possible_blockers
    assert not any("clearance" in c.lower() for c in concerns(r))


async def test_no_sponsorship_info():
    sem, r = await score("no_sponsorship_info", blocker_facts={"needs_visa_sponsorship": True})
    assert sem.work_authorization_signal.value == "not_stated" and not r.hard_blockers
    assert "Sponsorship: not stated" in [e.text for e in r.explanations if e.section == "note"]


async def test_explicit_no_sponsorship():
    _, r = await score("explicit_no_sponsorship", blocker_facts={"needs_visa_sponsorship": True})
    assert [b.type for b in r.hard_blockers] == ["no_sponsorship"] and r.status == "BLOCKED"
    assert "sponsorship" in r.hard_blockers[0].evidence


async def test_staff_title_senior_scope():
    _, r = await score("staff_title_senior_scope")
    assert "Title reads Staff; scope reads Senior" in concerns(r)


@pytest.mark.parametrize("value,status", [(85, "STRONG_MATCH"), (84.9, "GOOD_MATCH"), (70, "GOOD_MATCH"),
                                          (55, "REVIEW"), (54.9, "LOW_MATCH")])
def test_status_thresholds(value, status):
    assert status_for(value, blocked=False, cfg=ScoringConfig()) == status
    assert status_for(value, blocked=True, cfg=ScoringConfig()) == "BLOCKED"


async def test_low_confidence_needs_review_but_keeps_status():
    profile = make_profile(**IC_STAFF)
    job = make_job(**FIXTURES["android_staff_perfect"]["posting"])
    sem = await FakeJobSemanticEvaluator().evaluate(profile, job)
    confident = JobFitScorer().calculate(sem, profile, ScoringConfig())
    sem.technical_fit.confidence = 0.3
    unsure = JobFitScorer().calculate(sem, profile, ScoringConfig())
    assert unsure.status == confident.status and unsure.overall_score == confident.overall_score
    assert unsure.needs_review and "technical_fit" in unsure.uncertain_signals
    assert unsure.aggregate_confidence < confident.aggregate_confidence
