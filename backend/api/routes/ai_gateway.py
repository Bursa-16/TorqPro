"""TorqPro AI Gateway HTTP API (Faz v3.0.0-alpha.4 -- HTTP Exposure).

Thin FastAPI route over the existing, already-tested
``backend.ai_gateway.orchestrator.handle_query`` pipeline (Faz
v3.0.0-alpha.1/alpha.2/alpha.3, ADR-0017/ADR-0018/ADR-0019). No
permission rule, retrieval rule, evidence rule, or safety/validation
rule lives in this module -- every one of those already lives inside
``backend.ai_gateway`` and is covered by ``tests/ai/*``; this module
only does request validation, authentication, DB-connection/audit-sink
plumbing, the ``handle_query`` call itself, response serialization,
and domain-exception -> ``HTTPException`` mapping. Follows
``backend/api/routes/joints.py``'s / ``production_validation.py``'s /
``question_bank.py``'s established pattern (``APIRouter``,
``Depends(user)``, a single central ``_handle()`` exception-mapping
helper) without introducing a new convention.

Nothing inside ``backend/ai_gateway/`` is imported for modification or
reimplementation here -- only its public, already-frozen contracts
(``orchestrator.handle_query``, ``permission.UserContext``/
``ensure_read_only_action``, ``llm_client.AIModelClient``,
``audit.InMemoryAuditSink``, ``exceptions.*``) are used, exactly as
``tests/ai/test_orchestrator_boundary.py`` already exercises them.

**Default model provider (deliberate safety decision):** no concrete,
network-calling ``AIModelClient`` exists anywhere in TorqPro yet (see
``backend.ai_gateway.llm_client`` module docstring -- a real provider
under ``backend/ai_gateway/providers/*`` is explicitly deferred to a
later, separately-approved phase). This route's default runtime
dependency, :func:`get_model_client`, therefore returns
:class:`_UnavailableModelClient`, a route-local placeholder whose
``complete()`` always raises. It is never special-cased: the existing
orchestrator already normalizes *any* ``AIModelClient.complete()``
failure into ``ModelUnavailableError`` (ADR-0017 Karar 9, case 1), so
the "no provider configured" state is surfaced through the exact same,
already-tested path a genuine network failure would use, mapped below
to ``503``. This route never substitutes a fake/generated answer for a
missing real provider. Tests override :func:`get_model_client` (FastAPI
``dependency_overrides``) with ``backend.ai_gateway.llm_client.
FakeModelClient`` to exercise the complete HTTP pipeline -- production
traffic never reaches ``FakeModelClient``.

**Audit sink:** ``handle_query`` requires an ``AuditSink`` argument by
contract. SQLite persistence for the audit trail
(``ai_interactions``/``ai_evidence_links`` tables) is explicitly out of
scope for this phase (see ``backend.ai_gateway.audit`` module
docstring: deferred "once this in-process pipeline is proven"). This
route satisfies the interface with a fresh, request-scoped
``InMemoryAuditSink()`` -- recorded for the duration of the call only,
discarded after the response is returned, and never written to any
table. No new persistence, no new schema, no ``SCHEMA_VERSION`` bump.

**Read-only enforcement:** this route accepts no client-supplied
``action`` parameter (that would be new RBAC-policy surface, out of
scope). It always invokes
``backend.ai_gateway.permission.ensure_read_only_action("query")``
before calling ``handle_query`` -- a fixed, always-read value -- so the
existing write/approval-action guard is genuinely exercised on every
request rather than left unreachable dead code.

**Request/response contract:** ``AIQueryRequest`` carries exactly one
field, ``query_text`` (required, non-empty, length-capped), matching
the "minimal, explicit" validation this phase calls for. The response
mirrors ``backend.ai_gateway.composer.ComposedAnswer`` field-for-field
(``text``, ``evidence``, ``calculation_result``,
``insufficient_evidence``, ``model_name``, ``citations``,
``result_label``, ``validation_required``) -- no new confidence/status
vocabulary is invented here. ``calculation_result`` is always ``None``
in this phase's response: this route never passes
``calculation_provider``/``calculation_request`` into ``handle_query``
(wiring deterministic-calculation requests through HTTP is out of
scope for this narrow phase), and ``handle_query`` itself only
populates ``calculation_result`` when both are supplied.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["ai_gateway"])

# `router` is assigned before these imports for the same reason
# backend/api/routes/joints.py and backend/api/routes/production_validation.py
# already document on their own equivalent import blocks: if backend.app
# ends up re-entering this module while it is still mid-import, the
# partially-initialized module already exposes a usable `router`
# attribute, which breaks a circular-import failure instead of
# propagating it.
from backend.ai_gateway.audit import InMemoryAuditSink  # noqa: E402
from backend.ai_gateway.composer import ComposedAnswer  # noqa: E402
from backend.ai_gateway.exceptions import (  # noqa: E402
    AIGatewayConfigurationError,
    ModelUnavailableError,
    PermissionDeniedError,
)
from backend.ai_gateway.llm_client import AIModelClient, ModelResponse, PromptContext  # noqa: E402
from backend.ai_gateway.orchestrator import handle_query  # noqa: E402
from backend.ai_gateway.permission import UserContext, ensure_read_only_action  # noqa: E402
from backend.api.dependencies import user  # noqa: E402
from backend.app import conn, now_iso  # noqa: E402

#: Fixed, always-read action name passed to ``ensure_read_only_action``
#: (see module docstring, "Read-only enforcement"). Never derived from
#: request input.
_QUERY_ACTION = "query"

#: Explicit, minimal request-validation cap -- not a domain rule, just
#: a sane upper bound so this route never forwards an unbounded string
#: into the pipeline. Chosen generously above any realistic question.
_MAX_QUERY_TEXT_LENGTH = 4000


class _UnavailableModelClient(AIModelClient):
    """Route-level default runtime ``AIModelClient`` (see module
    docstring, "Default model provider").

    Always fails -- deliberately. No real, network-calling
    ``AIModelClient`` exists in this phase; this placeholder makes that
    state explicit and lets ``handle_query``'s existing
    ``ModelUnavailableError`` normalization (ADR-0017 Karar 9, case 1)
    do the actual error handling, rather than this route special-casing
    "no provider" separately from "provider failed".
    """

    name = "unavailable"

    def complete(self, prompt_context: PromptContext) -> ModelResponse:
        raise RuntimeError(
            "No AI model provider is configured for the TorqPro AI Gateway "
            "(v3.0.0-alpha.4: HTTP exposure only, no real AIModelClient yet)."
        )


def get_model_client() -> AIModelClient:
    """FastAPI dependency seam for the ``AIModelClient`` used by this
    route. Returns :class:`_UnavailableModelClient` by default.

    Tests override this dependency (``app.dependency_overrides``) with
    ``backend.ai_gateway.llm_client.FakeModelClient`` to exercise the
    full HTTP pipeline without a real model. Production traffic always
    receives the default, always-failing placeholder until a real
    provider is introduced in a later, separately-approved phase.
    """
    return _UnavailableModelClient()


class AIQueryRequest(BaseModel):
    """Minimal request body: exactly one required field.

    ``extra="forbid"`` rejects unknown fields explicitly (FastAPI's
    default 422) rather than silently ignoring them. Emptiness/length
    are checked in the route handler itself (not via Pydantic
    constraints) so this phase's own ``400`` mapping (see module
    docstring) applies deterministically instead of FastAPI's default
    ``422`` validation-error shape.
    """

    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(...)


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PermissionDeniedError as exc:
        raise HTTPException(403, str(exc))
    except ModelUnavailableError as exc:
        raise HTTPException(503, str(exc))
    except AIGatewayConfigurationError:
        # A caller/wiring mistake, not a runtime provider failure (see
        # backend.ai_gateway.exceptions.AIGatewayConfigurationError's
        # own docstring) -- a server-side misconfiguration, never the
        # requesting user's fault, so 500 rather than 503/403. Message
        # is generic; the internal exception detail is not echoed to
        # the client (see the bare `except Exception` branch below for
        # the same non-leaking policy).
        raise HTTPException(500, "AI gateway is misconfigured.")
    except Exception:
        # Deliberately broad and deliberately last: any failure mode
        # not already named above (a bug, an unexpected exception type
        # from a collaborator) is mapped to a generic 500 with no
        # exception detail echoed to the client -- never left to leak
        # through a framework default, and never silently turned into
        # a 200.
        raise HTTPException(500, "An unexpected error occurred in the AI gateway.")


def _serialize_answer(answer: ComposedAnswer) -> Dict[str, Any]:
    """Render a ``ComposedAnswer`` field-for-field into a plain JSON
    body (see module docstring, "Request/response contract"). No field
    is renamed, dropped, or reinterpreted; no new field is invented."""
    return {
        "text": answer.text,
        "insufficient_evidence": answer.insufficient_evidence,
        "result_label": answer.result_label,
        "validation_required": answer.validation_required,
        "model_name": answer.model_name,
        "citations": list(answer.citations),
        "evidence": [
            {
                "source_type": source.source_type,
                "source_id": source.source_id,
                "content_version": source.content_version,
                "title_tr": source.title_tr,
                "title_en": source.title_en,
                "body_tr": source.body_tr,
                "body_en": source.body_en,
                "standard_name": source.standard_name,
                "standard_clause": source.standard_clause,
                "source_kind": source.source_kind,
                "category": source.category,
                "difficulty": source.difficulty,
                "tags": list(source.tags),
                "traceability_level": source.traceability_level,
            }
            for source in answer.evidence
        ],
        # Always None in this phase -- see module docstring,
        # "Request/response contract". Read from `answer` (not
        # hardcoded) so this stays correct if a later phase wires
        # calculation_provider/calculation_request through.
        "calculation_result": answer.calculation_result,
    }


def _run_query(
    user_context: UserContext, query_text: str, model_client: AIModelClient
) -> Dict[str, Any]:
    ensure_read_only_action(_QUERY_ACTION)
    audit_sink = InMemoryAuditSink()
    query_text_hash = hashlib.sha256(query_text.encode("utf-8")).hexdigest()
    with conn() as c:
        answer = handle_query(
            user=user_context,
            query_text=query_text,
            conn=c,
            model_client=model_client,
            audit_sink=audit_sink,
            query_text_hash=query_text_hash,
            created_at=now_iso(),
        )
    return _serialize_answer(answer)


@router.post("/api/ai/query")
def ai_query(
    body: AIQueryRequest,
    u: dict = Depends(user),
    model_client: AIModelClient = Depends(get_model_client),
):
    query_text = body.query_text.strip()
    if not query_text:
        raise HTTPException(400, "query_text must not be empty.")
    if len(query_text) > _MAX_QUERY_TEXT_LENGTH:
        raise HTTPException(
            400, f"query_text must not exceed {_MAX_QUERY_TEXT_LENGTH} characters."
        )

    user_context = UserContext(
        user_id=u["id"], role=u["role"], is_active=bool(u["is_active"])
    )

    return _handle(_run_query, user_context, query_text, model_client)


__all__ = ["router", "get_model_client", "AIQueryRequest"]
