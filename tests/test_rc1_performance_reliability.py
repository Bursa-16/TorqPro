"""v3.0.0-rc.1 Performance & Reliability -- targeted regression /
reliability tests.

Part of the normal ``pytest -q`` run (unlike ``tests/performance/``,
which is opt-in) -- every test here is a deterministic pass/fail
correctness check, never a timing assertion, so it belongs in the
regular suite per this phase's own "yeni testler deterministic olmalı
/ timing-flaky test yazma" requirement.

Covers:

* P2 -- SQLite WAL + busy_timeout (``backend/app.py``'s ``conn()``):
  WAL is actually active on a real, file-backed database; normal CRUD
  is unaffected; a concurrent read/write smoke scenario produces no
  errors and no data loss/corruption.
* Reliability -- repeated calculation creation, concurrent project/
  calculation reads, concurrent writes, audit-log persistence,
  deterministic-engine repeated-call consistency, provider-independent/
  offline AI behavior under repeated requests, DB reopen/reconnect,
  and a failure/retry path (a deliberately malformed request retried
  after a valid one, proving one request's failure never corrupts
  state for the next).
"""

from __future__ import annotations

import os
import tempfile
import threading
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------
# P2 -- WAL / busy_timeout
# ---------------------------------------------------------------------


def test_wal_journal_mode_active_on_file_backed_db(tmp_path):
    """The real backend.app.conn() factory, against a real file-backed
    database (never :memory: -- see the module docstring in
    tests/performance/test_baseline_benchmarks.py for why that
    distinction matters), reports journal_mode=wal."""
    import subprocess
    import sys

    db_path = tmp_path / "wal_check.db"
    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(db_path)
    script = (
        "from backend.app import conn, migrate; migrate(); "
        "c = conn(); "
        "print('MODE', c.execute('PRAGMA journal_mode').fetchone()[0]); "
        "print('TIMEOUT', c.execute('PRAGMA busy_timeout').fetchone()[0]); "
        # migrate()'s own conn() already closed by this point -- SQLite
        # auto-checkpoints (and removes) -wal/-shm when the last
        # connection to a WAL database closes, so a fresh write is
        # needed here to guarantee the sidecar files exist *at the
        # moment this process checks for them*, not just that the
        # PRAGMA reports "wal".
        "c.execute(\"INSERT INTO audit_log(user_id,action,detail,request_id,created_at) VALUES(NULL,'wal_sidecar_check','','','2026-01-01T00:00:00Z')\"); "
        "c.commit()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MODE wal" in result.stdout
    assert "TIMEOUT 5000" in result.stdout
    # WAL leaves sidecar files next to the main db file while at least
    # one connection is open/has written -- confirms the mode is
    # genuinely active on disk, not just reported by the PRAGMA. The
    # subprocess above has already exited (all its connections
    # closed) by the time we check, so on some SQLite builds the final
    # connection's close may have already auto-checkpointed and
    # removed them again; the decisive, always-reliable signal is the
    # PRAGMA report asserted above; this is corroborating evidence
    # when available.
    sidecars_seen = (tmp_path / "wal_check.db-wal").exists() or (tmp_path / "wal_check.db-shm").exists()
    if not sidecars_seen:
        # Not a failure by itself (see comment above) -- but confirm
        # via a second, still-open connection that a write really did
        # produce WAL sidecar files while active, ruling out "WAL was
        # silently ignored".
        db_path = tmp_path / "wal_check.db"
        import sqlite3

        c = sqlite3.connect(db_path)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("INSERT INTO audit_log(user_id,action,detail,request_id,created_at) VALUES(NULL,'x','','','2026-01-01T00:00:00Z')")
        c.commit()
        assert (tmp_path / "wal_check.db-wal").exists() or (tmp_path / "wal_check.db-shm").exists()
        c.close()


def test_normal_crud_unaffected_by_wal(client, auth_headers):
    """Non-regression: create, list, and delete a calculation exactly
    as before -- WAL/busy_timeout change nothing about transaction
    semantics or query results."""
    r = client.post(
        "/api/calculations",
        headers=auth_headers,
        json={"thread": "M12", "torque_nm": 60.0, "standard": "VDI2230"},
    )
    assert r.status_code == 200, r.text
    calc_id = r.json()["id"]

    r_list = client.get("/api/calculations", headers=auth_headers)
    assert r_list.status_code == 200
    assert any(row["id"] == calc_id for row in r_list.json())

    r_del = client.delete(f"/api/calculations/{calc_id}", headers=auth_headers)
    assert r_del.status_code == 200, r_del.text


def test_concurrent_writes_no_errors_no_data_loss(client, auth_headers):
    """The Stage 0 / P2 motivating scenario: many writers hitting the
    same SQLite file at once. Every request must succeed (no
    "database is locked" OperationalError bubbling up as a 500), and
    every write must be durably visible afterwards (no lost commits)."""
    n_workers = 20
    statuses: list[int] = []
    exceptions: list[str] = []
    lock = threading.Lock()
    marker = uuid.uuid4().hex[:8]

    def worker(i: int) -> None:
        try:
            r = client.post(
                "/api/calculations",
                headers=auth_headers,
                json={
                    "thread": "M10",
                    "torque_nm": 45.0,
                    "standard": "VDI2230",
                    "source_mode": f"concurrency-smoke-{marker}-{i}",
                },
            )
            with lock:
                statuses.append(r.status_code)
        except Exception as exc:  # pragma: no cover - failure path itself is the assertion
            with lock:
                exceptions.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not exceptions, f"worker thread(s) raised: {exceptions}"
    assert len(statuses) == n_workers
    assert all(s == 200 for s in statuses), statuses

    r_list = client.get("/api/calculations", headers=auth_headers)
    assert r_list.status_code == 200
    # The list endpoint's ?q= filter only searches record_no/standard/
    # thread/property_class/family (see backend/app.py's lst()) --
    # never source_mode, so this filters client-side instead of
    # relying on a server-side search that was never meant to cover
    # this field.
    written = {row["source_mode"] for row in r_list.json() if row["source_mode"] and row["source_mode"].startswith(f"concurrency-smoke-{marker}-")}
    expected = {f"concurrency-smoke-{marker}-{i}" for i in range(n_workers)}
    assert written == expected, "some concurrent writes were lost or duplicated"


def test_concurrent_reads_alongside_writes(client, auth_headers):
    """Readers running at the same time as writers must never error
    or block indefinitely (WAL's core benefit: readers don't wait on
    an in-progress writer)."""
    n_writers = 10
    n_readers = 10
    write_statuses: list[int] = []
    read_statuses: list[int] = []
    exceptions: list[str] = []
    lock = threading.Lock()

    def writer(i: int) -> None:
        try:
            r = client.post(
                "/api/calculations",
                headers=auth_headers,
                json={"thread": "M8", "torque_nm": 20.0, "standard": "VDI2230"},
            )
            with lock:
                write_statuses.append(r.status_code)
        except Exception as exc:  # pragma: no cover
            with lock:
                exceptions.append(repr(exc))

    def reader() -> None:
        try:
            r = client.get("/api/calculations", headers=auth_headers)
            with lock:
                read_statuses.append(r.status_code)
        except Exception as exc:  # pragma: no cover
            with lock:
                exceptions.append(repr(exc))

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(n_writers)]
    threads += [threading.Thread(target=reader) for _ in range(n_readers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not exceptions, f"worker thread(s) raised: {exceptions}"
    assert len(write_statuses) == n_writers and all(s == 200 for s in write_statuses)
    assert len(read_statuses) == n_readers and all(s == 200 for s in read_statuses)


# ---------------------------------------------------------------------
# Reliability -- repeated/deterministic behavior, DB reopen, audit log
# ---------------------------------------------------------------------


def test_repeated_calculation_creation_is_stable(client, auth_headers):
    """Creating the same logical calculation 10 times in a row must
    succeed every time and produce 10 distinct, independently
    retrievable records (record_no is timestamp-based, so no
    collision is expected -- this pins that down)."""
    ids = []
    for _ in range(10):
        r = client.post(
            "/api/calculations",
            headers=auth_headers,
            json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230"},
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    assert len(set(ids)) == 10


def test_audit_log_persists_across_a_real_action(client, auth_headers):
    calc_marker = f"audit-persist-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/calculations",
        headers=auth_headers,
        json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230", "source_mode": calc_marker},
    )
    assert r.status_code == 200, r.text
    record_no = r.json()["record_no"]

    r_audit = client.get("/api/admin/audit", headers=auth_headers)
    assert r_audit.status_code == 200
    matches = [row for row in r_audit.json() if row["action"] == "calculation_create" and row["detail"] == record_no]
    assert len(matches) == 1


def test_deterministic_engine_repeated_calls_produce_identical_results(client, auth_headers):
    """The same joint-analysis input, called twice, must produce byte-
    identical calculated_values -- the deterministic engineering core
    has no hidden state/randomness (ADR-0002)."""
    payload = {
        "diameter_mm": 10.0,
        "pitch_mm": 1.5,
        "rp02_mpa": 900.0,
        "target_yield_ratio": 0.8,
        "max_utilization_ratio": 0.9,
        "mu_thread_nom": 0.12,
        "mu_bearing_nom": 0.12,
        "effective_bearing_diameter_mm": 14.0,
        "bolt_segments": [{"length_mm": 20, "modulus_mpa": 210000, "area_mm2": 200}],
        "joint_segments": [{"length_mm": 20, "modulus_mpa": 210000, "area_mm2": 200}],
        "external_axial_load_n": 5000.0,
        "minimum_required_clamp_load_n": 8000.0,
        "applied_torque_nm": 45.0,
        "fail_threshold": 1.0,
        "warn_threshold": 0.9,
    }
    r1 = client.post("/api/engineering/joint-analysis", headers=auth_headers, json=payload)
    r2 = client.post("/api/engineering/joint-analysis", headers=auth_headers, json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["calculated_values"] == r2.json()["calculated_values"]
    assert r1.json()["safety"] == r2.json()["safety"]


def test_offline_ai_provider_behavior_is_stable_under_repeated_requests(client, auth_headers):
    """POST /api/ai/query's default provider is always-unavailable in
    production (v3.0.0-alpha.4/alpha.5) -- repeated calls must
    consistently return 503, never flip to a different status/error
    shape across repeated calls (no hidden retry-dependent state)."""
    statuses = set()
    for _ in range(5):
        r = client.post("/api/ai/query", headers=auth_headers, json={"query_text": "reliability check"})
        statuses.add(r.status_code)
    assert statuses == {503}


def test_db_reopen_reconnect_after_close(tmp_path):
    """A fresh conn(), used and closed, followed by a second fresh
    conn() against the same file, must see data written by the first
    -- simulating an app restart / connection-pool churn against a
    WAL-mode database."""
    import subprocess
    import sys

    db_path = tmp_path / "reopen_check.db"
    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(db_path)
    script = (
        "from backend.app import conn, migrate; migrate(); "
        "c1 = conn(); "
        "c1.execute(\"INSERT INTO audit_log(user_id,action,detail,request_id,created_at) VALUES(NULL,'reopen_test','marker','', '2026-01-01T00:00:00Z')\"); "
        "c1.commit(); c1.close(); "
        "c2 = conn(); "
        "row = c2.execute(\"SELECT detail FROM audit_log WHERE action='reopen_test'\").fetchone(); "
        "print('MARKER', row[0] if row else None); "
        "c2.close()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MARKER marker" in result.stdout


def test_failure_then_valid_request_recovers_cleanly(client, auth_headers):
    """A malformed request (422) must not leave any connection/lock
    state that affects the very next, valid request -- each conn()
    call is independent (see backend/app.py's conn()), so a failed
    request's rejected transaction must not block or corrupt a
    following one."""
    r_bad = client.post(
        "/api/calculations",
        headers=auth_headers,
        json={"thread": "M10", "torque_nm": -5.0, "standard": "VDI2230"},  # torque_nm must be >=0
    )
    assert r_bad.status_code == 422, r_bad.text

    r_good = client.post(
        "/api/calculations",
        headers=auth_headers,
        json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230"},
    )
    assert r_good.status_code == 200, r_good.text
