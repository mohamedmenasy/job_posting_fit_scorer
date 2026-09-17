import json
import pathlib

import httpx2
import pytest

from app.ingest.fetch import fetch_posting
from app.ingest.fetch.base import FetchError
from app.ingest.fetch.url_guard import HttpFetcher

FIXTURES = pathlib.Path(__file__).parents[1] / "fixtures" / "http"
GREENHOUSE = json.loads((FIXTURES / "greenhouse_job.json").read_text())
LEVER = json.loads((FIXTURES / "lever_job.json").read_text())
ASHBY = json.loads((FIXTURES / "ashby_board.json").read_text())
ROBOTS = "User-agent: *\nAllow: /\n"


def recorded(payload, status=200):
    def handler(request):
        if str(request.url).endswith("/robots.txt"):
            return httpx2.Response(200, text=ROBOTS)
        if status != 200:
            return httpx2.Response(status, json={"error": "nope"})
        if isinstance(payload, str):
            return httpx2.Response(200, text=payload, headers={"content-type": "text/html"})
        return httpx2.Response(200, json=payload)
    return HttpFetcher(transport=httpx2.MockTransport(handler))


async def test_greenhouse_maps_recorded_response(public_dns):
    posting = await fetch_posting("https://boards.greenhouse.io/stripe/jobs/7038350", recorded(GREENHOUSE))
    assert posting.provider == "greenhouse" and posting.confidence == "structured"
    assert posting.company == GREENHOUSE["company_name"] and posting.title == GREENHOUSE["title"]
    assert posting.location == GREENHOUSE["location"]["name"]
    assert "<" not in posting.description and "&lt;" not in posting.description
    assert len(posting.description) > 200


async def test_lever_maps_recorded_response(public_dns):
    posting = await fetch_posting("https://jobs.lever.co/leverdemo/0f0f0f0f-0f0f-0f0f-0f0f-0f0f0f0f0f0f", recorded(LEVER))
    assert posting.provider == "lever" and posting.title == LEVER["text"]
    assert posting.location == LEVER["categories"]["location"]
    assert "<" not in posting.description and posting.description
    assert any("Company name" in w for w in posting.warnings)


async def test_ashby_matches_job_in_board(public_dns):
    job = ASHBY["jobs"][0]
    posting = await fetch_posting(f"https://jobs.ashbyhq.com/ramp/{job['id']}", recorded(ASHBY))
    assert posting.provider == "ashby" and posting.title == job["title"].strip()
    assert posting.location == job["location"] and posting.description
    assert posting.company == "Ramp"


async def test_ashby_unlisted_job_is_not_found(public_dns):
    with pytest.raises(FetchError) as err:
        await fetch_posting("https://jobs.ashbyhq.com/ramp/00000000-0000-0000-0000-000000000000", recorded(ASHBY))
    assert err.value.code == "not_found"


@pytest.mark.parametrize("payload", [{"jobs": []}, {"title": "", "content": ""}, {"unexpected": True}])
async def test_malformed_payloads_raise_upstream_error(public_dns, payload):
    with pytest.raises(FetchError) as err:
        await fetch_posting("https://boards.greenhouse.io/stripe/jobs/1", recorded(payload))
    assert err.value.code == "upstream_error"


async def test_api_error_is_reported(public_dns):
    with pytest.raises(FetchError) as err:
        await fetch_posting("https://jobs.lever.co/leverdemo/0f0f0f0f-0f0f-0f0f-0f0f-0f0f0f0f0f0f", recorded(None, 500))
    assert err.value.code == "upstream_error"


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/123456",
    "https://uk.indeed.com/viewjob?jk=abc",
    "https://www.glassdoor.com/job-listing/android-engineer",
    "https://www.ziprecruiter.com/c/Acme/Job/Android-Engineer",
])
async def test_blocked_sites_refuse_with_paste_hint(public_dns, url):
    def explode(request):
        raise AssertionError("a blocked site must never be requested")
    with pytest.raises(FetchError) as err:
        await fetch_posting(url, HttpFetcher(transport=httpx2.MockTransport(explode)))
    assert err.value.code == "blocked_site" and "Paste tab" in err.value.message


@pytest.mark.parametrize("url,provider", [
    ("https://boards.greenhouse.io/stripe/jobs/7038350", "greenhouse"),
    ("https://jobs.lever.co/leverdemo/0f0f0f0f-0f0f-0f0f-0f0f-0f0f0f0f0f0f", "lever"),
    ("https://jobs.ashbyhq.com/ramp/34413f8d-26bf-4bbc-8ade-eb309a0e2245", "ashby"),
    ("https://careers.acme.com/jobs/42", "html"),
    ("https://boards.greenhouse.io/stripe", "html"),
])
def test_registry_routes_urls(url, provider):
    from urllib.parse import urlparse

    from app.ingest.fetch import PROVIDERS
    assert next(p for p in PROVIDERS if p.matches(urlparse(url))).name == provider
