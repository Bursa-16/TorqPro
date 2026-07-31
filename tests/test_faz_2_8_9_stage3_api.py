"""Faz 2.8.9 tests (Stage 3): washer resolution decision API endpoints.

Covers: GET queue, GET decision history, POST decide (success, 404
unknown resolution, 409 blocked_authoritative_source, 409 invalid
transition, 400 invalid new_status/confidence_level/missing
idempotency key, 422 blank note/evidence), idempotent replay, backend-
generated decided_at, auth requirement, and a final sanity check that
the real Faz 2.8.5 source ledger's status counts are unchanged.

Every test's writes go through
``backend.library.washer_resolution_decisions_store`` with
``DATA_PATH``/``_LOCK_PATH`` monkeypatched to an isolated ``tmp_path``
file, per task brief rule 3 -- the real, committed
``washer_resolution_decisions.json`` is never written to by this
file, and ``washer_resolution_ledger.json`` (source ledger) is never
written to by anything in Faz 2.8.9.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.library import washer_resolution as wr
from backend.library import washer_resolution_decisions_store as store

client = TestClient(app)


def _login():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def auth_headers():
    return _login()


@pytest.fixture()
def isolated_ledger(tmp_path, monkeypatch):
    ledger_path = tmp_path / "washer_resolution_decisions.json"
    ledger_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "name": "Washer Resolution Decision Ledger",
                    "version": "test",
                    "source_ledger": "backend/library/data/washer_resolution_ledger.json",
                    "record_count": 0,
                },
                "decisions": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "DATA_PATH", ledger_path)
    monkeypatch.setattr(store, "_LOCK_PATH", ledger_path.with_suffix(".lock"))
    store.reload()
    yield ledger_path
    store.reload()


# A known-open record from the real Faz 2.8.5 ledger (read-only reference).
OPEN_RESOLUTION_ID = "RES-WASH-DIN127B-M10"
# A known-blocked record (ISO 7093 identity ambiguity).
BLOCKED_RESOLUTION_ID = "RES-WASH-ISO7093-M10"


def _decide_payload(**overrides):
    base = dict(
        new_status="under_review",
        resolution_note="Escalated for secondary source review.",
        evidence_reference="internal-review-log#2026-07-29",
        resolved_by="ilhan",
        idempotency_key="test-key-0001",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------


class TestAuthRequired:
    def test_queue_requires_auth(self, isolated_ledger):
        r = client.get("/api/library/washers/resolutions/queue")
        assert r.status_code in (401, 403)

    def test_decide_requires_auth(self, isolated_ledger):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(),
        )
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------


class TestQueueEndpoint:
    def test_queue_has_76_records(self, isolated_ledger, auth_headers):
        r = client.get("/api/library/washers/resolutions/queue", headers=auth_headers)
        assert r.status_code == 200
        records = r.json()["records"]
        assert len(records) == 76

    def test_queue_counts_match_known_distribution(self, isolated_ledger, auth_headers):
        r = client.get("/api/library/washers/resolutions/queue", headers=auth_headers)
        records = r.json()["records"]
        open_count = sum(1 for rec in records if rec["source_status"] == "open")
        blocked_count = sum(
            1 for rec in records if rec["source_status"] == "blocked_authoritative_source"
        )
        assert open_count == 71
        assert blocked_count == 5

    def test_blocked_record_flagged(self, isolated_ledger, auth_headers):
        r = client.get("/api/library/washers/resolutions/queue", headers=auth_headers)
        records = {rec["resolution_id"]: rec for rec in r.json()["records"]}
        blocked = records[BLOCKED_RESOLUTION_ID]
        assert blocked["is_blocked"] is True
        assert blocked["effective_status"] == "blocked_authoritative_source"
        assert blocked["decision_count"] == 0

    def test_effective_status_reflects_recorded_decision(self, isolated_ledger, auth_headers):
        client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(),
            headers=auth_headers,
        )
        r = client.get("/api/library/washers/resolutions/queue", headers=auth_headers)
        records = {rec["resolution_id"]: rec for rec in r.json()["records"]}
        target = records[OPEN_RESOLUTION_ID]
        assert target["source_status"] == "open"  # source ledger unchanged
        assert target["effective_status"] == "under_review"  # workflow overlay
        assert target["decision_count"] == 1


# ---------------------------------------------------------------------
# Decide: success path
# ---------------------------------------------------------------------


class TestDecideSuccess:
    def test_decide_returns_200_and_decision(self, isolated_ledger, auth_headers):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(),
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] is True
        decision = body["decision"]
        assert decision["resolution_id"] == OPEN_RESOLUTION_ID
        assert decision["previous_status"] == "open"
        assert decision["new_status"] == "under_review"
        assert decision["idempotency_key"] == "test-key-0001"

    def test_decided_at_is_backend_generated_utc(self, isolated_ledger, auth_headers):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(),
            headers=auth_headers,
        )
        decided_at = r.json()["decision"]["decided_at"]
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$", decided_at)

    def test_client_supplied_decided_at_is_ignored_if_sent(self, isolated_ledger, auth_headers):
        payload = _decide_payload()
        payload["decided_at"] = "1999-01-01T00:00:00Z"  # not a real schema field
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=payload,
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert not r.json()["decision"]["decided_at"].startswith("1999")

    def test_history_endpoint_reflects_decision(self, isolated_ledger, auth_headers):
        client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(),
            headers=auth_headers,
        )
        r = client.get(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decisions",
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert len(r.json()["decisions"]) == 1

    def test_source_ledger_untouched_after_decide(self, isolated_ledger, auth_headers):
        client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(),
            headers=auth_headers,
        )
        wr.reload()
        record = wr.get_washer_resolution(OPEN_RESOLUTION_ID)
        assert record.resolution_status == wr.WasherResolutionStatus.OPEN


# ---------------------------------------------------------------------
# Decide: idempotency
# ---------------------------------------------------------------------


class TestDecideIdempotency:
    def test_repeated_request_same_key_does_not_duplicate(self, isolated_ledger, auth_headers):
        payload = _decide_payload(idempotency_key="replay-key")
        first = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=payload,
            headers=auth_headers,
        )
        second = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=payload,
            headers=auth_headers,
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["created"] is True
        assert second.json()["created"] is False
        assert (
            first.json()["decision"]["decision_id"]
            == second.json()["decision"]["decision_id"]
        )
        history = client.get(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decisions",
            headers=auth_headers,
        )
        assert len(history.json()["decisions"]) == 1

    def test_missing_idempotency_key_rejected(self, isolated_ledger, auth_headers):
        payload = _decide_payload()
        del payload["idempotency_key"]
        payload["idempotency_key"] = ""
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=payload,
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_same_key_different_request_is_409(self, isolated_ledger, auth_headers):
        key = "conflict-key"
        first = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(idempotency_key=key, resolution_note="first note"),
            headers=auth_headers,
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(
                idempotency_key=key, resolution_note="a completely different note"
            ),
            headers=auth_headers,
        )
        assert second.status_code == 409
        # No second decision was appended.
        history = client.get(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decisions",
            headers=auth_headers,
        )
        assert len(history.json()["decisions"]) == 1

    def test_same_key_different_resolution_id_is_409(self, isolated_ledger, auth_headers):
        key = "cross-resolution-key"
        other_open_id = "RES-WASH-DIN127B-M12"  # a different real open record
        first = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(idempotency_key=key),
            headers=auth_headers,
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/library/washers/resolutions/{other_open_id}/decide",
            json=_decide_payload(idempotency_key=key),
            headers=auth_headers,
        )
        assert second.status_code == 409

    def test_previous_status_client_field_is_ignored(self, isolated_ledger, auth_headers):
        """A client sending an (undeclared) previous_status field must
        not influence the server-computed effective status at all."""
        payload = _decide_payload()
        payload["previous_status"] = "resolved"  # not a real request field
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=payload,
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        # The server computed previous_status from the ledger (open),
        # not from the bogus client-sent value.
        assert r.json()["decision"]["previous_status"] == "open"


# ---------------------------------------------------------------------
# Decide: domain error -> HTTP mapping
# ---------------------------------------------------------------------


class TestDecideErrorMapping:
    def test_unknown_resolution_id_is_404(self, isolated_ledger, auth_headers):
        r = client.post(
            "/api/library/washers/resolutions/RES-DOES-NOT-EXIST/decide",
            json=_decide_payload(),
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_blocked_source_record_is_409(self, isolated_ledger, auth_headers):
        r = client.post(
            f"/api/library/washers/resolutions/{BLOCKED_RESOLUTION_ID}/decide",
            json=_decide_payload(),
            headers=auth_headers,
        )
        assert r.status_code == 409

    def test_blocked_record_status_unaffected_by_rejected_attempt(
        self, isolated_ledger, auth_headers
    ):
        client.post(
            f"/api/library/washers/resolutions/{BLOCKED_RESOLUTION_ID}/decide",
            json=_decide_payload(),
            headers=auth_headers,
        )
        r = client.get("/api/library/washers/resolutions/queue", headers=auth_headers)
        records = {rec["resolution_id"]: rec for rec in r.json()["records"]}
        assert records[BLOCKED_RESOLUTION_ID]["effective_status"] == "blocked_authoritative_source"
        assert records[BLOCKED_RESOLUTION_ID]["decision_count"] == 0

    def test_terminal_reopen_is_409(self, isolated_ledger, auth_headers):
        # First: open -> resolved (terminal).
        client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="resolved", idempotency_key="k-terminal-1"),
            headers=auth_headers,
        )
        # Second, distinct idempotency key: any further transition must
        # be rejected -- reopening a terminal record is out of scope.
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="open", idempotency_key="k-terminal-2"),
            headers=auth_headers,
        )
        assert r.status_code == 409

    def test_invalid_new_status_is_400(self, isolated_ledger, auth_headers):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="not_a_real_status"),
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_invalid_confidence_level_is_400(self, isolated_ledger, auth_headers):
        payload = _decide_payload()
        payload["confidence_level"] = 99
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=payload,
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_blank_resolution_note_is_422(self, isolated_ledger, auth_headers):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(resolution_note="   "),
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_blank_evidence_reference_is_422(self, isolated_ledger, auth_headers):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(evidence_reference=""),
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_blank_resolved_by_is_422(self, isolated_ledger, auth_headers):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(resolved_by="   "),
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_duplicate_decision_id_maps_to_409(self, isolated_ledger, auth_headers, monkeypatch):
        """Force a decision_id collision (server-generated uuid4 is
        practically never a collision in production; monkeypatched
        here purely to exercise the DuplicateDecisionIdError -> 409
        HTTP mapping)."""
        import uuid as uuid_module

        from backend.library import washer_resolution_service as svc_module

        fixed = uuid_module.UUID("00000000-0000-0000-0000-000000000001")
        monkeypatch.setattr(svc_module.uuid, "uuid4", lambda: fixed)

        first = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(idempotency_key="dup-key-1"),
            headers=auth_headers,
        )
        assert first.status_code == 200

        second = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(idempotency_key="dup-key-2", new_status="rejected"),
            headers=auth_headers,
        )
        assert second.status_code == 409

    def test_corrupted_ledger_is_500_without_leaking_internals(
        self, isolated_ledger, auth_headers
    ):
        isolated_ledger.write_text("{ this is not valid json", encoding="utf-8")
        store.reload()
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(idempotency_key="corrupt-ledger-key"),
            headers=auth_headers,
        )
        assert r.status_code == 500
        body_text = r.text
        assert "Traceback" not in body_text
        assert str(isolated_ledger) not in body_text
        assert "/home/" not in body_text
        assert "\\" not in body_text or "washer_resolution_decisions.json" not in body_text


# ---------------------------------------------------------------------
# Stage 3 fix: cross-platform lock fallback (fcntl unavailable, e.g.
# Windows) must not crash the module and must still serialize writes
# correctly via the in-process lock.
# ---------------------------------------------------------------------


class TestLockPlatformFallback:
    def test_module_import_does_not_require_fcntl(self):
        """The module must already be importable regardless of
        platform (this process is Linux, so this mainly documents the
        guarantee) -- the real guard is the top-of-module
        try/except ImportError around `import fcntl`."""
        assert hasattr(store, "_HAS_FCNTL")

    def test_fallback_path_still_serializes_and_persists_correctly(
        self, isolated_ledger, monkeypatch
    ):
        """Force the non-fcntl branch of _locked() (as if fcntl were
        unavailable) and confirm append-only persistence and
        idempotency still work correctly through it."""
        monkeypatch.setattr(store, "_HAS_FCNTL", False)

        decision = store.build_decision(
            decision_id="DEC-FALLBACK-1",
            resolution_id="RES-TEST-0001",
            previous_status=wr.WasherResolutionStatus.OPEN,
            new_status=wr.WasherResolutionStatus.UNDER_REVIEW,
            resolution_note="Fallback-path note.",
            evidence_reference="fallback-evidence",
            resolved_by="ilhan",
            decided_at="2026-07-29T12:00:00Z",
            idempotency_key="fallback-key",
        )
        first, created_first = store.record_decision(decision)
        second, created_second = store.record_decision(decision)

        assert created_first is True
        assert created_second is False
        assert len(store.list_decisions()) == 1

    def test_fallback_path_concurrent_threads_still_safe(
        self, isolated_ledger, monkeypatch
    ):
        import threading

        monkeypatch.setattr(store, "_HAS_FCNTL", False)

        def worker(i):
            decision = store.build_decision(
                decision_id=f"DEC-FB-RACE-{i}",
                resolution_id="RES-TEST-0001",
                previous_status=wr.WasherResolutionStatus.OPEN,
                new_status=wr.WasherResolutionStatus.UNDER_REVIEW,
                resolution_note="race",
                evidence_reference="race-evidence",
                resolved_by="ilhan",
                decided_at="2026-07-29T12:00:00Z",
                idempotency_key="fallback-race-key",
            )
            store.record_decision(decision)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(store.list_decisions()) == 1


# ---------------------------------------------------------------------
# Final regression sanity (real files, not isolated_ledger)
# ---------------------------------------------------------------------


class TestRealDataUnaffected:
    def test_real_decision_ledger_file_still_empty(self):
        from pathlib import Path

        real_path = (
            Path(__file__).resolve().parent.parent
            / "backend"
            / "library"
            / "data"
            / "washer_resolution_decisions.json"
        )
        payload = json.loads(real_path.read_text(encoding="utf-8"))
        assert payload["decisions"] == []

    def test_real_source_ledger_status_counts_unchanged(self):
        wr.reload()
        counts = wr.count_by_status()
        assert counts[wr.WasherResolutionStatus.OPEN.value] == 71
        assert counts[wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE.value] == 5


# ---------------------------------------------------------------------
# Faz 2.8.12 Stage 3 -- best-effort governance synchronization on the
# real decide endpoint. Every test here isolates BOTH the washer
# decision ledger (via isolated_ledger) AND the governance event store
# (via a per-test TORQPRO_GOVERNANCE_EVENT_STORE_PATH monkeypatch) --
# never the real, committed governance data (there is none by default)
# and never the real washer files.
# ---------------------------------------------------------------------


@pytest.fixture()
def governance_store_path(tmp_path, monkeypatch):
    """Points TORQPRO_GOVERNANCE_EVENT_STORE_PATH at an isolated
    temp file for the duration of one test. Unset by default in this
    file's other tests (monkeypatch auto-reverts), matching the
    default, unconfigured production deployment."""
    path = tmp_path / "governance_events.json"
    monkeypatch.setenv("TORQPRO_GOVERNANCE_EVENT_STORE_PATH", str(path))
    return path


def _governance_events(path):
    from backend.governance.store import FileGovernanceEventStore

    return FileGovernanceEventStore(path).all_events()


class TestGovernanceSyncOnDecideEndpoint:
    def test_terminal_decision_writes_one_governance_event_when_configured(
        self, isolated_ledger, auth_headers, governance_store_path
    ):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="resolved", idempotency_key="gov-sync-key-1"),
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

        events = _governance_events(governance_store_path)
        assert len(events) == 1
        event = events[0]
        assert event.aggregate_id == OPEN_RESOLUTION_ID
        assert event.aggregate_type == "washer_resolution"
        assert event.new_status == "resolved"
        assert event.idempotency_key == "washer-sync:gov-sync-key-1"

    def test_open_or_under_review_decision_writes_no_governance_event(
        self, isolated_ledger, auth_headers, governance_store_path
    ):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="under_review", idempotency_key="gov-sync-key-2"),
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert _governance_events(governance_store_path) == []

    def test_response_schema_unchanged_when_governance_configured(
        self, isolated_ledger, auth_headers, governance_store_path
    ):
        """The public response must contain exactly the same two top-
        level keys as before Stage 3 -- no governance field is added
        to it."""
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="resolved", idempotency_key="gov-sync-key-3"),
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert set(r.json().keys()) == {"decision", "created"}

    def test_decide_succeeds_when_governance_store_unconfigured(
        self, isolated_ledger, auth_headers, monkeypatch
    ):
        """Default deployment state (no isolated governance_store_path
        fixture applied): the washer decision must succeed exactly as
        it did before Stage 3 existed."""
        monkeypatch.delenv("TORQPRO_GOVERNANCE_EVENT_STORE_PATH", raising=False)
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="resolved", idempotency_key="gov-sync-key-4"),
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["decision"]["resolution_id"] == OPEN_RESOLUTION_ID

    def test_decide_succeeds_when_governance_sync_raises_unexpectedly(
        self, isolated_ledger, auth_headers, governance_store_path, monkeypatch
    ):
        """Even a defect inside the governance sync call path itself
        (simulated here) must never affect the washer response --
        the outermost try/except in the endpoint is the final safety
        net, independent of sync_washer_decision's own internal
        never-raise guarantee."""
        import backend.governance.adapters.washer_resolution_sync as sync_mod

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated governance sync defect")

        monkeypatch.setattr(sync_mod, "sync_washer_decision_and_log", _boom)

        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="resolved", idempotency_key="gov-sync-key-5"),
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["decision"]["resolution_id"] == OPEN_RESOLUTION_ID

    def test_repeated_terminal_decision_does_not_duplicate_governance_event(
        self, isolated_ledger, auth_headers, governance_store_path
    ):
        payload = _decide_payload(new_status="resolved", idempotency_key="gov-sync-key-6")
        r1 = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=payload,
            headers=auth_headers,
        )
        r2 = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=payload,
            headers=auth_headers,
        )
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["decision"] == r2.json()["decision"]
        assert r2.json()["created"] is False
        assert len(_governance_events(governance_store_path)) == 1

    def test_source_and_decision_ledgers_untouched_by_governance_sync(
        self, isolated_ledger, auth_headers, governance_store_path
    ):
        client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="resolved", idempotency_key="gov-sync-key-7"),
            headers=auth_headers,
        )
        wr.reload()
        record = wr.get_washer_resolution(OPEN_RESOLUTION_ID)
        assert record.resolution_status == wr.WasherResolutionStatus.OPEN

    def test_governance_event_recoverable_via_reconciliation_after_unconfigured_decide(
        self, isolated_ledger, auth_headers, tmp_path, monkeypatch
    ):
        """Process-gap equivalent (ADR-0015 failure/recovery
        semantics): a washer decision recorded while the governance
        store was unconfigured has no governance event yet; a later
        reconciliation run, once a store is configured, must recover
        it without any special-casing."""
        monkeypatch.delenv("TORQPRO_GOVERNANCE_EVENT_STORE_PATH", raising=False)
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json=_decide_payload(new_status="rejected", idempotency_key="gov-sync-key-8"),
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

        from backend.governance.adapters.washer_resolution_reconciliation import reconcile
        from backend.governance.store import FileGovernanceEventStore

        store_path = tmp_path / "recovery_events.json"
        governance_store = FileGovernanceEventStore(store_path)
        report = reconcile(governance_store, dry_run=False)

        assert report.counters["synchronized"] == 1
        events = governance_store.all_events()
        assert len(events) == 1
        assert events[0].aggregate_id == OPEN_RESOLUTION_ID
        assert events[0].new_status == "rejected"
