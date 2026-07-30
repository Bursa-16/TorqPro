"""TorqPro Engineering Governance - Faz 2.8.11 Stage 2 typed domain
models.

Implements ADR-0014's "Canonical field names" and "Actor and
timestamp requirements" sections as real, importable Pydantic models
plus required-field validation -- the phase's stated Stage 2
deliverable ("Define Pydantic models for the three canonical
lifecycle groups and canonical field set, as a new, additive
package. No existing mechanism imports or depends on it yet.").

Each lifecycle group gets its own ``*Decision`` model (one immutable
record of a single transition) with only the canonical fields
relevant to that group -- mirroring
``backend.library.washer_resolution_decisions.WasherResolutionDecision``
and deliberately not merging the three groups' fields into one
model, for the same reason their status enums are not merged
(ADR-0014, "Canonical vocabulary").

Design constraints (Faz 2.8.11 Stage 2 scope, enforced structurally):

  - Every model uses ``extra="forbid"`` (mirrors
    ``WasherResolutionDecision``/``WasherResolutionRecord``): a
    decision record is a closed set of governance audit fields, not
    an open-ended bag.
  - ``decision_id`` and ``idempotency_key`` are required (non-
    ``Optional``) on every ``*Decision`` model -- this is how
    ADR-0014's idempotency requirement ("every state-changing
    governance request must carry an idempotency_key") is enforced
    structurally at the model layer, even before any persistence
    layer exists to check for a *reused* key (Stage 3).
  - No field here is computed from a wall-clock source. Every
    timestamp is supplied by the caller and only format-validated
    (UTC ISO-8601, mirroring
    ``backend.library.washer_resolution_decisions.UTC_ISO8601_PATTERN``)
    -- this module is deliberately self-contained and does not import
    that regex from ``backend.library`` (see module-level
    "Compatibility strategy" note in ``backend/governance/__init__.py``),
    so it duplicates the small pattern locally rather than creating a
    dependency from governance back into the library package.
  - This module has no persistence (no JSON ledger, no SQLite table)
    and defines no service function. Stage 3 (append-only governance
    event store and service layer) is where a decision produced by
    these models is actually written down and retrieved.
"""

from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from .enums import (
    PUBLICATION_TRANSITIONS,
    PublicationStatus,
    RESOLUTION_TRANSITIONS,
    REVIEW_TRANSITIONS,
    ResolutionStatus,
    ReviewStatus,
)
from .exceptions import MissingRequiredFieldError
from .transitions import validate_transition

# ---------------------------------------------------------------------
# Timestamp format validation (UTC ISO-8601, caller-supplied only)
# ---------------------------------------------------------------------

#: Strict UTC ISO-8601: ``YYYY-MM-DDTHH:MM:SS(.ffffff)?Z``. Mirrors
#: ``backend.library.washer_resolution_decisions.UTC_ISO8601_PATTERN``
#: exactly (duplicated locally by design -- see module docstring).
UTC_ISO8601_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")


def is_valid_utc_iso8601(value: str) -> bool:
    """``True`` if ``value`` matches :data:`UTC_ISO8601_PATTERN`."""
    return bool(UTC_ISO8601_PATTERN.match(value))


def _validate_optional_timestamp(value: Optional[str]) -> Optional[str]:
    """Shared Pydantic field-validator body: ``None`` passes through
    unchanged; a non-``None`` value must match
    :data:`UTC_ISO8601_PATTERN`."""
    if value is not None and not is_valid_utc_iso8601(value):
        raise ValueError(f"'{value}' is not a valid UTC ISO-8601 timestamp")
    return value


# ---------------------------------------------------------------------
# Lifecycle A: review
# ---------------------------------------------------------------------


class ReviewDecision(BaseModel):
    """One immutable record of a single lifecycle-A transition
    (``draft -> under_review``, ``under_review -> approved``, or
    ``under_review -> rejected``).

    ``extra="forbid"``: a closed set of audit fields, structurally
    incapable of carrying an unrelated engineering-data override.
    """

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    idempotency_key: str
    previous_status: ReviewStatus
    new_status: ReviewStatus
    submitted_by: Optional[str] = None
    submitted_at: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[str] = None
    review_comment: Optional[str] = None
    change_reason: Optional[str] = None
    created_at: str

    _validate_timestamps = field_validator(
        "submitted_at", "approved_at", "rejected_at", "created_at"
    )(_validate_optional_timestamp)


#: ADR-0014 "Actor and timestamp requirements" table, lifecycle A
#: rows. Keyed by ``(previous_status, new_status)``; the mandatory
#: field set for that exact transition.
REVIEW_REQUIRED_FIELDS: Dict[Tuple[ReviewStatus, ReviewStatus], FrozenSet[str]] = {
    (ReviewStatus.DRAFT, ReviewStatus.UNDER_REVIEW): frozenset(
        {"submitted_by", "submitted_at"}
    ),
    (ReviewStatus.UNDER_REVIEW, ReviewStatus.APPROVED): frozenset(
        {"approved_by", "approved_at"}
    ),
    (ReviewStatus.UNDER_REVIEW, ReviewStatus.REJECTED): frozenset(
        {"rejected_by", "rejected_at"}
    ),
}


# ---------------------------------------------------------------------
# Lifecycle B: publication/revision
# ---------------------------------------------------------------------


class PublicationDecision(BaseModel):
    """One immutable record of a single lifecycle-B transition
    (``draft -> active``, ``active -> superseded``, or
    ``active -> archived``)."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    idempotency_key: str
    previous_status: PublicationStatus
    new_status: PublicationStatus
    submitted_by: Optional[str] = None
    revision_no: Optional[int] = None
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    change_reason: Optional[str] = None
    created_at: str

    _validate_timestamps = field_validator("created_at")(_validate_optional_timestamp)


#: ADR-0014 "Actor and timestamp requirements" table, lifecycle B
#: rows. ``active -> archived`` reuses ``submitted_by`` as "whichever
#: actor field applies to the lifecycle in use" (ADR-0014's own
#: phrasing for that row).
PUBLICATION_REQUIRED_FIELDS: Dict[
    Tuple[PublicationStatus, PublicationStatus], FrozenSet[str]
] = {
    (PublicationStatus.DRAFT, PublicationStatus.ACTIVE): frozenset(
        {"submitted_by", "created_at"}
    ),
    (PublicationStatus.ACTIVE, PublicationStatus.SUPERSEDED): frozenset(
        {"superseded_by_id", "created_at"}
    ),
    (PublicationStatus.ACTIVE, PublicationStatus.ARCHIVED): frozenset(
        {"submitted_by", "created_at"}
    ),
}


# ---------------------------------------------------------------------
# Lifecycle C: resolution
# ---------------------------------------------------------------------


class ResolutionDecision(BaseModel):
    """One immutable record of a single lifecycle-C transition
    (``open -> resolved``, ``open -> rejected``, or
    ``open -> waived``)."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    idempotency_key: str
    previous_status: ResolutionStatus
    new_status: ResolutionStatus
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[str] = None
    review_comment: Optional[str] = None
    created_at: str

    _validate_timestamps = field_validator("reviewed_at", "rejected_at", "created_at")(
        _validate_optional_timestamp
    )


#: ADR-0014 "Actor and timestamp requirements" table, lifecycle C
#: row (the table lists one generic "open -> resolved/rejected/
#: waived" row; the same required fields apply to all three outcomes).
RESOLUTION_REQUIRED_FIELDS: Dict[
    Tuple[ResolutionStatus, ResolutionStatus], FrozenSet[str]
] = {
    (ResolutionStatus.OPEN, ResolutionStatus.RESOLVED): frozenset(
        {"reviewed_by", "reviewed_at"}
    ),
    (ResolutionStatus.OPEN, ResolutionStatus.REJECTED): frozenset(
        {"reviewed_by", "reviewed_at"}
    ),
    (ResolutionStatus.OPEN, ResolutionStatus.WAIVED): frozenset(
        {"reviewed_by", "reviewed_at"}
    ),
}


# ---------------------------------------------------------------------
# Required-field validation (shared mechanics, lifecycle-specific
# tables passed in by each wrapper below)
# ---------------------------------------------------------------------


def _is_present(value: Any) -> bool:
    """A field counts as "present" if it is neither ``None`` nor an
    empty/whitespace-only string."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def validate_required_fields(
    required: FrozenSet[str], provided: Mapping[str, Any], *, lifecycle_name: str
) -> None:
    """Raise :class:`MissingRequiredFieldError` if any field named in
    ``required`` is absent or empty in ``provided``; otherwise return
    ``None``. Pure and generic -- each lifecycle wrapper below passes
    its own required-field set and its own decision's field values,
    so this function carries no lifecycle-specific knowledge itself.
    """
    missing = {field for field in required if not _is_present(provided.get(field))}
    if missing:
        raise MissingRequiredFieldError(lifecycle_name, frozenset(missing))


def validate_review_decision(decision: ReviewDecision) -> None:
    """Validate one :class:`ReviewDecision`: the requested transition
    must be legal under :data:`backend.governance.enums.
    REVIEW_TRANSITIONS`, and every field
    :data:`REVIEW_REQUIRED_FIELDS` marks mandatory for that exact
    transition must be present and non-empty. Raises
    :class:`~backend.governance.exceptions.InvalidTransitionError` or
    :class:`~backend.governance.exceptions.MissingRequiredFieldError`
    as appropriate; returns ``None`` if the decision is valid."""
    validate_transition(
        REVIEW_TRANSITIONS,
        decision.previous_status,
        decision.new_status,
        lifecycle_name="review",
    )
    required = REVIEW_REQUIRED_FIELDS.get(
        (decision.previous_status, decision.new_status), frozenset()
    )
    validate_required_fields(required, decision.model_dump(), lifecycle_name="review")


def validate_publication_decision(decision: PublicationDecision) -> None:
    """Validate one :class:`PublicationDecision`. Same contract as
    :func:`validate_review_decision`, for lifecycle B."""
    validate_transition(
        PUBLICATION_TRANSITIONS,
        decision.previous_status,
        decision.new_status,
        lifecycle_name="publication",
    )
    required = PUBLICATION_REQUIRED_FIELDS.get(
        (decision.previous_status, decision.new_status), frozenset()
    )
    validate_required_fields(required, decision.model_dump(), lifecycle_name="publication")


def validate_resolution_decision(decision: ResolutionDecision) -> None:
    """Validate one :class:`ResolutionDecision`. Same contract as
    :func:`validate_review_decision`, for lifecycle C."""
    validate_transition(
        RESOLUTION_TRANSITIONS,
        decision.previous_status,
        decision.new_status,
        lifecycle_name="resolution",
    )
    required = RESOLUTION_REQUIRED_FIELDS.get(
        (decision.previous_status, decision.new_status), frozenset()
    )
    validate_required_fields(required, decision.model_dump(), lifecycle_name="resolution")


__all__ = [
    "UTC_ISO8601_PATTERN",
    "is_valid_utc_iso8601",
    "ReviewDecision",
    "REVIEW_REQUIRED_FIELDS",
    "validate_review_decision",
    "PublicationDecision",
    "PUBLICATION_REQUIRED_FIELDS",
    "validate_publication_decision",
    "ResolutionDecision",
    "RESOLUTION_REQUIRED_FIELDS",
    "validate_resolution_decision",
    "validate_required_fields",
]
