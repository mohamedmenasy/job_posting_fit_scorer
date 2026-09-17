"""JobFitScorer: pure, deterministic combination of semantic signals (spec §7)."""

from app.domain import CandidateProfile, FitStatus, JobFitResult, SemanticJobEvaluation
from app.scoring.blockers import evaluate_blockers
from app.scoring.components import base_score, clamp, components
from app.scoring.confidence import aggregate_confidence, uncertain_signals
from app.scoring.config import ScoringConfig
from app.scoring.explain import explanations
from app.scoring.penalties import penalties
from app.scoring.skills import missing_skills, skill_matches


def status_for(score: float, *, blocked: bool, cfg: ScoringConfig) -> FitStatus:
    t = cfg.status_thresholds
    if blocked:
        return "BLOCKED"
    if score >= t.strong_match:
        return "STRONG_MATCH"
    if score >= t.good_match:
        return "GOOD_MATCH"
    return "REVIEW" if score >= t.review else "LOW_MATCH"


class JobFitScorer:
    def calculate(self, sem: SemanticJobEvaluation, profile: CandidateProfile, cfg: ScoringConfig, *,
                  stale_semantics: bool = False) -> JobFitResult:
        comps = components(sem, profile, cfg)
        base = base_score(comps)
        missing = missing_skills(sem, profile, cfg)
        pens = penalties(sem, profile, cfg, missing)
        overall = clamp(base - sum(p.points for p in pens), 0, 100)
        hard, possible, blocker_concerns = evaluate_blockers(sem, profile, cfg)
        agg = aggregate_confidence(comps)
        uncertain = uncertain_signals(sem, profile, comps, cfg)
        return JobFitResult(
            overall_score=overall, base_score=base, status=status_for(overall, blocked=bool(hard), cfg=cfg),
            aggregate_confidence=agg,
            needs_review=agg < cfg.confidence_bands.accept or bool(uncertain) or bool(possible),
            stale_semantics=stale_semantics, components=comps, penalties=pens, hard_blockers=hard,
            possible_blockers=possible, skill_matches=skill_matches(sem, profile, cfg), missing_skills=missing,
            explanations=explanations(sem, profile, cfg, comps=comps, penalties=pens, blocker_concerns=blocker_concerns,
                                      stale_semantics=stale_semantics, uncertain=uncertain),
            uncertain_signals=uncertain)
