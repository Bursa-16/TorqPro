"""Faz 2.8.11 Stage 4 API tests.

Uses the shared `client`/`auth_headers` fixtures from `tests/conftest.py`
(the same TestClient bound to `backend.app.app` every other endpoint
test uses) plus a per-test dependency override that injects a
temporary :class:`~backend.governance.store.FileGovernanceEventStore`
-- no real filesystem env var is required for most tests, satisfying
"tests must inject temporary store paths" without relying on process-
wide environment state.
"""

from __future__ import annotations

import json

import pytest

from backend import app as appmod
from backend.governance.api import GOVERNANCE_EVENT_STORE_PATH_ENV, get_governance_store
from backend.governance.store import FileGovernanceEventStore

VALID_TS = "2026-07-30T10:00:00Z"
LATER_TS = "2026-07-30T11:00:00Z"


@pytest.fixture
def gov_store(tmp_path):
    """Overrides the `get_governance_store` FastAPI dependency for the
    duration of one test with a store backed by a temp-path file --
    this is the primary "inject a temporary store path" mechanism
    used throughout this file."""
    store = FileGovernanceEventStore(tmp_path / "events.json")
    appmod.app.dependency_overrides[get_governance_store] = lambda: store
    yield store
    appmod.app.dependency_overrides.pop(get_governance_store, None)


def _submit_body(**overrides):
    body = {
        "aggregate_type": "calc_revision",
        "decision_id": "d1",
        "idempotency_key": "k1",
        "occurred_at": VALID_TS,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------
# Router mounting / authentication
# ---------------------------------------------------------------------


def test_router_is_mounted(client, auth_headers, gov_store):
    r = client.get(
        "/api/governance/agg-nonexistent/history?aggregate_type=x", headers=auth_headers
    )
    # 404 (unknown aggregate) proves the route exists and executed --
    # a truly unmounted router would 404 with FastAPI's own "Not
    # Found" default body shape at a different layer, but any
    # response at all from this exact path confirms mounting; the
    # specific 404 body assertion below confirms it's *our* handler.
    assert r.status_code == 404
    assert "governance kaydı bulunamadı" in r.json()["detail"]


def test_unauthenticated_request_is_rejected(gov_store):
    from fastapi.testclient import TestClient

    unauth_client = TestClient(appmod.app)
    r = unauth_client.get("/api/governance/agg-1/history?aggregate_type=calc_revision")
    assert r.status_code == 401


def test_existing_endpoints_remain_unaffected(client, auth_headers):
    """A pre-existing, unrelated endpoint must behave exactly as
    before -- proves mounting the governance router did not disturb
    the rest of the app."""
    r = client.get("/api/library/materials", headers=auth_headers)
    assert r.status_code == 200


# ---------------------------------------------------------------------
# Actor handling
# ---------------------------------------------------------------------


def test_actor_is_derived_from_authenticated_user(client, auth_headers, gov_store):
    r = client.post(
        "/api/governance/review/agg-1/submit", json=_submit_body(), headers=auth_headers
    )
    assert r.status_code == 201
    assert r.json()["event"]["actor"] == "Protype Lab"


def test_actor_in_request_body_is_rejected(client, auth_headers, gov_store):
    r = client.post(
        "/api/governance/review/agg-1/submit",
        json=_submit_body(actor="Someone Else"),
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_previous_status_in_request_body_is_rejected(client, auth_headers, gov_store):
    r = client.post(
        "/api/governance/review/agg-1/submit",
        json=_submit_body(previous_status="approved"),
        headers=auth_headers,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------
# History / status / empty-aggregate behavior
# ---------------------------------------------------------------------


def test_empty_aggregate_history_returns_404(client, auth_headers, gov_store):
    r = client.get(
        "/api/governance/never-touched/history?aggregate_type=calc_revision",
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_empty_aggregate_status_returns_404(client, auth_headers, gov_store):
    r = client.get(
        "/api/governance/never-touched/status?aggregate_type=calc_revision",
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_history_after_submit_has_one_event(client, auth_headers, gov_store):
    client.post("/api/governance/review/agg-1/submit", json=_submit_body(), headers=auth_headers)
    r = client.get(
        "/api/governance/agg-1/history?aggregate_type=calc_revision", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_events"] == 1
    assert len(body["events"]) == 1
    assert body["aggregate_id"] == "agg-1"
    assert body["aggregate_type"] == "calc_revision"


def test_status_reflects_independent_lifecycle_groups(client, auth_headers, gov_store):
    client.post("/api/governance/review/agg-1/submit", json=_submit_body(), headers=auth_headers)
    client.post(
        "/api/governance/resolution/agg-1/waive",
        json=_submit_body(decision_id="d2", idempotency_key="k2"),
        headers=auth_headers,
    )
    r = client.get(
        "/api/governance/agg-1/status?aggregate_type=calc_revision", headers=auth_headers
    )
    body = r.json()
    assert body["status"]["review"] == "under_review"
    assert body["status"]["resolution"] == "waived"
    assert body["status"]["publication"] is None
    assert body["latest_events"]["publication"] is None


# ---------------------------------------------------------------------
# All nine write endpoints
# ---------------------------------------------------------------------


def test_review_submit_approve_happy_path(client, auth_headers, gov_store):
    r1 = client.post(
        "/api/governance/review/agg-1/submit", json=_submit_body(), headers=auth_headers
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/governance/review/agg-1/approve",
        json=_submit_body(decision_id="d2", idempotency_key="k2", occurred_at=LATER_TS),
        headers=auth_headers,
    )
    assert r2.status_code == 201
    assert r2.json()["event"]["new_status"] == "approved"


def test_review_submit_reject_happy_path(client, auth_headers, gov_store):
    client.post("/api/governance/review/agg-2/submit", json=_submit_body(), headers=auth_headers)
    r = client.post(
        "/api/governance/review/agg-2/reject",
        json=_submit_body(decision_id="d2", idempotency_key="k2", occurred_at=LATER_TS),
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["event"]["new_status"] == "rejected"


def test_publication_activate_supersede_archive(client, auth_headers, gov_store):
    r1 = client.post(
        "/api/governance/publication/rev-1/activate", json=_submit_body(), headers=auth_headers
    )
    assert r1.status_code == 201
    assert r1.json()["event"]["new_status"] == "active"

    r2 = client.post(
        "/api/governance/publication/rev-1/supersede",
        json=_submit_body(
            decision_id="d2",
            idempotency_key="k2",
            occurred_at=LATER_TS,
            superseded_by_id="rev-2",
        ),
        headers=auth_headers,
    )
    assert r2.status_code == 201
    assert r2.json()["event"]["new_status"] == "superseded"
    assert r2.json()["event"]["superseded_by_id"] == "rev-2"

    r3 = client.post(
        "/api/governance/publication/rev-3/activate",
        json=_submit_body(decision_id="d3", idempotency_key="k3"),
        headers=auth_headers,
    )
    r4 = client.post(
        "/api/governance/publication/rev-3/archive",
        json=_submit_body(decision_id="d4", idempotency_key="k4", occurred_at=LATER_TS),
        headers=auth_headers,
    )
    assert r3.status_code == 201 and r4.status_code == 201
    assert r4.json()["event"]["new_status"] == "archived"


def test_resolution_resolve_reject_waive(client, auth_headers, gov_store):
    r1 = client.post(
        "/api/governance/resolution/issue-1/resolve", json=_submit_body(), headers=auth_headers
    )
    r2 = client.post(
        "/api/governance/resolution/issue-2/reject",
        json=_submit_body(decision_id="d2", idempotency_key="k2"),
        headers=auth_headers,
    )
    r3 = client.post(
        "/api/governance/resolution/issue-3/waive",
        json=_submit_body(decision_id="d3", idempotency_key="k3"),
        headers=auth_headers,
    )
    assert [r.status_code for r in (r1, r2, r3)] == [201, 201, 201]
    assert r1.json()["event"]["new_status"] == "resolved"
    assert r2.json()["event"]["new_status"] == "rejected"
    assert r3.json()["event"]["new_status"] == "waived"


# ---------------------------------------------------------------------
# Idempotency / conflict / transition errors
# ---------------------------------------------------------------------


def test_identical_retry_returns_200_and_original_event(client, auth_headers, gov_store):
    r1 = client.post(
        "/api/governance/review/agg-3/submit", json=_submit_body(), headers=auth_headers
    )
    r2 = client.post(
        "/api/governance/review/agg-3/submit", json=_submit_body(), headers=auth_headers
    )
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r2.json()["result"] == "existing"
    assert r2.json()["idempotent"] is True
    assert r2.json()["event"]["event_id"] == r1.json()["event"]["event_id"]


def test_idempotency_conflict_returns_409(client, auth_headers, gov_store):
    client.post("/api/governance/review/agg-4/submit", json=_submit_body(), headers=auth_headers)
    r = client.post(
        "/api/governance/review/agg-4/submit",
        json=_submit_body(aggregate_type="different_type"),
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_duplicate_decision_id_returns_409(client, auth_headers, gov_store):
    client.post("/api/governance/review/agg-5/submit", json=_submit_body(), headers=auth_headers)
    r = client.post(
        "/api/governance/review/agg-6/submit",
        json=_submit_body(idempotency_key="k-different"),
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_invalid_transition_returns_409(client, auth_headers, gov_store):
    r = client.post(
        "/api/governance/review/agg-7/approve", json=_submit_body(), headers=auth_headers
    )
    assert r.status_code == 409


def test_terminal_state_reopen_rejected(client, auth_headers, gov_store):
    client.post("/api/governance/review/agg-8/submit", json=_submit_body(), headers=auth_headers)
    client.post(
        "/api/governance/review/agg-8/approve",
        json=_submit_body(decision_id="d2", idempotency_key="k2", occurred_at=LATER_TS),
        headers=auth_headers,
    )
    r = client.post(
        "/api/governance/review/agg-8/submit",
        json=_submit_body(decision_id="d3", idempotency_key="k3", occurred_at=LATER_TS),
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_publication_supersede_requires_superseded_by_id(client, auth_headers, gov_store):
    client.post(
        "/api/governance/publication/rev-9/activate", json=_submit_body(), headers=auth_headers
    )
    # superseded_by_id is a required (non-Optional) field on
    # PublicationSupersedeRequest, so omitting it is a 422 at the
    # request-validation layer.
    body = _submit_body(decision_id="d2", idempotency_key="k2", occurred_at=LATER_TS)
    r = client.post(
        "/api/governance/publication/rev-9/supersede", json=body, headers=auth_headers
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------
# Aggregate ID / aggregate type separation
# ---------------------------------------------------------------------


def test_aggregate_id_separation(client, auth_headers, gov_store):
    client.post("/api/governance/review/agg-A/submit", json=_submit_body(), headers=auth_headers)
    r = client.get(
        "/api/governance/agg-B/history?aggregate_type=calc_revision", headers=auth_headers
    )
    assert r.status_code == 404


def test_aggregate_type_separation(client, auth_headers, gov_store):
    client.post(
        "/api/governance/review/agg-C/submit",
        json=_submit_body(aggregate_type="calc_revision"),
        headers=auth_headers,
    )
    r = client.get(
        "/api/governance/agg-C/history?aggregate_type=joint_revision", headers=auth_headers
    )
    assert r.status_code == 404
    r2 = client.get(
        "/api/governance/agg-C/history?aggregate_type=calc_revision", headers=auth_headers
    )
    assert r2.status_code == 200


# ---------------------------------------------------------------------
# Safe error mapping / no leakage
# ---------------------------------------------------------------------


def test_unconfigured_store_returns_503_without_path_leak(client, auth_headers, monkeypatch):
    appmod.app.dependency_overrides.pop(get_governance_store, None)
    monkeypatch.delenv(GOVERNANCE_EVENT_STORE_PATH_ENV, raising=False)
    r = client.get(
        "/api/governance/agg-1/history?aggregate_type=calc_revision", headers=auth_headers
    )
    assert r.status_code == 503
    assert "/" not in r.json()["detail"]  # no path-like content
    assert "Traceback" not in r.text


def test_corrupted_store_returns_503_without_leak(client, auth_headers, tmp_path):
    path = tmp_path / "events.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = FileGovernanceEventStore(path)
    appmod.app.dependency_overrides[get_governance_store] = lambda: store
    try:
        r = client.get(
            "/api/governance/agg-1/history?aggregate_type=calc_revision", headers=auth_headers
        )
        assert r.status_code == 503
        assert str(tmp_path) not in r.text
        assert "Traceback" not in r.text
        assert "JSONDecodeError" not in r.text
    finally:
        appmod.app.dependency_overrides.pop(get_governance_store, None)


def test_malformed_occurred_at_returns_422(client, auth_headers, gov_store):
    r = client.post(
        "/api/governance/review/agg-9/submit",
        json=_submit_body(occurred_at="not-a-timestamp"),
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_temporary_injected_store_path_via_env_var(client, auth_headers, tmp_path, monkeypatch):
    """Proves the TORQPRO_GOVERNANCE_EVENT_STORE_PATH environment-
    variable pathway itself works end to end (not just the
    dependency-override test shortcut used elsewhere in this file)."""
    appmod.app.dependency_overrides.pop(get_governance_store, None)
    monkeypatch.setenv(GOVERNANCE_EVENT_STORE_PATH_ENV, str(tmp_path / "env-events.json"))
    r = client.post(
        "/api/governance/review/agg-env/submit", json=_submit_body(), headers=auth_headers
    )
    assert r.status_code == 201
    assert (tmp_path / "env-events.json").exists()


# ---------------------------------------------------------------------
# Isolation from existing mechanisms
# ---------------------------------------------------------------------


def test_no_existing_ledger_or_table_modified(client, auth_headers, gov_store):
    washer_ledger_path = (
        appmod.BASE / "backend" / "library" / "data" / "washer_resolution_ledger.json"
    )
    decisions_ledger_path = (
        appmod.BASE / "backend" / "library" / "data" / "washer_resolution_decisions.json"
    )
    before_ledger = washer_ledger_path.read_bytes() if washer_ledger_path.exists() else None
    before_decisions = (
        decisions_ledger_path.read_bytes() if decisions_ledger_path.exists() else None
    )
    with appmod.conn() as c:
        before_audit_count = c.execute("SELECT COUNT(*) n FROM audit_log").fetchone()["n"]

    client.post(
        "/api/governance/review/agg-isolated/submit", json=_submit_body(), headers=auth_headers
    )
    client.post(
        "/api/governance/publication/agg-isolated/activate",
        json=_submit_body(decision_id="d2", idempotency_key="k2"),
        headers=auth_headers,
    )

    after_ledger = washer_ledger_path.read_bytes() if washer_ledger_path.exists() else None
    after_decisions = (
        decisions_ledger_path.read_bytes() if decisions_ledger_path.exists() else None
    )
    with appmod.conn() as c:
        after_audit_count = c.execute("SELECT COUNT(*) n FROM audit_log").fetchone()["n"]

    assert before_ledger == after_ledger
    assert before_decisions == after_decisions
    assert before_audit_count == after_audit_count


# ---------------------------------------------------------------------
# Deterministic ordering / valid stable JSON
# ---------------------------------------------------------------------


def test_deterministic_event_ordering_in_history(client, auth_headers, gov_store):
    client.post(
        "/api/governance/review/agg-order/submit", json=_submit_body(), headers=auth_headers
    )
    client.post(
        "/api/governance/review/agg-order/approve",
        json=_submit_body(decision_id="d2", idempotency_key="k2", occurred_at=LATER_TS),
        headers=auth_headers,
    )
    r = client.get(
        "/api/governance/agg-order/history?aggregate_type=calc_revision", headers=auth_headers
    )
    statuses = [e["new_status"] for e in r.json()["events"]]
    assert statuses == ["under_review", "approved"]


def test_response_is_valid_stable_json(client, auth_headers, gov_store):
    client.post(
        "/api/governance/review/agg-json/submit", json=_submit_body(), headers=auth_headers
    )
    r1 = client.get(
        "/api/governance/agg-json/history?aggregate_type=calc_revision", headers=auth_headers
    )
    r2 = client.get(
        "/api/governance/agg-json/history?aggregate_type=calc_revision", headers=auth_headers
    )
    parsed1 = json.loads(r1.text)
    parsed2 = json.loads(r2.text)
    assert parsed1 == parsed2


# ---------------------------------------------------------------------
# Faz 2.8.12 Stage 2 -- washer_resolution aggregate-ownership guard.
#
# "washer_resolution" was never used as an aggregate_type by any test
# above (verified before this module was written), so none of the
# preceding tests are affected by the guard added in
# backend.governance.api._run_command.
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/governance/review/washer-1/submit",
        "/api/governance/review/washer-1/approve",
        "/api/governance/review/washer-1/reject",
        "/api/governance/publication/washer-1/archive",
        "/api/governance/resolution/washer-1/resolve",
        "/api/governance/resolution/washer-1/reject",
        "/api/governance/resolution/washer-1/waive",
    ],
)
def test_washer_resolution_aggregate_type_rejected_on_generic_write_endpoints(
    client, auth_headers, gov_store, path
):
    r = client.post(
        path,
        json=_submit_body(aggregate_type="washer_resolution"),
        headers=auth_headers,
    )
    assert r.status_code == 409
    assert "washer_resolution" in r.text
    # No event was ever written for the rejected request.
    assert gov_store.events_for_aggregate("washer-1") == []


def test_washer_resolution_aggregate_type_still_readable(client, auth_headers, gov_store):
    """The ownership guard applies only to the nine generic write
    endpoints -- read endpoints (history/status) remain available for
    any aggregate_type, including washer_resolution, so events written
    by the internal synchronization path stay visible."""
    from backend.governance.service import resolve_resolution

    resolve_resolution(
        gov_store,
        aggregate_id="washer-read-1",
        aggregate_type="washer_resolution",
        decision_id="DEC-1",
        idempotency_key="washer-sync:idem-1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    r = client.get(
        "/api/governance/washer-read-1/history?aggregate_type=washer_resolution",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["total_events"] == 1


def test_other_aggregate_types_unaffected_by_ownership_guard(client, auth_headers, gov_store):
    r = client.post(
        "/api/governance/resolution/issue-unaffected/resolve",
        json=_submit_body(aggregate_type="calc_revision"),
        headers=auth_headers,
    )
    assert r.status_code == 201
