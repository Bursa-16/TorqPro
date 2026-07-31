"""TorqPro Engineering Governance - Faz 2.8.12 Stage 2 washer
resolution write-path synchronization.

ADR-0015 formalizes the architecture this module implements:
"authoritative-write-then-synchronous-best-effort-sync". This module
never decides anything about a washer resolution -- it only projects
an *already-recorded, already-authoritative*
``backend.library.washer_resolution_decisions.WasherResolutionDecision``
onto a governance event, best-effort, deterministically classified.

Design constraints (Stage 2 scope, enforced structurally):

  - This module never writes to ``washer_resolution_ledger.json`` or
    ``washer_resolution_decisions.json`` -- it only *reads* a
    :class:`WasherResolutionDecision` a caller already obtained
    elsewhere (from ``decide_resolution`` in a future Stage 3, or
    from ``washer_resolution_decisions_store.list_decisions()`` in
    Stage 2's reconciliation tool).
  - :func:`sync_washer_decision` never raises. Every outcome --
    success, a representable-but-already-synced state, a
    non-representable washer state, an unconfigured store, or a
    governance-layer failure -- is returned as a
    :class:`SyncResult`, never as a propagated exception. This is
    what makes it safe to call synchronously from inside a future
    Stage 3 washer API handler without risking the washer business
    transaction's own success response.
  - One algorithm, two callers (task requirement): the exact same
    function serves a future Stage 3 direct-sync call
    (``dry_run=False`` implicitly, called once per fresh decision)
    and Stage 2's reconciliation tool (``dry_run`` either value,
    called once per historical decision). Neither caller re-derives
    any classification or mapping logic of its own.
  - Only the three washer statuses the existing Stage 5
    (``adapters/washer_resolution.py``) compatibility adapter already
    maps with ``MappingQuality.EXACT`` are ever synchronized:
    ``resolved`` -> ``RESOLVED``, ``accepted_as_is`` -> ``WAIVED``,
    ``rejected`` -> ``REJECTED``. ``open`` and ``under_review`` never
    produce a governance event (``skipped_open`` /
    ``not_representable``); ``blocked_authoritative_source`` never
    appears as a decision's ``new_status`` at all (the washer state
    machine has no transition into it), so it is not a case this
    module's classification needs to branch on for *decisions* --
    only the source ledger's original status can be
    ``blocked_authoritative_source``, which is out of this module's
    scope entirely (this module only ever looks at *decisions*, never
    at source ledger records).
  - No wall-clock call is hidden inside a deterministic-looking
    function: :func:`now_utc_iso8601` exists (mirrors
    ``washer_resolution_service.now_utc_iso8601``) and is only called
    when the caller does not supply ``synchronized_at`` explicitly,
    exactly as that module's own precedent already established.
  - Global identifier protection (ADR-0015): governance
    ``decision_id``/``idempotency_key`` uniqueness is *global*, not
    aggregate-scoped (verified against
    ``FileGovernanceEventStore.find_by_decision_id`` /
    ``find_by_idempotency_key``, which scan every event regardless of
    ``aggregate_type``). This module therefore always verifies a
    pre-existing matching event's ``aggregate_type``/``aggregate_id``/
    ``decision_id``/canonical status/source metadata before treating
    it as ``already_synchronized`` -- a same-key, different-content
    record is a conflict, never a silent replay.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from backend.library import washer_resolution as wr
from backend.library.washer_resolution_decisions import WasherResolutionDecision

from ..enums import ResolutionStatus
from ..events import GovernanceEvent
from ..exceptions import (
    GovernanceCorruptionError,
    GovernanceDuplicateDecisionError,
    GovernanceIdempotencyConflictError,
    GovernanceStoreError,
    InvalidTransitionError,
    MissingRequiredFieldError,
)
from ..service import reject_resolution, resolve_resolution, waive_resolution
from ..store import GovernanceEventStore
from .washer_resolution import MappingQuality
from .washer_resolution import _STATUS_MAP as _CANONICAL_WASHER_STATUS_MAP

SOURCE_SYSTEM = "washer_resolution"
AGGREGATE_TYPE = "washer_resolution"
SYNC_VERSION = "1"
IDEMPOTENCY_NAMESPACE = "washer-sync"

#: Derived -- never hand-duplicated -- from
#: ``backend.governance.adapters.washer_resolution._STATUS_MAP``, the
#: one canonical washer-status -> governance-status mapping table
#: (ADR-0015, "Preserve the Closed Allowlist": "The approved status
#: mapping must continue to come from one canonical existing mapping
#: source. Do not introduce a second independent mapping table.").
#: Only the entries the Stage 5 adapter already scores
#: ``MappingQuality.EXACT`` (and whose canonical status is not
#: ``None``) are ever synchronized -- ``under_review``
#: (``PARTIAL``) and ``blocked_authoritative_source``
#: (``UNSUPPORTED``) are excluded here exactly because
#: ``_STATUS_MAP`` itself already scores them below ``EXACT``,
#: not via a second, independently-maintained judgment call in this
#: module.
_SYNCABLE_STATUS_MAP: Dict[wr.WasherResolutionStatus, ResolutionStatus] = {
    washer_status: canonical_status
    for washer_status, (canonical_status, quality) in _CANONICAL_WASHER_STATUS_MAP.items()
    if quality == MappingQuality.EXACT and canonical_status is not None
}

#: The governance command function for each syncable canonical
#: status. One command per status, mirroring
#: ``backend.governance.service``'s own one-function-per-transition
#: design -- this module never re-implements transition selection
#: logic beyond this direct lookup.
_COMMAND_BY_STATUS = {
    ResolutionStatus.RESOLVED: resolve_resolution,
    ResolutionStatus.WAIVED: waive_resolution,
    ResolutionStatus.REJECTED: reject_resolution,
}


def now_utc_iso8601() -> str:
    """Backend-generated UTC ISO-8601 timestamp, ``Z``-suffixed,
    microsecond precision. Mirrors
    ``washer_resolution_service.now_utc_iso8601`` exactly. The only
    place in this module that calls a wall-clock function; always
    overridable by passing ``synchronized_at`` explicitly (tests
    always do)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class SyncOutcome(str, Enum):
    """Closed, deterministic classification of one
    :func:`sync_washer_decision` call. Every value here corresponds
    1:1 to a required reconciliation counter (ADR-0015)."""

    SYNCHRONIZED = "synchronized"
    ALREADY_SYNCHRONIZED = "already_synchronized"
    WOULD_SYNCHRONIZE = "would_synchronize"
    SKIPPED_OPEN = "skipped_open"
    NOT_REPRESENTABLE = "not_representable"
    GOVERNANCE_STORE_UNCONFIGURED = "governance_store_unconfigured"
    FAILED = "failed"


@dataclass(frozen=True)
class SyncResult:
    """Deterministic, structured result of one synchronization
    attempt. Never contains a filesystem path, an environment
    variable value, a traceback, a credential, or raw internal
    exception text -- ``safe_error_category``/``safe_message`` are
    the only fields describing a failure, and both are drawn from a
    closed, hand-written vocabulary (see the ``_FAILED_*`` helpers
    below), never from ``str(exc)`` on an arbitrary exception."""

    resolution_id: str
    washer_decision_id: str
    governance_aggregate_id: str
    outcome: SyncOutcome
    event_written: bool
    retry_may_help: bool
    safe_error_category: Optional[str] = None
    safe_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _build_metadata(
    decision: WasherResolutionDecision, *, synchronized_at: str
) -> Dict[str, Any]:
    """The optional, backward-compatible lineage metadata attached to
    every governance event this module writes. Deliberately not a
    schema change to :class:`~backend.governance.events.
    GovernanceEvent` (ADR-0015) -- everything here lives inside its
    existing, already-optional ``metadata`` field. No
    ``correlation_id`` is fabricated: washer resolution decisions
    carry no correlation identifier today, so the key is simply
    omitted rather than populated with a guessed value."""
    return {
        "source_system": SOURCE_SYSTEM,
        "source_decision_id": decision.decision_id,
        "source_idempotency_key": decision.idempotency_key,
        "source_aggregate_id": decision.resolution_id,
        "source_event_timestamp": decision.decided_at,
        "sync_version": SYNC_VERSION,
        "causation_id": decision.decision_id,
        "synchronized_at": synchronized_at,
    }


def _sync_idempotency_key(decision: WasherResolutionDecision) -> str:
    return f"{IDEMPOTENCY_NAMESPACE}:{decision.idempotency_key}"


def _existing_event_matches(
    existing: GovernanceEvent,
    decision: WasherResolutionDecision,
    canonical_status: ResolutionStatus,
) -> bool:
    """ADR-0015 "Global Identifier Protection": a same-idempotency-key
    event found in the (globally-scoped) governance store is only a
    legitimate prior sync of *this* decision if every one of these
    matches. Any mismatch is a conflict, not a replay -- see
    :data:`SyncOutcome.FAILED` / ``idempotency_conflict`` below."""
    return (
        existing.aggregate_type == AGGREGATE_TYPE
        and existing.aggregate_id == decision.resolution_id
        and existing.decision_id == decision.decision_id
        and existing.new_status == canonical_status.value
        and existing.metadata.get("source_decision_id") == decision.decision_id
        and existing.metadata.get("source_idempotency_key") == decision.idempotency_key
    )


def _result(
    decision: WasherResolutionDecision,
    outcome: SyncOutcome,
    *,
    event_written: bool,
    retry_may_help: bool = False,
    safe_error_category: Optional[str] = None,
    safe_message: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> SyncResult:
    return SyncResult(
        resolution_id=decision.resolution_id,
        washer_decision_id=decision.decision_id,
        governance_aggregate_id=decision.resolution_id,
        outcome=outcome,
        event_written=event_written,
        retry_may_help=retry_may_help,
        safe_error_category=safe_error_category,
        safe_message=safe_message,
        metadata=metadata or {},
    )


def sync_washer_decision(
    decision: WasherResolutionDecision,
    store: Optional[GovernanceEventStore],
    *,
    dry_run: bool = False,
    synchronized_at: Optional[str] = None,
) -> SyncResult:
    """Best-effort, deterministic, never-raising synchronization of
    one washer resolution decision onto the governance event store.

    ``store=None`` means "governance not configured" (the caller has
    already resolved this, e.g. from an unset/blank
    ``TORQPRO_GOVERNANCE_EVENT_STORE_PATH`` -- this function never
    reads that environment variable itself, mirroring every other
    deterministic module in this package).

    ``dry_run=True`` performs every read-only classification step
    (including the idempotency-consistency check) but never calls a
    governance write command -- an eligible, not-yet-synced decision
    is reported as :data:`SyncOutcome.WOULD_SYNCHRONIZE` instead of
    :data:`SyncOutcome.SYNCHRONIZED`.
    """
    if decision.new_status == wr.WasherResolutionStatus.OPEN:
        return _result(decision, SyncOutcome.SKIPPED_OPEN, event_written=False)

    canonical_status = _SYNCABLE_STATUS_MAP.get(decision.new_status)
    if canonical_status is None:
        # under_review (and, defensively, any future non-terminal
        # status this module does not yet know about) -- never
        # guessed, never synthesized. blocked_authoritative_source is
        # not reachable here at all: it is never a *decision*
        # new_status (see module docstring).
        return _result(decision, SyncOutcome.NOT_REPRESENTABLE, event_written=False)

    if store is None:
        return _result(decision, SyncOutcome.GOVERNANCE_STORE_UNCONFIGURED, event_written=False)

    sync_key = _sync_idempotency_key(decision)

    try:
        existing = store.find_by_idempotency_key(sync_key)
    except (GovernanceCorruptionError, GovernanceStoreError) as exc:
        return _result(
            decision,
            SyncOutcome.FAILED,
            event_written=False,
            retry_may_help=isinstance(exc, GovernanceStoreError),
            safe_error_category=_error_category(exc),
            safe_message="Governance event store could not be read.",
        )

    if existing is not None:
        if _existing_event_matches(existing, decision, canonical_status):
            return _result(decision, SyncOutcome.ALREADY_SYNCHRONIZED, event_written=False)
        return _result(
            decision,
            SyncOutcome.FAILED,
            event_written=False,
            retry_may_help=False,
            safe_error_category="idempotency_conflict",
            safe_message=(
                "A governance event already exists for this synchronization key but "
                "does not match the source washer decision. Not auto-repaired."
            ),
        )

    if dry_run:
        return _result(decision, SyncOutcome.WOULD_SYNCHRONIZE, event_written=False)

    resolved_synchronized_at = synchronized_at or now_utc_iso8601()
    metadata = _build_metadata(decision, synchronized_at=resolved_synchronized_at)
    command = _COMMAND_BY_STATUS[canonical_status]

    try:
        event, created = command(
            store,
            aggregate_id=decision.resolution_id,
            aggregate_type=AGGREGATE_TYPE,
            decision_id=decision.decision_id,
            idempotency_key=sync_key,
            actor=decision.resolved_by or None,
            occurred_at=decision.decided_at,
            review_comment=decision.resolution_note or None,
            metadata=metadata,
        )
    except GovernanceIdempotencyConflictError:
        return _result(
            decision,
            SyncOutcome.FAILED,
            event_written=False,
            retry_may_help=False,
            safe_error_category="idempotency_conflict",
            safe_message=(
                "Governance rejected this synchronization key as already used by a "
                "different request. Not auto-repaired."
            ),
        )
    except GovernanceDuplicateDecisionError:
        return _result(
            decision,
            SyncOutcome.FAILED,
            event_written=False,
            retry_may_help=False,
            safe_error_category="decision_id_collision",
            safe_message="Governance decision_id is already used by an unrelated event.",
        )
    except InvalidTransitionError:
        return _result(
            decision,
            SyncOutcome.FAILED,
            event_written=False,
            retry_may_help=False,
            safe_error_category="invalid_transition",
            safe_message=(
                "Governance rejected this transition for the aggregate's current "
                "effective status."
            ),
        )
    except MissingRequiredFieldError:
        return _result(
            decision,
            SyncOutcome.FAILED,
            event_written=False,
            retry_may_help=False,
            safe_error_category="missing_required_field",
            safe_message="Governance rejected this event for a missing required field.",
        )
    except (GovernanceCorruptionError, GovernanceStoreError) as exc:
        return _result(
            decision,
            SyncOutcome.FAILED,
            event_written=False,
            retry_may_help=isinstance(exc, GovernanceStoreError),
            safe_error_category=_error_category(exc),
            safe_message="Governance event store could not complete the write.",
        )
    except Exception:  # noqa: BLE001 - last-resort classification, never re-raised
        return _result(
            decision,
            SyncOutcome.FAILED,
            event_written=False,
            retry_may_help=False,
            safe_error_category="unexpected_error",
            safe_message="An unexpected error occurred during governance synchronization.",
        )

    if not created:
        # Governance's own idempotency engine recognized this as a
        # legitimate replay (matching an event our own pre-check did
        # not find, e.g. a benign race with a concurrent sync call).
        return _result(decision, SyncOutcome.ALREADY_SYNCHRONIZED, event_written=False)

    return _result(
        decision,
        SyncOutcome.SYNCHRONIZED,
        event_written=True,
        metadata={"governance_event_id": event.event_id},
    )


def _error_category(exc: Exception) -> str:
    if isinstance(exc, GovernanceCorruptionError):
        return "store_corruption"
    if isinstance(exc, GovernanceStoreError):
        return "store_io_error"
    return "unexpected_error"  # pragma: no cover - defensive fallback only


#: Faz 2.8.12 Stage 3 -- reuses the project's existing logging setup
#: (``logging.getLogger("torqpro")``, the exact logger name
#: ``backend/app.py`` already uses), never a new logging framework or
#: a separately-configured logger hierarchy.
_LOGGER = logging.getLogger("torqpro")


def sync_washer_decision_and_log(
    decision: WasherResolutionDecision,
    store: Optional[GovernanceEventStore],
) -> SyncResult:
    """The single call site a future (Stage 3) washer API handler
    invokes: runs :func:`sync_washer_decision` and emits one safe,
    structured log line describing the outcome, then returns the
    result unchanged. Never raises -- even a failure while
    constructing or emitting the log line is swallowed, so this
    function carries exactly the same "never affects the caller's
    success response" guarantee as :func:`sync_washer_decision`
    itself.

    The log line never contains a filesystem path, an environment
    variable value, a credential, a traceback, or the decision's own
    ``resolution_note``/``evidence_reference`` payload -- only
    identifiers and the closed, already-safe classification fields
    already present on :class:`SyncResult`.
    """
    result = sync_washer_decision(decision, store)
    try:
        _LOGGER.info(
            "washer_governance_sync resolution_id=%s decision_id=%s outcome=%s "
            "event_written=%s retry_may_help=%s safe_error_category=%s",
            result.resolution_id,
            result.washer_decision_id,
            result.outcome.value,
            result.event_written,
            result.retry_may_help,
            result.safe_error_category,
        )
    except Exception:  # noqa: BLE001 - logging must never break the washer response
        pass
    return result


__all__ = [
    "SOURCE_SYSTEM",
    "AGGREGATE_TYPE",
    "SYNC_VERSION",
    "IDEMPOTENCY_NAMESPACE",
    "SyncOutcome",
    "SyncResult",
    "now_utc_iso8601",
    "sync_washer_decision",
    "sync_washer_decision_and_log",
]
