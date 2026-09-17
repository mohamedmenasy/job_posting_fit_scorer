from app.domain import RequirementLine, SkillSignal
from app.scoring.config import ScoringConfig
from app.scoring.skills import evidence_level, missing_skills, skill_matches
from app.semantic.fake_fixtures import ch, sc
from tests.conftest import make_profile, make_semantic

CFG = ScoringConfig()
REQ = "RequirementLevel"


def skill(req, ev):
    return SkillSignal(requirement=ch(req, 0.9, options=REQ), evidence=sc(ev, 4))


def line(lid, kind, skill_id, ev, skills=("kmp", "kotlin", "none")):
    return RequirementLine(id=lid, text=f"text {lid}", kind=ch(kind, 0.9, options="LineKind"),
                           skill=ch(skill_id, 0.9, options=list(skills)), evidence=sc(ev, 4))


def test_evidence_levels():
    assert [evidence_level(x) for x in (0.49, 0.5, 1.49, 1.5, 2.49, 2.5)] == \
        ["none", "weak", "weak", "partial", "partial", "strong"]


def test_tracked_missing_importance_and_sort():
    sem = make_semantic(
        skills={"kotlin": skill("required", 0), "kmp": skill("preferred", 1), "java": skill("required", 2),
                "swift": skill("mentioned", 0), "android": skill("required", 3)},
        lines=[line("L001", "core_responsibility", "kotlin", 0), line("L002", "required_qualification", "none", 0),
               line("L003", "preferred_qualification", "none", 3), line("L004", "required_qualification", "kotlin", 0)])
    ms = missing_skills(sem, make_profile(), CFG)
    assert [(m.skill, m.importance, m.candidate_evidence, m.impact) for m in ms] == [
        ("Kotlin", "critical", "none", "significant"),
        ("text L002", "important", "none", "significant"),
        ("Java", "important", "partial", "minor"),
        ("Kotlin Multiplatform", "nice_to_have", "weak", "minor")]
    assert ms[0].line_ids == ["L004"]
    assert ms[1].source == "requirement_line" and ms[1].line_ids == ["L002"]


def test_skill_matches_exclude_not_mentioned():
    sem = make_semantic(skills={"kotlin": skill("required", 3), "swift": skill("not_mentioned", 0)},
                        lines=[line("L001", "required_qualification", "kotlin", 3)])
    [m] = skill_matches(sem, make_profile(), CFG)
    assert (m.skill, m.requirement_level, m.candidate_match, m.evidence_line_ids) == ("Kotlin", "required", 1.0, ["L001"])
    assert m.confidence == 0.9
