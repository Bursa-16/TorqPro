"""Faz 2.8.13 Stage 2 tests:
``GET /api/governance/joint-revision/{revision_id}``.

Exercises the new read-only route added in Stage 2, per the approved
Stage 1 contract
(``docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md``,
Section 5). Uses the shared ``client``/``auth_headers`` fixtures from
``tests/conftest.py`` (the same ``TestClient`` bound to
``backend.app.app`` every other endpoint test uses) and the same
joint/revision fixture pattern already established by
``tests/governance/adapters/test_joint_revision.py`` -- this file does
not re-test the adapter's own mapping logic (already covered there),
only the HTTP transport wrapped around it.
"""

from __future__ import annotations

import pytest

from backend import app as appmod
from backend.app import conn, now_iso
from backend.governance import service as svc
from backend.governance.adapters.joint_revision import ProjectionOutcome
from backend.governance.api import get_governance_store
from backend.governance.store import FileGovernanceEventStore
from backend.joints import service as joints_svc
from backend.joints.exceptions import JointCodeConflictError

_ROUTE_PREFIX = "/api/governance/joint-revision"


@pytest.fixture
def gov_store(tmp_path):
    """Overrides the ``get_governance_store`` FastAPI dependency for
    the duration of one test with a store backed by a temp-path file
    -- mirrors ``tests/governance/test_api.py``'s own fixture of the
    same name/shape, kept local here since no shared governance-level
    conftest exists yet (matching this test directory's established
    per-file-fixture convention)."""
    store = FileGovernanceEventStore(tmp_path / "events.json")
    appmod.app.dependency_overrides[get_governance_store] = lambda: store
    yield store
    appmod.app.dependency_overrides.pop(get_governance_store, None)


def _make_project(name="Governance API Joint Revision Test Project"):
    with conn() as c:
        c.execute(
            "INSERT INTO projects(name,status,created_at) VALUES(?,?,?)",
            (name, "open", now_iso()),
        )
        c.commit()
        return c.execute("SELECT id FROM projects WHERE id=last_insert_rowid()").fetchone()["id"]


def _make_joint_and_revision(joint_code_suffix):
    pid = _make_project()
    try:
        joint = joints_svc.create_joint(
            pid, f"J-GOVAPI-{joint_code_suffix}", "Governance API Test Joint", None, 1
        )
    except JointCodeConflictError:  # pragma: no cover - defensive, unique suffix expected
        joint = joints_svc.create_joint(
            pid, f"J-GOVAPI-{joint_code_suffix}-2", "Governance API Test Joint", None, 1
        )
    revision = joints_svc.create_joint_revision(joint["id"], {"thread": "M10"}, "initial", 1)
    return joint, revision


def _revision_row(revision_id):
    """Raw snapshot of the authoritative ``joint_revisions`` row, used
    to prove the route never mutates it."""
    with conn() as c:
        row = c.execute("SELECT * FROM joint_revisions WHERE id=?", (revision_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------
# Outcome -> HTTP status mapping (items 1-5)
# ---------------------------------------------------------------------


def test_supported_projection_returns_200(client, auth_headers):
    _, revision = _make_joint_and_revision("supported")
    r = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == ProjectionOutcome.SUPPORTED.value
    assert body["source_status"] == "draft"
    assert body["canonical_status"] == "draft"
    assert body["lifecycle_group"] == "review"
    assert body["joint_revision_id"] == revision["id"]
    assert body["source_system"] == "joint_revision"


def test_unsupported_status_returns_200(client, auth_headers, monkeypatch):
    import backend.joints.service as joints_service_module

    _, revision = _make_joint_and_revision("unsupported")

    def _fake_get_joint_revision(revision_id):
        return {"id": revision_id, "status": "some_future_status_not_in_vocabulary"}

    monkeypatch.setattr(joints_service_module, "get_joint_revision", _fake_get_joint_revision)

    r = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == ProjectionOutcome.UNSUPPORTED_STATUS.value
    assert body["canonical_status"] is None
    assert body["source_status"] == "some_future_status_not_in_vocabulary"
    assert body["safe_reason"]


def test_invalid_source_record_returns_200(client, auth_headers, monkeypatch):
    import backend.joints.service as joints_service_module

    monkeypatch.setattr(
        joints_service_module, "get_joint_revision", lambda revision_id: {"id": revision_id}
    )

    r = client.get(f"{_ROUTE_PREFIX}/1", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == ProjectionOutcome.INVALID_SOURCE_RECORD.value
    assert body["canonical_status"] is None


def test_source_unavailable_returns_200(client, auth_headers, monkeypatch):
    import backend.joints.service as joints_service_module

    def _boom(revision_id):
        raise RuntimeError("simulated sqlite3.OperationalError: disk I/O error at /secret/path")

    monkeypatch.setattr(joints_service_module, "get_joint_revision", _boom)

    r = client.get(f"{_ROUTE_PREFIX}/1", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == ProjectionOutcome.SOURCE_UNAVAILABLE.value
    # Item 11: no internal detail leaked into the response.
    safe_reason = body.get("safe_reason") or ""
    assert "/secret/path" not in safe_reason
    assert "OperationalError" not in safe_reason
    assert "RuntimeError" not in safe_reason
    assert "Traceback" not in safe_reason


def test_revision_not_found_returns_404(client, auth_headers):
    r = client.get(f"{_ROUTE_PREFIX}/999999999", headers=auth_headers)
    assert r.status_code == 404
    body = r.json()
    assert body["outcome"] == ProjectionOutcome.NOT_FOUND.value
    assert body["canonical_status"] is None
    assert body["source_status"] is None


# ---------------------------------------------------------------------
# Response shape (item 6)
# ---------------------------------------------------------------------


def test_response_preserves_adapter_canonical_fields(client, auth_headers):
    _, revision = _make_joint_and_revision("fields")
    r = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "source_system",
        "joint_revision_id",
        "source_status",
        "lifecycle_group",
        "canonical_status",
        "outcome",
        "safe_reason",
    }


# ---------------------------------------------------------------------
# No mutation / no governance persistence (items 7-9)
# ---------------------------------------------------------------------


def test_route_does_not_mutate_authoritative_joint_revision_data(client, auth_headers):
    _, revision = _make_joint_and_revision("no-mutate")
    before = _revision_row(revision["id"])
    r = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    assert r.status_code == 200
    after = _revision_row(revision["id"])
    assert before == after


def test_route_does_not_append_governance_events(client, auth_headers, gov_store):
    _, revision = _make_joint_and_revision("no-events")
    aggregate_id = f"joint-revision-{revision['id']}"
    before = svc.event_history(gov_store, aggregate_id)
    r = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    assert r.status_code == 200
    after = svc.event_history(gov_store, aggregate_id)
    assert before == [] and after == []


def test_route_does_not_change_governance_event_store_contents(client, auth_headers, gov_store):
    _, revision = _make_joint_and_revision("no-store-change")

    def _snapshot():
        return gov_store._path.read_bytes() if gov_store._path.exists() else None

    before = _snapshot()
    r = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    assert r.status_code == 200
    after = _snapshot()
    assert before == after  # both None: the store file is never created by this route


# ---------------------------------------------------------------------
# Determinism / idempotence (item 10)
# ---------------------------------------------------------------------


def test_repeated_get_requests_are_deterministic_and_side_effect_free(client, auth_headers):
    _, revision = _make_joint_and_revision("repeatable")
    first = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    before = _revision_row(revision["id"])
    second = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    third = client.get(f"{_ROUTE_PREFIX}/{revision['id']}", headers=auth_headers)
    after = _revision_row(revision["id"])
    assert first.status_code == second.status_code == third.status_code == 200
    assert first.json() == second.json() == third.json()
    assert before == after


# ---------------------------------------------------------------------
# Existing route regression (item 12)
# ---------------------------------------------------------------------


def test_existing_history_route_unaffected(client, auth_headers, gov_store):
    """Adding the new route must not disturb the pre-existing generic
    history/status endpoints -- same 404 body shape as before this
    stage's change."""
    r = client.get(
        "/api/governance/agg-nonexistent-2813/history?aggregate_type=x",
        headers=auth_headers,
    )
    assert r.status_code == 404
    assert "governance kaydı bulunamadı" in r.json()["detail"]


def test_existing_unrelated_endpoint_still_works(client, auth_headers):
    r = client.get("/api/library/materials", headers=auth_headers)
    assert r.status_code == 200


# ---------------------------------------------------------------------
# Path-parameter shape (item 13)
# ---------------------------------------------------------------------


def test_route_accepts_integer_revision_id_shape(client, auth_headers):
    """``project_joint_revision(revision_id: int)`` is the adapter's
    exact signature -- a non-integer path segment must be rejected by
    FastAPI's own path-parameter validation, not silently coerced or
    forwarded to the adapter."""
    r = client.get(f"{_ROUTE_PREFIX}/not-an-integer", headers=auth_headers)
    assert r.status_code == 422


def test_route_rejects_unauthenticated_request(gov_store):
    from fastapi.testclient import TestClient

    unauth_client = TestClient(appmod.app)
    r = unauth_client.get(f"{_ROUTE_PREFIX}/1")
    assert r.status_code == 401


# ---------------------------------------------------------------------
# Real request-path import-order safety (items 14-15)
# ---------------------------------------------------------------------


def test_joint_revision_route_importable_in_a_clean_process_before_app(tmp_path):
    """The real production import order this route is actually
    reached through: importing ``backend.governance.api`` (which now
    imports ``backend.governance.adapters.joint_revision`` at module
    level) in a process that has never imported ``backend.app`` must
    succeed -- proving the Faz 2.8.12 Stage 4.1-proven deferred-import
    mitigation still holds through this stage's new call path, not
    just at the adapter-module level already covered by
    ``tests/governance/test_compatibility.py``."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(tmp_path / "clean_before_app.db")
    script = (
        "import sys; assert 'backend.app' not in sys.modules; "
        "from backend.governance.api import router, governance_joint_revision; "
        "print('OK', router is not None, governance_joint_revision is not None)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK True True" in result.stdout


def test_joint_revision_route_reachable_via_testclient_in_a_clean_process(tmp_path):
    """The end-to-end real request-path scenario: a brand-new process
    imports ``backend.app`` first (the normal production entry point,
    which mounts the governance router including this stage's new
    route), migrates its schema, and successfully round-trips a real
    HTTP request through ``TestClient`` against the new route --
    proving import order safety under actual ASGI/request conditions,
    not just at import-statement level."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(tmp_path / "clean_via_testclient.db")
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r = c.post('/api/login', json={'username': 'Protype Lab', 'password': 'A1234'}); "
        "assert r.status_code == 200, r.text; "
        "token = r.json()['token']; "
        "headers = {'Authorization': 'Bearer ' + token}; "
        "r2 = c.get('/api/governance/joint-revision/999999999', headers=headers); "
        "assert r2.status_code == 404, r2.text; "
        "print('OK', r2.json()['outcome'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK not_found" in result.stdout
