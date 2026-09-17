# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Phase 1 implemented (plans in `docs/superpowers/plans/`). The approved design is
`docs/superpowers/specs/2026-09-17-jobfit-ai-design.md` ("spec §N" below) and is the source of truth.
If a design decision changes, update the spec in the same change. Phase 2/3 need their own spec and plan.

JobFit AI is a local, single-user job-posting evaluator: resume/profile + job posting → TypeSafe System
One typed signals → deterministic scorer → ranked dashboard. FastAPI backend (`backend/`, uv) + Next.js
frontend (`frontend/`, proxies `/api/*` to FastAPI), SQLite via SQLAlchemy 2 + Alembic.

## Commands

- `make setup` · `make dev` (uvicorn `--factory app.main:create_app` single process + `next dev`) · `make test` (backend pytest, no network + frontend `tsc`/ESLint/`next build`) · `make e2e` (Playwright smoke, fake evaluator, ports 8010/3010) · `make seed` · `make types` · `make screenshots` · `make migrate`
- Single backend test: `cd backend && uv run pytest tests/<path>/test_x.py::test_name`
- Live golden set: `make test-live` replays `backend/tests/live/cassettes/` (skips when none); `make test-live ARGS=--record` needs `TYPESAFE_API_KEY` + `TYPESAFE_MODEL`. Committed cassettes may only contain `SAMPLE_RESUME`.
- `EVALUATOR=fake` runs everything without an API key. Fixtures live in `backend/app/semantic/fake_fixtures.py` and are chosen by `external_id` `fixture:<name>` or by pasting a fixture's exact sample posting.
- Backend scripts run as modules: `uv run python -m scripts.seed_demo`, `uv run python -m scripts.export_openapi`.
- The app runs Alembic migrations on startup; after changing `app/models.py`, add a revision (`uv run alembic revision --autogenerate`) — `tests/api/test_migrations.py` fails on drift.

## Frontend notes

- Next.js 16 (read `frontend/node_modules/next/dist/docs/` before using unfamiliar APIs): `params` are async (client pages use `useParams`), `useSearchParams` needs a `<Suspense>` boundary, `next lint` is gone (use `npm run lint`).
- TanStack Table is **v9** (`useTable` + `tableFeatures`, not v8 `useReactTable`); sorting/filtering are server-side via URL params.
- API types are generated: change backend response models in `backend/app/api/schemas.py`, then `make types`; never hand-edit `frontend/src/lib/api/schema.d.ts`.
- Colors come from tokens in `globals.css` (`--brand`, `--status-*`); status color is for status badges only, bars use `--brand`.

## Architecture invariants (span many files — keep them true)

- **The score never comes from a model.** TypeSafe only answers typed Choice/Score/Noul questions. `backend/app/scoring/` is pure code (no I/O, no AI); weights, penalties, blocker rules, and thresholds live in a versioned `ScoringConfig` (spec §7).
- **Only `backend/app/semantic/typesafe_evaluator.py` imports `typesafe_sdk`.** Everything else uses the `JobSemanticEvaluator` protocol. `FakeJobSemanticEvaluator` picks fixtures by job `external_id` (`fixture:<name>`). `app/scoring/` may not import `app.semantic`/db/api — `tests/unit/test_boundaries.py` enforces both rules.
- **Two TypeSafe states:** `job` (posting only) for job-intrinsic questions; `fit` (posting + resume + preferred roles/locations) for candidate-fit questions. Blocker facts, work-authorization notes, and scoring-only preferences are never sent to TypeSafe — a unit test enforces this.
- **Evidence is a Choice over JD line IDs (`L000`…) plus `none`**, so snippets are always verbatim posting lines. Consequences: job postings are immutable after creation (edit = new job), and segmentation caps at 254 lines.
- **Bump `EVALUATOR_VERSION` when changing question wording, state format, segmentation, or parsing** — a test pins `catalog_hash` per version. `TYPESAFE_MODEL` is pinned, never `jev-latest`.
- **Re-scoring is free; re-evaluation costs API calls.** Profile edits create immutable profile versions. Scoring-only preference or config changes re-score stored signals; semantic fields (resume, preferred roles/locations, technologies, tracked skills) require re-evaluation. Evaluations and fit results are append-only history.
- **Fit score and confidence are never combined, and confidence never changes status.** Noul answers carry no confidence from the API; code derives `|2p−1|` and labels it as derived.
- **Hard blockers need both** an explicit posting signal at or above the blocker threshold **and** an explicitly set profile fact; otherwise at most a "verify" concern. `work_authorization_signal = not_stated` is never treated as sponsorship available.
- **The evaluation worker is an in-process asyncio queue** — run a single uvicorn process.

## Working with TypeSafe

- Read the live docs before touching the integration: index at `https://docs.typesafe.ai/llms.txt`; any page as Markdown by appending `.md`. Official agent skill: `typesafe-ai/skills` (`skills/typesafe-ai/SKILL.md`).
- Limits the design relies on: ~32k tokens per request shared by state and questions (the request packer keeps estimates under `TYPESAFE_TOKEN_BUDGET`); Choice ≤ 255 options; Score 2–10 levels, each written as a standalone concrete situation (the model never sees level numbers).
- `typesafe-sdk` is pinned to `0.6.*` (0.x with recent breaking changes).
- SDK `debug` logging prints full request bodies, including the resume — keep `TYPESAFE_LOG_LEVEL` at `warning`, and never log resume text or blocker facts.
