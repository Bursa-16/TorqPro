"""Faz 2.8.12 Stage 2 -- focused tests for
tools/run_washer_governance_reconciliation.py.

Runs the CLI as a real subprocess (matching
``tests/test_run_quality_gate.py``'s hermeticity note that only the
gate-runner tests themselves may need a subprocess; here the whole
tool's surface area is "parse args, resolve store from env, call
``reconcile``, print JSON, choose an exit code" -- small enough that
exercising it end-to-end via subprocess is both simple and a faithful
regression guard for its actual entry point).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "tools" / "run_washer_governance_reconciliation.py"


def _run(env_overrides=None, args=None):
    env = dict(os.environ)
    env.setdefault("TORQPRO_SECRET_KEY", "x" * 64)
    env.pop("TORQPRO_GOVERNANCE_EVENT_STORE_PATH", None)
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *(args or [])],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result


def test_runs_successfully_with_unconfigured_store():
    result = _run()
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["invariant_holds"] is True
    assert "counters" in payload


def test_default_is_dry_run():
    result = _run()
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True


def test_apply_flag_sets_dry_run_false(tmp_path):
    store_path = tmp_path / "events.json"
    result = _run(
        env_overrides={"TORQPRO_GOVERNANCE_EVENT_STORE_PATH": str(store_path)},
        args=["--apply"],
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is False


def test_output_never_contains_configured_filesystem_path(tmp_path):
    store_path = tmp_path / "super_secret_events_file.json"
    result = _run(env_overrides={"TORQPRO_GOVERNANCE_EVENT_STORE_PATH": str(store_path)})
    assert result.returncode == 0, result.stderr
    assert "super_secret_events_file" not in result.stdout
    assert str(store_path) not in result.stdout


def test_output_is_deterministic_json_with_sorted_keys():
    result = _run()
    # json.dumps(..., sort_keys=True) is used by the tool itself;
    # re-parsing and re-serializing with the same option must be a
    # no-op if the original output was already sorted.
    payload = json.loads(result.stdout)
    reserialized = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    assert result.stdout.strip() == reserialized.strip()


def test_exit_code_zero_when_no_failures():
    result = _run()
    payload = json.loads(result.stdout)
    assert payload["counters"]["failed"] == 0
    assert result.returncode == 0
