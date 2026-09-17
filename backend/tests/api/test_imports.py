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
