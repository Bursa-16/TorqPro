# Roadmap
Future expansion.

## Faz 2.8.11 — Engineering Governance Architecture and Decision Workflow Standardization

**Complete (Stages 1–5)**, delivered 2026-07-30 — see
`docs/adr/ADR-0014-engineering-governance-architecture.md`,
`docs/11_PRODUCT_BACKLOG.md` §12D, and
`docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md` for full detail.
Defined and implemented a canonical governance vocabulary (review /
publication / resolution lifecycles) as a standalone, additive
`backend/governance/` package with typed contracts (Stage 2), an
append-only event store and idempotency-first service layer
(Stage 3), a bilingual API and workspace (Stage 4), and one read-only
compatibility adapter for washer resolution (Stage 5) — without
modifying any of the four existing, independently-evolved mechanisms
(Production Validation, legacy calculation revisions, joint revision
lifecycle, Faz 2.8.9 washer resolution decisions).

Deferred to a future, separately-scoped phase: Production Validation,
legacy calculation-revision, and joint-revision compatibility
adapters (all three require a live database connection to read,
which this phase's first, narrowly-scoped adapter deliberately did
not take on), and any write-path integration connecting the
canonical governance workflow to a real TorqPro record type.

## Faz 2.8.12 — Governance Integration & Controlled Adoption

**Stage 2, Stage 3, Stage 4 (assessment), Stage 4.1 (spike), and
Stage 4.2 (joint revision read-only adapter) complete**, delivered
2026-07-30 — see
`docs/adr/ADR-0015-washer-resolution-governance-integration.md`,
`docs/11_PRODUCT_BACKLOG.md` §12E, and
`docs/phases/PHASE_2.8.12_STAGE2_INTEGRATION_CONTRACT.md` for full
detail. Scope corrected during Stage 1 assessment to washer
resolution only — the one existing mechanism with a real decision
workflow the canonical governance model can represent without
inventing new lifecycle states; Production Validation, legacy
calculation revisions, and joint revisions remain assessment-only
(Stage 4, not yet done); Material Intelligence, Fastener Assembly
Intelligence, Recommendation logic, report modules, the Quality
Harness, and future VDI 2230 extensions were explicitly ruled out of
scope (no existing decision workflow to govern).

Stage 2 delivered the washer resolution integration contract: an
"authoritative-write-then-synchronous-best-effort-sync" pattern plus
a mandatory, idempotent reconciliation mechanism
(`backend/governance/adapters/washer_resolution_sync.py`,
`.../washer_resolution_reconciliation.py`,
`tools/run_washer_governance_reconciliation.py`), an HTTP-only
aggregate-ownership guard (`backend/governance/ownership.py`), and no
background worker/scheduler/queue of any kind.

Stage 3 wired that contract into production: the real washer decide
endpoint now triggers synchronous best-effort governance
synchronization immediately after the authoritative washer decision
succeeds, with a verified-unchanged public API contract (same URL,
schema, status codes, error mapping) and safe structured logging.

Stage 4 assessed the three remaining ADR-0014 mechanisms: Production
Validation and Legacy Calculation Revisions returned NO-GO this phase
(source-side architectural mismatch and missing service-module
boundary, respectively); Joint Revision Lifecycle returned a
conditional GO for `joint_revisions.status` only, pending a
circular-import spike. Stage 4.1 (spike) empirically proved the risk
and its mitigation (deferred import, mirroring
`backend/api/dependencies.py`'s own established pattern). Stage 4.2
delivered the read-only adapter: `joint_revisions.status` →
governance `ReviewStatus`, with the deferred-import mitigation
mechanically enforced by AST-based and subprocess-based tests.
`joints.status` → `PublicationStatus` remains unimplemented (the
`superseded` transition has no live code path in the source
mechanism today).

Deferred: Stage 5 (final quality/documentation/release pass across
the whole phase). Production Validation and Legacy Calculation
Revisions governance integration remain out of scope unless a future,
separately-scoped phase revisits their source-side architecture.

## Faz 2.8.13 — Governance Workspace Completion

**Complete (Stages 1–5)**, delivered 2026-07-31 — see
`docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`,
`docs/11_PRODUCT_BACKLOG.md` §12F, and
`docs/phases/PHASE_2.8.13_COMPLETION_REPORT.md` for full detail.

Closed the one visibility gap identified in the approved pre-phase
repository analysis: the Faz 2.8.12 Stage 4.2 `joint_revision`
read-only governance projection adapter existed, was tested, and was
import-safety-verified, but had zero production consumers. Added
exactly one new read-only route,
`GET /api/governance/joint-revision/{revision_id}`, exposing the
existing adapter unmodified, and a minimal, additive extension of the
existing generic governance workspace UI — no new page, no write
action, no second status-mapping table, no new governance capability.

Stage 1 delivered the bilingual scope-lock and integration contract.
Stage 2 delivered the API route and corrected the governance adapters
package's stale docstring/exports (accurate only through Faz 2.8.11
Stage 5, not updated through Faz 2.8.12 Stage 2/3). Stage 3 delivered
the frontend lookup card with full TR/EN parity, fixing one
apostrophe-quoting bug and one stale hardcoded key-count constant in
a pre-existing structural test file along the way. Stage 4 performed
a full architectural-boundary, integrity, import-order, and
clean-clone verification pass with no regression found.

`backend/governance/adapters/joint_revision.py` and `backend/joints/`
remain byte-identical to their pre-phase state. No new database
table, migration, lifecycle transition, governance event, or
ownership-registry entry was introduced. Deferred, consistent with
the approved Stage 1 scope: a governance projection registry, a
cross-mechanism consistency validator, joint-revision write
synchronization, and Production Validation/legacy calculation-revision
governance integration (all previously assessed, not revisited).

## Faz 2.9.10 — Question Bank Statistics / Coverage API

**Complete**, delivered 2026-08-08. Added one read-only aggregation
endpoint, `GET /api/question-bank/stats`, over the Question Bank
foundation Faz 2.9.1–2.9.9 already built (`total`,
`by_validation_status`, `by_category`, `by_difficulty`,
`by_question_type`). New module `backend/question_bank/stats.py`
reuses `retrieval.list_questions`/`retrieval.get_validation_status_map`
verbatim -- no new persistence, schema, or lifecycle rule, and no
"publishable" count (deliberately out of scope: this view reports the
bank's whole shape for an admin, not a consumer-facing visibility
filter). Deleted/archived records excluded by the same safe default
every other Question Bank read route already uses.

Deferred: any frontend/admin-UI surface for these statistics
(`frontend/index.html` untouched this phase), and any date/time-based
or trend-over-time statistics (this phase is a single current-state
snapshot only).

## Faz 2.9.11 — Question Bank Statistics Dashboard / Admin UI

**Complete**, delivered 2026-08-08. Added a read-only Statistics /
Coverage section to the existing Question Bank Admin UI
(`frontend/index.html`), rendering `total`, `by_validation_status`,
`by_category`, `by_difficulty`, and `by_question_type` exactly as
returned by the Faz 2.9.10 `GET /api/question-bank/stats` endpoint --
reused verbatim, no new endpoint, no client-side re-aggregation of any
count. Full TR/EN i18n parity (`qb.stats.*`). No new UI framework: the
existing `frontend/index.html` card/table conventions are reused.
Loading, empty, and API-error states follow the same pattern already
used by the Questions list and Import/Export panels.

Deferred, consistent with the approved scope lock: date/time trend or
historical analytics, any charting library, and any new statistics
endpoint. Backend business logic, persistence, schema, and lifecycle
rules (including the Faz 2.9.10 statistics contract itself) are
unchanged.

## v3.0.0-alpha.5 — Persistent Audit, Explainability, Provider Abstraction

**Complete**, delivered 2026-08-09. Three scoped additions to the
existing `backend/ai_gateway` AI layer (v3.0.0-alpha.1 through
alpha.4), all additive:

- Provider abstraction (`backend/ai_gateway/providers/`): an explicit
  name -> `AIModelClient` registry, one offline-safe concrete provider
  (`DeterministicModelClient`), no new competing abstraction, no real
  network-calling provider added.
- Persistent audit (`backend/ai_gateway/store.py`): every
  `POST /api/ai/query` interaction (success and provider-failure) is
  now written to a new, additive/idempotent SQLite table
  (`ai_audit_records`) instead of only living in a request-scoped
  in-memory sink. Hash/metadata only -- never raw prompt/response
  text, never a secret or token. Two new admin-only endpoints to read
  it back (`GET /api/ai/audit`, `GET /api/ai/audit/{audit_id}`).
- Explainability: no new surface. The existing `ComposedAnswer`
  structure (citations/result_label/evidence_status/
  validation_required) already covers this phase's explainability
  requirement and is reused verbatim.

`POST /api/ai/query`'s pre-existing alpha.4 behavior is unchanged
(still defaults to an always-unavailable provider at runtime). 48 new
tests. See `docs/CHANGELOG.md`'s v3.0.0-alpha.5 entry for full detail.

Deferred: real network-calling AI providers (OpenAI/Claude/Ollama);
rewiring `POST /api/ai/query`'s default provider; the Torque
Recommendation Engine (v3.0.0-beta.1) and Engineering Reasoning Engine
(v3.0.0-beta.2).

## v3.0.0-beta.1 — Torque Recommendation Engine

**Complete**, delivered 2026-08-11. First production-oriented torque
recommendation surface (`backend/torque_recommendation/`), additive
and deterministic-first: engineering inputs flow through the existing
`backend.calculation_engine.joint_analysis.analyze_joint` calculation
stack, then through a fixed, closed-vocabulary confidence/
applicability classification (`HIGH`/`MEDIUM`/`LOW`/`NOT_APPLICABLE`)
and a deterministic, non-LLM explanation layer, before an audit record
is written. No formula, coefficient, or standard is invented; no AI/
LLM provider can compute or override a torque value in this phase --
`backend/torque_recommendation` never imports `backend.ai_gateway` at
all, so offline/deterministic operation holds unconditionally rather
than as a runtime fallback. New endpoint: `POST
/api/ai/torque-recommendation`. Traceability reuses the existing
`audit_log` table (`action="torque_recommendation"`) rather than a
new dedicated table -- no schema change. 37 new tests. See
`docs/CHANGELOG.md`'s v3.0.0-beta.1 entry for full detail.

Deferred: the Engineering Reasoning Engine (v3.0.0-beta.2), any
LLM-based explanation enhancement for recommendations, automatic
fastener selection, and multi-joint optimization.

## v3.0.0-beta.2 — Engineering Reasoning Engine

**Complete**, delivered 2026-08-12. Added a deterministic
**Engineering Reasoning Engine** (`backend/ai_gateway/reasoning/`)
that explains an already-computed v3.0.0-beta.1 Torque Recommendation
result by `trace_id` -- it never re-runs
`backend.torque_recommendation.engine.recommend_torque` and never
invokes any deterministic calculation core
(`backend.calculation_engine`/`backend.vdi2230_core`/
`backend.engineering_core`) itself. Lives inside `backend.ai_gateway`
(not a new top-level package, not inside
`backend.torque_recommendation`), reusing existing infrastructure
(`evidence_checker`, `composer`, `context_builder`, the `providers`
registry, `permission`) rather than introducing a parallel
architecture. Three closed reasoning states, no invented confidence
score: `SUPPORTED`, `UNSUPPORTED`, `INSUFFICIENT_EVIDENCE`
(fail-closed for unknown/corrupt/incomplete stored evidence). An
optional, structurally separate AI-generated wording layer
(`backend.ai_gateway.reasoning.wording`) is always fail-soft --
provider unavailability never affects HTTP status or any
deterministic field. New endpoint: `POST
/api/ai/engineering-reasoning`. Traceability reuses the existing
`ai_audit_records` table (v3.0.0-alpha.5) -- no new table, no new
column. 56 new tests. See `docs/CHANGELOG.md`'s v3.0.0-beta.2 entry
for full detail.

Deferred: a real, network-calling AI provider; reasoning support for
any deterministic result other than Torque Recommendation
(joint-analysis, friction, material intelligence, ...); a generic
rule-engine implementation (`docs/08_RULE_ENGINE.md` remains a design
spec only); a new RBAC role.

## v3.0.0-rc.1 — Performance, Security & Documentation

**Completed**, delivered 2026-08-12. Release-candidate hardening
phase for the TorqPro AI platform -- no new AI capability or
engineering engine was in scope. Stage 0 (repository-wide discovery/
audit, no code changes) concluded **GO** for implementation. Four
commits, in order:

- **Documentation & Release Consistency**
  (`f435569db978fe338ee0b48c4ae2989b23ded43b`): this roadmap
  synchronized with the actual repository state; `docs/07_API_SPECIFICATION.md`
  corrected to reflect the real, implemented `/api/...` route surface
  (the document's original `/api/v1` target design was never built
  and no migration toward it is in progress); `DOCUMENTATION_MANIFEST.json`
  checksums regenerated.
- **Security Hardening Phase 1**
  (`5aa6f55dad0800e6c7b751901665342d72a8d1a0`): `TORQPRO_ALLOWED_HOSTS`
  enforcement via `TrustedHostMiddleware`; production-only `/docs`/
  `/redoc`/`/openapi.json` restriction; a real cross-user project-
  ownership gap in calculation creation found and fixed.
- **Security Hardening Phase 2**
  (`5ce429dc3cc655af30843a548563b498fdb9e192`): opt-in general API
  rate limiting; Content-Security-Policy and (production-only)
  Strict-Transport-Security headers; four exception-detail-leakage
  fixes; `pip-audit` added to CI.
- **Performance & Reliability**
  (`245e2937863271af220308e1783302f4730f57b8`): a reusable, opt-in
  performance benchmark suite; SQLite WAL journal mode and
  `busy_timeout`; concurrency validation; critical-path profiling.

See `docs/CHANGELOG.md`'s v3.0.0-rc.1 entry for full detail, including
what was measured and deferred at each step.

The deterministic engineering layer remained the source of truth
throughout this phase; no AI capability was added or changed, and the
validated engineering boundaries established through the Alpha and
Beta phases were not modified.

Deferred, consistent with the Stage 0 scope decision and confirmed
during this phase with measured evidence rather than assumption: a
real network-calling AI provider; a new engineering engine; database
migration; a strict nonce/hash-based CSP (would require restructuring
`frontend/index.html`'s single inline `<script>` block into external
files); a broad sync→async route rewrite; a JSON-to-SQLite
persistence redesign for the Question Bank/washer-resolution stores;
and any hard, cross-machine performance regression threshold.

## v3.0.0 — Stable Release

**Complete**, delivered 2026-08-13 — see `docs/CHANGELOG.md`'s
`v3.0.0` entry and `docs/releases/v3.0.0.md` for full detail.

A release-metadata/version transition only, built on the validated
`v3.0.0-rc.1` baseline (`3c9efedf58b4f07cbd65bca7b50f2ac039209cf3`):
no engineering logic, AI/reasoning behavior, API contract, or
security/performance control changed. `VERSION`,
`tests/test_version_centralization.py`, `README.md`, this document,
and the CHANGELOG entry are the only substantive changes, plus a
narrow `.gitignore` addition for the opt-in benchmark suite's
generated artifact.

Full suite at release: 3371 passed, 13 skipped (unchanged from rc.1).
Opt-in benchmark suite: 13/13 passed. `pip-audit` clean. `git diff
--check` clean.

No new major roadmap phase is defined as of this release; future work
will be scoped separately.
