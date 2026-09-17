from tests.api.test_profile import body

CSV = (b"Company,Job Title,Job Description,City\n"
       b"Ledgerly,Staff Android Engineer,\"" + b"Own Android architecture across teams. " * 3 + b"\",Remote\n"
       b"Parcelio,Flutter Engineer,,Berlin\n"
       b",Broken Row,description here,Nowhere\n")


def preview(client, data=CSV):
    return client.post("/api/import/csv", files={"file": ("jobs.csv", data, "text/csv")})


def test_csv_preview_then_commit(app_client):
    app_client.put("/api/profile", json=body())
    p = preview(app_client).json()
    assert p["row_count"] == 3 and p["columns"][0] == "Company" and len(p["preview"]) == 3
    assert p["suggested_mapping"] == {"Company": "company", "Job Title": "title",
                                      "Job Description": "description", "City": "location"}
    commit = app_client.post("/api/import/csv/commit",
                             json={"mapping": p["suggested_mapping"], "rows": p["rows"]}).json()
    assert (commit["created"], commit["drafts"], commit["duplicates"]) == (1, 1, 0)
    assert commit["errors"] == [{"row": 3, "reason": "missing company"}]
    stats = app_client.get("/api/jobs").json()["stats"]
    assert stats["total"] == 1 and stats["drafts"] == 1 and stats["evaluated"] == 0
    assert app_client.get("/api/jobs", params={"state": ["draft"]}).json()["rows"][0]["company"] == "Parcelio"


def test_commit_is_idempotent_by_content_hash(app_client):
    app_client.put("/api/profile", json=body())
    p = preview(app_client).json()
    payload = {"mapping": p["suggested_mapping"], "rows": p["rows"]}
    app_client.post("/api/import/csv/commit", json=payload)
    again = app_client.post("/api/import/csv/commit", json=payload).json()
    assert again["created"] == 0 and again["drafts"] == 0 and again["duplicates"] == 2


def test_import_never_evaluates(app_client):
    app_client.put("/api/profile", json=body())
    p = preview(app_client).json()
    app_client.post("/api/import/csv/commit", json={"mapping": p["suggested_mapping"], "rows": p["rows"]})
    rows = app_client.get("/api/jobs").json()["rows"]
    assert [r["evaluation_status"] for r in rows] == [None]


def test_mapping_can_be_overridden(app_client):
    p = preview(app_client).json()
    mapping = {**p["suggested_mapping"], "City": None}
    commit = app_client.post("/api/import/csv/commit", json={"mapping": mapping, "rows": p["rows"]}).json()
    assert commit["created"] == 1
    assert app_client.get("/api/jobs").json()["rows"][0]["location"] is None


def test_rejects_oversized_upload(app_client):
    big = b"company,title,description\n" + b"a,b,cccc\n" * 501
    assert preview(app_client, big).status_code == 413
    assert preview(app_client, b"company,title\n").status_code == 422


# --- POST /api/import/url ------------------------------------------------------------------

import pytest  # noqa: E402

from app.ingest.fetch.base import FetchedPosting, FetchError  # noqa: E402

SAMPLE = FetchedPosting(company="Acme", title="Android Engineer", location="Remote", description="Build apps. " * 10,
                        source_url="https://careers.acme.com/1", provider="greenhouse", confidence="structured")


def stub_fetch(app, result):
    async def fetch(url: str):
        if isinstance(result, Exception):
            raise result
        return result
    app.state.fetch_posting = fetch


def test_import_url_returns_extracted_posting(app_client):
    stub_fetch(app_client.app, SAMPLE)
    r = app_client.post("/api/import/url", json={"url": "https://careers.acme.com/1"})
    assert r.status_code == 200
    posting = r.json()["posting"]
    assert posting["company"] == "Acme" and posting["confidence"] == "structured"
    assert app_client.get("/api/jobs").json()["stats"]["total"] == 0  # nothing stored


@pytest.mark.parametrize("code,status", [
    ("blocked_site", 403), ("robots_disallow", 403), ("unsupported_scheme", 400), ("private_address", 400),
    ("not_found", 404), ("too_large", 413), ("no_content", 422), ("upstream_error", 502), ("timeout", 504),
])
def test_fetch_errors_map_to_status_codes(app_client, code, status):
    stub_fetch(app_client.app, FetchError(code, "explanation for the user"))
    r = app_client.post("/api/import/url", json={"url": "https://careers.acme.com/1"})
    assert r.status_code == status and r.json()["detail"] == "explanation for the user"
