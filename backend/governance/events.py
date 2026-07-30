"""TorqPro Engineering Governance - Faz 2.8.11 Stage 3 typed event
model.

One :class:`GovernanceEvent` is one immutable, append-only record of
a single governance transition (a "decision", in Stage 2's
vocabulary, now given a persistable, lifecycle-group-tagged shape).
The event store (:mod:`backend.governance.store`) never updates or
deletes an event once appended; the *effective* state of an artifact
is always derived by replaying its event history
(:mod:`backend.governance.service`), never stored as a separately
mutated field.

Design constraints (Faz 2.8.11 Stage 3 scope, enforced structurally):

  - ``extra="forbid"``, matching every other model in this package
    and in ``backend.library.washer_resolution*``: a governance event
    is a closed set of audit fields.
  - ``previous_status``/``new_status`` are plain ``str`` here (not
    ``ReviewStatus``/``PublicationStatus``/``ResolutionStatus``)
    because one event model must be able to represent an event from
    any of the three lifecycle groups; the *specific* enum type is
    enforced one layer up, in ``backend.governance.service``, where
    each event is constructed from an already-validated Stage 2
    ``*Decision`` model (whose fields *are* strictly typed to the
    correct enum). This is deliberate: it keeps the persisted event
    shape uniform (so the store does not need a different table/file
    per lifecycle group) while keeping the actual fail-closed status
    validation exactly where Stage 2 already put it.
  - ``lifecycle_group`` (:class:`~backend.governance.enums.
    LifecycleGroup`) tags which of the three independent lifecycle
    groups this event belongs to. The three groups are never merged
    (ADR-0014): a reader must always filter by ``lifecycle_group``
    before interpreting ``previous_status``/``new_status`` against a
    specific status enum.
  - ``occurred_at`` is caller-supplied and format-validated (UTC
    ISO-8601) only -- this model never calls a wall-clock function
    itself, matching ``WasherResolutionDecision.decided_at``'s
    contract.
  - ``revision_no``/``supersedes_id``/``superseded_by_id`` are
    present (beyond the Stage 3 task brief's minimum field list) so
    lifecycle-B (publication) events can carry ADR-0014's revision-
    lineage pointers without a separate event shape.
  - ``metadata`` is an open ``Dict[str, Any]`` bag (the one
    deliberately-unstructured field on this otherwise closed model),
    for lifecycle-specific context that does not warrant its own
    named column -- e.g. a future consumer's request-tracing id. It
    is not interpreted by anything in this package.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import LifecycleGroup
from .models import is_valid_utc_iso8601


class GovernanceEvent(BaseModel):
    """One immutable, append-only governance event."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    aggregate_id: str
    aggregate_type: str
    lifecycle_group: LifecycleGroup
    previous_status: str
    new_status: str
    decision_id: str
    idempotency_key: str
    actor: Optional[str] = None
    occurred_at: str
    review_comment: Optional[str] = None
    change_reason: Optional[str] = None
    revision_no: Optional[int] = None
    supersedes_id: Optional[str] = None
    superseded_by_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def _validate_occurred_at(cls, value: str) -> str:
        if not is_valid_utc_iso8601(value):
            raise ValueError(f"'{value}' is not a valid UTC ISO-8601 timestamp")
        return value


__all__ = ["GovernanceEvent"]
