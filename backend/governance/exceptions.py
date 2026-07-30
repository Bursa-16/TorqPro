"""TorqPro Engineering Governance - Faz 2.8.11 Stage 2 domain errors.

Mirrors the error-class pattern already established by
``backend.library.washer_resolution_decisions``
(``WasherResolutionDecisionError`` and its subclasses): a small,
specific set of domain exceptions, independent of any web framework.
A future Stage 3/4 API layer is expected to map these to HTTP error
responses; this module itself never touches HTTP concerns.
"""

from __future__ import annotations

from typing import FrozenSet


class GovernanceError(Exception):
    """Base class for every domain error this package raises."""


class InvalidTransitionError(GovernanceError):
    """Raised when a requested ``previous_status -> new_status``
    transition is not present in the relevant lifecycle's transition
    table. Fail-closed: any transition not explicitly listed is
    rejected, including transitions involving statuses the table does
    not yet know about."""

    def __init__(self, lifecycle_name: str, previous_status, new_status) -> None:
        self.lifecycle_name = lifecycle_name
        self.previous_status = previous_status
        self.new_status = new_status
        previous_value = getattr(previous_status, "value", previous_status)
        new_value = getattr(new_status, "value", new_status)
        super().__init__(
            f"{lifecycle_name} lifecycle: transition '{previous_value}' -> "
            f"'{new_value}' is not permitted."
        )


class MissingRequiredFieldError(GovernanceError):
    """Raised when a decision is missing one or more of the actor/
    timestamp fields ADR-0014's "Actor and timestamp requirements"
    table marks as mandatory for the requested transition."""

    def __init__(self, lifecycle_name: str, missing_fields: FrozenSet[str]) -> None:
        self.lifecycle_name = lifecycle_name
        self.missing_fields = missing_fields
        super().__init__(
            f"{lifecycle_name} lifecycle: decision is missing required "
            "field(s): " + ", ".join(sorted(missing_fields))
        )


class GovernanceStoreError(GovernanceError):
    """Raised when the append-only event store cannot complete a read
    or write operation (e.g. an OS-level I/O failure during the
    atomic-write sequence). The message is deliberately generic --
    see module docstring: no filesystem path, no wrapped exception
    text, and no traceback is included, so this is safe to surface
    to a caller/API response as-is."""

    def __init__(self, message: str = "governance event store operation failed") -> None:
        super().__init__(message)


class GovernanceCorruptionError(GovernanceStoreError):
    """Raised when the persisted event store file exists but its
    content is not valid JSON, does not have the expected shape, or
    contains a record that fails to validate as a
    :class:`~backend.governance.events.GovernanceEvent`. Distinct
    from :class:`GovernanceStoreError` so a caller can tell "the
    store is unreachable" apart from "the store is reachable but its
    content is damaged". Never includes the parser's raw error text
    (which could echo back file content) or a filesystem path."""

    def __init__(self, message: str = "governance event store content is corrupted") -> None:
        super().__init__(message)


class GovernanceIdempotencyConflictError(GovernanceError):
    """Raised when a caller reuses an ``idempotency_key`` with a
    request that is not identical (once normalized) to the original
    request that key was first used for. Mirrors
    ``backend.library.washer_resolution_decisions_store``'s
    idempotency-key handling, generalized to all three lifecycle
    groups. A retry of the *exact* original request must never raise
    this -- see ``backend.governance.service``'s idempotency-first
    ordering."""

    def __init__(self, idempotency_key: str) -> None:
        self.idempotency_key = idempotency_key
        super().__init__(
            f"idempotency_key '{idempotency_key}' was already used for a "
            "different request."
        )


class GovernanceDuplicateDecisionError(GovernanceError):
    """Raised when a caller-supplied ``decision_id`` already exists in
    the event store under a *different* ``idempotency_key`` (i.e. it
    cannot be recognized as a legitimate retry of the original
    request that created it). The store is append-only and a
    ``decision_id`` must be unique across its whole history."""

    def __init__(self, decision_id: str) -> None:
        self.decision_id = decision_id
        super().__init__(f"decision_id '{decision_id}' already exists.")


class GovernanceAggregateNotFoundError(GovernanceError):
    """Raised by a strict read accessor (e.g.
    ``backend.governance.service.latest_event(..., strict=True)``)
    when the requested aggregate has no recorded governance events at
    all. Non-strict accessors return ``None``/an empty list instead
    of raising -- this error is only for callers that need to treat
    "never governed" as an error condition."""

    def __init__(self, aggregate_id: str, lifecycle_group: str) -> None:
        self.aggregate_id = aggregate_id
        self.lifecycle_group = lifecycle_group
        super().__init__(
            f"no governance events found for aggregate '{aggregate_id}' "
            f"in the {lifecycle_group} lifecycle."
        )


__all__ = [
    "GovernanceError",
    "InvalidTransitionError",
    "MissingRequiredFieldError",
    "GovernanceStoreError",
    "GovernanceCorruptionError",
    "GovernanceIdempotencyConflictError",
    "GovernanceDuplicateDecisionError",
    "GovernanceAggregateNotFoundError",
]
