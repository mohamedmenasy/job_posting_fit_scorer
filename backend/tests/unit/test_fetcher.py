import httpx2
import pytest

from app.ingest.fetch.base import FetchError
from app.ingest.fetch.url_guard import HttpFetcher

ROBOTS_ALLOW = "User-agent: *\nAllow: /\n"


def transport(handler):
    return httpx2.MockTransport(handler)


def routes(pages: dict[str, httpx2.Response], robots: str = ROBOTS_ALLOW):
    def handler(request):
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx2.Response(200, text=robots)
        if url in pages:
            return pages[url]
        return httpx2.Response(404)
    return transport(handler)


async def test_fetches_allowed_page(public_dns):
    fetcher = HttpFetcher(transport=routes({"https://a.test/j": httpx2.Response(200, text="hello")}))
    response = await fetcher.get("https://a.test/j")
    assert response.text == "hello"
    assert response.request.headers["user-agent"].startswith("JobFitAI/")
    assert "cookie" not in response.request.headers and "authorization" not in response.request.headers


async def test_redirects_are_walked_and_revalidated(public_dns):
    pages = {"https://a.test/j": httpx2.Response(302, headers={"location": "https://10.0.0.5/j"})}
    with pytest.raises(FetchError) as err:
        await HttpFetcher(transport=routes(pages)).get("https://a.test/j")
    assert err.value.code == "private_address"


async def test_https_to_http_downgrade_refused(public_dns):
    pages = {"https://a.test/j": httpx2.Response(302, headers={"location": "http://b.test/j"})}
    with pytest.raises(FetchError) as err:
        await HttpFetcher(transport=routes(pages)).get("https://a.test/j")
    assert err.value.code == "unsupported_scheme"


async def test_too_many_redirects(public_dns):
    pages = {f"https://a.test/{i}": httpx2.Response(302, headers={"location": f"https://a.test/{i + 1}"})
             for i in range(6)}
    with pytest.raises(FetchError) as err:
        await HttpFetcher(transport=routes(pages)).get("https://a.test/0")
    assert err.value.code == "too_many_redirects"


async def test_body_size_cap(public_dns):
    pages = {"https://a.test/j": httpx2.Response(200, content=b"x" * (3 * 1024 * 1024))}
    with pytest.raises(FetchError) as err:
        await HttpFetcher(transport=routes(pages)).get("https://a.test/j")
    assert err.value.code == "too_large"


async def test_unsupported_content_type(public_dns):
    pages = {"https://a.test/j": httpx2.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})}
    with pytest.raises(FetchError) as err:
        await HttpFetcher(transport=routes(pages)).get("https://a.test/j")
    assert err.value.code == "no_content"


async def test_not_found_and_upstream_error(public_dns):
    fetcher = HttpFetcher(transport=routes({}))
    with pytest.raises(FetchError) as err:
        await fetcher.get("https://a.test/missing")
    assert err.value.code == "not_found"
    pages = {"https://a.test/j": httpx2.Response(500)}
    with pytest.raises(FetchError) as err:
        await HttpFetcher(transport=routes(pages)).get("https://a.test/j")
    assert err.value.code == "upstream_error"


async def test_timeout_is_reported(public_dns):
    def handler(request):
        if str(request.url).endswith("/robots.txt"):
            return httpx2.Response(200, text=ROBOTS_ALLOW)
        raise httpx2.ConnectTimeout("too slow", request=request)
    with pytest.raises(FetchError) as err:
        await HttpFetcher(transport=transport(handler)).get("https://a.test/j")
    assert err.value.code == "timeout"
