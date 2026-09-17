# JobFit AI Backend Implementation Plan (Plan A of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Phase 1 FastAPI backend: domain models, TypeSafe semantic layer (real + fake evaluator), deterministic scorer, SQLite persistence, in-process evaluation worker, and the full `/api` surface.

**Architecture:** `ingest` → `semantic` (segment, states, catalog, packer, parser; only `typesafe_evaluator.py` imports `typesafe_sdk`) → `scoring` (pure functions over `SemanticJobEvaluation` + profile + `ScoringConfig`) → `pipeline` (asyncio queue, persistence, re-scoring) → `api`. Sync SQLAlchemy sessions (SQLite is local and fast); only the evaluator call is async.

**Tech Stack:** Python 3.13, uv, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2, Alembic, `typesafe-sdk==0.6.*`, pypdf, python-docx, pytest + pytest-asyncio, httpx (TestClient).

**Spec:** `docs/superpowers/specs/2026-09-17-jobfit-ai-design.md` ("§N" below). Read the referenced section before each task; exact question wording, formulas, thresholds, and templates are copied verbatim from it.

**Plan B** (separate file, written after Plan A lands): frontend (§11), live golden set (§13.3), seed script, Playwright smoke, README, `make types`.

## Global Constraints

- Python 3.13; `typesafe-sdk==0.6.*`; `TYPESAFE_MODEL` pinned (never `jev-latest`).
- Only `backend/app/semantic/typesafe_evaluator.py` imports `typesafe_sdk` (a unit test greps for it).
- The score never comes from a model: `backend/app/scoring/` has no I/O and imports nothing from `semantic` except domain types.
- Blocker facts, `work_authorization_notes`, and scoring-only preferences never appear in any TypeSafe state.
- Resume text, preferences text, blocker facts are never logged. `TYPESAFE_LOG_LEVEL` default `warning`; API key is `SecretStr`.
- Portable column types only (`Uuid`, `JSON`, `Float`, `String`, `Text`, `Boolean`, `DateTime(timezone=True)`); SQLite WAL.
- Errors use FastAPI `{"detail": ...}`.
- FastAPI bound to `127.0.0.1`; single uvicorn process.
- All commands run from `backend/` with `uv run`.

## SDK facts (verified by reading `typesafe-sdk` 0.6.0 source)

- `AsyncTypeSafeClient(api_key=, model=, retry=RetryPolicy(...), timeout=float, transport=httpx2.AsyncBaseTransport)`; `await client.system_one(state, questions, model=...)`.
- Questions may be plain dicts: `{"type": "choice", "instructions": ..., "criteria": {label: desc|None}}`, `{"type": "score", "instructions": ..., "criteria": [level0, ...]}`, `{"type": "noul", "instructions": ..., "criteria": {"true": ..., "false": ...}}`.
- Response: `.model`, `.usage.input_tokens/output_tokens`, `.answers: dict[str, ChoiceAnswer|ScoreAnswer|NoulAnswer]`, `.request_id` (raises if header absent), `.raw_http_response` (`httpx2.Response`). `ScoreAnswer.probabilities` is `dict[int, float]`.
- Errors: `TypeSafeError` base; `TypeSafeAPIError(.status, .request_id)`; `TypeSafeAPIConnectionError`.
- The SDK uses `httpx2` (not `httpx`), so fake transports in tests use `httpx2.MockTransport`.

## File structure

```
Makefile                                  setup/dev/test/migrate (backend targets; Plan B adds frontend)
.gitignore
backend/
  pyproject.toml  .env.example  alembic.ini
  alembic/env.py  alembic/versions/0001_initial.py
  app/
    main.py            create_app(settings) + lifespan (migrate, default config, worker start, re-queue)
    config.py          Settings
    logging.py         JsonFormatter, configure_logging(settings)
    db.py              make_engine(url), make_session_factory(engine), Base
    models.py          ORM tables (§8)
    domain.py          enums + Pydantic models (§5) + hashing helpers
    repo.py            current_profile(), active_config(), headline_columns()
    ingest/normalize.py        content_hash(), get_or_create_job()
    semantic/evaluator.py      JobSemanticEvaluator Protocol, SemanticEvaluationError
    semantic/lines.py          segment(), eligible_ids(), SEGMENTATION_VERSION
    semantic/state.py          build_job_state(), build_fit_state()
    semantic/catalog.py        Q, build_questions(), EVALUATOR_VERSION, catalog_hash(), question_set_hash(), tech_slug()
    semantic/packer.py         estimate_tokens(), pack(), PostingOrResumeTooLong
    semantic/parser.py         parse_answers(), MalformedTypeSafeResponse
    semantic/typesafe_evaluator.py
    semantic/fake_evaluator.py
    semantic/fake_fixtures.py  eight §13.1 fixtures as Python builders
    scoring/config.py  components.py  penalties.py  blockers.py  confidence.py  skills.py  explain.py  scorer.py
    pipeline/worker.py         EvaluationWorker, rescore_all()
    api/profile.py  jobs.py  evaluations.py  settings.py  meta.py  deps.py
  tests/
    conftest.py                profile/semantic builders, app client fixture
    unit/test_domain.py  test_lines.py  test_catalog.py  test_state.py  test_packer.py  test_parser.py
    unit/test_typesafe_evaluator.py  test_fake_evaluator.py
    unit/test_scoring_config.py  test_components.py  test_penalties.py  test_blockers.py
    unit/test_skills.py  test_explain.py  test_scorer_cases.py  test_boundaries.py
    api/test_flow.py  test_profile.py  test_jobs.py  test_settings.py  test_worker.py  test_migrations.py
```

Deviation from spec §6.6 (recorded in spec in Task 7): fake fixtures are Python builders in `semantic/fake_fixtures.py` instead of JSON files — a full `SemanticJobEvaluation` JSON is ~300 lines each, and builders keep eight fixtures readable.

---

### Task 1: Backend skeleton, settings, logging, domain models

**Files:**
- Create: `.gitignore`, `Makefile`, `backend/pyproject.toml`, `backend/.env.example`, `backend/app/__init__.py` (+ empty `__init__.py` in every package), `backend/app/config.py`, `backend/app/logging.py`, `backend/app/domain.py`
- Test: `backend/tests/unit/test_domain.py`

**Interfaces — Produces:**
- `Settings` fields: `typesafe_api_key: SecretStr | None`, `typesafe_model: str | None`, `typesafe_max_concurrency: int = 4`, `typesafe_token_budget: int = 24000`, `typesafe_log_level: str = "warning"`, `evaluator: Literal["typesafe","fake"] = "typesafe"`, `evaluation_workers: int = 4`, `database_url: str = "sqlite:///./data/jobfit.db"`, `log_level: str = "info"`; `model_name` property → `typesafe_model` or `"fake"`; `validate_for_startup()` raises `RuntimeError("TYPESAFE_API_KEY is required when EVALUATOR=typesafe")` / `"TYPESAFE_MODEL ..."`.
- `domain.py`: all §5 enums/models verbatim, plus `CandidateProfileIn` (`resume_text, preferences, blocker_facts, tracked_skills`) with §5.2 validation; `CandidateProfile(CandidateProfileIn)` adds `id, created_at, semantic_hash`; `semantic_hash(p: CandidateProfileIn) -> str`; `canonical_json(obj) -> str` (`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)`); `DEFAULT_TRACKED_SKILLS: list[TrackedSkill]` (§6.8); `JobPostingIn` with trimming/length validation.
- `configure_logging(settings)`: root handler with `JsonFormatter`; `logging.getLogger("typesafe_sdk").setLevel(settings.typesafe_log_level.upper())`. Events log as `logger.info("evaluation.completed", extra={"fields": {...}})`.

- [ ] **Step 1: Scaffold**

```bash
mkdir -p backend && cd backend && uv init --app --python 3.13 --name jobfit-backend --no-readme
uv add fastapi "uvicorn[standard]" pydantic-settings "sqlalchemy>=2" alembic "typesafe-sdk==0.6.*" pypdf python-docx python-multipart
uv add --dev pytest pytest-asyncio httpx
```

`pyproject.toml` pytest config:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = ["live: hits real TypeSafe (needs TYPESAFE_API_KEY)"]
addopts = "-m 'not live'"
```

`.gitignore`: `.DS_Store`, `backend/.venv/`, `backend/data/`, `backend/.env`, `__pycache__/`, `frontend/node_modules/`, `frontend/.next/`.

- [ ] **Step 2: Write failing tests** (`tests/unit/test_domain.py`)

```python
import pytest
from pydantic import ValidationError
from app.domain import (CandidateProfileIn, CandidatePreferences, BlockerFacts, TrackedSkill,
                        JobPostingIn, DEFAULT_TRACKED_SKILLS, semantic_hash)

def profile(**prefs):
    return CandidateProfileIn(resume_text="Android engineer", preferences=CandidatePreferences(**prefs),
                              blocker_facts=BlockerFacts(), tracked_skills=DEFAULT_TRACKED_SKILLS)

def test_default_tracked_skills_match_spec():
    assert [s.id for s in DEFAULT_TRACKED_SKILLS][:4] == ["android", "kotlin", "java", "jetpack_compose"]
    assert len(DEFAULT_TRACKED_SKILLS) == 18

def test_technology_in_two_lists_rejected():
    with pytest.raises(ValidationError):
        profile(required_technologies=["Kotlin"], avoid_technologies=[" kotlin "])

def test_role_family_preferred_and_avoided_rejected():
    with pytest.raises(ValidationError):
        profile(preferred_role_families=["flutter"], avoided_role_families=["flutter"])

def test_skill_ids_must_be_unique_slugs():
    with pytest.raises(ValidationError):
        CandidateProfileIn(resume_text="x", preferences=CandidatePreferences(), blocker_facts=BlockerFacts(),
                           tracked_skills=[TrackedSkill(id="Bad Id", label="x")])
    with pytest.raises(ValidationError):
        CandidateProfileIn(resume_text="x", preferences=CandidatePreferences(), blocker_facts=BlockerFacts(),
                           tracked_skills=[TrackedSkill(id="a", label="x"), TrackedSkill(id="a", label="y")])

def test_empty_resume_rejected():
    with pytest.raises(ValidationError):
        CandidateProfileIn(resume_text="  ", preferences=CandidatePreferences(), blocker_facts=BlockerFacts(), tracked_skills=[])

def test_semantic_hash_ignores_scoring_only_fields_and_blocker_facts():
    a = profile(remote_preference="remote")
    b = profile(remote_preference="onsite", management_preference="ic")
    b.blocker_facts.needs_visa_sponsorship = True
    assert semantic_hash(a) == semantic_hash(b)
    assert semantic_hash(a) != semantic_hash(profile(preferred_roles=["Staff Android"]))

def test_job_posting_validation():
    with pytest.raises(ValidationError):
        JobPostingIn(company="A", title="B", description="too short")
    with pytest.raises(ValidationError):
        JobPostingIn(company="A", title="B", description="x" * 60, source_url="ftp://x.com")
    j = JobPostingIn(company="  Acme ", title=" Eng ", description="x" * 60)
    assert (j.company, j.title) == ("Acme", "Eng")
```

- [ ] **Step 3:** `uv run pytest tests/unit/test_domain.py` → FAIL (import error).
- [ ] **Step 4: Implement** `config.py`, `logging.py`, `domain.py` per Interfaces and §5. `semantic_hash` = sha256 of `canonical_json({"resume_text", "preferred_roles", "preferred_locations", "required_technologies", "preferred_technologies", "avoid_technologies", "tracked_skills"})`. `source_url` validator rejects schemes other than http/https.
- [ ] **Step 5:** tests PASS.
- [ ] **Step 6:** Commit `feat(backend): skeleton, settings, logging, domain models`.

---

### Task 2: ScoringConfig

**Files:** Create `backend/app/scoring/config.py`; Test `tests/unit/test_scoring_config.py`

**Produces:** `ScoringConfig` (Pydantic, nested models mirroring §7.10 JSON exactly; `ScoringConfig()` equals the defaults). Validation per §7.10 last paragraph.

- [ ] **Step 1: Failing tests**

```python
import pytest
from pydantic import ValidationError
from app.scoring.config import ScoringConfig

def test_defaults_match_spec():
    c = ScoringConfig()
    assert c.weights.technical == 30 and c.weights.management == 5
    assert c.arrangement_matrix["remote"]["onsite"] == 0.0
    assert c.penalties.missing_required_skill.cap == 20
    assert c.blockers.threshold == 0.8 and c.blockers.possible_threshold == 0.5
    assert c.status_thresholds.strong_match == 85
    assert c.evidence_min_probability == 0.5

@pytest.mark.parametrize("patch", [
    {"weights": {"technical": -1}},
    {"weights": {"technical": 0, "android": 0, "seniority": 0, "domain": 0}},
    {"blockers": {"threshold": 0.5, "possible_threshold": 0.6}},
    {"status_thresholds": {"strong_match": 70, "good_match": 70, "review": 55}},
    {"confidence_bands": {"accept": 0.5, "review": 0.6}},
    {"arrangement_matrix": {"remote": {"remote": 1.5}}},
    {"evidence_min_probability": 1.2},
])
def test_invalid_configs_rejected(patch):
    data = ScoringConfig().model_dump()
    for k, v in patch.items():
        if isinstance(v, dict) and k != "arrangement_matrix":
            data[k].update(v)
        elif k == "arrangement_matrix":
            data[k]["remote"].update(v["remote"])
        else:
            data[k] = v
    with pytest.raises(ValidationError):
        ScoringConfig.model_validate(data)
```

- [ ] **Step 2:** run → FAIL. **Step 3:** implement (probabilities typed `Annotated[float, Field(ge=0, le=1)]`; `model_validator(mode="after")` for cross-field rules). **Step 4:** PASS. **Step 5:** commit `feat(scoring): versionable ScoringConfig`.

---

### Task 3: Line segmentation

**Files:** Create `backend/app/semantic/lines.py`; Test `tests/unit/test_lines.py`

**Produces:** `SEGMENTATION_VERSION = "1"`; `segment(description: str) -> dict[str, str]` (ordered `L000`…); `eligible_ids(lines: dict[str, str]) -> list[str]` (len ≥ 20 and not ending with `:`); `MAX_LINES = 254`.

- [ ] **Step 1: Failing tests**

```python
from app.semantic.lines import segment, eligible_ids

def test_bullets_whitespace_and_empty_lines():
    lines = segment("About the role:\r\n\r\n-   Build   Android apps with Kotlin\n• Lead architecture reviews\n1. Mentor engineers daily\n2) Ship")
    assert lines == {"L000": "About the role:", "L001": "Build Android apps with Kotlin",
                     "L002": "Lead architecture reviews", "L003": "Mentor engineers daily", "L004": "Ship"}

def test_long_line_split_on_sentences():
    long = ("We build payments. " * 20).strip()  # > 300 chars
    lines = segment(long)
    assert len(lines) == 20 and lines["L000"] == "We build payments."

def test_cap_merges_shortest_adjacent_pair():
    text = "\n".join(f"line number {i}" if i != 5 else "x" for i in range(300))
    lines = segment(text)
    assert len(lines) == 254
    assert list(lines) == [f"L{i:03d}" for i in range(254)]

def test_eligibility():
    lines = {"L000": "Requirements:", "L001": "Short one", "L002": "5+ years building Android apps"}
    assert eligible_ids(lines) == ["L002"]
```

- [ ] **Step 2:** FAIL. **Step 3: Implement** per §6.1:

```python
import re
SEGMENTATION_VERSION = "1"
MAX_LINES = 254
_BULLET = re.compile(r"^(?:[-*•–]|\d+[.)])\s*")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

def segment(description: str) -> dict[str, str]:
    raw = description.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    items: list[str] = []
    for line in raw:
        line = _BULLET.sub("", " ".join(line.split()))
        if not line:
            continue
        items.extend(_SENTENCE.split(line) if len(line) > 300 else [line])
    while len(items) > MAX_LINES:
        i = min(range(len(items) - 1), key=lambda k: len(items[k]) + len(items[k + 1]))
        items[i:i + 2] = [f"{items[i]} {items[i + 1]}"]
    return {f"L{i:03d}": text for i, text in enumerate(items)}

def eligible_ids(lines: dict[str, str]) -> list[str]:
    return [k for k, v in lines.items() if len(v) >= 20 and not v.endswith(":")]
```

Note: bullet stripping runs after whitespace collapse, and an empty result after stripping is dropped. **Step 4:** PASS. **Step 5:** commit `feat(semantic): JD line segmentation`.

---

### Task 4: States and question catalog

**Files:** Create `backend/app/semantic/state.py`, `backend/app/semantic/catalog.py`; Tests `tests/unit/test_state.py`, `tests/unit/test_catalog.py`

**Consumes:** `CandidateProfile`, `JobPosting`, `segment`, `eligible_ids`, `SEGMENTATION_VERSION`, `canonical_json`.

**Produces:**
- `build_job_state(job: JobPosting, lines: dict[str,str]) -> dict` and `build_fit_state(job, lines, profile) -> dict` (§6.2; omit empty optional job fields and empty lists; `salary` from `salary_text`).
- `@dataclass(frozen=True) class Q: id: str; state: Literal["job","fit"]; body: dict` with helpers `q.kind` (`body["type"]`), `q.options` (choice criteria keys), `q.levels` (len of score criteria).
- `EVALUATOR_VERSION = "1.0.0"`.
- `REQUIREMENT_CRITERIA`, `EVIDENCE_TARGETS: dict[str, str]` (target → question, §6.3.2 table).
- `tech_slug(text) -> str` (`re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")`); `technologies(prefs) -> dict[slug, text]` (first spelling wins, order required → preferred → avoid).
- `build_questions(profile: CandidateProfile, lines: dict[str,str]) -> list[Q]` in catalog order: job static (§6.3.1 order) → `skill_req.*` (skip `kmp`) → `tech_centrality.*` → `evidence.*` → `line_kind.*` → `line_skill.*` ; then fit: `technical_fit`, `seniority_fit`, `domain_fit`, `role_preference_fit` (only if preferred_roles), `location_match` (only if preferred_locations), `skill_ev.*`, `line_ev.*`.
- `catalog_hash() -> str`: sha256 of `canonical_json({"segmentation": SEGMENTATION_VERSION, "questions": [q.body ...]})` over questions built from a sentinel profile (one tracked skill `{id:"<skill>", label:"<label>", description:"<description>"}`, one required technology `"<technology>"`, preferred roles/locations `["<role>"]`/`["<location>"]`) and sentinel lines `{"L000": "<line text for catalog hash>"}`.
- `question_set_hash(questions: list[Q]) -> str`: sha256 of `canonical_json([[q.id, q.state, q.body] ...])`.

- [ ] **Step 1: Failing tests**

`tests/unit/test_state.py` — the privacy invariant:

```python
import json
from app.semantic.state import build_job_state, build_fit_state
from tests.conftest import make_profile, make_job

SECRET_MARKERS = ["SECRET-AUTH-NOTE", "never_sent"]

def test_states_never_contain_blocker_facts_notes_or_scoring_only_preferences():
    profile = make_profile(
        work_authorization_notes="SECRET-AUTH-NOTE", preferred_levels=["staff"], preferred_role_families=["flutter"],
        avoided_role_families=["ios"], preferred_domains=["fintech"], remote_preference="remote",
        willing_to_relocate=True, management_preference="ic", years_experience=11.5,
        preferred_roles=["Staff Android"], preferred_locations=["Remote US"],
        blocker_facts={"needs_visa_sponsorship": True, "can_meet_us_citizenship_requirement": False,
                       "can_meet_clearance_requirement": False})
    job = make_job()
    lines = {"L000": "Build Android apps with Kotlin daily"}
    blob = json.dumps([build_job_state(job, lines), build_fit_state(job, lines, profile)])
    for forbidden in ["SECRET-AUTH-NOTE", "needs_visa", "citizenship_requirement", "clearance_requirement",
                      "preferred_levels", "role_families", "preferred_domains", "remote_preference",
                      "relocate", "management_preference", "years_experience", "11.5", "fintech"]:
        assert forbidden not in blob
    fit = build_fit_state(job, lines, profile)
    assert set(fit["candidate"]) == {"resume", "preferred_roles", "preferred_locations"}

def test_empty_fields_omitted():
    job = make_job(location=None, salary_text=None)
    state = build_job_state(job, {"L000": "x"})
    assert set(state["job"]) == {"title", "company", "lines"}
    assert "preferred_roles" not in build_fit_state(job, {}, make_profile())["candidate"]
```

`tests/unit/test_catalog.py`:

```python
from app.semantic.catalog import build_questions, catalog_hash, EVALUATOR_VERSION, question_set_hash
from tests.conftest import make_profile

PINNED = {"1.0.0": "<fill in from first run, see Step 4>"}

def qs(**prefs):
    lines = {"L000": "Requirements:", "L001": "5+ years of Android development with Kotlin",
             "L002": "Experience with Kotlin Multiplatform is a plus"}
    return {q.id: q for q in build_questions(make_profile(**prefs), lines)}

def test_catalog_hash_pinned_to_evaluator_version():
    assert PINNED[EVALUATOR_VERSION] == catalog_hash()

def test_primitive_limits_and_unique_ids():
    built = build_questions(make_profile(required_technologies=["Kotlin"]),
                            {f"L{i:03d}": f"eligible requirement line {i}" for i in range(254)})
    assert len({q.id for q in built}) == len(built)
    for q in built:
        if q.kind == "score":
            assert 2 <= q.levels <= 10
        if q.kind == "choice":
            assert len(q.options) <= 255

def test_dynamic_questions():
    q = qs(required_technologies=["Jetpack Compose"], avoid_technologies=["Flutter"])
    assert "skill_req.kmp" not in q and "skill_req.kotlin" in q and "skill_ev.kmp" in q
    assert {"tech_centrality.jetpack_compose", "tech_centrality.flutter"} <= set(q)
    assert set(q["evidence.seniority"].options) == {"L000", "L001", "L002", "none"}
    assert "line_kind.L000" not in q and {"line_kind.L001", "line_skill.L002", "line_ev.L001"} <= set(q)
    assert q["line_skill.L001"].options[-1] == "none"
    assert q["line_kind.L001"].state == "job" and q["line_ev.L001"].state == "fit"

def test_optional_fit_questions():
    assert "role_preference_fit" not in qs() and "location_match" not in qs()
    both = qs(preferred_roles=["Staff Android"], preferred_locations=["Remote US"])
    assert both["role_preference_fit"].levels == 4 and both["location_match"].options == [
        "in_preferred_location", "outside_preferred_locations", "unclear"]

def test_question_set_hash_changes_with_questions():
    a = build_questions(make_profile(), {"L000": "Build Android apps with Kotlin daily"})
    b = build_questions(make_profile(), {"L000": "Build iOS apps with Swift every day"})
    assert question_set_hash(a) != question_set_hash(b)
```

`tests/conftest.py` builders (used from here on):

```python
from datetime import datetime, UTC
from uuid import uuid4
from app.domain import (CandidateProfile, CandidateProfileIn, CandidatePreferences, BlockerFacts,
                        DEFAULT_TRACKED_SKILLS, JobPosting, semantic_hash)

def make_profile(blocker_facts=None, tracked_skills=None, resume_text="Staff Android engineer, Kotlin, Compose", **prefs) -> CandidateProfile:
    base = CandidateProfileIn(resume_text=resume_text, preferences=CandidatePreferences(**prefs),
                              blocker_facts=BlockerFacts(**(blocker_facts or {})),
                              tracked_skills=DEFAULT_TRACKED_SKILLS if tracked_skills is None else tracked_skills)
    return CandidateProfile(**base.model_dump(), id=uuid4(), created_at=datetime.now(UTC), semantic_hash=semantic_hash(base))

def make_job(**over) -> JobPosting:
    data = dict(company="Acme", title="Staff Android Engineer", description="Build Android apps with Kotlin. " * 3,
                location="Remote (US)", salary_text="$220k", external_id=None)
    data.update(over)
    now = datetime.now(UTC)
    return JobPosting(**data, id=uuid4(), content_hash="h", created_at=now, imported_at=now)
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** `state.py` and `catalog.py`. Question bodies are copied verbatim from §6.3.1–§6.3.3 as dicts: `{"type": "choice", "instructions": {"question": ..., "inspect": "`job.lines`", "focus": ...}, "criteria": {...}}`. Choice criteria listed without description in the spec use `None`; contrastive criteria are dicts with keys `what`, `not_for`, `examples` (omit absent keys). Score criteria are the level strings in order. Noul criteria use keys `"true"`/`"false"`. Per-line questions reference `` `job.lines.<id>` ``. `evidence.*` criteria: `{**{lid: None for lid in lines}, "none": "No line of the posting states this"}`. `line_skill.*` criteria: `{s.id: f"{s.label}: {s.description}" if s.description else s.label, ..., "none": "None of the listed skills, or the line asks for no skill"}`. `domain` criteria: every `Domain` value, `None` except the six described in §6.3.1.
- [ ] **Step 4:** Run `uv run python -c "from app.semantic.catalog import catalog_hash; print(catalog_hash())"` and paste the value into `PINNED`. Run tests → PASS.
- [ ] **Step 5:** commit `feat(semantic): states and question catalog`.

---

### Task 5: Request packer

**Files:** Create `backend/app/semantic/packer.py`; Test `tests/unit/test_packer.py`

**Produces:** `class PostingOrResumeTooLong(Exception)`; `estimate_tokens(state: dict, questions: list[Q]) -> int` = `ceil(len(canonical_json({"state": state, "questions": {q.id: q.body for q in questions}})) / 3.5)`; `pack(state: dict, questions: list[Q], budget: int) -> list[list[Q]]` (greedy, catalog order; raises when the state alone, or state + any single question, exceeds budget).

- [ ] **Step 1: Failing tests**

```python
import pytest
from app.semantic.catalog import Q
from app.semantic.packer import pack, estimate_tokens, PostingOrResumeTooLong

def q(i, size=100):
    return Q(id=f"q{i}", state="job", body={"type": "noul", "instructions": "x" * size})

def test_packs_greedily_within_budget_preserving_order():
    state = {"job": {"lines": {"L000": "y" * 100}}}
    questions = [q(i) for i in range(50)]
    groups = pack(state, questions, budget=500)
    assert len(groups) > 1
    assert [x.id for g in groups for x in g] == [x.id for x in questions]
    assert all(estimate_tokens(state, g) <= 500 for g in groups)

def test_single_request_when_it_fits():
    assert len(pack({"a": 1}, [q(1), q(2)], budget=24000)) == 1

def test_oversized_state_fails():
    with pytest.raises(PostingOrResumeTooLong):
        pack({"resume": "z" * 10_000}, [q(1)], budget=1000)
```

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(semantic): token-budget request packer`.

---

### Task 6: Answer parser

**Files:** Create `backend/app/semantic/parser.py`; Test `tests/unit/test_parser.py`

**Consumes:** `Q`, `build_questions`, `EVIDENCE_TARGETS`, `tech_slug`, `technologies`, `eligible_ids`, domain signal models.

**Produces:**
- `class MalformedTypeSafeResponse(Exception)`.
- `parse_answers(answers: dict[str, dict], questions: list[Q], profile: CandidateProfile, lines: dict[str,str], *, model: str, requests: list[RequestMeta], question_set_hash: str) -> SemanticJobEvaluation`. Answer dicts are plain JSON: choice `{"type":"choice","choice","probabilities","confidence"}`, score `{"type":"score","score","probabilities","confidence"}` (probability keys may be `int` or `str`), noul `{"type":"noul","noul"}`.
- `choice_signal(ans) -> ChoiceSignal`, `score_signal(ans, levels) -> ScoreSignal`, `noul_signal(ans) -> NoulSignal` (reused by fake fixtures).
- Test helper in `tests/conftest.py`: `fake_answers(questions: list[Q]) -> dict[str, dict]` returning a valid answer for every question (choice: first option p=1.0 conf 0.9; score: level 0 p=1.0 score 0 conf 0.9; noul: 0.1).

- [ ] **Step 1: Failing tests**

```python
import pytest
from app.semantic.catalog import build_questions, catalog_hash
from app.semantic.parser import parse_answers, MalformedTypeSafeResponse
from tests.conftest import make_profile, fake_answers

LINES = {"L000": "Requirements:", "L001": "5+ years of Android development with Kotlin",
         "L002": "Active Secret clearance required for this role"}

def run(answers=None, **prefs):
    profile = make_profile(**prefs)
    questions = build_questions(profile, LINES)
    answers = answers if answers is not None else fake_answers(questions)
    return questions, parse_answers(answers, questions, profile, LINES, model="m", requests=[], question_set_hash="h")

def test_parses_complete_answer_set():
    questions, ev = run(required_technologies=["Kotlin"])
    assert ev.role_family.value == "android_native"
    assert ev.android_relevance.levels == 5 and ev.android_relevance.normalized == 0
    assert ev.staff_ic_signal.derived_confidence == pytest.approx(0.8)
    assert set(ev.skills) == {"android", "kotlin", "java", "jetpack_compose", "coroutines", "architecture",
        "system_design", "testing", "ci_cd", "kmp", "flutter", "react_native", "ios", "swift", "backend",
        "leadership", "people_management", "ai_ml"}
    assert ev.skills["kmp"].requirement == ev.kmp_requirement
    assert set(ev.technologies) == {"kotlin"}
    assert [l.id for l in ev.lines] == ["L001", "L002"] and ev.all_lines == LINES
    assert ev.role_preference_fit is None and ev.location_match is None
    assert set(ev.evidence) == {"security_clearance_required", "us_citizenship_required", "work_authorization_signal",
        "work_arrangement", "requires_relocation", "kmp_requirement", "min_years_required", "seniority", "management_intensity"}

def test_evidence_resolves_line_text_and_none():
    profile = make_profile()
    questions = build_questions(profile, LINES)
    answers = fake_answers(questions)
    answers["evidence.security_clearance_required"] = {"type": "choice", "choice": "L002",
        "probabilities": {"L002": 0.9, "none": 0.1}, "confidence": 0.9}
    answers["evidence.seniority"] = {"type": "choice", "choice": "none", "probabilities": {"none": 1.0}, "confidence": 1}
    ev = parse_answers(answers, questions, profile, LINES, model="m", requests=[], question_set_hash="h")
    assert ev.evidence["security_clearance_required"].text == LINES["L002"]
    assert ev.evidence["security_clearance_required"].probability == 0.9
    assert ev.evidence["seniority"].line_id is None and ev.evidence["seniority"].text is None

def test_score_normalized_and_int_keys():
    profile = make_profile()
    questions = build_questions(profile, LINES)
    answers = fake_answers(questions)
    answers["technical_fit"] = {"type": "score", "score": 3.0, "confidence": 0.8,
                                "probabilities": {"0": 0, "1": 0, "2": 0.1, "3": 0.8, "4": 0.1}}
    ev = parse_answers(answers, questions, profile, LINES, model="m", requests=[], question_set_hash="h")
    assert ev.technical_fit.normalized == 0.75 and ev.technical_fit.probabilities[3] == 0.8

@pytest.mark.parametrize("mutate", [
    lambda a: a.pop("role_family"),
    lambda a: a.__setitem__("role_family", {"type": "score", "score": 1, "probabilities": {}, "confidence": 1}),
    lambda a: a["role_family"].__setitem__("choice", "astronaut"),
    lambda a: a.__setitem__("technical_fit", {"type": "score", "score": 1, "confidence": 1, "probabilities": {"0": 1}}),
    lambda a: a.__setitem__("staff_ic_signal", {"type": "noul", "noul": 1.5}),
])
def test_rejects_malformed(mutate):
    profile = make_profile()
    questions = build_questions(profile, LINES)
    answers = fake_answers(questions)
    mutate(answers)
    with pytest.raises(MalformedTypeSafeResponse):
        parse_answers(answers, questions, profile, LINES, model="m", requests=[], question_set_hash="h")
```

- [ ] **Step 2–4:** FAIL → implement (validate every question first, then assemble) → PASS.
- [ ] **Step 5:** commit `feat(semantic): strict answer parser`.

---

### Task 7: Evaluator protocol, fake evaluator, fixtures

**Files:** Create `backend/app/semantic/evaluator.py`, `backend/app/semantic/fake_fixtures.py`, `backend/app/semantic/fake_evaluator.py`; Modify spec §6.6 (fixture format sentence); Test `tests/unit/test_fake_evaluator.py`

**Produces:**
- `class JobSemanticEvaluator(Protocol): model: str; async def evaluate(self, profile, job) -> SemanticJobEvaluation`.
- `class SemanticEvaluationError(Exception)`: `__init__(self, message: str, status: int | None = None, request_id: str | None = None)`; `sanitized() -> str` → `"<message> (status=..., request_id=...)"`.
- `fake_fixtures.py`: helpers `ch(value, p=0.9, conf=None, options=None)` (puts `p` on value, spreads `1-p` evenly over the other options of the enum), `sc(score, levels, conf=0.9)` (probabilities: mass on floor/ceil levels so the weighted mean equals `score`), `nl(p)`; `FIXTURES: dict[str, dict]` with keys `default`, `android_staff_perfect`, `flutter_heavy`, `engineering_manager`, `clearance_required`, `gov_contractor_no_clearance`, `no_sponsorship_info`, `explicit_no_sponsorship`, `staff_title_senior_scope`. Each value is a dict of `SemanticJobEvaluation` job/fit signal fields plus optional `skills: {id: (requirement_value, evidence_score)}`, `technologies: {slug: score}`, `lines: {line_id: {"kind": value, "skill": id|"none", "evidence": score}}`, `evidence: {target: line_id}`. `default` = `android_staff_perfect`. Each fixture also provides `posting: JobPostingIn`-shaped dict (company/title/location/description) — a realistic posting for that case, reused by the seed script and live golden set in Plan B.
- `FakeJobSemanticEvaluator(model="fake")`: picks `FIXTURES[job.external_id.removeprefix("fixture:")]` when present else `default`; segments `job.description`; fills skills for every profile tracked skill (fixture value or `not_mentioned`/0), technologies for every profile technology slug (fixture value or 0), lines for every eligible line (fixture override or `other`/`none`/0), evidence for all nine targets (fixture line if it exists in the job's lines at p 0.9, else `none`); drops `location_match`/`role_preference_fit` when the profile preference list is empty; computes real `catalog_hash()` and `question_set_hash(build_questions(...))`; `requests=[]`.

- [ ] **Step 1: Failing tests**

```python
from app.semantic.fake_evaluator import FakeJobSemanticEvaluator
from app.semantic.fake_fixtures import FIXTURES
from tests.conftest import make_profile, make_job

async def test_picks_fixture_by_external_id_and_uses_real_segmentation():
    posting = FIXTURES["clearance_required"]["posting"]
    job = make_job(**posting, external_id="fixture:clearance_required")
    ev = await FakeJobSemanticEvaluator().evaluate(make_profile(), job)
    assert ev.security_clearance_required.probability >= 0.8
    ev_line = ev.evidence["security_clearance_required"]
    assert ev_line.line_id in ev.all_lines and "clearance" in ev_line.text.lower()

async def test_default_fixture_and_dropped_missing_lines():
    job = make_job(description="Tiny posting about Android work.\nAnother line for the fake evaluator.")
    ev = await FakeJobSemanticEvaluator().evaluate(make_profile(preferred_roles=["Staff Android"]), job)
    assert ev.role_family.value == "android_native"
    assert all(e.line_id is None or e.line_id in ev.all_lines for e in ev.evidence.values())
    assert ev.role_preference_fit is not None and ev.location_match is None

async def test_every_fixture_builds():
    for name, fx in FIXTURES.items():
        job = make_job(**fx["posting"], external_id=f"fixture:{name}")
        await FakeJobSemanticEvaluator().evaluate(make_profile(required_technologies=["Kotlin"]), job)
```

- [ ] **Step 2–4:** FAIL → implement → PASS. Fixture targets (asserted by Task 12's scorer case tests): `flutter_heavy` android_relevance ≈1.0, cross_platform_intensity 3.5, role_family flutter; `engineering_manager` management_intensity 3.6, role_family engineering_management, seniority manager; `clearance_required` clearance p 0.95, domain government_defense; `gov_contractor_no_clearance` clearance p 0.05, domain government_defense; `no_sponsorship_info` work_authorization_signal `not_stated` 0.95; `explicit_no_sponsorship` `explicit_no_sponsorship` 0.93; `staff_title_senior_scope` title_level staff 0.9, seniority senior 0.85; `android_staff_perfect` technical 3.7, android 3.9, seniority_fit 3.6, role_preference 2.8, management 1.2, remote 0.9, domain fintech 0.9, domain_fit 3.4, kmp preferred 0.85.
- [ ] **Step 5:** Update spec §6.6 fake-evaluator bullet: "fixtures are Python builders in `semantic/fake_fixtures.py` (each with a realistic sample posting)". Commit `feat(semantic): fake evaluator with case fixtures`.

---

### Task 8: TypeSafe evaluator

**Files:** Create `backend/app/semantic/typesafe_evaluator.py`; Test `tests/unit/test_typesafe_evaluator.py`, `tests/unit/test_boundaries.py`

**Consumes:** `segment`, `build_job_state`, `build_fit_state`, `build_questions`, `pack`, `parse_answers`, `catalog_hash`, `question_set_hash`, `SemanticEvaluationError`.

**Produces:** `TypeSafeJobSemanticEvaluator(api_key: str, model: str, budget: int, semaphore: asyncio.Semaphore, transport=None)`; `.model`; `evaluate()`: segment → states → questions → pack each state kind → `asyncio.gather` all requests (each inside `async with semaphore`) → convert answers with `msgspec.to_builtins` → `parse_answers`. Client: `AsyncTypeSafeClient(api_key=, model=, retry=RetryPolicy(max_retries=3, timeout=120.0), timeout=30.0, transport=transport)`, created per evaluation inside `async with`. `RequestMeta.raw_response = response.raw_http_response.json()`; `request_id` read via `response.__dict__`-safe try/except `TypeSafeError` → None. SDK `TypeSafeAPIError` → `SemanticEvaluationError(type(e).__name__, e.status, e.request_id)`; other `TypeSafeError` → `SemanticEvaluationError(type(e).__name__)`. Logs per request `{request_id, state_kind, question_count, estimated_tokens, input_tokens, output_tokens, latency_ms}` at info under event `typesafe.request`.

- [ ] **Step 1: Failing tests**

```python
import asyncio, json
import httpx2, pytest
from app.semantic.typesafe_evaluator import TypeSafeJobSemanticEvaluator
from app.semantic.evaluator import SemanticEvaluationError
from tests.conftest import make_profile, make_job, fake_answers_for_bodies

def transport(calls, status=200):
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if status != 200:
            return httpx2.Response(status, json={"error": "boom"}, headers={"x-typesafe-request-id": "req-err"})
        return httpx2.Response(200, headers={"x-typesafe-request-id": f"req-{len(calls)}"}, json={
            "model": body["model"], "usage": {"input_tokens": 10, "output_tokens": 2},
            "answers": fake_answers_for_bodies(body["questions"])})
    return httpx2.MockTransport(handler)

async def test_sends_job_and_fit_requests_and_parses():
    calls = []
    ev = TypeSafeJobSemanticEvaluator("k", "jev-2026-09", 24000, asyncio.Semaphore(4), transport=transport(calls))
    result = await ev.evaluate(make_profile(blocker_facts={"needs_visa_sponsorship": True}), make_job())
    assert sorted("candidate" in c["state"] for c in calls) == [False, True]
    assert all(c["model"] == "jev-2026-09" for c in calls)
    assert "needs_visa_sponsorship" not in json.dumps(calls)
    assert {r.state_kind for r in result.requests} == {"job", "fit"}
    assert result.requests[0].request_id.startswith("req-") and result.model == "jev-2026-09"

async def test_small_budget_splits_requests():
    calls = []
    ev = TypeSafeJobSemanticEvaluator("k", "m", 4000, asyncio.Semaphore(4), transport=transport(calls))
    await ev.evaluate(make_profile(), make_job())
    assert len(calls) > 2

async def test_api_error_is_sanitized():
    ev = TypeSafeJobSemanticEvaluator("k", "m", 24000, asyncio.Semaphore(4), transport=transport([], status=400))
    with pytest.raises(SemanticEvaluationError) as err:
        await ev.evaluate(make_profile(resume_text="PRIVATE RESUME"), make_job())
    assert err.value.status == 400 and err.value.request_id == "req-err"
    assert "PRIVATE RESUME" not in err.value.sanitized()
```

`fake_answers_for_bodies(questions: dict[str, dict]) -> dict` goes in conftest (same answers as `fake_answers`, keyed from raw bodies; `fake_answers` delegates to it). Adds `"type"` per answer.

`tests/unit/test_boundaries.py`:

```python
import pathlib, re
APP = pathlib.Path(__file__).parents[2] / "app"

def test_only_typesafe_evaluator_imports_sdk():
    hits = [p.relative_to(APP).as_posix() for p in APP.rglob("*.py") if re.search(r"^\s*(from|import) typesafe_sdk", p.read_text(), re.M)]
    assert hits == ["semantic/typesafe_evaluator.py"]

def test_scoring_is_pure():
    for p in (APP / "scoring").rglob("*.py"):
        text = p.read_text()
        assert not re.search(r"^\s*(from|import) (app\.(db|models|semantic|pipeline|api)|sqlalchemy|httpx|typesafe_sdk)", text, re.M), p
```

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(semantic): TypeSafe System One evaluator`.

---

### Task 9: Scoring — components, base score, confidence

**Files:** Create `backend/app/scoring/components.py`, `backend/app/scoring/confidence.py`; Test `tests/unit/test_components.py`

**Produces:**
- `components(sem: SemanticJobEvaluation, profile: CandidateProfile, cfg: ScoringConfig) -> list[ComponentResult]` — all eight in §7.1 order, with `effective_weight = w / Σ applicable w` (0 when n/a) and `contribution = 100 · effective_weight · value`; `confidence` per §7.6.
- `base_score(comps) -> float` = `Σ contribution`.
- `band(conf: float, cfg) -> Literal["accepted","review","uncertain"]`.
- `aggregate_confidence(comps) -> float`; `uncertain_signals(sem, comps, cfg) -> list[str]` (signal names driving applicable components whose confidence < `cfg.confidence_bands.review`).
- conftest builder `make_semantic(**overrides) -> SemanticJobEvaluation`: neutral baseline (all Score signals at mid level, conf 0.9; choices `other`/`unclear` p 0.9; Nouls 0.05; `work_authorization_signal=not_stated`; empty skills/technologies/lines/evidence; `min_years_required=not_stated`). Overrides accept already-built signals via `fake_fixtures.ch/sc/nl`.

- [ ] **Step 1: Failing tests** — cover the worked example §7.12 plus each n/a rule and formula:

```python
import pytest
from app.scoring.components import components, base_score
from app.scoring.confidence import aggregate_confidence
from app.scoring.config import ScoringConfig
from app.semantic.fake_fixtures import ch, sc
from tests.conftest import make_semantic, make_profile

CFG = ScoringConfig()
def by_name(comps): return {c.name: c for c in comps}

def test_worked_example_7_12():
    sem = make_semantic(technical_fit=sc(3.7, 5), android_relevance=sc(3.9, 5), seniority_fit=sc(3.6, 5),
        role_preference_fit=sc(2.8, 4), role_family=ch("android_native", 0.92, options="RoleFamily"),
        domain_fit=sc(3.4, 5), domain=ch("fintech", 1.0, options="Domain"),
        work_arrangement=ch("remote", 0.9, options="WorkArrangement"), management_intensity=sc(1.2, 5))
    # platform: 0.92*1 + 0.08 spread over 9 others, one of which (kotlin_multiplatform) is preferred -> 0.92 + 0.08/9*(1) + 0.08*8/9*0.5
    profile = make_profile(preferred_roles=["Staff Android"], preferred_role_families=["android_native", "kotlin_multiplatform"],
        preferred_domains=["fintech"], remote_preference="remote", management_preference="ic", preferred_levels=["staff", "principal"])
    c = by_name(components(sem, profile, CFG))
    assert c["technical"].value == pytest.approx(0.925)
    assert c["management"].value == pytest.approx(1 - 0.2 / 3)
    assert c["domain"].value == pytest.approx(0.5 * 0.85 + 0.5 * 1.0)
    assert all(x.applicable for x in c.values())
    assert base_score(list(c.values())) == pytest.approx(sum(x.weight * x.value for x in c.values()))

def test_na_components_renormalize():
    comps = components(make_semantic(), make_profile(), CFG)
    c = by_name(comps)
    for name in ["role_preference", "platform", "work_arrangement", "management"]:
        assert not c[name].applicable and c[name].effective_weight == 0 and c[name].reason.startswith("n/a")
    assert sum(x.effective_weight for x in comps) == pytest.approx(1.0)
    assert c["technical"].effective_weight == pytest.approx(30 / 70)

def test_platform_avoided_family():
    sem = make_semantic(role_family=ch("flutter", 1.0, options="RoleFamily"))
    c = by_name(components(sem, make_profile(avoided_role_families=["flutter"]), CFG))
    assert c["platform"].value == 0.0

@pytest.mark.parametrize("pref,m,expected", [("ic", 1, 1.0), ("ic", 4, 0.0), ("tech_lead", 2, 1.0), ("tech_lead", 4, 0.0),
                                             ("manager", 4, 1.0), ("manager", 1, 0.0)])
def test_management_formula(pref, m, expected):
    c = by_name(components(make_semantic(management_intensity=sc(m, 5)), make_profile(management_preference=pref), CFG))
    assert c["management"].value == pytest.approx(expected)

def test_work_arrangement_with_location_factor():
    sem = make_semantic(work_arrangement=ch("onsite", 1.0, options="WorkArrangement"),
                        location_match=ch("outside_preferred_locations", 1.0, options="LocationMatch"))
    p = make_profile(remote_preference="hybrid", preferred_locations=["Berlin"], willing_to_relocate=True)
    assert by_name(components(sem, p, CFG))["work_arrangement"].value == pytest.approx(0.4 * 0.5)

def test_aggregate_confidence_weighted():
    sem = make_semantic(technical_fit=sc(2, 5, conf=0.5))
    comps = components(sem, make_profile(), CFG)
    expected = sum(c.effective_weight * c.confidence for c in comps if c.applicable)
    assert aggregate_confidence(comps) == pytest.approx(expected)
```

`ch(value, p, options=...)` accepts an enum name string (resolved via `typing.get_args` on the `domain` Literal) or a list of options.

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(scoring): components, base score, confidence`.

---

### Task 10: Scoring — skills, missing skills, penalties

**Files:** Create `backend/app/scoring/skills.py`, `backend/app/scoring/penalties.py`; Tests `tests/unit/test_skills.py`, `tests/unit/test_penalties.py`

**Produces:**
- `evidence_level(score: float) -> Literal["none","weak","partial","strong"]` (§7.8 cut-offs).
- `skill_matches(sem, profile, cfg) -> list[SkillMatch]` (§7.7).
- `missing_skills(sem, profile, cfg) -> list[MissingSkill]` (§7.8, sorted).
- `penalties(sem, profile, cfg, missing: list[MissingSkill]) -> list[Penalty]` (§7.3, disabled penalties skipped). Reasons: `avoided_tech_heavy` → "Heavy use of an avoided technology"; `management_heavy_for_ic` → "Management-heavy role for IC preference"; `seniority_mismatch` → "Seniority outside preferred levels"; `required_tech_weak` → "Required technology {text} is not central"; `missing_required_skill` → "Missing required skills: {labels}". `signal_ids` list the driving signal names.

- [ ] **Step 1: Failing tests** (`test_skills.py`)

```python
from app.domain import SkillSignal, RequirementLine
from app.scoring.config import ScoringConfig
from app.scoring.skills import skill_matches, missing_skills, evidence_level
from app.semantic.fake_fixtures import ch, sc
from tests.conftest import make_semantic, make_profile

CFG = ScoringConfig()
REQ = ["required", "preferred", "mentioned", "not_mentioned"]
KINDS = ["required_qualification", "preferred_qualification", "core_responsibility", "other"]

def skill(req, ev): return SkillSignal(requirement=ch(req, 0.9, options=REQ), evidence=sc(ev, 4))
def line(lid, kind, skill_id, ev, skills=("kmp", "kotlin", "none")):
    return RequirementLine(id=lid, text=f"text {lid}", kind=ch(kind, 0.9, options=KINDS),
                           skill=ch(skill_id, 0.9, options=list(skills)), evidence=sc(ev, 4))

def test_evidence_levels():
    assert [evidence_level(x) for x in (0.49, 0.5, 1.49, 1.5, 2.49, 2.5)] == ["none", "weak", "weak", "partial", "partial", "strong"]

def test_tracked_missing_importance_and_sort():
    sem = make_semantic(
        skills={"kotlin": skill("required", 0), "kmp": skill("preferred", 1), "java": skill("required", 2),
                "swift": skill("mentioned", 0), "android": skill("required", 3)},
        lines=[line("L001", "core_responsibility", "kotlin", 0), line("L002", "required_qualification", "none", 0),
               line("L003", "preferred_qualification", "none", 3)])
    ms = missing_skills(sem, make_profile(), CFG)
    labels = [(m.skill, m.importance, m.candidate_evidence, m.impact) for m in ms]
    assert labels == [("Kotlin", "critical", "none", "significant"),
                      ("text L002", "important", "none", "significant"),
                      ("Java", "important", "partial", "minor"),
                      ("Kotlin Multiplatform", "nice_to_have", "weak", "minor")]
    assert ms[1].source == "requirement_line" and ms[1].line_ids == ["L002"]

def test_skill_matches_exclude_not_mentioned():
    sem = make_semantic(skills={"kotlin": skill("required", 3), "swift": skill("not_mentioned", 0)},
                        lines=[line("L001", "required_qualification", "kotlin", 3)])
    [m] = skill_matches(sem, make_profile(), CFG)
    assert (m.skill, m.requirement_level, m.candidate_match, m.evidence_line_ids) == ("Kotlin", "required", 1.0, ["L001"])
```

Note `ch(value, p, options)` spreads the remainder, so `P(line_skill=none)` for a line mapped to kotlin is 0.05 (< 0.5) — correct for the tests.

`test_penalties.py` — one test per penalty at its boundary:

```python
import pytest
from app.domain import MissingSkill
from app.scoring.config import ScoringConfig
from app.scoring.penalties import penalties
from app.semantic.fake_fixtures import ch, sc
from tests.conftest import make_semantic, make_profile

CFG = ScoringConfig()
def types(sem, profile, missing=()): return {p.type: p.points for p in penalties(sem, profile, CFG, list(missing))}

@pytest.mark.parametrize("score,fires", [(2.5, True), (2.4, False)])
def test_avoided_tech_heavy_via_family(score, fires):
    sem = make_semantic(cross_platform_intensity=sc(score, 5))
    assert ("avoided_tech_heavy" in types(sem, make_profile(avoided_role_families=["flutter"]))) is fires

def test_avoided_tech_heavy_once_when_both_triggers():
    sem = make_semantic(cross_platform_intensity=sc(3.5, 5), technologies={"flutter": sc(3, 4)})
    assert types(sem, make_profile(avoided_role_families=["flutter"], avoid_technologies=["Flutter"])) == {"avoided_tech_heavy": 10}

@pytest.mark.parametrize("m,fires", [(2.5, True), (2.4, False)])
def test_management_heavy_for_ic(m, fires):
    assert ("management_heavy_for_ic" in types(make_semantic(management_intensity=sc(m, 5)), make_profile(management_preference="ic"))) is fires

def test_seniority_mismatch_respects_unclear():
    sen = lambda v, p: make_semantic(seniority=ch(v, p, options="Seniority"))
    p = make_profile(preferred_levels=["staff"])
    assert "seniority_mismatch" in types(sen("senior", 0.9), p)
    assert "seniority_mismatch" not in types(sen("unclear", 0.9), p)
    assert "seniority_mismatch" not in types(sen("staff", 0.9), p)

@pytest.mark.parametrize("score,fires", [(1.0, True), (1.1, False)])
def test_required_tech_weak(score, fires):
    sem = make_semantic(technologies={"kotlin": sc(score, 4)})
    assert ("required_tech_weak" in types(sem, make_profile(required_technologies=["Kotlin"]))) is fires

def test_missing_required_skill_points_and_cap():
    ms = lambda imp, ev: MissingSkill(skill="x", source="tracked_skill", importance=imp, candidate_evidence=ev, impact="minor", line_ids=[])
    assert types(make_semantic(), make_profile(), [ms("critical", "weak")]) == {"missing_required_skill": 5}
    assert types(make_semantic(), make_profile(), [ms("important", "none")] * 3) == {"missing_required_skill": 20}
    assert types(make_semantic(), make_profile(), [ms("nice_to_have", "none"), ms("important", "partial")]) == {}
```

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(scoring): skill matches, missing skills, penalties`.

---

### Task 11: Scoring — hard blockers

**Files:** Create `backend/app/scoring/blockers.py`; Test `tests/unit/test_blockers.py`

**Produces:** `evaluate_blockers(sem, profile, cfg) -> tuple[list[HardBlocker], list[HardBlocker], list[Explanation]]` = (hard, possible, concerns). Concern texts exactly: possible → `f"Possible {label} requirement ({p:.2f}) — verify"`; unset fact → `f"Explicit {label} requirement — set your {fact_label} in Profile to evaluate"`; work auth specific/ambiguous → texts from §7.9. Labels: `security_clearance` "security clearance" / fact "clearance eligibility"; `us_citizenship` "US citizenship" / "US citizenship eligibility"; `no_sponsorship` "no-sponsorship" / "visa sponsorship need". `relocation`, `onsite_location`, `technology_mismatch`, `seniority_far_below` have no unset-fact case. `evidence_text(sem, target, cfg) -> str | None` (shared with `explain.py`).

Each rule is a small function returning `(probability_conditions: list[float], thresholds: list[float], fact_state: "blocks"|"unset"|"ok")` so firing/possible/unset logic is written once:

```python
def classify(probs, thresholds, fact, possible):
    if fact == "ok" or not probs:
        return None
    if all(p >= t for p, t in zip(probs, thresholds)):
        return "fire" if fact == "blocks" else "unset"
    if fact == "blocks" and all(p >= possible for p in probs):
        return "possible"
    return None
```

`technology_mismatch` evaluates each technology separately (fact always "blocks"); `confidence` = the minimum triggering probability.

- [ ] **Step 1: Failing tests**

```python
import pytest
from app.domain import Evidence
from app.scoring.blockers import evaluate_blockers
from app.scoring.config import ScoringConfig
from app.semantic.fake_fixtures import ch, nl, sc
from tests.conftest import make_semantic, make_profile

CFG = ScoringConfig()
def run(sem, **profile_kw):
    hard, possible, concerns = evaluate_blockers(sem, make_profile(**profile_kw), CFG)
    return [b.type for b in hard], [b.type for b in possible], [c.text for c in concerns]

def test_clearance_fires_only_with_fact_false():
    sem = make_semantic(security_clearance_required=nl(0.95),
                        evidence={"security_clearance_required": Evidence(line_id="L003", text="Active Secret clearance required", probability=0.9)})
    hard, _, _ = run(sem, blocker_facts={"can_meet_clearance_requirement": False})
    assert hard == ["security_clearance"]
    hard, _, concerns = run(sem)
    assert hard == [] and concerns == ["Explicit security clearance requirement — set your clearance eligibility in Profile to evaluate"]
    assert run(sem, blocker_facts={"can_meet_clearance_requirement": True}) == ([], [], [])

def test_blocker_carries_confidence_and_evidence():
    sem = make_semantic(security_clearance_required=nl(0.95),
                        evidence={"security_clearance_required": Evidence(line_id="L003", text="Active Secret clearance required", probability=0.9)})
    [b], _, _ = evaluate_blockers(sem, make_profile(blocker_facts={"can_meet_clearance_requirement": False}), CFG)
    assert b.confidence == 0.95 and b.evidence == "Active Secret clearance required"

@pytest.mark.parametrize("p,expected", [(0.8, "hard"), (0.79, "possible"), (0.5, "possible"), (0.49, "none")])
def test_possible_band(p, expected):
    hard, possible, concerns = run(make_semantic(us_citizenship_required=nl(p)), blocker_facts={"can_meet_us_citizenship_requirement": False})
    assert {"hard": (["us_citizenship"], []), "possible": ([], ["us_citizenship"]), "none": ([], [])}[expected] == (hard, possible)
    if expected == "possible":
        assert concerns == [f"Possible US citizenship requirement ({p:.2f}) — verify"]

def test_not_stated_never_blocks_or_concerns():
    sem = make_semantic(work_authorization_signal=ch("not_stated", 0.99, options="WorkAuthSignal"))
    assert run(sem, blocker_facts={"needs_visa_sponsorship": True}) == ([], [], [])

def test_explicit_no_sponsorship():
    sem = make_semantic(work_authorization_signal=ch("explicit_no_sponsorship", 0.93, options="WorkAuthSignal"))
    assert run(sem, blocker_facts={"needs_visa_sponsorship": True})[0] == ["no_sponsorship"]
    assert run(sem, blocker_facts={"needs_visa_sponsorship": False}) == ([], [], [])

def test_specific_authorization_is_concern_not_blocker():
    sem = make_semantic(work_authorization_signal=ch("explicit_specific_work_authorization_requirement", 0.9, options="WorkAuthSignal"))
    assert run(sem, blocker_facts={"needs_visa_sponsorship": True}) == ([], [], ["Specific work authorization requirement — see posting"])

def test_relocation_and_onsite_location():
    assert run(make_semantic(requires_relocation=nl(0.9)))[0] == ["relocation"]
    assert run(make_semantic(requires_relocation=nl(0.9)), willing_to_relocate=True)[0] == []
    sem = make_semantic(work_arrangement=ch("onsite", 0.9, options="WorkArrangement"),
                        location_match=ch("outside_preferred_locations", 0.85, options="LocationMatch"))
    assert run(sem, preferred_locations=["Berlin"])[0] == ["onsite_location"]
    assert run(make_semantic(work_arrangement=ch("onsite", 0.9, options="WorkArrangement")))[0] == []

def test_technology_mismatch():
    avoid = make_semantic(technologies={"flutter": sc(3, 4, probabilities={3: 0.85, 2: 0.15})})
    assert run(avoid, avoid_technologies=["Flutter"])[0] == ["technology_mismatch"]
    absent = make_semantic(technologies={"kotlin": sc(0, 4, probabilities={0: 0.95, 1: 0.05})})
    assert run(absent, required_technologies=["Kotlin"])[0] == ["technology_mismatch"]

def test_seniority_far_below():
    sem = make_semantic(seniority=ch("mid", 0.85, options="Seniority"))
    assert run(sem, preferred_levels=["staff", "manager"])[0] == ["seniority_far_below"]   # k=3, levels ≤1
    assert run(sem, preferred_levels=["senior"])[0] == []                                  # k=2, levels ≤0
    assert run(sem, preferred_levels=["manager"])[0] == []                                 # n/a
```

`sc(score, levels, conf=0.9, probabilities=None)` uses explicit probabilities when given.

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(scoring): hard and possible blockers`.

---

### Task 12: Scoring — explanations, JobFitScorer, §40 case tests

**Files:** Create `backend/app/scoring/explain.py`, `backend/app/scoring/scorer.py`; Tests `tests/unit/test_explain.py`, `tests/unit/test_scorer_cases.py`

**Produces:**
- `explanations(sem, profile, cfg, *, comps, penalties, blocker_concerns, stale_semantics, uncertain) -> list[Explanation]`: the §7.9 rule table as a list of `Rule(section, component, fn)` where `fn` returns `(text, signal_ids, confidence, evidence_target) | None`. Hedging applied centrally: `confidence is None or ≥ accept` → plain; `≥ review` → `"Likely: " + text`; else section becomes `uncertain` with text `f"{signal}: confidence {c:.2f}"` (deduplicated against `uncertain_signals` entries). Strengths sorted by component weight desc (rules with no component last). Signal names in templates: `{score}` formatted `:.1f`, `{p}` `:.2f`; enum values rendered by `value.replace("_", " ")` with first letter capitalized. `evidence_line_id` from `sem.evidence[target]` only when `probability ≥ evidence_min_probability` and `line_id` set.
- `class JobFitScorer: def calculate(self, sem, profile, cfg, *, stale_semantics: bool = False) -> JobFitResult` — composes Tasks 9–11: components → base → missing skills → penalties → `overall = clamp(base − Σ points, 0, 100)` → blockers → status (§7.5, from `cfg.status_thresholds`) → confidence → explanations.

- [ ] **Step 1: Failing tests**

`test_explain.py`:

```python
from app.scoring.config import ScoringConfig
from app.scoring.scorer import JobFitScorer
from app.semantic.fake_fixtures import ch, nl, sc
from tests.conftest import make_semantic, make_profile

def texts(result, section): return [e.text for e in result.explanations if e.section == section]

def test_hedging_bands():
    s = JobFitScorer()
    plain = s.calculate(make_semantic(android_relevance=sc(3.5, 5, conf=0.85)), make_profile(), ScoringConfig())
    likely = s.calculate(make_semantic(android_relevance=sc(3.5, 5, conf=0.7)), make_profile(), ScoringConfig())
    unsure = s.calculate(make_semantic(android_relevance=sc(3.5, 5, conf=0.4)), make_profile(), ScoringConfig())
    assert "Android is the main day-to-day work (3.5/4)" in texts(plain, "strength")
    assert "Likely: Android is the main day-to-day work (3.5/4)" in texts(likely, "strength")
    assert not any("Android is the main" in t for t in texts(unsure, "strength"))
    assert "android_relevance: confidence 0.40" in texts(unsure, "uncertain")

def test_notes_and_stale():
    r = JobFitScorer().calculate(make_semantic(), make_profile(), ScoringConfig(), stale_semantics=True)
    assert "Sponsorship: not stated" in texts(r, "note")
    assert "Security clearance: no explicit requirement detected" in texts(r, "note")
    assert "Profile changed since this evaluation — re-evaluate for accurate results" in texts(r, "concern")
    assert r.stale_semantics

def test_title_vs_scope_and_years():
    sem = make_semantic(title_level=ch("staff", 0.9, options="Seniority"), seniority=ch("senior", 0.85, options="Seniority"),
                        min_years_required=ch("y8_10", 0.9, options="YearsBucket"))
    r = JobFitScorer().calculate(sem, make_profile(years_experience=6), ScoringConfig())
    assert "Title reads Staff; scope reads Senior" in texts(r, "concern")
    assert "Asks 8–10 years; profile says 6" in texts(r, "concern")
```

Bucket display labels: `y0_2` "0–2", `y3_4` "3–4", `y5_7` "5–7", `y8_10` "8–10", `y11_plus` "11+"; years rendered with `:g`.

`test_scorer_cases.py` — §13.1 cases through the fake fixtures:

```python
import pytest
from app.scoring.config import ScoringConfig
from app.scoring.scorer import JobFitScorer
from app.semantic.fake_evaluator import FakeJobSemanticEvaluator
from app.semantic.fake_fixtures import FIXTURES
from tests.conftest import make_profile, make_job

IC_STAFF = dict(preferred_roles=["Staff Android Engineer"], preferred_levels=["staff", "principal"],
                preferred_role_families=["android_native", "kotlin_multiplatform"], preferred_domains=["fintech"],
                remote_preference="remote", management_preference="ic")

async def score(name, **profile_kw):
    profile = make_profile(**{**IC_STAFF, **profile_kw})
    job = make_job(**FIXTURES[name]["posting"], external_id=f"fixture:{name}")
    sem = await FakeJobSemanticEvaluator().evaluate(profile, job)
    return sem, JobFitScorer().calculate(sem, profile, ScoringConfig())

def concerns(r): return [e.text for e in r.explanations if e.section == "concern"]

async def test_android_staff_perfect():
    sem, r = await score("android_staff_perfect")
    assert r.status == "STRONG_MATCH" and not r.hard_blockers and r.overall_score >= 85

async def test_flutter_heavy():
    sem, r = await score("flutter_heavy", avoided_role_families=["flutter"],
                         preferred_role_families=["android_native"])
    assert sem.android_relevance.score <= 1.5 and sem.cross_platform_intensity.score >= 3
    assert "avoided_tech_heavy" in {p.type for p in r.penalties}

async def test_engineering_manager():
    sem, r = await score("engineering_manager")
    assert sem.management_intensity.score >= 3
    assert "management_heavy_for_ic" in {p.type for p in r.penalties}
    assert next(c for c in r.components if c.name == "management").value < 0.3

async def test_clearance_required():
    _, r = await score("clearance_required", blocker_facts={"can_meet_clearance_requirement": False})
    assert r.status == "BLOCKED" and r.hard_blockers[0].evidence
    _, r = await score("clearance_required")
    assert r.status != "BLOCKED" and any("security clearance" in c for c in concerns(r))

async def test_gov_contractor_no_clearance():
    _, r = await score("gov_contractor_no_clearance", blocker_facts={"can_meet_clearance_requirement": False})
    assert not r.hard_blockers and not r.possible_blockers and not any("clearance" in c for c in concerns(r))

async def test_no_sponsorship_info():
    sem, r = await score("no_sponsorship_info", blocker_facts={"needs_visa_sponsorship": True})
    assert sem.work_authorization_signal.value == "not_stated" and not r.hard_blockers
    assert "Sponsorship: not stated" in [e.text for e in r.explanations if e.section == "note"]

async def test_explicit_no_sponsorship():
    _, r = await score("explicit_no_sponsorship", blocker_facts={"needs_visa_sponsorship": True})
    assert [b.type for b in r.hard_blockers] == ["no_sponsorship"] and r.status == "BLOCKED"

async def test_staff_title_senior_scope():
    _, r = await score("staff_title_senior_scope")
    assert "Title reads Staff; scope reads Senior" in concerns(r)

@pytest.mark.parametrize("score_value,status", [(85, "STRONG_MATCH"), (84.9, "GOOD_MATCH"), (70, "GOOD_MATCH"), (55, "REVIEW"), (54.9, "LOW_MATCH")])
def test_status_thresholds(score_value, status):
    from app.scoring.scorer import status_for
    assert status_for(score_value, blocked=False, cfg=ScoringConfig()) == status
    assert status_for(score_value, blocked=True, cfg=ScoringConfig()) == "BLOCKED"

async def test_confidence_never_changes_status():
    _, r = await score("android_staff_perfect")
    assert r.aggregate_confidence != r.overall_score / 100
```

- [ ] **Step 2–4:** FAIL → implement → PASS (tune fixture numbers from Task 7 only if a case test's expectation is not met by the §7.12 formulas — never tune the formulas).
- [ ] **Step 5:** commit `feat(scoring): explanations and JobFitScorer`.

---

### Task 13: ORM tables and Alembic migration

**Files:** Create `backend/app/db.py`, `backend/app/models.py`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_initial.py`, `backend/app/repo.py`; Test `tests/api/test_migrations.py`

**Produces:**
- `db.py`: `class Base(DeclarativeBase)`; `make_engine(url)` (creates `data/` dir for sqlite file URLs; `connect` event sets `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`); `make_session_factory(engine) -> sessionmaker[Session]` (`expire_on_commit=False`); `run_migrations(url)` (programmatic `alembic upgrade head` using `backend/alembic.ini` path resolved from `__file__`).
- `models.py`: `ProfileVersion`, `JobPostingRow`, `JobEvaluation`, `ScoringConfigRow`, `FitResult` with exactly the §8 columns; FKs `ondelete="CASCADE"` for `job_evaluations.job_id` and `fit_results.evaluation_id`; relationships `JobPostingRow.evaluations` (cascade delete-orphan, passive_deletes), `JobEvaluation.fit_results`, `JobPostingRow.current_fit_result` (`foreign_keys=[current_fit_result_id]`, `post_update=True`), `FitResult.evaluation`, `FitResult.scoring_config`. `current_fit_result_id` FK uses `ondelete="SET NULL"` and `use_alter=True`.
- `repo.py`: `current_profile(session) -> ProfileVersion | None` (latest `created_at`); `to_domain_profile(row) -> CandidateProfile`; `to_domain_job(row) -> JobPosting`; `active_config(session) -> ScoringConfigRow`; `ensure_default_config(session)` (inserts version 1 when table empty); `headline_columns(sem: SemanticJobEvaluation) -> dict` (§8 note).
- `alembic/env.py` reads URL from `config.get_main_option("sqlalchemy.url")` overridden by `Settings().database_url`, `target_metadata = Base.metadata`, `render_as_batch=True`.

- [ ] **Step 1: Failing test**

```python
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from app.db import make_engine, run_migrations, Base
import app.models  # noqa: F401

def test_migration_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    run_migrations(url)
    engine = make_engine(url)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
    assert {"profile_versions", "job_postings", "job_evaluations", "scoring_configs", "fit_results"} <= set(inspect(engine).get_table_names())
```

- [ ] **Step 2:** FAIL. **Step 3:** implement `db.py`/`models.py`/`repo.py`; `uv run alembic init alembic`, edit `env.py`; generate `uv run alembic revision --autogenerate -m initial --rev-id 0001` against an empty temp DB (`DATABASE_URL=sqlite:///./data/tmp_gen.db`), then delete that DB file. **Step 4:** PASS. **Step 5:** commit `feat(backend): ORM tables and initial migration`.

---

### Task 14: Pipeline worker and re-scoring

**Files:** Create `backend/app/pipeline/worker.py`, `backend/app/main.py` (lifespan only, routers added in Task 15), `backend/app/api/deps.py`; Test `tests/api/test_worker.py`

**Produces:**
- `class EvaluationWorker(session_factory, evaluator: JobSemanticEvaluator, workers: int)`: `start()`, `async stop()`, `enqueue(evaluation_id: UUID)`, `depth` property, `requeue_unfinished()` (pending+running, oldest first), `async evaluate_job(evaluation_id)` (§10 steps; on exception marks failed with `SemanticEvaluationError.sanitized()` or `type(e).__name__`; `PostingOrResumeTooLong` and `MalformedTypeSafeResponse` use class name + message).
- `create_evaluation(session, job_id, profile_version_id) -> JobEvaluation` (status pending; commit is caller's).
- `score_evaluation(session, evaluation: JobEvaluation, profile_row, config_row) -> FitResult` — builds `SemanticJobEvaluation` from `signals` + `raw_typesafe_response`, `stale_semantics = evaluation.profile_version.semantic_hash != profile_row.semantic_hash`, inserts fit result, sets job's `current_fit_result_id`.
- `rescore_all(session) -> int` — for every job, its latest succeeded evaluation → `score_evaluation` with current profile + active config; returns count.
- `create_app(settings: Settings | None = None, evaluator: JobSemanticEvaluator | None = None) -> FastAPI`; lifespan: `configure_logging`, `settings.validate_for_startup()` (skipped when an evaluator is injected), `run_migrations`, `ensure_default_config`, build evaluator (`fake` → `FakeJobSemanticEvaluator()`; `typesafe` → `TypeSafeJobSemanticEvaluator(key, model, budget, Semaphore(max_concurrency))`), start worker, requeue; store on `app.state.{settings, session_factory, worker, evaluator}`.
- `deps.py`: `get_session(request)` generator; `get_worker(request)`.
- Logs `evaluation.enqueued|started|completed|failed` with the §12 fields.

- [ ] **Step 1: Failing tests** (`tests/conftest.py` gains an `app_client` fixture: `create_app(Settings(database_url=f"sqlite:///{tmp_path}/t.db", evaluator="fake", evaluation_workers=2))` inside `TestClient(...)` context, plus `wait_for(client, evaluation_id)` polling `GET /api/evaluations/{id}` up to 5 s. The worker test uses the app objects directly:

```python
import asyncio
from app.config import Settings
from app.main import create_app
from app.models import JobEvaluation, JobPostingRow, ProfileVersion
from app.pipeline.worker import create_evaluation
from app.domain import DEFAULT_TRACKED_SKILLS
from fastapi.testclient import TestClient

class Exploding:
    model = "fake"
    async def evaluate(self, profile, job):
        from app.semantic.evaluator import SemanticEvaluationError
        raise SemanticEvaluationError("TypeSafeBadRequestError", 400, "req-1")

def seed(session_factory):
    with session_factory() as s:
        p = ProfileVersion(resume_text="Android", preferences={}, blocker_facts={},
                           tracked_skills=[x.model_dump() for x in DEFAULT_TRACKED_SKILLS], semantic_hash="h")
        j = JobPostingRow(company="A", title="B", description="Build Android apps with Kotlin. " * 3, source="manual", content_hash="c")
        s.add_all([p, j]); s.flush()
        e = create_evaluation(s, j.id, p.id); s.commit()
        return e.id

def test_failed_evaluation_is_sanitized(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path}/t.db", evaluator="fake"), evaluator=Exploding())
    with TestClient(app):
        eid = seed(app.state.session_factory)
        asyncio.run(app.state.worker.evaluate_job(eid))
        with app.state.session_factory() as s:
            e = s.get(JobEvaluation, eid)
            assert e.status == "failed" and "req-1" in e.error and e.finished_at

def test_startup_requeues_pending(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path}/t.db", evaluator="fake")
    first = create_app(settings)
    with TestClient(first):
        pass
    eid = seed(first.state.session_factory)   # pending row written while no app is running
    second = create_app(settings)
    with TestClient(second) as client:
        for _ in range(50):
            with second.state.session_factory() as s:
                if s.get(JobEvaluation, eid).status == "succeeded":
                    break
            client.get("/api/health")
        else:
            raise AssertionError("pending evaluation was not re-queued")
```

(The health route is added in Task 17; until then this test uses `asyncio.run(asyncio.sleep(0.1))` in the loop — replace with the health call in Task 17.)

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(pipeline): evaluation worker and re-scoring`.

---

### Task 15: Profile API

**Files:** Create `backend/app/api/profile.py`; Modify `backend/app/main.py` (include router); Test `tests/api/test_profile.py`

**Produces:** `GET /api/profile` → `CandidateProfile` JSON + `version_id`; `PUT /api/profile` body `CandidateProfileIn` → `{profile, change_kind, affected_jobs, rescored}` (§9; identical content → `none`, no new row); `POST /api/profile/resume/extract` (§9; 413 over 5 MB, 415 other types, text via pypdf/python-docx/utf-8 decode). `affected_jobs` = count of jobs whose latest succeeded evaluation's profile version `semantic_hash` ≠ new hash (only for `semantic`).

- [ ] **Step 1: Failing tests**

```python
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
    assert app_client.post("/api/profile/resume/extract", files={"file": ("r.txt", b"Kotlin dev", "text/plain")}).json() == {"text": "Kotlin dev"}
    buf = io.BytesIO(); d = Document(); d.add_paragraph("Compose expert"); d.save(buf)
    r = app_client.post("/api/profile/resume/extract", files={"file": ("r.docx", buf.getvalue(), "application/octet-stream")})
    assert "Compose expert" in r.json()["text"]
    assert app_client.post("/api/profile/resume/extract", files={"file": ("r.exe", b"x", "application/octet-stream")}).status_code == 415
    big = b"x" * (5 * 1024 * 1024 + 1)
    assert app_client.post("/api/profile/resume/extract", files={"file": ("r.txt", big, "text/plain")}).status_code == 413
```

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(api): profile versions and resume extraction`.

---

### Task 16: Jobs and evaluate API (definition-of-done flow)

**Files:** Create `backend/app/ingest/normalize.py`, `backend/app/api/jobs.py`, `backend/app/api/evaluations.py`; Modify `main.py`; Tests `tests/api/test_flow.py`, `tests/api/test_jobs.py`

**Produces:**
- `content_hash(company, title, description) -> str` (§5.3); `get_or_create_job(session, data: JobPostingIn) -> tuple[JobPostingRow, bool]`.
- `POST /api/jobs` (201 created / 200 existing, body `{job, created}`), `GET /api/jobs/{id}` (`{job, evaluation, fit_result, latest_evaluation_status}` where `evaluation` is the evaluation behind the current fit result including `signals`), `DELETE /api/jobs/{id}` (204), `POST /api/jobs/{id}/evaluate` (202/409/404), `POST /api/jobs/reevaluate` (202), `POST /api/evaluate` (§9 incl. reuse), `GET /api/evaluations?job_id=`, `GET /api/evaluations/{id}` (full incl. `raw_typesafe_response`, `fit_results`), `GET /api/evaluations/{id}/request` (§6.7: `{states: {job, fit}, questions: [{id, state, body}], question_set_hash, hash_matches}`).
- Serializers in `api/jobs.py`: `job_out(row)`, `evaluation_out(row, full: bool)`, `fit_out(row)` (merges columns + `details`).

- [ ] **Step 1: Failing tests** (`test_flow.py` — §13.2 definition of done)

```python
from app.semantic.fake_fixtures import FIXTURES
from tests.api.test_profile import body
from tests.conftest import wait_for

def posting(name="clearance_required", **over):
    return {**FIXTURES[name]["posting"], "external_id": f"fixture:{name}", **over}

def test_definition_of_done_flow(app_client):
    assert app_client.post("/api/evaluate", json=posting()).status_code == 409
    app_client.put("/api/profile", json={**body(), "blocker_facts": {"can_meet_clearance_requirement": False}})
    r = app_client.post("/api/evaluate", json=posting())
    assert r.status_code == 202 and r.json()["created"] and not r.json()["reused"]
    wait_for(app_client, r.json()["evaluation_id"])
    detail = app_client.get(f"/api/jobs/{r.json()['job']['id']}").json()
    fit = detail["fit_result"]
    assert fit["status"] == "BLOCKED" and fit["hard_blockers"][0]["type"] == "security_clearance"
    assert detail["evaluation"]["signals"]["all_lines"] and fit["explanations"]
    assert "missing_skills" in fit and "components" in fit

def test_reuse_and_dedupe(app_client):
    app_client.put("/api/profile", json=body())
    first = app_client.post("/api/evaluate", json=posting("android_staff_perfect")).json()
    wait_for(app_client, first["evaluation_id"])
    again = app_client.post("/api/evaluate", json=posting("android_staff_perfect", company="  " + FIXTURES["android_staff_perfect"]["posting"]["company"].upper())).json()
    assert again["reused"] and not again["created"] and again["evaluation_id"] == first["evaluation_id"]

def test_history_retained_and_delete_cascade(app_client):
    app_client.put("/api/profile", json=body())
    first = app_client.post("/api/evaluate", json=posting("android_staff_perfect")).json()
    job_id = first["job"]["id"]
    wait_for(app_client, first["evaluation_id"])
    second = app_client.post(f"/api/jobs/{job_id}/evaluate")
    assert second.status_code == 202
    wait_for(app_client, second.json()["evaluation_id"])
    history = app_client.get("/api/evaluations", params={"job_id": job_id}).json()
    assert len(history) == 2 and all(h["fit_results"] for h in history)
    rebuilt = app_client.get(f"/api/evaluations/{first['evaluation_id']}/request").json()
    assert rebuilt["hash_matches"] and "candidate" in rebuilt["states"]["fit"]
    assert app_client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert app_client.get(f"/api/evaluations/{first['evaluation_id']}").status_code == 404
```

`test_jobs.py`: `POST /api/jobs` twice with whitespace/case variants → second `created: false` same id; invalid body → 422; `GET /api/jobs/{random uuid}` → 404.

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(api): jobs, evaluate flow, evaluation history and debug rebuild`.

---

### Task 17: Settings, meta, health, re-scoring on profile/config change

**Files:** Create `backend/app/api/settings.py`, `backend/app/api/meta.py`; Modify `api/profile.py` (call `rescore_all`), `main.py`; Test `tests/api/test_settings.py`; Modify `tests/api/test_worker.py` (use `/api/health` in loop)

**Produces:** `GET /api/settings/scoring` → `{version, config, defaults}`; `PUT /api/settings/scoring` body `ScoringConfig` → `{version, rescored}`; `GET /api/meta` → `{enums: {name: [{value, label}]}, default_tracked_skills, evaluator_version, model}`; `GET /api/health` → §9 fields. Profile PUT (scoring_only or semantic) calls `rescore_all` and returns `rescored`.

- [ ] **Step 1: Failing tests**

```python
from app.scoring.config import ScoringConfig
from tests.api.test_flow import posting
from tests.api.test_profile import body
from tests.conftest import wait_for

def evaluated(client, name="android_staff_perfect"):
    client.put("/api/profile", json=body())
    r = client.post("/api/evaluate", json=posting(name)).json()
    wait_for(client, r["evaluation_id"])
    return r["job"]["id"]

def test_settings_change_rescores_without_evaluator_calls(app_client, monkeypatch):
    job_id = evaluated(app_client)
    before = app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]
    async def boom(*a, **k): raise AssertionError("evaluator called")
    monkeypatch.setattr(app_client.app.state.evaluator, "evaluate", boom)
    cfg = ScoringConfig().model_dump()
    cfg["status_thresholds"] = {"strong_match": 99, "good_match": 98, "review": 97}
    r = app_client.put("/api/settings/scoring", json=cfg).json()
    assert r == {"version": 2, "rescored": 1}
    after = app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]
    assert after["id"] != before["id"] and after["status"] == "LOW_MATCH"
    assert app_client.put("/api/settings/scoring", json={**cfg, "weights": {**cfg["weights"], "technical": -1}}).status_code == 422

def test_profile_changes_rescore_and_flag_stale(app_client):
    job_id = evaluated(app_client)
    r = app_client.put("/api/profile", json=body(management_preference="manager")).json()
    assert r["change_kind"] == "scoring_only" and r["rescored"] == 1
    assert not app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]["stale_semantics"]
    r = app_client.put("/api/profile", json=body(preferred_roles=["iOS Lead"])).json()
    assert r["change_kind"] == "semantic" and r["affected_jobs"] == 1
    assert app_client.get(f"/api/jobs/{job_id}").json()["fit_result"]["stale_semantics"]

def test_meta_and_health(app_client):
    meta = app_client.get("/api/meta").json()
    assert {"value": "android_native", "label": "Android native"} in meta["enums"]["RoleFamily"]
    assert len(meta["default_tracked_skills"]) == 18
    health = app_client.get("/api/health").json()
    assert health == {"status": "ok", "evaluator": "fake", "model": "fake", "api_key_configured": False, "queue_depth": 0}
```

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(api): scoring settings, meta, health, automatic re-scoring`.

---

### Task 18: Dashboard list (filters, sort, stats) and batch

**Files:** Modify `backend/app/api/jobs.py`; Test `tests/api/test_jobs.py` (append)

**Produces:** `GET /api/jobs` → `{rows: [...], stats: {total, evaluated, strong, good, review, low, blocked, pending, failed}, total_filtered}` with every §9 query parameter; row fields `id, company, title, location, source, created_at, overall_score, status, aggregate_confidence, needs_review, role_family, seniority, domain, work_arrangement, kmp_requirement, work_authorization_signal, android_relevance, security_clearance_required, evaluation_status, evaluation_error, latest_evaluation_id`. Filtering and sorting in Python over all jobs (`# ponytail: in-memory filter/sort; move to SQL if job count grows past ~10k`). `POST /api/jobs/batch` (§9; `jobs` max 500 → 422; `auto_evaluate` requires a profile → 409).

- [ ] **Step 1: Failing tests** (append to `test_jobs.py`)

```python
from app.semantic.fake_fixtures import FIXTURES
from tests.api.test_profile import body
from tests.conftest import wait_for

NAMES = ["android_staff_perfect", "flutter_heavy", "engineering_manager", "clearance_required"]

def batch(client):
    client.put("/api/profile", json={**body(preferred_levels=["staff"], management_preference="ic"),
                                     "blocker_facts": {"can_meet_clearance_requirement": False}})
    jobs = [{**FIXTURES[n]["posting"], "external_id": f"fixture:{n}"} for n in NAMES]
    r = client.post("/api/jobs/batch", json={"jobs": jobs + jobs[:1], "auto_evaluate": True}).json()
    assert (r["created"], r["existing"], len(r["evaluation_ids"])) == (4, 1, 4)
    for eid in r["evaluation_ids"]:
        wait_for(client, eid)

def test_batch_list_sort_filter_stats(app_client):
    batch(app_client)
    data = app_client.get("/api/jobs").json()
    scores = [row["overall_score"] for row in data["rows"]]
    assert scores == sorted(scores, reverse=True)
    assert data["stats"]["total"] == 4 and data["stats"]["evaluated"] == 4 and data["stats"]["blocked"] == 1
    assert [r["status"] for r in app_client.get("/api/jobs", params={"status": ["BLOCKED"]}).json()["rows"]] == ["BLOCKED"]
    assert len(app_client.get("/api/jobs", params={"clearance": "required"}).json()["rows"]) == 1
    assert len(app_client.get("/api/jobs", params={"role_family": ["flutter"]}).json()["rows"]) == 1
    q = app_client.get("/api/jobs", params={"q": FIXTURES["flutter_heavy"]["posting"]["company"][:4].lower()}).json()["rows"]
    assert len(q) >= 1
    by_company = app_client.get("/api/jobs", params={"sort": "company", "order": "asc"}).json()["rows"]
    assert [r["company"] for r in by_company] == sorted(r["company"] for r in by_company)

def test_unscored_jobs_sort_last(app_client):
    batch(app_client)
    app_client.post("/api/jobs", json={"company": "Zed", "title": "Android", "description": "Android work " * 10})
    assert app_client.get("/api/jobs").json()["rows"][-1]["overall_score"] is None

def test_batch_limit(app_client):
    job = {"company": "A", "title": "B", "description": "x" * 60}
    assert app_client.post("/api/jobs/batch", json={"jobs": [job] * 501, "auto_evaluate": False}).status_code == 422
```

- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `feat(api): dashboard list with filters, stats, batch import`.

---

### Task 19: Wiring, Makefile, full verification

**Files:** Modify `Makefile`, `backend/.env.example`, root `CLAUDE.md` (Commands section: mark backend commands real)

- [ ] **Step 1:** `Makefile` backend targets:

```make
.PHONY: setup dev test test-live migrate
setup:
	cd backend && uv sync
dev:
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
test:
	cd backend && uv run pytest
test-live:
	cd backend && uv run pytest -m live
migrate:
	cd backend && uv run alembic upgrade head
```

`app/main.py` exposes module-level `app = create_app()` built lazily via uvicorn `--factory`? Use `--factory app.main:create_app` instead to avoid import-time settings validation; Makefile uses `uv run uvicorn --factory app.main:create_app ...`.

- [ ] **Step 2:** `.env.example` lists every §14 variable with defaults (`EVALUATOR=fake` commented alternative).
- [ ] **Step 3:** Run `make test` → all pass. Run `cd backend && EVALUATOR=fake uv run uvicorn --factory app.main:create_app --port 8765 &`, `curl -s 127.0.0.1:8765/api/health` → `{"status":"ok","evaluator":"fake",...}`; stop the server.
- [ ] **Step 4:** Commit `chore: Makefile and env example for backend`.
