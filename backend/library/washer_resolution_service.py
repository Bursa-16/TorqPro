"""TorqPro Engineering Library - Faz 2.8.9 washer resolution decision
service layer (Stage 3: orchestration).

This is the only module that cross-references the Faz 2.8.5 source
ledger (``backend.library.washer_resolution``, read-only) with the
Faz 2.8.9 append-only decision audit trail
(``backend.library.washer_resolution_decisions_store``). Neither of
those two modules imports the other; this module is where they meet.

Key architectural point: recording a decision here **never writes to
``washer_resolution_ledger.json``**. The source ledger's 76 records
keep their original ``resolution_status`` forever (71
``open`` + 5 ``blocked_authoritative_source``, unless a *future* phase
regenerates that file from a new provenance run -- out of scope here).
What this workflow provides instead is an **effective status**: the
``new_status`` of the most recently recorded decision for a
``resolution_id``, if any decision exists, falling back to the source
ledger's original status otherwise. This is what makes the workflow
actually function (a second decision attempt must see the first
decision's outcome) without ever mutating the Faz 2.8.5 file, exactly
as task brief rule 4 requires.

Idempotency is checked **before** state-machine validation, not
after: a retried request (same ``idempotency_key``) must return the
original decision unchanged even if, by the time of the retry, the
effective status has already moved past what a fresh validation would
accept. Checking the state machine first would make legitimate
network retries fail with a spurious :class:`InvalidTransitionError`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from . import washer_resolution as wr
from .washer_resolution_decisions import (
    BlockedRecordDecisionError,
    InvalidTransitionError,
    MissingEvidenceError,
    WasherResolutionDecision,
    validate_decision_fields,
    validate_transition,
)
from .washer_resolution_decisions_store import (
    DuplicateDecisionIdError,
    build_decision,
    decisions_for_resolution,
    find_by_idempotency_key,
    record_decision,
)

__all__ = [
    "ResolutionNotFoundError",
    "MissingIdempotencyKeyError",
    "IdempotencyConflictError",
    "BlockedRecordDecisionError",
    "InvalidTransitionError",
    "MissingEvidenceError",
    "DuplicateDecisionIdError",
    "now_utc_iso8601",
    "effective_status",
    "decide_resolution",
    "resolution_queue",
]


class ResolutionNotFoundError(Exception):
    """Raised when ``resolution_id`` does not exist in the Faz 2.8.5
    source ledger at all -- distinct from a legal-but-blocked record,
    which raises :class:`BlockedRecordDecisionError` instead."""

    def __init__(self, resolution_id: str):
        self.resolution_id = resolution_id
        super().__init__(f"Resolution '{resolution_id}' was not found in the ledger.")


class MissingIdempotencyKeyError(Exception):
    """Raised when a decision request has no ``idempotency_key``. The
    Faz 2.8.9 API requires one on every decision request (task brief
    rule 11); the underlying schema still accepts ``None`` for
    backward compatibility with Stage 1 tests, but this service layer
    enforces the real requirement for anything reaching the API."""


class IdempotencyConflictError(Exception):
    """Raised when ``idempotency_key`` matches a previously recorded
    decision, but the *current* request's fields (status/note/
    evidence/resolved_by/confidence) differ from that original
    decision's fields. A true retry of the same request is a safe,
    silent replay (see :func:`decide_resolution`); reusing a key for a
    materially different request is a client bug and must fail loudly
    rather than silently return a stale, mismatched decision."""

    def __init__(self, idempotency_key: str):
        self.idempotency_key = idempotency_key
        super().__init__(
            f"idempotency_key '{idempotency_key}' was already used for a "
            "different decision request."
        )


def now_utc_iso8601() -> str:
    """Backend-generated UTC ISO-8601 timestamp, ``Z``-suffixed,
    microsecond precision. The **only** place in the entire washer
    resolution decision workflow that calls a wall-clock function --
    every other module (domain model, persistence) is deterministic
    given its inputs. The API layer calls this itself and never
    accepts a client-supplied ``decided_at`` (task brief rule 7)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def effective_status(resolution_id: str) -> wr.WasherResolutionStatus:
    """The status this workflow currently treats as authoritative for
    ``resolution_id``: the ``new_status`` of the most recent recorded
    decision, or -- if no decision has ever been recorded for this
    resolution -- the Faz 2.8.5 source ledger's original
    ``resolution_status``.

    Raises :class:`ResolutionNotFoundError` if ``resolution_id`` does
    not exist in the source ledger at all.
    """
    source_record = wr.get_washer_resolution(resolution_id)
    if source_record is None:
        raise ResolutionNotFoundError(resolution_id)
    history = decisions_for_resolution(resolution_id)
    if history:
        return history[-1].new_status
    return source_record.resolution_status


def _same_request(
    existing: WasherResolutionDecision,
    *,
    resolution_id: str,
    new_status: wr.WasherResolutionStatus,
    resolution_note: str,
    evidence_reference: str,
    resolved_by: str,
    confidence_level: Optional[wr.ConfidenceLevel],
) -> bool:
    """``True`` if a fresh request's fields exactly match the
    previously recorded decision's own fields -- i.e. this is a safe
    replay of the same request, not a different request (including a
    different ``resolution_id``) reusing the same key by mistake."""
    return (
        existing.resolution_id == resolution_id
        and existing.new_status == new_status
        and existing.resolution_note == resolution_note
        and existing.evidence_reference == evidence_reference
        and existing.resolved_by == resolved_by
        and existing.confidence_level == confidence_level
    )


def decide_resolution(
    *,
    resolution_id: str,
    new_status: wr.WasherResolutionStatus,
    resolution_note: str,
    evidence_reference: str,
    resolved_by: str,
    idempotency_key: str,
    confidence_level: Optional[wr.ConfidenceLevel] = None,
) -> Tuple[WasherResolutionDecision, bool]:
    """Full orchestration for one decision request.

    1. Reject a missing ``idempotency_key`` outright.
    2. If this exact ``idempotency_key`` was already recorded:
       - if the current request's fields match the original decision
         exactly, return that original decision unchanged
         (``created=False``) -- a safe, silent replay. No further
         validation runs, so a legitimate retry can never fail
         state-machine validation just because the first attempt
         already advanced the effective status.
       - if any field differs, raise :class:`IdempotencyConflictError`
         -- reusing a key for a different request is rejected, not
         silently accepted as if it were the original.
    3. Otherwise: look up the resolution (404 domain error if absent),
       compute its current :func:`effective_status`, validate the
       requested transition is legal for that status (raises
       :class:`BlockedRecordDecisionError` for the 5 blocked records,
       :class:`InvalidTransitionError` for any other illegal move),
       validate the note/evidence/resolved_by are non-blank, generate
       ``decided_at`` here (never from the caller), build a
       checksummed decision and record it.

    Never writes to ``washer_resolution_ledger.json``. Any
    client-supplied ``previous_status`` is not accepted by this
    function's signature at all -- the effective previous status is
    always computed server-side from the ledger + decision history,
    never trusted from the caller.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise MissingIdempotencyKeyError()

    replay = find_by_idempotency_key(idempotency_key)
    if replay is not None:
        if _same_request(
            replay,
            resolution_id=resolution_id,
            new_status=new_status,
            resolution_note=resolution_note,
            evidence_reference=evidence_reference,
            resolved_by=resolved_by,
            confidence_level=confidence_level,
        ):
            return replay, False
        raise IdempotencyConflictError(idempotency_key)

    previous_status = effective_status(resolution_id)  # raises ResolutionNotFoundError
    validate_transition(previous_status, new_status, resolution_id=resolution_id)
    validate_decision_fields(resolution_note, evidence_reference, resolved_by)

    decision = build_decision(
        decision_id=f"DEC-{uuid.uuid4()}",
        resolution_id=resolution_id,
        previous_status=previous_status,
        new_status=new_status,
        resolution_note=resolution_note,
        evidence_reference=evidence_reference,
        resolved_by=resolved_by,
        decided_at=now_utc_iso8601(),
        idempotency_key=idempotency_key,
        confidence_level=confidence_level,
    )
    return record_decision(decision)


def resolution_queue() -> List[dict]:
    """Read-only view of every one of the 76 Faz 2.8.5 ledger records,
    each annotated with its :func:`effective_status`, its original
    source status, and its decision count -- the shape the Stage 3 API
    and the Stage 5 frontend "Resolution Queue" are built from. Never
    mutates anything; safe to call at any time."""
    rows: List[dict] = []
    for record in wr.list_washer_resolutions():
        history = decisions_for_resolution(record.resolution_id)
        current = history[-1].new_status if history else record.resolution_status
        rows.append(
            {
                "resolution_id": record.resolution_id,
                "washer_record_id": record.washer_record_id,
                "issue_type": record.issue_type.value,
                "source_status": record.resolution_status.value,
                "effective_status": current.value,
                "decision_count": len(history),
                "is_blocked": record.resolution_status
                == wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE,
                "is_terminal": current in wr.TERMINAL_STATUSES,
                "requires_authoritative_source": record.requires_authoritative_source,
            }
        )
    return rows
