"""In-process evaluation queue (spec §10). Run a single uvicorn process: the queue lives in memory,
durable status lives in the DB, and unfinished evaluations are re-queued on startup."""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain import SemanticJobEvaluation
from app.models import FitResult, JobEvaluation, JobPostingRow, ProfileVersion, ScoringConfigRow
from app.repo import active_config, current_profile, headline_columns, to_domain_job, to_domain_profile
from app.scoring.config import ScoringConfig
from app.scoring.scorer import JobFitScorer
from app.semantic.evaluator import JobSemanticEvaluator, SemanticEvaluationError

log = logging.getLogger("app.pipeline")


def create_evaluation(session: Session, job_id: uuid.UUID, profile_version_id: uuid.UUID) -> JobEvaluation:
    evaluation = JobEvaluation(job_id=job_id, profile_version_id=profile_version_id, status="pending")
    session.add(evaluation)
    session.flush()
    return evaluation


def stored_semantics(evaluation: JobEvaluation) -> SemanticJobEvaluation:
    return SemanticJobEvaluation.model_validate({**evaluation.signals, "requests": evaluation.raw_typesafe_response or []})


def score_evaluation(session: Session, evaluation: JobEvaluation, profile_row: ProfileVersion,
                     config_row: ScoringConfigRow) -> FitResult:
    result = JobFitScorer().calculate(
        stored_semantics(evaluation), to_domain_profile(profile_row), ScoringConfig.model_validate(config_row.config),
        stale_semantics=evaluation.profile_version.semantic_hash != profile_row.semantic_hash)
    fit = FitResult(
        evaluation_id=evaluation.id, profile_version_id=profile_row.id, scoring_config_id=config_row.id,
        overall_score=result.overall_score, aggregate_confidence=result.aggregate_confidence, status=result.status,
        needs_review=result.needs_review, stale_semantics=result.stale_semantics,
        details=result.model_dump(mode="json", exclude={"overall_score", "aggregate_confidence", "status",
                                                        "needs_review", "stale_semantics"}))
    session.add(fit)
    session.flush()
    evaluation.job.current_fit_result_id = fit.id
    return fit


def latest_succeeded(job: JobPostingRow) -> JobEvaluation | None:
    return next((e for e in reversed(job.evaluations) if e.status == "succeeded"), None)


def rescore_all(session: Session) -> int:
    """Re-score every job's latest succeeded evaluation with the current profile and active config. No API calls."""
    profile = current_profile(session)
    if profile is None:
        return 0
    config = active_config(session)
    count = 0
    for job in session.scalars(select(JobPostingRow)):
        if evaluation := latest_succeeded(job):
            score_evaluation(session, evaluation, profile, config)
            count += 1
    session.commit()
    return count


class EvaluationWorker:
    def __init__(self, session_factory: sessionmaker[Session], evaluator: JobSemanticEvaluator, workers: int):
        self._sf = session_factory
        self.evaluator = evaluator
        self._workers = workers
        self._queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._run()) for _ in range(self._workers)]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def enqueue(self, evaluation_id: uuid.UUID) -> None:
        self._queue.put_nowait(evaluation_id)
        log.info("evaluation.enqueued", extra={"fields": {"evaluation_id": evaluation_id}})

    def requeue_unfinished(self) -> None:
        with self._sf() as s:
            ids = s.scalars(select(JobEvaluation.id).where(JobEvaluation.status.in_(["pending", "running"]))
                            .order_by(JobEvaluation.created_at)).all()
        for evaluation_id in ids:
            self.enqueue(evaluation_id)

    async def _run(self) -> None:
        while True:
            evaluation_id = await self._queue.get()
            try:
                await self.evaluate_job(evaluation_id)
            except Exception:  # never let one evaluation kill the worker
                log.exception("evaluation.worker_error", extra={"fields": {"evaluation_id": evaluation_id}})
            finally:
                self._queue.task_done()

    async def evaluate_job(self, evaluation_id: uuid.UUID) -> None:
        # ponytail: sync SQLite calls inside the event loop; each is sub-millisecond locally
        with self._sf() as s:
            evaluation = s.get(JobEvaluation, evaluation_id)
            if evaluation is None or evaluation.status in ("succeeded", "failed"):
                return
            evaluation.status, evaluation.started_at = "running", datetime.now(UTC)
            s.commit()
            job, profile = to_domain_job(evaluation.job), to_domain_profile(evaluation.profile_version)
            fields = {"evaluation_id": evaluation_id, "job_id": job.id, "model": self.evaluator.model}
        log.info("evaluation.started", extra={"fields": fields})
        start = time.monotonic()
        try:
            semantic = await self.evaluator.evaluate(profile, job)
            with self._sf() as s:
                evaluation = s.get(JobEvaluation, evaluation_id)
                requests = [r.model_dump(mode="json") for r in semantic.requests]
                tokens_in = [r.input_tokens for r in semantic.requests if r.input_tokens is not None]
                tokens_out = [r.output_tokens for r in semantic.requests if r.output_tokens is not None]
                for key, value in {
                    **headline_columns(semantic),
                    "signals": semantic.model_dump(mode="json", exclude={"requests"}), "raw_typesafe_response": requests,
                    "evaluator_version": semantic.evaluator_version, "catalog_hash": semantic.catalog_hash,
                    "question_set_hash": semantic.question_set_hash, "model": semantic.model,
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "input_tokens": sum(tokens_in) if tokens_in else None,
                    "output_tokens": sum(tokens_out) if tokens_out else None,
                }.items():
                    setattr(evaluation, key, value)
                fit = score_evaluation(s, evaluation, current_profile(s), active_config(s))
                evaluation.status, evaluation.finished_at = "succeeded", datetime.now(UTC)
                s.commit()
                log.info("evaluation.completed", extra={"fields": {
                    **fields, "evaluator_version": semantic.evaluator_version, "catalog_hash": semantic.catalog_hash,
                    "requests": [{k: v for k, v in r.items() if k != "raw_response"} for r in requests],
                    "latency_ms": evaluation.latency_ms, "overall_score": fit.overall_score,
                    "aggregate_confidence": fit.aggregate_confidence, "status": fit.status}})
        except Exception as e:  # sanitized: class name + TypeSafe status/request id only
            error = e.sanitized() if isinstance(e, SemanticEvaluationError) else f"{type(e).__name__}: {str(e)[:200]}"
            if not isinstance(e, SemanticEvaluationError) and type(e).__module__.startswith(("pydantic", "sqlalchemy")):
                error = type(e).__name__
            with self._sf() as s:
                evaluation = s.get(JobEvaluation, evaluation_id)
                evaluation.status, evaluation.error, evaluation.finished_at = "failed", error, datetime.now(UTC)
                s.commit()
            log.warning("evaluation.failed", extra={"fields": {**fields, "error": error}})
