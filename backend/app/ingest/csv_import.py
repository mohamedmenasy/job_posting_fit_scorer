"""CSV import: parse any spreadsheet export, guess a column mapping, build postings (import §5)."""

import csv
import io
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.domain import JobDraftIn

MAX_ROWS = 500
MAX_BYTES = 5 * 1024 * 1024
DELIMITERS = ",;\t|"

TARGET_FIELDS = ("company", "title", "description", "location", "source_url", "salary_text", "external_id")
REQUIRED_FIELDS = ("company", "title")

SYNONYMS: dict[str, tuple[str, ...]] = {
    "company": ("company", "company name", "employer", "organisation", "organization", "org", "firm"),
    "title": ("title", "job title", "role", "position", "job"),
    "description": ("description", "job description", "details", "summary", "body", "text", "content"),
    "location": ("location", "city", "place", "where", "job location", "office"),
    "source_url": ("url", "link", "job url", "posting url", "apply link", "job link", "apply url"),
    "salary_text": ("salary", "compensation", "pay", "salary range", "comp"),
    "external_id": ("id", "job id", "req id", "requisition", "requisition id", "external id"),
}


class CsvError(Exception):
    """`too_large` means the file exceeds a limit (HTTP 413); `invalid` means it cannot be read (422)."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


@dataclass
class ParsedCsv:
    columns: list[str]
    rows: list[dict[str, str]]
    delimiter: str
    encoding: str


@dataclass
class RowResult:
    posting: JobDraftIn | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def _decode(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding), "utf-8"
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1"), "latin-1"


def _headers(raw: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    columns = []
    for i, name in enumerate(raw, start=1):
        name = name.strip() or f"column_{i}"
        seen[name] = seen.get(name, 0) + 1
        columns.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return columns


def parse_csv(data: bytes) -> ParsedCsv:
    if len(data) > MAX_BYTES:
        raise CsvError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB", "too_large")
    text, encoding = _decode(data)
    if not text.strip():
        raise CsvError("The file is empty")
    sample = text[:8192]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        delimiter = max(DELIMITERS, key=lambda d: sample.count(d))
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise CsvError("The file is empty") from None
    columns = _headers(header)
    rows: list[dict[str, str]] = []
    for values in reader:
        if not any(v.strip() for v in values):
            continue
        rows.append({column: (values[i].strip() if i < len(values) else "") for i, column in enumerate(columns)})
        if len(rows) > MAX_ROWS:
            raise CsvError(f"More than {MAX_ROWS} rows; split the file and import it in parts", "too_large")
    if not rows:
        raise CsvError("The file has headers but no data rows")
    return ParsedCsv(columns=columns, rows=rows, delimiter=delimiter, encoding=encoding)


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    """Guess which column feeds which posting field; each field is claimed by at most one column."""
    mapping: dict[str, str | None] = {column: None for column in columns}
    taken: set[str] = set()
    for field_name in TARGET_FIELDS:  # field order decides who wins when two columns match
        for column in columns:
            if mapping[column] is not None:
                continue
            if field_name not in taken and _normalize(column) in SYNONYMS[field_name]:
                mapping[column] = field_name
                taken.add(field_name)
                break
    return mapping


def rows_from_mapping(rows: list[dict[str, str]], mapping: dict[str, str | None]) -> list[RowResult]:
    results: list[RowResult] = []
    for row in rows:
        values = {field_name: row.get(column, "").strip()
                  for column, field_name in mapping.items() if field_name}
        missing = [f for f in REQUIRED_FIELDS if not values.get(f)]
        if missing:
            results.append(RowResult(error=f"missing {', '.join(missing)}"))
            continue
        warnings: list[str] = []
        payload = {k: v for k, v in values.items() if v} | {"description": values.get("description", "")}
        payload.setdefault("source", "other")
        try:
            posting = JobDraftIn(**payload, import_source="csv")
        except ValidationError:
            payload.pop("source_url", None)
            warnings.append("source_url was not a valid http(s) URL and was dropped")
            try:
                posting = JobDraftIn(**payload, import_source="csv")
            except ValidationError as error:
                results.append(RowResult(error=str(error.errors()[0].get("msg", "invalid row"))))
                continue
        results.append(RowResult(posting=posting, warnings=warnings))
    return results
