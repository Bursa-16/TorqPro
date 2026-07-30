import pytest
from pydantic import ValidationError

from backend.governance.enums import PublicationStatus, ResolutionStatus, ReviewStatus
from backend.governance.exceptions import InvalidTransitionError, MissingRequiredFieldError
from backend.governance.models import (
    PublicationDecision,
    ResolutionDecision,
    ReviewDecision,
    is_valid_utc_iso8601,
    validate_publication_decision,
    validate_required_fields,
    validate_resolution_decision,
    validate_review_decision,
)

VALID_TS = "2026-07-30T10:00:00Z"


# ---------------------------------------------------------------------
# Shared model contract: extra="forbid", required decision_id/idempotency_key
# ---------------------------------------------------------------------


def test_review_decision_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ReviewDecision(
            decision_id="d1",
            idempotency_key="k1",
            previous_status=ReviewStatus.DRAFT,
            new_status=ReviewStatus.UNDER_REVIEW,
            created_at=VALID_TS,
            washer_geometry_override="not a governance field",
        )


def test_review_decision_requires_decision_id_and_idempotency_key():
    with pytest.raises(ValidationError):
        ReviewDecision(
            previous_status=ReviewStatus.DRAFT,
            new_status=ReviewStatus.UNDER_REVIEW,
            created_at=VALID_TS,
        )


def test_publication_decision_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        PublicationDecision(
            decision_id="d1",
            idempotency_key="k1",
            previous_status=PublicationStatus.DRAFT,
            new_status=PublicationStatus.ACTIVE,
            created_at=VALID_TS,
            extra_field="not allowed",
        )


def test_resolution_decision_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ResolutionDecision(
            decision_id="d1",
            idempotency_key="k1",
            previous_status=ResolutionStatus.OPEN,
            new_status=ResolutionStatus.RESOLVED,
            created_at=VALID_TS,
            resolved_standard="not allowed here",
        )


# ---------------------------------------------------------------------
# Timestamp format validation
# ---------------------------------------------------------------------


def test_is_valid_utc_iso8601():
    assert is_valid_utc_iso8601("2026-07-30T10:00:00Z")
    assert is_valid_utc_iso8601("2026-07-30T10:00:00.123456Z")
    assert not is_valid_utc_iso8601("2026-07-30 10:00:00")
    assert not is_valid_utc_iso8601("2026-07-30T10:00:00+03:00")
    assert not is_valid_utc_iso8601("not-a-timestamp")


def test_review_decision_rejects_malformed_timestamp():
    with pytest.raises(ValidationError):
        ReviewDecision(
            decision_id="d1",
            idempotency_key="k1",
            previous_status=ReviewStatus.DRAFT,
            new_status=ReviewStatus.UNDER_REVIEW,
            created_at="not-a-timestamp",
        )


def test_review_decision_none_timestamps_are_allowed():
    # submitted_at is Optional; a decision that hasn't reached that
    # transition yet may legitimately leave it unset.
    ReviewDecision(
        decision_id="d1",
        idempotency_key="k1",
        previous_status=ReviewStatus.DRAFT,
        new_status=ReviewStatus.UNDER_REVIEW,
        created_at=VALID_TS,
    )


# ---------------------------------------------------------------------
# validate_required_fields (generic mechanics)
# ---------------------------------------------------------------------


def test_validate_required_fields_passes_when_all_present():
    validate_required_fields(
        frozenset({"a", "b"}), {"a": "x", "b": "y"}, lifecycle_name="review"
    )


def test_validate_required_fields_raises_on_missing():
    with pytest.raises(MissingRequiredFieldError) as excinfo:
        validate_required_fields(
            frozenset({"a", "b"}), {"a": "x"}, lifecycle_name="review"
        )
    assert excinfo.value.missing_fields == frozenset({"b"})


def test_validate_required_fields_treats_blank_string_as_missing():
    with pytest.raises(MissingRequiredFieldError):
        validate_required_fields(
            frozenset({"a"}), {"a": "   "}, lifecycle_name="review"
        )


# ---------------------------------------------------------------------
# Lifecycle A: review decision validation (ADR-0014 required-field table)
# ---------------------------------------------------------------------


def test_review_decision_submit_requires_submitted_by_and_at():
    decision = ReviewDecision(
        decision_id="d1",
        idempotency_key="k1",
        previous_status=ReviewStatus.DRAFT,
        new_status=ReviewStatus.UNDER_REVIEW,
        created_at=VALID_TS,
    )
    with pytest.raises(MissingRequiredFieldError) as excinfo:
        validate_review_decision(decision)
    assert excinfo.value.missing_fields == frozenset({"submitted_by", "submitted_at"})


def test_review_decision_submit_valid():
    decision = ReviewDecision(
        decision_id="d1",
        idempotency_key="k1",
        previous_status=ReviewStatus.DRAFT,
        new_status=ReviewStatus.UNDER_REVIEW,
        submitted_by="ilhan",
        submitted_at=VALID_TS,
        created_at=VALID_TS,
    )
    validate_review_decision(decision)  # must not raise


def test_review_decision_approve_requires_approved_by_and_at():
    decision = ReviewDecision(
        decision_id="d2",
        idempotency_key="k2",
        previous_status=ReviewStatus.UNDER_REVIEW,
        new_status=ReviewStatus.APPROVED,
        created_at=VALID_TS,
    )
    with pytest.raises(MissingRequiredFieldError) as excinfo:
        validate_review_decision(decision)
    assert excinfo.value.missing_fields == frozenset({"approved_by", "approved_at"})


def test_review_decision_reject_requires_rejected_by_and_at():
    decision = ReviewDecision(
        decision_id="d3",
        idempotency_key="k3",
        previous_status=ReviewStatus.UNDER_REVIEW,
        new_status=ReviewStatus.REJECTED,
        created_at=VALID_TS,
    )
    with pytest.raises(MissingRequiredFieldError) as excinfo:
        validate_review_decision(decision)
    assert excinfo.value.missing_fields == frozenset({"rejected_by", "rejected_at"})


def test_review_decision_illegal_transition_rejected_before_field_check():
    # draft -> approved is illegal even with every field populated;
    # the transition check must fire first.
    decision = ReviewDecision(
        decision_id="d4",
        idempotency_key="k4",
        previous_status=ReviewStatus.DRAFT,
        new_status=ReviewStatus.APPROVED,
        approved_by="ilhan",
        approved_at=VALID_TS,
        created_at=VALID_TS,
    )
    with pytest.raises(InvalidTransitionError):
        validate_review_decision(decision)


# ---------------------------------------------------------------------
# Lifecycle B: publication decision validation
# ---------------------------------------------------------------------


def test_publication_decision_activate_requires_submitted_by_and_created_at():
    decision = PublicationDecision(
        decision_id="d5",
        idempotency_key="k5",
        previous_status=PublicationStatus.DRAFT,
        new_status=PublicationStatus.ACTIVE,
        created_at=VALID_TS,
    )
    with pytest.raises(MissingRequiredFieldError) as excinfo:
        validate_publication_decision(decision)
    assert excinfo.value.missing_fields == frozenset({"submitted_by"})


def test_publication_decision_activate_valid():
    decision = PublicationDecision(
        decision_id="d5",
        idempotency_key="k5",
        previous_status=PublicationStatus.DRAFT,
        new_status=PublicationStatus.ACTIVE,
        submitted_by="ilhan",
        created_at=VALID_TS,
    )
    validate_publication_decision(decision)  # must not raise


def test_publication_decision_supersede_requires_superseded_by_id():
    decision = PublicationDecision(
        decision_id="d6",
        idempotency_key="k6",
        previous_status=PublicationStatus.ACTIVE,
        new_status=PublicationStatus.SUPERSEDED,
        created_at=VALID_TS,
    )
    with pytest.raises(MissingRequiredFieldError) as excinfo:
        validate_publication_decision(decision)
    assert excinfo.value.missing_fields == frozenset({"superseded_by_id"})


def test_publication_decision_supersede_valid():
    decision = PublicationDecision(
        decision_id="d6",
        idempotency_key="k6",
        previous_status=PublicationStatus.ACTIVE,
        new_status=PublicationStatus.SUPERSEDED,
        superseded_by_id="rev-2",
        created_at=VALID_TS,
    )
    validate_publication_decision(decision)  # must not raise


def test_publication_decision_no_reopening_superseded():
    decision = PublicationDecision(
        decision_id="d7",
        idempotency_key="k7",
        previous_status=PublicationStatus.SUPERSEDED,
        new_status=PublicationStatus.ACTIVE,
        submitted_by="ilhan",
        created_at=VALID_TS,
    )
    with pytest.raises(InvalidTransitionError):
        validate_publication_decision(decision)


# ---------------------------------------------------------------------
# Lifecycle C: resolution decision validation
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "new_status", [ResolutionStatus.RESOLVED, ResolutionStatus.REJECTED, ResolutionStatus.WAIVED]
)
def test_resolution_decision_requires_reviewed_by_and_at(new_status):
    decision = ResolutionDecision(
        decision_id="d8",
        idempotency_key="k8",
        previous_status=ResolutionStatus.OPEN,
        new_status=new_status,
        created_at=VALID_TS,
    )
    with pytest.raises(MissingRequiredFieldError) as excinfo:
        validate_resolution_decision(decision)
    assert excinfo.value.missing_fields == frozenset({"reviewed_by", "reviewed_at"})


def test_resolution_decision_waived_valid():
    decision = ResolutionDecision(
        decision_id="d9",
        idempotency_key="k9",
        previous_status=ResolutionStatus.OPEN,
        new_status=ResolutionStatus.WAIVED,
        reviewed_by="ilhan",
        reviewed_at=VALID_TS,
        created_at=VALID_TS,
    )
    validate_resolution_decision(decision)  # must not raise


def test_resolution_decision_no_reopening_terminal_status():
    decision = ResolutionDecision(
        decision_id="d10",
        idempotency_key="k10",
        previous_status=ResolutionStatus.RESOLVED,
        new_status=ResolutionStatus.OPEN,
        reviewed_by="ilhan",
        reviewed_at=VALID_TS,
        created_at=VALID_TS,
    )
    with pytest.raises(InvalidTransitionError):
        validate_resolution_decision(decision)
