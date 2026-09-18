"""Shared types for posting fetchers (import §4.1)."""

from typing import Literal, Protocol
from urllib.parse import ParseResult

from pydantic import BaseModel

from app.domain import JobSource

FetchErrorCode = Literal[
    "blocked_site", "robots_disallow", "unsupported_scheme", "private_address",
    "too_many_redirects", "not_found", "too_large", "timeout", "no_content", "upstream_error",
]

# Errors the user caused or can act on, mapped to HTTP status codes by the API (import §7).
ERROR_STATUS: dict[str, int] = {
    "unsupported_scheme": 400, "private_address": 400, "too_many_redirects": 400,
    "blocked_site": 403, "robots_disallow": 403,
    "not_found": 404, "no_content": 422, "too_large": 413, "upstream_error": 502, "timeout": 504,
}


class FetchError(Exception):
    def __init__(self, code: FetchErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class FetchedPosting(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    description: str = ""
    salary_text: str | None = None
    source: JobSource = "other"
    source_url: str
    provider: str
    confidence: Literal["structured", "extracted"]
    warnings: list[str] = []


class JobContentProvider(Protocol):
    name: str

    def matches(self, url: ParseResult) -> bool: ...

    async def fetch(self, url: str, fetcher) -> FetchedPosting: ...
