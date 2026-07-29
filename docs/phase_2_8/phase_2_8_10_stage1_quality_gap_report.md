# Phase 2.8.10 — Stage 1: Quality Gap Report

**Status:** Analysis only. No production code modified.
**Baseline commit:** `d80046a` (main, up to date through Faz 2.8.9)
**Analysis environment:** clean clone, fresh venv, `pytest -q`, `pytest --cov=backend`, `flake8 --max-line-length=100 backend/`, `python -m compileall`, `node` v22.22.2.

## 1. Current state (verified, not assumed)

| Check | Result |
|---|---|
| `pytest -q` (full suite) | **1525 passed**, 0 failed, 0 skipped, 101.8s |
| `pytest --cov=backend` | **93% statement coverage** (6625 stmts, 444 missed) |
| `flake8 --max-line-length=100 backend/` (full-repo, unscoped) | **2175 findings** (pre-existing style debt — see §2.4) |
| `python -m compileall backend/ tools/ tests/` | clean, exit 0 |
| `node tests/js/run_*.js` (all 5 harnesses) | all pass (already covered by the 1525 above via subprocess wrappers) |
| TR/EN key parity (`I18N` object, `frontend/index.html`) | **1370 / 1370**, 0 missing either direction (verified by direct key-set diff, not by a repo test — see §3.1) |

The suite is green and coverage is high in absolute terms. The gaps below are architectural/process gaps, not failing tests.

## 2. Identified gaps

### 2.1 Coverage gaps (by module, from `--cov-report=term-missing`)

Modules below TorqPro's own newer-phase norm (≥94% is typical for Faz 2.6+/2.8.x modules):

| Module | Coverage | Missed stmts | Notes |
|---|---|---|---|
| `backend/joints/service.py` | 77% | 23 | Lowest in the tree. Missed lines cluster around error/exception branches (60, 65-72, 118, 140, 161-180). |
| `backend/app.py` | 82% | 193 | Largest module (1791 lines) and largest absolute miss count. Monolithic route file; misses are spread across admin/edge-case branches, not one feature. |
| `backend/production_validation/service.py` | 85% | 52 | Concentrated in less-common transition/error paths. |
| `backend/api/dependencies.py` | 81% | 4 | Small absolute number but proportionally low; auth-adjacent code, worth closing. |
| `backend/calculation_engine/assembly_intelligence.py` | 89% | 21 | |
| `backend/library/population.py` | 91% | 31 | Largest absolute miss after app.py/service.py. |
| `backend/calculation_engine/material_intelligence.py` | 91% | 15 | |

All other modules sit at 94–100%. No module in `backend/vdi2230_core`, `backend/standards`, `backend/engineering_core` (except `validation.py` at 91%), or the Faz 2.8.5/2.8.9 washer-resolution stack has a material gap.

**No coverage tool is currently part of the repo or CI.** `pytest-cov` is not in `requirements-dev.txt`; the 93% figure above was produced by installing it manually for this analysis. This means coverage regressions are currently invisible unless someone reruns this manually — there is no gate and no trend.

### 2.2 Test-architecture duplication (not test-assertion duplication)

- **25 of ~85 test files** hardcode the literal admin credential (`"Protype Lab"` / `"A1234"`) and **16 files** independently define a local `def auth(...)` / `def token(...)` helper that performs the same login POST. There is a root `tests/conftest.py`, but it only prepares environment/DB — it defines no shared `client` or `auth_headers` fixture. `tests/production_validation/conftest.py` shows the better pattern already exists in the repo (fixtures + shared builder functions) but was never lifted to the root.
- **The 5 JS regression harnesses** (`tests/js/run_*.js`, 450–4174 lines each) each independently re-implement the same ~150-200 lines of infrastructure: `extractScript()`, `extractFunctionDecl()`, `buildDom()`, `check()`, `checkIncludes()`, `checkNotIncludes()`. This was a deliberate per-phase choice (each harness's own docstring says "separate file on purpose... does not modify any existing, already-passing harness") and it has kept each phase's delivery isolated and safe — but it now means ~750-1000 lines of near-identical boilerplate exist five times over, and any future improvement to (e.g.) `buildDom()`'s DOM stub has to be manually propagated five times or drifts.
- Several root-level legacy test files (`test_data_versions.py`, `test_engine_library.py`, `test_data_upload_calibration.py`) independently re-implement the same "create data package → approve → activate" sequence with near-identical bodies rather than sharing a helper.

### 2.3 No repo-codified translation-parity gate

TR/EN key parity is currently **100% (1370/1370)**, but nothing in the repository enforces this as an invariant. Each feature's JS harness spot-checks a handful of keys relevant to that feature (e.g. i18n harness checks specific Friction Condition keys); no test walks the full `I18N.en` / `I18N.tr` key sets and asserts they are identical. A future phase could add an `en` key without its `tr` counterpart (or vice versa) and every existing test would still pass.

### 2.4 Quality-gate steps exist only as manual practice, not as repo/CI artifacts

The delivery protocol (flake8 scoped to changed files, `compileall`, JSON validity, determinism checks, `git diff --check`) is followed per-phase but is **not encoded anywhere in the repository**:
- `flake8` is not in `requirements-dev.txt` and there is no `.flake8`/`setup.cfg`/`tox.ini` configuration file. Running it unscoped against the full `backend/` tree currently surfaces **2175 findings**, overwhelmingly `E231`/`E225`/`E701`/`E702`/`E302` (missing whitespace, semicolon-joined statements, missing blank lines before defs) — i.e. pre-existing terse-style debt in `backend/app.py` and other early modules, not correctness bugs. This is exactly why the working convention is "scope to changed files only" — but that convention lives only in institutional memory, not in a committed script or CI step.
- `.github/workflows/ci.yml` runs only `pytest -q` after an import smoke check. It does **not** run flake8, does not run `compileall` explicitly (though import already exercises most of it), and does not declare a Node.js setup step even though 5 test files shell out to `node` via `subprocess`. Node happens to be preinstalled on GitHub's `ubuntu-latest` runner images, so those tests do execute today — but this is incidental (each wrapper uses `pytest.mark.skipif(not NODE_AVAILABLE)`, so a runner-image change that drops Node would silently skip these tests rather than fail CI).
- Determinism (byte-identical output across runs) is verified per-phase by 25 test files that reference it, but there is no single reusable "run twice, diff bytes" helper — each phase reimplements its own determinism check inline.
- There is no committed script equivalent to "generate patch + bundle + SHA256SUMS + verify on a fresh clone" — this is done by hand each phase per the delivery protocol.

### 2.5 No test categorization / pyramid markers

`docs/14_TESTING_STRATEGY.md` §1 defines a test pyramid (Unit / Integration / Engineering regression / E2E / Deployment), and §2 explicitly instructs that the early "legacy" tests (`test_smoke.py`, `test_engineering.py`, `test_engine_library.py`, `test_data_versions.py`, `test_golive_wizard.py`, `test_release_package.py`, `test_mobile_pwa.py`, `test_data_upload_calibration.py`, `test_cloud_deployment.py`, `test_enterprise_license.py`, `test_deployment_migration.py`, `test_quality_gate_release.py`) **"must be retained and reorganized, not discarded."** These are therefore not obsolete — they are intentionally-kept early-generation platform/deployment tests — but there is currently no `pytest.ini`, no registered custom markers, and no directory structure that reflects the pyramid. `pytest -m unit` (etc.) is not possible today; the only marker in use anywhere is the built-in `parametrize` (28 uses).

### 2.6 No dedicated obsolete/duplicate tests found at the assertion level

No test file was found to be a stale duplicate of another (i.e., testing the same behavior with the same assertions, safe to delete outright). The closest candidates are the boilerplate-duplication cases in §2.2, which are architecture-level, not correctness-level, duplication. **No test is recommended for deletion in this report.**

## 3. Summary of findings for Stage 2 planning (not implemented in this Stage)

1. Add `pytest-cov` to `requirements-dev.txt` and wire a coverage threshold/report into CI.
2. Close the three lowest-coverage modules (`joints/service.py` 77%, `app.py` 82%, `production_validation/service.py` 85%) with targeted, additive tests.
3. Introduce a root-level `auth_headers`/`client` fixture in `tests/conftest.py` (additive; does not require touching the 16 files that already work).
4. Introduce a single shared `tests/js/harness_common.js` module for the 5 JS harnesses' common extraction/DOM/assertion helpers (additive; existing harnesses keep working, future harnesses stop re-deriving the boilerplate).
5. Add one repo-wide TR/EN key-parity test (`I18N.en` keys == `I18N.tr` keys) as a permanent regression guard.
6. Commit the ad-hoc quality-gate steps (scoped flake8, compileall, determinism-diff, JSON validity) as a single reusable script/CI job instead of re-deriving them from memory each phase.
7. Register `pytest.ini` markers matching `docs/14_TESTING_STRATEGY.md`'s pyramid so suites can be selectively run.

None of the above is implemented in this Stage. See `phase_2_8_10_stage1_recommended_test_architecture.md` for the detailed proposal.
