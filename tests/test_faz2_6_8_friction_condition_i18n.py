"""Faz 2.6.8 -- TR/EN i18n foundation for the Friction Condition
workspace.

The actual regression assertions live in tests/js/run_i18n_tests.js
(a dependency-free Node script -- no npm packages, no jsdom -- that
extracts the real i18n/Friction Condition declarations straight out
of frontend/index.html via brace-counting and exercises them against
a small hand-built DOM/localStorage stub; see that file's module
docstring for the full rationale). This module is a thin pytest
wrapper around it, following the same subprocess-based pattern the
existing test_faz2_6_6_friction_condition_frontend_workspace.py file
already uses for `node --check` (see test_frontend_js_syntax_is_valid
there) -- just extended from a syntax check to an actual behavioral
run. Node is required, exactly as it already implicitly is for that
existing syntax test; this module additionally skips (rather than
erroring) when `node` is genuinely not on PATH, since that's an
environment-provisioning gap, not a code regression.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_i18n_tests.js"
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"

NODE_AVAILABLE = shutil.which("node") is not None

pytestmark = pytest.mark.skipif(
    not NODE_AVAILABLE, reason="node is not available on PATH in this environment"
)


def _run_harness() -> subprocess.CompletedProcess:
    assert HARNESS_PATH.exists(), f"harness missing: {HARNESS_PATH}"
    return subprocess.run(
        ["node", str(HARNESS_PATH)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_i18n_harness_all_assertions_pass():
    """Runs the full Node/vm regression suite (default language,
    TR<->EN switching, localStorage persistence and fallback, no
    unnecessary refetch on switch, dynamic content translation, enum
    coverage and safe fallback, API/JSON-key stability, and the
    documented backend free-text limitation). Fails clearly, with the
    harness's own per-assertion failure list, on any non-zero exit.
    """
    result = _run_harness()
    assert result.returncode == 0, (
        "i18n harness reported failures:\n" + result.stdout + result.stderr
    )


def test_i18n_harness_reports_a_nonzero_assertion_count():
    """Guards against a silently-empty or short-circuited run (e.g. an
    extraction exception swallowed somewhere) reporting a false
    all-clear -- the harness must have actually exercised assertions,
    not just exited 0 having run nothing."""
    result = _run_harness()
    m = re.search(r"(\d+) passed, (\d+) failed", result.stdout)
    assert m, (
        "harness output did not contain the expected 'N passed, N failed' summary:\n"
        + result.stdout
    )
    passed, failed = int(m.group(1)), int(m.group(2))
    assert failed == 0
    assert passed > 0, "harness ran zero assertions"


def test_harness_file_is_dependency_free():
    """No npm packages / package.json / node_modules were introduced
    -- the harness must stay pure Node `vm` + `fs`, matching the
    project's existing zero-frontend-dependency stance."""
    src = HARNESS_PATH.read_text(encoding="utf-8")
    assert "require('jsdom')" not in src
    assert "require(\"jsdom\")" not in src
    assert not (REPO_ROOT / "tests" / "js" / "package.json").exists()
    assert not (REPO_ROOT / "tests" / "js" / "node_modules").exists()


def test_harness_never_edits_the_real_frontend_file():
    """The var-conversion workaround for vm's let/const scoping quirk
    must only ever rewrite an in-memory copy of the extracted
    declarations -- frontend/index.html itself must still declare
    the Friction Condition workspace state with `let`, unchanged."""
    frontend_src = FRONTEND_PATH.read_text(encoding="utf-8")
    for name in ("FC_LIST", "FC_SELECTED_ID", "FC_COMPARE_ID", "FC_REQUEST_SEQ", "FC_LAST_REPORT"):
        assert re.search(r"\blet\s+" + name + r"\s*=", frontend_src), (
            f"{name} must remain declared with `let` in frontend/index.html"
        )
    harness_src = HARNESS_PATH.read_text(encoding="utf-8")
    assert "fs.readFileSync(FRONTEND_PATH" in harness_src
    # The harness must never open frontend/index.html for writing.
    assert "writeFileSync" not in harness_src
