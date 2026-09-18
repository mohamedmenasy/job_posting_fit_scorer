"""Providers for applicant tracking systems with public JSON APIs (import §4.2).

Response shapes are pinned by recorded responses in tests/fixtures/http (see SOURCES.md).
Anything unexpected raises upstream_error rather than producing a half-parsed job.
"""

import html as html_module
import json
import re
from urllib.parse import ParseResult

from app.ingest.fetch.base import FetchedPosting, FetchError
from app.ingest.fetch.html import html_to_text

GREENHOUSE_URL = re.compile(r"^/(?:embed/job_app\?for=)?(?P<board>[^/]+)/jobs/(?P<id>\d+)")
LEVER_URL = re.compile(r"^/(?P<org>[^/]+)/(?P<id>[0-9a-f-]{16,})")
ASHBY_URL = re.compile(r"^/(?P<org>[^/]+)/(?P<id>[0-9a-f-]{16,})")


def _slug_company(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _require(value, field: str, provider: str):
    if not value:
        raise FetchError("upstream_error", f"{provider} returned no {field} for that posting")
    return value


class GreenhouseProvider:
    name = "greenhouse"

    def matches(self, url: ParseResult) -> bool:
        return url.hostname in ("boards.greenhouse.io", "job-boards.greenhouse.io", "www.greenhouse.io") \
            and bool(GREENHOUSE_URL.match(url.path))

    async def fetch(self, url: str, fetcher) -> FetchedPosting:
        parsed = GREENHOUSE_URL.match(_path(url))
        assert parsed  # matches() ran first
        api = f"https://boards-api.greenhouse.io/v1/boards/{parsed['board']}/jobs/{parsed['id']}"
        data = await _json(fetcher, api, self.name)
        # Greenhouse escapes the posting HTML, so it is unescaped once before tags are stripped.
        description = html_to_text(html_module.unescape(data.get("content", "")))
        return FetchedPosting(
            company=data.get("company_name") or _slug_company(parsed["board"]),
            title=_require(data.get("title"), "title", self.name),
            location=(data.get("location") or {}).get("name"),
            description=_require(description, "description", self.name),
            source="company_site", source_url=data.get("absolute_url") or url,
            provider=self.name, confidence="structured")


class LeverProvider:
    name = "lever"

    def matches(self, url: ParseResult) -> bool:
        return url.hostname in ("jobs.lever.co", "jobs.eu.lever.co") and bool(LEVER_URL.match(url.path))

    async def fetch(self, url: str, fetcher) -> FetchedPosting:
        parsed = LEVER_URL.match(_path(url))
        assert parsed
        api = f"https://api.lever.co/v0/postings/{parsed['org']}/{parsed['id']}?mode=json"
        data = await _json(fetcher, api, self.name)
        categories = data.get("categories") or {}
        description = html_to_text(data.get("description", "")) or data.get("descriptionPlain", "")
        body = html_to_text(data.get("descriptionBody", "")) or data.get("descriptionBodyPlain", "")
        return FetchedPosting(
            company=_slug_company(parsed["org"]),
            title=_require(data.get("text"), "title", self.name),
            location=categories.get("location"),
            description=_require("\n".join(part for part in (description, body) if part), "description", self.name),
            source="company_site", source_url=data.get("hostedUrl") or url,
            provider=self.name, confidence="structured",
            warnings=["Company name came from the job board address — check it"])


class AshbyProvider:
    name = "ashby"

    def matches(self, url: ParseResult) -> bool:
        return url.hostname in ("jobs.ashbyhq.com", "app.ashbyhq.com") and bool(ASHBY_URL.match(url.path))

    async def fetch(self, url: str, fetcher) -> FetchedPosting:
        parsed = ASHBY_URL.match(_path(url))
        assert parsed
        api = f"https://api.ashbyhq.com/posting-api/job-board/{parsed['org']}?includeCompensation=true"
        data = await _json(fetcher, api, self.name)
        job = next((j for j in data.get("jobs", []) if j.get("id") == parsed["id"]), None)
        if job is None:
            raise FetchError("not_found", "That posting is no longer listed on this job board")
        compensation = (job.get("compensation") or {}).get("compensationTierSummary")
        return FetchedPosting(
            company=_slug_company(parsed["org"]),
            title=_require((job.get("title") or "").strip(), "title", self.name),
            location=job.get("location"),
            description=_require(html_to_text(job.get("descriptionHtml", "")) or job.get("descriptionPlain", ""),
                                 "description", self.name),
            salary_text=compensation,
            source="company_site", source_url=job.get("jobUrl") or url,
            provider=self.name, confidence="structured",
            warnings=["Company name came from the job board address — check it"])


def _path(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).path


async def _json(fetcher, api: str, provider: str) -> dict:
    response = await fetcher.get(api, accept="application/json")
    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        raise FetchError("upstream_error", f"{provider} returned something that is not a job posting") from None
    if not isinstance(data, dict):
        raise FetchError("upstream_error", f"{provider} returned an unexpected response")
    return data
