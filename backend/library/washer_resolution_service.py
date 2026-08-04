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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from . import washer_resolution as wr
from . import washer_resolution_closure as wc
from . import washer_resolution_closure_store as wc_store
from . import washer_resolution_evidence as we
from . import washer_resolution_evidence_store as we_store
from .washer_resolution_decisions import (
    BlockedRecordDecisionError,
    InvalidTransitionError,
    MissingEvidenceError,
    WasherResolutionDecision,
    is_blocked_source_status,
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
from .washer_resolution_closure_store import DuplicateClosureError

__all__ = [
    "ResolutionNotFoundError",
    "MissingIdempotencyKeyError",
    "IdempotencyConflictError",
    "BlockedRecordDecisionError",
    "InvalidTransitionError",
    "MissingEvidenceError",
    "DuplicateDecisionIdError",
    "EvidenceIntegrityError",
    "ClosureIntegrityError",
    "ClosureNotReadyError",
    "DuplicateClosureError",
    "now_utc_iso8601",
    "effective_status",
    "decide_resolution",
    "resolution_queue",
    "resolution_detail",
    "ClosureReadiness",
    "record_resolution_evidence",
    "resolution_evidence_for",
    "evaluate_closure_readiness",
    "close_resolution",
    "get_resolution_closure",
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


class EvidenceIntegrityError(Exception):
    """Raised when a :class:`~backend.library.washer_resolution_evidence.
    WasherResolutionEvidence` record's ``integrity_checksum`` does not
    match a fresh recomputation over its own fields -- i.e. it is
    corrupt or was hand-edited. Raised both at write time (Stage 3
    task brief rule: service must verify integrity *before* calling
    ``washer_resolution_evidence_store.append_evidence``) and at read
    time (:func:`resolution_evidence_for`, when a persisted record
    fails verification). One shared exception for both cases: the
    underlying problem -- checksum does not match content -- is
    identical regardless of when it is detected."""

    def __init__(self, evidence_id: str):
        self.evidence_id = evidence_id
        super().__init__(
            f"Evidence '{evidence_id}' failed integrity verification "
            "(checksum does not match content)."
        )


class ClosureIntegrityError(Exception):
    """Raised when a :class:`~backend.library.washer_resolution_closure.
    WasherResolutionClosure` record's ``integrity_checksum`` does not
    match a fresh recomputation over its own fields. Kept distinct
    from :class:`EvidenceIntegrityError` (rather than reused) because
    the two protect different record types with different callers --
    a caller catching one must not accidentally also catch integrity
    failures for the other kind of record."""

    def __init__(self, resolution_id: str):
        self.resolution_id = resolution_id
        super().__init__(
            f"Closure for resolution '{resolution_id}' failed integrity "
            "verification (checksum does not match content)."
        )


class ClosureNotReadyError(Exception):
    """Raised by :func:`close_resolution` when
    :func:`evaluate_closure_readiness` reports ``is_ready=False``.
    Carries the same ``blocking_reasons`` the readiness result
    reported, so a caller does not have to call
    :func:`evaluate_closure_readiness` separately just to learn why."""

    def __init__(self, resolution_id: str, blocking_reasons: List[str]):
        self.resolution_id = resolution_id
        self.blocking_reasons = list(blocking_reasons)
        super().__init__(
            f"Resolution '{resolution_id}' is not ready for closure: "
            + "; ".join(blocking_reasons)
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


def resolution_detail(resolution_id: str) -> Optional[dict]:
    """Faz 2.8.19 Stage 1: read-only detail view for a single
    resolution. Merges the Faz 2.8.5 canonical ledger record's own
    fields (``reason_code``, ``resolution_note``, ``evidence_reference``,
    ``resolved_standard``, ``resolved_by``, ``resolved_at``,
    ``confidence_level``) with the effective-status/decision-count/
    ``is_blocked``/``is_terminal`` annotation :func:`resolution_queue`
    already computes for every record.

    Deliberately calls :func:`resolution_queue` rather than
    re-deriving that annotation here: the Faz 2.8.9 Stage 4/5A design
    principle is that effective-status logic is never duplicated
    between the report, the API and the frontend -- this function
    extends that principle to a third consumer instead of forking a
    second copy of the formula. Returns ``None`` if ``resolution_id``
    does not exist in the source ledger. Never mutates anything: no
    file is written, no decision is recorded, both source calls are
    already read-only.
    """
    record = wr.get_washer_resolution(resolution_id)
    if record is None:
        return None
    queue_row = next(
        row for row in resolution_queue() if row["resolution_id"] == resolution_id
    )
    return {
        "resolution_id": record.resolution_id,
        "washer_record_id": record.washer_record_id,
        "issue_type": record.issue_type.value,
        "reason_code": record.reason_code,
        "source_status": queue_row["source_status"],
        "effective_status": queue_row["effective_status"],
        "decision_count": queue_row["decision_count"],
        "is_blocked": queue_row["is_blocked"],
        "is_terminal": queue_row["is_terminal"],
        "resolution_note": record.resolution_note,
        "evidence_reference": record.evidence_reference,
        "resolved_standard": record.resolved_standard,
        "resolved_by": record.resolved_by,
        "resolved_at": record.resolved_at,
        "confidence_level": (
            record.confidence_level.value if record.confidence_level is not None else None
        ),
        "requires_authoritative_source": record.requires_authoritative_source,
    }


# =======================================================================
# Faz 2.8.20 Stage 3 - evidence orchestration and controlled closure
# =======================================================================
#
# This section is the third cross-reference point this module adds
# (after decisions in the section above): it is where the Faz 2.8.5
# source ledger, the Faz 2.8.9 decision audit trail, the Faz 2.8.20
# Stage 1/2 evidence ledger, and the Stage 3 closure ledger all meet.
# None of those four modules imports any of the others; this module
# remains the single place that cross-references them, exactly as its
# module docstring already states for decisions.
#
# resolution_id existence is validated here (wr.get_washer_resolution),
# never inside washer_resolution_evidence_store.py or
# washer_resolution_closure_store.py -- neither persistence layer
# performs this check by design (Stage 1/2 decisions), so it is a
# service-layer responsibility on every function below that touches a
# resolution_id.
#
# Checksum integrity is verified here too, on both the write path
# (before every append_evidence/append_closure call) and the read
# path (every persisted record this module hands back to a caller) --
# neither persistence layer verifies integrity automatically either
# (see the Stage 2 code review). A corrupted persisted evidence record
# is never silently included in a closure-readiness computation.
#
# Reopen does not exist anywhere in this section, matching ADR-0013:
# a closure, once appended, has no code path that alters or removes
# it.


@dataclass(frozen=True)
class ClosureReadiness:
    """Immutable, typed result of :func:`evaluate_closure_readiness`.
    Never persisted -- this is a computed, point-in-time view, not a
    ledger record."""

    resolution_id: str
    effective_status: wr.WasherResolutionStatus
    is_ready: bool
    decision_id: Optional[str] = None
    verified_evidence_ids: List[str] = field(default_factory=list)
    unverified_evidence_ids: List[str] = field(default_factory=list)
    rejected_evidence_ids: List[str] = field(default_factory=list)
    corrupted_evidence_ids: List[str] = field(default_factory=list)
    blocking_reasons: List[str] = field(default_factory=list)


def record_resolution_evidence(
    *,
    resolution_id: str,
    evidence_type: we.EvidenceType,
    title: str,
    description: str,
    source_reference: str,
    created_by: str,
    source_locator: Optional[str] = None,
    source_url: Optional[str] = None,
    source_standard: Optional[str] = None,
) -> we.WasherResolutionEvidence:
    """Validate ``resolution_id`` against the source ledger, build a
    checksummed evidence record (:func:`~backend.library.
    washer_resolution_evidence.create_washer_resolution_evidence`),
    verify its own integrity before persisting it, then append it.

    Raises :class:`ResolutionNotFoundError` if ``resolution_id`` does
    not exist in the source ledger, or :class:`EvidenceIntegrityError`
    if the freshly-built record somehow fails its own integrity check
    (a defense-in-depth guard -- the factory always produces a
    matching checksum, so this should never actually fire in
    practice). Never writes to
    ``washer_resolution_ledger.json`` or
    ``washer_resolution_decisions.json``.
    """
    if wr.get_washer_resolution(resolution_id) is None:
        raise ResolutionNotFoundError(resolution_id)

    evidence = we.create_washer_resolution_evidence(
        resolution_id=resolution_id,
        evidence_type=evidence_type,
        title=title,
        description=description,
        source_reference=source_reference,
        created_by=created_by,
        source_locator=source_locator,
        source_url=source_url,
        source_standard=source_standard,
    )
    if not we.verify_evidence_integrity(evidence):
        raise EvidenceIntegrityError(evidence.evidence_id)
    return we_store.append_evidence(evidence)


def resolution_evidence_for(resolution_id: str) -> List[we.WasherResolutionEvidence]:
    """Validate ``resolution_id``, then return every persisted
    evidence record for it, in append order.

    Raises :class:`ResolutionNotFoundError` if ``resolution_id`` does
    not exist, or :class:`EvidenceIntegrityError` on the **first**
    persisted record whose checksum no longer matches its content --
    a corrupted record is never silently included in the returned
    list."""
    if wr.get_washer_resolution(resolution_id) is None:
        raise ResolutionNotFoundError(resolution_id)
    records = we_store.evidence_for_resolution(resolution_id)
    for record in records:
        if not we.verify_evidence_integrity(record):
            raise EvidenceIntegrityError(record.evidence_id)
    return records


def evaluate_closure_readiness(resolution_id: str) -> ClosureReadiness:
    """Compute, but never persist, whether ``resolution_id`` may be
    closed right now.

    ``is_ready`` is ``True`` only if **all** of the following hold:

      - the source ledger's status is not
        ``blocked_authoritative_source``;
      - :func:`effective_status` is one of ``TERMINAL_STATUSES``
        (``resolved`` / ``accepted_as_is`` / ``rejected``), and a
        decision record for that terminal transition was found (its
        ``decision_id`` is carried on the result);
      - at least one persisted evidence record has
        ``verification_status == verified``;
      - **no** persisted evidence record for this resolution fails
        integrity verification -- a single corrupted record blocks
        closure entirely, even if enough verified evidence exists
        elsewhere (task brief rule 9: never silently drop a corrupted
        record from the computation);
      - no closure has already been recorded for this resolution.

    Every reason ``is_ready`` is ``False`` is appended to
    ``blocking_reasons`` in human-readable form -- callers never have
    to re-derive why. Raises :class:`ResolutionNotFoundError` if
    ``resolution_id`` does not exist in the source ledger.
    """
    source_record = wr.get_washer_resolution(resolution_id)
    if source_record is None:
        raise ResolutionNotFoundError(resolution_id)

    blocking_reasons: List[str] = []

    if is_blocked_source_status(source_record.resolution_status):
        blocking_reasons.append(
            "resolution is blocked_authoritative_source and cannot be closed"
        )

    current_status = effective_status(resolution_id)
    decision_id: Optional[str] = None
    if current_status not in wr.TERMINAL_STATUSES:
        blocking_reasons.append(
            f"effective_status '{current_status.value}' is not terminal"
        )
    else:
        history = decisions_for_resolution(resolution_id)
        if history:
            decision_id = history[-1].decision_id
        else:
            # Structurally unreachable today: no source-ledger record
            # is itself born into a TERMINAL_STATUSES value (see
            # effective_status() docstring) -- a terminal
            # effective_status can only be reached via a recorded
            # decision. Guarded anyway, fail-closed, rather than
            # assumed.
            blocking_reasons.append(
                "effective_status is terminal but no decision record was found"
            )

    verified_ids: List[str] = []
    unverified_ids: List[str] = []
    rejected_ids: List[str] = []
    corrupted_ids: List[str] = []
    for evidence in we_store.evidence_for_resolution(resolution_id):
        if not we.verify_evidence_integrity(evidence):
            corrupted_ids.append(evidence.evidence_id)
            continue
        if evidence.verification_status == we.EvidenceVerificationStatus.VERIFIED:
            verified_ids.append(evidence.evidence_id)
        elif evidence.verification_status == we.EvidenceVerificationStatus.REJECTED:
            rejected_ids.append(evidence.evidence_id)
        else:
            unverified_ids.append(evidence.evidence_id)

    if corrupted_ids:
        blocking_reasons.append(
            f"{len(corrupted_ids)} evidence record(s) failed integrity verification"
        )

    if not verified_ids:
        blocking_reasons.append("no verified evidence exists for this resolution")

    existing_closure = wc_store.get_closure_for_resolution(resolution_id)
    if existing_closure is not None:
        blocking_reasons.append(
            f"resolution already has a closure ('{existing_closure.closure_id}')"
        )

    return ClosureReadiness(
        resolution_id=resolution_id,
        effective_status=current_status,
        is_ready=not blocking_reasons,
        decision_id=decision_id,
        verified_evidence_ids=verified_ids,
        unverified_evidence_ids=unverified_ids,
        rejected_evidence_ids=rejected_ids,
        corrupted_evidence_ids=corrupted_ids,
        blocking_reasons=blocking_reasons,
    )


def close_resolution(
    *,
    resolution_id: str,
    closure_rationale: str,
    closed_by: str,
) -> wc.WasherResolutionClosure:
    """Full orchestration for one closure request.

    1. Validate ``resolution_id`` against the source ledger (404
       domain error if absent).
    2. Reject ``blocked_authoritative_source`` records outright
       (:class:`BlockedRecordDecisionError`, reused unchanged from
       the decision workflow -- not redefined here).
    3. Fast, non-atomic pre-check: if a closure already exists,
       raise :class:`DuplicateClosureError` immediately rather than
       running the full readiness computation.
    4. Call :func:`evaluate_closure_readiness`; if not ready, raise
       :class:`ClosureNotReadyError` carrying its ``blocking_reasons``.
    5. Build a checksummed closure whose ``evidence_ids`` are
       *exactly* the readiness result's ``verified_evidence_ids``
       (never unverified/rejected/corrupted ones) and whose
       ``decision_id`` is the readiness result's terminal decision.
    6. Verify the freshly-built closure's own integrity
       (defense-in-depth), then append it.

    The authoritative duplicate guard is
    ``washer_resolution_closure_store.append_closure``'s own
    ``resolution_id``-keyed, lock-protected check (step 3 above is
    only a friendlier, non-racing fast path) -- this is what makes
    "only one of several concurrent close attempts for the same
    resolution succeeds" actually true under concurrency, not just on
    the common sequential path.

    Never writes to ``washer_resolution_ledger.json``,
    ``washer_resolution_decisions.json``, or
    ``washer_resolution_evidence.json``.
    """
    source_record = wr.get_washer_resolution(resolution_id)
    if source_record is None:
        raise ResolutionNotFoundError(resolution_id)

    if is_blocked_source_status(source_record.resolution_status):
        raise BlockedRecordDecisionError(resolution_id)

    if wc_store.get_closure_for_resolution(resolution_id) is not None:
        raise DuplicateClosureError(resolution_id)

    readiness = evaluate_closure_readiness(resolution_id)
    if not readiness.is_ready:
        raise ClosureNotReadyError(resolution_id, readiness.blocking_reasons)

    assert readiness.decision_id is not None  # guaranteed by is_ready == True

    closure = wc.create_washer_resolution_closure(
        resolution_id=resolution_id,
        closure_rationale=closure_rationale,
        closed_by=closed_by,
        evidence_ids=readiness.verified_evidence_ids,
        decision_id=readiness.decision_id,
    )
    if not wc.verify_closure_integrity(closure):
        raise ClosureIntegrityError(resolution_id)

    return wc_store.append_closure(closure)


def get_resolution_closure(resolution_id: str) -> Optional[wc.WasherResolutionClosure]:
    """Validate ``resolution_id``, then return its closure record if
    one exists (``None`` otherwise), after verifying its integrity.

    Raises :class:`ResolutionNotFoundError` if ``resolution_id`` does
    not exist in the source ledger, or :class:`ClosureIntegrityError`
    if a persisted closure record's checksum no longer matches its
    content."""
    if wr.get_washer_resolution(resolution_id) is None:
        raise ResolutionNotFoundError(resolution_id)
    closure = wc_store.get_closure_for_resolution(resolution_id)
    if closure is None:
        return None
    if not wc.verify_closure_integrity(closure):
        raise ClosureIntegrityError(resolution_id)
    return closure
