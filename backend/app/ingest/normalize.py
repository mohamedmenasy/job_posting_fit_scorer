"""Single seam for all posting sources: validate, hash, dedupe, create (spec §5.3)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import JobPostingIn, sha256
from app.models import JobPostingRow


def content_hash(company: str, title: str, description: str) -> str:
    return sha256(" ".join(f"{company}|{title}|{description}".split()).lower())


def get_or_create_job(session: Session, data: JobPostingIn) -> tuple[JobPostingRow, bool]:
    digest = content_hash(data.company, data.title, data.description)
    existing = session.scalars(select(JobPostingRow).where(JobPostingRow.content_hash == digest).limit(1)).first()
    if existing:
        return existing, False
    row = JobPostingRow(**data.model_dump(exclude={"source_url"}),
                        source_url=str(data.source_url) if data.source_url else None, content_hash=digest)
    session.add(row)
    session.flush()
    return row, True
