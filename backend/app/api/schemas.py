"""Response models: FastAPI validates router output against these and publishes them in OpenAPI
(the frontend's generated types come from here)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.domain import (
    CandidateProfile,
    ImportSource,
    JobStatus,
    EvaluationStatus,
    FitStatus,
    JobFitResult,
    JobSource,
    RequestMeta,
    SemanticSignals,
    TrackedSkill,
)
from app.scoring.config import ScoringConfig


class JobOut(BaseModel):
    id: UUID
    status_kind: JobStatus
    import_source: ImportSource
    company: str
    title: str
    location: str | None
    source: JobSource
    source_url: str | None
    external_id: str | None
    salary_text: str | None
    description: str
    content_hash: str
    created_at: datetime
    imported_at: datetime


class FitResultOut(JobFitResult):
    id: UUID
    evaluation_id: UUID
    profile_version_id: UUID
    scoring_config_id: UUID
    scoring_config_version: int
    created_at: datetime


class EvaluationOut(BaseModel):
    id: UUID
    job_id: UUID
    profile_version_id: UUID
    evaluator_version: str | None
    catalog_hash: str | None
    question_set_hash: str | None
    model: str | None
    status: EvaluationStatus
    error: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    fit_results: list[FitResultOut] = []


class EvaluationDetailOut(EvaluationOut):
    signals: SemanticSignals | None = None
    raw_typesafe_response: list[RequestMeta] | None = None


class JobDetailOut(BaseModel):
    job: JobOut
    fit_result: FitResultOut | None
    evaluation: EvaluationDetailOut | None
    latest_evaluation: EvaluationOut | None


class JobRowOut(BaseModel):
    id: UUID
    status_kind: JobStatus
    import_source: ImportSource
    company: str
    title: str
    location: str | None
    source: JobSource
    created_at: datetime
    overall_score: float | None
    status: FitStatus | None
    aggregate_confidence: float | None
    needs_review: bool | None
    role_family: str | None
    seniority: str | None
    domain: str | None
    work_arrangement: str | None
    kmp_requirement: str | None
    work_authorization_signal: str | None
    android_relevance: float | None
    security_clearance_required: float | None
    evaluation_status: EvaluationStatus | None
    evaluation_error: str | None
    latest_evaluation_id: UUID | None


class JobStatsOut(BaseModel):
    total: int
    drafts: int
    evaluated: int
    strong: int
    good: int
    review: int
    low: int
    blocked: int
    pending: int
    failed: int


class JobListOut(BaseModel):
    rows: list[JobRowOut]
    total_filtered: int
    stats: JobStatsOut


class CreateJobOut(BaseModel):
    job: JobOut
    created: bool


class JobPatchOut(BaseModel):
    job: JobOut


class BatchOut(BaseModel):
    created: int
    existing: int
    evaluation_ids: list[UUID]


class EnqueuedOut(BaseModel):
    evaluation_id: UUID
    status: EvaluationStatus


class EvaluationIdsOut(BaseModel):
    evaluation_ids: list[UUID]


class EvaluatePostingOut(BaseModel):
    job: JobOut
    evaluation_id: UUID
    created: bool
    reused: bool


class ProfileSaveOut(BaseModel):
    profile: CandidateProfile
    change_kind: Literal["none", "scoring_only", "semantic"]
    affected_jobs: int
    rescored: int


class ResumeTextOut(BaseModel):
    text: str


class RequestQuestionOut(BaseModel):
    id: str
    state: Literal["job", "fit"]
    body: dict


class RequestRebuildOut(BaseModel):
    states: dict[str, dict]
    questions: list[RequestQuestionOut]
    question_set_hash: str
    hash_matches: bool


class ScoringSettingsOut(BaseModel):
    version: int
    config: ScoringConfig
    defaults: ScoringConfig


class RescoreOut(BaseModel):
    version: int
    rescored: int


class FetchedPostingOut(BaseModel):
    company: str | None
    title: str | None
    location: str | None
    description: str
    salary_text: str | None
    source: JobSource
    source_url: str
    provider: str
    confidence: Literal["structured", "extracted"]
    warnings: list[str]


class ImportUrlOut(BaseModel):
    posting: FetchedPostingOut


class CsvPreviewOut(BaseModel):
    columns: list[str]
    suggested_mapping: dict[str, str | None]
    row_count: int
    preview: list[dict[str, str]]
    rows: list[dict[str, str]]
    delimiter: str
    encoding: str


class CsvRowError(BaseModel):
    row: int
    reason: str


class CsvCommitOut(BaseModel):
    created: int
    duplicates: int
    drafts: int
    errors: list[CsvRowError]
    job_ids: list[UUID]


class EnumOption(BaseModel):
    value: str
    label: str


class MetaOut(BaseModel):
    enums: dict[str, list[EnumOption]]
    default_tracked_skills: list[TrackedSkill]
    evaluator_version: str
    model: str


class HealthOut(BaseModel):
    status: Literal["ok"]
    evaluator: Literal["typesafe", "fake"]
    model: str
    api_key_configured: bool
    queue_depth: int
