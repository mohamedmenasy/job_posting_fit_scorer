from fastapi import APIRouter
from sqlalchemy import func, select, update

from app.api.deps import SessionDep
from app.api.schemas import RescoreOut, ScoringSettingsOut
from app.models import ScoringConfigRow
from app.pipeline.worker import rescore_all
from app.repo import active_config
from app.scoring.config import ScoringConfig

router = APIRouter(tags=["settings"])


@router.get("/settings/scoring", response_model=ScoringSettingsOut)
def get_scoring(session: SessionDep):
    row = active_config(session)
    return {"version": row.version, "config": row.config, "defaults": ScoringConfig().model_dump(mode="json")}


@router.put("/settings/scoring", response_model=RescoreOut)
def put_scoring(body: ScoringConfig, session: SessionDep):
    version = (session.scalar(select(func.max(ScoringConfigRow.version))) or 0) + 1
    session.execute(update(ScoringConfigRow).values(is_active=False))
    session.add(ScoringConfigRow(version=version, config=body.model_dump(mode="json"), is_active=True))
    session.commit()
    return {"version": version, "rescored": rescore_all(session)}
