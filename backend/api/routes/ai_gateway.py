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

**New in this phase (Faz v3.0.0-beta.2, Engineering Reasoning Engine):**

- ``POST /api/ai/engineering-reasoning`` (``Depends(user)``): the
  Stage 0-approved reasoning endpoint. Thin orchestration only, same
  discipline as every other route in this file -- no reasoning rule
  lives here; every one of those lives in
  ``backend.ai_gateway.reasoning`` and is covered by
  ``tests/ai/reasoning/*``. This route only does trace lookup +
  ownership authorization (raw SQL, deliberately not going through
  ``backend.torque_recommendation.audit.get_recommendation_audit``
  for *this* step -- see ``_fetch_trace_owner``'s own docstring for
  why), the ``run_reasoning``/``attempt_ai_explanation`` calls
  themselves, persistent-audit-trail recording (reusing
  ``ai_audit_records`` -- no new table, no new column), and
  domain-exception -> ``HTTPException`` mapping. This is still the
  *only* file in the repository permitted to import
  ``backend.ai_gateway`` -- adding
  ``backend.ai_gateway.reasoning.*`` imports here does not add a
  second consumer (see ``backend.ai_gateway.reasoning``'s own
  ``__init__.py`` docstring for the architecture rationale).

  This route never re-runs
  ``backend.torque_recommendation.engine.recommend_torque`` -- it only
  reads an already-persisted Beta.1 result by ``trace_id``. A request
  naming an unknown ``trace_id`` -> ``404``; a ``trace_id`` that exists
  but belongs to a different, non-admin user -> ``403`` (ownership
  check happens *before* any reasoning is attempted, and before the
  potentially-corrupt ``detail`` JSON is even parsed). AI wording
  (``include_ai_wording=True``) failing/being unavailable/naming an
  unregistered provider never affects the HTTP status or the
  deterministic fields of the response -- it only leaves
  ``ai_explanation``/``ai_explanation_provider`` as ``None`` (see
  ``backend.ai_gateway.reasoning.wording`` module docstring).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import replace as _replace
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
from backend.ai_gateway.audit import AIInteractionRecord, InMemoryAuditSink  # noqa: E402
from backend.ai_gateway.composer import ComposedAnswer  # noqa: E402
from backend.ai_gateway.evidence_checker import EvidenceStatus  # noqa: E402
from backend.ai_gateway.exceptions import (  # noqa: E402
    AIGatewayConfigurationError,
    ModelUnavailableError,
    PermissionDeniedError,
    ProviderNotFoundError,
)
from backend.ai_gateway.llm_client import AIModelClient, ModelResponse, PromptContext  # noqa: E402
from backend.ai_gateway.orchestrator import handle_query  # noqa: E402
from backend.ai_gateway.permission import UserContext, ensure_read_only_action  # noqa: E402
from backend.ai_gateway.providers.registry import build_default_registry  # noqa: E402
from backend.ai_gateway.reasoning import engine as reasoning_engine  # noqa: E402
from backend.ai_gateway.reasoning import evidence_adapter as reasoning_evidence_adapter  # noqa
from backend.ai_gateway.reasoning import wording as reasoning_wording  # noqa: E402
from backend.ai_gateway.reasoning.models import ReasoningResult  # noqa: E402
from backend.ai_gateway.store import (  # noqa: E402
    PersistedAuditRecord,
    SQLiteAuditSink,
    get_audit_record,
    list_audit_records,
    migrate as migrate_persistent_audit,
)
from backend.api.dependencies import admin, user  # noqa: E402
from backend.app import conn, now_iso  # noqa: E402
from backend.torque_recommendation import audit as trq_audit  # noqa: E402

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
    except HTTPException:
        # Faz v3.0.0-beta.2 addition: a wrapped function (specifically
        # ``_run_engineering_reasoning``) may itself raise a deliberate,
        # already-correctly-coded ``HTTPException`` (404 unknown
        # trace_id, 403 cross-user access) -- this must pass through
        # unchanged rather than falling into the generic 500 branch
        # below. No existing caller of ``_handle`` ever raised
        # ``HTTPException`` from within its wrapped function before
        # this phase, so this branch is purely additive and changes no
        # existing route's behaviour.
        raise
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


# ---------------------------------------------------------------------
# Faz v3.0.0-beta.2: POST /api/ai/engineering-reasoning
# ---------------------------------------------------------------------


class EngineeringReasoningRequest(BaseModel):
    """Request body for ``POST /api/ai/engineering-reasoning``.

    ``trace_id`` (an existing ``audit_log.id`` created by
    ``POST /api/ai/torque-recommendation``) is the *only* required
    field -- the Stage 0-approved design deliberately exposes no raw
    engineering-parameter input path here, so this endpoint can never
    be used to re-run or duplicate
    ``backend.torque_recommendation.engine.recommend_torque``.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: int = Field(..., gt=0)
    include_ai_wording: bool = False
    provider_name: Optional[str] = None


def _fetch_trace_owner(c, trace_id: int) -> Optional[int]:
    """Raw, JSON-parsing-free existence + ownership lookup for Beta.1
    audit row ``trace_id``. Returns ``None`` if the row does not exist
    or is not a ``torque_recommendation`` row.

    Deliberately reads only the ``user_id`` column -- never
    ``detail`` -- so a corrupt/unparseable stored JSON payload can
    never block this authorization check from completing correctly.
    This is why authorization always runs *before*
    ``_fetch_reasoning_record`` (below) is even attempted: a caller
    must never learn anything about another user's trace (not even
    "this row's JSON happens to be corrupt") before their own
    ownership has been confirmed.
    """
    row = c.execute(
        "SELECT user_id FROM audit_log WHERE id=? AND action=?",
        (trace_id, trq_audit.ACTION),
    ).fetchone()
    return int(row["user_id"]) if row is not None else None


def _fetch_reasoning_record(c, trace_id: int) -> Optional[Dict[str, Any]]:
    """Best-effort structured fetch of the Beta.1 result via
    ``backend.torque_recommendation.audit.get_recommendation_audit``
    (reused unchanged -- see that function's own docstring).

    Returns ``None`` -- never raises -- when the stored ``detail`` JSON
    is missing an expected key or is not valid JSON at all
    (``json.JSONDecodeError`` is a ``ValueError`` subclass).
    ``backend.ai_gateway.reasoning.engine.run_reasoning`` treats a
    ``None`` record as ``ReasoningState.INSUFFICIENT_EVIDENCE``
    (fail-closed), never as a ``500`` -- this is the "incomplete/
    corrupt stored evidence" scenario named in the approved Stage 0
    API contract.
    """
    try:
        return trq_audit.get_recommendation_audit(c, trace_id)
    except (ValueError, KeyError, TypeError):
        return None


def _resolve_wording_provider(provider_name: Optional[str]):
    """Resolve an ``AIModelClient`` from the *same* module-level
    ``_PROVIDER_REGISTRY`` this file already builds for
    ``GET /api/ai/providers`` -- no second registry is constructed
    anywhere in this phase (Stage 0 constraint: "avoid duplicate
    registries").

    Returns ``None`` -- never raises -- for an unknown ``provider_name``
    or when no registry lookup was requested at all;
    ``backend.ai_gateway.reasoning.wording.attempt_ai_explanation``
    already treats a ``None`` client as "skip AI wording", so an
    unknown provider name degrades to the same safe, deterministic-
    result-unaffected outcome as a provider that raised at call time.
    """
    name = provider_name if provider_name is not None else "deterministic"
    try:
        return _PROVIDER_REGISTRY.get(name)
    except ProviderNotFoundError:
        return None


def _serialize_reasoning_result(result: ReasoningResult) -> Dict[str, Any]:
    """Field-for-field render of ``ReasoningResult`` -- no field is
    renamed, dropped, or reinterpreted (mirrors
    ``_serialize_answer``'s own discipline above)."""
    return result.to_dict()


def _run_engineering_reasoning(
    body: EngineeringReasoningRequest,
    u: Dict[str, Any],
    x_request_id: Optional[str],
) -> Dict[str, Any]:
    trace_id = body.trace_id
    started_at = time.perf_counter()

    with conn() as c:
        owner_id = _fetch_trace_owner(c, trace_id)
        if owner_id is None:
            raise HTTPException(404, f"trace_id {trace_id} bulunamadı")
        if owner_id != u["id"] and u["role"] != "admin":
            raise HTTPException(403, "Bu trace_id başka bir kullanıcıya ait")

        record = _fetch_reasoning_record(c, trace_id)
        user_context = UserContext(
            user_id=u["id"], role=u["role"], is_active=bool(u["is_active"])
        )

        # Deterministic reasoning first, always -- see
        # backend.ai_gateway.reasoning.engine module docstring:
        # run_reasoning never imports/calls an AIModelClient, so this
        # call's outcome is unaffected by anything below it.
        reasoning_result = reasoning_engine.run_reasoning(trace_id, record, user=user_context)

        calculation_response = (
            reasoning_evidence_adapter.to_calculation_response(record)
            if record is not None
            else None
        )

        if body.include_ai_wording:
            model_client = _resolve_wording_provider(body.provider_name)
            ai_text, ai_provider = reasoning_wording.attempt_ai_explanation(
                reasoning_result,
                calculation_response=calculation_response,
                model_client=model_client,
                user=user_context,
            )
            reasoning_result = reasoning_engine.with_ai_explanation(
                reasoning_result, ai_explanation=ai_text, ai_explanation_provider=ai_provider
            )

        # Audit persistence -- reuses the existing ai_audit_records
        # table unchanged (Stage 0 constraint: no new table, no new
        # column). The Beta.1 source relationship is represented via
        # the existing (source_type, source_id) evidence-id pairing
        # already used for Question Bank sources, per the approved
        # Stage 0 decision: ("torque_recommendation", str(trace_id)).
        calculation_formula_ids = (
            tuple(result.formula_id for result in calculation_response.results)
            if calculation_response is not None
            else ()
        )
        query_text_hash = hashlib.sha256(
            f"engineering_reasoning:trace_id={trace_id}".encode("utf-8")
        ).hexdigest()
        response_text_hash = (
            hashlib.sha256(reasoning_result.ai_explanation.encode("utf-8")).hexdigest()
            if reasoning_result.ai_explanation
            else None
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)

        interaction_record = AIInteractionRecord(
            user_id=u["id"],
            query_text_hash=query_text_hash,
            evidence_source_ids=(("torque_recommendation", str(trace_id)),),
            calculation_formula_ids=calculation_formula_ids,
            model_name=reasoning_result.ai_explanation_provider,
            had_sufficient_evidence=reasoning_result.evidence_status != EvidenceStatus.FAIL,
            created_at=now_iso(),
            retrieval_source_types_queried=("torque_recommendation",),
            evidence_count_by_source_type=(
                ("torque_recommendation", len(calculation_formula_ids)),
            ),
            evidence_status=reasoning_result.evidence_status,
            result_label=reasoning_result.result_label,
        )
        persistent_sink = SQLiteAuditSink(c)
        reasoning_trace_id = persistent_sink.record_with_latency(
            interaction_record,
            latency_ms=latency_ms,
            user_role=u["role"],
            correlation_id=x_request_id,
            response_text_hash=response_text_hash,
        )

    reasoning_result = _replace(reasoning_result, reasoning_trace_id=reasoning_trace_id)
    return _serialize_reasoning_result(reasoning_result)


@router.post("/api/ai/engineering-reasoning")
def engineering_reasoning_endpoint(
    body: EngineeringReasoningRequest,
    u: dict = Depends(user),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
):
    return _handle(_run_engineering_reasoning, body, u, x_request_id)


__all__ = [
    "router",
    "get_model_client",
    "AIQueryRequest",
    "EngineeringReasoningRequest",
    "migrate_persistent_audit",
]
