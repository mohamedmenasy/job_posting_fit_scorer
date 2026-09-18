"""Provider registry: the first provider that matches a URL handles it (import §4.1)."""

from app.ingest.fetch.ats import AshbyProvider, GreenhouseProvider, LeverProvider
from app.ingest.fetch.base import FetchedPosting, FetchError, JobContentProvider
from app.ingest.fetch.blocked import BlockedSiteProvider
from app.ingest.fetch.html import HtmlProvider
from app.ingest.fetch.url_guard import HttpFetcher, validate_url

PROVIDERS: list[JobContentProvider] = [
    BlockedSiteProvider(), GreenhouseProvider(), LeverProvider(), AshbyProvider(), HtmlProvider(),
]

__all__ = ["PROVIDERS", "FetchError", "FetchedPosting", "HttpFetcher", "fetch_posting"]


async def fetch_posting(url: str, fetcher: HttpFetcher | None = None) -> FetchedPosting:
    parsed = validate_url(url)
    provider = next(p for p in PROVIDERS if p.matches(parsed))
    owned = fetcher is None
    fetcher = fetcher or HttpFetcher()
    try:
        return await provider.fetch(url, fetcher)
    finally:
        if owned:
            await fetcher.aclose()
