"""Washer Resolution Evidence & Controlled Closure HTTP API (Faz
2.8.20 Stage 4).

Thin FastAPI routes over the existing, already-tested
``backend.library.washer_resolution_service`` orchestration layer
(Stage 3). No business logic, no checksum computation, no readiness
rule, and no ledger I/O lives in this module -- every one of those
already lives in ``washer_resolution_service`` /
``washer_resolution_evidence`` / ``washer_resolution_closure`` and is
covered by ``tests/test_faz_2_8_20_stage3_washer_resolution_controlled_closure.py``;
this module only does request validation, authentication, the service
call itself, response serialization, and domain-exception ->
``HTTPException`` mapping.

Follows ``backend/api/routes/joints.py``'s established pattern
(``APIRouter``, Pydantic request schemas, ``Depends(user)``, a single
central ``_handle()`` exception-mapping helper) without introducing a
new convention.

Never writes to ``washer_resolution_ledger.json``,
``washer_resolution_decisions.json``,
``washer_resolution_evidence.json``, or
``washer_resolution_closure.json`` directly -- every write goes
through the Stage 2/3 persistence layers via the service functions
above, exactly as those functions' own docstrings already guarantee.

No idempotency-key field exists on either request model here
(``ResolutionEvidenceCreate``, ``ResolutionCloseRequest``) -- Stage 3
task brief decision 2 deliberately did not add an idempotency
mechanism to evidence or closure (unlike the decision workflow's
``/decide`` endpoint), so none is invented at the API layer either.

``GET .../closure`` returns ``200 {"closure": null}`` when no closure
exists yet, not a ``404`` -- the *resolution* was found (a 404 there
would be misleading); it simply has not been closed. This mirrors
``GET .../evidence`` returning ``200 {"records": []}`` for a
resolution with no evidence yet, rather than treating "zero records"
as an error.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["washer_resolution_closure"])

# `router` is assigned before these imports for the same reason
# backend/api/routes/production_validation.py and
# backend/api/routes/joints.py already document on their own
# equivalent import blocks: if backend.app ends up re-entering this
# module while it is still mid-import, the partially-initialized
# module already exposes a usable `router` attribute, which breaks a
# circular-import failure instead of propagating it.
from backend.api.dependencies import user  # noqa: E402
from backend.library import washer_resolution_evidence as we  # noqa: E402
from backend.library import washer_resolution_service as svc  # noqa: E402

import logging  # noqa: E402

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------


class ResolutionEvidenceCreate(BaseModel):
    """Faz 2.8.20 Stage 4: additive, new endpoint. ``extra="forbid"``
    so a client cannot smuggle in a backend-generated field
    (``evidence_id``, ``created_at``, ``integrity_checksum``,
    ``verification_status``, ``verified_by``, ``verified_at``) --
    each is rejected as an unknown field (422) rather than silently
    ignored, matching this project's closed-request-schema
    convention."""

    model_config = ConfigDict(extra="forbid")

    evidence_type: str
    title: str
    description: str
    source_reference: str
    created_by: str
    source_locator: Optional[str] = None
    source_url: Optional[str] = None
    source_standard: Optional[str] = None


class ResolutionCloseRequest(BaseModel):
    """Faz 2.8.20 Stage 4: additive, new endpoint. ``extra="forbid"``
    -- ``closed_at``/``closure_id``/``integrity_checksum`` are always
    backend-generated (see ``create_washer_resolution_closure``) and
    never accepted from a client, not even as an optional override."""

    model_config = ConfigDict(extra="forbid")

    closure_rationale: str
    closed_by: str


# ---------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.ResolutionNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except (svc.EvidenceIntegrityError, svc.ClosureIntegrityError) as exc:
        raise HTTPException(422, str(exc))
    except (
        svc.ClosureNotReadyError,
        svc.DuplicateClosureError,
        svc.BlockedRecordDecisionError,
    ) as exc:
        raise HTTPException(409, str(exc))
    except HTTPException:
        # Re-raise HTTPExceptions raised deliberately inside a route
        # handler (e.g. the evidence_type conversion below) unchanged
        # -- never let the generic handler below re-wrap a 4xx that
        # was already deliberately chosen as a 5xx.
        raise
    except Exception:
        # Anything else (e.g. a corrupted ledger file) is an internal
        # fault: log the real detail server-side, never leak a file
        # path or stack trace to the client. Matches
        # washer_resolution_decide_endpoint's own catch-all in
        # backend/app.py.
        log.exception("washer_resolution_closure API: unexpected error")
        raise HTTPException(500, "Beklenmeyen bir hata oluştu.")


# ---------------------------------------------------------------------
# Evidence endpoints
# ---------------------------------------------------------------------


@router.post("/api/library/washers/resolutions/{resolution_id}/evidence")
def create_resolution_evidence(
    resolution_id: str, x: ResolutionEvidenceCreate, u=Depends(user)
):
    try:
        evidence_type = we.EvidenceType(x.evidence_type)
    except ValueError:
        raise HTTPException(422, f"Geçersiz evidence_type: {x.evidence_type}")

    evidence = _handle(
        svc.record_resolution_evidence,
        resolution_id=resolution_id,
        evidence_type=evidence_type,
        title=x.title,
        description=x.description,
        source_reference=x.source_reference,
        created_by=x.created_by,
        source_locator=x.source_locator,
        source_url=x.source_url,
        source_standard=x.source_standard,
    )
    return {"evidence": evidence.model_dump(mode="json")}


@router.get("/api/library/washers/resolutions/{resolution_id}/evidence")
def list_resolution_evidence(resolution_id: str, u=Depends(user)):
    records = _handle(svc.resolution_evidence_for, resolution_id)
    return {"records": [record.model_dump(mode="json") for record in records]}


# ---------------------------------------------------------------------
# Closure readiness endpoint
# ---------------------------------------------------------------------


@router.get("/api/library/washers/resolutions/{resolution_id}/closure-readiness")
def get_resolution_closure_readiness(resolution_id: str, u=Depends(user)):
    readiness = _handle(svc.evaluate_closure_readiness, resolution_id)
    # ClosureReadiness is a plain dataclass, not a Pydantic model --
    # no .model_dump() available, and effective_status is a
    # WasherResolutionStatus enum member, never handed to the client
    # as-is (see module docstring).
    return {
        "resolution_id": readiness.resolution_id,
        "effective_status": readiness.effective_status.value,
        "is_ready": readiness.is_ready,
        "decision_id": readiness.decision_id,
        "verified_evidence_ids": list(readiness.verified_evidence_ids),
        "unverified_evidence_ids": list(readiness.unverified_evidence_ids),
        "rejected_evidence_ids": list(readiness.rejected_evidence_ids),
        "corrupted_evidence_ids": list(readiness.corrupted_evidence_ids),
        "blocking_reasons": list(readiness.blocking_reasons),
    }


# ---------------------------------------------------------------------
# Closure endpoints
# ---------------------------------------------------------------------


@router.post("/api/library/washers/resolutions/{resolution_id}/close")
def close_resolution_endpoint(
    resolution_id: str, x: ResolutionCloseRequest, u=Depends(user)
):
    closure = _handle(
        svc.close_resolution,
        resolution_id=resolution_id,
        closure_rationale=x.closure_rationale,
        closed_by=x.closed_by,
    )
    return {"closure": closure.model_dump(mode="json")}


@router.get("/api/library/washers/resolutions/{resolution_id}/closure")
def get_resolution_closure_endpoint(resolution_id: str, u=Depends(user)):
    closure = _handle(svc.get_resolution_closure, resolution_id)
    return {"closure": closure.model_dump(mode="json") if closure is not None else None}
