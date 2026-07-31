"""TorqPro Engineering Governance - Faz 2.8.12 Stage 4.2 read-only
compatibility adapter: joint revision review lifecycle -> canonical
governance ``ReviewStatus`` projection.

Read-only, additive, deterministic -- mirrors the read-only contract
``adapters/washer_resolution.py`` (Stage 5) already established, but
does **not** reuse that module's washer-specific resolution semantics
(``MappingQuality``, ``blocked_authoritative_source`` handling, etc.):
joint revisions have their own, simpler four-state model with no
partial/blocked cases, so this module defines its own, purpose-built
outcome vocabulary (see :class:`ProjectionOutcome`) instead of forcing
washer's onto it.

This module reads from ``backend.joints.service``/``backend.joints.
exceptions``/``backend.joints.schema`` and returns a
:class:`JointRevisionProjection`; it never writes anywhere -- not to
the ``joints``/``joint_revisions`` tables, not to the governance event
store. No governance event is ever created by importing or calling
this module. No governance transition command
(``submit_review``/``approve_review``/``reject_review``/etc.) is ever
called by this module.

Critical import rule (Faz 2.8.12 Stage 4.1 spike, empirically
verified -- see
``docs/phases/PHASE_2.8.12_STAGE4_2_JOINT_REVISION_READ_ONLY_ADAPTER.md``
Sec. "Stage 4.1 circular-import evidence"): ``backend.joints.service``
imports ``conn``/``audit``/``now_iso`` from ``backend.app`` **at its
own module level**. ``backend.app`` itself imports
``backend.governance.api`` at its own module level (the Stage 4/
2.8.11-approved router mount). If this adapter imported
``backend.joints.service`` at *its* module level, any code path that
imports ``backend.governance.api`` (or anything that imports this
adapter) before ``backend.app`` has ever been imported would fail with
a real, deterministic ``ImportError`` ("partially initialized
module") -- proven empirically in an isolated spike clone, not merely
theorized. Therefore:

  - ``backend.joints.service`` is imported **only inside a function
    body** (:func:`_joints_service`), on every call, exactly mirroring
    the same, already-proven mitigation
    ``backend/api/dependencies.py``'s own module docstring documents
    for the identical problem with ``backend.app.conn``.
  - ``backend.joints.exceptions`` and ``backend.joints.schema`` have
    **no** dependency on ``backend.app`` at all (verified: neither
    file contains any import beyond ``from __future__ import
    annotations``) and are safe to import at this module's own top
    level, exactly like any other closed-vocabulary/exception import
    elsewhere in this package.
  - This invariant is mechanically enforced by
    ``tests/governance/test_compatibility.py``'s AST-based checks
    (Stage 4.2 additions), not merely documented here.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from backend.joints.exceptions import JointRevisionNotFoundError
from backend.joints.schema import JOINT_REVISION_STATUSES

from ..enums import LifecycleGroup, ReviewStatus

SOURCE_SYSTEM = "joint_revision"


class ProjectionOutcome(str, Enum):
    """Closed, purpose-built classification for one
    :func:`project_joint_revision` call. Deliberately not washer's
    ``MappingQuality`` vocabulary (exact/partial/unsupported) -- joint
    revisions have no partial-mapping case today (all four known
    source statuses map exactly), so a three-value quality scale
    would carry an unused value; this vocabulary instead distinguishes
    *why* a projection did or did not succeed, which is what a reader
    of joint revision data actually needs to know."""

    SUPPORTED = "supported"
    NOT_FOUND = "not_found"
    UNSUPPORTED_STATUS = "unsupported_status"
    INVALID_SOURCE_RECORD = "invalid_source_record"
    SOURCE_UNAVAILABLE = "source_unavailable"


#: Explicit, closed mapping: every value in
#: ``backend.joints.schema.JOINT_REVISION_STATUSES`` maps exactly to a
#: canonical :class:`~backend.governance.enums.ReviewStatus` member.
#: ``review`` -> ``UNDER_REVIEW`` is the one spelling difference;
#: every other value matches verbatim. This is the single source of
#: mapping truth for this module -- never redefined elsewhere.
_STATUS_MAP: dict[str, ReviewStatus] = {
    "draft": ReviewStatus.DRAFT,
    "review": ReviewStatus.UNDER_REVIEW,
    "approved": ReviewStatus.APPROVED,
    "rejected": ReviewStatus.REJECTED,
}

# Import-time self-check: every value the source schema declares is
# accounted for by _STATUS_MAP, and vice versa -- if either ever
# drifts from the other, import fails loudly instead of silently
# projecting (or failing to project) a real status.
assert set(JOINT_REVISION_STATUSES) == set(_STATUS_MAP), (
    "joint_revision adapter's _STATUS_MAP is out of sync with "
    "backend.joints.schema.JOINT_REVISION_STATUSES: "
    f"{set(JOINT_REVISION_STATUSES) ^ set(_STATUS_MAP)}"
)


class JointRevisionProjection(BaseModel):
    """Read-only canonical governance view of one joint revision
    record. Never persisted; never used to construct a
    :class:`~backend.governance.events.GovernanceEvent` or write to
    the governance event store -- purely an on-demand, computed
    read-side projection.

    ``lifecycle_group``/``canonical_status`` are ``None`` exactly when
    ``outcome != ProjectionOutcome.SUPPORTED`` -- a consumer must
    never treat a missing canonical status as equivalent to any real
    status value."""

    model_config = ConfigDict(extra="forbid")

    source_system: str = SOURCE_SYSTEM
    joint_revision_id: int
    source_status: Optional[str] = None
    lifecycle_group: Optional[LifecycleGroup] = None
    canonical_status: Optional[str] = None
    outcome: str
    safe_reason: Optional[str] = None


def _joints_service() -> Any:
    """The **only** place this module imports ``backend.joints.
    service`` -- deferred to call time, never at module level (see
    module docstring, "Critical import rule"). Returns the imported
    module object; callers use it exactly once per
    :func:`project_joint_revision` call."""
    from backend.joints import service as joint_service

    return joint_service


def _unsupported_or_invalid(source_status: Any, revision_id: int) -> JointRevisionProjection:
    """Shared fail-closed path for a status value this module cannot
    project: distinguishes a non-string/missing value (a malformed
    source record -- ``invalid_source_record``) from a well-formed but
    unrecognized string (``unsupported_status``, e.g. a future status
    this module's closed vocabulary does not yet know about). Never
    guesses a canonical status for either case."""
    if not isinstance(source_status, str) or not source_status:
        return JointRevisionProjection(
            joint_revision_id=revision_id,
            source_status=None,
            outcome=ProjectionOutcome.INVALID_SOURCE_RECORD.value,
            safe_reason="Source record is missing a valid status value.",
        )
    return JointRevisionProjection(
        joint_revision_id=revision_id,
        source_status=source_status,
        outcome=ProjectionOutcome.UNSUPPORTED_STATUS.value,
        safe_reason=f"Source status '{source_status}' is not in the supported vocabulary.",
    )


def project_joint_revision(revision_id: int) -> JointRevisionProjection:
    """Read ``revision_id`` from the existing joint revision review
    lifecycle (``backend.joints.service.get_joint_revision``) and
    return its canonical governance compatibility projection.
    Read-only: this function never writes to the ``joints``/
    ``joint_revisions`` tables, never calls a governance transition
    command, and never writes to the governance event store. Never
    raises -- every outcome (found-and-supported, not-found,
    unsupported status, invalid record, source unavailable) is
    returned as a :class:`JointRevisionProjection`, never propagated
    as an exception, so a caller never needs a
    mechanism-specific ``except`` clause to use this function safely.
    """
    try:
        joint_service = _joints_service()
    except Exception:  # noqa: BLE001 - the joints module itself failed to import
        return JointRevisionProjection(
            joint_revision_id=revision_id,
            outcome=ProjectionOutcome.SOURCE_UNAVAILABLE.value,
            safe_reason="Joint revision source module is unavailable.",
        )

    try:
        record = joint_service.get_joint_revision(revision_id)
    except JointRevisionNotFoundError:
        return JointRevisionProjection(
            joint_revision_id=revision_id,
            outcome=ProjectionOutcome.NOT_FOUND.value,
            safe_reason="No joint revision exists with this id.",
        )
    except Exception:  # noqa: BLE001 - sqlite3.Error and any other read-path failure
        # Never echoes a raw exception message, a database path, or a
        # traceback -- see module docstring's "never leak internal
        # detail" contract, mirrored from every other adapter/service
        # boundary in this package.
        return JointRevisionProjection(
            joint_revision_id=revision_id,
            outcome=ProjectionOutcome.SOURCE_UNAVAILABLE.value,
            safe_reason="Joint revision source data could not be read.",
        )

    if not isinstance(record, dict):
        return _unsupported_or_invalid(None, revision_id)

    source_status = record.get("status")
    canonical_status = _STATUS_MAP.get(source_status) if isinstance(source_status, str) else None

    if canonical_status is None:
        return _unsupported_or_invalid(source_status, revision_id)

    return JointRevisionProjection(
        joint_revision_id=revision_id,
        source_status=source_status,
        lifecycle_group=LifecycleGroup.REVIEW,
        canonical_status=canonical_status.value,
        outcome=ProjectionOutcome.SUPPORTED.value,
    )


__all__ = [
    "SOURCE_SYSTEM",
    "ProjectionOutcome",
    "JointRevisionProjection",
    "project_joint_revision",
]
