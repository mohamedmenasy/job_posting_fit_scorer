"""The ONLY module that imports typesafe_sdk (spec §6.6)."""

import asyncio
import logging
import time

import httpx2
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeAPIError, TypeSafeError

from app.domain import CandidateProfile, JobPosting, RequestMeta, SemanticJobEvaluation
from app.semantic.catalog import EVALUATOR_VERSION, Q, build_questions, catalog_hash, question_set_hash
from app.semantic.evaluator import SemanticEvaluationError
from app.semantic.lines import segment
from app.semantic.packer import estimate_tokens, pack
from app.semantic.parser import parse_answers
from app.semantic.state import build_fit_state, build_job_state

log = logging.getLogger("app.semantic")


class TypeSafeJobSemanticEvaluator:
    def __init__(self, api_key: str, model: str, budget: int, semaphore: asyncio.Semaphore,
                 transport: httpx2.AsyncBaseTransport | None = None):
        self._api_key = api_key
        self.model = model
        self._budget = budget
        self._semaphore = semaphore
        self._transport = transport

    async def evaluate(self, profile: CandidateProfile, job: JobPosting) -> SemanticJobEvaluation:
        lines = segment(job.description)
        states = {"job": build_job_state(job, lines), "fit": build_fit_state(job, lines, profile)}
        questions = build_questions(profile, lines)
        batches = [(kind, group) for kind in ("job", "fit")
                   for group in pack(states[kind], [q for q in questions if q.state == kind], self._budget)]
        try:
            async with AsyncTypeSafeClient(api_key=self._api_key, model=self.model, timeout=30.0,
                                           retry=RetryPolicy(max_retries=3, timeout=120.0),
                                           transport=self._transport) as client:
                results = await asyncio.gather(*(self._send(client, kind, states[kind], group)
                                                 for kind, group in batches))
        except TypeSafeAPIError as e:
            raise SemanticEvaluationError(type(e).__name__, e.status, e.request_id) from None
        except TypeSafeError as e:
            raise SemanticEvaluationError(type(e).__name__) from None
        answers = {qid: ans for meta in results for qid, ans in meta.raw_response["answers"].items()}
        return parse_answers(answers, questions, profile, lines, model=results[0].raw_response["model"],
                             requests=results, question_set_hash=question_set_hash(questions))

    async def _send(self, client: AsyncTypeSafeClient, kind: str, state: dict, group: list[Q]) -> RequestMeta:
        async with self._semaphore:
            start = time.monotonic()
            response = await client.system_one(state, {q.id: q.body for q in group}, model=self.model)
            latency_ms = int((time.monotonic() - start) * 1000)
        try:
            request_id = response.request_id
        except TypeSafeError:
            request_id = None
        meta = RequestMeta(request_id=request_id, state_kind=kind, question_count=len(group),
                           input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                           latency_ms=latency_ms, raw_response=response.raw_http_response.json())
        log.info("typesafe.request", extra={"fields": {
            "request_id": request_id, "state_kind": kind, "question_count": len(group),
            "estimated_tokens": estimate_tokens(state, group), "input_tokens": meta.input_tokens,
            "output_tokens": meta.output_tokens, "latency_ms": latency_ms,
            "evaluator_version": EVALUATOR_VERSION, "catalog_hash": catalog_hash()}})
        return meta
