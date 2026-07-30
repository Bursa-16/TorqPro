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


__all__ = [
    "GovernanceError",
    "InvalidTransitionError",
    "MissingRequiredFieldError",
]
