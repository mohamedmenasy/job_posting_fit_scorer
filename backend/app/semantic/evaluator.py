from typing import Protocol

from app.domain import CandidateProfile, JobPosting, SemanticJobEvaluation


class JobSemanticEvaluator(Protocol):
    model: str

    async def evaluate(self, profile: CandidateProfile, job: JobPosting) -> SemanticJobEvaluation: ...


class SemanticEvaluationError(Exception):
    """Sanitized evaluator failure: never carries request bodies, resume text, or API keys."""

    def __init__(self, message: str, status: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.request_id = request_id

    def sanitized(self) -> str:
        extra = ", ".join(f"{k}={v}" for k, v in (("status", self.status), ("request_id", self.request_id)) if v)
        return f"{self.message} ({extra})" if extra else self.message
