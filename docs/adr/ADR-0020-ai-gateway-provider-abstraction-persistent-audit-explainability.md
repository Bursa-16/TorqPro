# ADR-0020: AI Gateway Provider Abstraction, Persistent Audit, Explainability (v3.0.0-alpha.5)

**Status:** Accepted
**Date:** 2026-08-09
**Phase:** v3.0.0-alpha.5

## Context

`backend/ai_gateway` (v3.0.0-alpha.1 through alpha.4) established the
AI layer's orchestration pipeline, retrieval/grounding, safety/
validation, and a minimal HTTP surface (`POST /api/ai/query`), but
left three things explicitly deferred, per those phases' own module
docstrings: a real, selectable `AIModelClient` provider abstraction;
SQLite persistence for the audit trail (in-memory only until then);
and any dedicated explainability design work. This phase closes those
three, narrowly, without touching the Torque Recommendation Engine
(v3.0.0-beta.1) or Engineering Reasoning Engine (v3.0.0-beta.2) scope.

Numbering note: this file is `ADR-0020` rather than the next
sequential-looking number because `ADR-0017`/`ADR-0018`/`ADR-0019`
are already referenced throughout `backend/ai_gateway`'s existing
module docstrings as the accepted decisions behind v3.0.0-alpha.1/
alpha.2/alpha.3, respectively — those files were never committed to
`docs/adr/` (a pre-existing documentation gap this phase does not
backfill, out of scope). `ADR-0020` is the next number genuinely free
for a new decision, consistent with what the pre-existing code already
assumed.

## Decisions

**1. Provider abstraction stays a metadata layer over the existing
`AIModelClient`, never a second interface.** `backend.ai_gateway.
llm_client.AIModelClient`/`ModelResponse` remain the sole request/
response contract. `backend/ai_gateway/providers/registry.py` adds
only an explicit, deterministic name -> `AIModelClient` lookup
(`ProviderRegistry`) plus a read-only `ProviderInfo` descriptor;
`AIModelClient` itself gains two small, additive, defaulted hooks
(`model_identifier`, `is_available()`). No class named `Provider` is
introduced anywhere in `backend.ai_gateway`, to avoid any naming/
conceptual collision with `backend.calculation_engine.provider.
Provider` (an unrelated, pre-existing concept for the deterministic
calculation engine). Only one concrete provider is registered by
default in this phase — `providers.deterministic.
DeterministicModelClient`, offline-safe, no network call. Real
network-calling providers (OpenAI/Claude/Ollama) remain deferred;
adding one later means one new module plus one `.register(...)` call,
with no change required to `orchestrator`/`composer`/`audit`.

**2. Persistent audit is wired into `backend/app.py`'s migration
through the already-sanctioned HTTP route module, never directly.**
`tests/ai/test_dependency_direction.py` enforces, by AST inspection,
that `backend/app.py` (and every other existing package) may never
import `backend.ai_gateway` directly — the sole sanctioned exception
is `backend/api/routes/ai_gateway.py`. The new persistence module
(`backend/ai_gateway/store.py`, table `ai_audit_records`, additive/
idempotent `CREATE TABLE IF NOT EXISTS`/`CREATE INDEX IF NOT EXISTS`,
matching `backend.question_bank.store.migrate`'s established pattern)
is therefore migrated via a two-line hook in `backend/app.py`'s
existing `migrate()` that imports `migrate_persistent_audit` from
`backend.api.routes.ai_gateway` — the sanctioned module — rather than
from `backend.ai_gateway.store` directly. `POST /api/ai/query` persists
both successful and provider-failure interactions (hash/metadata only:
`query_text_hash`, `response_text_hash`, `latency_ms`, requesting
user's `role`, an optional `X-Request-ID` correlation id — never raw
prompt/response text, never a secret/token/credential). The
orchestrator's own already-tested `AuditSink` contract
(`InMemoryAuditSink`, exercised by `tests/ai/
test_orchestrator_boundary.py`) is left completely unchanged: the route
layer reads the one entry `handle_query` captured and re-persists it
itself with the additional fields `AIInteractionRecord` does not carry.

**3. Explainability reuses the existing `ComposedAnswer` structure
verbatim; no new surface is introduced.** `citations`/`result_label`/
`evidence_status`/`validation_required` (already produced by
`backend.ai_gateway.composer`) already satisfy this phase's
explainability requirement (decision summary, evidence/reference
identifiers, warnings/limitations, confidence/traceability metadata).
No internal reasoning or chain-of-thought field is added anywhere, on
the HTTP response or the persisted audit record.

**4. The audit-listing `limit` bound lives in the HTTP route layer,
outside `backend/ai_gateway/`, never as a literal inside it.**
`tests/ai/test_safety_and_validation.py::
test_no_engineering_numeric_literal_anywhere_in_ai_gateway` bans every
bare int/float literal outside `{-1, 0, 1}` anywhere under
`backend/ai_gateway/`, on principle, so that no engineering constant
can ever be smuggled into this package. `GET /api/ai/audit`'s `limit`
bound (`Query(default=50, ge=1, le=500)`) is therefore expressed in
`backend/api/routes/ai_gateway.py` using FastAPI's own validation
convention; `backend.ai_gateway.store.list_audit_records` applies
whatever already-validated `limit` it is given, with no clamping or
default value of its own.

## Consequences

- Adding a real network-calling provider later requires no change to
  `orchestrator`, `composer`, `audit`, or any existing test.
- `backend/app.py`'s one-way dependency-direction guarantee (ADR-0017
  Karar 2/10, referenced but not yet committed as a file) is preserved
  exactly, including for a persistence concern that in every other
  domain module is wired directly.
- The persisted audit trail is queryable and durable across process
  restarts, but still carries no raw prompt/response content and no
  secret — the same privacy posture the in-memory-only design already
  had, now durable.
- `POST /api/ai/query`'s runtime behavior (default always-unavailable
  provider, response shape, permission/read-only enforcement) is
  unchanged; this phase does not decide which provider that route uses
  by default.

## Deferred

Real OpenAI/Claude/Ollama provider integration; rewiring
`POST /api/ai/query`'s default runtime `AIModelClient`; backfilling
`ADR-0017`/`ADR-0018`/`ADR-0019` as committed files; the Torque
Recommendation Engine (v3.0.0-beta.1); the Engineering Reasoning
Engine (v3.0.0-beta.2).
