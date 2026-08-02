"""HTTP API tests for backend/api/routes/joints.py (Faz 2.8.17 Stage 2).

Uses the shared `client`/`auth_headers`/`login_as` fixtures from
tests/conftest.py -- the same TestClient bound to backend.app.app every
other endpoint test uses (see tests/governance/test_joint_revision_api.py
for the established precedent of using these fixtures for a joints-
adjacent route).

Scope: this file exercises the thin HTTP adapter only -- request
validation, authentication, response serialization, and exception ->
status-code mapping. Revision-number generation, the archived-joint
check, and the entire idempotency lookup/compare/conflict decision are
already covered at the service layer by tests/test_joints_foundation.py
and are not re-tested here; this file only confirms the route wires
them correctly.
"""
from __future__ import annotations

import uuid

from backend.app import conn, now_iso
from backend.joints import service as joints_svc


def _make_project(name=None):
    with conn() as c:
        c.execute(
            "INSERT INTO projects(name,status,created_at) VALUES(?,?,?)",
            (name or f"Joints API Test Project {uuid.uuid4().hex[:8]}", "open", now_iso()),
        )
        c.commit()
        return c.execute("SELECT id FROM projects WHERE id=last_insert_rowid()").fetchone()["id"]


def _create_joint_via_api(client, headers, project_id, code=None):
    payload = {
        "project_id": project_id,
        "joint_code": code or f"J-API-{uuid.uuid4().hex[:8]}",
        "name": "API Test Joint",
    }
    r = client.post("/api/joints", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _count_create_audit_entries(joint_id, rev_no):
    with conn() as c:
        row = c.execute(
            "SELECT COUNT(*) n FROM audit_log WHERE action='joint_revision_create' AND detail=?",
            (f"joint={joint_id} rev={rev_no}",),
        ).fetchone()
    return row["n"]


# --------------------------------------------------------------- smoke/auth


def test_joints_router_is_mounted(client):
    """Scenario 17: the router is actually reachable through
    backend.app.app (not just importable on its own) -- proves
    backend/app.py's additive include_router() call took effect."""
    schema = client.get("/openapi.json").json()
    assert "/api/joints" in schema["paths"]
    assert "/api/joints/{joint_id}/revisions" in schema["paths"]
    assert "/api/joints/revisions/{revision_id}" in schema["paths"]


def test_create_joint_requires_authentication(client):
    """Scenario 16 (create_joint)."""
    r = client.post("/api/joints", json={"project_id": 1, "joint_code": "J-NOAUTH", "name": "x"})
    assert r.status_code == 401


def test_create_joint_revision_requires_authentication(client):
    """Scenario 16 (create_joint_revision)."""
    r = client.post("/api/joints/1/revisions", json={"snapshot": {}})
    assert r.status_code == 401


# ------------------------------------------------------------------ joints


def test_get_unknown_joint_returns_404(client, auth_headers):
    """Scenario 15 (joint not found)."""
    r = client.get("/api/joints/999999999", headers=auth_headers)
    assert r.status_code == 404


def test_create_joint_revision_for_unknown_joint_returns_404(client, auth_headers):
    """Scenario 15 (revision create against a non-existent joint)."""
    r = client.post(
        "/api/joints/999999999/revisions", headers=auth_headers, json={"snapshot": {}}
    )
    assert r.status_code == 404


# --------------------------------------------------------- revisions: basic


def test_create_joint_revision_without_idempotency_key(client, auth_headers):
    """Scenario 1: key omitted -- every call creates a new revision,
    exactly like before Stage 1/2 existed."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    payload = {"snapshot": {"thread": "M10"}, "change_summary": "r1"}
    r1 = client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    r2 = client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] != r2.json()["id"]
    assert r2.json()["revision_no"] == r1.json()["revision_no"] + 1


def test_create_joint_revision_with_idempotency_key_creates_revision(client, auth_headers):
    """Scenario 2: the first request under a new key creates a revision
    normally."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    r = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"thread": "M10"}, "change_summary": "r1", "idempotency_key": "API-KEY-1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["revision_no"] == 1
    assert body["idempotency_key"] == "API-KEY-1"


def test_replay_same_key_same_payload_returns_same_revision(client, auth_headers):
    """Scenario 3."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    payload = {
        "snapshot": {"thread": "M12"}, "change_summary": "r1", "idempotency_key": "API-KEY-2",
    }
    first = client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    replay = client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    assert first.status_code == 200 and replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["revision_no"] == replay.json()["revision_no"]


def test_replay_does_not_create_second_revision(client, auth_headers):
    """Scenario 4: a replay must not advance the per-joint revision_no
    counter."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    payload = {"snapshot": {}, "change_summary": "r1", "idempotency_key": "API-KEY-3"}
    client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    fresh = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={"snapshot": {}, "change_summary": "r2"},
    )
    assert fresh.status_code == 200
    assert fresh.json()["revision_no"] == 2


def test_replay_does_not_write_second_audit_entry(client, auth_headers):
    """Scenario 5."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    payload = {"snapshot": {}, "change_summary": "r1", "idempotency_key": "API-KEY-4"}
    first = client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    rev_no = first.json()["revision_no"]
    assert _count_create_audit_entries(joint["id"], rev_no) == 1
    client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    assert _count_create_audit_entries(joint["id"], rev_no) == 1


# ------------------------------------------------------------ replay conflicts


def test_replay_different_snapshot_returns_409(client, auth_headers):
    """Scenario 6."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"thread": "M10"}, "change_summary": "r1", "idempotency_key": "API-KEY-5",
        },
    )
    r = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"thread": "M12"}, "change_summary": "r1", "idempotency_key": "API-KEY-5",
        },
    )
    assert r.status_code == 409


def test_replay_different_change_summary_returns_409(client, auth_headers):
    """Scenario 7."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={"snapshot": {}, "change_summary": "first", "idempotency_key": "API-KEY-6"},
    )
    r = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={"snapshot": {}, "change_summary": "second", "idempotency_key": "API-KEY-6"},
    )
    assert r.status_code == 409


def test_replay_different_actor_returns_409(client, auth_headers, login_as):
    """Scenario 8: same key, same snapshot/summary, different
    authenticated actor -> conflict."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    username = f"joints_api_reviewer_{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username, "display_name": "Joints API Reviewer",
            "password": "reviewerpass1", "role": "engineer",
        },
    )
    assert r.status_code == 200, r.text
    other_headers = login_as(username, "reviewerpass1")

    client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={"snapshot": {}, "change_summary": "x", "idempotency_key": "API-KEY-7"},
    )
    r = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=other_headers,
        json={"snapshot": {}, "change_summary": "x", "idempotency_key": "API-KEY-7"},
    )
    assert r.status_code == 409


def test_replay_different_joint_same_key_is_allowed(client, auth_headers):
    """Scenario 9: the same key may be reused freely across different
    joints."""
    pid = _make_project()
    j1 = _create_joint_via_api(client, auth_headers, pid)
    j2 = _create_joint_via_api(client, auth_headers, pid)
    r1 = client.post(
        f"/api/joints/{j1['id']}/revisions",
        headers=auth_headers,
        json={"snapshot": {}, "change_summary": "x", "idempotency_key": "SHARED-API-KEY"},
    )
    r2 = client.post(
        f"/api/joints/{j2['id']}/revisions",
        headers=auth_headers,
        json={"snapshot": {}, "change_summary": "x", "idempotency_key": "SHARED-API-KEY"},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] != r2.json()["id"]


def test_replay_accepts_reordered_snapshot_keys(client, auth_headers):
    """Scenario 10: semantic (parsed-JSON) equality, not raw string
    comparison -- a snapshot object with the same keys/values in a
    different order must still be recognised as the same request."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    first = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"thread": "M10", "class": "8.8"},
            "change_summary": "r1",
            "idempotency_key": "API-KEY-8",
        },
    )
    replay = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"class": "8.8", "thread": "M10"},
            "change_summary": "r1",
            "idempotency_key": "API-KEY-8",
        },
    )
    assert first.status_code == 200 and replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]


def test_conflict_response_does_not_leak_snapshot_or_internal_detail(client, auth_headers):
    """Scenario 11."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"internal_note": "CONFIDENTIAL-API-VALUE"},
            "change_summary": "r1",
            "idempotency_key": "API-KEY-9",
        },
    )
    r = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"internal_note": "different"},
            "change_summary": "r1",
            "idempotency_key": "API-KEY-9",
        },
    )
    assert r.status_code == 409
    body_text = r.text
    assert "CONFIDENTIAL-API-VALUE" not in body_text
    assert "sqlite" not in body_text.lower()
    assert "/home/" not in body_text
    assert ".db" not in body_text
    assert "Traceback" not in body_text


# ------------------------------------------------------------- archived joint


def test_archived_joint_replay_of_existing_key_still_succeeds(client, auth_headers):
    """Scenario 12: a replay of an already-successful key returns the
    existing revision even after the joint is later archived -- see
    backend/api/routes/joints.py module docstring."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    payload = {
        "snapshot": {"thread": "M10"}, "change_summary": "r1", "idempotency_key": "API-KEY-10",
    }
    first = client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    assert first.status_code == 200

    joints_svc.archive_joint(joint["id"], None)

    replay = client.post(f"/api/joints/{joint['id']}/revisions", headers=auth_headers, json=payload)
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]


def test_archived_joint_new_key_write_is_rejected(client, auth_headers):
    """Scenario 13: a genuinely new write (new key) against an
    archived joint is rejected by the existing domain rule (400)."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    joints_svc.archive_joint(joint["id"], None)

    r = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={"snapshot": {}, "change_summary": "x", "idempotency_key": "API-KEY-11-NEW"},
    )
    assert r.status_code == 400


def test_archived_joint_same_key_different_payload_returns_409(client, auth_headers):
    """Scenario 14: the idempotency lookup runs before the archived
    check, so a key collision on an archived joint is still a 409, not
    a 400."""
    pid = _make_project()
    joint = _create_joint_via_api(client, auth_headers, pid)
    client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"thread": "M10"}, "change_summary": "r1", "idempotency_key": "API-KEY-12",
        },
    )
    joints_svc.archive_joint(joint["id"], None)

    r = client.post(
        f"/api/joints/{joint['id']}/revisions",
        headers=auth_headers,
        json={
            "snapshot": {"thread": "M14"}, "change_summary": "r1", "idempotency_key": "API-KEY-12",
        },
    )
    assert r.status_code == 409
