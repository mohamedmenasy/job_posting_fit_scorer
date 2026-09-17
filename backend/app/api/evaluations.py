from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import SessionDep
from app.api.schemas import EvaluationDetailOut, EvaluationOut, RequestRebuildOut
from app.api.serializers import evaluation_out
from app.models import JobEvaluation
from app.repo import to_domain_job, to_domain_profile
from app.semantic.catalog import build_questions, question_set_hash
from app.semantic.lines import segment
from app.semantic.state import build_fit_state, build_job_state

router = APIRouter(tags=["evaluations"])


def _get(session, evaluation_id: UUID) -> JobEvaluation:
    row = session.get(JobEvaluation, evaluation_id)
    if row is None:
        raise HTTPException(404, "Evaluation not found")
    return row


@router.get("/evaluations", response_model=list[EvaluationOut])
def list_evaluations(job_id: UUID, session: SessionDep):
    rows = session.scalars(select(JobEvaluation).where(JobEvaluation.job_id == job_id).order_by(JobEvaluation.created_at))
    return [evaluation_out(r) for r in rows]


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationDetailOut)
def get_evaluation(evaluation_id: UUID, session: SessionDep):
    return evaluation_out(_get(session, evaluation_id), signals=True, raw=True)


@router.get("/evaluations/{evaluation_id}/request", response_model=RequestRebuildOut)
def rebuild_request(evaluation_id: UUID, session: SessionDep):
    """Debug: rebuild the exact states and questions from stored inputs and current code (spec §6.7)."""
    row = _get(session, evaluation_id)
    job, profile = to_domain_job(row.job), to_domain_profile(row.profile_version)
    lines = segment(job.description)
    questions = build_questions(profile, lines)
    digest = question_set_hash(questions)
    return {"states": {"job": build_job_state(job, lines), "fit": build_fit_state(job, lines, profile)},
            "questions": [{"id": q.id, "state": q.state, "body": q.body} for q in questions],
            "question_set_hash": digest, "hash_matches": digest == row.question_set_hash}
