import inspect

import pytest
from pydantic import ValidationError

import backend.governance.service as service
from backend.governance.enums import LifecycleGroup
from backend.governance.exceptions import (
    GovernanceAggregateNotFoundError,
    GovernanceDuplicateDecisionError,
    GovernanceIdempotencyConflictError,
    InvalidTransitionError,
    MissingRequiredFieldError,
)
from backend.governance.store import FileGovernanceEventStore

VALID_TS = "2026-07-30T10:00:00Z"
LATER_TS = "2026-07-30T11:00:00Z"


@pytest.fixture
def store(tmp_path):
    return FileGovernanceEventStore(tmp_path / "events.json")


# ---------------------------------------------------------------------
# Valid transitions (one per lifecycle group, end to end)
# ---------------------------------------------------------------------


def test_review_lifecycle_full_happy_path(store):
    ev1, created1 = service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert created1 and ev1.new_status == "under_review"

    ev2, created2 = service.approve_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="reviewer",
        occurred_at=LATER_TS,
        review_comment="looks fine",
    )
    assert created2 and ev2.new_status == "approved"
    assert ev2.previous_status == "under_review"


def test_review_lifecycle_reject_path(store):
    service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    ev, created = service.reject_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="reviewer",
        occurred_at=LATER_TS,
        review_comment="needs rework",
    )
    assert created and ev.new_status == "rejected"


def test_publication_lifecycle_activate_and_archive(store):
    ev1, _ = service.activate_publication(
        store,
        aggregate_id="rev-1",
        aggregate_type="joint_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert ev1.new_status == "active"

    ev2, _ = service.archive_publication(
        store,
        aggregate_id="rev-1",
        aggregate_type="joint_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="ilhan",
        occurred_at=LATER_TS,
    )
    assert ev2.new_status == "archived"
    assert ev2.previous_status == "active"


def test_resolution_lifecycle_resolve_reject_waive(store):
    ev1, _ = service.resolve_resolution(
        store,
        aggregate_id="issue-1",
        aggregate_type="washer_style_issue",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert ev1.new_status == "resolved"

    ev2, _ = service.reject_resolution(
        store,
        aggregate_id="issue-2",
        aggregate_type="washer_style_issue",
        decision_id="d2",
        idempotency_key="k2",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert ev2.new_status == "rejected"

    ev3, _ = service.waive_resolution(
        store,
        aggregate_id="issue-3",
        aggregate_type="washer_style_issue",
        decision_id="d3",
        idempotency_key="k3",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert ev3.new_status == "waived"


# ---------------------------------------------------------------------
# Invalid transitions / terminal-state reopening
# ---------------------------------------------------------------------


def test_approve_without_submit_is_invalid_transition(store):
    with pytest.raises(InvalidTransitionError):
        service.approve_review(
            store,
            aggregate_id="agg-1",
            aggregate_type="calc_revision",
            decision_id="d1",
            idempotency_key="k1",
            actor="reviewer",
            occurred_at=VALID_TS,
        )


def test_cannot_reopen_approved_review(store):
    service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    service.approve_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="reviewer",
        occurred_at=LATER_TS,
    )
    with pytest.raises(InvalidTransitionError):
        service.submit_review(
            store,
            aggregate_id="agg-1",
            aggregate_type="calc_revision",
            decision_id="d3",
            idempotency_key="k3",
            actor="ilhan",
            occurred_at=LATER_TS,
        )


def test_cannot_reopen_superseded_publication(store):
    service.activate_publication(
        store,
        aggregate_id="rev-1",
        aggregate_type="joint_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    service.supersede_publication(
        store,
        aggregate_id="rev-1",
        aggregate_type="joint_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="ilhan",
        occurred_at=LATER_TS,
        superseded_by_id="rev-2",
    )
    with pytest.raises(InvalidTransitionError):
        service.activate_publication(
            store,
            aggregate_id="rev-1",
            aggregate_type="joint_revision",
            decision_id="d3",
            idempotency_key="k3",
            actor="ilhan",
            occurred_at=LATER_TS,
        )


def test_supersede_requires_superseded_by_id_field(store):
    service.activate_publication(
        store,
        aggregate_id="rev-1",
        aggregate_type="joint_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    with pytest.raises((MissingRequiredFieldError, TypeError)):
        service.supersede_publication(
            store,
            aggregate_id="rev-1",
            aggregate_type="joint_revision",
            decision_id="d2",
            idempotency_key="k2",
            occurred_at=LATER_TS,
            superseded_by_id="",
        )


# ---------------------------------------------------------------------
# Idempotency behavior
# ---------------------------------------------------------------------


def test_identical_retry_returns_original_event_not_created(store):
    ev1, created1 = service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    ev2, created2 = service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert created1 is True
    assert created2 is False
    assert ev1.event_id == ev2.event_id
    assert len(store.all_events()) == 1


def test_retry_remains_valid_after_state_has_progressed(store):
    """The critical ordering guarantee: submitting a retry of the
    *original* submit request must succeed (returning the original
    event) even after the aggregate has since been approved -- proof
    that idempotency is checked before transition validation."""
    ev1, created1 = service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    service.approve_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="reviewer",
        occurred_at=LATER_TS,
    )
    # Retry the *original* submit request (same idempotency_key and
    # decision_id as the very first call) -- must not raise, even
    # though effective status has moved on to "approved" in the
    # meantime.
    ev1_retry, created_retry = service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert created_retry is False
    assert ev1_retry.event_id == ev1.event_id
    assert len(store.all_events()) == 2  # no third event was appended


def test_same_key_different_request_raises_idempotency_conflict(store):
    service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    with pytest.raises(GovernanceIdempotencyConflictError):
        service.submit_review(
            store,
            aggregate_id="agg-1",
            aggregate_type="calc_revision",
            decision_id="d1",
            idempotency_key="k1",
            actor="SOMEONE_ELSE",  # different actor -> different request
            occurred_at=VALID_TS,
        )


def test_duplicate_decision_id_different_key_raises_conflict(store):
    service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    with pytest.raises(GovernanceDuplicateDecisionError):
        service.submit_review(
            store,
            aggregate_id="agg-2",
            aggregate_type="calc_revision",
            decision_id="d1",  # reused decision_id
            idempotency_key="k-different",
            actor="ilhan",
            occurred_at=VALID_TS,
        )


def test_idempotency_conflict_does_not_append_a_new_event(store):
    service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    with pytest.raises(GovernanceIdempotencyConflictError):
        service.submit_review(
            store,
            aggregate_id="agg-1",
            aggregate_type="calc_revision",
            decision_id="d1",
            idempotency_key="k1",
            actor="DIFFERENT",
            occurred_at=VALID_TS,
        )
    assert len(store.all_events()) == 1


# ---------------------------------------------------------------------
# previous_status is never caller-suppliable
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn",
    [
        service.submit_review,
        service.approve_review,
        service.reject_review,
        service.activate_publication,
        service.supersede_publication,
        service.archive_publication,
        service.resolve_resolution,
        service.reject_resolution,
        service.waive_resolution,
    ],
)
def test_no_transition_function_accepts_previous_status(fn):
    assert "previous_status" not in inspect.signature(fn).parameters


def test_passing_previous_status_kwarg_is_rejected_with_typeerror(store):
    with pytest.raises(TypeError):
        service.submit_review(
            store,
            aggregate_id="agg-1",
            aggregate_type="calc_revision",
            decision_id="d1",
            idempotency_key="k1",
            actor="ilhan",
            occurred_at=VALID_TS,
            previous_status="approved",  # would be a lie if accepted
        )


# ---------------------------------------------------------------------
# Supersession lineage
# ---------------------------------------------------------------------


def test_supersession_lineage_pointers_are_recorded_on_both_sides(store):
    service.activate_publication(
        store,
        aggregate_id="rev-1",
        aggregate_type="joint_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    superseded_event, _ = service.supersede_publication(
        store,
        aggregate_id="rev-1",
        aggregate_type="joint_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="ilhan",
        occurred_at=LATER_TS,
        superseded_by_id="rev-2",
    )
    activate_event, _ = service.activate_publication(
        store,
        aggregate_id="rev-2",
        aggregate_type="joint_revision",
        decision_id="d3",
        idempotency_key="k3",
        actor="ilhan",
        occurred_at=LATER_TS,
        revision_no=2,
        supersedes_id="rev-1",
    )
    assert superseded_event.superseded_by_id == "rev-2"
    assert activate_event.supersedes_id == "rev-1"
    assert activate_event.revision_no == 2
    assert service.effective_status(store, "rev-1", LifecycleGroup.PUBLICATION) == "superseded"
    assert service.effective_status(store, "rev-2", LifecycleGroup.PUBLICATION) == "active"


# ---------------------------------------------------------------------
# Effective status derivation / latest event / event history
# ---------------------------------------------------------------------


def test_effective_status_is_draft_for_unknown_aggregate(store):
    assert service.effective_status(store, "unknown", LifecycleGroup.REVIEW) == "draft"
    assert service.effective_status(store, "unknown", LifecycleGroup.PUBLICATION) == "draft"
    assert service.effective_status(store, "unknown", LifecycleGroup.RESOLUTION) == "open"


def test_effective_status_derived_from_latest_event_only(store):
    service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert service.effective_status(store, "agg-1", LifecycleGroup.REVIEW) == "under_review"
    service.approve_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="reviewer",
        occurred_at=LATER_TS,
    )
    assert service.effective_status(store, "agg-1", LifecycleGroup.REVIEW) == "approved"


def test_latest_event_returns_none_for_unknown_aggregate(store):
    assert service.latest_event(store, "unknown") is None


def test_latest_event_strict_raises_for_unknown_aggregate(store):
    with pytest.raises(GovernanceAggregateNotFoundError):
        service.latest_event(store, "unknown", LifecycleGroup.REVIEW, strict=True)


def test_latest_event_returns_most_recent(store):
    service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    service.approve_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="reviewer",
        occurred_at=LATER_TS,
    )
    latest = service.latest_event(store, "agg-1", LifecycleGroup.REVIEW)
    assert latest.new_status == "approved"


def test_event_history_filters_by_lifecycle_group(store):
    service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    service.resolve_resolution(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d2",
        idempotency_key="k2",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    review_history = service.event_history(store, "agg-1", LifecycleGroup.REVIEW)
    resolution_history = service.event_history(store, "agg-1", LifecycleGroup.RESOLUTION)
    assert len(review_history) == 1
    assert len(resolution_history) == 1
    assert review_history[0].lifecycle_group == LifecycleGroup.REVIEW
    assert resolution_history[0].lifecycle_group == LifecycleGroup.RESOLUTION


# ---------------------------------------------------------------------
# UTC timestamps / no hidden local time
# ---------------------------------------------------------------------


def test_occurred_at_must_be_valid_utc_iso8601(store):
    with pytest.raises(ValidationError):
        service.submit_review(
            store,
            aggregate_id="agg-1",
            aggregate_type="calc_revision",
            decision_id="d1",
            idempotency_key="k1",
            actor="ilhan",
            occurred_at="not-a-timestamp",
        )


def test_service_module_never_calls_datetime_now():
    import inspect as _inspect
    import re as _re

    source = _inspect.getsource(service)
    code_only = _re.sub(r'"""[\s\S]*?"""', "", source)
    assert "datetime.now(" not in code_only
    assert ".now()" not in code_only
    assert "utcnow" not in code_only


# ---------------------------------------------------------------------
# Deterministic / injectable identifiers
# ---------------------------------------------------------------------


def test_event_id_is_injectable_and_deterministic(store):
    event, _ = service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
        event_id="deterministic-event-id-1",
    )
    assert event.event_id == "deterministic-event-id-1"


def test_event_id_is_generated_when_omitted(store):
    event, _ = service.submit_review(
        store,
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    assert event.event_id  # non-empty, some id was generated
