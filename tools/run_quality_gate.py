"""TorqPro repository quality gate -- Faz 2.8.10 Stage 4.

One deterministic, repository-level command developers and CI can run
from the repository root:

    python tools/run_quality_gate.py

Runs a fixed, ordered sequence of checks and stops at the first
failure, so a person (or CI) gets a single clear signal of exactly
which gate failed and why, rather than a wall of unrelated output from
running several separate commands by hand. Every check already exists
as an established project command (``git diff --check``,
``python -m compileall``, ``pytest -q``, the JS harnesses under
``tests/js/``); this script only orders and reports them -- it does
not reimplement or duplicate any of their underlying logic.

Standard library only, plus the project's own existing dependencies
(this script shells out to ``git``, ``node``, and the project's own
``python -m compileall`` / ``pytest`` -- it does not import any new
package). No coverage threshold and no full-tree ``flake8`` are
enforced here: Stage 1's Quality Gap Report found flake8 unscoped
against the full tree currently reports ~2175 pre-existing style-debt
findings unrelated to correctness, so enforcing it here would make
this gate fail for reasons unrelated to the change being validated;
that remains a scoped, per-diff practice instead (see
docs/phase_2_8/phase_2_8_10_stage1_quality_gap_report.md Sec. 2.4).

Order (fixed, deterministic -- see ``default_gates()``):
  1. git diff --check
  2. Python compile validation (backend/, tests/)
  3. JSON validity (repository-owned *.json files, sorted)
  4. TR/EN key parity (tests/test_i18n_key_parity.py)
  5. JavaScript harnesses (tests/js/run_*.js -- Node required, never
     silently skipped)
  6. Full pytest suite (pytest -q)

Exit code 0 = every gate passed. Non-zero = the first failing gate's
exit behavior is propagated; that gate's underlying command output is
printed in full so nothing about the failure is hidden.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directory *names* (not full paths) excluded from the JSON-file walk:
# version control internals, virtualenvs, caches, generated/runtime
# output, and vendor/third-party trees. Matched against every path
# component seen during the walk, at any depth, so e.g. a
# `frontend/node_modules/pkg/data.json` is excluded exactly like a
# top-level one would be.
EXCLUDED_DIR_NAMES = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".tox",
    "venv", ".venv", "env", ".env",
    "node_modules", "runtime", "dist", "build", "htmlcov",
    "vendor", "third_party",
    ".idea", ".vscode", ".cache",
})

JS_HARNESS_FILENAMES: tuple[str, ...] = (
    "run_assembly_intelligence_tests.js",
    "run_i18n_tests.js",
    "run_joint_analysis_tests.js",
    "run_material_intelligence_tests.js",
    "run_washer_resolution_report_tests.js",
    "run_joint_revision_list_ux_tests.js",
    "run_washer_resolution_queue_tests.js",
    "run_washer_resolution_decision_form_tests.js",
    "run_washer_resolution_decision_history_tests.js",
)

NODE_MISSING_MESSAGE = (
    "Node.js is required to run the JavaScript regression harnesses "
    "(tests/js/run_*.js) but `node` was not found on PATH.\n"
    "Install Node.js (https://nodejs.org) and ensure `node` is on PATH, "
    "then re-run this quality gate. The JavaScript checks are never "
    "silently skipped -- Node absence is a gate failure, not a pass."
)


@dataclass(frozen=True)
class GateOutcome:
    """Result of running one gate's check."""
    passed: bool
    output: str = ""


@dataclass(frozen=True)
class Gate:
    """One named, ordered quality-gate check."""
    name: str
    scope: str
    run: Callable[[], GateOutcome] = field(repr=False)


# ---------------------------------------------------------------
# 1. git diff --check
# ---------------------------------------------------------------

def _run_git_diff_check(repo_root: Path, *, runner=subprocess.run) -> GateOutcome:
    result = runner(
        ["git", "diff", "--check"], cwd=str(repo_root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        return GateOutcome(False, result.stdout + result.stderr)
    return GateOutcome(True, "git diff --check: no whitespace/conflict-marker errors.")


# ---------------------------------------------------------------
# 2. Python compile validation
# ---------------------------------------------------------------

def _run_python_compileall(repo_root: Path, *, runner=subprocess.run) -> GateOutcome:
    result = runner(
        [sys.executable, "-m", "compileall", "-q", "backend", "tests"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        return GateOutcome(False, result.stdout + result.stderr)
    return GateOutcome(True, "python -m compileall -q backend tests: OK")


# ---------------------------------------------------------------
# 3. JSON validity (repository-owned *.json files)
# ---------------------------------------------------------------

def find_repository_json_files(
    root: Path, excluded_dir_names: frozenset = EXCLUDED_DIR_NAMES,
) -> list[Path]:
    """All ``*.json`` files under ``root``, excluding any path that
    passes through a directory named in ``excluded_dir_names`` at any
    depth. Returns a list sorted by string path -- deterministic
    regardless of the underlying filesystem's directory-entry order.
    """
    root = Path(root)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in place so os.walk never
        # descends into them; also keeps traversal order itself
        # deterministic (final result is sorted anyway).
        dirnames[:] = sorted(d for d in dirnames if d not in excluded_dir_names)
        for filename in sorted(filenames):
            if filename.endswith(".json"):
                found.append(Path(dirpath) / filename)
    return sorted(found)


def validate_json_files(paths: Sequence[Path]) -> GateOutcome:
    """Parse every path in ``paths`` (already expected to be in
    deterministic order) as JSON. Stops at, and reports, the first
    invalid file -- exact filename plus the underlying parse error --
    rather than collecting every failure, matching this script's
    overall stop-at-first-failure design.
    """
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                json.load(fh)
        except json.JSONDecodeError as exc:
            return GateOutcome(False, f"Invalid JSON in {path}: {exc}")
        except OSError as exc:
            return GateOutcome(False, f"Could not read {path}: {exc}")
    return GateOutcome(True, f"{len(paths)} repository JSON file(s) validated.")


def _run_json_validation(repo_root: Path) -> GateOutcome:
    paths = find_repository_json_files(repo_root)
    return validate_json_files(paths)


# ---------------------------------------------------------------
# 4. TR/EN key parity
# ---------------------------------------------------------------

def _run_i18n_parity(repo_root: Path, *, runner=subprocess.run) -> GateOutcome:
    result = runner(
        [sys.executable, "-m", "pytest", "-q", "tests/test_i18n_key_parity.py"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        return GateOutcome(False, result.stdout + result.stderr)
    return GateOutcome(True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "OK")


# ---------------------------------------------------------------
# 5. JavaScript harnesses (Node required -- never silently skipped)
# ---------------------------------------------------------------

def _run_js_harnesses(repo_root: Path, *, runner=subprocess.run) -> GateOutcome:
    if shutil.which("node") is None:
        return GateOutcome(False, NODE_MISSING_MESSAGE)
    for filename in JS_HARNESS_FILENAMES:
        harness_path = repo_root / "tests" / "js" / filename
        result = runner(
            ["node", str(harness_path)], cwd=str(repo_root), capture_output=True, text=True,
        )
        if result.returncode != 0:
            return GateOutcome(
                False,
                f"{filename} FAILED (exit {result.returncode}):\n{result.stdout}{result.stderr}",
            )
    return GateOutcome(True, f"All {len(JS_HARNESS_FILENAMES)} JavaScript harnesses passed.")


# ---------------------------------------------------------------
# 6. Full pytest suite
# ---------------------------------------------------------------

def _run_full_pytest(repo_root: Path, *, runner=subprocess.run) -> GateOutcome:
    result = runner(
        [sys.executable, "-m", "pytest", "-q"], cwd=str(repo_root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        return GateOutcome(False, result.stdout + result.stderr)
    return GateOutcome(True, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "OK")


# ---------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------

def default_gates(repo_root: Path) -> list[Gate]:
    """The fixed, deterministic gate order. Always returns the same
    six gates in the same order for a given repo_root -- this is
    itself asserted by a focused test, since a future edit
    accidentally reordering or dropping a gate would otherwise be easy
    to miss."""
    return [
        Gate(
            "git diff --check",
            "working tree vs index (whitespace / conflict markers)",
            lambda: _run_git_diff_check(repo_root),
        ),
        Gate(
            "Python compile validation",
            "backend/ and tests/ (python -m compileall)",
            lambda: _run_python_compileall(repo_root),
        ),
        Gate(
            "JSON validity",
            "repository-owned *.json files (git/venv/cache/build/vendor excluded)",
            lambda: _run_json_validation(repo_root),
        ),
        Gate(
            "TR/EN key parity",
            "tests/test_i18n_key_parity.py",
            lambda: _run_i18n_parity(repo_root),
        ),
        Gate(
            "JavaScript harnesses",
            f"tests/js/{{{','.join(JS_HARNESS_FILENAMES)}}} (Node required)",
            lambda: _run_js_harnesses(repo_root),
        ),
        Gate(
            "Full pytest suite",
            "pytest -q",
            lambda: _run_full_pytest(repo_root),
        ),
    ]


def run_gates(gates: Sequence[Gate], *, stream=None) -> int:
    """Run ``gates`` in order, printing a PASS/FAIL section for each,
    and stop at the first failure. Returns 0 if every gate passed,
    1 otherwise. ``stream`` defaults to stdout; tests pass an
    in-memory buffer instead.
    """
    if stream is None:
        stream = sys.stdout
    total = len(gates)
    for index, gate in enumerate(gates, start=1):
        stream.write(f"\n[{index}/{total}] {gate.name}\n")
        stream.write(f"    scope: {gate.scope}\n")
        outcome = gate.run()
        status = "PASS" if outcome.passed else "FAIL"
        stream.write(f"    result: {status}\n")
        if outcome.output:
            for line in outcome.output.splitlines():
                stream.write(f"    | {line}\n")
        if not outcome.passed:
            stream.write(
                f"\nQuality gate FAILED at check {index}/{total}: {gate.name}\n"
            )
            return 1
    stream.write(
        f"\nQuality gate PASSED: all {total} checks succeeded. "
        "Repository is release-ready for this gate.\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    del argv  # no CLI arguments in Stage 4 -- fixed, deterministic order only
    gates = default_gates(REPO_ROOT)
    return run_gates(gates)


if __name__ == "__main__":
    sys.exit(main())
