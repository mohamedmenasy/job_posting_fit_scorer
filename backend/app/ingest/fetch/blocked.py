"""Sites that require a login. Refused by name — JobFit never works around a login or a CAPTCHA."""

from urllib.parse import ParseResult

from app.ingest.fetch.base import FetchError

BLOCKED = {
    "linkedin": ("linkedin.com",),
    "Indeed": ("indeed.com", "indeed.co.uk", "indeed.ca", "indeed.de", "indeed.fr", "indeed.nl", "indeed.es"),
    "Glassdoor": ("glassdoor.com", "glassdoor.co.uk", "glassdoor.ca"),
    "ZipRecruiter": ("ziprecruiter.com",),
}


def blocked_name(host: str) -> str | None:
    host = host.lower()
    for name, domains in BLOCKED.items():
        if any(host == d or host.endswith(f".{d}") for d in domains):
            return "LinkedIn" if name == "linkedin" else name
    return None


class BlockedSiteProvider:
    name = "blocked"

    def matches(self, url: ParseResult) -> bool:
        return blocked_name(url.hostname or "") is not None

    async def fetch(self, url: str, fetcher):
        from urllib.parse import urlparse
        site = blocked_name(urlparse(url).hostname or "") or "That site"
        raise FetchError("blocked_site", f"{site} requires a login, so JobFit cannot fetch this posting. "
                                         "Open it in your browser, copy the description, and use the Paste tab.")
