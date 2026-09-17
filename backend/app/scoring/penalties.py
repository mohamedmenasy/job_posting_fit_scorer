"""Score penalties, each applied at most once per job (spec §7.3)."""

from app.domain import CandidateProfile, MissingSkill, Penalty, SemanticJobEvaluation, tech_slug
from app.scoring.config import ScoringConfig


def penalties(sem: SemanticJobEvaluation, profile: CandidateProfile, cfg: ScoringConfig,
              missing: list[MissingSkill]) -> list[Penalty]:
    prefs = profile.preferences
    pc = cfg.penalties
    out: list[Penalty] = []

    c = pc.avoided_tech_heavy
    if c.enabled:
        heavy_family = (sem.cross_platform_intensity.score >= c.min_cross_platform_intensity
                        and set(prefs.avoided_role_families) & set(c.cross_platform_families))
        heavy_tech = [t for t in prefs.avoid_technologies
                      if (s := sem.technologies.get(tech_slug(t))) and s.score >= c.min_tech_centrality]
        if heavy_family or heavy_tech:
            signals = (["cross_platform_intensity"] if heavy_family else []) + [f"tech_centrality.{tech_slug(t)}" for t in heavy_tech]
            out.append(Penalty(type="avoided_tech_heavy", points=c.points, signal_ids=signals,
                               reason="Heavy use of an avoided technology"))

    c = pc.management_heavy_for_ic
    if c.enabled and prefs.management_preference == "ic" and sem.management_intensity.score >= c.min_intensity:
        out.append(Penalty(type="management_heavy_for_ic", points=c.points, signal_ids=["management_intensity"],
                           reason="Management-heavy role for IC preference"))

    c = pc.seniority_mismatch
    if (c.enabled and prefs.preferred_levels
            and sem.seniority.p(*prefs.preferred_levels) < c.max_preferred_probability
            and sem.seniority.p("unclear") < c.max_unclear_probability):
        out.append(Penalty(type="seniority_mismatch", points=c.points, signal_ids=["seniority"],
                           reason="Seniority outside preferred levels"))

    c = pc.required_tech_weak
    if c.enabled:
        weak = [t for t in prefs.required_technologies
                if (s := sem.technologies.get(tech_slug(t))) and s.score <= c.max_centrality]
        if weak:
            out.append(Penalty(type="required_tech_weak", points=c.points,
                               signal_ids=[f"tech_centrality.{tech_slug(t)}" for t in weak],
                               reason=f"Required technology {', '.join(weak)} is not central"))

    c = pc.missing_required_skill
    if c.enabled:
        counted = [m for m in missing if m.importance in ("critical", "important") and m.candidate_evidence in ("none", "weak")]
        points = min(c.cap, sum(c.points_none if m.candidate_evidence == "none" else c.points_weak for m in counted))
        if points:
            out.append(Penalty(type="missing_required_skill", points=points, signal_ids=[],
                               reason=f"Missing required skills: {', '.join(m.skill for m in counted)}"))
    return out
