"""Faz 2.8.10 Stage 4 -- focused tests for tools/run_quality_gate.py.

tools/ has no __init__.py (it is a collection of standalone scripts,
not a package), so this module is loaded the same way every existing
test that depends on a tools/ script already does --
``importlib.util.spec_from_file_location`` by file path (see e.g.
tests/test_faz_2_8_3_bolt_nut_strength_classes.py's
``TestBaselineProblem``). One addition beyond that existing pattern:
the loaded module is registered in ``sys.modules`` before
``exec_module`` runs, which ``run_quality_gate.py`` needs because it
uses ``@dataclass`` -- dataclass processing looks the defining module
up in ``sys.modules`` by name, which fails with a confusing
``AttributeError`` if the module was never registered there.

These tests are all fast and hermetic: real subprocess calls (git,
node, python -m compileall/pytest) are only exercised by
``run_quality_gate.py`` itself when invoked directly by a person or
CI, never by this test file. Every test here either calls a pure
function directly (``find_repository_json_files``,
``validate_json_files``) or injects a fake ``runner``/gate list so no
external process, network, or real Node/git installation is required
for the suite to pass.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "run_quality_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_quality_gate_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def qg():
    return _load_module()


# ---------------------------------------------------------------
# Fakes used to exercise run_gates()/gate functions without any real
# subprocess/filesystem work.
# ---------------------------------------------------------------

class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _RecordingRunner:
    """Stand-in for subprocess.run that records every call and returns
    a scripted sequence of results (or a fixed default)."""

    def __init__(self, results=None, default_returncode: int = 0):
        self._results = list(results) if results is not None else None
        self._default_returncode = default_returncode
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        if self._results is not None:
            return self._results.pop(0)
        return _FakeCompletedProcess(self._default_returncode)


def _make_gate(qg, name: str, passed: bool, call_log: list[str] | None = None):
    def _run():
        if call_log is not None:
            call_log.append(name)
        return qg.GateOutcome(passed, f"{name} output")
    return qg.Gate(name=name, scope=f"scope for {name}", run=_run)


# ---------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------

def test_default_gates_have_the_exact_required_order(qg):
    names = [g.name for g in qg.default_gates(REPO_ROOT)]
    assert names == [
        "git diff --check",
        "Python compile validation",
        "JSON validity",
        "TR/EN key parity",
        "JavaScript harnesses",
        "Full pytest suite",
    ]


def test_default_gates_order_is_stable_across_calls(qg):
    first = [g.name for g in qg.default_gates(REPO_ROOT)]
    second = [g.name for g in qg.default_gates(REPO_ROOT)]
    assert first == second


# ---------------------------------------------------------------
# Successful command execution / exit-code propagation
# ---------------------------------------------------------------

def test_run_gates_returns_zero_and_runs_every_gate_when_all_pass(qg):
    import io

    call_log: list[str] = []
    gates = [_make_gate(qg, f"gate-{i}", True, call_log) for i in range(4)]
    buf = io.StringIO()
    rc = qg.run_gates(gates, stream=buf)
    assert rc == 0
    assert call_log == ["gate-0", "gate-1", "gate-2", "gate-3"]
    assert "PASSED" in buf.getvalue()


def test_run_gates_returns_nonzero_when_any_gate_fails(qg):
    import io

    gates = [
        _make_gate(qg, "gate-a", True),
        _make_gate(qg, "gate-b", False),
        _make_gate(qg, "gate-c", True),
    ]
    buf = io.StringIO()
    rc = qg.run_gates(gates, stream=buf)
    assert rc == 1
    assert "FAILED" in buf.getvalue()


# ---------------------------------------------------------------
# First-failure short-circuit
# ---------------------------------------------------------------

def test_run_gates_stops_at_first_failure_and_does_not_run_later_gates(qg):
    import io

    call_log: list[str] = []
    gates = [
        _make_gate(qg, "gate-1-pass", True, call_log),
        _make_gate(qg, "gate-2-fail", False, call_log),
        _make_gate(qg, "gate-3-never-runs", True, call_log),
        _make_gate(qg, "gate-4-never-runs", True, call_log),
    ]
    buf = io.StringIO()
    rc = qg.run_gates(gates, stream=buf)
    assert rc == 1
    assert call_log == ["gate-1-pass", "gate-2-fail"]
    output = buf.getvalue()
    assert "gate-2-fail" in output
    assert "gate-3-never-runs output" not in output


def test_run_js_harnesses_stops_at_first_failing_harness(qg, monkeypatch):
    monkeypatch.setattr(qg.shutil, "which", lambda name: "/usr/bin/node")
    runner = _RecordingRunner(results=[
        _FakeCompletedProcess(0),  # run_assembly_intelligence_tests.js
        _FakeCompletedProcess(1, stdout="boom"),  # run_i18n_tests.js fails
        _FakeCompletedProcess(0),
        _FakeCompletedProcess(0),
        _FakeCompletedProcess(0),
    ])
    outcome = qg._run_js_harnesses(REPO_ROOT, runner=runner)
    assert outcome.passed is False
    assert "run_i18n_tests.js" in outcome.output
    # Only the first two harnesses were actually invoked.
    assert len(runner.calls) == 2


# ---------------------------------------------------------------
# Missing Node failure message (explicit failure, not a skip)
# ---------------------------------------------------------------

def test_missing_node_fails_explicitly_with_actionable_message(qg, monkeypatch):
    monkeypatch.setattr(qg.shutil, "which", lambda name: None)
    runner = _RecordingRunner()
    outcome = qg._run_js_harnesses(REPO_ROOT, runner=runner)
    assert outcome.passed is False
    assert "Node.js is required" in outcome.output
    assert "node" in outcome.output.lower()
    # No harness should ever be invoked when Node is absent.
    assert runner.calls == []


def test_missing_node_message_is_not_a_skip_marker(qg, monkeypatch):
    # Regression guard for the Stage 3/4 requirement: Node absence must
    # be a hard failure (GateOutcome.passed is False, propagating a
    # non-zero exit code), never a pytest-style skip outcome. The
    # message is allowed to *say* "not silently skipped" as
    # reassurance text -- what matters is the outcome itself.
    monkeypatch.setattr(qg.shutil, "which", lambda name: None)
    outcome = qg._run_js_harnesses(REPO_ROOT, runner=_RecordingRunner())
    assert outcome.passed is False
    assert isinstance(outcome, qg.GateOutcome)
    assert "silently skipped" in outcome.output.lower(), (
        "the message should explicitly reassure that this is a failure, "
        "not an implicit/silent skip"
    )


# ---------------------------------------------------------------
# JSON validation: valid acceptance
# ---------------------------------------------------------------

def test_validate_json_files_accepts_well_formed_json(qg, tmp_path):
    good = tmp_path / "good.json"
    good.write_text('{"a": 1, "b": [1, 2, 3]}', encoding="utf-8")
    outcome = qg.validate_json_files([good])
    assert outcome.passed is True
    assert "1 repository JSON file" in outcome.output


def test_validate_json_files_accepts_multiple_well_formed_files(qg, tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"file{i}.json"
        p.write_text(f'{{"index": {i}}}', encoding="utf-8")
        paths.append(p)
    outcome = qg.validate_json_files(sorted(paths))
    assert outcome.passed is True


# ---------------------------------------------------------------
# JSON validation: invalid failure with filename
# ---------------------------------------------------------------

def test_validate_json_files_reports_exact_invalid_filename_and_error(qg, tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text('{"a": 1,}', encoding="utf-8")  # trailing comma -- invalid JSON
    outcome = qg.validate_json_files([bad])
    assert outcome.passed is False
    assert str(bad) in outcome.output
    assert "broken.json" in outcome.output


def test_validate_json_files_stops_at_first_invalid_file(qg, tmp_path):
    good = tmp_path / "a_good.json"
    good.write_text("{}", encoding="utf-8")
    bad = tmp_path / "b_bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    also_bad_but_later = tmp_path / "c_also_bad.json"
    also_bad_but_later.write_text("{also not valid", encoding="utf-8")
    outcome = qg.validate_json_files([good, bad, also_bad_but_later])
    assert outcome.passed is False
    assert "b_bad.json" in outcome.output
    assert "c_also_bad.json" not in outcome.output


# ---------------------------------------------------------------
# JSON validation: excluded-directory behavior
# ---------------------------------------------------------------

def test_find_repository_json_files_excludes_git_directory(qg, tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "real.json").write_text("{}", encoding="utf-8")
    found = qg.find_repository_json_files(tmp_path)
    assert found == [tmp_path / "real.json"]


def test_find_repository_json_files_excludes_node_modules_and_caches(qg, tmp_path):
    for excluded_dir in ("node_modules", "__pycache__", ".pytest_cache", "venv", "runtime"):
        d = tmp_path / excluded_dir
        d.mkdir()
        (d / "should_be_ignored.json").write_text("{}", encoding="utf-8")
    (tmp_path / "kept.json").write_text("{}", encoding="utf-8")
    found = qg.find_repository_json_files(tmp_path)
    assert found == [tmp_path / "kept.json"]


def test_find_repository_json_files_excludes_nested_excluded_directories(qg, tmp_path):
    nested = tmp_path / "backend" / "library" / "node_modules"
    nested.mkdir(parents=True)
    (nested / "vendor.json").write_text("{}", encoding="utf-8")
    kept = tmp_path / "backend" / "library" / "data.json"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text("{}", encoding="utf-8")
    found = qg.find_repository_json_files(tmp_path)
    assert found == [kept]


# ---------------------------------------------------------------
# JSON validation: deterministic ordering
# ---------------------------------------------------------------

def test_find_repository_json_files_returns_sorted_order(qg, tmp_path):
    # Create files in a deliberately non-alphabetical order.
    names = ["zeta.json", "alpha.json", "mu.json", "beta.json"]
    for name in names:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    found = qg.find_repository_json_files(tmp_path)
    assert found == sorted(found)
    assert [p.name for p in found] == ["alpha.json", "beta.json", "mu.json", "zeta.json"]


def test_find_repository_json_files_ordering_is_stable_across_calls(qg, tmp_path):
    for name in ["c.json", "a.json", "b.json"]:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    first = qg.find_repository_json_files(tmp_path)
    second = qg.find_repository_json_files(tmp_path)
    assert first == second


def test_find_repository_json_files_orders_across_subdirectories_deterministically(qg, tmp_path):
    (tmp_path / "z_dir").mkdir()
    (tmp_path / "z_dir" / "file.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "a_dir" / "file.json").write_text("{}", encoding="utf-8")
    found = qg.find_repository_json_files(tmp_path)
    assert found == sorted(found)


# ---------------------------------------------------------------
# Real repository sanity checks (still hermetic: read-only, no
# subprocess -- just confirms the pure functions behave sensibly
# against the actual repo tree).
# ---------------------------------------------------------------

def test_find_repository_json_files_against_real_repo_finds_known_files(qg):
    found = qg.find_repository_json_files(REPO_ROOT)
    found_names = {p.relative_to(REPO_ROOT).as_posix() for p in found}
    assert "backend/library/data/washer_library.json" in found_names
    assert "DOCUMENTATION_MANIFEST.json" in found_names


def test_find_repository_json_files_against_real_repo_excludes_pycache(qg):
    found = qg.find_repository_json_files(REPO_ROOT)
    for path in found:
        assert "__pycache__" not in path.parts
        assert ".git" not in path.parts


def test_validate_json_files_accepts_the_real_repository_json_files(qg):
    paths = qg.find_repository_json_files(REPO_ROOT)
    outcome = qg.validate_json_files(paths)
    assert outcome.passed is True, outcome.output
