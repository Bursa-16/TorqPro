"""Faz 2.8.16 Stage 5 -- focused tests proving
``tests/js/run_joint_revision_list_ux_tests.js`` is genuinely wired
into ``tools/run_quality_gate.py``'s canonical JS harness list, not
merely present on disk.

Loads ``tools/run_quality_gate.py`` the same way
``tests/test_run_quality_gate.py`` already does
(``importlib.util.spec_from_file_location``, registered in
``sys.modules`` before ``exec_module`` for ``@dataclass`` support --
see that file's own module docstring for why). Every test here
either inspects the pure ``JS_HARNESS_FILENAMES`` tuple directly or
injects a fake ``runner`` into ``_run_js_harnesses`` (mirroring
``tests/test_run_quality_gate.py``'s own ``_RecordingRunner``/
``_FakeCompletedProcess`` pattern) -- no real subprocess, no real
Node invocation, no network. This is "Option B" from the Stage 5
scope: a controlled runner-injection proof that a failing harness
fails the gate, rather than temporarily corrupting a real file on
disk.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "run_quality_gate.py"

NEW_HARNESS_FILENAME = "run_joint_revision_list_ux_tests.js"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_quality_gate_under_test_jrux", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def qg():
    return _load_module()


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _RecordingRunner:
    """Stand-in for subprocess.run: records every invoked command and
    returns a scripted sequence of results (or a fixed default) --
    byte-identical contract to tests/test_run_quality_gate.py's own
    helper of the same name, reimplemented locally here rather than
    imported across test modules (matching this repository's existing
    convention of per-test-file local fakes, e.g.
    tests/governance/test_joint_revision_bulk_api.py's own local
    ``gov_store`` fixture instead of importing one from a sibling
    test file)."""

    def __init__(self, results=None, default_returncode: int = 0):
        self._results = list(results) if results is not None else None
        self._default_returncode = default_returncode
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        if self._results is not None:
            return self._results.pop(0)
        return _FakeCompletedProcess(self._default_returncode)


# ---------------------------------------------------------------
# The new harness is genuinely part of the canonical list
# ---------------------------------------------------------------


def test_new_harness_is_in_the_canonical_js_harness_list(qg):
    assert NEW_HARNESS_FILENAME in qg.JS_HARNESS_FILENAMES


def test_new_harness_appears_exactly_once(qg):
    assert qg.JS_HARNESS_FILENAMES.count(NEW_HARNESS_FILENAME) == 1


def test_no_duplicate_harness_filenames_at_all(qg):
    names = qg.JS_HARNESS_FILENAMES
    assert len(names) == len(set(names))


def test_all_five_pre_existing_harnesses_are_still_present(qg):
    pre_existing = {
        "run_assembly_intelligence_tests.js",
        "run_i18n_tests.js",
        "run_joint_analysis_tests.js",
        "run_material_intelligence_tests.js",
        "run_washer_resolution_report_tests.js",
    }
    assert pre_existing <= set(qg.JS_HARNESS_FILENAMES)


def test_js_harness_total_count_is_eight(qg):
    # Faz 2.8.19 Stage 3 (Decision Entry Form frontend) appended an
    # 8th harness (run_washer_resolution_decision_form_tests.js)
    # after Stage 2's -- same additive-append pattern this phase
    # itself established.
    assert len(qg.JS_HARNESS_FILENAMES) == 8


def test_every_listed_harness_file_actually_exists_on_disk(qg):
    for filename in qg.JS_HARNESS_FILENAMES:
        path = REPO_ROOT / "tests" / "js" / filename
        assert path.is_file(), f"listed harness does not exist: {path}"


def test_harness_list_has_no_path_separators_no_repo_external_entries(qg):
    # Every entry is a bare filename resolved under tests/js/ by
    # _run_js_harnesses() -- never an absolute path, a relative path
    # escaping tests/js/, or a glob pattern.
    for filename in qg.JS_HARNESS_FILENAMES:
        assert "/" not in filename and "\\" not in filename
        assert "*" not in filename and "?" not in filename


def test_gate_step_count_is_still_six_despite_new_harness(qg):
    # Adding a harness *inside* step 5's list must never turn this
    # into a 7th top-level gate -- default_gates() must still return
    # exactly 6 Gate objects.
    assert len(qg.default_gates(REPO_ROOT)) == 6


# ---------------------------------------------------------------
# The new harness is genuinely *executed*, in order, via subprocess
# ---------------------------------------------------------------


def test_new_harness_is_invoked_via_node_subprocess(qg, monkeypatch):
    monkeypatch.setattr(qg.shutil, "which", lambda name: "/usr/bin/node")
    runner = _RecordingRunner(default_returncode=0)
    outcome = qg._run_js_harnesses(REPO_ROOT, runner=runner)
    assert outcome.passed is True
    invoked_paths = [call[1] for call in runner.calls]  # ["node", <path>]
    assert any(NEW_HARNESS_FILENAME in p for p in invoked_paths)
    assert all(call[0] == "node" for call in runner.calls)


def test_new_harness_runs_after_all_five_pre_existing_harnesses(qg, monkeypatch):
    # Confirms this phase's own harness still runs immediately after
    # the five harnesses that pre-existed it, at index 5 (position
    # 6 of what is now 7 -- Faz 2.8.19 Stage 2 appended one more
    # harness after this one, so this entry is no longer last, but
    # its own relative position after the original five is unchanged).
    monkeypatch.setattr(qg.shutil, "which", lambda name: "/usr/bin/node")
    runner = _RecordingRunner(default_returncode=0)
    qg._run_js_harnesses(REPO_ROOT, runner=runner)
    invoked_filenames = [Path(call[1]).name for call in runner.calls]
    assert invoked_filenames[5] == NEW_HARNESS_FILENAME
    assert invoked_filenames[:5] == list(qg.JS_HARNESS_FILENAMES[:5])


# ---------------------------------------------------------------
# Negative-path proof: a failing new harness fails the gate step
# ---------------------------------------------------------------


def test_new_harness_failure_fails_the_js_harness_step(qg, monkeypatch):
    monkeypatch.setattr(qg.shutil, "which", lambda name: "/usr/bin/node")
    # Five pre-existing harnesses pass; the new, 6th one fails.
    results = [_FakeCompletedProcess(0) for _ in range(5)] + [
        _FakeCompletedProcess(1, stdout="3 assertions, 2 passed, 1 failed"),
    ]
    runner = _RecordingRunner(results=results)
    outcome = qg._run_js_harnesses(REPO_ROOT, runner=runner)
    assert outcome.passed is False
    assert NEW_HARNESS_FILENAME in outcome.output
    assert "1 failed" in outcome.output
    # All six were invoked (failure is the last one in the list).
    assert len(runner.calls) == 6


def test_new_harness_failure_fails_the_whole_gate_run(qg, monkeypatch):
    monkeypatch.setattr(qg.shutil, "which", lambda name: "/usr/bin/node")
    results = [_FakeCompletedProcess(0) for _ in range(5)] + [
        _FakeCompletedProcess(1, stdout="boom"),
    ]
    runner = _RecordingRunner(results=results)

    def _js_gate():
        return qg._run_js_harnesses(REPO_ROOT, runner=runner)

    gates = [
        qg.Gate("git diff --check", "scope", lambda: qg.GateOutcome(True, "ok")),
        qg.Gate("JavaScript harnesses", "scope", _js_gate),
        qg.Gate("Full pytest suite", "scope", lambda: qg.GateOutcome(True, "ok")),
    ]
    import io
    buf = io.StringIO()
    rc = qg.run_gates(gates, stream=buf)
    assert rc == 1
    output = buf.getvalue()
    assert "FAILED at check 2/3: JavaScript harnesses" in output
    # The gate after the failing one must never have run.
    assert "3/3" not in output.split("FAILED")[0].split("[2/3]")[-1]


def test_new_harness_success_allows_js_step_to_pass(qg, monkeypatch):
    monkeypatch.setattr(qg.shutil, "which", lambda name: "/usr/bin/node")
    runner = _RecordingRunner(default_returncode=0)
    outcome = qg._run_js_harnesses(REPO_ROOT, runner=runner)
    assert outcome.passed is True
    # Faz 2.8.19 Stage 3 appended an 8th harness; the message reflects
    # the current total, not a value frozen at an earlier phase.
    assert "All 8 JavaScript harnesses passed." in outcome.output
