from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models import ProfileVersion
from app.pipeline.worker import EvaluationWorker
from app.repo import current_profile


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_worker(request: Request) -> EvaluationWorker:
    return request.app.state.worker


SessionDep = Annotated[Session, Depends(get_session)]
WorkerDep = Annotated[EvaluationWorker, Depends(get_worker)]


def require_profile(session: Session) -> ProfileVersion:
    profile = current_profile(session)
    if profile is None:
        raise HTTPException(409, "Create a profile before evaluating jobs")
    return profile
