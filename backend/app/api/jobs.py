from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import defer, selectinload

from app.api.deps import SessionDep, WorkerDep, require_profile
from app.api.schemas import (
    BatchOut,
    CreateJobOut,
    JobPatchOut,
    EnqueuedOut,
    EvaluatePostingOut,
    EvaluationIdsOut,
    JobDetailOut,
    JobListOut,
)
from app.api.serializers import evaluation_out, fit_out, job_out
from app.domain import JobDraftIn, JobPatch, JobPostingIn
from app.ingest.normalize import content_hash, find_by_content, get_or_create_job, job_status
from app.models import FitResult, JobEvaluation, JobPostingRow
from app.pipeline.worker import create_evaluation
from app.semantic.catalog import EVALUATOR_VERSION

router = APIRouter(tags=["jobs"])


def _job(session, job_id: UUID) -> JobPostingRow:
    row = session.get(JobPostingRow, job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    return row


@router.post("/jobs", status_code=201, response_model=CreateJobOut)
def create_job(body: JobPostingIn, session: SessionDep, response: Response):
    row, created = get_or_create_job(session, body)
    session.commit()
    if not created:
        response.status_code = 200
    return {"job": job_out(row), "created": created}


DRAFT_MESSAGE = "Add a job description before evaluating"


@router.post("/jobs/draft", status_code=201, response_model=CreateJobOut)
def create_draft(body: JobDraftIn, session: SessionDep, response: Response):
    """Store an incomplete posting (import §3.2). Drafts are editable and never evaluated."""
    row, created = get_or_create_job(session, body)
    session.commit()
    if not created:
        response.status_code = 200
    return {"job": job_out(row), "created": created}


@router.patch("/jobs/{job_id}", response_model=JobPatchOut)
def patch_job(job_id: UUID, body: JobPatch, session: SessionDep):
    row = _job(session, job_id)
    if any(e.status == "succeeded" for e in row.evaluations):
        raise HTTPException(409, "Evaluated jobs are immutable — create a new job instead")
    patch = body.model_dump(exclude_unset=True)
    for key, value in patch.items():
        setattr(row, key, str(value) if key == "source_url" and value is not None else value)
    digest = content_hash(row.company, row.title, row.description)
    clash = find_by_content(session, digest)
    if clash is not None and clash.id != row.id:
        session.rollback()
        raise HTTPException(409, {"message": "Another job already has this content", "existing_job_id": str(clash.id)})
    row.content_hash = digest
    if row.status == "draft":
        row.status = job_status(row.description)
    session.commit()
    return {"job": job_out(row)}


class BatchIn(BaseModel):
    jobs: list[JobPostingIn] = Field(max_length=500)
    auto_evaluate: bool = False


@router.post("/jobs/batch", response_model=BatchOut)
def batch_create(body: BatchIn, session: SessionDep, worker: WorkerDep):
    profile = require_profile(session) if body.auto_evaluate else None
    created, existing, evaluation_ids = 0, 0, []
    for posting in body.jobs:
        row, is_new = get_or_create_job(session, posting)
        if not is_new:
            existing += 1
            continue
        created += 1
        if profile:
            evaluation_ids.append(create_evaluation(session, row.id, profile.id).id)
    session.commit()
    for evaluation_id in evaluation_ids:
        worker.enqueue(evaluation_id)
    return {"created": created, "existing": existing, "evaluation_ids": evaluation_ids}


SortKey = Literal["score", "confidence", "company", "created_at", "android_relevance"]


def _row(job: JobPostingRow) -> dict:
    fit: FitResult | None = job.current_fit_result
    ev: JobEvaluation | None = fit.evaluation if fit else None
    latest = job.evaluations[-1] if job.evaluations else None
    headline = ("role_family", "seniority", "domain", "work_arrangement", "kmp_requirement", "work_authorization_signal",
                "android_relevance", "security_clearance_required")
    return {"id": job.id, "status_kind": job.status, "import_source": job.import_source, "company": job.company, "title": job.title, "location": job.location, "source": job.source,
            "created_at": job.created_at, "overall_score": fit.overall_score if fit else None,
            "status": fit.status if fit else None, "aggregate_confidence": fit.aggregate_confidence if fit else None,
            "needs_review": fit.needs_review if fit else None,
            **{k: getattr(ev, k) if ev else None for k in headline},
            "evaluation_status": latest.status if latest else None, "evaluation_error": latest.error if latest else None,
            "latest_evaluation_id": latest.id if latest else None}


@router.get("/jobs", response_model=JobListOut)
def list_jobs(
    session: SessionDep,
    q: str | None = None,
    min_score: float | None = None,
    status: Annotated[list[str] | None, Query()] = None,
    state: Annotated[list[str] | None, Query()] = None,
    company: str | None = None,
    role_family: Annotated[list[str] | None, Query()] = None,
    seniority: Annotated[list[str] | None, Query()] = None,
    domain: Annotated[list[str] | None, Query()] = None,
    work_arrangement: Annotated[list[str] | None, Query()] = None,
    kmp_requirement: Annotated[list[str] | None, Query()] = None,
    min_android_relevance: float | None = None,
    clearance: Literal["required", "possible", "not_required"] | None = None,
    work_authorization_signal: Annotated[list[str] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    evaluation_status: Annotated[list[str] | None, Query()] = None,
    needs_review: bool | None = None,
    sort: SortKey = "score",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    # ponytail: in-memory filter/sort over all jobs; move to SQL if job count grows past ~10k
    jobs = session.scalars(select(JobPostingRow).options(
        selectinload(JobPostingRow.evaluations).options(defer(JobEvaluation.signals), defer(JobEvaluation.raw_typesafe_response)),
        selectinload(JobPostingRow.current_fit_result).selectinload(FitResult.evaluation)
        .options(defer(JobEvaluation.signals), defer(JobEvaluation.raw_typesafe_response)),
    )).all()
    all_rows = [_row(j) for j in jobs]
    wanted = set(state or ["ready"])
    rows = [r for r in all_rows if r["status_kind"] in wanted]
    ready = [r for r in all_rows if r["status_kind"] == "ready"]

    stats = {"total": len(ready), "evaluated": sum(r["status"] is not None for r in ready),
             "drafts": sum(r["status_kind"] == "draft" for r in all_rows)}
    for key, value in (("strong", "STRONG_MATCH"), ("good", "GOOD_MATCH"), ("review", "REVIEW"), ("low", "LOW_MATCH"),
                       ("blocked", "BLOCKED")):
        stats[key] = sum(r["status"] == value for r in ready)
    stats["pending"] = sum(r["evaluation_status"] in ("pending", "running") for r in ready)
    stats["failed"] = sum(r["evaluation_status"] == "failed" for r in ready)

    def within(value, allowed):
        return allowed is None or value in allowed

    def keep(r: dict) -> bool:
        clearance_p = r["security_clearance_required"]
        return all([
            not q or any(q.lower() in (r[k] or "").lower() for k in ("company", "title", "location")),
            min_score is None or (r["overall_score"] is not None and r["overall_score"] >= min_score),
            within(r["status"], status),
            not company or r["company"].lower() == company.lower(),
            within(r["role_family"], role_family), within(r["seniority"], seniority), within(r["domain"], domain),
            within(r["work_arrangement"], work_arrangement), within(r["kmp_requirement"], kmp_requirement),
            min_android_relevance is None or (r["android_relevance"] is not None and r["android_relevance"] >= min_android_relevance),
            clearance is None or (clearance_p is not None and {
                "required": clearance_p >= 0.8, "possible": 0.5 <= clearance_p < 0.8, "not_required": clearance_p < 0.5}[clearance]),
            within(r["work_authorization_signal"], work_authorization_signal), within(r["source"], source),
            within(r["evaluation_status"], evaluation_status),
            needs_review is None or r["needs_review"] is needs_review,
        ])

    rows = [r for r in rows if keep(r)]
    field = {"score": "overall_score", "confidence": "aggregate_confidence"}.get(sort, sort)
    present = sorted((r for r in rows if r[field] is not None),
                     key=lambda r: r[field].lower() if isinstance(r[field], str) else r[field], reverse=order == "desc")
    rows = present + [r for r in rows if r[field] is None]  # unscored jobs always last
    return {"rows": rows[offset:offset + limit], "total_filtered": len(rows), "stats": stats}


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
def get_job(job_id: UUID, session: SessionDep):
    row = _job(session, job_id)
    fit = row.current_fit_result
    latest = row.evaluations[-1] if row.evaluations else None
    return {"job": job_out(row), "fit_result": fit_out(fit) if fit else None,
            "evaluation": evaluation_out(fit.evaluation, signals=True, fits=False) if fit else None,
            "latest_evaluation": evaluation_out(latest, fits=False) if latest else None}


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: UUID, session: SessionDep):
    row = _job(session, job_id)
    row.current_fit_result_id = None
    session.flush()
    session.delete(row)
    session.commit()


def _enqueue(session, worker, job_id: UUID, profile_id: UUID) -> UUID:
    evaluation_id = create_evaluation(session, job_id, profile_id).id
    session.commit()
    worker.enqueue(evaluation_id)
    return evaluation_id


@router.post("/jobs/{job_id}/evaluate", status_code=202, response_model=EnqueuedOut)
def evaluate_job(job_id: UUID, session: SessionDep, worker: WorkerDep):
    row = _job(session, job_id)
    if row.status == "draft":
        raise HTTPException(409, DRAFT_MESSAGE)
    profile = require_profile(session)
    return {"evaluation_id": _enqueue(session, worker, job_id, profile.id), "status": "pending"}


class ReevaluateIn(BaseModel):
    job_ids: list[UUID] | None = None


@router.post("/jobs/reevaluate", status_code=202, response_model=EvaluationIdsOut)
def reevaluate(body: ReevaluateIn, session: SessionDep, worker: WorkerDep):
    profile = require_profile(session)
    if body.job_ids is None:
        ids = session.scalars(select(JobPostingRow.id).where(JobPostingRow.status == "ready")).all()
    else:
        ids = body.job_ids
        for job_id in ids:
            if _job(session, job_id).status == "draft":
                raise HTTPException(409, DRAFT_MESSAGE)
    return {"evaluation_ids": [_enqueue(session, worker, _job(session, i).id, profile.id) for i in ids]}


@router.post("/evaluate", status_code=202, response_model=EvaluatePostingOut)
def evaluate_posting(body: JobPostingIn, session: SessionDep, worker: WorkerDep, response: Response):
    """Create (or find) a job and evaluate it — the paste flow and future browser-extension entry point."""
    profile = require_profile(session)
    row, created = get_or_create_job(session, body)
    if row.status == "draft":
        raise HTTPException(409, DRAFT_MESSAGE)
    reusable = next((e for e in reversed(row.evaluations)
                     if e.status == "succeeded" and e.profile_version.semantic_hash == profile.semantic_hash
                     and e.evaluator_version == EVALUATOR_VERSION and e.model == worker.evaluator.model), None)
    if reusable:
        session.commit()
        response.status_code = 200
        return {"job": job_out(row), "evaluation_id": reusable.id, "created": created, "reused": True}
    return {"job": job_out(row), "evaluation_id": _enqueue(session, worker, row.id, profile.id), "created": created,
            "reused": False}
