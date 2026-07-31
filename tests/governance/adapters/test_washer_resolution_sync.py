"""Faz 2.8.12 Stage 2 tests:
backend.governance.adapters.washer_resolution_sync."""

from __future__ import annotations

import pytest

from backend.governance.adapters.washer_resolution_sync import (
    AGGREGATE_TYPE,
    SyncOutcome,
    sync_washer_decision,
)
from backend.governance.store import FileGovernanceEventStore
from backend.library.washer_resolution import WasherResolutionStatus
from backend.library.washer_resolution_decisions import WasherResolutionDecision

FIXED_CHECKSUM = "0" * 64


def _decision(
    *,
    decision_id="DEC-1",
    resolution_id="RES-1",
    previous_status=WasherResolutionStatus.OPEN,
    new_status=WasherResolutionStatus.RESOLVED,
    resolution_note="note",
    evidence_reference="evidence",
    resolved_by="ilhan",
    decided_at="2026-07-30T10:00:00.000000Z",
    idempotency_key="idem-1",
) -> WasherResolutionDecision:
    return WasherResolutionDecision(
        decision_id=decision_id,
        resolution_id=resolution_id,
        previous_status=previous_status,
        new_status=new_status,
        resolution_note=resolution_note,
        evidence_reference=evidence_reference,
        resolved_by=resolved_by,
        decided_at=decided_at,
        integrity_checksum=FIXED_CHECKSUM,
        idempotency_key=idempotency_key,
    )


@pytest.fixture
def store(tmp_path):
    return FileGovernanceEventStore(tmp_path / "events.json")


# ---------------------------------------------------------------------
# Non-representable / non-eligible classification (never touches store)
# ---------------------------------------------------------------------


def test_open_is_skipped_without_store():
    decision = _decision(new_status=WasherResolutionStatus.OPEN)
    result = sync_washer_decision(decision, store=None)
    assert result.outcome == SyncOutcome.SKIPPED_OPEN
    assert result.event_written is False


def test_under_review_is_not_representable(store):
    decision = _decision(new_status=WasherResolutionStatus.UNDER_REVIEW)
    result = sync_washer_decision(decision, store=store)
    assert result.outcome == SyncOutcome.NOT_REPRESENTABLE
    assert result.event_written is False
    # Never writes a governance event for a non-representable decision.
    assert store.all_events() == []


def test_open_never_touches_store_even_if_provided(store):
    decision = _decision(new_status=WasherResolutionStatus.OPEN)
    result = sync_washer_decision(decision, store=store)
    assert result.outcome == SyncOutcome.SKIPPED_OPEN
    assert store.all_events() == []


# ---------------------------------------------------------------------
# Store-unconfigured handling
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "new_status",
    [
        WasherResolutionStatus.RESOLVED,
        WasherResolutionStatus.ACCEPTED_AS_IS,
        WasherResolutionStatus.REJECTED,
    ],
)
def test_eligible_decision_without_store_is_classified_unconfigured(new_status):
    decision = _decision(new_status=new_status)
    result = sync_washer_decision(decision, store=None)
    assert result.outcome == SyncOutcome.GOVERNANCE_STORE_UNCONFIGURED
    assert result.event_written is False


# ---------------------------------------------------------------------
# Representable statuses -- successful sync
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "washer_status,canonical_status",
    [
        (WasherResolutionStatus.RESOLVED, "resolved"),
        (WasherResolutionStatus.ACCEPTED_AS_IS, "waived"),
        (WasherResolutionStatus.REJECTED, "rejected"),
    ],
)
def test_representable_statuses_synchronize(store, washer_status, canonical_status):
    decision = _decision(new_status=washer_status)
    result = sync_washer_decision(decision, store=store, synchronized_at="2026-07-30T10:05:00Z")

    assert result.outcome == SyncOutcome.SYNCHRONIZED
    assert result.event_written is True

    events = store.events_for_aggregate(decision.resolution_id)
    assert len(events) == 1
    event = events[0]
    assert event.aggregate_type == AGGREGATE_TYPE
    assert event.aggregate_id == decision.resolution_id
    assert event.decision_id == decision.decision_id
    assert event.new_status == canonical_status
    assert event.idempotency_key == f"washer-sync:{decision.idempotency_key}"
    assert event.metadata["source_decision_id"] == decision.decision_id
    assert event.metadata["source_idempotency_key"] == decision.idempotency_key
    assert event.metadata["source_aggregate_id"] == decision.resolution_id
    assert event.metadata["synchronized_at"] == "2026-07-30T10:05:00Z"
    assert event.metadata["synchronized_at"] != event.occurred_at
    assert event.occurred_at == decision.decided_at


def test_identifiers_are_never_transformed(store):
    decision = _decision(decision_id="DEC-preserve-me-exactly", resolution_id="RES-preserve")
    sync_washer_decision(decision, store=store)
    event = store.events_for_aggregate("RES-preserve")[0]
    assert event.decision_id == "DEC-preserve-me-exactly"
    assert event.aggregate_id == "RES-preserve"


# ---------------------------------------------------------------------
# Idempotent replay
# ---------------------------------------------------------------------


def test_replay_is_already_synchronized_not_a_second_event(store):
    decision = _decision()
    first = sync_washer_decision(decision, store=store)
    second = sync_washer_decision(decision, store=store)

    assert first.outcome == SyncOutcome.SYNCHRONIZED
    assert second.outcome == SyncOutcome.ALREADY_SYNCHRONIZED
    assert second.event_written is False
    assert len(store.events_for_aggregate(decision.resolution_id)) == 1


def test_conflicting_reuse_of_idempotency_key_is_failed_not_replayed(store):
    decision = _decision(idempotency_key="shared-key")
    sync_washer_decision(decision, store=store)

    conflicting = _decision(
        decision_id="DEC-different",
        resolution_id="RES-different",
        idempotency_key="shared-key",
    )
    result = sync_washer_decision(conflicting, store=store)

    assert result.outcome == SyncOutcome.FAILED
    assert result.safe_error_category == "idempotency_conflict"
    assert result.retry_may_help is False
    # No second/overwritten event was written for the conflicting aggregate.
    assert store.events_for_aggregate("RES-different") == []


def test_global_uniqueness_conflict_against_other_aggregate_types(store):
    """ADR-0015 'Global Identifier Protection': governance decision_id/
    idempotency_key uniqueness is global, not aggregate-scoped. A
    pre-existing event for an unrelated aggregate_type using the same
    sync idempotency key must be treated as a conflict, never as a
    valid replay."""
    from backend.governance.service import resolve_resolution

    # Simulate a foreign event that happens to reuse the same
    # namespaced idempotency key under a different aggregate entirely.
    resolve_resolution(
        store,
        aggregate_id="SOME-OTHER-AGGREGATE",
        aggregate_type="not_washer_resolution",
        decision_id="DEC-1",
        idempotency_key="washer-sync:idem-1",
        actor="someone",
        occurred_at="2026-07-30T09:00:00Z",
    )

    decision = _decision(decision_id="DEC-1", resolution_id="RES-1", idempotency_key="idem-1")
    result = sync_washer_decision(decision, store=store)

    assert result.outcome == SyncOutcome.FAILED
    assert result.safe_error_category == "idempotency_conflict"


# ---------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------


def test_dry_run_never_writes(store):
    decision = _decision()
    result = sync_washer_decision(decision, store=store, dry_run=True)

    assert result.outcome == SyncOutcome.WOULD_SYNCHRONIZE
    assert result.event_written is False
    assert store.all_events() == []


def test_dry_run_recognizes_already_synchronized(store):
    decision = _decision()
    sync_washer_decision(decision, store=store, dry_run=False)
    result = sync_washer_decision(decision, store=store, dry_run=True)

    assert result.outcome == SyncOutcome.ALREADY_SYNCHRONIZED
    assert len(store.all_events()) == 1


def test_dry_run_never_calls_a_write_even_when_would_conflict(store):
    decision = _decision(idempotency_key="shared-key")
    sync_washer_decision(decision, store=store)

    conflicting = _decision(
        decision_id="DEC-different",
        resolution_id="RES-different",
        idempotency_key="shared-key",
    )
    result = sync_washer_decision(conflicting, store=store, dry_run=True)

    assert result.outcome == SyncOutcome.FAILED
    assert result.safe_error_category == "idempotency_conflict"
    assert store.events_for_aggregate("RES-different") == []


# ---------------------------------------------------------------------
# Result never leaks unsafe detail
# ---------------------------------------------------------------------


def test_result_never_contains_filesystem_path(tmp_path):
    secret_path = tmp_path / "super_secret_governance_events.json"
    store = FileGovernanceEventStore(secret_path)
    decision = _decision()
    result = sync_washer_decision(decision, store=store)
    combined = str(result)
    assert str(secret_path) not in combined
    assert "super_secret" not in combined


# ---------------------------------------------------------------------
# Faz 2.8.12 Stage 3 -- sync_washer_decision_and_log (the exact call
# site backend/app.py's washer decide endpoint uses).
# ---------------------------------------------------------------------


def test_and_log_delegates_to_sync_washer_decision_and_returns_same_result(store):
    from backend.governance.adapters.washer_resolution_sync import (
        sync_washer_decision_and_log,
    )

    decision = _decision()
    result = sync_washer_decision_and_log(decision, store)
    assert result.outcome == SyncOutcome.SYNCHRONIZED
    assert result.event_written is True
    assert len(store.events_for_aggregate(decision.resolution_id)) == 1


def test_and_log_never_raises_when_logging_handler_is_broken(store, monkeypatch):
    """Even if the logging call itself fails (simulated), the caller
    must still get a valid SyncResult back -- logging must never be
    able to break the washer response."""
    import backend.governance.adapters.washer_resolution_sync as sync_mod

    class _BrokenLogger:
        def info(self, *args, **kwargs):
            raise RuntimeError("simulated logging handler failure")

    monkeypatch.setattr(sync_mod, "_LOGGER", _BrokenLogger())

    decision = _decision()
    result = sync_mod.sync_washer_decision_and_log(decision, store)
    assert result.outcome == SyncOutcome.SYNCHRONIZED


def test_and_log_emits_safe_fields_only(store, caplog):
    import logging

    from backend.governance.adapters.washer_resolution_sync import (
        sync_washer_decision_and_log,
    )

    decision = _decision(
        resolution_note="a secret internal note nobody else should see verbatim",
        evidence_reference="internal://confidential/path",
    )
    with caplog.at_level(logging.INFO, logger="torqpro"):
        sync_washer_decision_and_log(decision, store)

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert decision.resolution_id in message
    assert decision.decision_id in message
    assert "synchronized" in message
    # Never leaks the decision's own free-text fields.
    assert "secret internal note" not in message
    assert "confidential" not in message


def test_and_log_governance_store_unconfigured_still_returns_result():
    from backend.governance.adapters.washer_resolution_sync import (
        sync_washer_decision_and_log,
    )

    decision = _decision()
    result = sync_washer_decision_and_log(decision, None)
    assert result.outcome == SyncOutcome.GOVERNANCE_STORE_UNCONFIGURED
