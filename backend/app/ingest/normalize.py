"""Single seam for all posting sources: validate, hash, dedupe, create (spec §5.3)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import MIN_DESCRIPTION, ImportSource, JobDraftIn, JobPostingIn, sha256
from app.models import JobPostingRow


def content_hash(company: str, title: str, description: str) -> str:
    return sha256(" ".join(f"{company}|{title}|{description}".split()).lower())


def job_status(description: str) -> str:
    """A posting is a draft until it has enough text to evaluate (import §3.2)."""
    return "ready" if len(description.strip()) >= MIN_DESCRIPTION else "draft"


def find_by_content(session: Session, digest: str) -> JobPostingRow | None:
    return session.scalars(select(JobPostingRow).where(JobPostingRow.content_hash == digest).limit(1)).first()


def get_or_create_job(session: Session, data: JobPostingIn | JobDraftIn, *,
                      import_source: ImportSource | None = None) -> tuple[JobPostingRow, bool]:
    import_source = import_source or getattr(data, "import_source", "paste")
    digest = content_hash(data.company, data.title, data.description)
    existing = find_by_content(session, digest)
    if existing:
        return existing, False
    row = JobPostingRow(**data.model_dump(exclude={"source_url", "import_source"}),
                        source_url=str(data.source_url) if data.source_url else None, content_hash=digest,
                        status=job_status(data.description), import_source=import_source)
    session.add(row)
    session.flush()
    return row, True
