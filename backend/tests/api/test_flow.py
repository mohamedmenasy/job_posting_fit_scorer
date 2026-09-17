from app.semantic.fake_fixtures import FIXTURES
from tests.api.test_profile import body
from tests.conftest import wait_for


def posting(name="clearance_required", **over):
    return {**FIXTURES[name]["posting"], "external_id": f"fixture:{name}", **over}


def test_definition_of_done_flow(app_client):
    assert app_client.post("/api/evaluate", json=posting()).status_code == 409
    app_client.put("/api/profile", json={**body(), "blocker_facts": {"can_meet_clearance_requirement": False}})
    r = app_client.post("/api/evaluate", json=posting())
    assert r.status_code == 202 and r.json()["created"] and not r.json()["reused"]
    wait_for(app_client, r.json()["evaluation_id"])
    detail = app_client.get(f"/api/jobs/{r.json()['job']['id']}").json()
    fit = detail["fit_result"]
    assert fit["status"] == "BLOCKED" and fit["hard_blockers"][0]["type"] == "security_clearance"
    assert "clearance" in fit["hard_blockers"][0]["evidence"]
    assert detail["evaluation"]["signals"]["all_lines"] and fit["explanations"]
    assert "missing_skills" in fit and len(fit["components"]) == 8
    assert detail["latest_evaluation"]["status"] == "succeeded"


def test_reuse_and_dedupe(app_client):
    app_client.put("/api/profile", json=body())
    first = app_client.post("/api/evaluate", json=posting("android_staff_perfect")).json()
    wait_for(app_client, first["evaluation_id"])
    company = FIXTURES["android_staff_perfect"]["posting"]["company"]
    again = app_client.post("/api/evaluate", json=posting("android_staff_perfect", company=f"  {company.upper()} "))
    assert again.status_code == 200
    again = again.json()
    assert again["reused"] and not again["created"] and again["evaluation_id"] == first["evaluation_id"]
    app_client.put("/api/profile", json=body(preferred_roles=["iOS Lead"]))
    third = app_client.post("/api/evaluate", json=posting("android_staff_perfect")).json()
    assert not third["reused"] and third["evaluation_id"] != first["evaluation_id"]
    wait_for(app_client, third["evaluation_id"])


def test_history_retained_and_delete_cascade(app_client):
    app_client.put("/api/profile", json=body())
    first = app_client.post("/api/evaluate", json=posting("android_staff_perfect")).json()
    job_id = first["job"]["id"]
    wait_for(app_client, first["evaluation_id"])
    second = app_client.post(f"/api/jobs/{job_id}/evaluate")
    assert second.status_code == 202
    wait_for(app_client, second.json()["evaluation_id"])
    history = app_client.get("/api/evaluations", params={"job_id": job_id}).json()
    assert len(history) == 2 and all(h["fit_results"] for h in history)
    assert app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]["evaluation_id"] == second.json()["evaluation_id"]
    rebuilt = app_client.get(f"/api/evaluations/{first['evaluation_id']}/request").json()
    assert rebuilt["hash_matches"] and "candidate" in rebuilt["states"]["fit"]
    assert "blocker" not in str(rebuilt["states"])
    assert app_client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert app_client.get(f"/api/evaluations/{first['evaluation_id']}").status_code == 404
    assert app_client.get(f"/api/jobs/{job_id}").status_code == 404


def test_reevaluate_all(app_client):
    app_client.put("/api/profile", json=body())
    first = app_client.post("/api/evaluate", json=posting("android_staff_perfect")).json()
    wait_for(app_client, first["evaluation_id"])
    r = app_client.post("/api/jobs/reevaluate", json={})
    assert r.status_code == 202 and len(r.json()["evaluation_ids"]) == 1
    wait_for(app_client, r.json()["evaluation_ids"][0])
