"""TorqPro AI Gateway HTTP API (Faz v3.0.0-alpha.4 -- HTTP Exposure;
Faz v3.0.0-alpha.5 -- Persistent Audit, Explainability, Provider
Abstraction, ADR-0020).

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
``audit.InMemoryAuditSink``, ``store.SQLiteAuditSink``,
``providers.registry``, ``exceptions.*``) are used, exactly as
``tests/ai/test_orchestrator_boundary.py`` already exercises the
orchestrator itself. This file remains the *only* file in the
repository permitted to import ``backend.ai_gateway`` (see
``tests/ai/test_dependency_direction.py``'s ``SANCTIONED_ENTRY_POINTS``)
-- this phase adds new imports from that package, but does not add a
second consumer.

**Default model provider for POST /api/ai/query (unchanged from
alpha.4, deliberate safety decision):** no concrete, network-calling
``AIModelClient`` is wired as this route's default in this phase
either. :func:`get_model_client` still returns
:class:`_UnavailableModelClient`, whose ``complete()`` always raises,
normalized by the orchestrator into ``ModelUnavailableError`` (ADR-0017
Karar 9, case 1) and mapped below to ``503``. This is a deliberate
scope boundary for this phase: ADR-0020 adds a *listable* provider
registry (``GET /api/ai/providers``, see below) containing the new
offline-safe ``DeterministicModelClient``, but does **not** change
which client ``POST /api/ai/query`` actually uses by default --
rewiring that default is a separate, out-of-scope decision left to a
later phase, so the already-tested alpha.4 "unavailable by default"
behavior (``tests/ai/test_http_route.py``) is left completely
unchanged. Tests override :func:`get_model_client` (FastAPI
``dependency_overrides``) with ``backend.ai_gateway.llm_client.
FakeModelClient`` (or, from this phase on, with a registry-selected
``DeterministicModelClient``) to exercise the complete HTTP pipeline.

**Audit sink (ADR-0020, superseding the alpha.4 in-memory-only note
below):** ``handle_query`` still requires an ``AuditSink`` argument by
contract -- this route still satisfies that interface with a
request-scoped ``InMemoryAuditSink()``, so ``handle_query``'s own,
already-tested contract is completely unchanged. What is new in this
phase: *after* ``handle_query`` returns (or raises
``ModelUnavailableError``), this route additionally persists the
interaction into ``ai_audit_records`` (``backend.ai_gateway.store``)
via :class:`~backend.ai_gateway.store.SQLiteAuditSink`, using the same
already-open connection -- adding ``latency_ms``, the requesting
user's ``role``, an optional ``X-Request-ID`` correlation id, and a
hash of the response text, none of which ``AIInteractionRecord``
itself carries. Raw prompt/response text and any secret/API key are
never written to this table (see ``backend.ai_gateway.store`` module
docstring, Privacy).

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

**New in this phase (ADR-0020):**

- ``GET /api/ai/providers`` (``Depends(user)``, read-only): lists every
  registered provider (``backend.ai_gateway.providers.registry.
  build_default_registry()``) -- name, model identifier, availability.
  No secret/credential value is ever included.
- ``GET /api/ai/audit`` / ``GET /api/ai/audit/{audit_id}``
  (``Depends(admin)``, matching ``backend.api.dependencies.admin``'s
  existing role-gate pattern already used throughout ``backend/app.py``):
  read the persisted, hash-only audit trail. 404 for an unknown
  ``audit_id`` (never a 500 or a silently-empty 200).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
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
from backend.ai_gateway.providers.registry import build_default_registry  # noqa: E402
from backend.ai_gateway.store import (  # noqa: E402
    PersistedAuditRecord,
    SQLiteAuditSink,
    get_audit_record,
    list_audit_records,
    migrate as migrate_persistent_audit,
)
from backend.api.dependencies import admin, user  # noqa: E402
from backend.app import conn, now_iso  # noqa: E402

#: Fixed, always-read action name passed to ``ensure_read_only_action``
#: (see module docstring, "Read-only enforcement"). Never derived from
#: request input.
_QUERY_ACTION = "query"

#: Explicit, minimal request-validation cap -- not a domain rule, just
#: a sane upper bound so this route never forwards an unbounded string
#: into the pipeline. Chosen generously above any realistic question.
_MAX_QUERY_TEXT_LENGTH = 4000

#: ADR-0020: the one, fixed provider registry this route lists via
#: ``GET /api/ai/providers``. Built once at import time -- every
#: registered ``AIModelClient`` (only ``DeterministicModelClient`` in
#: this phase) is itself stateless/side-effect-free to construct, so a
#: module-level singleton is safe and avoids rebuilding it per request.
_PROVIDER_REGISTRY = build_default_registry()


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


def _serialize_persisted_record(record: PersistedAuditRecord) -> Dict[str, Any]:
    """Render a :class:`~backend.ai_gateway.store.PersistedAuditRecord`
    field-for-field into a plain JSON body. Only hashes/identifiers/
    structured metadata ever appear here -- no raw prompt/response text,
    no secret, no credential (see ``backend.ai_gateway.store`` module
    docstring, Privacy)."""
    return {
        "audit_id": record.id,
        "user_id": record.user_id,
        "user_role": record.user_role,
        "correlation_id": record.correlation_id,
        "created_at": record.created_at,
        "query_text_hash": record.query_text_hash,
        "response_text_hash": record.response_text_hash,
        "model_name": record.model_name,
        "had_sufficient_evidence": record.had_sufficient_evidence,
        "evidence_status": record.evidence_status,
        "result_label": record.result_label,
        "evidence_source_ids": [list(pair) for pair in record.evidence_source_ids],
        "calculation_formula_ids": list(record.calculation_formula_ids),
        "retrieval_source_types_queried": list(record.retrieval_source_types_queried),
        "evidence_count_by_source_type": [
            list(pair) for pair in record.evidence_count_by_source_type
        ],
        "latency_ms": record.latency_ms,
        "success": record.success,
        "error_category": record.error_category,
    }


def _run_query(
    user_context: UserContext,
    query_text: str,
    model_client: AIModelClient,
    correlation_id: Optional[str],
) -> Dict[str, Any]:
    ensure_read_only_action(_QUERY_ACTION)
    # `capture_sink` is what `handle_query` itself writes to -- passing
    # it through unchanged (instead of `SQLiteAuditSink` directly) keeps
    # the orchestrator's own, already-tested `AuditSink` contract
    # (`tests/ai/test_orchestrator_boundary.py`) completely untouched.
    # This route reads the one entry it captured back out afterwards and
    # persists it itself, alongside the extra fields (latency/role/
    # correlation id/response hash) that `AIInteractionRecord` does not
    # carry (see module docstring, "Audit sink").
    capture_sink = InMemoryAuditSink()
    query_text_hash = hashlib.sha256(query_text.encode("utf-8")).hexdigest()
    started_at = time.perf_counter()
    with conn() as c:
        persistent_sink = SQLiteAuditSink(c)
        try:
            answer = handle_query(
                user=user_context,
                query_text=query_text,
                conn=c,
                model_client=model_client,
                audit_sink=capture_sink,
                query_text_hash=query_text_hash,
                created_at=now_iso(),
            )
        except ModelUnavailableError as exc:
            # ADR-0020, "provider failure audit": handle_query raises
            # before ever calling capture_sink.record(), so without this
            # branch a provider failure would leave zero trace anywhere
            # -- neither in-memory nor persisted. This is the one,
            # deliberately narrow failure path this phase audits (a
            # genuine AI-interaction attempt that failed); permission
            # denials are not audited here (see final report).
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            persistent_sink.record_failure(
                user_id=user_context.user_id,
                query_text_hash=query_text_hash,
                model_name=getattr(model_client, "name", None),
                created_at=now_iso(),
                error_category=type(exc).__name__,
                latency_ms=latency_ms,
                user_role=user_context.role,
                correlation_id=correlation_id,
            )
            raise

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        response_text_hash = hashlib.sha256(answer.text.encode("utf-8")).hexdigest()
        captured_entries = capture_sink.all_entries()
        if captured_entries:
            persistent_sink.record_with_latency(
                captured_entries[-1],
                latency_ms=latency_ms,
                user_role=user_context.role,
                correlation_id=correlation_id,
                response_text_hash=response_text_hash,
            )

    return _serialize_answer(answer)


@router.post("/api/ai/query")
def ai_query(
    body: AIQueryRequest,
    u: dict = Depends(user),
    model_client: AIModelClient = Depends(get_model_client),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
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

    return _handle(_run_query, user_context, query_text, model_client, x_request_id)


@router.get("/api/ai/providers")
def ai_providers(u: dict = Depends(user)):
    """ADR-0020: list every registered ``AIModelClient`` provider.

    Read-only, ``Depends(user)`` (matching every other read-only AI
    gateway surface) -- listing available providers is not itself a
    privileged operation. Never includes a secret/credential value:
    ``ProviderInfo`` (``backend.ai_gateway.providers.registry``)
    structurally carries only ``name``/``model_identifier``/
    ``available``.
    """
    return {
        "providers": [
            {
                "name": info.name,
                "model_identifier": info.model_identifier,
                "available": info.available,
            }
            for info in _PROVIDER_REGISTRY.list_providers()
        ]
    }


@router.get("/api/ai/audit")
def ai_audit_list(
    limit: int = Query(default=50, ge=1, le=500),
    u: dict = Depends(admin),
):
    """ADR-0020: most-recent-first page of the persisted AI audit
    trail. ``Depends(admin)`` -- matches ``backend.api.dependencies.
    admin``'s existing role-gate pattern already used throughout
    ``backend/app.py`` for every other admin-only listing endpoint.

    ``limit`` bounds/default live here, not in
    ``backend.ai_gateway.store`` (see that module's
    ``list_audit_records`` docstring): this route module is outside
    ``backend/ai_gateway/`` and therefore outside the scope of
    ``tests/ai/test_safety_and_validation.py``'s numeric-literal guard,
    so the ordinary FastAPI ``Query(ge=..., le=...)`` validation
    convention (already used for other query parameters throughout
    ``backend/api/routes/*``) is the natural place for this bound to
    live -- ``backend.ai_gateway.store.list_audit_records`` itself
    applies whatever already-validated ``limit`` it is given, with no
    clamping of its own.
    """
    with conn() as c:
        records = list_audit_records(c, limit=limit)
    return {"records": [_serialize_persisted_record(r) for r in records]}


@router.get("/api/ai/audit/{audit_id}")
def ai_audit_detail(audit_id: int, u: dict = Depends(admin)):
    """ADR-0020: single persisted audit record by id. 404 (never a
    500 or a silently-empty 200) when ``audit_id`` does not exist --
    matches ``backend/api/routes/question_bank.py``'s own
    ``_require_question_exists``-style 404 convention for an unknown
    id."""
    with conn() as c:
        record = get_audit_record(c, audit_id)
    if record is None:
        raise HTTPException(404, f"audit_id {audit_id} bulunamadı")
    return _serialize_persisted_record(record)


__all__ = [
    "router",
    "get_model_client",
    "AIQueryRequest",
    "migrate_persistent_audit",
]
