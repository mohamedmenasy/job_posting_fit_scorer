"""Confidence aggregation (spec §7.6). Confidence never changes fit status."""

from typing import Literal

from app.domain import CandidateProfile, ComponentResult, SemanticJobEvaluation
from app.scoring.config import ScoringConfig


def band(confidence: float, cfg: ScoringConfig) -> Literal["accepted", "review", "uncertain"]:
    if confidence >= cfg.confidence_bands.accept:
        return "accepted"
    return "review" if confidence >= cfg.confidence_bands.review else "uncertain"


def component_signals(name: str, sem: SemanticJobEvaluation, profile: CandidateProfile) -> list[str]:
    prefs = profile.preferences
    return {
        "technical": ["technical_fit"], "android": ["android_relevance"], "seniority": ["seniority_fit"],
        "role_preference": ["role_preference_fit"], "platform": ["role_family"],
        "domain": ["domain_fit"] + (["domain"] if prefs.preferred_domains else []),
        "work_arrangement": ["work_arrangement"] + (["location_match"] if sem.location_match and prefs.preferred_locations else []),
        "management": ["management_intensity"],
    }[name]


def aggregate_confidence(comps: list[ComponentResult]) -> float:
    applicable = [c for c in comps if c.applicable]
    total = sum(c.effective_weight for c in applicable)
    return sum(c.effective_weight * c.confidence for c in applicable) / total if total else 0.0


def uncertain_signals(sem: SemanticJobEvaluation, profile: CandidateProfile, comps: list[ComponentResult],
                      cfg: ScoringConfig) -> list[str]:
    out: list[str] = []
    for c in comps:
        if not c.applicable:
            continue
        for signal in component_signals(c.name, sem, profile):
            if getattr(sem, signal).confidence < cfg.confidence_bands.review and signal not in out:
                out.append(signal)
    return out
