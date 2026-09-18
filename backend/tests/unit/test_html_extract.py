import pathlib

import httpx2
import pytest

from app.ingest.fetch import fetch_posting
from app.ingest.fetch.base import FetchError
from app.ingest.fetch.html import html_to_text
from app.ingest.fetch.url_guard import HttpFetcher

FIXTURES = pathlib.Path(__file__).parents[1] / "fixtures" / "http"


def page(html: str):
    def handler(request):
        if str(request.url).endswith("/robots.txt"):
            return httpx2.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx2.Response(200, text=html, headers={"content-type": "text/html; charset=utf-8"})
    return HttpFetcher(transport=httpx2.MockTransport(handler))


async def test_json_ld_page_gives_structured_fields(public_dns):
    posting = await fetch_posting("https://careers.acme.com/jobs/42", page((FIXTURES / "jsonld_page.html").read_text()))
    assert posting.provider == "html" and posting.confidence == "extracted"
    assert posting.company == "Acme Robotics" and posting.title == "Senior Android Engineer"
    assert posting.location == "Berlin, DE"
    assert "5+ years of Android development" in posting.description and "<" not in posting.description
    assert posting.warnings == []


async def test_plain_page_drops_nav_script_and_cookie_banner(public_dns):
    posting = await fetch_posting("https://careers.nimbus.dev/jobs/7", page((FIXTURES / "plain_page.html").read_text()))
    assert "4+ years building Android apps in Kotlin" in posting.description
    for noise in ("Accept cookies", "window.analytics", "All jobs", "Nimbus Ltd"):
        assert noise not in posting.description
    assert posting.title == "Mobile Engineer"
    assert any("company" in w for w in posting.warnings)


async def test_page_without_a_description_is_refused(public_dns):
    with pytest.raises(FetchError) as err:
        await fetch_posting("https://careers.acme.com/jobs/1", page("<html><body><div>Loading…</div></body></html>"))
    assert err.value.code == "no_content" and "paste" in err.value.message.lower()


def test_html_to_text_keeps_line_structure():
    assert html_to_text("<p>One</p><p>Two</p>") == "One\nTwo"
    assert html_to_text("plain text") == "plain text"
    assert html_to_text("") == ""
