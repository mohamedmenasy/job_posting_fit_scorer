"""Skill matches and missing skills (spec §7.7–§7.8)."""

from typing import Literal

from app.domain import CandidateProfile, MissingSkill, RequirementLine, SemanticJobEvaluation, SkillMatch
from app.scoring.config import ScoringConfig

EvidenceLevel = Literal["none", "weak", "partial", "strong"]
_IMPORTANCE = {"critical": 0, "important": 1, "nice_to_have": 2}
_EVIDENCE = {"none": 0, "weak": 1, "partial": 2}


def evidence_level(score: float) -> EvidenceLevel:
    if score < 0.5:
        return "none"
    if score < 1.5:
        return "weak"
    return "partial" if score < 2.5 else "strong"


def _mapped(line: RequirementLine, skill_id: str) -> bool:
    return line.skill.p(skill_id) >= 0.5


def _qualification_lines(sem: SemanticJobEvaluation, skill_id: str, cfg: ScoringConfig) -> list[str]:
    threshold = cfg.missing_skills.min_line_kind_probability
    return [line.id for line in sem.lines if _mapped(line, skill_id)
            and line.kind.p("required_qualification", "preferred_qualification") >= threshold]


def _labels(profile: CandidateProfile) -> dict[str, str]:
    return {s.id: s.label for s in profile.tracked_skills}


def skill_matches(sem: SemanticJobEvaluation, profile: CandidateProfile, cfg: ScoringConfig) -> list[SkillMatch]:
    labels = _labels(profile)
    return [SkillMatch(skill=labels.get(sid, sid), requirement_level=sig.requirement.value,
                       candidate_match=sig.evidence.normalized,
                       confidence=min(sig.requirement.confidence, sig.evidence.confidence),
                       evidence_line_ids=_qualification_lines(sem, sid, cfg))
            for sid, sig in sem.skills.items() if sig.requirement.value != "not_mentioned"]


def _impact(importance: str, evidence: str) -> str:
    return "significant" if importance in ("critical", "important") and evidence in ("none", "weak") else "minor"


def missing_skills(sem: SemanticJobEvaluation, profile: CandidateProfile, cfg: ScoringConfig) -> list[MissingSkill]:
    labels = _labels(profile)
    kind_threshold = cfg.missing_skills.min_line_kind_probability
    out: list[MissingSkill] = []
    for sid, sig in sem.skills.items():
        level = evidence_level(sig.evidence.score)
        if sig.requirement.value not in ("required", "preferred") or level == "strong":
            continue
        if sig.requirement.value == "preferred":
            importance = "nice_to_have"
        elif any(_mapped(line, sid) and line.kind.p("core_responsibility") >= kind_threshold for line in sem.lines):
            importance = "critical"
        else:
            importance = "important"
        out.append(MissingSkill(skill=labels.get(sid, sid), source="tracked_skill", importance=importance,
                                candidate_evidence=level, impact=_impact(importance, level),
                                line_ids=_qualification_lines(sem, sid, cfg)))
    for line in sem.lines:
        level = evidence_level(line.evidence.score)
        required, preferred = line.kind.p("required_qualification"), line.kind.p("preferred_qualification")
        if (required + preferred >= kind_threshold
                and line.skill.p("none") >= cfg.missing_skills.min_line_skill_none_probability and level != "strong"):
            importance = "important" if required >= preferred else "nice_to_have"
            out.append(MissingSkill(skill=line.text, source="requirement_line", importance=importance,
                                    candidate_evidence=level, impact=_impact(importance, level), line_ids=[line.id]))
    return sorted(out, key=lambda m: (_IMPORTANCE[m.importance], _EVIDENCE[m.candidate_evidence]))
