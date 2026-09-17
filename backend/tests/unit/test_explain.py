from app.domain import Evidence, SkillSignal
from app.scoring.config import ScoringConfig
from app.scoring.scorer import JobFitScorer
from app.semantic.fake_fixtures import ch, nl, sc
from tests.conftest import make_profile, make_semantic

CFG = ScoringConfig()


def texts(result, section):
    return [e.text for e in result.explanations if e.section == section]


def calc(sem, profile=None, **kw):
    return JobFitScorer().calculate(sem, profile or make_profile(), CFG, **kw)


def test_hedging_bands():
    plain = calc(make_semantic(android_relevance=sc(3.5, 5, conf=0.85)))
    likely = calc(make_semantic(android_relevance=sc(3.5, 5, conf=0.7)))
    unsure = calc(make_semantic(android_relevance=sc(3.5, 5, conf=0.4)))
    assert "Android is the main day-to-day work (3.5/4)" in texts(plain, "strength")
    assert "Likely: Android is the main day-to-day work (3.5/4)" in texts(likely, "strength")
    assert not any("Android is the main" in t for t in texts(unsure, "strength"))
    assert texts(unsure, "uncertain").count("android_relevance: confidence 0.40") == 1


def test_notes_and_stale():
    r = calc(make_semantic(), stale_semantics=True)
    assert "Sponsorship: not stated" in texts(r, "note")
    assert "Security clearance: no explicit requirement detected" in texts(r, "note")
    assert "Profile changed since this evaluation — re-evaluate for accurate results" in texts(r, "concern")
    assert r.stale_semantics


def test_title_vs_scope_and_years():
    sem = make_semantic(title_level=ch("staff", 0.9, options="Seniority"), seniority=ch("senior", 0.85, options="Seniority"),
                        min_years_required=ch("y8_10", 0.9, options="YearsBucket"),
                        evidence={"seniority": Evidence(line_id="L002", text="Own the booking screens", probability=0.8)})
    r = calc(sem, make_profile(years_experience=6))
    concern = next(e for e in r.explanations if e.text == "Title reads Staff; scope reads Senior")
    assert concern.evidence_line_id == "L002" and concern.confidence == 0.85
    assert "Asks 8–10 years; profile says 6" in texts(r, "concern")


def test_strengths_ordered_by_component_weight():
    sem = make_semantic(technical_fit=sc(3.5, 5), android_relevance=sc(3.5, 5), domain_fit=sc(3.5, 5),
                        domain=ch("fintech", 0.9, options="Domain"))
    s = texts(calc(sem), "strength")
    assert s.index("Strong technical match (3.5/4)") < s.index("Android is the main day-to-day work (3.5/4)") \
        < s.index("Background transfers to Fintech (3.5/4)")


def test_kmp_rules_and_penalty_concerns():
    kmp = SkillSignal(requirement=ch("preferred", 0.9, options="RequirementLevel"), evidence=sc(1, 4))
    sem = make_semantic(kmp_requirement=ch("preferred", 0.9, options="RequirementLevel"), skills={"kmp": kmp},
                        management_intensity=sc(3.5, 5), staff_ic_signal=nl(0.8))
    r = calc(sem, make_profile(management_preference="ic", preferred_levels=["staff"]))
    assert "KMP is preferred, not required" in texts(r, "strength")
    assert "KMP listed as preferred; weak resume evidence" in texts(r, "concern")
    assert "Management-heavy role for IC preference (−15)" in texts(r, "concern")
    assert "Likely: Staff-level IC scope (0.80)" in texts(r, "strength")  # derived confidence |2p-1| = 0.6


def test_work_arrangement_rules():
    remote = make_semantic(work_arrangement=ch("remote", 0.95, options="WorkArrangement"))
    assert "Remote, matches your preference" in texts(calc(remote, make_profile(remote_preference="remote")), "strength")
    onsite = make_semantic(work_arrangement=ch("onsite", 0.95, options="WorkArrangement"))
    assert "Onsite; you prefer remote" in texts(calc(onsite, make_profile(remote_preference="remote")), "concern")
    assert "Work arrangement not stated" in texts(calc(make_semantic()), "concern")
