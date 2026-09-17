import uuid

from app.semantic.fake_fixtures import FIXTURES
from tests.api.test_profile import body
from tests.conftest import wait_for

JOB = {"company": "Acme", "title": "Android Engineer", "description": "Build Android apps with Kotlin and Compose. " * 3}


def test_create_dedupes_by_content_hash(app_client):
    first = app_client.post("/api/jobs", json=JOB)
    assert first.status_code == 201 and first.json()["created"]
    variant = {**JOB, "company": " ACME ", "description": JOB["description"].replace(" ", "   ")}
    second = app_client.post("/api/jobs", json=variant)
    assert second.status_code == 200 and not second.json()["created"]
    assert second.json()["job"]["id"] == first.json()["job"]["id"]


def test_validation_and_404(app_client):
    assert app_client.post("/api/jobs", json={**JOB, "description": "short"}).status_code == 422
    assert app_client.get(f"/api/jobs/{uuid.uuid4()}").status_code == 404
    job_id = app_client.post("/api/jobs", json=JOB).json()["job"]["id"]
    assert app_client.post(f"/api/jobs/{job_id}/evaluate").status_code == 409


NAMES = ["android_staff_perfect", "flutter_heavy", "engineering_manager", "clearance_required"]


def batch(client):
    client.put("/api/profile", json={**body(preferred_levels=["staff"], management_preference="ic"),
                                     "blocker_facts": {"can_meet_clearance_requirement": False}})
    jobs = [{**FIXTURES[n]["posting"], "external_id": f"fixture:{n}"} for n in NAMES]
    r = client.post("/api/jobs/batch", json={"jobs": jobs + jobs[:1], "auto_evaluate": True}).json()
    assert (r["created"], r["existing"], len(r["evaluation_ids"])) == (4, 1, 4)
    for eid in r["evaluation_ids"]:
        wait_for(client, eid)


def test_batch_list_sort_filter_stats(app_client):
    batch(app_client)
    data = app_client.get("/api/jobs").json()
    scores = [row["overall_score"] for row in data["rows"]]
    assert scores == sorted(scores, reverse=True)
    assert data["stats"]["total"] == 4 and data["stats"]["evaluated"] == 4 and data["stats"]["blocked"] == 1
    assert [r["status"] for r in app_client.get("/api/jobs", params={"status": ["BLOCKED"]}).json()["rows"]] == ["BLOCKED"]
    assert len(app_client.get("/api/jobs", params={"clearance": "required"}).json()["rows"]) == 1
    assert len(app_client.get("/api/jobs", params={"role_family": ["flutter", "engineering_management"]}).json()["rows"]) == 2
    assert len(app_client.get("/api/jobs", params={"q": "parcel"}).json()["rows"]) == 1
    assert len(app_client.get("/api/jobs", params={"min_android_relevance": 3}).json()["rows"]) == 2
    by_company = app_client.get("/api/jobs", params={"sort": "company", "order": "asc"}).json()["rows"]
    assert [r["company"] for r in by_company] == sorted((r["company"] for r in by_company), key=str.lower)
    paged = app_client.get("/api/jobs", params={"limit": 2, "offset": 1}).json()
    assert len(paged["rows"]) == 2 and paged["total_filtered"] == 4


def test_unscored_jobs_sort_last(app_client):
    batch(app_client)
    app_client.post("/api/jobs", json={"company": "Zed", "title": "Android", "description": "Android work " * 10})
    rows = app_client.get("/api/jobs").json()["rows"]
    assert rows[-1]["overall_score"] is None and rows[-1]["evaluation_status"] is None
    assert app_client.get("/api/jobs", params={"order": "asc"}).json()["rows"][-1]["overall_score"] is None


def test_batch_limit_and_profile_requirement(app_client):
    job = {"company": "A", "title": "B", "description": "x" * 60}
    assert app_client.post("/api/jobs/batch", json={"jobs": [job] * 501, "auto_evaluate": False}).status_code == 422
    assert app_client.post("/api/jobs/batch", json={"jobs": [job], "auto_evaluate": True}).status_code == 409
