import pytest

from app.domain import Evidence
from app.scoring.blockers import evaluate_blockers
from app.scoring.config import ScoringConfig
from app.semantic.fake_fixtures import ch, nl, sc
from tests.conftest import make_profile, make_semantic

CFG = ScoringConfig()
CLEARANCE_EVIDENCE = {"security_clearance_required": Evidence(line_id="L003", text="Active Secret clearance required",
                                                              probability=0.9)}


def run(sem, **profile_kw):
    hard, possible, concerns = evaluate_blockers(sem, make_profile(**profile_kw), CFG)
    return [b.type for b in hard], [b.type for b in possible], [c.text for c in concerns]


def test_clearance_fires_only_with_fact_false():
    sem = make_semantic(security_clearance_required=nl(0.95), evidence=CLEARANCE_EVIDENCE)
    assert run(sem, blocker_facts={"can_meet_clearance_requirement": False})[0] == ["security_clearance"]
    hard, _, concerns = run(sem)
    assert hard == [] and concerns == [
        "Explicit security clearance requirement — set your clearance eligibility in Profile to evaluate"]
    assert run(sem, blocker_facts={"can_meet_clearance_requirement": True}) == ([], [], [])


def test_blocker_carries_confidence_and_evidence():
    sem = make_semantic(security_clearance_required=nl(0.95), evidence=CLEARANCE_EVIDENCE)
    [b], _, _ = evaluate_blockers(sem, make_profile(blocker_facts={"can_meet_clearance_requirement": False}), CFG)
    assert b.confidence == 0.95 and b.evidence == "Active Secret clearance required"


def test_low_probability_evidence_hidden():
    ev = {"security_clearance_required": Evidence(line_id="L003", text="x", probability=0.4)}
    sem = make_semantic(security_clearance_required=nl(0.95), evidence=ev)
    [b], _, _ = evaluate_blockers(sem, make_profile(blocker_facts={"can_meet_clearance_requirement": False}), CFG)
    assert b.evidence is None


@pytest.mark.parametrize("p,expected", [(0.8, "hard"), (0.79, "possible"), (0.5, "possible"), (0.49, "none")])
def test_possible_band(p, expected):
    hard, possible, concerns = run(make_semantic(us_citizenship_required=nl(p)),
                                   blocker_facts={"can_meet_us_citizenship_requirement": False})
    assert {"hard": (["us_citizenship"], []), "possible": ([], ["us_citizenship"]), "none": ([], [])}[expected] == (hard, possible)
    if expected == "possible":
        assert concerns == [f"Possible US citizenship requirement ({p:.2f}) — verify"]


def test_not_stated_never_blocks_or_concerns():
    sem = make_semantic(work_authorization_signal=ch("not_stated", 0.99, options="WorkAuthSignal"))
    assert run(sem, blocker_facts={"needs_visa_sponsorship": True}) == ([], [], [])


def test_explicit_no_sponsorship():
    sem = make_semantic(work_authorization_signal=ch("explicit_no_sponsorship", 0.93, options="WorkAuthSignal"))
    assert run(sem, blocker_facts={"needs_visa_sponsorship": True})[0] == ["no_sponsorship"]
    assert run(sem, blocker_facts={"needs_visa_sponsorship": False}) == ([], [], [])
    assert run(sem)[2] == ["Explicit no-sponsorship requirement — set your visa sponsorship need in Profile to evaluate"]


def test_specific_authorization_and_ambiguous_are_concerns_not_blockers():
    sem = make_semantic(work_authorization_signal=ch("explicit_specific_work_authorization_requirement", 0.9,
                                                     options="WorkAuthSignal"))
    assert run(sem, blocker_facts={"needs_visa_sponsorship": True}) == (
        [], [], ["Specific work authorization requirement — see posting"])
    sem = make_semantic(work_authorization_signal=ch("ambiguous", 0.9, options="WorkAuthSignal"))
    assert run(sem)[2] == ["Work authorization wording is ambiguous — see posting"]


def test_relocation_and_onsite_location():
    assert run(make_semantic(requires_relocation=nl(0.9)))[0] == ["relocation"]
    assert run(make_semantic(requires_relocation=nl(0.9)), willing_to_relocate=True)[0] == []
    sem = make_semantic(work_arrangement=ch("onsite", 0.9, options="WorkArrangement"),
                        location_match=ch("outside_preferred_locations", 0.85, options="LocationMatch"))
    assert run(sem, preferred_locations=["Berlin"])[0] == ["onsite_location"]
    assert run(sem, preferred_locations=["Berlin"], willing_to_relocate=True)[0] == []
    assert run(make_semantic(work_arrangement=ch("onsite", 0.9, options="WorkArrangement")))[0] == []


def test_technology_mismatch():
    avoid = make_semantic(technologies={"flutter": sc(3, 4, probabilities={3: 0.85, 2: 0.15})})
    assert run(avoid, avoid_technologies=["Flutter"])[0] == ["technology_mismatch"]
    absent = make_semantic(technologies={"kotlin": sc(0, 4, probabilities={0: 0.95, 1: 0.05})})
    assert run(absent, required_technologies=["Kotlin"])[0] == ["technology_mismatch"]
    barely = make_semantic(technologies={"kotlin": sc(0, 4, probabilities={0: 0.85, 1: 0.15})})
    assert run(barely, required_technologies=["Kotlin"])[:2] == ([], ["technology_mismatch"])


def test_seniority_far_below():
    sem = make_semantic(seniority=ch("mid", 0.85, options="Seniority"))
    assert run(sem, preferred_levels=["staff", "manager"])[0] == ["seniority_far_below"]
    assert run(sem, preferred_levels=["senior"])[:2] == ([], [])
    assert run(sem, preferred_levels=["manager"])[:2] == ([], [])


def test_disabled_rule():
    cfg = ScoringConfig()
    cfg.blockers.relocation.enabled = False
    assert evaluate_blockers(make_semantic(requires_relocation=nl(0.99)), make_profile(), cfg)[0] == []
