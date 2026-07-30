from backend.governance.enums import (
    PUBLICATION_TERMINAL_STATUSES,
    PUBLICATION_TRANSITIONS,
    PublicationStatus,
    RESOLUTION_TERMINAL_STATUSES,
    RESOLUTION_TRANSITIONS,
    REVIEW_TERMINAL_STATUSES,
    REVIEW_TRANSITIONS,
    ResolutionStatus,
    ReviewStatus,
)


def test_review_status_vocabulary_matches_adr_0014():
    assert {s.value for s in ReviewStatus} == {
        "draft",
        "under_review",
        "approved",
        "rejected",
    }


def test_publication_status_vocabulary_matches_adr_0014():
    assert {s.value for s in PublicationStatus} == {
        "draft",
        "active",
        "superseded",
        "archived",
    }


def test_resolution_status_vocabulary_matches_adr_0014():
    assert {s.value for s in ResolutionStatus} == {
        "open",
        "resolved",
        "rejected",
        "waived",
    }


def test_review_transitions_are_closed_and_fail_closed():
    assert REVIEW_TRANSITIONS[ReviewStatus.DRAFT] == frozenset({ReviewStatus.UNDER_REVIEW})
    assert REVIEW_TRANSITIONS[ReviewStatus.UNDER_REVIEW] == frozenset(
        {ReviewStatus.APPROVED, ReviewStatus.REJECTED}
    )
    # Terminal statuses have no key at all -- an unlisted transition
    # (e.g. draft -> approved, skipping review) must never appear.
    assert ReviewStatus.APPROVED not in REVIEW_TRANSITIONS
    assert ReviewStatus.REJECTED not in REVIEW_TRANSITIONS


def test_review_terminal_statuses():
    assert REVIEW_TERMINAL_STATUSES == frozenset(
        {ReviewStatus.APPROVED, ReviewStatus.REJECTED}
    )


def test_publication_transitions_are_closed():
    assert PUBLICATION_TRANSITIONS[PublicationStatus.DRAFT] == frozenset(
        {PublicationStatus.ACTIVE}
    )
    assert PUBLICATION_TRANSITIONS[PublicationStatus.ACTIVE] == frozenset(
        {PublicationStatus.SUPERSEDED, PublicationStatus.ARCHIVED}
    )
    assert PublicationStatus.SUPERSEDED not in PUBLICATION_TRANSITIONS
    assert PublicationStatus.ARCHIVED not in PUBLICATION_TRANSITIONS


def test_publication_terminal_statuses():
    assert PUBLICATION_TERMINAL_STATUSES == frozenset(
        {PublicationStatus.SUPERSEDED, PublicationStatus.ARCHIVED}
    )


def test_resolution_transitions_are_closed():
    assert RESOLUTION_TRANSITIONS[ResolutionStatus.OPEN] == frozenset(
        {ResolutionStatus.RESOLVED, ResolutionStatus.REJECTED, ResolutionStatus.WAIVED}
    )
    assert ResolutionStatus.RESOLVED not in RESOLUTION_TRANSITIONS
    assert ResolutionStatus.REJECTED not in RESOLUTION_TRANSITIONS
    assert ResolutionStatus.WAIVED not in RESOLUTION_TRANSITIONS


def test_resolution_terminal_statuses():
    assert RESOLUTION_TERMINAL_STATUSES == frozenset(
        {ResolutionStatus.RESOLVED, ResolutionStatus.REJECTED, ResolutionStatus.WAIVED}
    )


def test_every_status_is_either_a_transition_key_or_terminal():
    """Restates the module's own import-time exhaustiveness
    assertion as an explicit, independently-readable test (the
    import-time assertion already ran when this module was imported
    by test collection -- this test documents and re-checks the same
    invariant so a future refactor cannot silently weaken it without
    a visible test failure)."""
    for status in ReviewStatus:
        assert status in REVIEW_TRANSITIONS or status in REVIEW_TERMINAL_STATUSES
    for status in PublicationStatus:
        assert status in PUBLICATION_TRANSITIONS or status in PUBLICATION_TERMINAL_STATUSES
    for status in ResolutionStatus:
        assert status in RESOLUTION_TRANSITIONS or status in RESOLUTION_TERMINAL_STATUSES
