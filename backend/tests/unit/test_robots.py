import httpx2
import pytest

from app.ingest.fetch.base import FetchError
from app.ingest.fetch.url_guard import HttpFetcher

PAGE = httpx2.Response(200, text="ok")


def transport_with_robots(body: str | None, status: int = 200, count=None):
    def handler(request):
        if str(request.url).endswith("/robots.txt"):
            if count is not None:
                count.append(str(request.url))
            return httpx2.Response(status, text=body or "")
        return PAGE
    return httpx2.MockTransport(handler)


async def test_disallowed_path_is_refused(public_dns):
    fetcher = HttpFetcher(transport=transport_with_robots("User-agent: *\nDisallow: /jobs\n"))
    with pytest.raises(FetchError) as err:
        await fetcher.get("https://c.test/jobs/1")
    assert err.value.code == "robots_disallow"


async def test_allowed_path_passes(public_dns):
    fetcher = HttpFetcher(transport=transport_with_robots("User-agent: *\nDisallow: /admin\n"))
    assert (await fetcher.get("https://c.test/jobs/1")).text == "ok"


@pytest.mark.parametrize("body,status", [(None, 404), ("<html>not robots</html>", 200), (None, 500)])
async def test_missing_or_unreadable_robots_allows(public_dns, body, status):
    fetcher = HttpFetcher(transport=transport_with_robots(body, status))
    assert (await fetcher.get("https://c.test/jobs/1")).status_code == 200


async def test_robots_is_fetched_once_per_host(public_dns):
    seen: list[str] = []
    fetcher = HttpFetcher(transport=transport_with_robots("User-agent: *\nAllow: /\n", count=seen))
    await fetcher.get("https://c.test/jobs/1")
    await fetcher.get("https://c.test/jobs/2")
    assert len(seen) == 1
