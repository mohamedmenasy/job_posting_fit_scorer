from fastapi.testclient import TestClient

from app.main import create_app
from scripts.seed_demo import seed
from tests.conftest import make_settings


def test_seed_is_idempotent_and_evaluates_all(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    assert seed(url) == {"profile_created": True, "created": 8, "existing": 0}
    assert seed(url) == {"profile_created": False, "created": 0, "existing": 8}
    with TestClient(create_app(make_settings(tmp_path))) as client:
        stats = client.get("/api/jobs").json()["stats"]
        assert stats["evaluated"] == 8 and stats["blocked"] >= 2 and stats["failed"] == 0
