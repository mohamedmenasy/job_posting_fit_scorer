"""Record/replay transport for live TypeSafe tests. Cassettes are keyed by the exact request body (incl. model)."""

import json
from pathlib import Path

import httpx2

from app.domain import canonical_json, sha256


class CassetteMissing(Exception):
    pass


class CassetteTransport(httpx2.AsyncBaseTransport):
    def __init__(self, directory: Path, record: bool, inner: httpx2.AsyncBaseTransport | None = None):
        self.directory = directory
        self.record = record
        self.inner = inner

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        body = await request.aread()
        path = self.directory / f"{sha256(canonical_json(json.loads(body)))}.json"
        if not self.record:
            if not path.exists():
                raise CassetteMissing(path.name)
            data = json.loads(path.read_text())
            return httpx2.Response(data["status"], headers=data["headers"], json=data["body"], request=request)
        self.inner = self.inner or httpx2.AsyncHTTPTransport()
        response = await self.inner.handle_async_request(request)
        content = await response.aread()
        headers = {k: v for k, v in response.headers.items() if k.lower() == "x-typesafe-request-id"}
        self.directory.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": response.status_code, "headers": headers, "body": json.loads(content)},
                                   indent=1, sort_keys=True))
        return httpx2.Response(response.status_code, headers=headers, content=content, request=request)

    async def aclose(self) -> None:
        if self.inner:
            await self.inner.aclose()
