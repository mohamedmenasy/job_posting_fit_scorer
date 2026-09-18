import uuid

from tests.api.test_flow import posting
from tests.api.test_profile import body
from tests.conftest import wait_for

DRAFT = {"company": "Acme", "title": "Android Engineer", "description": "", "import_source": "csv"}
FULL_DESCRIPTION = "Build Android apps with Kotlin and Jetpack Compose every day. " * 3


def make_draft(client, **over):
    response = client.post("/api/jobs/draft", json={**DRAFT, **over})
    assert response.status_code == 201, response.text
    return response.json()["job"]


def test_draft_is_hidden_from_default_list_and_counted_separately(app_client):
    app_client.put("/api/profile", json=body())
    make_draft(app_client)
    data = app_client.get("/api/jobs").json()
    assert data["rows"] == [] and data["stats"]["drafts"] == 1 and data["stats"]["total"] == 0
    drafts = app_client.get("/api/jobs", params={"state": ["draft"]}).json()
    assert [r["status_kind"] for r in drafts["rows"]] == ["draft"]
    assert drafts["rows"][0]["import_source"] == "csv"


def test_draft_cannot_be_evaluated(app_client):
    app_client.put("/api/profile", json=body())
    job = make_draft(app_client)
    r = app_client.post(f"/api/jobs/{job['id']}/evaluate")
    assert r.status_code == 409 and "description" in r.json()["detail"]
    assert app_client.post("/api/jobs/reevaluate", json={"job_ids": [job["id"]]}).status_code == 409
    assert app_client.post("/api/jobs/reevaluate", json={}).json()["evaluation_ids"] == []


def test_patch_promotes_draft_then_locks_after_evaluation(app_client):
    app_client.put("/api/profile", json=body())
    job = make_draft(app_client)
    r = app_client.patch(f"/api/jobs/{job['id']}", json={"description": "short"})
    assert r.status_code == 200 and r.json()["job"]["status_kind"] == "draft"
    r = app_client.patch(f"/api/jobs/{job['id']}", json={"description": FULL_DESCRIPTION, "location": "Remote (US)"})
    assert r.json()["job"]["status_kind"] == "ready" and r.json()["job"]["location"] == "Remote (US)"
    evaluation = app_client.post(f"/api/jobs/{job['id']}/evaluate").json()["evaluation_id"]
    wait_for(app_client, evaluation)
    locked = app_client.patch(f"/api/jobs/{job['id']}", json={"title": "Staff Android Engineer"})
    assert locked.status_code == 409 and "immutable" in locked.json()["detail"]


def test_patch_rejects_duplicate_content(app_client):
    app_client.put("/api/profile", json=body())
    existing = app_client.post("/api/jobs", json=posting("android_staff_perfect")).json()["job"]
    draft = make_draft(app_client)
    r = app_client.patch(f"/api/jobs/{draft['id']}", json={
        "company": existing["company"], "title": existing["title"], "description": existing["description"]})
    assert r.status_code == 409 and r.json()["detail"]["existing_job_id"] == existing["id"]


def test_patch_unknown_job(app_client):
    assert app_client.patch(f"/api/jobs/{uuid.uuid4()}", json={"title": "x"}).status_code == 404


def test_paste_and_batch_still_default_to_ready(app_client):
    app_client.put("/api/profile", json=body())
    created = app_client.post("/api/jobs", json=posting("android_staff_perfect")).json()["job"]
    assert created["status_kind"] == "ready" and created["import_source"] == "paste"
    rows = app_client.get("/api/jobs").json()["rows"]
    assert [r["id"] for r in rows] == [created["id"]]
