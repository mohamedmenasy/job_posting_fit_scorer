import pytest

from app.scoring.components import base_score, components
from app.scoring.confidence import aggregate_confidence, uncertain_signals
from app.scoring.config import ScoringConfig
from app.semantic.fake_fixtures import ch, sc
from tests.conftest import make_profile, make_semantic

CFG = ScoringConfig()


def by_name(comps):
    return {c.name: c for c in comps}


def test_worked_example_7_12():
    sem = make_semantic(technical_fit=sc(3.7, 5), android_relevance=sc(3.9, 5), seniority_fit=sc(3.6, 5),
                        role_preference_fit=sc(2.8, 4), role_family=ch("android_native", 0.92),
                        domain_fit=sc(3.4, 5), domain=ch("fintech", 1.0, options="Domain"),
                        work_arrangement=ch("remote", 0.9, options="WorkArrangement"), management_intensity=sc(1.2, 5))
    profile = make_profile(preferred_roles=["Staff Android"], preferred_levels=["staff", "principal"],
                           preferred_role_families=["android_native", "kotlin_multiplatform"],
                           preferred_domains=["fintech"], remote_preference="remote", management_preference="ic")
    c = by_name(components(sem, profile, CFG))
    assert c["technical"].value == pytest.approx(0.925)
    assert c["android"].value == pytest.approx(0.975)
    assert c["role_preference"].value == pytest.approx(2.8 / 3)
    assert c["platform"].value == pytest.approx(0.92 + 0.08 / 9 + 0.08 * 8 / 9 * 0.5)
    assert c["management"].value == pytest.approx(1 - 0.2 / 3)
    assert c["domain"].value == pytest.approx(0.5 * 0.85 + 0.5 * 1.0)
    assert c["work_arrangement"].value == pytest.approx(0.9 + 0.025 * (0.4 + 0.0 + 0.9 + 0.5))
    assert all(x.applicable for x in c.values())
    assert c["technical"].contribution == pytest.approx(27.75)
    assert base_score(list(c.values())) == pytest.approx(sum(x.weight * x.value for x in c.values()))


def test_na_components_renormalize():
    comps = components(make_semantic(), make_profile(), CFG)
    c = by_name(comps)
    for name in ["role_preference", "platform", "work_arrangement", "management"]:
        assert not c[name].applicable and c[name].effective_weight == 0 and c[name].reason.startswith("n/a")
        assert c[name].contribution == 0 and c[name].value is None
    assert sum(x.effective_weight for x in comps) == pytest.approx(1.0)
    assert c["technical"].effective_weight == pytest.approx(30 / 70)
    assert base_score(comps) == pytest.approx(50.0)


def test_platform_avoided_family():
    sem = make_semantic(role_family=ch("flutter", 1.0))
    assert by_name(components(sem, make_profile(avoided_role_families=["flutter"]), CFG))["platform"].value == 0.0


@pytest.mark.parametrize("pref,m,expected", [("ic", 1, 1.0), ("ic", 4, 0.0), ("tech_lead", 2, 1.0),
                                             ("tech_lead", 4, 0.0), ("manager", 4, 1.0), ("manager", 1, 0.0)])
def test_management_formula(pref, m, expected):
    c = by_name(components(make_semantic(management_intensity=sc(m, 5)), make_profile(management_preference=pref), CFG))
    assert c["management"].value == pytest.approx(expected)


def test_domain_without_preferences_uses_fit_only():
    c = by_name(components(make_semantic(domain_fit=sc(3, 5)), make_profile(), CFG))
    assert c["domain"].value == pytest.approx(0.75)


def test_work_arrangement_with_location_factor():
    sem = make_semantic(work_arrangement=ch("onsite", 1.0, options="WorkArrangement"),
                        location_match=ch("outside_preferred_locations", 1.0, options="LocationMatch"))
    p = make_profile(remote_preference="hybrid", preferred_locations=["Berlin"], willing_to_relocate=True)
    assert by_name(components(sem, p, CFG))["work_arrangement"].value == pytest.approx(0.4 * 0.5)
    p = make_profile(remote_preference="hybrid", preferred_locations=["Berlin"])
    assert by_name(components(sem, p, CFG))["work_arrangement"].value == 0


def test_aggregate_confidence_and_uncertain_signals():
    sem = make_semantic(technical_fit=sc(2, 5, conf=0.5))
    comps = components(sem, make_profile(), CFG)
    assert aggregate_confidence(comps) == pytest.approx((30 * 0.5 + 20 * 0.9 + 15 * 0.9 + 5 * 0.9) / 70)
    assert uncertain_signals(sem, make_profile(), comps, CFG) == ["technical_fit"]
