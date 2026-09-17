import pytest

from app.domain import MissingSkill
from app.scoring.config import ScoringConfig
from app.scoring.penalties import penalties
from app.semantic.fake_fixtures import ch, sc
from tests.conftest import make_profile, make_semantic

CFG = ScoringConfig()


def types(sem, profile, missing=(), cfg=CFG):
    return {p.type: p.points for p in penalties(sem, profile, cfg, list(missing))}


@pytest.mark.parametrize("score,fires", [(2.5, True), (2.4, False)])
def test_avoided_tech_heavy_via_family(score, fires):
    sem = make_semantic(cross_platform_intensity=sc(score, 5))
    assert ("avoided_tech_heavy" in types(sem, make_profile(avoided_role_families=["flutter"]))) is fires


def test_avoided_tech_heavy_once_when_both_triggers():
    sem = make_semantic(cross_platform_intensity=sc(3.5, 5), technologies={"flutter": sc(3, 4)})
    assert types(sem, make_profile(avoided_role_families=["flutter"], avoid_technologies=["Flutter"])) == {"avoided_tech_heavy": 10}


def test_avoided_technology_centrality_boundary():
    p = make_profile(avoid_technologies=["Flutter"])
    assert "avoided_tech_heavy" in types(make_semantic(technologies={"flutter": sc(2.0, 4)}), p)
    assert "avoided_tech_heavy" not in types(make_semantic(technologies={"flutter": sc(1.9, 4)}), p)


@pytest.mark.parametrize("m,fires", [(2.5, True), (2.4, False)])
def test_management_heavy_for_ic(m, fires):
    sem = make_semantic(management_intensity=sc(m, 5))
    assert ("management_heavy_for_ic" in types(sem, make_profile(management_preference="ic"))) is fires
    assert "management_heavy_for_ic" not in types(sem, make_profile(management_preference="manager"))


def test_seniority_mismatch_respects_unclear():
    p = make_profile(preferred_levels=["staff"])
    assert "seniority_mismatch" in types(make_semantic(seniority=ch("senior", 0.9, options="Seniority")), p)
    assert "seniority_mismatch" not in types(make_semantic(seniority=ch("unclear", 0.9, options="Seniority")), p)
    assert "seniority_mismatch" not in types(make_semantic(seniority=ch("staff", 0.9, options="Seniority")), p)
    assert "seniority_mismatch" not in types(make_semantic(seniority=ch("senior", 0.9, options="Seniority")), make_profile())


@pytest.mark.parametrize("score,fires", [(1.0, True), (1.1, False)])
def test_required_tech_weak(score, fires):
    sem = make_semantic(technologies={"kotlin": sc(score, 4)})
    assert ("required_tech_weak" in types(sem, make_profile(required_technologies=["Kotlin"]))) is fires


def test_missing_required_skill_points_and_cap():
    def ms(imp, ev):
        return MissingSkill(skill="x", source="tracked_skill", importance=imp, candidate_evidence=ev, impact="minor", line_ids=[])
    assert types(make_semantic(), make_profile(), [ms("critical", "weak")]) == {"missing_required_skill": 5}
    assert types(make_semantic(), make_profile(), [ms("important", "none")] * 3) == {"missing_required_skill": 20}
    assert types(make_semantic(), make_profile(), [ms("nice_to_have", "none"), ms("important", "partial")]) == {}


def test_disabled_penalty_skipped():
    cfg = ScoringConfig()
    cfg.penalties.management_heavy_for_ic.enabled = False
    assert types(make_semantic(management_intensity=sc(4, 5)), make_profile(management_preference="ic"), cfg=cfg) == {}
