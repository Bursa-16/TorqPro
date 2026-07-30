import pytest

from backend.governance.enums import (
    PUBLICATION_TRANSITIONS,
    PublicationStatus,
    RESOLUTION_TRANSITIONS,
    REVIEW_TRANSITIONS,
    ResolutionStatus,
    ReviewStatus,
)
from backend.governance.exceptions import InvalidTransitionError
from backend.governance.transitions import is_transition_allowed, validate_transition


def test_is_transition_allowed_true_for_legal_move():
    assert is_transition_allowed(
        REVIEW_TRANSITIONS, ReviewStatus.DRAFT, ReviewStatus.UNDER_REVIEW
    )


def test_is_transition_allowed_false_for_illegal_move():
    assert not is_transition_allowed(
        REVIEW_TRANSITIONS, ReviewStatus.DRAFT, ReviewStatus.APPROVED
    )


def test_is_transition_allowed_false_for_terminal_status_key_absent():
    # ReviewStatus.APPROVED has no key in REVIEW_TRANSITIONS at all;
    # this must not raise KeyError.
    assert not is_transition_allowed(
        REVIEW_TRANSITIONS, ReviewStatus.APPROVED, ReviewStatus.REJECTED
    )


def test_validate_transition_raises_for_illegal_move():
    with pytest.raises(InvalidTransitionError) as excinfo:
        validate_transition(
            REVIEW_TRANSITIONS,
            ReviewStatus.DRAFT,
            ReviewStatus.APPROVED,
            lifecycle_name="review",
        )
    assert excinfo.value.lifecycle_name == "review"
    assert excinfo.value.previous_status == ReviewStatus.DRAFT
    assert excinfo.value.new_status == ReviewStatus.APPROVED


def test_validate_transition_no_raise_for_legal_move():
    validate_transition(
        REVIEW_TRANSITIONS,
        ReviewStatus.UNDER_REVIEW,
        ReviewStatus.APPROVED,
        lifecycle_name="review",
    )


def test_validate_transition_works_for_publication_lifecycle():
    validate_transition(
        PUBLICATION_TRANSITIONS,
        PublicationStatus.ACTIVE,
        PublicationStatus.SUPERSEDED,
        lifecycle_name="publication",
    )
    with pytest.raises(InvalidTransitionError):
        validate_transition(
            PUBLICATION_TRANSITIONS,
            PublicationStatus.SUPERSEDED,
            PublicationStatus.ACTIVE,
            lifecycle_name="publication",
        )


def test_validate_transition_works_for_resolution_lifecycle():
    validate_transition(
        RESOLUTION_TRANSITIONS,
        ResolutionStatus.OPEN,
        ResolutionStatus.WAIVED,
        lifecycle_name="resolution",
    )
    with pytest.raises(InvalidTransitionError):
        validate_transition(
            RESOLUTION_TRANSITIONS,
            ResolutionStatus.RESOLVED,
            ResolutionStatus.OPEN,
            lifecycle_name="resolution",
        )


def test_no_reopening_a_terminal_review_status():
    """Restates ADR-0014's 'terminal states have no outgoing
    transition' principle as an explicit regression test."""
    with pytest.raises(InvalidTransitionError):
        validate_transition(
            REVIEW_TRANSITIONS,
            ReviewStatus.APPROVED,
            ReviewStatus.UNDER_REVIEW,
            lifecycle_name="review",
        )
    with pytest.raises(InvalidTransitionError):
        validate_transition(
            REVIEW_TRANSITIONS,
            ReviewStatus.REJECTED,
            ReviewStatus.DRAFT,
            lifecycle_name="review",
        )
