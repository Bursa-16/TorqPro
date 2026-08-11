"""Torque Recommendation Engine HTTP API (Faz v3.0.0-beta.1).

Thin FastAPI route over the existing, already-tested
``backend.torque_recommendation.engine.recommend_torque`` pipeline. No
engineering formula, validation rule, or explanation rule lives in
this module -- every one of those already lives inside
``backend.torque_recommendation`` and is covered by
``tests/torque_recommendation/*``; this module only does request
validation, authentication, the engine call itself, response
serialization, audit persistence, and domain-exception ->
``HTTPException`` mapping. Follows
``backend/api/routes/joints.py``'s / ``production_validation.py``'s /
``ai_gateway.py``'s established pattern (``APIRouter``,
``Depends(user)``, a single central ``_handle()`` exception-mapping
helper) without introducing a new convention.

This module does **not** import ``backend.ai_gateway`` -- see
``backend.torque_recommendation.engine``'s own module docstring for
the architecture rationale (the existing one-way dependency guard,
``tests/ai/test_dependency_direction.py``, permits exactly one
``backend.ai_gateway`` consumer, and expanding that allowlist is out
of beta.1's scope). Every field this route returns is fully
deterministic; ``provider_involved`` is therefore always persisted as
``False`` in this phase.

**Traceability (scope item 8, revised per architecture decision):**
after a successful ``recommend_torque()`` call, this route persists
the request/result into the existing, repository-wide ``audit_log``
table (``backend.torque_recommendation.audit.record_recommendation``
-- see that module's own docstring for why a dedicated table was
considered and rejected) using the same already-open connection
pattern ``backend/joints/service.py`` already uses (``backend.app.
conn``), and returns the new ``audit_log`` row id as ``trace_id`` in
the response. An optional ``X-Request-ID`` header is stored verbatim
in ``audit_log.request_id``, the same field every other authenticated
write endpoint in this repository already populates from that header
when supplied. A malformed request body never reaches this point
(rejected by Pydantic first); a domain validation failure inside
``analyze_joint`` (mapped to ``422`` below) is also never audited,
mirroring ``backend.ai_gateway.orchestrator.handle_query``'s own
documented rule that a failed calculation writes no partial audit
record.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Header

router = APIRouter(tags=["torque_recommendation"])

# `router` is assigned before these imports for the same reason
# backend/api/routes/joints.py already documents on its own
# equivalent import block: if backend.app ends up re-entering this
# module while it is still mid-import, the partially-initialized
# module already exposes a usable `router` attribute, which breaks a
# circular-import failure instead of propagating it.
from backend.api.dependencies import user  # noqa: E402
from backend.torque_recommendation import audit as trq_audit  # noqa: E402
from backend.torque_recommendation.engine import recommend_torque  # noqa: E402
from backend.torque_recommendation.models import TorqueRecommendationRequest  # noqa: E402
from backend.vdi2230_core import (  # noqa: E402
    CalculationDomainError as VdiCalculationDomainError,
    CalculationInputError as VdiCalculationInputError,
)


@router.post("/api/ai/torque-recommendation")
def torque_recommendation_endpoint(
    x: TorqueRecommendationRequest,
    u=Depends(user),
    x_request_id: str = Header(default="", alias="X-Request-ID"),
):
    # Orchestration only: no engineering formula, confidence rule or
    # explanation rule lives here -- see
    # backend.torque_recommendation.engine.recommend_torque, which
    # this route calls unchanged. Deterministic error mapping: a
    # *malformed* value the wired core rejects (e.g. a degenerate
    # torque coefficient) surfaces as its own vdi2230_core exception,
    # mapped here to 422 exactly like /api/engineering/joint-analysis
    # already does for the same underlying exceptions. A malformed
    # request body (wrong type, out-of-range field) is rejected by
    # Pydantic before this function runs.
    from backend.app import conn, now_iso

    try:
        result = recommend_torque(x)
    except (VdiCalculationInputError, VdiCalculationDomainError) as e:
        raise HTTPException(422, str(e))

    response = result.to_dict()

    with conn() as c:
        audit_id = trq_audit.record_recommendation(
            c,
            user_id=u["id"],
            request_dict=x.model_dump(),
            result_dict=response,
            created_at=now_iso(),
            request_id=x_request_id,
            provider_involved=False,
        )

    response["trace_id"] = str(audit_id)
    return response


__all__ = ["router"]
