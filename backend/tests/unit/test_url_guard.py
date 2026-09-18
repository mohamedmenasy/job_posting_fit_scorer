import pytest

from app.ingest.fetch.base import FetchError
from app.ingest.fetch.url_guard import validate_url


@pytest.mark.parametrize("url,code", [
    ("file:///etc/passwd", "unsupported_scheme"),
    ("ftp://example.com/job", "unsupported_scheme"),
    ("http://user:pass@example.com/job", "unsupported_scheme"),
    ("https://example.com:22/job", "unsupported_scheme"),
    ("not a url", "unsupported_scheme"),
    ("http://localhost/job", "private_address"),
    ("http://127.0.0.1/job", "private_address"),
    ("http://10.0.0.5/job", "private_address"),
    ("http://192.168.1.10/job", "private_address"),
    ("http://169.254.169.254/latest/meta-data", "private_address"),
    ("http://[::1]/job", "private_address"),
    ("http://[fd00::1]/job", "private_address"),
    ("http://0.0.0.0/job", "private_address"),
])
def test_rejects_unsafe_urls(url, code):
    with pytest.raises(FetchError) as err:
        validate_url(url)
    assert err.value.code == code


def test_rejects_hosts_that_do_not_resolve(monkeypatch):
    monkeypatch.setattr("app.ingest.fetch.url_guard.resolve_addresses", lambda host: [])
    with pytest.raises(FetchError) as err:
        validate_url("https://nowhere.test/job")
    assert err.value.code == "private_address"


def test_accepts_public_https(public_dns):
    parsed = validate_url("https://boards.greenhouse.io/acme/jobs/1")
    assert parsed.netloc == "boards.greenhouse.io" and parsed.path == "/acme/jobs/1"


def test_rejects_when_any_resolved_address_is_private(monkeypatch):
    monkeypatch.setattr("app.ingest.fetch.url_guard.resolve_addresses", lambda host: ["93.184.216.34", "10.0.0.5"])
    with pytest.raises(FetchError) as err:
        validate_url("https://split.test/job")
    assert err.value.code == "private_address"
