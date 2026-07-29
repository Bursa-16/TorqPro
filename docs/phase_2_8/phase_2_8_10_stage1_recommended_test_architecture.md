# Phase 2.8.10 — Stage 1: Recommended Test Architecture (proposal)

**Status:** Proposal only. Nothing in this document is implemented. Subject to approval before any Stage 2 work begins. Every item is additive by design — none require touching existing passing tests or production code.

## 1. Design principles carried forward from the current codebase

- Zero external JS test dependencies (no jsdom/npm) — the existing `vm`-based extraction technique is sound and should be centralized, not replaced.
- Backend tests stay on plain `pytest` + `fastapi.testclient.TestClient` — no new test framework.
- Additive-only: every recommendation below can land without touching a single existing assertion.
- Legacy platform tests (§8 of the Test Inventory) are retained as-is per `docs/14_TESTING_STRATEGY.md` §2 — reorganization means re-labeling/re-locating with markers, not rewriting.

## 2. Proposed structure

### 2.1 Root fixture layer (`tests/conftest.py`)

Add, without removing anything currently there:
- `client` fixture wrapping `TestClient(app)`.
- `auth_headers` fixture (module- or session-scoped) performing the existing `"Protype Lab"`/`"A1234"` login once.
- Optional `second_reviewer_headers` fixture, generalized from the pattern already proven in `tests/production_validation/conftest.py`.

Existing files keep their local `auth()`/`token()` helpers working unchanged (no forced migration). New test files, and any file touched for another reason, adopt the shared fixture instead of re-defining a local helper. This mirrors exactly how `tests/production_validation/conftest.py` already works today — Stage 2 would just make the same facility available at the root.

### 2.2 Shared JS harness infrastructure (`tests/js/harness_common.js`)

Extract the six functions duplicated across all 5 existing harnesses (`extractScript`, `extractFunctionDecl`, `buildDom`, `check`, `checkIncludes`, `checkNotIncludes`) into one `require()`-able module. Existing harnesses are updated to `require('./harness_common')` **only when next touched for an unrelated reason** — not as a blanket rewrite in Stage 2, to keep the change additive and low-risk (per the "no unrelated refactoring" constraint). Any new Faz-2.8.10+ frontend harness is written against `harness_common.js` from day one.

### 2.3 Repo-wide TR/EN parity guard

New file: `tests/test_i18n_key_parity.py`. Pure Python, no Node dependency (keeps it running even if Node is ever unavailable): parses `frontend/index.html`, locates `const I18N = {...}` via brace counting (same technique already used by the JS harnesses, just ported to Python since this check doesn't need to *execute* the app code, only inspect its literal key set), extracts the `en` and `tr` object key sets, and asserts they are identical. On mismatch, the assertion message lists the exact keys missing from each side. This becomes a permanent regression guard for the 1370/1370 parity verified in Stage 1.

### 2.4 Coverage as a first-class, visible gate

- Add `pytest-cov` to `requirements-dev.txt`.
- Add a `[tool:pytest]` (or `pytest.ini`) `addopts` entry to always emit `--cov=backend --cov-report=term-missing` in local/CI runs, without failing the build on a threshold initially (avoids surprising an in-flight phase) — a hard `--cov-fail-under` threshold can be proposed once the 3 lowest-coverage modules (§2.1 of the Gap Report) are addressed, so the initial baseline is realistic rather than aspirational.
- CI (`ci.yml`) gains a step publishing the coverage summary (does not need external services — `term-missing` to the log is sufficient for this project's scale).

### 2.5 Explicit CI quality-gate step, codifying existing manual practice

Add one new CI step (and a corresponding local script, e.g. `tools/run_quality_gates.sh`, for parity with local dev) that runs, in order:
1. `python -m compileall backend/ tools/ tests/` (already implicit via import-check, made explicit and total).
2. `flake8 --max-line-length=100 <changed files>` — for CI, `<changed files>` is derived from `git diff --name-only origin/main...HEAD` on PRs (on `main` pushes, this step is skipped or run informationally, since full-tree flake8 currently reports 2175 pre-existing findings that are out of scope for any single phase to fix).
3. `actions/setup-node@v4` added explicitly to `ci.yml` before the `pytest` step, so the 5 JS-harness-wrapping tests are guaranteed to run (not silently skip) in CI regardless of future runner-image changes.
4. JSON validity check for any `backend/library/data/*.json` file touched in the diff (`python -m json.tool <file> > /dev/null`).

This does not change what individual phases must do — it just makes the "you already do this by hand" steps into something CI enforces so a future phase can't accidentally skip a step.

### 2.6 pytest markers matching the documented pyramid

Register in `pytest.ini`:
```ini
[pytest]
markers =
    unit: pure-function / domain-model tests, no TestClient
    integration: API/DB/auth/versioning tests via TestClient
    engineering_regression: golden-case and boundary-dataset tests
    frontend: JS-harness-wrapping tests (subprocess to node)
    deployment: Docker/health/migration/PWA/go-live tests
```
Existing tests are **not required to be retroactively marked in Stage 2** — markers are opt-in and additive; a full retroactive labeling pass (if wanted) would be its own later, explicitly-scoped phase given ~1525 test cases across 81 files. New tests from Phase 2.8.10 onward are written with the appropriate marker from the start. This alone unblocks `pytest -m unit` / `pytest -m frontend` style targeted runs going forward.

### 2.7 Targeted coverage additions (Stage 3+ implementation, not Stage 2 architecture work)

Once the architecture above exists, the three modules identified in the Gap Report (§2.1) — `backend/joints/service.py` (77%), `backend/app.py` (82%), `backend/production_validation/service.py` (85%) — get dedicated, additive test cases targeting their currently-missed branches (mostly error/exception paths). This is implementation work, sequenced after the architecture is in place so new tests can immediately use the new fixtures/markers rather than adding to the duplication problem they're meant to fix.

## 3. What this proposal deliberately does NOT include

- No rewrite of any of the 5 existing JS harnesses' internal logic — only extraction of literally-duplicated helper functions, applied opportunistically.
- No deletion or rewrite of any legacy platform test (§8 of the Inventory) — explicitly preserved per `docs/14_TESTING_STRATEGY.md`.
- No change to any production/backend module in this Stage.
- No hard coverage-failure threshold until the current gaps are closed (avoids blocking unrelated future phases on this phase's findings).
- No forced migration of the 16 files with local `auth()` helpers to the new fixture — coexistence is intentional.

## 4. Sequencing recommendation for Stage 2 (pending approval)

1. `tests/conftest.py` fixtures (§2.1) — lowest risk, purely additive.
2. `tests/test_i18n_key_parity.py` (§2.3) — self-contained, no dependency on other items.
3. `pytest.ini` + markers (§2.6) — no behavior change, just registration.
4. `pytest-cov` wiring (§2.4) — visibility before any threshold.
5. `tools/run_quality_gates.sh` + CI step (§2.5) — codifies existing practice.
6. `tests/js/harness_common.js` (§2.2) — highest line-count change; done carefully, harness-by-harness.
7. Targeted coverage additions (§2.7) — last, once the above scaffolding exists.

This ordering keeps each step independently reviewable and independently revertable, consistent with the delivery protocol's incremental, feature-branch-per-step approach used in prior Faz phases.
