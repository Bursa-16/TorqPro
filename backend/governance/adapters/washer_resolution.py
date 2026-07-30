"""TorqPro Engineering Governance - Faz 2.8.11 Stage 5 compatibility
adapter: washer resolution lifecycle -> canonical governance
projection.

Read-only, additive, deterministic. This module reads from
``backend.library.washer_resolution`` / ``washer_resolution_service`` /
``washer_resolution_decisions_store`` and returns a
:class:`CompatibilityProjection`; it never writes anywhere -- not to
the washer ledgers, not to the governance event store. No governance
event is ever created by importing or calling this module.

Why washer resolution and not the other three mechanisms (Stage 5
scope decision, see ``docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md``
Sec. 5): washer resolution's read surface
(``get_washer_resolution``, ``effective_status``,
``decisions_for_resolution``) is pure and file-backed -- no live
SQLite connection parameter is required, so this adapter can be
called with nothing but a ``resolution_id`` and stays fully
deterministic and independently testable. Production Validation, the
legacy calculation-revision workflow, and the joint revision
lifecycle all require a caller-supplied database connection (``c``)
to read anything; wiring a connection-acquisition dependency into
``backend.governance.adapters`` would mean either importing
connection-management helpers from ``backend.app`` (deepening
coupling beyond "read-only, additive") or duplicating that logic here
-- both are exactly what Stage 5's "no new dependency cycle" /
minimal-coupling requirement rules out for a first, narrowly-scoped
adapter. Those three are intentionally deferred; see the completion
report for the follow-up scope.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from backend.library import washer_resolution as wr
from backend.library.washer_resolution_decisions_store import decisions_for_resolution
from backend.library.washer_resolution_service import effective_status

from ..enums import LifecycleGroup, ResolutionStatus

SOURCE_SYSTEM = "washer_resolution"


class MappingQuality:
    """Closed vocabulary for how confidently a source status maps
    onto the canonical vocabulary. Not a Pydantic-facing enum member
    set directly on :class:`CompatibilityProjection` because the
    projection stores the plain string value (mirrors
    :class:`~backend.governance.events.GovernanceEvent`'s own
    ``previous_status``/``new_status`` design: one shared projection
    shape across every future adapter, not a per-source-system enum
    type)."""

    EXACT = "exact"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"

    ALL = frozenset({EXACT, PARTIAL, UNSUPPORTED})


class AdapterSourceRecordNotFoundError(Exception):
    """Raised when ``source_record_id`` does not exist in the source
    system at all -- fail closed rather than returning a guessed or
    partially-populated projection."""

    def __init__(self, source_system: str, source_record_id: str) -> None:
        self.source_system = source_system
        self.source_record_id = source_record_id
        super().__init__(f"{source_system}: no record '{source_record_id}' found.")


class CompatibilityProjection(BaseModel):
    """Read-only canonical governance view of one existing-mechanism
    record. Never persisted; never used to construct a
    :class:`~backend.governance.events.GovernanceEvent` or write to
    the governance event store -- purely an on-demand, computed
    read-side projection.

    ``lifecycle_group``/``canonical_status`` are ``None`` exactly
    when ``mapping_quality == MappingQuality.UNSUPPORTED`` -- a
    consumer must never treat a missing canonical status as
    equivalent to any real status value (see module docstring,
    "Never guess")."""

    model_config = ConfigDict(extra="forbid")

    source_system: str
    source_record_id: str
    source_status: str
    lifecycle_group: Optional[LifecycleGroup] = None
    canonical_status: Optional[str] = None
    mapping_quality: str
    revision_no: Optional[int] = None
    actor: Optional[str] = None
    occurred_at: Optional[str] = None
    reason: Optional[str] = None
    metadata: Dict[str, Any] = {}


#: Explicit, closed mapping table:
#: WasherResolutionStatus -> (canonical ResolutionStatus or None, MappingQuality).
#: ``blocked_authoritative_source`` is deliberately unsupported --
#: ADR-0014's "Compatibility strategy" already decided this washer-
#: specific escape hatch is not forced into the canonical resolution
#: vocabulary. ``under_review`` is "partial": the canonical resolution
#: lifecycle (open -> resolved/rejected/waived) has no distinct
#: in-review state of its own, so it is projected as still `open`,
#: with the loss of that distinction reflected in `mapping_quality`.
_STATUS_MAP = {
    wr.WasherResolutionStatus.OPEN: (ResolutionStatus.OPEN, MappingQuality.EXACT),
    wr.WasherResolutionStatus.UNDER_REVIEW: (ResolutionStatus.OPEN, MappingQuality.PARTIAL),
    wr.WasherResolutionStatus.RESOLVED: (ResolutionStatus.RESOLVED, MappingQuality.EXACT),
    wr.WasherResolutionStatus.ACCEPTED_AS_IS: (ResolutionStatus.WAIVED, MappingQuality.EXACT),
    wr.WasherResolutionStatus.REJECTED: (ResolutionStatus.REJECTED, MappingQuality.EXACT),
    wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE: (None, MappingQuality.UNSUPPORTED),
}


def project_washer_resolution(resolution_id: str) -> CompatibilityProjection:
    """Read ``resolution_id`` from the existing Faz 2.8.5/2.8.9 washer
    resolution workflow and return its canonical governance
    compatibility projection. Raises
    :class:`AdapterSourceRecordNotFoundError` if the id does not
    exist in the source ledger at all. Read-only: this function never
    writes to any ledger, any table, or the governance event store."""
    source_record = wr.get_washer_resolution(resolution_id)
    if source_record is None:
        raise AdapterSourceRecordNotFoundError(SOURCE_SYSTEM, resolution_id)

    current_status = effective_status(resolution_id)
    canonical_status, quality = _STATUS_MAP[current_status]

    decisions = decisions_for_resolution(resolution_id)
    latest_decision = decisions[-1] if decisions else None

    if latest_decision is not None:
        actor = latest_decision.resolved_by or None
        occurred_at = latest_decision.decided_at or None
        reason = latest_decision.resolution_note or None
    else:
        actor = source_record.resolved_by or None
        occurred_at = source_record.resolved_at or None
        reason = source_record.resolution_note or None

    return CompatibilityProjection(
        source_system=SOURCE_SYSTEM,
        source_record_id=resolution_id,
        source_status=current_status.value,
        lifecycle_group=(LifecycleGroup.RESOLUTION if canonical_status is not None else None),
        canonical_status=(canonical_status.value if canonical_status is not None else None),
        mapping_quality=quality,
        revision_no=None,
        actor=actor,
        occurred_at=occurred_at,
        reason=reason,
        metadata={
            "washer_record_id": source_record.washer_record_id,
            "issue_type": source_record.issue_type.value,
            "decision_count": len(decisions),
        },
    )


__all__ = [
    "SOURCE_SYSTEM",
    "MappingQuality",
    "AdapterSourceRecordNotFoundError",
    "CompatibilityProjection",
    "project_washer_resolution",
]
