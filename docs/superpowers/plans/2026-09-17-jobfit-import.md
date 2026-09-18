# JobFit AI Import Implementation Plan (CSV and URL)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let jobs enter JobFit from a CSV file or a posting URL, with anything incomplete saved as an editable draft that is never evaluated.

**Architecture:** Both paths funnel into the existing `ingest.normalize` seam (content hash + dedupe). URL fetching sits behind a provider registry with a single guarded HTTP client; CSV parsing is a separate pure module. Drafts are a new posting status that relaxes immutability only until the first successful evaluation.

**Tech Stack:** Existing Phase 1 stack, plus `selectolax` for HTML parsing. Outbound HTTP uses `httpx2` (already present via the TypeSafe SDK). Frontend adds a Tabs-based New job page and a mapping table; no new npm dependencies.

**Spec:** `docs/superpowers/specs/2026-09-17-jobfit-import-design.md` ("§N" below). Core Phase 1 spec is `docs/superpowers/specs/2026-09-17-jobfit-ai-design.md` ("core §N").

## Global Constraints

- No test in `make test` may open a socket: providers are tested against recorded responses, API tests use a stub registry.
- Import never enqueues an evaluation (§2 D4). Drafts are refused by every evaluation endpoint with 409.
- A `ready` job is immutable; `PATCH` only applies to drafts (§3.2, core §5.3).
- Every outbound request passes through the guard in `fetch/url_guard.py`: public IPs only, ≤ 3 manually walked redirects, 10 s timeout, 2 MB cap, no cookies or auth headers, robots.txt honored (§6).
- Login-walled sites are refused by name; no workaround is implemented or documented (§4.4).
- The backend still runs as a single uvicorn process; `app/scoring/` stays pure.

## File structure

```
backend/app/domain.py                 + JobStatus, ImportSource, JobDraftIn, JobPatch
backend/app/models.py                 + job_postings.status, .import_source
backend/alembic/versions/0002_import.py
backend/app/ingest/normalize.py       get_or_create_job takes status/import_source
backend/app/ingest/csv_import.py      parse_csv, suggest_mapping, rows_from_mapping
backend/app/ingest/fetch/{__init__,base,url_guard,robots,ats,html,blocked}.py
backend/app/api/imports.py            POST /api/import/{url,csv,csv/commit}
backend/app/api/jobs.py               PATCH /api/jobs/{id}, status filter, drafts stat, draft refusals
backend/app/api/schemas.py            + FetchedPostingOut, CsvPreviewOut, CsvCommitOut, JobPatchIn
backend/tests/unit/test_url_guard.py  test_robots.py  test_ats_providers.py  test_html_extract.py  test_csv_import.py
backend/tests/fixtures/http/*.json|*.html
backend/tests/api/test_drafts.py  test_imports.py
frontend/src/app/jobs/new/page.tsx    tabs: Paste | From URL | From CSV
frontend/src/components/import/{url-tab,csv-tab,mapping-table}.tsx
frontend/src/app/jobs/[id]/page.tsx   draft editing
frontend/src/components/dashboard/*   drafts filter + stat tile
frontend/e2e/import.spec.ts
```

---

### Task 1: Draft status, editing, and evaluation refusals

**Files:** Modify `app/domain.py`, `app/models.py`, `app/ingest/normalize.py`, `app/api/jobs.py`, `app/api/schemas.py`, `app/api/serializers.py`; Create `alembic/versions/0002_import.py`, `tests/api/test_drafts.py`

**Produces:**
- `JobStatus = Literal["draft", "ready"]`, `ImportSource = Literal["paste", "url", "csv"]`.
- `JobDraftIn`: same fields as `JobPostingIn` but `description: str = ""` with no minimum; `JobPatch`: every posting field optional.
- `get_or_create_job(session, data: JobPostingIn | JobDraftIn, *, import_source="paste") -> tuple[JobPostingRow, bool]` sets `status` from the description length.
- `PATCH /api/jobs/{id}` (§7): 404 unknown; 409 `"Evaluated jobs are immutable — create a new job instead"` when the job has any succeeded evaluation; 409 with `existing_job_id` when the new content hash collides; promotes `draft` → `ready` at 50+ characters.
- `GET /api/jobs?status=` (repeatable, default `ready`), `JobStatsOut.drafts`.
- 409 `"Add a job description before evaluating"` from `POST /api/jobs/{id}/evaluate`, `POST /api/jobs/reevaluate`, `POST /api/jobs/batch` (skips drafts), and `POST /api/evaluate` when the stored job is a draft.

- [ ] **Step 1: Write the failing tests** (`tests/api/test_drafts.py`)

```python
import uuid

from app.domain import DEFAULT_TRACKED_SKILLS
from tests.api.test_flow import posting
from tests.api.test_profile import body
from tests.conftest import wait_for

DRAFT = {"company": "Acme", "title": "Android Engineer", "description": "", "import_source": "csv"}


def make_draft(client, **over):
    return client.post("/api/jobs/draft", json={**DRAFT, **over}).json()["job"]


def test_draft_is_hidden_from_default_list_and_counted_separately(app_client):
    app_client.put("/api/profile", json=body())
    make_draft(app_client)
    data = app_client.get("/api/jobs").json()
    assert data["rows"] == [] and data["stats"]["drafts"] == 1 and data["stats"]["total"] == 0
    drafts = app_client.get("/api/jobs", params={"status": ["draft"]}).json()
    assert [r["status_kind"] for r in drafts["rows"]] == ["draft"]


def test_draft_cannot_be_evaluated(app_client):
    app_client.put("/api/profile", json=body())
    job = make_draft(app_client)
    r = app_client.post(f"/api/jobs/{job['id']}/evaluate")
    assert r.status_code == 409 and "description" in r.json()["detail"]
    assert app_client.post("/api/jobs/reevaluate", json={"job_ids": [job["id"]]}).status_code == 409


def test_patch_promotes_draft_then_locks_after_evaluation(app_client):
    app_client.put("/api/profile", json=body())
    job = make_draft(app_client)
    r = app_client.patch(f"/api/jobs/{job['id']}", json={"description": "short"})
    assert r.status_code == 200 and r.json()["job"]["status_kind"] == "draft"
    full = "Build Android apps with Kotlin and Jetpack Compose every day. " * 3
    r = app_client.patch(f"/api/jobs/{job['id']}", json={"description": full, "location": "Remote (US)"})
    assert r.json()["job"]["status_kind"] == "ready" and r.json()["job"]["location"] == "Remote (US)"
    evaluation = app_client.post(f"/api/jobs/{job['id']}/evaluate").json()["evaluation_id"]
    wait_for(app_client, evaluation)
    locked = app_client.patch(f"/api/jobs/{job['id']}", json={"title": "Staff Android Engineer"})
    assert locked.status_code == 409 and "immutable" in locked.json()["detail"]


def test_patch_rejects_duplicate_content(app_client):
    app_client.put("/api/profile", json=body())
    existing = app_client.post("/api/jobs", json=posting("android_staff_perfect")).json()["job"]
    draft = make_draft(app_client)
    r = app_client.patch(f"/api/jobs/{draft['id']}", json={
        "company": existing["company"], "title": existing["title"], "description": existing["description"]})
    assert r.status_code == 409 and r.json()["detail"]["existing_job_id"] == existing["id"]


def test_patch_unknown_job(app_client):
    assert app_client.patch(f"/api/jobs/{uuid.uuid4()}", json={"title": "x"}).status_code == 404
```

Note: `POST /api/jobs/draft` is added in this task (thin wrapper over `get_or_create_job` with `JobDraftIn`); the row field is named `status_kind` in API output to avoid colliding with the existing fit `status`.

- [ ] **Step 2:** `cd backend && uv run pytest tests/api/test_drafts.py -q` → FAIL.
- [ ] **Step 3: Implement.** Add columns with `server_default` so existing rows backfill; generate the migration with `uv run alembic revision --autogenerate -m import --rev-id 0002` and verify `tests/api/test_migrations.py` still passes.
- [ ] **Step 4:** `uv run pytest` → all pass.
- [ ] **Step 5:** Commit `feat(ingest): draft postings that can be edited before evaluation`.

---

### Task 2: CSV parsing, mapping, preview, and commit

**Files:** Create `app/ingest/csv_import.py`, `app/api/imports.py`, `tests/unit/test_csv_import.py`, `tests/api/test_imports.py`; Modify `app/main.py`, `app/api/schemas.py`

**Produces:**
- `parse_csv(data: bytes) -> ParsedCsv` with `columns: list[str]`, `rows: list[dict[str, str]]`, `delimiter`, `encoding`; strips BOM, falls back to Latin-1, sniffs `, ; \t |`, de-duplicates blank/repeated headers (`column_2`), raises `CsvError` for no headers, no rows, > 500 rows, > 5 MB.
- `suggest_mapping(columns) -> dict[str, str | None]` using the §5.2 synonym table, normalizing case, spaces, and punctuation.
- `rows_from_mapping(rows, mapping) -> list[RowResult]` where each entry is a `JobDraftIn` or an error reason.
- `POST /api/import/csv` (multipart) → `CsvPreviewOut{columns, suggested_mapping, row_count, preview, delimiter, encoding}`; `POST /api/import/csv/commit` → `CsvCommitOut{created, duplicates, drafts, errors, job_ids}`, one transaction, `import_source="csv"`.

- [ ] **Step 1: Failing unit tests** (`tests/unit/test_csv_import.py`)

```python
import pytest

from app.ingest.csv_import import CsvError, parse_csv, rows_from_mapping, suggest_mapping

CSV = b"Company,Job Title,Job Description,City\nAcme,Android Engineer,\"Build apps.\nShip them.\",Berlin\n"


def test_parses_headers_rows_and_quoted_newlines():
    parsed = parse_csv(CSV)
    assert parsed.columns == ["Company", "Job Title", "Job Description", "City"]
    assert parsed.rows[0]["Job Description"] == "Build apps.\nShip them."
    assert parsed.delimiter == "," and parsed.encoding == "utf-8"


def test_bom_semicolons_and_tabs():
    assert parse_csv("﻿company;title\nAcme;Dev\n".encode()).delimiter == ";"
    assert parse_csv(b"company\ttitle\nAcme\tDev\n").delimiter == "\t"
    assert parse_csv("company,title\nAcmé,Dev\n".encode("latin-1")).encoding == "latin-1"


def test_duplicate_and_blank_headers_are_disambiguated():
    assert parse_csv(b"company,company,\nA,B,C\n").columns == ["company", "company_2", "column_3"]


@pytest.mark.parametrize("data,message", [
    (b"", "empty"), (b"company,title\n", "no data rows"),
    (b"company,title\n" + b"a,b\n" * 501, "500"),
])
def test_rejects_bad_files(data, message):
    with pytest.raises(CsvError) as err:
        parse_csv(data)
    assert message in str(err.value).lower()


@pytest.mark.parametrize("column,field", [
    ("Company", "company"), ("Employer", "company"), ("Job Title", "title"), ("Role", "title"),
    ("Job Description", "description"), ("Details", "description"), ("City", "location"),
    ("Apply Link", "source_url"), ("Salary Range", "salary_text"), ("Req ID", "external_id"),
    ("Notes", None),
])
def test_mapping_synonyms(column, field):
    assert suggest_mapping([column]).get(column) == field


def test_rows_from_mapping_reports_missing_required_fields():
    mapping = {"Company": "company", "Job Title": "title", "Job Description": "description"}
    rows = [{"Company": "Acme", "Job Title": "Dev", "Job Description": "x" * 60},
            {"Company": "", "Job Title": "Dev", "Job Description": "x" * 60},
            {"Company": "Acme", "Job Title": "Dev", "Job Description": ""}]
    results = rows_from_mapping(rows, mapping)
    assert results[0].posting and results[0].posting.description.startswith("x")
    assert results[1].error and "company" in results[1].error
    assert results[2].posting and results[2].posting.description == ""   # becomes a draft
```

- [ ] **Step 2: Failing API test** (`tests/api/test_imports.py`)

```python
from tests.api.test_profile import body

CSV = (b"Company,Job Title,Job Description,City\n"
       b"Ledgerly,Staff Android Engineer,\"" + b"Own Android architecture across teams. " * 3 + b"\",Remote\n"
       b"Parcelio,Flutter Engineer,,Berlin\n"
       b",Broken Row,description here,Nowhere\n")


def test_csv_preview_then_commit(app_client):
    app_client.put("/api/profile", json=body())
    preview = app_client.post("/api/import/csv", files={"file": ("jobs.csv", CSV, "text/csv")}).json()
    assert preview["row_count"] == 3 and preview["columns"][0] == "Company"
    assert preview["suggested_mapping"] == {"Company": "company", "Job Title": "title",
                                            "Job Description": "description", "City": "location"}
    commit = app_client.post("/api/import/csv/commit", json={
        "mapping": preview["suggested_mapping"], "rows": preview["preview"]}).json()
    assert (commit["created"], commit["drafts"], len(commit["errors"])) == (2, 1, 1)
    assert commit["errors"][0]["row"] == 3
    assert app_client.get("/api/jobs").json()["stats"] == {**app_client.get("/api/jobs").json()["stats"],
                                                           "total": 1, "drafts": 1}
    assert app_client.get("/api/jobs", params={"status": ["draft"]}).json()["rows"][0]["company"] == "Parcelio"


def test_commit_dedupes_against_existing_jobs(app_client):
    app_client.put("/api/profile", json=body())
    preview = app_client.post("/api/import/csv", files={"file": ("jobs.csv", CSV, "text/csv")}).json()
    payload = {"mapping": preview["suggested_mapping"], "rows": preview["preview"]}
    app_client.post("/api/import/csv/commit", json=payload)
    again = app_client.post("/api/import/csv/commit", json=payload).json()
    assert again["created"] == 0 and again["duplicates"] == 2


def test_rejects_oversized_upload(app_client):
    big = b"company,title,description\n" + b"a,b,cccc\n" * 501
    assert app_client.post("/api/import/csv", files={"file": ("big.csv", big, "text/csv")}).status_code == 413
```

- [ ] **Step 3–4:** FAIL → implement → all pass.
- [ ] **Step 5:** Commit `feat(ingest): CSV import with column mapping`.

---

### Task 3: Guarded fetcher, robots, and provider registry

**Files:** Create `app/ingest/fetch/{__init__,base,url_guard,robots}.py`, `tests/unit/test_url_guard.py`, `tests/unit/test_robots.py`

**Produces:**
- `validate_url(url: str) -> ParseResult` raising `FetchError` for non-http(s) schemes, userinfo, odd ports, unresolvable hosts, and any host resolving to a non-global address (`private_address`).
- `class HttpFetcher`: `async get(url, *, accept) -> Response`; manual redirects (≤ 3, each re-validated, no https→http), 10 s timeout, 2 MB streaming cap, fixed user agent, no cookies, per-host `asyncio.Lock`, `robots_allowed()` consulted before the first request to a host.
- `robots.py`: `RobotsCache(ttl=3600, max_hosts=200)` wrapping `urllib.robotparser`; missing/unreadable robots means allowed.
- `fetch_posting(url, fetcher=None) -> FetchedPosting` walking `PROVIDERS`.
- Tests inject a `transport` so nothing touches the network.

- [ ] **Step 1: Failing tests** (`tests/unit/test_url_guard.py`)

```python
import pytest

from app.ingest.fetch.base import FetchError
from app.ingest.fetch.url_guard import validate_url

@pytest.mark.parametrize("url,code", [
    ("file:///etc/passwd", "unsupported_scheme"),
    ("ftp://example.com/job", "unsupported_scheme"),
    ("http://user:pass@example.com/job", "unsupported_scheme"),
    ("http://localhost:8000/job", "private_address"),
    ("http://127.0.0.1/job", "private_address"),
    ("http://10.0.0.5/job", "private_address"),
    ("http://169.254.169.254/latest/meta-data", "private_address"),
    ("http://[::1]/job", "private_address"),
    ("http://example.com:22/job", "unsupported_scheme"),
])
def test_rejects_unsafe_urls(url, code):
    with pytest.raises(FetchError) as err:
        validate_url(url)
    assert err.value.code == code


def test_accepts_public_https(monkeypatch):
    monkeypatch.setattr("app.ingest.fetch.url_guard.resolve_addresses", lambda host: ["93.184.216.34"])
    assert validate_url("https://boards.greenhouse.io/acme/jobs/1").netloc == "boards.greenhouse.io"
```

Redirect, size, timeout, and robots behavior (`tests/unit/test_robots.py` plus fetcher tests in the same file) use `httpx2.MockTransport`:

```python
async def test_redirects_are_walked_and_revalidated(public_dns):
    hops = {"https://a.test/j": "https://b.test/j", "https://b.test/j": "http://10.0.0.5/j"}
    fetcher = HttpFetcher(transport=redirect_transport(hops))
    with pytest.raises(FetchError) as err:
        await fetcher.get("https://a.test/j")
    assert err.value.code == "private_address"


async def test_too_many_redirects_and_size_cap(public_dns):
    ...  # 4-hop chain → "too_many_redirects"; 3 MB body → "too_large"


async def test_robots_disallow_blocks_fetch(public_dns):
    fetcher = HttpFetcher(transport=robots_transport("User-agent: *\nDisallow: /jobs"))
    with pytest.raises(FetchError) as err:
        await fetcher.get("https://c.test/jobs/1")
    assert err.value.code == "robots_disallow"


async def test_missing_robots_allows_fetch(public_dns):
    ...  # 404 robots.txt → request proceeds
```

- [ ] **Step 2–4:** FAIL → implement → pass.
- [ ] **Step 5:** Commit `feat(ingest): guarded URL fetcher with robots support`.

---

### Task 4: Providers (ATS, HTML, blocked) and `POST /api/import/url`

**Files:** Create `app/ingest/fetch/{ats,html,blocked}.py`, `tests/unit/test_ats_providers.py`, `tests/unit/test_html_extract.py`, `tests/fixtures/http/*`, `tests/live/test_providers_live.py`; Modify `app/api/imports.py`, `app/api/schemas.py`, `backend/pyproject.toml` (add `selectolax`)

**Produces:** the four ATS providers, the HTML extractor, the blocked-site provider, and `POST /api/import/url` mapping `FetchError.code` to the §7 status codes.

- [ ] **Step 1: Record real responses once.** With network access, save one response per provider into `tests/fixtures/http/` (`greenhouse_job.json`, `lever_job.json`, `ashby_board.json`, `workable_job.json`) and one representative career page (`jsonld_page.html`, `plain_page.html`). Note each source URL in a `SOURCES.md` beside them. If a documented endpoint shape differs from §4.2, update the spec table in the same commit.
- [ ] **Step 2: Failing tests** — each provider maps its recorded response to a `FetchedPosting` with non-empty description, expected company/title/location, `confidence="structured"`; a 404 and a truncated payload raise `upstream_error`; `matches()` accepts the real URL shapes and rejects others.

```python
async def test_greenhouse_maps_recorded_response():
    posting = await fetch_posting("https://boards.greenhouse.io/acme/jobs/4567", fetcher=recorded("greenhouse_job.json"))
    assert posting.provider == "greenhouse" and posting.confidence == "structured"
    assert posting.title and posting.company and "<" not in posting.description


@pytest.mark.parametrize("url", ["https://www.linkedin.com/jobs/view/123", "https://uk.indeed.com/viewjob?jk=1",
                                 "https://www.glassdoor.com/job-listing/x"])
async def test_blocked_sites_refuse_with_paste_hint(url):
    with pytest.raises(FetchError) as err:
        await fetch_posting(url, fetcher=never_called_fetcher())
    assert err.value.code == "blocked_site" and "Paste" in err.value.message
```

HTML tests: JSON-LD page yields title/company/location and clean text; a plain page yields text with nav, script, and cookie banner removed; an empty shell raises `no_content`; extracted postings carry `confidence="extracted"` and a warning naming missing fields.

API tests (`tests/api/test_imports.py`): `POST /api/import/url` with a stub registry returns the posting payload; each `FetchError` code maps to its status (403 blocked/robots, 400 scheme/private, 404, 413, 502, 504) and never leaks a stack trace.

- [ ] **Step 3–4:** implement → all pass, `make test` still opens no sockets (`tests/live/test_providers_live.py` is marked `live_http` and excluded by `addopts`).
- [ ] **Step 5:** Commit `feat(ingest): ATS and HTML providers for posting URLs`.

---

### Task 5: Frontend import tabs, drafts, and editing

**Files:** Modify `frontend/src/app/jobs/new/page.tsx`, `frontend/src/app/jobs/[id]/page.tsx`, `frontend/src/components/dashboard/{filter-bar,stat-strip,jobs-table}.tsx`, `frontend/src/lib/api/hooks.ts`, `frontend/src/lib/api/schema.d.ts` (regenerated); Create `frontend/src/components/import/{url-tab,csv-tab,mapping-table}.tsx`

**Produces:**
- Hooks `useImportUrl`, `useCsvPreview`, `useCsvCommit`, `usePatchJob`, plus `status` in the dashboard query.
- **From URL tab:** URL field, Fetch button, provider badge ("From the employer's job board API" / "Extracted from the page — check the fields"), warnings, fields populated into the shared posting form, blocked-site message pointing at the Paste tab.
- **From CSV tab:** file input, mapping table (one row per column, select per target field, duplicate-target warning, required-field guard), five-row preview, Import button, result panel with created/duplicate/draft counts, row errors, and links to the new jobs and to the drafts filter.
- **Dashboard:** `Drafts` toggle in the filter bar; a drafts stat tile shown only when `stats.drafts > 0`; draft rows render "Needs description" instead of a score.
- **Job detail (draft):** Draft badge, editable company/title/location/description, Save button (`PATCH`), evaluation controls disabled with the reason; after promotion the page returns to the normal read-only view.

- [ ] **Step 1:** `make types` after Task 4, then implement the components.
- [ ] **Step 2:** `npm run typecheck && npm run lint && npm run build`.
- [ ] **Step 3:** Manual check against `EVALUATOR=fake`: import the sample CSV, fix a mapping, see counts, open the draft, paste text, save, evaluate.
- [ ] **Step 4:** Commit `feat(frontend): import from URL or CSV, and draft editing`.

---

### Task 6: End-to-end test and docs

**Files:** Create `frontend/e2e/import.spec.ts`; Modify `README.md`, `CLAUDE.md`, core spec §15, `Makefile` (if a target is added)

- [ ] **Step 1:** Playwright test: upload a two-row CSV (one complete, one description-less), change one mapping select, import, assert "1 job, 1 draft", open the draft from the drafts filter, paste a description, save, evaluate, and see a score.
- [ ] **Step 2:** `make e2e` passes; `make test` passes.
- [ ] **Step 3:** README gains an "Adding jobs" section (paste, URL with the supported boards and the blocked-site note, CSV with the mapping step) and a line in the privacy section stating that fetching honors robots.txt, never sends credentials, and only reaches public addresses. `CLAUDE.md` gains the ingest invariants. Core spec §15 marks CSV import and URL fetch as delivered, pointing at the import spec.
- [ ] **Step 4:** Commit `docs: describe CSV and URL import`, push, open a PR against `main`.
