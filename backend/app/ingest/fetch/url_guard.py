"""The only component that makes outbound requests (import §6).

Every hop is validated: http(s) only, public addresses only, manual redirects, robots.txt honored,
hard timeout, hard size cap, no cookies or credentials.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import ParseResult, urljoin, urlparse

import httpx2

from app.ingest.fetch.base import FetchError
from app.ingest.fetch.robots import RobotsCache

USER_AGENT = "JobFitAI/0.1 (+local personal job tracker; respects robots.txt)"
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443, 8080, 8443)
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 10.0
MAX_BYTES = 2 * 1024 * 1024
ALLOWED_CONTENT = ("text/html", "application/json", "text/plain", "application/ld+json", "text/xhtml+xml")


def resolve_addresses(host: str) -> list[str]:
    try:
        return [info[4][0] for info in socket.getaddrinfo(host, None)]
    except socket.gaierror:
        return []


def validate_url(url: str) -> ParseResult:
    try:
        parsed = urlparse(url)
    except ValueError:
        raise FetchError("unsupported_scheme", "That does not look like a URL") from None
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise FetchError("unsupported_scheme", "Only http and https URLs can be fetched")
    if parsed.username or parsed.password:
        raise FetchError("unsupported_scheme", "URLs with credentials are not fetched")
    try:
        port = parsed.port
    except ValueError:
        raise FetchError("unsupported_scheme", "That URL has an invalid port") from None
    if port is not None and port not in ALLOWED_PORTS:
        raise FetchError("unsupported_scheme", f"Port {port} is not allowed")
    host = parsed.hostname.strip("[]")
    try:  # an IP literal is checked directly; it must never depend on a resolver
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = resolve_addresses(host)
    if not addresses:
        raise FetchError("private_address", f"{host} does not resolve to a public address")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise FetchError("private_address", f"{host} is not a public address")
    return parsed


class HttpFetcher:
    """Fetches public pages politely. One in-flight request per host."""

    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None):
        self._client = httpx2.AsyncClient(
            transport=transport, timeout=TIMEOUT_SECONDS, follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
        self._robots = RobotsCache()
        self._locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    def _lock(self, host: str) -> asyncio.Lock:
        return self._locks.setdefault(host, asyncio.Lock())

    async def _robots_allows(self, parsed: ParseResult) -> bool:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots.get(origin)
        if parser == "miss":
            parser = None
            try:
                response = await self._client.get(f"{origin}/robots.txt")
                if response.status_code == 200 and "<html" not in response.text[:200].lower():
                    parser = RobotsCache.parse(response.text)
            except httpx2.HTTPError:
                parser = None
            self._robots.put(origin, parser)
        return True if parser is None else parser.can_fetch(USER_AGENT, parsed.geturl())

    async def get(self, url: str, accept: str = "text/html,application/json") -> httpx2.Response:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            parsed = validate_url(current)
            async with self._lock(parsed.hostname or ""):
                if not await self._robots_allows(parsed):
                    raise FetchError("robots_disallow", "This site's robots.txt asks automated tools not to fetch that page")
                response = await self._send(current, accept)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchError("upstream_error", "The site redirected without a destination")
                target = urljoin(current, location)
                if urlparse(current).scheme == "https" and urlparse(target).scheme == "http":
                    raise FetchError("unsupported_scheme", "That page redirects to an insecure address")
                current = target
                continue
            return self._checked(response)
        raise FetchError("too_many_redirects", "That URL redirects too many times")

    async def _send(self, url: str, accept: str) -> httpx2.Response:
        try:
            request = self._client.build_request("GET", url, headers={"Accept": accept})
            response = await self._client.send(request, stream=True)
        except httpx2.TimeoutException:
            raise FetchError("timeout", "The site took too long to respond") from None
        except httpx2.HTTPError:
            raise FetchError("upstream_error", "Could not reach that site") from None
        try:
            length = response.headers.get("content-length")
            if length and int(length) > MAX_BYTES:
                raise FetchError("too_large", "That page is too large to import")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise FetchError("too_large", "That page is too large to import")
        finally:
            await response.aclose()
        return httpx2.Response(response.status_code, headers=response.headers, content=bytes(body),
                               request=response.request)

    @staticmethod
    def _checked(response: httpx2.Response) -> httpx2.Response:
        if response.status_code == 404:
            raise FetchError("not_found", "That posting could not be found — it may have been taken down")
        if response.status_code >= 400:
            raise FetchError("upstream_error", f"The site returned {response.status_code}")
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type and not any(content_type.startswith(allowed) for allowed in ALLOWED_CONTENT):
            raise FetchError("no_content", f"That URL returned {content_type}, not a job posting page")
        return response
