"""Domain enums and Pydantic models (spec §5)."""

import hashlib
import json
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

RoleFamily = Literal["android_native", "mobile_general", "ios", "kotlin_multiplatform", "flutter",
                     "react_native", "backend", "fullstack", "engineering_management", "other"]
Seniority = Literal["junior", "mid", "senior", "staff", "principal", "architect", "manager",
                    "senior_manager", "director_plus", "unclear"]
Domain = Literal["fintech", "healthcare", "ecommerce", "marketplace", "social", "media_streaming",
                 "automotive", "ai_ml", "enterprise", "developer_tools", "travel",
                 "delivery_logistics", "gaming", "government_defense", "other"]
WorkArrangement = Literal["remote", "hybrid", "onsite", "multiple_options", "unclear"]
RequirementLevel = Literal["required", "preferred", "mentioned", "not_mentioned"]
WorkAuthSignal = Literal["explicit_sponsorship_available", "explicit_no_sponsorship",
                         "explicit_specific_work_authorization_requirement", "not_stated", "ambiguous"]
YearsBucket = Literal["not_stated", "y0_2", "y3_4", "y5_7", "y8_10", "y11_plus"]
LineKind = Literal["required_qualification", "preferred_qualification", "core_responsibility", "other"]
LocationMatch = Literal["in_preferred_location", "outside_preferred_locations", "unclear"]
FitStatus = Literal["STRONG_MATCH", "GOOD_MATCH", "REVIEW", "LOW_MATCH", "BLOCKED"]
EvaluationStatus = Literal["pending", "running", "succeeded", "failed"]
JobSource = Literal["linkedin", "indeed", "company_site", "recruiter_email", "manual", "other"]
JobStatus = Literal["draft", "ready"]          # draft: incomplete import, editable, never evaluated
ImportSource = Literal["paste", "url", "csv"]  # how the posting reached JobFit, not where it was advertised

ENUMS = {name: globals()[name] for name in [
    "RoleFamily", "Seniority", "Domain", "WorkArrangement", "RequirementLevel", "WorkAuthSignal", "YearsBucket",
    "LineKind", "LocationMatch", "FitStatus", "EvaluationStatus", "JobSource", "JobStatus", "ImportSource"]}


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def tech_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ---------------------------------------------------------------- candidate profile (§5.2)

class CandidatePreferences(BaseModel):
    # semantic fields
    preferred_roles: list[str] = []
    preferred_locations: list[str] = []
    required_technologies: list[str] = []
    preferred_technologies: list[str] = []
    avoid_technologies: list[str] = []
    # scoring-only fields
    preferred_levels: list[Seniority] = []
    preferred_role_families: list[RoleFamily] = []
    avoided_role_families: list[RoleFamily] = []
    preferred_domains: list[Domain] = []
    remote_preference: Literal["remote", "hybrid", "onsite", "any"] = "any"
    willing_to_relocate: bool = False
    management_preference: Literal["ic", "tech_lead", "manager", "any"] = "any"
    years_experience: float | None = Field(default=None, ge=0)
    # display only
    work_authorization_notes: str | None = None

    @field_validator("preferred_roles", "preferred_locations", "required_technologies",
                     "preferred_technologies", "avoid_technologies")
    @classmethod
    def _strip_items(cls, v: list[str]) -> list[str]:
        return [item.strip() for item in v if item.strip()]

    @model_validator(mode="after")
    def _no_overlaps(self):
        seen: dict[str, str] = {}
        for field in ("required_technologies", "preferred_technologies", "avoid_technologies"):
            for tech in getattr(self, field):
                key = tech.strip().lower()
                if key in seen and seen[key] != field:
                    raise ValueError(f"technology {tech!r} appears in both {seen[key]} and {field}")
                seen[key] = field
        both = set(self.preferred_role_families) & set(self.avoided_role_families)
        if both:
            raise ValueError(f"role families both preferred and avoided: {sorted(both)}")
        return self


class BlockerFacts(BaseModel):
    needs_visa_sponsorship: bool | None = None
    can_meet_us_citizenship_requirement: bool | None = None
    can_meet_clearance_requirement: bool | None = None


class TrackedSkill(BaseModel):
    id: str
    label: str
    description: str = ""


_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")


class CandidateProfileIn(BaseModel):
    resume_text: str
    preferences: CandidatePreferences = CandidatePreferences()
    blocker_facts: BlockerFacts = BlockerFacts()
    tracked_skills: list[TrackedSkill]

    @field_validator("resume_text")
    @classmethod
    def _resume_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("resume_text must not be empty")
        return v

    @field_validator("tracked_skills")
    @classmethod
    def _skill_ids(cls, v: list[TrackedSkill]) -> list[TrackedSkill]:
        ids = [s.id for s in v]
        bad = [i for i in ids if not _SLUG.match(i)]
        if bad:
            raise ValueError(f"tracked skill ids must match ^[a-z][a-z0-9_]*$: {bad}")
        if len(set(ids)) != len(ids):
            raise ValueError("tracked skill ids must be unique")
        return v


class CandidateProfile(CandidateProfileIn):
    id: UUID
    created_at: datetime
    semantic_hash: str


def semantic_hash(p: CandidateProfileIn) -> str:
    prefs = p.preferences
    return sha256(canonical_json({
        "resume_text": p.resume_text,
        "preferred_roles": prefs.preferred_roles,
        "preferred_locations": prefs.preferred_locations,
        "required_technologies": prefs.required_technologies,
        "preferred_technologies": prefs.preferred_technologies,
        "avoid_technologies": prefs.avoid_technologies,
        "tracked_skills": [s.model_dump() for s in p.tracked_skills],
    }))


DEFAULT_TRACKED_SKILLS = [TrackedSkill(id=i, label=label, description=desc) for i, label, desc in [
    ("android", "Android", "native Android app development with the Android SDK"),
    ("kotlin", "Kotlin", ""),
    ("java", "Java", ""),
    ("jetpack_compose", "Jetpack Compose", "declarative Android UI toolkit"),
    ("coroutines", "Kotlin Coroutines and Flow", ""),
    ("architecture", "Mobile app architecture", "MVVM/MVI, modularization, clean architecture"),
    ("system_design", "Mobile or distributed system design", ""),
    ("testing", "Automated testing", "unit, UI, integration"),
    ("ci_cd", "CI/CD and release automation", ""),
    ("kmp", "Kotlin Multiplatform", ""),
    ("flutter", "Flutter", ""),
    ("react_native", "React Native", ""),
    ("ios", "Native iOS development", ""),
    ("swift", "Swift", ""),
    ("backend", "Backend or server-side development", ""),
    ("leadership", "Technical leadership and mentoring", ""),
    ("people_management", "People management", "direct reports, performance reviews, hiring"),
    ("ai_ml", "AI/ML", "on-device ML, LLM integration, ML platforms"),
]]


# ---------------------------------------------------------------- job posting (§5.3)

class JobPostingIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=50)
    location: str | None = None
    source: JobSource = "manual"
    source_url: HttpUrl | None = None
    salary_text: str | None = None
    external_id: str | None = None

    @field_validator("company", "title", "description", "location", "salary_text", "external_id", mode="before")
    @classmethod
    def _strip(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("location", "salary_text", "external_id")
    @classmethod
    def _empty_to_none(cls, v):
        return v or None

    @field_validator("source_url")
    @classmethod
    def _http_only(cls, v):
        if v is not None and v.scheme not in ("http", "https"):
            raise ValueError("source_url must be http or https")
        return v


class JobDraftIn(JobPostingIn):
    """An incomplete posting (import §3.2): description may be empty until the user completes it."""

    description: str = ""
    import_source: ImportSource = "paste"


class JobPatch(BaseModel):
    """Fields editable on a draft (import §7). Unset fields are left unchanged."""

    company: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    location: str | None = None
    source: JobSource | None = None
    source_url: HttpUrl | None = None
    salary_text: str | None = None
    external_id: str | None = None

    _strip = field_validator("company", "title", "description", "location", "salary_text", "external_id",
                             mode="before")(lambda cls, v: v.strip() if isinstance(v, str) else v)

    @field_validator("source_url")
    @classmethod
    def _http_only(cls, v):
        if v is not None and v.scheme not in ("http", "https"):
            raise ValueError("source_url must be http or https")
        return v


MIN_DESCRIPTION = 50


class JobPosting(JobPostingIn):
    id: UUID
    content_hash: str
    created_at: datetime
    imported_at: datetime
    status: JobStatus = "ready"
    import_source: ImportSource = "paste"


# ---------------------------------------------------------------- semantic evaluation (§5.4)

class ChoiceSignal(BaseModel):
    value: str
    probabilities: dict[str, float]
    confidence: float

    def p(self, *values: str) -> float:
        return sum(self.probabilities.get(v, 0.0) for v in values)


class ScoreSignal(BaseModel):
    score: float
    levels: int
    normalized: float
    probabilities: dict[int, float]
    confidence: float


class NoulSignal(BaseModel):
    probability: float
    derived_confidence: float


class Evidence(BaseModel):
    line_id: str | None
    text: str | None
    probability: float


class SkillSignal(BaseModel):
    requirement: ChoiceSignal
    evidence: ScoreSignal


class RequirementLine(BaseModel):
    id: str
    text: str
    kind: ChoiceSignal
    skill: ChoiceSignal
    evidence: ScoreSignal


class RequestMeta(BaseModel):
    request_id: str | None
    state_kind: Literal["job", "fit"]
    question_count: int
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    raw_response: dict


class SemanticSignals(BaseModel):
    """All semantic signals and metadata except raw request data (what evaluations store in `signals`)."""

    role_family: ChoiceSignal
    android_relevance: ScoreSignal
    seniority: ChoiceSignal
    title_level: ChoiceSignal
    staff_ic_signal: NoulSignal
    management_intensity: ScoreSignal
    kmp_requirement: ChoiceSignal
    cross_platform_intensity: ScoreSignal
    domain: ChoiceSignal
    work_arrangement: ChoiceSignal
    requires_relocation: NoulSignal
    security_clearance_required: NoulSignal
    us_citizenship_required: NoulSignal
    work_authorization_signal: ChoiceSignal
    min_years_required: ChoiceSignal
    technical_fit: ScoreSignal
    seniority_fit: ScoreSignal
    domain_fit: ScoreSignal
    role_preference_fit: ScoreSignal | None
    location_match: ChoiceSignal | None
    skills: dict[str, SkillSignal]
    technologies: dict[str, ScoreSignal]
    lines: list[RequirementLine]
    all_lines: dict[str, str]
    evidence: dict[str, Evidence]
    model: str
    evaluator_version: str
    catalog_hash: str
    question_set_hash: str


class SemanticJobEvaluation(SemanticSignals):
    requests: list[RequestMeta]


# ---------------------------------------------------------------- fit result (§5.5)

class ComponentResult(BaseModel):
    name: str
    applicable: bool
    value: float | None
    weight: float
    effective_weight: float
    contribution: float
    confidence: float | None
    reason: str | None


class Penalty(BaseModel):
    type: str
    points: float
    reason: str
    signal_ids: list[str]


class HardBlocker(BaseModel):
    type: str
    reason: str
    confidence: float
    evidence: str | None


class SkillMatch(BaseModel):
    skill: str
    requirement_level: Literal["required", "preferred", "mentioned"]
    candidate_match: float
    confidence: float
    evidence_line_ids: list[str]


class MissingSkill(BaseModel):
    skill: str
    source: Literal["tracked_skill", "requirement_line"]
    importance: Literal["critical", "important", "nice_to_have"]
    candidate_evidence: Literal["none", "weak", "partial"]
    impact: Literal["blocker", "significant", "minor"]
    line_ids: list[str]


class Explanation(BaseModel):
    section: Literal["strength", "concern", "uncertain", "note"]
    text: str
    signal_ids: list[str]
    confidence: float | None
    evidence_line_id: str | None


class JobFitResult(BaseModel):
    overall_score: float
    base_score: float
    status: FitStatus
    aggregate_confidence: float
    needs_review: bool
    stale_semantics: bool
    components: list[ComponentResult]
    penalties: list[Penalty]
    hard_blockers: list[HardBlocker]
    possible_blockers: list[HardBlocker]
    skill_matches: list[SkillMatch]
    missing_skills: list[MissingSkill]
    explanations: list[Explanation]
    uncertain_signals: list[str]
