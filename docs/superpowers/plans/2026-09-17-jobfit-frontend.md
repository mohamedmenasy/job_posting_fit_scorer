# JobFit AI Frontend, Golden Set, Seed & Docs Implementation Plan (Plan B of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase 1: typed API contract, seed script, live golden set with record/replay cassettes, the Next.js UI (dashboard, new job, job detail, profile, settings), a Playwright smoke test of the definition-of-done flow, and the README.

**Architecture:** Backend gains Pydantic response models so FastAPI's OpenAPI schema fully describes responses; `make types` exports it and `openapi-typescript` generates `frontend/src/lib/api/schema.d.ts` (committed). The frontend is a client-rendered Next.js App Router app: TanStack Query hooks over an `openapi-fetch` client; the browser only calls same-origin `/api/*`, which `next.config.ts` rewrites to `BACKEND_URL`.

**Tech Stack:** Next.js 16.3 (Turbopack default, React 19.2, async `params`, `useSearchParams` requires a `<Suspense>` boundary, `next lint` removed → `eslint`), TypeScript strict, Tailwind v4 (CSS-first), shadcn/ui 4 (`radix` base, lucide icons, `next-themes`, `sonner`), TanStack Query 5 + Table 8, openapi-typescript 7 + openapi-fetch 0.17, Playwright 1.63. Backend: existing Plan A stack.

**Spec:** `docs/superpowers/specs/2026-09-17-jobfit-ai-design.md` — §11 (frontend), §13.3 (live golden set), §13.4 (frontend checks), §14 (Makefile), §15 step 8 (README contents).

## Global Constraints

- `TYPESAFE_API_KEY` never reaches the frontend: no `NEXT_PUBLIC_*` variables; `BACKEND_URL` is read only in `next.config.ts` (server side), default `http://127.0.0.1:8000`.
- Visual direction (§11): dense productivity tool; neutral grayscale + one accent; status colors strong green, good teal, review amber, low gray, blocked red; `tabular-nums` for numbers; light and dark themes; no gradients, no sparkles; transitions ≤ 150 ms. Keyboard: `/` focuses search, `n` opens New job.
- Fit score and confidence are always shown as separate values; Noul-derived confidence is labeled "derived".
- Blocker facts UI copy: "Stored locally; never sent to TypeSafe".
- Next 16 docs live in `frontend/node_modules/next/dist/docs/`; read the relevant page before using an API not listed here.
- Committed live cassettes may only contain the synthetic sample resume.
- All backend commands run from `backend/` with `uv run`; frontend from `frontend/` with `npm`.

## File structure

```
backend/
  app/api/schemas.py              response models (JobOut, FitResultOut, EvaluationOut, JobDetailOut, JobListOut, ...)
  app/semantic/fake_fixtures.py   + SAMPLE_RESUME, DEMO_PREFERENCES
  scripts/export_openapi.py       prints create_app().openapi() JSON
  scripts/seed_demo.py            demo profile + eight fixture jobs via fake evaluator
  tests/api/test_openapi.py  tests/api/test_seed.py
  tests/live/conftest.py          --record option, CassetteTransport
  tests/live/test_golden.py       eight postings → real evaluator, signal-range assertions
  tests/live/cassettes/           <sha256>.json (committed after recording)
  tests/unit/test_cassettes.py    replay/record/missing-cassette behavior without network
frontend/
  next.config.ts  eslint.config.mjs  playwright.config.ts  e2e/smoke.spec.ts
  src/app/{layout,providers,page}.tsx  globals.css
  src/app/jobs/new/page.tsx  src/app/jobs/[id]/page.tsx  src/app/profile/page.tsx  src/app/settings/page.tsx
  src/components/ui/*             shadcn components
  src/components/app-shell.tsx    top nav, theme toggle, global shortcuts
  src/components/common.tsx       StatusBadge, ConfidenceBadge, ScoreBar, EvaluationStateIcon, Section, EmptyState
  src/components/tag-input.tsx  src/components/multi-select.tsx
  src/components/dashboard/{stat-strip,filter-bar,jobs-table}.tsx
  src/components/job/{job-header,why-apply,fit-overview,classification,skills,blockers,work-auth,signals-table,posting,history}.tsx
  src/lib/api/schema.d.ts (generated)  src/lib/api/client.ts  src/lib/api/hooks.ts
  src/lib/format.ts               labels, percent, confidence band, status color classes
Makefile  README.md  docs/screenshots/*.png
```

---

### Task 1: Typed API responses and OpenAPI export

**Files:** Create `backend/app/api/schemas.py`, `backend/scripts/export_openapi.py`, `backend/tests/api/test_openapi.py`; Modify every router to declare `response_model`.

**Produces (response models, all `BaseModel`):**
- `JobOut` (job columns), `FitResultOut(JobFitResult)` + `id, evaluation_id, profile_version_id, scoring_config_id, scoring_config_version, created_at`, `EvaluationOut` (evaluation columns + `fit_results: list[FitResultOut] = []`), `EvaluationDetailOut(EvaluationOut)` + `signals: SemanticSignalsOut | None, raw_typesafe_response: list[RequestMeta] | None` where `SemanticSignalsOut` = `SemanticJobEvaluation` without `requests`.
- `JobDetailOut {job, fit_result, evaluation: EvaluationDetailOut | None, latest_evaluation: EvaluationOut | None}`; `JobRowOut`; `JobStatsOut`; `JobListOut {rows, total_filtered, stats}`; `CreateJobOut {job, created}`; `BatchOut`; `EnqueuedOut {evaluation_id, status}`; `EvaluationIdsOut`; `EvaluatePostingOut {job, evaluation_id, created, reused}`; `ProfileOut(CandidateProfile)`; `ProfileSaveOut {profile, change_kind, affected_jobs, rescored}`; `ResumeTextOut`; `ScoringSettingsOut {version, config: ScoringConfig, defaults: ScoringConfig}`; `RescoreOut {version, rescored}`; `MetaOut {enums: dict[str, list[EnumOption]], default_tracked_skills, evaluator_version, model}`; `HealthOut`; `RequestRebuildOut`.

- [ ] **Step 1: Failing test**

```python
from app.main import create_app


def test_openapi_describes_responses():
    spec = create_app().openapi()
    schemas = spec["components"]["schemas"]
    for name in ["JobDetailOut", "JobListOut", "FitResultOut", "ProfileSaveOut", "ScoringSettingsOut", "MetaOut",
                 "EvaluatePostingOut", "SemanticSignalsOut"]:
        assert name in schemas
    detail = spec["paths"]["/api/jobs/{job_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert detail == {"$ref": "#/components/schemas/JobDetailOut"}
```

- [ ] **Step 2:** FAIL. **Step 3:** implement; routers keep returning dicts, FastAPI validates them against `response_model`. `export_openapi.py`: `print(json.dumps(create_app().openapi(), indent=2))`. **Step 4:** `uv run pytest` → all pass (Plan A API tests prove the dicts satisfy the models). **Step 5:** commit `feat(api): typed response models for OpenAPI`.

---

### Task 2: Sample resume and seed script

**Files:** Modify `backend/app/semantic/fake_fixtures.py`; Create `backend/scripts/seed_demo.py`, `backend/tests/api/test_seed.py`

**Produces:** `SAMPLE_RESUME: str` (synthetic Staff Android engineer, ~25 lines, no real person); `DEMO_PREFERENCES: dict` (preferred roles "Staff Android Engineer", "Mobile Tech Lead"; levels staff/principal; families android_native/kotlin_multiplatform; avoided flutter; domains fintech/healthcare; remote; ic; years 11); `seed(database_url: str) -> dict` returning `{"profile_created": bool, "created": int, "existing": int}` — runs `create_app(Settings(evaluator="fake", database_url=...))` in a `TestClient`, `PUT /api/profile` (blocker facts: needs sponsorship true, clearance false), `POST /api/jobs/batch` with the eight fixture postings (`external_id=fixture:<name>`, `source` varied), waits for evaluations. CLI: `uv run python scripts/seed_demo.py` uses `Settings().database_url`.

- [ ] **Step 1: Failing test**

```python
from fastapi.testclient import TestClient

from app.main import create_app
from scripts.seed_demo import seed
from tests.conftest import make_settings


def test_seed_is_idempotent_and_evaluates_all(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    assert seed(url) == {"profile_created": True, "created": 8, "existing": 0}
    assert seed(url) == {"profile_created": False, "created": 0, "existing": 8}
    with TestClient(create_app(make_settings(tmp_path))) as client:
        data = client.get("/api/jobs").json()
        assert data["stats"]["evaluated"] == 8 and data["stats"]["blocked"] >= 2
```

(`backend/scripts/__init__.py` makes the import work; `pyproject` pytest `pythonpath = ["."]` if needed.)

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(backend): demo seed script`.

---

### Task 3: Live golden set with record/replay cassettes

**Files:** Create `backend/tests/live/__init__.py`, `backend/tests/live/conftest.py`, `backend/tests/live/test_golden.py`, `backend/tests/unit/test_cassettes.py`, `backend/tests/cassette.py`

**Produces (`tests/cassette.py`):** `class CassetteTransport(httpx2.AsyncBaseTransport)`: `__init__(self, directory: Path, record: bool, inner: httpx2.AsyncBaseTransport | None = None)`; key = sha256 of the canonical request JSON body **with `model` kept** (so a model change invalidates cassettes); replay reads `<key>.json` `{"status", "headers": {"x-typesafe-request-id"}, "body"}`; missing cassette in replay mode raises `CassetteMissing` (tests turn it into `pytest.skip`); record mode forwards to `inner` (default `httpx2.AsyncHTTPTransport()`), writes the cassette, returns the response.

**live conftest:** `pytest_addoption("--record")`; fixture `evaluator` → `TypeSafeJobSemanticEvaluator(api_key or "replay", model=os.environ.get("TYPESAFE_MODEL", "<pinned-in-cassettes>"), budget=24000, Semaphore(4), transport=CassetteTransport(dir, record))`; recording without `TYPESAFE_API_KEY`/`TYPESAFE_MODEL` → `pytest.fail` with a clear message. Replay needs no key. The pinned model name used when replaying is stored in `tests/live/cassettes/MODEL` (written on record).

**test_golden.py** (all `@pytest.mark.live`), profile = `make_profile(resume_text=SAMPLE_RESUME, **DEMO_PREFERENCES)`, job from `FIXTURES[name]["posting"]`, assertions (§13.3):
- `clearance_required`: `security_clearance_required.probability >= 0.8`; evidence line text contains "clearance".
- `gov_contractor_no_clearance`: `security_clearance_required.probability <= 0.2`.
- `no_sponsorship_info`: `work_authorization_signal.value == "not_stated"`.
- `explicit_no_sponsorship`: value `explicit_no_sponsorship`; evidence text contains "sponsorship".
- `flutter_heavy`: `cross_platform_intensity.score >= 3`.
- `engineering_manager`: `management_intensity.score >= 3`.
- `staff_title_senior_scope`: `title_level.value == "staff"` and `seniority.value == "senior"`.
- `android_staff_perfect`: `android_relevance.score >= 3` and `role_family.value == "android_native"`.
- Each test prints estimated vs actual input tokens and latency per request (`capsys`-visible via `-s`).

- [ ] **Step 1: Failing unit test** (`tests/unit/test_cassettes.py`, no network):

```python
import json
import httpx2, pytest
from tests.cassette import CassetteMissing, CassetteTransport


async def test_record_then_replay(tmp_path):
    inner = httpx2.MockTransport(lambda r: httpx2.Response(200, json={"ok": True}, headers={"x-typesafe-request-id": "r1"}))
    body = {"model": "m", "state": {"a": 1}, "questions": {}}
    async with httpx2.AsyncClient(transport=CassetteTransport(tmp_path, record=True, inner=inner)) as c:
        assert (await c.post("https://x/v1/systemone", json=body)).json() == {"ok": True}
    async with httpx2.AsyncClient(transport=CassetteTransport(tmp_path, record=False)) as c:
        r = await c.post("https://x/v1/systemone", json=body)
        assert r.json() == {"ok": True} and r.headers["x-typesafe-request-id"] == "r1"
        with pytest.raises(CassetteMissing):
            await c.post("https://x/v1/systemone", json={**body, "model": "other"})
```

- [ ] **Step 2–4:** FAIL → implement → PASS; `uv run pytest -m live` → 8 skipped (no cassettes) with reason "no cassette; run make test-live ARGS=--record with TYPESAFE_API_KEY".
- [ ] **Step 5:** Makefile `test-live: cd backend && uv run pytest -m live $(ARGS)`. Commit `test(live): golden set with record/replay cassettes`.

---

### Task 4: Frontend scaffold, API client, app shell

**Files:** `frontend/*` scaffold; Create `src/app/providers.tsx`, `src/components/app-shell.tsx`, `src/components/common.tsx`, `src/lib/api/client.ts`, `src/lib/api/hooks.ts`, `src/lib/format.ts`; Modify `next.config.ts`, `src/app/layout.tsx`, `src/app/globals.css`, `Makefile`, root `.gitignore`

- [ ] **Step 1: Scaffold**

```bash
npx -y create-next-app@16.3.5 frontend --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm --yes
cd frontend && rm -rf .git
npx -y shadcn@4.21.0 init -d -b radix --no-monorepo --no-rtl
npx -y shadcn@4.21.0 add button badge input textarea select table tabs switch label card separator tooltip dialog dropdown-menu popover command checkbox sonner skeleton scroll-area alert-dialog -y
npm i @tanstack/react-query @tanstack/react-table openapi-fetch
npm i -D openapi-typescript @playwright/test
```

Remove any stray dependency shadcn adds that nothing imports (verify with `grep -r`).

- [ ] **Step 2: Config**
  - `next.config.ts`: `async rewrites() { return [{ source: "/api/:path*", destination: \`${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/api/:path*\` }] }`.
  - `tsconfig.json` already `strict`; add `"noUncheckedIndexedAccess": true`.
  - `package.json` scripts: `"typecheck": "tsc --noEmit"`, `"types": "openapi-typescript ../backend/openapi.json -o src/lib/api/schema.d.ts"`, `"e2e": "playwright test"`.
  - Root `Makefile`: `setup` adds `cd frontend && npm ci`; `dev` runs backend and `cd frontend && npm run dev` together (`trap 'kill 0' EXIT; ... & ...; wait`); `test` adds `cd frontend && npm run typecheck && npm run lint && npm run build`; `types` = `cd backend && uv run python scripts/export_openapi.py > openapi.json && cd ../frontend && npm run types && rm ../backend/openapi.json`; `seed` = `cd backend && uv run python scripts/seed_demo.py`; `e2e` = `cd frontend && npm run e2e`.
- [ ] **Step 3: API layer** — `client.ts`: `export const api = createClient<paths>({ baseUrl: "" })` and `export async function unwrap<T>(p: Promise<{data?: T; error?: unknown; response: Response}>): Promise<T>` that throws `ApiError(status, detail)` (detail string from FastAPI `{"detail"}`; 422 arrays joined as `loc: msg`). `hooks.ts`: `useMeta`, `useHealth`, `useProfile` (404 → `null`), `useSaveProfile`, `useExtractResume`, `useJobs(params)` (`placeholderData: keepPreviousData`, `refetchInterval` 2000 ms while any row is pending/running), `useJob(id)` (`refetchInterval` 1000 ms while `latest_evaluation.status` is pending/running), `useEvaluations(jobId)`, `useEvaluatePosting`, `useReevaluate(jobId)`, `useReevaluateMany`, `useDeleteJob`, `useScoringSettings`, `useSaveScoring`. Mutations invalidate `["jobs"]`, `["job", id]`, `["profile"]`, `["scoring"]` as relevant and toast via `sonner`.
- [ ] **Step 4: Shell** — `providers.tsx` (`"use client"`: `QueryClientProvider`, `ThemeProvider attribute="class" defaultTheme="system"`, `Toaster`); `layout.tsx` wraps children in `Providers` + `AppShell` (brand "JobFit AI", links Dashboard · New job · Profile · Settings, theme toggle, health dot showing evaluator + model with tooltip); `app-shell.tsx` global `keydown`: `/` focuses `#job-search` when present (ignored while typing in inputs), `n` → `router.push("/jobs/new")`. `globals.css`: status color tokens `--status-strong/good/review/low/blocked` for light & dark, `--accent` single indigo, `* { transition-duration: ≤150ms }` via Tailwind defaults (`duration-150`), body `font-variant-numeric: tabular-nums` on `.tabular`.
- [ ] **Step 5:** `format.ts`: `pct(x)` → `"82%"`, `score(x)` → `"93"`, `band(conf)` → `"accepted"|"review"|"uncertain"` (0.8/0.6), `STATUS_LABEL`, `statusClass(status)`, `bandClass(band)`, `enumLabel(meta, enumName, value)`.
- [ ] **Step 6:** `make types`, then `npm run typecheck && npm run lint && npm run build` → all succeed. Commit `feat(frontend): scaffold, typed API client, app shell`.

---

### Task 5: Profile page

**Files:** Create `src/app/profile/page.tsx`, `src/components/tag-input.tsx`, `src/components/multi-select.tsx`

**Behavior (§11.1 /profile):**
- Loads `useProfile` + `useMeta`; empty profile starts with `meta.default_tracked_skills`.
- Resume: textarea + file input (`accept=".pdf,.docx,.txt"`) → `POST /api/profile/resume/extract` (multipart via `fetch` + `FormData`) → replaces textarea content; toast "Resume text extracted — review before saving".
- Preferences: `TagInput` (Enter/comma adds, Backspace removes, chip × removes) for preferred roles, preferred locations, required/preferred/avoid technologies; `MultiSelect` (popover + command list + checkboxes) for preferred levels, preferred/avoided role families, preferred domains; `Select` for remote preference and management preference; `Switch` willing to relocate; number input years of experience; textarea work authorization notes ("Display only").
- Blocker facts: three tri-state segmented controls Yes / No / Not set; section caption "Stored locally; never sent to TypeSafe".
- Tracked skills editor: rows of id / label / description inputs, add row, delete row, "Reset to defaults".
- Every field label has a hint chip: "instant re-score" (scoring-only fields, blocker facts) or "needs re-evaluation" (resume, roles, locations, technologies, tracked skills).
- Save → `PUT /api/profile`; 422 → toast with detail; success toast: `none` → "No changes"; else "Profile saved · re-scored N jobs", and for `semantic` with `affected_jobs > 0` the toast has action "Re-evaluate N jobs" → `POST /api/jobs/reevaluate {}`.
- Sticky footer with Save button, disabled while pending; unsaved-changes dot.

- [ ] **Step 1:** implement. **Step 2:** `npm run typecheck && npm run lint`. **Step 3:** manual check with `make dev` + `EVALUATOR=fake`: save profile, reload, values persist. **Step 4:** commit `feat(frontend): profile editor`.

---

### Task 6: New job and job detail pages (vertical slice)

**Files:** Create `src/app/jobs/new/page.tsx`, `src/app/jobs/[id]/page.tsx`, `src/components/job/*.tsx`

**`/jobs/new`:** two-column layout (description textarea first, ~70% width, `autoFocus`, min 50 chars counter; right column company, title, location, URL, salary, source `Select`). No profile → inline notice linking to Profile, submit disabled. "Save & evaluate" → `POST /api/evaluate` → `router.push(/jobs/{job.id})`; toast "Existing evaluation reused" when `reused`.

**`/jobs/[id]`** (`"use client"`, `useParams`): sticky left section nav (IntersectionObserver highlights current); sections in §11.1 order:
1. `JobHeader`: title, company · location · source link; big score + `StatusBadge`; `ConfidenceBadge` (% + band color); "Review recommended" badge when `needs_review`; stale badge; actions Re-evaluate, Delete (`AlertDialog` confirm → dashboard). While latest evaluation pending/running: spinner banner "Evaluating…"; failed: error banner with Retry.
2. `WhyApply`: ✓ strengths, △ concerns, ⛔ hard blockers ("None detected"); each item shows confidence and, when `evidence_line_id`, a link that scrolls to and flashes the line in section 9.
3. `FitOverview`: per component a horizontal bar (value), label `x/4` for score-backed components (technical, android, seniority, domain: value × 4; role_preference: value × 3), weight → effective %, contribution points, n/a reason dimmed; penalties list `−points reason`; base → penalties → overall line.
4. `Classification`: grid of role family, level (title vs scope), domain, work arrangement, KMP, years required, Staff IC signal (derived) — each `value · ConfidenceBadge`.
5. `Skills`: missing skills grouped by importance (tracked skill: label + mapped line quotes; requirement line: quoted text) with evidence + impact chips; then skill matches table (skill, requirement, match %, confidence, lines).
6. `Blockers`: hard and possible blockers with confidence and evidence quote.
7. `WorkAuth`: sponsorship signal, clearance, citizenship, relocation — probability/confidence and evidence line ("No supporting line found" when absent or < 0.5).
8. `SignalsTable`: every signal from `evaluation.signals` (value/score/probability, confidence band, "derived" tag for Nouls); row expands to probabilities; "Raw JSON" dialog showing `raw_typesafe_response` (fetched lazily from `GET /api/evaluations/{id}`); request metadata (model, tokens, latency, request IDs).
9. `Posting`: `all_lines` with line IDs in a gutter; lines cited by evidence or explanations highlighted; hover tooltip lists citing signals.
10. `History`: `useEvaluations(jobId)` table — date, evaluator version, model, profile version (short id), config version, score, status.

- [ ] **Step 1:** implement. **Step 2:** typecheck + lint + build. **Step 3:** manual vertical-slice check against `EVALUATOR=fake` backend with the seeded DB: paste the `clearance_required` posting text, land on detail, see BLOCKED + evidence quote. **Step 4:** commit `feat(frontend): new job and job detail pages`.

---

### Task 7: Dashboard

**Files:** Modify `src/app/page.tsx`; Create `src/components/dashboard/{stat-strip,filter-bar,jobs-table}.tsx`

- `page.tsx` renders `<Suspense fallback={<Skeleton/>}><Dashboard/></Suspense>` (required by `useSearchParams`).
- URL is the filter state: `useSearchParams` → params object (multi-value keys via `getAll`); updates via `router.replace(\`?${qs}\`, { scroll: false })`; search input debounced 250 ms.
- `StatStrip`: Jobs evaluated · Strong matches · Good matches · Need review · Blocked — clicking sets `status` (Need review sets `needs_review=true`); active tile highlighted.
- `FilterBar`: search (`id="job-search"`), min score, status, company, role family, seniority, min Android relevance (0–4), KMP, domain, work arrangement, clearance required, sponsorship signal, source, needs review; "Clear" button; option labels from `useMeta`.
- `JobsTable` (TanStack Table, manual sorting mapped to API `sort`/`order`; columns without an API sort key are not sortable): Score (number + compact bar) · Company · Role · Level · Platform · Location · Work type · Domain · Confidence (% band color) · Status (badge; spinner pending/running; error icon + tooltip failed). Row click → `/jobs/[id]`. Pagination 100 per page with prev/next.
- Empty states: no profile → card "Create your profile" → `/profile`; no jobs → "Add job" → `/jobs/new`; filters exclude everything → "No jobs match these filters" + Clear.

- [ ] **Step 1:** implement. **Step 2:** typecheck + lint + build. **Step 3:** manual check with seeded DB: sort by company, filter Blocked, URL reload keeps filters, `/` focuses search, `n` opens new job. **Step 4:** commit `feat(frontend): dashboard`.

---

### Task 8: Settings page

**Files:** Create `src/app/settings/page.tsx`

- Loads `useScoringSettings`; local draft state.
- Weights: number inputs + normalized % (weight / Σ weights) per component.
- Penalties: per penalty toggle, trigger fields, points.
- Blocker rules: threshold, possible threshold, per-rule toggles, technology mismatch probabilities, seniority steps.
- Status thresholds, confidence bands, evidence minimum probability, missing-skill probabilities, neutral platform preference, domain blend, relocation factor.
- Arrangement matrix: 3×5 grid of number inputs (0–1).
- "Save & re-score" → `PUT /api/settings/scoring` → toast "Saved version N · re-scored M jobs (no API calls)"; 422 detail toast. "Reset to defaults" loads `defaults` into the draft (not saved until Save).

- [ ] **Step 1:** implement. **Step 2:** typecheck + lint + build. **Step 3:** manual: raise strong threshold to 99, save, dashboard statuses change. **Step 4:** commit `feat(frontend): scoring settings`.

---

### Task 9: Playwright smoke, README, screenshots, final verification

**Files:** Create `frontend/playwright.config.ts`, `frontend/e2e/smoke.spec.ts`, `frontend/e2e/screenshots.spec.ts`, `README.md`, `docs/screenshots/*.png`; Modify `Makefile`, root `CLAUDE.md`, spec §14 if commands changed

- `playwright.config.ts`: `webServer` array — backend `uv run uvicorn --factory app.main:create_app --port 8010` with env `EVALUATOR=fake`, `DATABASE_URL=sqlite:///<tmp>/e2e.db` (deleted in `globalSetup`), cwd `../backend`; frontend `npm run dev -- --port 3010` with `BACKEND_URL=http://127.0.0.1:8010`. `use.baseURL = http://127.0.0.1:3010`. Chromium only.
- `smoke.spec.ts` (definition of done): open `/profile`, fill resume, set "can meet clearance requirement" = No, Save → toast; open `/jobs/new`, paste the `clearance_required` posting (company/title/description), Save & evaluate → detail page shows `Blocked` badge and the clearance evidence quote; dashboard shows the row with status Blocked; stat "Blocked" = 1.
- `screenshots.spec.ts` (tagged `@screenshots`, excluded from default run): seeds via `POST /api/profile` + `POST /api/jobs/batch` with the eight fixtures, captures dashboard, job detail, profile, settings (light theme, 1440×900) into `../docs/screenshots/`.
- `README.md` (§15 step 8): purpose; why TypeSafe; semantic vs deterministic split; Mermaid architecture (§4.1); setup (`make setup`, `.env`, choose model via `client.models.list()`); env vars table (§14); scoring formula (§7.1–7.5 condensed); TypeSafe dimensions table (every signal, primitive, levels/options, state); tests (`make test`, `make test-live`, `--record`, `make e2e`); screenshots; single-process note; privacy notes; future integrations (Phase 2/3).
- Makefile: `e2e`, `screenshots` targets; `test` stays network-free.
- Final: `make test` (backend + frontend checks) and `make e2e` pass; update root `CLAUDE.md` Status/Commands to real commands. Commit `feat: Playwright smoke test and README`.
