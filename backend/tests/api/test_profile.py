import io

from docx import Document

from app.domain import DEFAULT_TRACKED_SKILLS


def body(**prefs):
    return {"resume_text": "Staff Android engineer", "preferences": prefs, "blocker_facts": {},
            "tracked_skills": [s.model_dump() for s in DEFAULT_TRACKED_SKILLS]}


def test_profile_versions_and_change_kind(app_client):
    assert app_client.get("/api/profile").status_code == 404
    r = app_client.put("/api/profile", json=body())
    assert r.status_code == 200 and r.json()["change_kind"] == "semantic"
    assert app_client.put("/api/profile", json=body()).json()["change_kind"] == "none"
    assert app_client.put("/api/profile", json=body(remote_preference="remote")).json()["change_kind"] == "scoring_only"
    assert app_client.put("/api/profile", json=body(preferred_roles=["Staff Android"])).json()["change_kind"] == "semantic"
    assert app_client.get("/api/profile").json()["preferences"]["preferred_roles"] == ["Staff Android"]


def test_profile_validation(app_client):
    r = app_client.put("/api/profile", json=body(required_technologies=["Kotlin"], avoid_technologies=["kotlin"]))
    assert r.status_code == 422


def test_resume_extract(app_client):
    txt = app_client.post("/api/profile/resume/extract", files={"file": ("r.txt", b"Kotlin dev", "text/plain")})
    assert txt.json() == {"text": "Kotlin dev"}
    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("Compose expert")
    doc.save(buf)
    r = app_client.post("/api/profile/resume/extract", files={"file": ("r.docx", buf.getvalue(), "application/octet-stream")})
    assert "Compose expert" in r.json()["text"]
    assert app_client.post("/api/profile/resume/extract", files={"file": ("r.exe", b"x", "application/octet-stream")}).status_code == 415
    big = b"x" * (5 * 1024 * 1024 + 1)
    assert app_client.post("/api/profile/resume/extract", files={"file": ("r.txt", big, "text/plain")}).status_code == 413
    assert app_client.post("/api/profile/resume/extract", files={"file": ("r.pdf", b"not a pdf", "application/pdf")}).status_code == 422
