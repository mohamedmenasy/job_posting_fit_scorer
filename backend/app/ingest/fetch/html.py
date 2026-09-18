"""Generic extraction for career pages with no public API (import §4.3).

Text is kept verbatim so evidence lines stay quotable; fields that cannot be determined stay empty
rather than being guessed.
"""

import json
import re
from urllib.parse import ParseResult, urlparse

from selectolax.parser import HTMLParser

from app.ingest.fetch.base import FetchedPosting, FetchError

DROP_TAGS = ("script", "style", "nav", "header", "footer", "form", "noscript", "svg", "aside", "iframe")
NOISE = re.compile(r"cookie|consent|banner|newsletter|subscribe|related-jobs|breadcrumb", re.I)
BLOCK_TAGS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}


def html_to_text(html: str) -> str:
    """Strip tags, keep block structure as newlines, collapse runs of whitespace."""
    if not html or "<" not in html:
        return " ".join(html.split()) if html else ""
    tree = HTMLParser(html)
    for tag in DROP_TAGS:
        for node in tree.css(tag):
            node.decompose()
    for node in tree.css("*"):
        if node.tag in BLOCK_TAGS:
            node.insert_after("\n")
    text = tree.text(separator=" ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _json_ld_posting(tree: HTMLParser) -> dict | None:
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text())
        except (json.JSONDecodeError, ValueError):
            continue
        for candidate in data if isinstance(data, list) else [data]:
            if not isinstance(candidate, dict):
                continue
            graph = candidate.get("@graph") if isinstance(candidate.get("@graph"), list) else [candidate]
            for entry in graph:
                if isinstance(entry, dict) and entry.get("@type") == "JobPosting":
                    return entry
    return None


def _location(posting: dict) -> str | None:
    location = posting.get("jobLocation")
    if isinstance(location, list):
        location = location[0] if location else None
    if isinstance(location, dict):
        address = location.get("address")
        if isinstance(address, dict):
            parts = [address.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
            return ", ".join(str(p) for p in parts if isinstance(p, str)) or None
    if posting.get("jobLocationType") == "TELECOMMUTE":
        return "Remote"
    return None


def _main_text(tree: HTMLParser) -> str:
    for selector in ("main", "article", '[role="main"]', "body"):
        node = tree.css_first(selector)
        if node is None:
            continue
        for child in node.css("*"):
            attributes = f"{child.attributes.get('class', '')} {child.attributes.get('id', '')}"
            if NOISE.search(attributes):
                child.decompose()
        text = html_to_text(node.html or "")
        if len(text) >= 200:
            return text
    return ""


class HtmlProvider:
    """Last resort: read the page itself."""

    name = "html"

    def matches(self, url: ParseResult) -> bool:
        return True

    async def fetch(self, url: str, fetcher) -> FetchedPosting:
        response = await fetcher.get(url)
        tree = HTMLParser(response.text)
        warnings: list[str] = []
        posting = _json_ld_posting(tree)
        company = title = location = None
        description = ""
        if posting:
            organization = posting.get("hiringOrganization")
            company = organization.get("name") if isinstance(organization, dict) else None
            title = posting.get("title")
            location = _location(posting)
            description = html_to_text(posting.get("description", ""))
        if not description:
            description = _main_text(tree)
            if posting:
                warnings.append("The page's job data had no description, so the page text was used")
        if not description:
            raise FetchError("no_content", "No job description could be read from that page — paste the text instead")
        if not title:
            heading = tree.css_first("h1")
            title = (heading.text(strip=True) if heading else None) or _title_tag(tree)
        missing = [name for name, value in (("company", company), ("title", title), ("location", location)) if not value]
        if missing:
            warnings.append(f"Could not read {', '.join(missing)} from the page — fill in by hand")
        return FetchedPosting(
            company=company, title=title, location=location, description=description,
            source="company_site" if not _is_aggregator(url) else "other", source_url=url,
            provider=self.name, confidence="extracted", warnings=warnings)


def _title_tag(tree: HTMLParser) -> str | None:
    node = tree.css_first("title")
    if node is None:
        return None
    text = node.text(strip=True)
    return re.split(r"\s+[|\-–]\s+", text)[0] or None


def _is_aggregator(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(part in host for part in ("jobs", "careers", "boards")) is False
