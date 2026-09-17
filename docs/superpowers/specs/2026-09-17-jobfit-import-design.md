# JobFit AI — Import Design (Phase 2a: CSV and URL)

- **Date:** 2026-09-17
- **Status:** Approved in brainstorming; pending written-spec review
- **Builds on:** `docs/superpowers/specs/2026-09-17-jobfit-ai-design.md` (Phase 1, referenced as *core §N*)
- **Covers:** Phase 2 items "CSV import" and "URL fetch via `JobContentProvider`" (core §15)
- **Not covered:** compare view and duplicate detection (separate spec), any Phase 3 integration

## 1. Summary

Today a job enters JobFit one way: paste the text. This spec adds two more, behind the ingest seam that already
normalizes, hashes, and dedupes postings.

```
CSV file  → parse → column mapping → rows ─┐
posting URL → provider → extracted fields ─┼→ ingest.normalize → JobPosting (ready | draft)
paste (existing) ──────────────────────────┘
```

Nothing evaluates automatically. Imported jobs are stored, then you choose what to evaluate, because every
evaluation costs TypeSafe requests (core §6.4: roughly 150–250 questions across two requests per job).

A posting that arrives without usable text is stored as a **draft**: editable, never evaluated, hidden from
dashboard counts until you complete it.

## 2. Decisions log

| # | Decision | Choice |
|---|----------|--------|
| D1 | Scope | CSV import + URL fetch. Compare and duplicate detection get their own spec. |
| D2 | URL coverage | Public ATS JSON APIs (Greenhouse, Lever, Ashby, Workable) with a generic HTML fallback. Login-walled sites (LinkedIn, Indeed, Glassdoor) are refused by name, never circumvented. |
| D3 | CSV columns | Any headers; the server guesses a mapping and the user confirms it before import. |
| D4 | Evaluation on import | Never automatic. Import stores jobs; evaluation stays an explicit action. |
| D5 | Failed rows and fetches | Stored as drafts (D7), never silently dropped. Per-row errors are reported. |
| D6 | Fetch execution | Synchronous inside the request, one URL at a time. CSV import performs no fetching. |
| D7 | Draft postings | New `status` on `job_postings`. Drafts are editable and cannot be evaluated; on first successful evaluation a job becomes immutable, preserving core §5.3. |
| D8 | UI | New job page becomes three tabs: Paste, From URL, From CSV. No new nav entry. |

## 3. Domain and persistence changes

### 3.1 Enums (`app/domain.py`)

```python
JobStatus    = Literal["draft", "ready"]
ImportSource = Literal["paste", "url", "csv"]
```

`JobSource` (core §5.3, where the job was advertised) is unchanged and stays independent of `ImportSource`
(how the row reached JobFit).

### 3.2 `JobPosting`

- `status: JobStatus = "ready"`, `import_source: ImportSource = "paste"`.
- `JobPostingIn.description` keeps its 50-character minimum. A new `JobDraftIn` allows `description` of any
  length, including empty, and is the only way to create a `draft`.
- A `draft` job may be edited (§7, `PATCH /api/jobs/{id}`). A `ready` job may not; editing means creating a new job, because evidence
  line IDs must keep pointing at the text that was evaluated (core §5.3).
- A job becomes `ready` when an edit brings its description to 50+ characters. It never returns to `draft`.

### 3.3 Migration `0002_import`

Adds `job_postings.status` (default `'ready'`, indexed) and `job_postings.import_source` (default `'paste'`).
Both columns are backfilled by the defaults, so existing rows keep today's behavior. A test asserts the
migration matches the models, as in core §13.2.

### 3.4 Dashboard and counts

- `GET /api/jobs` accepts `status` (`draft` | `ready`, repeatable). Default: `ready` only.
- `JobStatsOut` gains `drafts`. All other counts continue to describe `ready` jobs only, so a pile of unfinished
  drafts cannot make the pipeline look larger than it is.
- Drafts are never enqueued: `POST /api/jobs/{id}/evaluate`, `POST /api/jobs/reevaluate`, and the batch endpoint
  refuse a draft with 409 and the message "Add a job description before evaluating".

## 4. Ingest structure

```
backend/app/ingest/
  normalize.py            unchanged seam: content_hash, get_or_create_job
  csv_import.py           parse_csv, suggest_mapping, rows_from_mapping
  fetch/
    __init__.py           PROVIDERS registry, fetch_posting(url)
    base.py               JobContentProvider protocol, FetchedPosting, FetchError
    url_guard.py          scheme/host/IP validation, redirect walking, size and time caps
    robots.py             cached robots.txt lookups
    ats.py                Greenhouse, Lever, Ashby, Workable (public JSON APIs)
    html.py               generic readable-text extraction
    blocked.py            login-walled sites, refused by name
```

### 4.1 Provider interface (`fetch/base.py`)

```python
class FetchedPosting(BaseModel):
    company: str | None
    title: str | None
    location: str | None
    description: str            # may be "" → the caller creates a draft
    salary_text: str | None
    source: JobSource           # linkedin | indeed | company_site | other
    source_url: str
    provider: str               # "greenhouse" | "lever" | … | "html"
    confidence: Literal["structured", "extracted"]
    warnings: list[str]

class FetchError(Exception):
    def __init__(self, code: FetchErrorCode, message: str): ...

FetchErrorCode = Literal[
    "blocked_site", "robots_disallow", "unsupported_scheme", "private_address",
    "too_many_redirects", "not_found", "too_large", "timeout", "no_content", "upstream_error",
]

class JobContentProvider(Protocol):
    name: str
    def matches(self, url: ParseResult) -> bool: ...
    async def fetch(self, url: str, client: HttpFetcher) -> FetchedPosting: ...
```

`fetch_posting(url)` validates the URL (§6), then walks `PROVIDERS` in order — blocked sites, each ATS provider,
generic HTML last — and calls the first whose `matches` returns true. Every provider receives the same
`HttpFetcher`, which is the only component allowed to make outbound requests; it enforces the guard rules on
every hop so a provider cannot accidentally bypass them.

### 4.2 ATS providers (`fetch/ats.py`)

Each provider recognizes its URL shape, derives the public API endpoint, and maps the JSON response.

| Provider | URL shape | Public endpoint |
|----------|-----------|-----------------|
| Greenhouse | `boards.greenhouse.io/<board>/jobs/<id>`, `job-boards.greenhouse.io/<board>/jobs/<id>` | `https://boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>` |
| Lever | `jobs.lever.co/<org>/<id>` | `https://api.lever.co/v0/postings/<org>/<id>` |
| Ashby | `jobs.ashbyhq.com/<org>/<id>` | `https://api.ashbyhq.com/posting-api/job-board/<org>`, then the posting whose `id` matches `<id>` |
| Workable | `apply.workable.com/<org>/j/<code>` | `https://apply.workable.com/api/v1/accounts/<org>/jobs/<code>` |

Exact response shapes are pinned by recorded-response tests written against a real call during implementation; any mismatch raises `upstream_error`. Descriptions arrive as HTML and go through the same sanitizer as §4.3 so line segmentation (core §6.1) sees
clean text. `confidence` is `structured`; `source` is `company_site`.

If an ATS API returns 404 or an unexpected shape, the provider raises `upstream_error` rather than silently
falling back, so a mis-parsed page never becomes a job that looks trustworthy.

### 4.3 Generic HTML (`fetch/html.py`)

For any other public URL: parse with `selectolax`, then, in order of preference, take
(1) a JSON-LD `JobPosting` block (schema.org — many career pages ship one, giving real title, company, location,
and description), (2) `<main>` or the `<article>`/role-main subtree, (3) `<body>`. Remove `script`, `style`,
`nav`, `header`, `footer`, `form`, and elements whose class or id matches a small cookie/consent pattern list.
Convert block elements to newlines, collapse whitespace, and keep the text verbatim otherwise — evidence lines
must remain quotable (core §3, D3).

Title, company, and location come from JSON-LD when present, else from `og:title` / `<title>` heuristics, and
are returned as `None` when not found, so the user fills them in rather than being shown a guess. `confidence`
is `extracted`, and a warning names what could not be determined.

### 4.4 Blocked sites (`fetch/blocked.py`)

`linkedin.com`, `indeed.*`, `glassdoor.*`, and `ziprecruiter.com` raise `blocked_site` with:
"LinkedIn requires a login, so JobFit cannot fetch this posting. Open it in your browser, copy the description,
and use the Paste tab." No workaround is offered, implemented, or documented.

## 5. CSV import

### 5.1 Parsing (`ingest/csv_import.py`)

- Accept `.csv` and `.tsv`, at most 5 MB and 500 data rows; both limits return 413 with the actual count.
- Decode UTF-8 (BOM stripped) and fall back to Latin-1; sniff the delimiter among `, ; \t |`.
- Headers are required. Duplicate or blank headers are suffixed so mapping stays unambiguous.

### 5.2 Mapping

`suggest_mapping(columns)` matches each target field against a synonym list, case- and punctuation-insensitive:

| Field | Matches |
|-------|---------|
| `company` | company, employer, organisation/organization, firm |
| `title` | title, job title, role, position |
| `description` | description, job description, details, summary, body, text |
| `location` | location, city, place, where |
| `source_url` | url, link, job url, posting url, apply link |
| `salary_text` | salary, compensation, pay, salary range |
| `external_id` | id, job id, req id, requisition |

Unmatched fields map to `null`; `company` and `title` are required before import, `description` is optional
(missing means drafts). The user may change any mapping in the UI. Columns that map to nothing are ignored.

### 5.3 Commit

For each row, in file order: build `JobDraftIn`, trim and collapse whitespace, then reuse
`get_or_create_job` so content-hash dedupe (core §9) behaves exactly as for paste and batch. Results per row are
`created`, `duplicate`, `draft`, or `error` with a reason (missing company/title, unparseable URL, row too long).
Import is one transaction: any unexpected exception rolls the whole file back, so a half-imported file never
needs manual cleanup.

## 6. Network safety (`fetch/url_guard.py`, `fetch/robots.py`)

Applies to every outbound request, including each redirect hop and the `robots.txt` request itself:

1. Scheme must be `http` or `https`; no userinfo in the URL; no non-default ports other than 80/443/8080/8443.
2. The hostname is resolved; every returned address must be global — private, loopback, link-local (including
   `169.254.169.254`), unique-local, multicast, and reserved ranges are rejected with `private_address`.
3. Redirects are followed manually, at most 3, re-validating each `Location`; cross-scheme downgrades to http
   are refused.
4. 10-second total timeout; responses stream with a 2 MB cap (`too_large` beyond it); only HTML, JSON, and plain
   text content types are accepted.
5. No cookies are stored or sent, no `Authorization` header, no proxy support. User agent:
   `JobFitAI/0.1 (+local personal job tracker; respects robots.txt)`.
6. `robots.txt` is fetched once per host (cached in memory, 1-hour TTL, 200 hosts max) and evaluated with
   `urllib.robotparser` for our user agent. A disallowed path raises `robots_disallow`. A missing or unreadable
   `robots.txt` is treated as allowed; a `robots.txt` that is itself unreachable does not block the fetch.
7. One in-flight request per host, enforced by a per-host `asyncio.Lock`.

**Accepted limitation:** the host is resolved for validation and resolved again by the HTTP client, so a hostile
DNS server could answer differently between the two (DNS rebinding). Pinning the validated IP would mean a custom
transport and would break TLS hostname verification for redirects; for a local, single-user tool that only fetches
URLs the user pastes, the trade is not worth it. This is recorded here so it is a decision, not an oversight.

## 7. API

| method & path | behavior |
|---------------|----------|
| `POST /api/import/url` | Body `{url}`. Fetches and returns `{posting: FetchedPosting}` without storing anything. Errors map to 400 (`unsupported_scheme`, `private_address`), 403 (`blocked_site`, `robots_disallow`), 404 (`not_found`), 413 (`too_large`), 502 (`upstream_error`), 504 (`timeout`), each with a plain-language `detail`. |
| `POST /api/import/csv` | Multipart file. Returns `{columns, suggested_mapping, row_count, preview: rows[0:5], delimiter, encoding}`. Stores nothing. |
| `POST /api/import/csv/commit` | Body `{mapping, rows}` (rows echoed back from the preview step, ≤ 500). Returns `{created, duplicates, drafts, errors: [{row, reason}], job_ids}`. |
| `PATCH /api/jobs/{id}` | Body: any of company, title, description, location, salary_text, source, source_url, external_id. Draft only: 409 `"Evaluated jobs are immutable — create a new job instead"` when the job is `ready`. Recomputes `content_hash`; if the new hash already exists, returns 409 with the existing job's id. Promotes to `ready` when the description reaches 50 characters. |
| `GET /api/jobs` | Gains `status[]`; defaults to `ready`. Stats gain `drafts`. |

`POST /api/evaluate` keeps its current behavior for pasted postings and rejects drafts the same way as the other
evaluation endpoints.

## 8. Frontend

**`/jobs/new` becomes three tabs** (shadcn `Tabs`, remembered per session):

- **Paste** — today's form, unchanged.
- **From URL** — one URL field and a Fetch button. On success the same form fields fill in, above a badge that
  reads either "From the employer's job board API" (`structured`) or "Extracted from the page — check the fields"
  (`extracted`), plus any warnings. The user edits anything, then saves with the existing Save and evaluate
  button. On a blocked site or robots refusal, an inline message explains why and points at the Paste tab.
- **From CSV** — file picker → mapping table (one row per CSV column, a select per target field, guesses
  pre-filled, conflicts flagged) with a five-row preview → "Import N jobs". The result panel reports created,
  duplicate, and draft counts and lists row errors, with links to the imported jobs and to the drafts filter.

**Dashboard:** a Drafts toggle in the filter bar and a `drafts` stat tile that appears only when drafts exist.
Draft rows show "Needs description" in place of a score and cannot be selected for evaluation.

**Job detail, draft state:** the header shows a Draft badge; company, title, location, and description become
editable fields with a Save button; evaluation controls are disabled with the reason. Once saved with a
50+ character description, the page becomes the normal read-only detail view.

## 9. Testing

**Unit, offline (`make test`):**

- `url_guard`: localhost, `127.0.0.1`, `10.0.0.5`, `169.254.169.254`, `[::1]`, `file://`, `ftp://`, userinfo URLs,
  a redirect chain ending in a private address, a 4-hop chain, an oversized body, an unsupported content type.
- `robots`: allow, disallow, missing file, malformed file, cache reuse within TTL.
- ATS providers against saved API responses (one per provider), including a 404 and a malformed payload.
- HTML extractor against saved pages: a JSON-LD page, a plain page, one wrapped in a cookie banner, and a page
  with no readable content (`no_content`).
- CSV: BOM, semicolon and tab delimiters, quoted newlines, duplicate headers, missing required columns, 501 rows,
  synonym mapping for each field.
- Draft lifecycle: create draft → PATCH → promotion at 50 characters → evaluation allowed; PATCH on an evaluated
  job returns 409; drafts are excluded from stats and refused by every evaluation endpoint.

**API tests** use a stub provider registry, so no test in `make test` opens a socket.

**End-to-end (`make e2e`)**: upload a small CSV with one complete row and one description-less row, adjust one
mapping, import, see one job and one draft, open the draft, paste a description, save, evaluate with the fake
evaluator, and see it scored.

**Opt-in live check (`pytest -m live_http`, excluded by default):** fetch one real Greenhouse and one real Lever
posting and assert a non-empty description, so provider drift is detectable on purpose rather than by surprise.

## 10. Dependencies

`selectolax` (HTML parsing; small, no C++ toolchain) is added to the backend. CSV, `urllib.robotparser`,
`ipaddress`, and `socket` come from the standard library. `httpx2` already ships with the TypeSafe SDK and is
used for outbound fetches. No new frontend dependencies.

## 11. Build order

1. Draft status, migration, `PATCH /api/jobs/{id}`, evaluation refusals, dashboard `status` filter and stats.
2. CSV parse, mapping suggestions, preview and commit endpoints.
3. URL guard, robots, provider registry, ATS providers, HTML fallback, blocked sites, `POST /api/import/url`.
4. Frontend tabs, mapping UI, drafts on dashboard and detail.
5. End-to-end test, README and CLAUDE.md updates, core §15 amended to mark these Phase 2 items done.

## 12. Risks

| risk | mitigation |
|------|------------|
| ATS APIs change shape | One provider per site, each with a recorded-response test and an opt-in live check; failures raise `upstream_error` instead of producing a bad job. |
| Generic extraction yields noisy descriptions | Marked `extracted` in the UI, fields left blank rather than guessed, and the user reviews before saving. Evidence lines stay quotable because the text is not rewritten. |
| A user pastes a URL behind a login | Blocked-site list plus a clear message; `no_content` covers unknown login walls. |
| Importing many jobs tempts bulk evaluation | Import never evaluates; the UI shows what evaluation will cost before the user starts it. |
| Draft editing weakens posting immutability | Editing is allowed only before the first successful evaluation, enforced in the API and covered by tests. |
