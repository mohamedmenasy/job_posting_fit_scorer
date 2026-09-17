"""Import endpoints: CSV files now, posting URLs in the next task (import §7)."""

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import SessionDep
from app.api.schemas import CsvCommitOut, CsvPreviewOut
from app.ingest.csv_import import MAX_BYTES, CsvError, parse_csv, rows_from_mapping, suggest_mapping
from app.ingest.normalize import get_or_create_job

router = APIRouter(tags=["import"])
PREVIEW_ROWS = 5


@router.post("/import/csv", response_model=CsvPreviewOut)
async def preview_csv(file: UploadFile):
    """Parse a CSV and propose a column mapping. Stores nothing."""
    data = await file.read(MAX_BYTES + 1)
    try:
        parsed = parse_csv(data)
    except CsvError as error:
        raise HTTPException(413 if error.code == "too_large" else 422, str(error)) from None
    return {"columns": parsed.columns, "suggested_mapping": suggest_mapping(parsed.columns),
            "row_count": len(parsed.rows), "preview": parsed.rows[:PREVIEW_ROWS],
            "rows": parsed.rows, "delimiter": parsed.delimiter, "encoding": parsed.encoding}


class CsvCommitIn(BaseModel):
    mapping: dict[str, str | None]
    rows: list[dict[str, str]] = Field(max_length=500)


@router.post("/import/csv/commit", response_model=CsvCommitOut)
def commit_csv(body: CsvCommitIn, session: SessionDep):
    """Create jobs from confirmed rows. Never evaluates (import §2 D4); one transaction for the whole file."""
    created, duplicates, drafts, errors, job_ids = 0, 0, 0, [], []
    for number, result in enumerate(rows_from_mapping(body.rows, body.mapping), start=1):
        if result.error or result.posting is None:
            errors.append({"row": number, "reason": result.error or "invalid row"})
            continue
        row, is_new = get_or_create_job(session, result.posting)
        job_ids.append(row.id)
        if not is_new:
            duplicates += 1
        elif row.status == "draft":
            drafts += 1
        else:
            created += 1
    session.commit()
    return {"created": created, "duplicates": duplicates, "drafts": drafts, "errors": errors, "job_ids": job_ids}
