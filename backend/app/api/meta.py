from typing import get_args

from fastapi import APIRouter, Request

from app.domain import DEFAULT_TRACKED_SKILLS, ENUMS
from app.scoring.explain import YEARS, label
from app.semantic.catalog import EVALUATOR_VERSION

router = APIRouter(tags=["meta"])

LABELS = {"ios": "iOS", "ai_ml": "AI/ML", "kotlin_multiplatform": "Kotlin Multiplatform", "react_native": "React Native",
          "fullstack": "Full-stack", "director_plus": "Director+", "not_stated": "Not stated",
          "company_site": "Company site", "linkedin": "LinkedIn", **{k: f"{v} years" for k, (_, v) in YEARS.items()}}


@router.get("/meta")
def get_meta(request: Request):
    return {"enums": {name: [{"value": v, "label": LABELS.get(v) or label(v.lower())} for v in get_args(enum)]
                      for name, enum in ENUMS.items()},
            "default_tracked_skills": [s.model_dump() for s in DEFAULT_TRACKED_SKILLS],
            "evaluator_version": EVALUATOR_VERSION, "model": request.app.state.evaluator.model}


@router.get("/health")
def health(request: Request):
    settings = request.app.state.settings
    return {"status": "ok", "evaluator": settings.evaluator, "model": request.app.state.evaluator.model,
            "api_key_configured": bool(settings.typesafe_api_key and settings.typesafe_api_key.get_secret_value()),
            "queue_depth": request.app.state.worker.depth}
