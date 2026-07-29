"""TorqPro Engineering Library - Faz 2.8.9 washer resolution decision
workflow (domain model, state machine and validation layer).

This module defines *how a resolution decision may legally be
recorded* against a ``backend.library.washer_resolution`` ledger
entry. It does not, by itself, decide anything: no function here
invents a standard designation, a dimensional value, or a
correctness judgement. Every decision this module accepts must
already carry a human-provided ``resolution_note`` and
``evidence_reference`` -- this module only enforces that the
*transition* being requested is structurally legal, and that the
*fields* required to audit that transition later are present.

Design constraints (Faz 2.8.9 task brief, enforced structurally):

  - Nothing in this module writes to ``washer_resolution_ledger.json``
    (the Faz 2.8.5 source ledger) or to ``washer_library.json``. It
    only defines the record shape and transition rules for a
    *separate*, additive ledger
    (``backend/library/data/washer_resolution_decisions.json``,
    persistence added in Stage 2).
  - ``WasherResolutionDecision`` uses ``extra="forbid"``, mirroring
    ``WasherResolutionRecord`` (Faz 2.8.5): a decision record is a
    closed set of audit-trail fields and cannot smuggle in a washer
    geometry/material override.
  - Terminal statuses (``RESOLVED``, ``ACCEPTED_AS_IS``, ``REJECTED``)
    have no outgoing transitions in this phase -- reopening a
    terminal record is out of scope (task brief rule 9) and is
    represented here as an empty transition set, not a special case
    the caller has to remember.
  - Records whose *current* ledger status is
    ``BLOCKED_AUTHORITATIVE_SOURCE`` have no outgoing transitions
    either -- a normal decision can never be recorded against them in
    this phase (task brief rule 10); the API layer (Stage 3) is
    expected to surface :class:`BlockedRecordDecisionError` as a 409.
  - This module never calls ``datetime.now()`` or any other
    wall-clock source. ``decided_at`` is supplied by the caller (the
    API layer generates it, per task brief rule 7) and is only
    format-validated here.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from .models import ConfidenceLevel
from .washer_resolution import TERMINAL_STATUSES, WasherResolutionStatus

__all__ = [
    "WasherResolutionDecisionError",
    "InvalidTransitionError",
    "BlockedRecordDecisionError",
    "MissingEvidenceError",
    "ALLOWED_TRANSITIONS",
    "WasherResolutionDecision",
    "is_transition_allowed",
    "validate_transition",
    "is_blocked_source_status",
    "validate_decision_fields",
    "UTC_ISO8601_PATTERN",
    "is_valid_utc_iso8601",
]


# ---------------------------------------------------------------------
# Domain errors
# ---------------------------------------------------------------------


class WasherResolutionDecisionError(Exception):
    """Base class for every domain error this module raises. The API
    layer (Stage 3) maps these to specific HTTP error responses; this
    module itself never touches HTTP concerns."""


class InvalidTransitionError(WasherResolutionDecisionError):
    """Raised when the requested ``previous_status -> new_status``
    transition is not in :data:`ALLOWED_TRANSITIONS`. Fail-closed: any
    transition not explicitly listed is rejected, including transitions
    involving statuses this module does not yet know about."""

    def __init__(self, previous_status: WasherResolutionStatus, new_status: WasherResolutionStatus):
        self.previous_status = previous_status
        self.new_status = new_status
        super().__init__(
            f"Transition '{previous_status.value}' -> '{new_status.value}' is not permitted."
        )


class BlockedRecordDecisionError(WasherResolutionDecisionError):
    """Raised when a decision is attempted against a ledger record
    whose current status is ``BLOCKED_AUTHORITATIVE_SOURCE``. This
    phase does not permit any transition out of that status through
    the normal decision workflow (task brief rule 10) -- such records
    may only be viewed."""

    def __init__(self, resolution_id: str):
        self.resolution_id = resolution_id
        super().__init__(
            f"Resolution '{resolution_id}' is blocked_authoritative_source; "
            "it cannot be decided through this workflow in this phase."
        )


class MissingEvidenceError(WasherResolutionDecisionError):
    """Raised when a decision is missing a non-empty
    ``resolution_note`` and/or ``evidence_reference``. No decision may
    be recorded without both, regardless of the requested status."""

    def __init__(self, missing_fields: FrozenSet[str]):
        self.missing_fields = missing_fields
        super().__init__(
            "Decision is missing required field(s): " + ", ".join(sorted(missing_fields))
        )


# ---------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------

#: Explicit, closed transition table. Any ``(previous_status,
#: new_status)`` pair not present here is illegal. Statuses absent as
#: a *key* (currently ``BLOCKED_AUTHORITATIVE_SOURCE`` and every
#: member of ``TERMINAL_STATUSES``) have no legal outgoing transition
#: in this phase -- looked up as an empty frozenset, not a KeyError,
#: so callers get a normal :class:`InvalidTransitionError` rather than
#: an unhandled exception.
ALLOWED_TRANSITIONS: Dict[WasherResolutionStatus, FrozenSet[WasherResolutionStatus]] = {
    WasherResolutionStatus.OPEN: frozenset(
        {
            WasherResolutionStatus.UNDER_REVIEW,
            WasherResolutionStatus.RESOLVED,
            WasherResolutionStatus.ACCEPTED_AS_IS,
            WasherResolutionStatus.REJECTED,
        }
    ),
    WasherResolutionStatus.UNDER_REVIEW: frozenset(
        {
            WasherResolutionStatus.OPEN,
            WasherResolutionStatus.RESOLVED,
            WasherResolutionStatus.ACCEPTED_AS_IS,
            WasherResolutionStatus.REJECTED,
        }
    ),
    # BLOCKED_AUTHORITATIVE_SOURCE: deliberately absent (see
    # BlockedRecordDecisionError docstring). Callers must check
    # is_blocked_source_status() first and raise that specific error
    # instead of a generic InvalidTransitionError, so the API layer
    # can return 409 rather than a generic 4xx.
    #
    # RESOLVED / ACCEPTED_AS_IS / REJECTED: deliberately absent (see
    # TERMINAL_STATUSES docstring in washer_resolution.py) -- reopening
    # is out of scope for this phase.
}


def is_blocked_source_status(status: WasherResolutionStatus) -> bool:
    """``True`` if this is the current ledger status that must be
    rejected with :class:`BlockedRecordDecisionError` rather than run
    through the normal transition table."""
    return status == WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE


def is_transition_allowed(
    previous_status: WasherResolutionStatus, new_status: WasherResolutionStatus
) -> bool:
    """Pure predicate: does :data:`ALLOWED_TRANSITIONS` permit this
    exact transition? Does not raise; used by both
    :func:`validate_transition` and any read-only "can this be
    decided" UI check."""
    return new_status in ALLOWED_TRANSITIONS.get(previous_status, frozenset())


def validate_transition(
    previous_status: WasherResolutionStatus,
    new_status: WasherResolutionStatus,
    resolution_id: str,
) -> None:
    """Raise the appropriate domain error if this transition is not
    legal; return ``None`` (no exception) if it is.

    ``resolution_id`` is required so a blocked-source rejection can
    name the specific ledger entry in its error (and so the API layer
    has it ready for the 409 response body without re-deriving it).

    Checks :func:`is_blocked_source_status` first so a blocked-source
    record always raises :class:`BlockedRecordDecisionError`, never
    the more generic :class:`InvalidTransitionError`, even though both
    would otherwise apply (blocked has no entries in
    ``ALLOWED_TRANSITIONS`` either).
    """
    if is_blocked_source_status(previous_status):
        raise BlockedRecordDecisionError(resolution_id=resolution_id)
    if not is_transition_allowed(previous_status, new_status):
        raise InvalidTransitionError(previous_status, new_status)


def validate_decision_fields(
    resolution_note: str,
    evidence_reference: str,
    resolved_by: Optional[str] = None,
) -> None:
    """Raise :class:`MissingEvidenceError` if any required field is
    empty or whitespace-only. ``resolution_note`` and
    ``evidence_reference`` are always required. ``resolved_by`` is
    only checked when the caller passes it explicitly (not ``None``)
    -- this keeps the two-argument call form used by Stage 1's tests
    working unchanged, while the Stage 3 service layer (which always
    has a ``resolved_by`` value from the request) gets it validated
    too."""
    missing = set()
    if not resolution_note or not resolution_note.strip():
        missing.add("resolution_note")
    if not evidence_reference or not evidence_reference.strip():
        missing.add("evidence_reference")
    if resolved_by is not None and not resolved_by.strip():
        missing.add("resolved_by")
    if missing:
        raise MissingEvidenceError(frozenset(missing))


# ---------------------------------------------------------------------
# decided_at format validation (UTC ISO-8601, API-generated only)
# ---------------------------------------------------------------------

#: Strict UTC ISO-8601: ``YYYY-MM-DDTHH:MM:SS(.ffffff)?Z``. Only the
#: ``Z`` (Zulu/UTC) offset form is accepted -- task brief rule 7
#: requires the API to generate this value itself in UTC, so no other
#: timezone offset should ever legitimately appear here.
UTC_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"
)


def is_valid_utc_iso8601(value: str) -> bool:
    """``True`` if ``value`` matches :data:`UTC_ISO8601_PATTERN`."""
    return bool(UTC_ISO8601_PATTERN.match(value))


# ---------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------


class WasherResolutionDecision(BaseModel):
    """One immutable, append-only audit-trail entry: a single human
    decision recorded against a single
    ``backend.library.washer_resolution.WasherResolutionRecord``.

    ``extra="forbid"`` is deliberate (see module docstring): a
    decision record is a closed set of audit fields, not an
    open-ended bag that could carry a washer geometry override.

    ``integrity_checksum`` is validated here only for non-emptiness
    and a plausible hex-digest shape; the deterministic computation
    of its value is Stage 2's responsibility (persistence layer), so
    this model does not itself compute or verify the digest content.
    """

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    resolution_id: str
    previous_status: WasherResolutionStatus
    new_status: WasherResolutionStatus
    resolution_note: str
    evidence_reference: str
    resolved_by: str
    decided_at: str
    confidence_level: Optional[ConfidenceLevel] = None
    integrity_checksum: str
    #: Caller-supplied idempotency key (Stage 2/3: the API layer is
    #: expected to require this on every decision request). ``None``
    #: is still accepted at the model level so Stage 1's existing
    #: tests, written before idempotency was in scope, keep working
    #: unchanged -- the *requirement* that it be present is enforced
    #: by the Stage 3 API layer, not by this schema.
    idempotency_key: Optional[str] = None

    @field_validator("resolution_note")
    @classmethod
    def _note_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("resolution_note must not be blank")
        return value

    @field_validator("evidence_reference")
    @classmethod
    def _evidence_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("evidence_reference must not be blank")
        return value

    @field_validator("decided_at")
    @classmethod
    def _decided_at_is_utc_iso8601(cls, value: str) -> str:
        if not is_valid_utc_iso8601(value):
            raise ValueError(
                "decided_at must be UTC ISO-8601 with a 'Z' suffix, "
                f"got: {value!r}"
            )
        return value

    @field_validator("integrity_checksum")
    @classmethod
    def _checksum_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("integrity_checksum must not be blank")
        return value

    def to_dict(self) -> Dict[str, object]:
        """JSON-safe projection (enums -> their ``.value``)."""
        return self.model_dump(mode="json")


# Sanity: every status in ACTIVE_STATUSES / TERMINAL_STATUSES (imported
# from the Faz 2.8.5 module) is accounted for by either
# ALLOWED_TRANSITIONS (as a source with real targets) or by the
# deliberate-absence comment above. This is asserted at import time so
# a future addition of a new WasherResolutionStatus member cannot
# silently fall through the state machine unnoticed.
_ACCOUNTED_STATUSES = set(ALLOWED_TRANSITIONS.keys()) | TERMINAL_STATUSES | {
    WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE
}
assert _ACCOUNTED_STATUSES == set(WasherResolutionStatus), (
    "WasherResolutionStatus has member(s) not accounted for in the "
    "Faz 2.8.9 state machine: "
    f"{set(WasherResolutionStatus) - _ACCOUNTED_STATUSES}"
)
