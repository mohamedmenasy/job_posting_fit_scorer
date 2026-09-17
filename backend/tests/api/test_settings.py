from app.scoring.config import ScoringConfig
from tests.api.test_flow import posting
from tests.api.test_profile import body
from tests.conftest import wait_for


def evaluated(client, name="android_staff_perfect"):
    client.put("/api/profile", json=body())
    r = client.post("/api/evaluate", json=posting(name)).json()
    wait_for(client, r["evaluation_id"])
    return r["job"]["id"]


def test_settings_change_rescores_without_evaluator_calls(app_client, monkeypatch):
    job_id = evaluated(app_client)
    before = app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]

    async def boom(*args, **kwargs):
        raise AssertionError("evaluator called")
    monkeypatch.setattr(app_client.app.state.evaluator, "evaluate", boom)
    cfg = ScoringConfig().model_dump()
    cfg["status_thresholds"] = {"strong_match": 99.9, "good_match": 99.8, "review": 99.7}
    r = app_client.put("/api/settings/scoring", json=cfg).json()
    assert r == {"version": 2, "rescored": 1}
    after = app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]
    assert after["id"] != before["id"] and after["status"] == "LOW_MATCH" and after["scoring_config_version"] == 2
    assert app_client.get("/api/settings/scoring").json()["version"] == 2
    bad = {**cfg, "weights": {**cfg["weights"], "technical": -1}}
    assert app_client.put("/api/settings/scoring", json=bad).status_code == 422


def test_profile_changes_rescore_and_flag_stale(app_client):
    job_id = evaluated(app_client)
    r = app_client.put("/api/profile", json=body(management_preference="manager")).json()
    assert r["change_kind"] == "scoring_only" and r["rescored"] == 1
    assert not app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]["stale_semantics"]
    r = app_client.put("/api/profile", json=body(preferred_roles=["iOS Lead"])).json()
    assert r["change_kind"] == "semantic" and r["affected_jobs"] == 1
    fit = app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]
    assert fit["stale_semantics"]
    assert any("re-evaluate" in e["text"] for e in fit["explanations"])


def test_meta_and_health(app_client):
    meta = app_client.get("/api/meta").json()
    assert {"value": "android_native", "label": "Android native"} in meta["enums"]["RoleFamily"]
    assert {"value": "STRONG_MATCH", "label": "Strong match"} in meta["enums"]["FitStatus"]
    assert len(meta["default_tracked_skills"]) == 18 and meta["evaluator_version"] == "1.0.0"
    assert app_client.get("/api/health").json() == {
        "status": "ok", "evaluator": "fake", "model": "fake", "api_key_configured": False, "queue_depth": 0}
