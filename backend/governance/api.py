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
and ``backend.governance.*``.

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
from backend.governance import service as svc
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


def get_governance_store() -> GovernanceEventStore:
    """FastAPI dependency: resolve the governance event store lazily,
    per request, from :data:`GOVERNANCE_EVENT_STORE_PATH_ENV`. Reading
    the environment variable at call time (not at import time) is
    what makes this overridable/injectable in tests via
    ``app.dependency_overrides``.

    Raises a 503 with a generic message (no filesystem path) if the
    variable is unset or blank -- this is a configuration problem,
    not a client error, so it is intentionally not a 4xx."""
    raw_path = os.environ.get(GOVERNANCE_EVENT_STORE_PATH_ENV, "")
    if not raw_path.strip():
        raise HTTPException(503, "Governance event store yapılandırılmamış.")
    return FileGovernanceEventStore(Path(raw_path))


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
    it, so no route hand-rolls its own mapping."""
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


__all__ = ["router", "get_governance_store", "GOVERNANCE_EVENT_STORE_PATH_ENV"]
