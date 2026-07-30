"""TorqPro Engineering Governance - Faz 2.8.11 Stage 3 service layer.

Additive command functions (one per legal transition, across all
three lifecycle groups) and read accessors, all operating against a
caller-supplied :class:`~backend.governance.store.GovernanceEventStore`
-- there is no module-level default store and nothing here is wired
into any existing mechanism or API route (see package ``__init__.py``
for the full compatibility contract).

Design constraints (Faz 2.8.11 Stage 3 scope, enforced structurally):

  - **Idempotency-key-first, always.** Every one of the nine
    transition functions below resolves idempotency
    (:func:`_resolve_idempotency`) *before* computing effective
    status or validating the requested transition
    (:func:`_execute_transition`'s ordering). This matters
    concretely: without this ordering, a legitimate retry of an
    already-applied request would see the *already-advanced*
    effective status (e.g. ``under_review`` instead of ``draft``) and
    fail Stage 2 transition validation even though it is the exact
    same request that already succeeded once. Checking idempotency
    first means a genuine retry is recognized and returned unchanged
    before effective status is even computed. This restates
    ADR-0013 Sec. 4's justification, generalized to all three
    lifecycle groups.
  - **``previous_status`` is never caller-suppliable.** None of the
    nine transition functions accepts a ``previous_status``
    parameter at all -- the *effective* previous status is always
    computed from the aggregate's own event history
    (:func:`effective_status`), exactly mirroring
    ``backend.library.washer_resolution_service.effective_status``'s
    "client-supplied previous_status is not accepted by this
    function's signature at all" design.
  - **No lifecycle rule duplication.** Every transition's legality
    and required-field enforcement is delegated to the Stage 2
    validators (``backend.governance.models.validate_review_decision``
    / ``validate_publication_decision`` / ``validate_resolution_decision``)
    via a Stage 2 ``*Decision`` model built from this call's actual
    field values. This module adds no second transition table and no
    second required-fields table.
  - **No hidden use of local time.** No function in this module calls
    ``datetime.now()`` or any other wall-clock source. ``occurred_at``
    is always caller-supplied and UTC-ISO-8601-format-validated by
    :class:`~backend.governance.events.GovernanceEvent` itself.
  - **Injectable identifiers.** ``event_id`` is an optional parameter
    on every command; when omitted, a random id is generated via
    :func:`_default_event_id_factory`, which tests can bypass
    entirely by always supplying an explicit ``event_id``.
  - **Fail-closed on malformed/unsupported lifecycle or status
    values.** Each of the nine transition functions hard-codes its
    own ``new_status`` (there is no generic "transition(new_status)"
    entry point a caller could pass an arbitrary string into); a
    request for a status the underlying enum does not define fails at
    Stage 2 model construction (a Pydantic ``ValidationError``) before
    any event is built or persisted.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from .enums import LifecycleGroup, PublicationStatus, ResolutionStatus, ReviewStatus
from .events import GovernanceEvent
from .exceptions import (
    GovernanceAggregateNotFoundError,
    GovernanceDuplicateDecisionError,
    GovernanceIdempotencyConflictError,
)
from .models import (
    PublicationDecision,
    ResolutionDecision,
    ReviewDecision,
    validate_publication_decision,
    validate_resolution_decision,
    validate_review_decision,
)
from .store import GovernanceEventStore

#: The status a lifecycle group is in for an aggregate with no
#: recorded events yet -- ADR-0014's "draft"/"open" initial states.
_INITIAL_STATUS: Dict[LifecycleGroup, str] = {
    LifecycleGroup.REVIEW: ReviewStatus.DRAFT.value,
    LifecycleGroup.PUBLICATION: PublicationStatus.DRAFT.value,
    LifecycleGroup.RESOLUTION: ResolutionStatus.OPEN.value,
}


def _default_event_id_factory() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------
# Read accessors
# ---------------------------------------------------------------------


def event_history(
    store: GovernanceEventStore,
    aggregate_id: str,
    lifecycle_group: Optional[LifecycleGroup] = None,
) -> List[GovernanceEvent]:
    """Every event recorded for ``aggregate_id``, in append order
    (oldest first) -- the store's own history, filtered to one
    lifecycle group if ``lifecycle_group`` is given. This history is
    authoritative and immutable: nothing in this package ever
    rewrites or removes an entry from it."""
    events = store.events_for_aggregate(aggregate_id)
    if lifecycle_group is not None:
        events = [e for e in events if e.lifecycle_group == lifecycle_group]
    return events


def latest_event(
    store: GovernanceEventStore,
    aggregate_id: str,
    lifecycle_group: Optional[LifecycleGroup] = None,
    *,
    strict: bool = False,
) -> Optional[GovernanceEvent]:
    """The most recently appended event for ``aggregate_id`` (in the
    given ``lifecycle_group`` if provided), or ``None`` if there is
    none. If ``strict=True`` and there is none, raises
    :class:`~backend.governance.exceptions.GovernanceAggregateNotFoundError`
    instead of returning ``None``."""
    events = event_history(store, aggregate_id, lifecycle_group)
    if not events:
        if strict:
            raise GovernanceAggregateNotFoundError(
                aggregate_id, lifecycle_group.value if lifecycle_group else "any"
            )
        return None
    return events[-1]


def effective_status(
    store: GovernanceEventStore, aggregate_id: str, lifecycle_group: LifecycleGroup
) -> str:
    """The effective status of ``aggregate_id`` in ``lifecycle_group``:
    the ``new_status`` of its most recent event in that group, or the
    group's initial status (``draft``/``open``) if it has no events
    yet. This is the *only* place effective status is computed in
    this package -- every transition function below calls this
    rather than re-deriving it, mirroring
    ``backend.library.washer_resolution_service.effective_status``'s
    "no second implementation of this logic exists anywhere" rule."""
    event = latest_event(store, aggregate_id, lifecycle_group)
    if event is None:
        return _INITIAL_STATUS[lifecycle_group]
    return event.new_status


# ---------------------------------------------------------------------
# Idempotency-first request handling (shared by all nine commands)
# ---------------------------------------------------------------------


def _normalize_request(
    *,
    aggregate_id: str,
    aggregate_type: str,
    lifecycle_group: LifecycleGroup,
    decision_id: str,
    new_status: str,
    actor: Optional[str],
    review_comment: Optional[str],
    change_reason: Optional[str],
    revision_no: Optional[int],
    supersedes_id: Optional[str],
    superseded_by_id: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """A comparable, JSON-safe projection of "everything about this
    request that determines its effect", deliberately excluding
    ``occurred_at`` and ``event_id`` -- a legitimate network retry may
    carry a freshly-generated timestamp/id without ceasing to be the
    "same" request, mirroring ADR-0013 Sec. 4's precedent (which
    likewise excludes ``decided_at`` from its idempotency comparison).
    Also excludes ``previous_status`` deliberately -- it is never
    caller-supplied in the first place (see module docstring)."""
    return {
        "aggregate_id": aggregate_id,
        "aggregate_type": aggregate_type,
        "lifecycle_group": lifecycle_group.value,
        "decision_id": decision_id,
        "new_status": new_status,
        "actor": actor,
        "review_comment": review_comment,
        "change_reason": change_reason,
        "revision_no": revision_no,
        "supersedes_id": supersedes_id,
        "superseded_by_id": superseded_by_id,
        "metadata": metadata or {},
    }


def _event_matches_request(event: GovernanceEvent, normalized: Dict[str, Any]) -> bool:
    return {
        "aggregate_id": event.aggregate_id,
        "aggregate_type": event.aggregate_type,
        "lifecycle_group": event.lifecycle_group.value,
        "decision_id": event.decision_id,
        "new_status": event.new_status,
        "actor": event.actor,
        "review_comment": event.review_comment,
        "change_reason": event.change_reason,
        "revision_no": event.revision_no,
        "supersedes_id": event.supersedes_id,
        "superseded_by_id": event.superseded_by_id,
        "metadata": event.metadata,
    } == normalized


def _resolve_idempotency(
    store: GovernanceEventStore, idempotency_key: str, decision_id: str, normalized: Dict[str, Any]
) -> Optional[GovernanceEvent]:
    """The *first* thing every transition function does (see
    :func:`_execute_transition`) -- called before effective status is
    computed or any transition table is consulted. Three outcomes:

      1. An event with this ``idempotency_key`` already exists and
         matches ``normalized`` exactly -> return it (legitimate
         retry; caller should treat this as ``created=False``).
      2. An event with this ``idempotency_key`` already exists but
         does *not* match -> raise
         :class:`GovernanceIdempotencyConflictError`.
      3. No event with this ``idempotency_key`` exists, but
         ``decision_id`` is already used by a *different* event (so
         it cannot be recognized as this key's retry) -> raise
         :class:`GovernanceDuplicateDecisionError`.

    Returns ``None`` only when neither the key nor the decision id
    has been seen before -- i.e. the caller should proceed to compute
    effective status, validate the transition, and append a new
    event.
    """
    existing_by_key = store.find_by_idempotency_key(idempotency_key)
    if existing_by_key is not None:
        if _event_matches_request(existing_by_key, normalized):
            return existing_by_key
        raise GovernanceIdempotencyConflictError(idempotency_key)

    existing_by_decision = store.find_by_decision_id(decision_id)
    if existing_by_decision is not None:
        raise GovernanceDuplicateDecisionError(decision_id)

    return None


def _execute_transition(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    lifecycle_group: LifecycleGroup,
    decision_id: str,
    idempotency_key: str,
    new_status: str,
    occurred_at: str,
    actor: Optional[str],
    review_comment: Optional[str],
    change_reason: Optional[str],
    revision_no: Optional[int],
    supersedes_id: Optional[str],
    superseded_by_id: Optional[str],
    metadata: Optional[Dict[str, Any]],
    event_id: Optional[str],
    validate_against_previous: Callable[[str], None],
) -> Tuple[GovernanceEvent, bool]:
    """Shared engine for all nine transition functions, in the
    required order:

      1. Resolve idempotency first (:func:`_resolve_idempotency`) --
         a genuine retry returns here, before step 2 ever runs.
      2. Only for a genuinely new request: compute effective status
         (:func:`effective_status`) and call
         ``validate_against_previous(previous_status)`` -- a small
         closure each transition function supplies, which builds its
         own Stage 2 ``*Decision`` model with that previous status
         and calls the matching ``validate_*_decision`` (raises
         :class:`~backend.governance.exceptions.InvalidTransitionError`
         or
         :class:`~backend.governance.exceptions.MissingRequiredFieldError`
         if illegal).
      3. Build and append the :class:`~backend.governance.events.
         GovernanceEvent`.
    """
    normalized = _normalize_request(
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=lifecycle_group,
        decision_id=decision_id,
        new_status=new_status,
        actor=actor,
        review_comment=review_comment,
        change_reason=change_reason,
        revision_no=revision_no,
        supersedes_id=supersedes_id,
        superseded_by_id=superseded_by_id,
        metadata=metadata,
    )

    # Step 1: idempotency, before anything else touches transition
    # legality or effective status.
    existing = _resolve_idempotency(store, idempotency_key, decision_id, normalized)
    if existing is not None:
        return existing, False

    # Step 2: only now, for a genuinely new request, compute
    # effective status and validate the transition.
    previous_status = effective_status(store, aggregate_id, lifecycle_group)
    validate_against_previous(previous_status)

    # Step 3: persist.
    event = GovernanceEvent(
        event_id=event_id or _default_event_id_factory(),
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=lifecycle_group,
        previous_status=previous_status,
        new_status=new_status,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        actor=actor,
        occurred_at=occurred_at,
        review_comment=review_comment,
        change_reason=change_reason,
        revision_no=revision_no,
        supersedes_id=supersedes_id,
        superseded_by_id=superseded_by_id,
        metadata=metadata or {},
    )
    store.append(event)
    return event, True


# ---------------------------------------------------------------------
# Lifecycle A: review commands
# ---------------------------------------------------------------------


def submit_review(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    change_reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``draft -> under_review``. Requires ``actor``/``occurred_at``
    (mapped onto Stage 2's ``submitted_by``/``submitted_at``, per
    ADR-0014's required-field table)."""

    def _validate(previous: str) -> None:
        validate_review_decision(
            ReviewDecision(
                decision_id=decision_id,
                idempotency_key=idempotency_key,
                previous_status=ReviewStatus(previous),
                new_status=ReviewStatus.UNDER_REVIEW,
                submitted_by=actor,
                submitted_at=occurred_at,
                change_reason=change_reason,
                created_at=occurred_at,
            )
        )

    return _execute_transition(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=LifecycleGroup.REVIEW,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        new_status=ReviewStatus.UNDER_REVIEW.value,
        occurred_at=occurred_at,
        actor=actor,
        review_comment=None,
        change_reason=change_reason,
        revision_no=None,
        supersedes_id=None,
        superseded_by_id=None,
        metadata=metadata,
        event_id=event_id,
        validate_against_previous=_validate,
    )


def approve_review(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    review_comment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``under_review -> approved`` (terminal)."""

    def _validate(previous: str) -> None:
        validate_review_decision(
            ReviewDecision(
                decision_id=decision_id,
                idempotency_key=idempotency_key,
                previous_status=ReviewStatus(previous),
                new_status=ReviewStatus.APPROVED,
                approved_by=actor,
                approved_at=occurred_at,
                review_comment=review_comment,
                created_at=occurred_at,
            )
        )

    return _execute_transition(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=LifecycleGroup.REVIEW,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        new_status=ReviewStatus.APPROVED.value,
        occurred_at=occurred_at,
        actor=actor,
        review_comment=review_comment,
        change_reason=None,
        revision_no=None,
        supersedes_id=None,
        superseded_by_id=None,
        metadata=metadata,
        event_id=event_id,
        validate_against_previous=_validate,
    )


def reject_review(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    review_comment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``under_review -> rejected`` (terminal)."""

    def _validate(previous: str) -> None:
        validate_review_decision(
            ReviewDecision(
                decision_id=decision_id,
                idempotency_key=idempotency_key,
                previous_status=ReviewStatus(previous),
                new_status=ReviewStatus.REJECTED,
                rejected_by=actor,
                rejected_at=occurred_at,
                review_comment=review_comment,
                created_at=occurred_at,
            )
        )

    return _execute_transition(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=LifecycleGroup.REVIEW,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        new_status=ReviewStatus.REJECTED.value,
        occurred_at=occurred_at,
        actor=actor,
        review_comment=review_comment,
        change_reason=None,
        revision_no=None,
        supersedes_id=None,
        superseded_by_id=None,
        metadata=metadata,
        event_id=event_id,
        validate_against_previous=_validate,
    )


# ---------------------------------------------------------------------
# Lifecycle B: publication/revision commands
# ---------------------------------------------------------------------


def activate_publication(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    revision_no: Optional[int] = None,
    supersedes_id: Optional[str] = None,
    change_reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``draft -> active``. ``supersedes_id`` is optional: pass the
    aggregate_id of the revision this one replaces to record the
    forward half of a supersession lineage pointer pair (the backward
    half is recorded separately by :func:`supersede_publication` on
    the other aggregate -- see ADR-0014, "Revision lineage
    principles")."""

    def _validate(previous: str) -> None:
        validate_publication_decision(
            PublicationDecision(
                decision_id=decision_id,
                idempotency_key=idempotency_key,
                previous_status=PublicationStatus(previous),
                new_status=PublicationStatus.ACTIVE,
                submitted_by=actor,
                revision_no=revision_no,
                supersedes_id=supersedes_id,
                change_reason=change_reason,
                created_at=occurred_at,
            )
        )

    return _execute_transition(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=LifecycleGroup.PUBLICATION,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        new_status=PublicationStatus.ACTIVE.value,
        occurred_at=occurred_at,
        actor=actor,
        review_comment=None,
        change_reason=change_reason,
        revision_no=revision_no,
        supersedes_id=supersedes_id,
        superseded_by_id=None,
        metadata=metadata,
        event_id=event_id,
        validate_against_previous=_validate,
    )


def supersede_publication(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    superseded_by_id: str,
    occurred_at: str,
    actor: Optional[str] = None,
    change_reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``active -> superseded`` (terminal). ``superseded_by_id`` is
    mandatory (ADR-0014's required-field table for this transition):
    the aggregate_id of the revision that replaces this one -- the
    backward half of the lineage pointer pair (see
    :func:`activate_publication`)."""

    def _validate(previous: str) -> None:
        validate_publication_decision(
            PublicationDecision(
                decision_id=decision_id,
                idempotency_key=idempotency_key,
                previous_status=PublicationStatus(previous),
                new_status=PublicationStatus.SUPERSEDED,
                superseded_by_id=superseded_by_id,
                change_reason=change_reason,
                created_at=occurred_at,
            )
        )

    return _execute_transition(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=LifecycleGroup.PUBLICATION,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        new_status=PublicationStatus.SUPERSEDED.value,
        occurred_at=occurred_at,
        actor=actor,
        review_comment=None,
        change_reason=change_reason,
        revision_no=None,
        supersedes_id=None,
        superseded_by_id=superseded_by_id,
        metadata=metadata,
        event_id=event_id,
        validate_against_previous=_validate,
    )


def archive_publication(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    change_reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``active -> archived`` (terminal)."""

    def _validate(previous: str) -> None:
        validate_publication_decision(
            PublicationDecision(
                decision_id=decision_id,
                idempotency_key=idempotency_key,
                previous_status=PublicationStatus(previous),
                new_status=PublicationStatus.ARCHIVED,
                submitted_by=actor,
                change_reason=change_reason,
                created_at=occurred_at,
            )
        )

    return _execute_transition(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=LifecycleGroup.PUBLICATION,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        new_status=PublicationStatus.ARCHIVED.value,
        occurred_at=occurred_at,
        actor=actor,
        review_comment=None,
        change_reason=change_reason,
        revision_no=None,
        supersedes_id=None,
        superseded_by_id=None,
        metadata=metadata,
        event_id=event_id,
        validate_against_previous=_validate,
    )


# ---------------------------------------------------------------------
# Lifecycle C: resolution commands
# ---------------------------------------------------------------------


def _resolution_command(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    new_status: ResolutionStatus,
    review_comment: Optional[str],
    metadata: Optional[Dict[str, Any]],
    event_id: Optional[str],
) -> Tuple[GovernanceEvent, bool]:
    """Shared body for :func:`resolve_resolution`,
    :func:`reject_resolution`, and :func:`waive_resolution` -- all
    three are ``open -> <terminal>`` with the same required fields
    (ADR-0014's resolution-lifecycle row lists one generic rule for
    all three outcomes)."""

    def _validate(previous: str) -> None:
        validate_resolution_decision(
            ResolutionDecision(
                decision_id=decision_id,
                idempotency_key=idempotency_key,
                previous_status=ResolutionStatus(previous),
                new_status=new_status,
                reviewed_by=actor,
                reviewed_at=occurred_at,
                review_comment=review_comment,
                created_at=occurred_at,
            )
        )

    return _execute_transition(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        lifecycle_group=LifecycleGroup.RESOLUTION,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        new_status=new_status.value,
        occurred_at=occurred_at,
        actor=actor,
        review_comment=review_comment,
        change_reason=None,
        revision_no=None,
        supersedes_id=None,
        superseded_by_id=None,
        metadata=metadata,
        event_id=event_id,
        validate_against_previous=_validate,
    )


def resolve_resolution(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    review_comment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``open -> resolved`` (terminal)."""
    return _resolution_command(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        actor=actor,
        occurred_at=occurred_at,
        new_status=ResolutionStatus.RESOLVED,
        review_comment=review_comment,
        metadata=metadata,
        event_id=event_id,
    )


def reject_resolution(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    review_comment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``open -> rejected`` (terminal)."""
    return _resolution_command(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        actor=actor,
        occurred_at=occurred_at,
        new_status=ResolutionStatus.REJECTED,
        review_comment=review_comment,
        metadata=metadata,
        event_id=event_id,
    )


def waive_resolution(
    store: GovernanceEventStore,
    *,
    aggregate_id: str,
    aggregate_type: str,
    decision_id: str,
    idempotency_key: str,
    actor: str,
    occurred_at: str,
    review_comment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
) -> Tuple[GovernanceEvent, bool]:
    """``open -> waived`` (terminal)."""
    return _resolution_command(
        store,
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        decision_id=decision_id,
        idempotency_key=idempotency_key,
        actor=actor,
        occurred_at=occurred_at,
        new_status=ResolutionStatus.WAIVED,
        review_comment=review_comment,
        metadata=metadata,
        event_id=event_id,
    )


__all__ = [
    "event_history",
    "latest_event",
    "effective_status",
    "submit_review",
    "approve_review",
    "reject_review",
    "activate_publication",
    "supersede_publication",
    "archive_publication",
    "resolve_resolution",
    "reject_resolution",
    "waive_resolution",
]
