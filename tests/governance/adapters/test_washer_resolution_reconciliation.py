"""Faz 2.8.12 Stage 2 tests:
backend.governance.adapters.washer_resolution_reconciliation."""

from __future__ import annotations

import pytest

from backend.governance.adapters.washer_resolution_reconciliation import reconcile
from backend.governance.adapters.washer_resolution_sync import SyncOutcome
from backend.governance.store import FileGovernanceEventStore
from backend.library.washer_resolution import WasherResolutionStatus
from backend.library.washer_resolution_decisions import WasherResolutionDecision

FIXED_CHECKSUM = "0" * 64


def _decision(**overrides) -> WasherResolutionDecision:
    fields = dict(
        decision_id="DEC-1",
        resolution_id="RES-1",
        previous_status=WasherResolutionStatus.OPEN,
        new_status=WasherResolutionStatus.RESOLVED,
        resolution_note="note",
        evidence_reference="evidence",
        resolved_by="ilhan",
        decided_at="2026-07-30T10:00:00.000000Z",
        integrity_checksum=FIXED_CHECKSUM,
        idempotency_key="idem-1",
    )
    fields.update(overrides)
    return WasherResolutionDecision(**fields)


@pytest.fixture
def store(tmp_path):
    return FileGovernanceEventStore(tmp_path / "events.json")


def _mixed_decisions():
    return [
        _decision(decision_id="DEC-open", resolution_id="RES-open",
                  new_status=WasherResolutionStatus.OPEN, idempotency_key="idem-open"),
        _decision(decision_id="DEC-under-review", resolution_id="RES-under-review",
                  new_status=WasherResolutionStatus.UNDER_REVIEW, idempotency_key="idem-ur"),
        _decision(decision_id="DEC-resolved", resolution_id="RES-resolved",
                  new_status=WasherResolutionStatus.RESOLVED, idempotency_key="idem-resolved"),
        _decision(decision_id="DEC-accepted", resolution_id="RES-accepted",
                  new_status=WasherResolutionStatus.ACCEPTED_AS_IS,
                  idempotency_key="idem-accepted"),
        _decision(decision_id="DEC-rejected", resolution_id="RES-rejected",
                  new_status=WasherResolutionStatus.REJECTED, idempotency_key="idem-rejected"),
    ]


# ---------------------------------------------------------------------
# Counter invariant
# ---------------------------------------------------------------------


def test_counter_invariant_holds_on_mixed_batch(store):
    report = reconcile(store, decisions=_mixed_decisions(), dry_run=False)
    assert report.counters["scanned"] == 5
    assert report.counters["scanned"] == report.terminal_outcome_sum()
    assert report.counters["skipped_open"] == 1
    assert report.counters["not_representable"] == 1
    assert report.counters["synchronized"] == 3
    assert report.counters["eligible"] == 3  # excludes skipped_open/not_representable


def test_counter_invariant_holds_when_store_unconfigured():
    report = reconcile(None, decisions=_mixed_decisions(), dry_run=False)
    assert report.counters["scanned"] == 5
    assert report.counters["scanned"] == report.terminal_outcome_sum()
    assert report.counters["skipped_open"] == 1
    assert report.counters["not_representable"] == 1
    assert report.counters["governance_store_unconfigured"] == 3
    assert report.counters["synchronized"] == 0
    assert report.counters["failed"] == 0


def test_counter_invariant_holds_in_dry_run(store):
    report = reconcile(store, decisions=_mixed_decisions(), dry_run=True)
    assert report.counters["scanned"] == 5
    assert report.counters["scanned"] == report.terminal_outcome_sum()
    assert report.counters["would_synchronize"] == 3
    assert report.counters["synchronized"] == 0
    # Dry-run never actually writes.
    assert store.all_events() == []


def test_empty_batch_is_all_zero_counters(store):
    report = reconcile(store, decisions=[], dry_run=False)
    assert report.counters["scanned"] == 0
    assert report.terminal_outcome_sum() == 0
    assert all(v == 0 for v in report.counters.values())


# ---------------------------------------------------------------------
# Store-unconfigured behaviour (ADR-0015 Sec. "Store-Unconfigured Behaviour")
# ---------------------------------------------------------------------


def test_unconfigured_store_still_classifies_open_and_not_representable_accurately():
    report = reconcile(None, decisions=_mixed_decisions(), dry_run=False)
    outcomes = {r.washer_decision_id: r.outcome for r in report.records}
    assert outcomes["DEC-open"] == SyncOutcome.SKIPPED_OPEN
    assert outcomes["DEC-under-review"] == SyncOutcome.NOT_REPRESENTABLE
    assert outcomes["DEC-resolved"] == SyncOutcome.GOVERNANCE_STORE_UNCONFIGURED


def test_unconfigured_store_report_contains_no_env_var_hint():
    report = reconcile(None, decisions=_mixed_decisions(), dry_run=False)
    for record in report.records:
        assert "TORQPRO_GOVERNANCE_EVENT_STORE_PATH" not in (record.safe_message or "")
        assert "TORQPRO_GOVERNANCE_EVENT_STORE_PATH" not in (record.safe_error_category or "")


# ---------------------------------------------------------------------
# Idempotent re-run
# ---------------------------------------------------------------------


def test_rerun_is_idempotent(store):
    decisions = _mixed_decisions()
    first = reconcile(store, decisions=decisions, dry_run=False)
    second = reconcile(store, decisions=decisions, dry_run=False)

    assert first.counters["synchronized"] == 3
    assert second.counters["synchronized"] == 0
    assert second.counters["already_synchronized"] == 3
    # No duplicate events were created by the second pass.
    for resolution_id in ("RES-resolved", "RES-accepted", "RES-rejected"):
        assert len(store.events_for_aggregate(resolution_id)) == 1


def test_partial_prior_coverage_is_reported_correctly(store):
    decisions = _mixed_decisions()
    already_synced = [d for d in decisions if d.decision_id == "DEC-resolved"]
    reconcile(store, decisions=already_synced, dry_run=False)

    report = reconcile(store, decisions=decisions, dry_run=False)
    assert report.counters["already_synchronized"] == 1
    assert report.counters["synchronized"] == 2


def test_dry_run_never_modifies_governance_store_even_on_second_pass(store):
    decisions = _mixed_decisions()
    reconcile(store, decisions=decisions, dry_run=False)
    events_before = list(store.all_events())

    reconcile(store, decisions=decisions, dry_run=True)
    events_after = list(store.all_events())

    assert events_before == events_after


# ---------------------------------------------------------------------
# Read-only over washer data
# ---------------------------------------------------------------------


def test_reconcile_never_mutates_the_decisions_list_passed_in(store):
    decisions = _mixed_decisions()
    snapshot = list(decisions)
    reconcile(store, decisions=decisions, dry_run=False)
    assert decisions == snapshot
