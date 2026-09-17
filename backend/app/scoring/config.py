"""Versionable scoring configuration (spec §7.10)."""

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

Prob = Annotated[float, Field(ge=0, le=1)]
NonNeg = Annotated[float, Field(ge=0)]

ARRANGEMENTS = ("remote", "hybrid", "onsite", "multiple_options", "unclear")


class Weights(BaseModel):
    technical: NonNeg = 30
    android: NonNeg = 20
    seniority: NonNeg = 15
    role_preference: NonNeg = 10
    platform: NonNeg = 10
    domain: NonNeg = 5
    work_arrangement: NonNeg = 5
    management: NonNeg = 5

    @model_validator(mode="after")
    def _core_positive(self):
        if self.technical + self.android + self.seniority + self.domain <= 0:
            raise ValueError("weights of technical, android, seniority, domain must sum to > 0")
        return self


class AvoidedTechHeavy(BaseModel):
    enabled: bool = True
    points: NonNeg = 10
    min_cross_platform_intensity: NonNeg = 2.5
    cross_platform_families: list[str] = ["flutter", "react_native"]
    min_tech_centrality: NonNeg = 2.0


class ManagementHeavyForIc(BaseModel):
    enabled: bool = True
    points: NonNeg = 15
    min_intensity: NonNeg = 2.5


class SeniorityMismatch(BaseModel):
    enabled: bool = True
    points: NonNeg = 10
    max_preferred_probability: Prob = 0.4
    max_unclear_probability: Prob = 0.5


class RequiredTechWeak(BaseModel):
    enabled: bool = True
    points: NonNeg = 10
    max_centrality: NonNeg = 1.0


class MissingRequiredSkill(BaseModel):
    enabled: bool = True
    points_none: NonNeg = 10
    points_weak: NonNeg = 5
    cap: NonNeg = 20


class Penalties(BaseModel):
    avoided_tech_heavy: AvoidedTechHeavy = AvoidedTechHeavy()
    management_heavy_for_ic: ManagementHeavyForIc = ManagementHeavyForIc()
    seniority_mismatch: SeniorityMismatch = SeniorityMismatch()
    required_tech_weak: RequiredTechWeak = RequiredTechWeak()
    missing_required_skill: MissingRequiredSkill = MissingRequiredSkill()


class Toggle(BaseModel):
    enabled: bool = True


class TechnologyMismatch(BaseModel):
    enabled: bool = True
    avoid_core_probability: Prob = 0.8
    required_absent_probability: Prob = 0.9


class SeniorityFarBelow(BaseModel):
    enabled: bool = True
    min_steps_below: int = Field(default=2, ge=1)


class Blockers(BaseModel):
    threshold: Prob = 0.8
    possible_threshold: Prob = 0.5
    security_clearance: Toggle = Toggle()
    us_citizenship: Toggle = Toggle()
    no_sponsorship: Toggle = Toggle()
    relocation: Toggle = Toggle()
    onsite_location: Toggle = Toggle()
    technology_mismatch: TechnologyMismatch = TechnologyMismatch()
    seniority_far_below: SeniorityFarBelow = SeniorityFarBelow()

    @model_validator(mode="after")
    def _ordered(self):
        if self.possible_threshold >= self.threshold:
            raise ValueError("possible_threshold must be < threshold")
        return self


class StatusThresholds(BaseModel):
    strong_match: float = 85
    good_match: float = 70
    review: float = 55

    @model_validator(mode="after")
    def _ordered(self):
        if not self.review < self.good_match < self.strong_match:
            raise ValueError("status thresholds must satisfy review < good_match < strong_match")
        return self


class ConfidenceBands(BaseModel):
    accept: Prob = 0.8
    review: Prob = 0.6

    @model_validator(mode="after")
    def _ordered(self):
        if self.review >= self.accept:
            raise ValueError("confidence_bands.review must be < accept")
        return self


class MissingSkillsConfig(BaseModel):
    min_line_kind_probability: Prob = 0.6
    min_line_skill_none_probability: Prob = 0.5


def _default_matrix() -> dict[str, dict[str, float]]:
    return {
        "remote": {"remote": 1.0, "hybrid": 0.4, "onsite": 0.0, "multiple_options": 0.9, "unclear": 0.5},
        "hybrid": {"remote": 1.0, "hybrid": 1.0, "onsite": 0.4, "multiple_options": 1.0, "unclear": 0.5},
        "onsite": {"remote": 0.8, "hybrid": 1.0, "onsite": 1.0, "multiple_options": 1.0, "unclear": 0.5},
    }


class ScoringConfig(BaseModel):
    weights: Weights = Weights()
    neutral_platform_preference: Prob = 0.5
    domain_preference_blend: Prob = 0.5
    relocation_location_factor: Prob = 0.5
    arrangement_matrix: dict[str, dict[str, Prob]] = Field(default_factory=_default_matrix)
    penalties: Penalties = Penalties()
    blockers: Blockers = Blockers()
    status_thresholds: StatusThresholds = StatusThresholds()
    confidence_bands: ConfidenceBands = ConfidenceBands()
    missing_skills: MissingSkillsConfig = MissingSkillsConfig()
    evidence_min_probability: Prob = 0.5

    @model_validator(mode="after")
    def _matrix_complete(self):
        for pref in ("remote", "hybrid", "onsite"):
            if set(self.arrangement_matrix.get(pref, {})) != set(ARRANGEMENTS):
                raise ValueError(f"arrangement_matrix.{pref} must define {ARRANGEMENTS}")
        return self
