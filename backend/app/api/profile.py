import io
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from sqlalchemy import select

from app.api.deps import SessionDep
from app.domain import CandidateProfileIn, semantic_hash
from app.models import JobPostingRow, ProfileVersion
from app.pipeline.worker import latest_succeeded, rescore_all
from app.repo import current_profile, to_domain_profile

router = APIRouter(tags=["profile"])
MAX_UPLOAD = 5 * 1024 * 1024


def _content(row: ProfileVersion) -> dict:
    return CandidateProfileIn(resume_text=row.resume_text, preferences=row.preferences,
                              blocker_facts=row.blocker_facts, tracked_skills=row.tracked_skills).model_dump(mode="json")


@router.get("/profile")
def get_profile(session: SessionDep):
    row = current_profile(session)
    if row is None:
        raise HTTPException(404, "No profile yet")
    return to_domain_profile(row).model_dump(mode="json")


@router.put("/profile")
def put_profile(body: CandidateProfileIn, session: SessionDep):
    current = current_profile(session)
    content = body.model_dump(mode="json")
    if current is not None and _content(current) == content:
        return {"profile": to_domain_profile(current).model_dump(mode="json"), "change_kind": "none",
                "affected_jobs": 0, "rescored": 0}
    new_hash = semantic_hash(body)
    change_kind = "semantic" if current is None or current.semantic_hash != new_hash else "scoring_only"
    row = ProfileVersion(**content, semantic_hash=new_hash)
    session.add(row)
    session.commit()
    rescored = rescore_all(session)
    affected = 0
    if change_kind == "semantic":
        affected = sum(1 for job in session.scalars(select(JobPostingRow))
                       if (e := latest_succeeded(job)) and e.profile_version.semantic_hash != new_hash)
    return {"profile": to_domain_profile(row).model_dump(mode="json"), "change_kind": change_kind,
            "affected_jobs": affected, "rescored": rescored}


@router.post("/profile/resume/extract")
async def extract_resume(file: UploadFile):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File exceeds 5 MB")
    suffix = Path(file.filename or "").suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        elif suffix == ".docx":
            from docx import Document
            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        elif suffix == ".txt":
            text = data.decode("utf-8", errors="replace")
        else:
            raise HTTPException(415, "Upload a .pdf, .docx, or .txt file")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, f"Could not read {suffix} file") from None
    return {"text": text.strip()}
