import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import evaluations, jobs, meta, profile, settings as settings_api
from app.config import Settings
from app.db import make_engine, make_session_factory, run_migrations
from app.logging import configure_logging
from app.pipeline.worker import EvaluationWorker
from app.repo import ensure_default_config
from app.semantic.evaluator import JobSemanticEvaluator


def build_evaluator(settings: Settings) -> JobSemanticEvaluator:
    if settings.evaluator == "fake":
        from app.semantic.fake_evaluator import FakeJobSemanticEvaluator
        return FakeJobSemanticEvaluator()
    from app.semantic.typesafe_evaluator import TypeSafeJobSemanticEvaluator
    return TypeSafeJobSemanticEvaluator(settings.typesafe_api_key.get_secret_value(), settings.typesafe_model,
                                        settings.typesafe_token_budget,
                                        asyncio.Semaphore(settings.typesafe_max_concurrency))


def create_app(settings: Settings | None = None, evaluator: JobSemanticEvaluator | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings)
        if evaluator is None:
            settings.validate_for_startup()
        run_migrations(settings.database_url)
        engine = make_engine(settings.database_url)
        session_factory = make_session_factory(engine)
        with session_factory() as session:
            ensure_default_config(session)
        worker = EvaluationWorker(session_factory, evaluator or build_evaluator(settings), settings.evaluation_workers)
        app.state.settings, app.state.session_factory, app.state.worker = settings, session_factory, worker
        app.state.evaluator = worker.evaluator
        worker.start()
        worker.requeue_unfinished()
        yield
        await worker.stop()
        engine.dispose()

    app = FastAPI(title="JobFit AI", lifespan=lifespan)
    for module in (profile, jobs, evaluations, settings_api, meta):
        app.include_router(module.router, prefix="/api")
    return app
