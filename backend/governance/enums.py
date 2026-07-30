"""TorqPro Engineering Governance - Faz 2.8.11 Stage 2 canonical
lifecycle enums and transition tables.

This module is the first concrete artifact of
``docs/adr/ADR-0014-engineering-governance-architecture.md``'s
canonical model: three independent lifecycle groups, each with its
own status enum and its own closed transition table, deliberately
never merged into a single overloaded status field (ADR-0014,
"Canonical vocabulary").

  - :class:`ReviewStatus` -- lifecycle A (review): whether an
    artifact's content has been checked and judged correct.
  - :class:`PublicationStatus` -- lifecycle B (publication/revision):
    which numbered revision of a versioned artifact is currently in
    effect.
  - :class:`ResolutionStatus` -- lifecycle C (resolution): whether a
    specific flagged issue about an artifact has been closed.

Design constraints (Faz 2.8.11 Stage 2 scope, enforced structurally):

  - This module is additive only. Nothing here is imported by
    ``backend/production_validation``, ``backend/joints``,
    ``backend/library/washer_resolution*``, or ``backend/app.py`` --
    those mechanisms keep their own existing status vocabularies and
    transition tables completely unchanged (ADR-0014, "Compatibility
    strategy"). This module does not read or write to any of their
    tables or JSON ledgers.
  - Every transition table is explicit and closed, fail-closed
    (mirrors ``backend.library.washer_resolution_decisions.
    ALLOWED_TRANSITIONS``, generalized to three lifecycle groups): a
    transition not listed here is illegal. Terminal statuses
    (``approved``/``rejected``, ``superseded``/``archived``,
    ``resolved``/``rejected``/``waived``) have no outgoing transition
    in this base model -- reopening a terminal state is out of scope
    (ADR-0014, "Canonical transition principles" #3), matching the
    precedent already set for washer resolution decisions
    (ADR-0013 Sec. 3).
  - An import-time exhaustiveness assertion cross-checks that every
    status enum member is accounted for by its transition table (as a
    key) or its terminal set, so a future new status value cannot
    silently fall through unnoticed -- the same safeguard
    ``backend.library.washer_resolution_decisions`` uses for
    ``WasherResolutionStatus``.
  - No persistence, no service layer, no API. This module defines
    vocabulary and legal-transition rules only; Stage 3 (append-only
    governance event store and service layer) is where a decision is
    actually recorded and persisted.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class ReviewStatus(str, Enum):
    """Lifecycle A: review. Canonical vocabulary from ADR-0014's
    "Canonical vocabulary" section, group A."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublicationStatus(str, Enum):
    """Lifecycle B: publication/revision. Canonical vocabulary from
    ADR-0014's "Canonical vocabulary" section, group B (reuses joint-
    revision-lifecycle spelling verbatim, per ADR-0014's rationale)."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ResolutionStatus(str, Enum):
    """Lifecycle C: resolution. Canonical vocabulary from ADR-0014's
    "Canonical vocabulary" section, group C (``waived`` is the
    canonical rename of the washer-resolution-workflow's
    ``accepted_as_is`` -- see ADR-0014 for the rationale; this module
    does not alter ``WasherResolutionStatus`` itself)."""

    OPEN = "open"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    WAIVED = "waived"


class LifecycleGroup(str, Enum):
    """Which of the three canonical lifecycle groups a governance
    event belongs to (Faz 2.8.11 Stage 3,
    ``backend.governance.events.GovernanceEvent.lifecycle_group``).
    Deliberately a separate, small "which group is this" tag -- it is
    not itself a status value and is never compared against
    :class:`ReviewStatus`/:class:`PublicationStatus`/
    :class:`ResolutionStatus` members, so the three status
    vocabularies stay independent per ADR-0014."""

    REVIEW = "review"
    PUBLICATION = "publication"
    RESOLUTION = "resolution"


#: Explicit, closed transition table for lifecycle A. Any
#: ``(previous_status, new_status)`` pair not present here is
#: illegal. Statuses absent as a key (``approved``, ``rejected``) are
#: terminal -- looked up as an empty frozenset via ``.get(status,
#: frozenset())``, not a KeyError.
REVIEW_TRANSITIONS: Dict[ReviewStatus, FrozenSet[ReviewStatus]] = {
    ReviewStatus.DRAFT: frozenset({ReviewStatus.UNDER_REVIEW}),
    ReviewStatus.UNDER_REVIEW: frozenset(
        {ReviewStatus.APPROVED, ReviewStatus.REJECTED}
    ),
}

#: Terminal statuses for lifecycle A -- no outgoing transition in
#: this base model (ADR-0014, "Canonical transition principles" #3).
REVIEW_TERMINAL_STATUSES: FrozenSet[ReviewStatus] = frozenset(
    {ReviewStatus.APPROVED, ReviewStatus.REJECTED}
)

#: Explicit, closed transition table for lifecycle B.
PUBLICATION_TRANSITIONS: Dict[PublicationStatus, FrozenSet[PublicationStatus]] = {
    PublicationStatus.DRAFT: frozenset({PublicationStatus.ACTIVE}),
    PublicationStatus.ACTIVE: frozenset(
        {PublicationStatus.SUPERSEDED, PublicationStatus.ARCHIVED}
    ),
}

#: Terminal statuses for lifecycle B.
PUBLICATION_TERMINAL_STATUSES: FrozenSet[PublicationStatus] = frozenset(
    {PublicationStatus.SUPERSEDED, PublicationStatus.ARCHIVED}
)

#: Explicit, closed transition table for lifecycle C.
RESOLUTION_TRANSITIONS: Dict[ResolutionStatus, FrozenSet[ResolutionStatus]] = {
    ResolutionStatus.OPEN: frozenset(
        {ResolutionStatus.RESOLVED, ResolutionStatus.REJECTED, ResolutionStatus.WAIVED}
    ),
}

#: Terminal statuses for lifecycle C.
RESOLUTION_TERMINAL_STATUSES: FrozenSet[ResolutionStatus] = frozenset(
    {ResolutionStatus.RESOLVED, ResolutionStatus.REJECTED, ResolutionStatus.WAIVED}
)


def _assert_transition_table_is_exhaustive(
    status_enum, transitions: Dict, terminal_statuses: FrozenSet, *, lifecycle_name: str
) -> None:
    """Import-time safeguard: every member of ``status_enum`` must be
    accounted for by ``transitions`` (as a key with at least a
    defined, possibly-empty, outgoing set) or by
    ``terminal_statuses``. Raises ``AssertionError`` immediately at
    import time if a status is silently unaccounted for -- mirrors
    ``backend.library.washer_resolution_decisions``' equivalent
    safeguard for ``WasherResolutionStatus``.
    """
    unaccounted = [
        status
        for status in status_enum
        if status not in transitions and status not in terminal_statuses
    ]
    assert not unaccounted, (
        f"{lifecycle_name} lifecycle: status(es) "
        f"{[s.value for s in unaccounted]} have no transition table entry "
        "and are not marked terminal -- every status must be one or the "
        "other."
    )


_assert_transition_table_is_exhaustive(
    ReviewStatus, REVIEW_TRANSITIONS, REVIEW_TERMINAL_STATUSES, lifecycle_name="review"
)
_assert_transition_table_is_exhaustive(
    PublicationStatus,
    PUBLICATION_TRANSITIONS,
    PUBLICATION_TERMINAL_STATUSES,
    lifecycle_name="publication",
)
_assert_transition_table_is_exhaustive(
    ResolutionStatus,
    RESOLUTION_TRANSITIONS,
    RESOLUTION_TERMINAL_STATUSES,
    lifecycle_name="resolution",
)


__all__ = [
    "ReviewStatus",
    "PublicationStatus",
    "ResolutionStatus",
    "LifecycleGroup",
    "REVIEW_TRANSITIONS",
    "REVIEW_TERMINAL_STATUSES",
    "PUBLICATION_TRANSITIONS",
    "PUBLICATION_TERMINAL_STATUSES",
    "RESOLUTION_TRANSITIONS",
    "RESOLUTION_TERMINAL_STATUSES",
]
