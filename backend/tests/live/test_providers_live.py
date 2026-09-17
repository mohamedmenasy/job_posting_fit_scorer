"""Opt-in network check that real job boards still return the shapes our providers expect.

Run with: cd backend && uv run pytest -m live_http
Recorded copies of these responses live in tests/fixtures/http (see SOURCES.md).
"""

import pytest

from app.ingest.fetch import fetch_posting

pytestmark = pytest.mark.live_http


async def test_greenhouse_posting_is_readable():
    from app.ingest.fetch import HttpFetcher
    fetcher = HttpFetcher()
    try:  # job ids change constantly, so take whatever is listed today
        board = (await fetcher.get("https://boards-api.greenhouse.io/v1/boards/stripe/jobs",
                                   accept="application/json")).json()
        posting = await fetch_posting(f"https://boards.greenhouse.io/stripe/jobs/{board['jobs'][0]['id']}", fetcher)
    finally:
        await fetcher.aclose()
    assert posting.provider == "greenhouse" and len(posting.description) > 200 and posting.title


async def test_lever_posting_is_readable():
    from app.ingest.fetch import HttpFetcher
    fetcher = HttpFetcher()
    try:
        listing = (await fetcher.get("https://api.lever.co/v0/postings/leverdemo?mode=json&limit=1",
                                     accept="application/json")).json()
        posting = await fetch_posting(f"https://jobs.lever.co/leverdemo/{listing[0]['id']}", fetcher)
    finally:
        await fetcher.aclose()
    assert posting.provider == "lever" and posting.description
