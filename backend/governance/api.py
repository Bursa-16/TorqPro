"""TorqPro Engineering Governance - Faz 2.8.11 Stage 4 API.

Thin, additive FastAPI routes over the Stage 3 service layer
(:mod:`backend.governance.service`). Every route here is orchestration
only: request parsing, calling exactly one Stage 3 function, and
mapping its result/exceptions to an HTTP response. No transition
rule, idempotency rule, effective-status calculation, lifecycle
validation, or event-construction logic is duplicated here -- see
each handler's single call into ``backend.governance.service``.

Mounted from ``backend/app.py`` under the ``/api/governance`` prefix,
reusing the existing ``backend.api.dependencies.user`` authentication
dependency (the same one every other TorqPro endpoint uses) -- no new
authentication mechanism is introduced.

Compatibility (restated from ``backend/governance/__init__.py``):
this module never reads, writes, or imports anything from
``backend.production_validation``, ``backend.joints``,
``backend.library`` (including the washer resolution ledgers), or the
``calculation_revisions``/``audit_log`` tables in ``backend/app.py``.
It only reaches into ``backend.api.dependencies`` (for the shared
``user`` auth dependency, mirroring
``backend/api/routes/production_validation.py``'s existing pattern)
and ``backend.governance.*`` -- including, since Faz 2.8.13 Stage 2,
``backend.governance.adapters.joint_revision`` (an intra-package
import; this module still never imports ``backend.joints`` itself,
only the already-approved adapter that safely does so via its own
deferred-import pattern).

Faz 2.8.13 Stage 2: one additional read-only endpoint,
``GET /joint-revision/{revision_id}``, exposes the existing,
already-approved ``project_joint_revision`` compatibility adapter
(Faz 2.8.12 Stage 4.2). This handler performs no mapping, mutation,
or persistence of its own -- see ``governance_joint_revision`` below.
It does not use ``get_governance_store``/the event store at all: the
projection it returns is computed on demand from
``backend.joints.service`` (via the adapter's own deferred import),
never read from or written to any governance-owned storage.

Store configuration (task item 6): the event store is resolved
*lazily*, per request, via :func:`get_governance_store`, from the
``TORQPRO_GOVERNANCE_EVENT_STORE_PATH`` environment variable -- there
is no hard-coded production path and nothing is written into the
source tree by default. If the variable is unset or blank, every
route that needs the store raises a safe 503 with a generic message
(no filesystem path is ever included). Tests override
:func:`get_governance_store` via FastAPI's ``dependency_overrides`` to
inject a temporary path per test, exactly as task item 6 requires.

Actor handling: per the approved request contract, ``actor`` is never
accepted from the request body -- it is always derived from the
authenticated user's ``display_name`` (the same field every other
TorqPro endpoint already trusts from the ``user`` dependency). A
client attempting to send ``actor`` in a command body is rejected at
the request-validation layer (every command model uses
``extra="forbid"``), before the handler body ever runs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.api.dependencies import user
from backend.governance import ownership
from backend.governance import service as svc
from backend.governance.adapters.joint_revision import (
    ProjectionOutcome,
    project_joint_revision,
    project_joint_revisions_bulk,
)
from backend.governance.enums import LifecycleGroup
from backend.governance.events import GovernanceEvent
from backend.governance.exceptions import (
    GovernanceCorruptionError,
    GovernanceDuplicateDecisionError,
    GovernanceIdempotencyConflictError,
    GovernanceStoreError,
    InvalidTransitionError,
    MissingRequiredFieldError,
)
from backend.governance.store import FileGovernanceEventStore, GovernanceEventStore

router = APIRouter(prefix="/api/governance", tags=["governance"])

#: Environment variable holding the governance event store's writable
#: file path. No default/fallback path is defined -- an unset or
#: blank value means "not configured", handled by
#: :func:`get_governance_store` as a 503, never as a silent
#: source-tree write.
GOVERNANCE_EVENT_STORE_PATH_ENV = "TORQPRO_GOVERNANCE_EVENT_STORE_PATH"


def resolve_governance_store() -> Optional[GovernanceEventStore]:
    """Non-raising resolution of the governance event store from
    :data:`GOVERNANCE_EVENT_STORE_PATH_ENV`, read lazily at call time
    (not import time). Returns ``None`` if the variable is unset or
    blank -- "not configured" is a normal, expected outcome for this
    function, never an exception.

    This is the single source of governance-store resolution logic,
    reused by :func:`get_governance_store` (the FastAPI dependency,
    which raises 503 on ``None``) and, since Faz 2.8.12 Stage 3, by
    the washer resolution decide endpoint's best-effort governance
    synchronization call (which passes ``None`` straight through to
    :func:`~backend.governance.adapters.washer_resolution_sync.
    sync_washer_decision`, classified
    ``governance_store_unconfigured`` -- never an error). No new
    environment variable is introduced; no production store is ever
    auto-created."""
    raw_path = os.environ.get(GOVERNANCE_EVENT_STORE_PATH_ENV, "")
    if not raw_path.strip():
        return None
    return FileGovernanceEventStore(Path(raw_path))


def get_governance_store() -> GovernanceEventStore:
    """FastAPI dependency: resolve the governance event store lazily,
    per request, via :func:`resolve_governance_store`. Reading the
    environment variable at call time (not at import time) is what
    makes this overridable/injectable in tests via
    ``app.dependency_overrides``.

    Raises a 503 with a generic message (no filesystem path) if the
    variable is unset or blank -- this is a configuration problem,
    not a client error, so it is intentionally not a 4xx."""
    store = resolve_governance_store()
    if store is None:
        raise HTTPException(503, "Governance event store yapılandırılmamış.")
    return store


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------
#
# Every field here maps 1:1 onto a parameter the target Stage 3
# service function already accepts -- no field is invented beyond
# what that function's signature supports. `actor`, `event_id`, and
# `previous_status` are deliberately never fields on any of these
# models (see module docstring).


class _GovernanceCommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aggregate_type: str
    decision_id: str
    idempotency_key: str
    occurred_at: str
    metadata: Optional[Dict[str, Any]] = None


class ReviewSubmitRequest(_GovernanceCommandBase):
    change_reason: Optional[str] = None


class ReviewApproveRequest(_GovernanceCommandBase):
    review_comment: Optional[str] = None


class ReviewRejectRequest(_GovernanceCommandBase):
    review_comment: Optional[str] = None


class PublicationActivateRequest(_GovernanceCommandBase):
    revision_no: Optional[int] = None
    supersedes_id: Optional[str] = None
    change_reason: Optional[str] = None


class PublicationSupersedeRequest(_GovernanceCommandBase):
    # activate_publication accepts revision_no/supersedes_id;
    # supersede_publication's actual Stage 3 signature accepts only
    # superseded_by_id as its lineage field -- no revision_no or
    # supersedes_id parameter exists on that function, so neither is
    # exposed here (task rule: "do not invent unsupported lineage
    # fields").
    superseded_by_id: str


class PublicationArchiveRequest(_GovernanceCommandBase):
    change_reason: Optional[str] = None


class ResolutionActionRequest(_GovernanceCommandBase):
    review_comment: Optional[str] = None


# ---------------------------------------------------------------------
# Shared response building / exception mapping
# ---------------------------------------------------------------------


def _command_response(event: GovernanceEvent, created: bool) -> JSONResponse:
    """Uniform response shape for every write endpoint, per the
    approved response-behavior contract: 201 + result="created" for a
    genuinely new event, 200 + result="existing" for a recognized
    idempotent retry (the original stored event, never a second
    one)."""
    payload = {
        "result": "created" if created else "existing",
        "idempotent": not created,
        "event": event.model_dump(mode="json"),
    }
    return JSONResponse(status_code=201 if created else 200, content=payload)


def _run_command(fn, /, **kwargs):
    """Call one Stage 3 command function and map its exceptions to
    the approved HTTP status codes. This is the *only* place that
    exception-to-status mapping happens -- every route below reuses
    it, so no route hand-rolls its own mapping.

    Faz 2.8.12 Stage 2 aggregate-ownership guard: this is also the
    single choke point shared by all nine write endpoints, so it is
    the one place the ownership check
    (:func:`backend.governance.ownership.is_externally_owned`) needs
    to live -- no per-route duplication. An externally-owned
    ``aggregate_type`` (e.g. ``"washer_resolution"``) is rejected
    with the same 409 conflict convention every other write-rejection
    in this module already uses, *before* ``fn`` is ever called, so
    no governance event is written and no Stage 3 service function
    runs. This check only applies to the generic HTTP surface: an
    internal, in-process caller (e.g. a future
    ``backend.governance.adapters.washer_resolution_sync`` call) never
    goes through this function's HTTP request path and is unaffected.
    """
    aggregate_type = kwargs.get("aggregate_type")
    if aggregate_type is not None and ownership.is_externally_owned(aggregate_type):
        raise HTTPException(
            409,
            f"aggregate_type '{aggregate_type}' is owned by another mechanism; "
            "writes must go through that mechanism's own synchronization path.",
        )
    try:
        event, created = fn(**kwargs)
    except InvalidTransitionError as exc:
        raise HTTPException(409, str(exc))
    except MissingRequiredFieldError as exc:
        raise HTTPException(422, str(exc))
    except GovernanceIdempotencyConflictError as exc:
        raise HTTPException(409, str(exc))
    except GovernanceDuplicateDecisionError as exc:
        raise HTTPException(409, str(exc))
    except ValidationError:
        # A client-supplied field (most likely occurred_at) failed
        # Stage 2/3 model validation -- a client input problem, not a
        # server fault.
        raise HTTPException(422, "Geçersiz istek alanı (ör. occurred_at biçimi).")
    except (GovernanceCorruptionError, GovernanceStoreError):
        # Never echo the underlying message (it is already generic,
        # but the boundary between "client-visible" and
        # "server-internal" errors is enforced here regardless of
        # what a lower layer's message happens to say).
        raise HTTPException(503, "Governance event store şu anda kullanılamıyor.")
    return _command_response(event, created)


def _events_for_aggregate_and_type(
    store: GovernanceEventStore, aggregate_id: str, aggregate_type: str
) -> List[GovernanceEvent]:
    """Every event recorded for ``aggregate_id`` whose own
    ``aggregate_type`` matches the caller-supplied query parameter.
    This is presentation-layer filtering over data
    ``backend.governance.service.event_history`` already returns --
    it does not re-derive or duplicate any effective-status or
    transition logic, it only narrows which already-computed events
    are shown."""
    try:
        all_events = svc.event_history(store, aggregate_id)
    except (GovernanceCorruptionError, GovernanceStoreError):
        raise HTTPException(503, "Governance event store şu anda kullanılamıyor.")
    return [e for e in all_events if e.aggregate_type == aggregate_type]


def _require_known_aggregate(
    store: GovernanceEventStore, aggregate_id: str, aggregate_type: str
) -> List[GovernanceEvent]:
    events = _events_for_aggregate_and_type(store, aggregate_id, aggregate_type)
    if not events:
        raise HTTPException(
            404,
            "Belirtilen aggregate_id / aggregate_type için governance kaydı bulunamadı.",
        )
    return events


# ---------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------


@router.get("/{aggregate_id}/history")
def governance_history(
    aggregate_id: str,
    aggregate_type: str,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    events = _require_known_aggregate(store, aggregate_id, aggregate_type)
    return {
        "aggregate_id": aggregate_id,
        "aggregate_type": aggregate_type,
        "events": [e.model_dump(mode="json") for e in events],
        "total_events": len(events),
    }


@router.get("/{aggregate_id}/status")
def governance_status(
    aggregate_id: str,
    aggregate_type: str,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    _require_known_aggregate(store, aggregate_id, aggregate_type)

    def _latest_for(group: LifecycleGroup) -> Optional[GovernanceEvent]:
        try:
            return svc.latest_event(store, aggregate_id, group)
        except (GovernanceCorruptionError, GovernanceStoreError):
            raise HTTPException(503, "Governance event store şu anda kullanılamıyor.")

    latest = {
        "review": _latest_for(LifecycleGroup.REVIEW),
        "publication": _latest_for(LifecycleGroup.PUBLICATION),
        "resolution": _latest_for(LifecycleGroup.RESOLUTION),
    }
    return {
        "aggregate_id": aggregate_id,
        "aggregate_type": aggregate_type,
        "status": {group: (event.new_status if event else None) for group, event in latest.items()},
        "latest_events": {
            group: (event.model_dump(mode="json") if event else None)
            for group, event in latest.items()
        },
    }


# ---------------------------------------------------------------------
# Compatibility projection endpoints -- read-only, mechanism-specific
# (Faz 2.8.13 Stage 2)
# ---------------------------------------------------------------------

#: HTTP status for every possible ``project_joint_revision`` outcome.
#: Only ``not_found`` differs from ``200``: ``unsupported_status``,
#: ``invalid_source_record``, and ``source_unavailable`` are all
#: legitimate, already-classified adapter results, not request-
#: handling failures -- each is returned as ``200`` with the outcome
#: visible in the response body, exactly like ``supported``, so a
#: caller can distinguish "record does not exist" (404) from "record
#: exists but this adapter could not project it" (200, self-
#: describing). This is the single source of this mapping -- never
#: duplicated elsewhere in this module or the frontend.
_JOINT_REVISION_OUTCOME_STATUS: Dict[str, int] = {
    ProjectionOutcome.SUPPORTED.value: 200,
    ProjectionOutcome.UNSUPPORTED_STATUS.value: 200,
    ProjectionOutcome.INVALID_SOURCE_RECORD.value: 200,
    ProjectionOutcome.SOURCE_UNAVAILABLE.value: 200,
    ProjectionOutcome.NOT_FOUND.value: 404,
}


@router.get("/joint-revision/{revision_id}")
def governance_joint_revision(revision_id: int, u=Depends(user)):
    """Faz 2.8.13 Stage 2: read-only exposure of the existing, Faz
    2.8.12 Stage 4.2 ``project_joint_revision`` adapter -- the
    Phase 2.8.13 Stage 1 contract's one approved new route
    (``docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md``,
    Section 5).

    This handler adds no mapping, mutation, or persistence logic of
    its own: it calls the adapter exactly once and returns its
    existing, already-serializable ``JointRevisionProjection`` as-is,
    selecting the HTTP status from
    :data:`_JOINT_REVISION_OUTCOME_STATUS`. ``project_joint_revision``
    is documented and tested to never raise, so this handler
    deliberately has no ``try/except`` around the call -- adding one
    would risk reintroducing exactly the exception-message/traceback
    leakage the adapter itself was built to prevent, for no benefit.

    No governance event store dependency is injected here (unlike
    every route below): this endpoint never reads from or writes to
    the governance event store, so it has none to depend on.
    """
    projection = project_joint_revision(revision_id)
    status_code = _JOINT_REVISION_OUTCOME_STATUS[projection.outcome]
    return JSONResponse(status_code=status_code, content=projection.model_dump(mode="json"))


@router.get("/joint-revisions")
def governance_joint_revisions_bulk(joint_id: Optional[int] = None, u=Depends(user)):
    """Faz 2.8.14 Stage 3: read-only, additive bulk exposure of the
    existing, Faz 2.8.14 Stage 2 ``project_joint_revisions_bulk``
    adapter function -- the Phase 2.8.14 Stage 1 contract's one
    approved new route
    (``docs/phases/PHASE_2.8.14_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md``,
    Section 10).

    Distinct static path segment (``joint-revisions``, plural) from
    the existing ``joint-revision/{revision_id}`` route above
    (singular) -- Starlette matches on exact literal segment text, so
    the two never collide regardless of declaration order; this route
    is placed directly after the single-record route purely for
    reader locality (both are "compatibility projection endpoints"),
    not because ordering affects matching here.

    This handler adds no mapping, mutation, or persistence logic of
    its own: it calls the bulk adapter function exactly once and
    returns its existing, already-serializable
    ``JointRevisionProjection`` list as a bare JSON array -- no
    wrapper object, no pagination metadata, matching the Stage 1
    contract's explicit "no envelope" decision. Always ``200`` for a
    well-formed request: an empty result is a legitimate, non-error
    outcome (empty list), not a ``404`` -- unlike the single-record
    route above, whose ``404`` means "this specific id does not
    exist," a concept that does not apply to a list endpoint.
    ``joint_id`` is typed ``Optional[int]``, so a non-integer query
    value produces FastAPI's own standard ``422`` validation response
    with no custom validation logic added here.

    ``project_joint_revisions_bulk`` is documented and tested to never
    raise (mirrors ``project_joint_revision``'s own fail-closed
    design, returning ``[]`` on any internal read failure rather than
    propagating an exception), so this handler deliberately has no
    ``try/except`` of its own -- adding one would risk reintroducing
    exactly the exception-message/traceback leakage the adapter was
    built to prevent, for no benefit.

    No governance event store dependency is injected here (unlike
    every write route below): this endpoint never reads from or
    writes to the governance event store, so it has none to depend
    on.
    """
    projections = project_joint_revisions_bulk(joint_id)
    return [p.model_dump(mode="json") for p in projections]


# ---------------------------------------------------------------------
# Write endpoints -- lifecycle A: review
# ---------------------------------------------------------------------


@router.post("/review/{aggregate_id}/submit")
def governance_review_submit(
    aggregate_id: str,
    x: ReviewSubmitRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.submit_review,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        change_reason=x.change_reason,
        metadata=x.metadata,
    )


@router.post("/review/{aggregate_id}/approve")
def governance_review_approve(
    aggregate_id: str,
    x: ReviewApproveRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.approve_review,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        review_comment=x.review_comment,
        metadata=x.metadata,
    )


@router.post("/review/{aggregate_id}/reject")
def governance_review_reject(
    aggregate_id: str,
    x: ReviewRejectRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.reject_review,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        review_comment=x.review_comment,
        metadata=x.metadata,
    )


# ---------------------------------------------------------------------
# Write endpoints -- lifecycle B: publication/revision
# ---------------------------------------------------------------------


@router.post("/publication/{aggregate_id}/activate")
def governance_publication_activate(
    aggregate_id: str,
    x: PublicationActivateRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.activate_publication,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        revision_no=x.revision_no,
        supersedes_id=x.supersedes_id,
        change_reason=x.change_reason,
        metadata=x.metadata,
    )


@router.post("/publication/{aggregate_id}/supersede")
def governance_publication_supersede(
    aggregate_id: str,
    x: PublicationSupersedeRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.supersede_publication,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        superseded_by_id=x.superseded_by_id,
        metadata=x.metadata,
    )


@router.post("/publication/{aggregate_id}/archive")
def governance_publication_archive(
    aggregate_id: str,
    x: PublicationArchiveRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.archive_publication,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        change_reason=x.change_reason,
        metadata=x.metadata,
    )


# ---------------------------------------------------------------------
# Write endpoints -- lifecycle C: resolution
# ---------------------------------------------------------------------


@router.post("/resolution/{aggregate_id}/resolve")
def governance_resolution_resolve(
    aggregate_id: str,
    x: ResolutionActionRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.resolve_resolution,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        review_comment=x.review_comment,
        metadata=x.metadata,
    )


@router.post("/resolution/{aggregate_id}/reject")
def governance_resolution_reject(
    aggregate_id: str,
    x: ResolutionActionRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.reject_resolution,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        review_comment=x.review_comment,
        metadata=x.metadata,
    )


@router.post("/resolution/{aggregate_id}/waive")
def governance_resolution_waive(
    aggregate_id: str,
    x: ResolutionActionRequest,
    store: GovernanceEventStore = Depends(get_governance_store),
    u=Depends(user),
):
    return _run_command(
        svc.waive_resolution,
        store=store,
        aggregate_id=aggregate_id,
        aggregate_type=x.aggregate_type,
        decision_id=x.decision_id,
        idempotency_key=x.idempotency_key,
        actor=u["display_name"],
        occurred_at=x.occurred_at,
        review_comment=x.review_comment,
        metadata=x.metadata,
    )


__all__ = [
    "router",
    "get_governance_store",
    "resolve_governance_store",
    "GOVERNANCE_EVENT_STORE_PATH_ENV",
]
