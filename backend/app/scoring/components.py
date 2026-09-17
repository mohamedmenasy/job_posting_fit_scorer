"""Weighted fit components and base score (spec §7.1–§7.2)."""

from app.domain import CandidateProfile, ComponentResult, SemanticJobEvaluation
from app.scoring.config import ScoringConfig


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def components(sem: SemanticJobEvaluation, profile: CandidateProfile, cfg: ScoringConfig) -> list[ComponentResult]:
    prefs = profile.preferences
    raw: list[tuple[str, float | None, float | None, str | None]] = []  # name, value, confidence, n/a reason

    raw.append(("technical", sem.technical_fit.normalized, sem.technical_fit.confidence, None))
    raw.append(("android", sem.android_relevance.normalized, sem.android_relevance.confidence, None))
    raw.append(("seniority", sem.seniority_fit.normalized, sem.seniority_fit.confidence, None))

    if not prefs.preferred_roles:
        raw.append(("role_preference", None, None, "n/a: no preferred roles set"))
    elif sem.role_preference_fit is None:
        raw.append(("role_preference", None, None, "n/a: preferred roles changed — re-evaluate to score"))
    else:
        raw.append(("role_preference", sem.role_preference_fit.normalized, sem.role_preference_fit.confidence, None))

    if not prefs.preferred_role_families and not prefs.avoided_role_families:
        raw.append(("platform", None, None, "n/a: no role-family preferences set"))
    else:
        def pref(family: str) -> float:
            if family in prefs.preferred_role_families:
                return 1.0
            if family in prefs.avoided_role_families:
                return 0.0
            return cfg.neutral_platform_preference
        value = sum(p * pref(f) for f, p in sem.role_family.probabilities.items())
        raw.append(("platform", value, sem.role_family.confidence, None))

    fit = sem.domain_fit.normalized
    if prefs.preferred_domains:
        blend = cfg.domain_preference_blend
        value = (1 - blend) * fit + blend * sem.domain.p(*prefs.preferred_domains)
        raw.append(("domain", value, _mean([sem.domain_fit.confidence, sem.domain.confidence]), None))
    else:
        raw.append(("domain", fit, sem.domain_fit.confidence, None))

    if prefs.remote_preference == "any":
        raw.append(("work_arrangement", None, None, "n/a: remote preference is any"))
    else:
        row = cfg.arrangement_matrix[prefs.remote_preference]
        value = sum(p * row.get(a, 0.0) for a, p in sem.work_arrangement.probabilities.items())
        confs = [sem.work_arrangement.confidence]
        if prefs.preferred_locations and sem.location_match is not None:
            lm = sem.location_match
            r = cfg.relocation_location_factor if prefs.willing_to_relocate else 0.0
            value *= lm.p("in_preferred_location") + 0.5 * lm.p("unclear") + r * lm.p("outside_preferred_locations")
            confs.append(lm.confidence)
        raw.append(("work_arrangement", value, _mean(confs), None))

    if prefs.management_preference == "any":
        raw.append(("management", None, None, "n/a: management preference is any"))
    else:
        m = sem.management_intensity.score
        value = {"ic": 1 - clamp((m - 1) / 3),
                 "tech_lead": 1 - clamp(abs(m - 2) / 2),
                 "manager": clamp((m - 1) / 3)}[prefs.management_preference]
        raw.append(("management", value, sem.management_intensity.confidence, None))

    weights = cfg.weights.model_dump()
    total = sum(weights[name] for name, value, _, _ in raw if value is not None)
    out = []
    for name, value, confidence, reason in raw:
        applicable = value is not None
        effective = weights[name] / total if applicable and total else 0.0
        out.append(ComponentResult(
            name=name, applicable=applicable, value=clamp(value) if applicable else None, weight=weights[name],
            effective_weight=effective, contribution=100 * effective * clamp(value) if applicable else 0.0,
            confidence=confidence, reason=reason))
    return out


def base_score(comps: list[ComponentResult]) -> float:
    return sum(c.contribution for c in comps)
