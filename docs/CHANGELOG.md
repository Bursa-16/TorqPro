# TorqPro Documentation Changelog


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1.0.0-draft — 2026-07-16

- Added full SDS baseline to existing TorqPro_24 package.
- Documented current implementation and migration strategy.
- Defined joint-centred domain model.
- Corrected load-sharing, nut-factor, stiffness, service stress, settlement and thermal architecture.
- Added API, rule, library, UI, AI, backlog, developer, testing and deployment specifications.
- Added mandatory Claude/AI-agent context and ADRs.

## Faz 2.5A — 2026-07-22

- Added minimal Joint/JointRevision prerequisite foundation (`backend/joints/`)
  as a real, forward-compatible domain layer, not a stub — see
  `docs/adr/ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md`.
- Added Production Validation Foundation domain (`backend/production_validation/`):
  `ValidationStudy`, `MeasurementDataset`, `MeasurementRecord`,
  `SpecificationSnapshot`, `ToolReference`, with full API, CSV import,
  audit logging and a `draft -> data_collection -> completed -> under_review
  -> approved|rejected -> archived` state machine.
- Process capability math (Cp/Cpk/Pp/Ppk/Cmk) intentionally not implemented;
  reserved for Faz 2.5B/2.5C.
- Documented in `docs/phases/PHASE_2.5A_PRODUCTION_VALIDATION_FOUNDATION.md`.

## Faz 2.8.9 — 2026-07-29

- Added the washer resolution decision workflow: an append-only decision
  ledger (`backend/library/data/washer_resolution_decisions.json`) separate
  from and never overwriting the Faz 2.8.5 source resolution ledger; a
  closed state machine; an idempotency-key-first decision API; an
  `effective_status` overlay computed from both ledgers together — see
  `docs/adr/ADR-0013-washer-resolution-decision-workflow.md`.
- Extended `backend/library/washer_report.py` additively with
  effective-status counts, a real-decision-only `resolved` count, and a
  new English Markdown renderer (TR/EN parity) — no existing report field
  removed or renamed.
- Added `GET /api/library/washers/resolutions/{queue,decisions,report}`
  (all read-only, additive) and the `page-washerresolution` frontend
  workspace, with full TR/EN parity (38/38 `wrr.*` keys).
- Documented in `docs/phases/PHASE_2.8.9_WASHER_RESOLUTION_DECISION_WORKFLOW.md`.

## Faz 2.8.11 (Stage 1) — 2026-07-30

- Documentation-only architecture stage. No table, JSON ledger, API
  endpoint, enum, transition graph, or frontend string was added,
  modified, or renamed; `backend/`, `frontend/`, and `tests/` are
  unchanged.
- Added `docs/adr/ADR-0014-engineering-governance-architecture.md`:
  a canonical governance model unifying the vocabulary of four
  independently-evolved mechanisms — the Production Validation
  workflow (Faz 2.5A), the legacy `calculation_revisions` review/
  approve/reject workflow in `backend/app.py`, the joint revision
  lifecycle (`backend/joints/`, ADR-0003), and the Faz 2.8.9 Washer
  Resolution Decision Workflow (ADR-0013) — into three independent
  lifecycle groups (review, publication/revision, resolution) and a
  canonical field-name set, without changing any existing mechanism.
- Documented in
  `docs/phases/PHASE_2.8.11_ENGINEERING_GOVERNANCE_ARCHITECTURE.md`.
- Stages 2–5 (shared contracts, event store, additive API/TR-EN
  workspace, compatibility adapters) are not started.

## Faz 2.8.11 (Stages 2–5) — 2026-07-30

- **Stage 2**: added `backend/governance/enums.py` (`ReviewStatus`,
  `PublicationStatus`, `ResolutionStatus`, `LifecycleGroup`, closed
  fail-closed transition tables), `models.py` (`ReviewDecision`/
  `PublicationDecision`/`ResolutionDecision`, `extra="forbid"`,
  ADR-0014's required-field tables), `transitions.py`,
  `exceptions.py`. Additive only; no existing mechanism imports it.
- **Stage 3**: added `events.py` (`GovernanceEvent`), `store.py`
  (`FileGovernanceEventStore` — atomic temp-file+`os.replace` writes,
  `fcntl.flock` with a `threading.Lock` fallback, UTF-8,
  `sort_keys=True`/`ensure_ascii=False` JSON, corruption detection,
  no default data path), `service.py` (nine idempotency-first command
  functions; idempotency resolved before transition validation;
  `previous_status` never caller-suppliable). 65 new tests.
- **Stage 4**: added `backend/governance/api.py` (11 additive routes
  under `/api/governance`, mounted onto `backend.app.app`, reusing
  the existing `user` auth dependency; `actor` derived from the
  authenticated user; lazy `TORQPRO_GOVERNANCE_EVENT_STORE_PATH`
  store provider with a safe 503 when unconfigured) and a generic,
  bilingual `page-governance` frontend workspace (53/53 TR/EN `gov.*`
  key parity). 71 new tests (29 API + 42 frontend), plus a
  dependency-free Node/vm harness (`run_governance_workspace_tests.js`,
  58 assertions).
- **Stage 5**: added `backend/governance/adapters/
  washer_resolution.py` — a read-only `CompatibilityProjection` of
  the existing Faz 2.8.9 washer resolution workflow onto the
  canonical vocabulary (71 exact + 5 explicitly unsupported mappings
  across all 76 real ledger records; zero source-ledger writes,
  verified byte-identical before/after). Production Validation, the
  legacy calculation-revision workflow, and joints were deliberately
  not adapted (each requires a live database connection). Fixed the
  pre-existing async test-harness defect in
  `tests/js/run_material_intelligence_tests.js` (Faz 2.8.8) — 19
  scenarios now run through an awaited `async function main()`. 13
  new governance/adapter tests plus 3 new/strengthened frontend
  regression-guard tests.
- No existing table, JSON ledger, API endpoint, enum, or transition
  graph was modified anywhere across Stages 2–5. No data migrated, no
  field renamed. Full suite: 1759/1759 passing.
- Documented in
  `docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md` (bilingual
  final phase report).

## Faz 2.8.12 Stage 2 — 2026-07-30

- Washer Resolution Integration Contract: additive write-path
  synchronization from the Faz 2.8.9 washer resolution decision
  workflow onto the Faz 2.8.11 governance event store, per
  `docs/adr/ADR-0015-washer-resolution-governance-integration.md`
  ("authoritative-write-then-synchronous-best-effort-sync" +
  mandatory idempotent reconciliation). **Not yet wired to the
  production washer API** — that connection is Stage 3.
- Added `backend/governance/ownership.py`: a closed, additive
  aggregate-type registry (`"washer_resolution"` today) and a guard
  applied at the single choke point shared by all nine generic
  governance HTTP write endpoints (`backend/governance/api.py`'s
  `_run_command`) — rejects writes to an externally-owned
  `aggregate_type` with `409`, using the module's existing
  conflict-response convention. Read endpoints and internal
  (in-process) governance service calls are unaffected.
- Added `backend/governance/adapters/washer_resolution_sync.py`:
  `sync_washer_decision()` — a never-raising, deterministically
  classified (`synchronized`/`already_synchronized`/
  `would_synchronize`/`skipped_open`/`not_representable`/
  `governance_store_unconfigured`/`failed`) synchronization of one
  washer resolution decision onto a governance event. Reuses the
  existing Stage 5 adapter's `_STATUS_MAP` as the single canonical
  mapping source (derives, never redefines, the three syncable
  statuses: `resolved→RESOLVED`, `accepted_as_is→WAIVED`,
  `rejected→REJECTED`). `under_review` and
  `blocked_authoritative_source` are never synchronized and never
  guessed. Global governance decision_id/idempotency_key uniqueness
  (verified, not aggregate-scoped) is protected by a namespaced
  `washer-sync:` idempotency key plus explicit pre-write consistency
  verification against any pre-existing same-key event.
- Added `backend/governance/adapters/washer_resolution_reconciliation.py`:
  `reconcile()` — deterministic, idempotent, read-only-over-washer
  batch reconciliation reusing `sync_washer_decision()` for every
  record (no second, independently-written transition/mapping
  logic). Deterministic counters
  (`scanned`/`eligible`/`synchronized`/`already_synchronized`/
  `would_synchronize`/`not_representable`/`skipped_open`/`failed`/
  `governance_store_unconfigured`) with a tested invariant. Dry-run
  supported; never writes to any washer file.
- Added `tools/run_washer_governance_reconciliation.py`: explicitly
  invoked CLI (dry-run by default; `--apply` to write), deterministic
  JSON report, no filesystem path or environment-variable value ever
  printed.
- 108 new tests (21 sync + 10 reconciliation + 6 CLI + 9 API
  ownership-guard + 9 ownership-registry + 20 compatibility, net of
  2 compatibility tests renamed/replaced — see
  `docs/phases/PHASE_2.8.12_STAGE2_INTEGRATION_CONTRACT.md` for the
  exact count). `tests/governance/test_compatibility.py` updated
  (not weakened) to reflect ADR-0015's explicit 3-file
  mechanism-import allowlist (previously 1), with new AST-based
  boundary tests proving the two new files write exclusively through
  the existing, unmodified `backend.governance.service` command
  functions and never duplicate the canonical status mapping or
  transition logic.
- `backend/app.py` and every washer production module
  (`washer_resolution_service.py`,
  `washer_resolution_decisions.py`,
  `washer_resolution_decisions_store.py`) are unchanged. The
  immutable washer resolution ledger and the washer decision store
  are unchanged (SHA256-verified before/after).
- Full suite: 1814/1814 passing (1759 baseline + 55 net new).
  Governance suite: 204/204. All 6 JS harnesses unchanged
  (44/58/1097/45/40/32). flake8/compileall/`git diff --check` clean.
- Documented in
  `docs/phases/PHASE_2.8.12_STAGE2_INTEGRATION_CONTRACT.md`.

## Faz 2.8.12 Stage 3 — 2026-07-30

- Washer Controlled Write Integration: wired Stage 2's
  `sync_washer_decision` into the real washer decide endpoint (`POST
  /api/library/washers/resolutions/{resolution_id}/decide`),
  immediately after the authoritative washer decision succeeds. The
  washer decision store remains the sole authority; governance
  synchronization is synchronous, best-effort, and provably cannot
  alter the washer response (tested by monkeypatching the sync call
  itself to raise).
- Added `sync_washer_decision_and_log` and `resolve_governance_store`
  (Stage 2 files, additive functions) — safe structured logging via
  the project's existing `logging.getLogger("torqpro")`, never a new
  logging framework; log lines never contain filesystem paths,
  environment-variable values, credentials, tracebacks, or the
  decision's own free-text fields (tested).
- Public API contract unchanged and verified: same URL, request
  schema, response schema (`{"decision", "created"}` — no governance
  field added), success status code, and error mapping. No second
  idempotency mechanism was introduced at the HTTP layer.
- `backend/app.py`'s governance-import allowlist
  (`tests/governance/test_compatibility.py`) widened from 1 to 3
  approved lines (Stage 4's router mount + Stage 3's two sync-call-
  site imports) — documented, tested, closed. No ADR amendment
  required (routine implementation of the pattern ADR-0015 already
  formalized).
- 13 new integration/failure-isolation tests (8 API-level in
  `tests/test_faz_2_8_9_stage3_api.py::TestGovernanceSyncOnDecideEndpoint`
  + 4 logging-safety unit tests + 1 compatibility inverse-check),
  reusing Stage 2's own adapter test coverage rather than duplicating
  it.
- `backend/library/washer_resolution_service.py`,
  `washer_resolution_decisions.py`,
  `washer_resolution_decisions_store.py`, the immutable washer
  resolution ledger, and the washer decision store are unchanged
  (SHA256-verified before/after).
- Full suite: 1827/1827 passing. Governance suite: 209/209. All 6 JS
  harnesses unchanged. flake8/compileall/`git diff --check` clean
  (flake8 scoped per the project's own established convention — see
  `tools/run_quality_gate.py`'s docstring on pre-existing,
  out-of-scope style debt).
- Documented in
  `docs/phases/PHASE_2.8.12_STAGE3_CONTROLLED_WRITE_INTEGRATION.md`.

## Faz 2.8.12 Stage 4.1 — 2026-07-30 (spike, no production code)

- Isolated proof-of-concept (disposable clone, deleted after use)
  empirically confirmed a real, deterministic circular import: any
  governance file importing `backend.joints.service` at module level
  crashes with `ImportError: cannot import name 'router' from
  partially initialized module 'backend.governance.api'` if something
  imports `backend.governance.api` directly before `backend.app` has
  been loaded. Confirmed the established mitigation already used by
  `backend/api/dependencies.py` (deferred/function-body import)
  resolves it in every tested order, including clean `__pycache__`
  and `importlib.reload`.

## Faz 2.8.12 Stage 4.2 — 2026-07-30

- Added `backend/governance/adapters/joint_revision.py`: a read-only
  compatibility adapter projecting `joint_revisions.status` onto
  canonical governance `ReviewStatus` (`draft→DRAFT`,
  `review→UNDER_REVIEW`, `approved→APPROVED`,
  `rejected→REJECTED`) — the exact Stage 4.1-mitigated deferred-import
  pattern for `backend.joints.service`; `backend.joints.exceptions`/
  `schema` (zero `backend.app` dependency, verified) imported safely
  at module level. `joints.status`→`PublicationStatus`, Production
  Validation, and Legacy Calculation Revisions remain explicitly out
  of scope (Stage 4 assessment: NO-GO this phase).
- New `ProjectionOutcome` vocabulary (`supported`/`not_found`/
  `unsupported_status`/`invalid_source_record`/`source_unavailable`)
  — deliberately not washer's `MappingQuality`, since joint revisions
  have no partial-mapping case today.
- Mechanism-import allowlist widened from 3 to 4 approved files
  (ADR-0015's established pattern, extended); two new AST-based tests
  mechanically prove `backend.joints.service` is imported only inside
  a function body, plus 3 subprocess-based clean-process regression
  tests (governance.api standalone, adapter standalone, adapter after
  normal app init) and a reload-safety test.
- 24 new tests (15 adapter runtime + 9 compatibility/import-order).
  `backend/joints/`, `backend/production_validation/`, and
  `backend/app.py` are byte-identical to their pre-Stage-4.2 state
  (verified via `git diff --quiet`) — no production code, migration,
  or schema change of any kind.
- Full suite: 1851/1851 passing. Governance suite: 233/233. Existing
  joints tests: 9/9 unchanged. All 6 JS harnesses unchanged.
  flake8/compileall/`git diff --check` clean; existing quality gate
  PASSED.
- Documented in
  `docs/phases/PHASE_2.8.12_STAGE4_2_JOINT_REVISION_READ_ONLY_ADAPTER.md`.

## Faz 2.8.13 — Governance Workspace Completion — 2026-07-31

- Added exactly one new route,
  `GET /api/governance/joint-revision/{revision_id}`, exposing the
  existing, previously-unwired Faz 2.8.12 Stage 4.2
  `project_joint_revision()` adapter — unmodified. Outcome→HTTP-status
  mapping: `supported`/`unsupported_status`/`invalid_source_record`/
  `source_unavailable` → 200 (all legitimate, already-classified
  adapter results, visible in the response body); `not_found` → 404.
  No `try/except` in the handler (`project_joint_revision` never
  raises); no governance-store dependency (the route never reads or
  writes governance state).
- Corrected `backend/governance/adapters/__init__.py`'s stale Faz
  2.8.11-era docstring/`__all__`, which had gone stale since Faz
  2.8.12 Stage 2/3 (it still claimed "no adapter here writes to the
  governance event store" and omitted three newer adapter files). Now
  accurately distinguishes read-only source projection adapters,
  controlled governance-event synchronization adapters, and
  reconciliation utilities; exports `joint_revision`'s stable public
  symbols (empirically verified safe — no circular-import risk).
- Added a minimal, additive "Joint Revision Projection (read-only)"
  card inside the existing generic governance workspace
  (`frontend/index.html`) — a revision-ID input, a lookup button, and
  a result area rendering all five real outcomes directly from the
  API's own fields (no second status-mapping table). No new
  standalone page, no write action. 16 new `gov.jr.*` translation
  keys, full TR/EN parity.
- 20 new backend tests (`tests/governance/test_joint_revision_api.py`,
  16; 4 focused additions to `tests/governance/test_compatibility.py`)
  and 13 new frontend scenarios
  (`tests/js/run_governance_workspace_tests.js`, 98/98 assertions).
  Corrected one genuine pre-existing-file consequence: an apostrophe
  forced a double-quoted JS string, which broke
  `tests/test_faz_2_8_11_stage4_frontend.py`'s single-quote-only
  key/value extraction regex; fixed the quoting and updated that
  file's stale hardcoded gov.*/`sidebar.governance` key-count constant
  (53 → 69), made obsolete directly by the required new keys.
- Full suite: 1871/1871 passing (1851 baseline + 20 new). Governance
  suite: 253/253 (233 baseline + 20 new). All 6 JS harnesses passing.
  flake8/compileall/`git diff --check` clean; quality gate PASSED
  (6/6). Full architectural-boundary and integrity verification
  (Stage 4): `backend/governance/adapters/joint_revision.py` and
  `backend/joints/` byte-identical to baseline; no new write route,
  governance event, database table, lifecycle transition, or
  ownership-registry entry; deferred-import mitigation re-verified
  under the new call path with no circular-import error; independent
  clean-clone reproduction confirmed identical results.
- Documented in
  `docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`
  and `docs/phases/PHASE_2.8.13_COMPLETION_REPORT.md`.

## Faz 2.8.18 — UI/UX Refactoring and Dashboard Improvements — 2026-08-03

- GitHub Release `v2.8.18` (tag commit `59ce6458fabf002ceab1be1ef18f6145fd01da0c`,
  merge of PR #31 `feature/faz-stage5-final-acceptance-audit`) was published
  without an accompanying `VERSION`/README/test version bump; `VERSION`,
  `README.md`, and `tests/test_version_centralization.py` still identified
  the codebase as `2.8.17` after the tag existed. This entry retroactively
  aligns the single-source version (`VERSION` file, read dynamically by
  `backend.app.APP_VERSION`, exposed via `/api/health`) with the already-
  published tag. No architecture, API behaviour, or engineering value was
  changed by this alignment.
- Restricted `/api/runtime/status` to admin-only access
  (`Depends(admin)`) — previously unauthenticated.
- Reorganized dashboard measurement KPIs.
- Added a tightening-class equipment drill-down view.
- Finalized dashboard acceptance labels.
- Changed files: `backend/app.py`, `frontend/index.html`,
  `tests/js/run_i18n_tests.js`,
  `tests/test_faz_stage2_system_health_authorization.py` (new),
  `VERSION`, `README.md`, `tests/test_version_centralization.py`.

## Faz 2.8.19 — Washer Resolution Decision Workflow Integration — 2026-08-03

Connects the Faz 2.8.9 washer resolution decision backend (built but
never wired to any UI) to a full frontend workflow, across five
additive, independently-committed stages.

- **Stage 1** (`58ca1d487c0f4bdfd7ac0937ed260d5ed98f6732`) — additive
  `GET /api/library/washers/resolutions/{resolution_id}` endpoint.
  `backend/library/washer_resolution_service.py`: new
  `resolution_detail()`, reusing `get_washer_resolution()` (Faz 2.8.5)
  and `resolution_queue()` (Faz 2.8.9) unmodified — no new business
  logic, no duplicated effective-status formula. Thin HTTP adapter in
  `backend/app.py`, registered after the static `/queue` and `/report`
  routes so route matching is unaffected (verified programmatically
  via `app.routes`).
- **Stage 2** (`2481b21d240b51f49cd0f5b08b2e8ffdde48f29e`) — read-only
  Resolution Queue + Detail frontend inside `page-washerresolution`,
  listing all 76 washer resolution records (`resolution_id`,
  `washer_record_id`, `issue_type`, `source_status`,
  `effective_status`, `decision_count`, `is_blocked`, `is_terminal`)
  with a per-record detail lookup. 20 new `wrr.queue.*`/`wrr.detail.*`
  TR/EN keys.
- **Stage 3** (`bdb5d3d3cd72a56e319fb1566aabbe7da3cae3b2`) — additive
  decision-entry form, submitting only user-typed values to the
  existing, already-tested `POST /{resolution_id}/decide` endpoint.
  No status, evidence, or confidence value is inferred, suggested, or
  computed. Idempotency-key generation/persistence-on-retry,
  double-submit prevention, and blocked/terminal-record disabling all
  read only from backend-provided fields — no client-side
  state-machine table. 15 new `wrr.decide.*` TR/EN keys.
- **Stage 4** (`3eecfaf7eb2fb6a345ca9c4524055ee14d626202`) — read-only
  Decision History view, using the existing
  `GET /{resolution_id}/decisions` endpoint, rendered in the API's own
  append order (no client-side sort). No edit, delete, rollback, or
  replay. Hooked into the same detail-load success path used by
  Stage 1-3, so it is accessible for blocked/terminal records and
  refreshes automatically after a successful decision submit. 11 new
  `wrr.history.*` TR/EN keys.
- **Stage 5** (this entry) — `VERSION` bumped to `2.8.19`,
  `README.md` and this changelog aligned, `docs/11_PRODUCT_BACKLOG.md`
  washer-resolution entry updated,
  `docs/phases/PHASE_2.8.19_WASHER_RESOLUTION_DECISION_WORKFLOW_INTEGRATION.md`
  added, `tests/test_version_centralization.py` updated to `2.8.19`.

No backend or API behaviour changed at any stage of this phase — every
endpoint used was either a newly-added thin, additive read adapter
(Stage 1) or reused verbatim from Faz 2.8.9 (Stages 2-4). No
engineering value, evidence, or decision was invented anywhere in this
workflow.

**This phase delivers the workflow, not resolved records.** As of this
release, `backend/library/data/washer_resolution_decisions.json`
contains zero recorded decisions, and all 76 washer resolution records
in `backend/library/data/washer_resolution_ledger.json` remain
unresolved (71 `open`, 5 `blocked_authoritative_source`). None were
closed automatically by this phase.

Full test suite: 2291 passed (Stage 1 baseline 2213 + 13 + 25 + 21 +
19 across the four stages). Canonical quality gate
(`tools/run_quality_gate.py`) 6/6 PASSED at every stage, including 9
JavaScript regression harnesses.

## Faz 2.8.20 — Washer Resolution Evidence & Controlled Closure — 2026-08-05

Adds a structured evidence trail and a controlled, evidence-backed
closure workflow on top of the Faz 2.8.9/2.8.19 washer resolution
decision system, across five additive, independently-committed stages
(PR #33) plus a short follow-up test-maintenance series (PR #34).

- **Stage 1** (`ea65071`, refactored `46ec085`) — `WasherResolutionEvidence`
  domain model (`backend/library/washer_resolution_evidence.py`):
  immutable, checksummed evidence records with a closed `EvidenceType`
  vocabulary (authoritative standard, manufacturer document, approved
  engineering source, internal measurement, comparison analysis,
  legacy provenance reference, other) and an `EvidenceVerificationStatus`
  (unverified/verified/rejected). No persistence, no API, no readiness
  logic at this stage.
- **Stage 2** (`b3a2d39`) — append-only evidence persistence layer
  (`backend/library/washer_resolution_evidence_store.py` +
  `backend/library/data/washer_resolution_evidence.json`), mirroring
  the Faz 2.8.9 decision ledger's locked/atomic-write pattern exactly.
  No `resolution_id` validation and no idempotency at this layer
  (deliberate; both are the service layer's responsibility).
- **Stage 3** (`58f15ae`, hardened `323222a`) — controlled closure
  service: a `WasherResolutionClosure` domain model, its own
  append-only ledger, and `record_resolution_evidence()` /
  `evaluate_closure_readiness()` / `close_resolution()` /
  `get_resolution_closure()` orchestration in
  `backend/library/washer_resolution_service.py`. Closure requires a
  terminal decision and at least one *verified* evidence record;
  corrupted evidence blocks closure rather than being silently
  dropped. No reopen mechanism anywhere (ADR-0013 consistent).
- **Stage 4** (`8c557b6`) — five new REST endpoints under
  `/api/library/washers/resolutions/{resolution_id}/(evidence|
  closure-readiness|close|closure)`
  (`backend/api/routes/washer_resolution_closure.py`), following the
  established modular-router convention (`APIRouter`, `Depends(user)`,
  a central exception-mapping helper). `GET .../closure` returns
  `200 {"closure": null}`, not 404, when nothing has been closed yet.
- **Stage 5** (`a0ce595`) — additive Evidence List/Form, Closure
  Readiness, and Close Form/Result cards inside the existing
  washer-resolution detail screen; `verification_status` is shown,
  never changed, from this screen. 62 new
  `wrr.evidence.*`/`wrr.closure.*` TR/EN keys. New dependency-free
  JS/vm regression harness
  (`tests/js/run_washer_resolution_evidence_closure_tests.js`, 128
  assertions) registered in the canonical quality gate.
- **Follow-up test-maintenance series** (`309097c`, `81fd04d`,
  `a39210e`, `1b87954`; PR #34, merged after the `v2.8.20` tag) —
  cross-platform (`sys.executable`) portability for the Stage 5
  wrapper's i18n-parity subprocess call; refreshed hardcoded
  `wrr.*` key-count and JS-harness-count assertions to match Stage 5's
  own additions; a brace-depth-based, version-independent rewrite of
  the Joint Revision List UX harness's I18N-block extraction (Faz
  2.8.16), replacing a fragile regex that could throw an unclear
  `TypeError` if the block's trailing text ever shifted; and a final
  scope-list update recognizing that fix as an intentional part of
  Stage 5.

No backend business rule, checksum algorithm, or readiness rule was
duplicated across layers at any stage — each new layer (domain model,
persistence, service, API, frontend) calls the one beneath it
unchanged. No reopen, governance sync, or reporting/export UI exists
anywhere in this phase.

**This phase delivers the workflow, not closed records.** As of this
release, `backend/library/data/washer_resolution_evidence.json` and
`backend/library/data/washer_resolution_closure.json` are both empty;
no washer resolution has been evidenced or closed by this phase.

**Release note:** `v2.8.20` was tagged at the PR #33 merge commit
(`e30e5e1`). The four follow-up test-maintenance commits above
(PR #34) were merged to `main` *after* that tag and are included in
this changelog entry for completeness, but are not covered by the
`v2.8.20` tag itself.

## Faz 2.8.21 — Engineering Formula Traceability and Governance Foundation — 2026-08-05

Governance and visibility only -- no engineering formula, coefficient,
or numerical result changed anywhere in this phase. Adds
`backend/engineering_core/trace.py`, giving the 10 live formulas
actually reachable from `evaluate_joint()` (torque, thread friction,
pitch/minor diameter, helix angle, thread shear area, material shear
strength, preload, proof-load utilization, and the composite joint
check) the same APPROVED/PROVISIONAL/EXPERIMENTAL/DEPRECATED/UNVERIFIED
traceability already proven out in `backend.vdi2230_core.trace` --
reused architecturally, not duplicated: `APPROVED`/`PROVISIONAL` are
imported directly from `vdi2230_core.trace`, not redefined.

Result: 0 APPROVED, 9 PROVISIONAL, 1 UNVERIFIED (the `0.58`
shear-strength factor, whose origin is not documented in the
codebase). `internal_thread_sf`/`external_thread_sf` -- previously
returned with no visible status -- now carry an explicit PROVISIONAL,
LOW-confidence governance record naming the `d2`/`d3` diameter basis,
the `0.5` coefficient, and a fixed set of prohibited compliance claims
(ISO 16224, VDI 2230, FCA C2001, ASME). The existing
`/api/engineering/formula-validation` endpoint was extended (not
replaced) to also report these; `/api/engineering/check` gained one
additive `formula_governance` key. The frontend's "Hızlı Hesap" screen
-- found during this phase to compute its own `internal_thread_sf`/
`external_thread_sf` independently in client-side JavaScript, never
calling `/api/engineering/check` -- gained a small, existing-i18n-driven
"Provisional model" / "Geçici model (Provisional)" label next to both
values.

Thread-stripping model (`0.5*pi*d_effective*Le`) remains PROVISIONAL,
confidence LOW, per the source-validation review that preceded this
phase (structurally aligned with a RoyMech "convenient formula," no
primary ISO/DIN/VDI/ASME citation found). Not redesigned or replaced
here. Torsional stress, von Mises equivalent stress, bearing/contact
pressure, and a standalone tensile-stress (F/A) function remain
genuinely absent from `backend.engineering_core` and were **not**
given placeholder registry entries.

36 new governance tests (`tests/test_faz_2_8_21_engineering_core_traceability.py`),
including a LEGACY_REGRESSION_ONLY numerical baseline locking
`evaluate_joint()`'s pre-phase output bit-for-bit. See
`docs/phases/PHASE_2.8.21_ENGINEERING_CORE_TRACEABILITY.md` for the
full delivery report.

## Faz 2.9.10 — Question Bank Statistics / Coverage API — 2026-08-08

- Added `GET /api/question-bank/stats`, a read-only aggregate view over
  the Question Bank: `total`, `by_validation_status`, `by_category`,
  `by_difficulty`, `by_question_type` (`backend/question_bank/stats.py`).
- No new persistence, schema, or lifecycle rule: reuses
  `retrieval.list_questions` (`publishable_only=False`, matching every
  other read route's existing `include_deleted=False`/
  `include_archived=False` safe default) and
  `retrieval.get_validation_status_map` verbatim.
- Deliberately no "publishable" count in this phase — a statistics view
  is for an admin to see the whole bank's shape, not a consumer-facing
  visibility filter; `validate_publishable` is never invoked here.
- Missing/blank breakdown values (in practice: a JSON content record
  with no matching SQLite lifecycle row) are grouped under a
  deterministic `"unknown"` bucket.
- Route registered before every `{question_id}`-shaped dynamic route in
  `backend/api/routes/question_bank.py`, so the literal path segment
  `stats` is never captured by a path parameter.
- 18 new tests
  (`tests/test_faz_2_9_10_question_bank_stats.py`): empty bank, total
  count, each of the four breakdowns individually and combined, the
  unknown bucket, soft-deleted/archived exclusion and restore
  reappearance, non-publishable records still counted, no publishable
  count in the response, HTTP auth enforcement, response shape,
  route-order (not shadowed by `{question_id}`), and no regression on
  the pre-existing list/export routes.

## Faz 2.9.11 — Question Bank Statistics Dashboard / Admin UI — 2026-08-08

- Added a read-only Statistics / Coverage section to the Question Bank
  Admin UI (`frontend/index.html`): `total`, `by_validation_status`,
  `by_category`, `by_difficulty`, `by_question_type`, rendered exactly
  as returned by the existing `GET /api/question-bank/stats` (Faz
  2.9.10) -- reused verbatim, no new backend endpoint, no client-side
  re-aggregation.
- Full TR/EN i18n parity (`qb.stats.*`). No new UI framework: reuses
  the existing `frontend/index.html` card/table conventions.
- Loading, empty, and API-error states handled with the same pattern
  already used by the Questions list and Import/Export panels.
- 23 new tests
  (`tests/test_faz_2_9_11_question_bank_statistics_dashboard_frontend.py`):
  card presence/placement, loading/empty/error-state handling, all
  four breakdowns rendered without re-implementing aggregation,
  `qbInit()`/`qbReapplyLanguage()` lifecycle wiring, `qb.stats.*`
  TR/EN key parity, and JS syntax validity.

## v3.0.0-alpha.5 — Persistent Audit, Explainability, Provider Abstraction — 2026-08-09

- **Provider abstraction** (`backend/ai_gateway/providers/`): an
  explicit, deterministic name -> `AIModelClient` registry
  (`registry.ProviderRegistry`/`build_default_registry`). Adds two
  small, additive capability hooks directly onto the existing
  `AIModelClient` base class (`model_identifier`, `is_available()`)
  rather than a second, competing abstraction -- deliberately never
  named/aliased to `backend.calculation_engine.provider.Provider`.
  Only one concrete provider is registered in this phase:
  `providers.deterministic.DeterministicModelClient`, offline-safe,
  no network call. An unknown provider name raises the new
  `exceptions.ProviderNotFoundError`. No real OpenAI/Claude/Ollama
  integration is added -- explicitly deferred.
- **Persistent audit** (`backend/ai_gateway/store.py`): additive,
  idempotent SQLite migration (`ai_audit_records`), wired into
  `backend/app.py`'s existing `migrate()` through the one file
  already sanctioned to import `backend.ai_gateway`
  (`backend/api/routes/ai_gateway.py`), never directly -- preserves
  the pre-existing one-way dependency-direction guard
  (`tests/ai/test_dependency_direction.py`). `POST /api/ai/query` now
  persists every interaction (success and provider-failure) via
  `SQLiteAuditSink`, alongside `latency_ms`, the requesting user's
  role, an optional `X-Request-ID` correlation id, and a hash of the
  response text -- never raw prompt/response text, never a
  secret/token. Two new admin-only read endpoints:
  `GET /api/ai/audit`, `GET /api/ai/audit/{audit_id}` (404 for an
  unknown id).
- **Explainability**: no new surface introduced. The existing
  `ComposedAnswer` (citations, `result_label`, `evidence_status`,
  `validation_required`) already carries every explainability element
  this phase's audit trail exposes; internal reasoning/chain-of-thought
  is never persisted or returned.
- **New HTTP surface**: `GET /api/ai/providers` (any authenticated
  user, read-only listing of registered providers).
- `POST /api/ai/query`'s pre-existing alpha.4 behavior (default
  always-unavailable provider, response shape, permission/read-only
  enforcement) is unchanged.
- Numeric-literal safety guard
  (`tests/ai/test_safety_and_validation.py::
  test_no_engineering_numeric_literal_anywhere_in_ai_gateway`) was not
  weakened: the audit-listing `limit` bound (`ge=1, le=500`) lives in
  `backend/api/routes/ai_gateway.py` (outside the guarded
  `backend/ai_gateway/` package), not inside it;
  `backend.ai_gateway.store.list_audit_records` applies whatever
  already-validated `limit` it is given, with no literal of its own.
- 48 new tests across `tests/ai/test_providers.py`,
  `tests/ai/test_persistent_audit.py`,
  `tests/ai/test_http_route_alpha5.py`,
  `tests/ai/test_explainability.py`: provider registry/interface
  contract, deterministic provider, unknown-provider handling,
  migration idempotency and pre-existing-database safety, write/read
  round-trips, reopen-persistence, successful- and failed-query audit
  writes, no-raw-content/no-secret persistence guarantees,
  explainability metadata shape, no-private-reasoning-exposure,
  providers/audit endpoint authorization, audit 404, and alpha.4/
  AI-disabled-noop non-regression.
- **Note (pre-existing documentation gap, not introduced by this
  phase):** ADR-0017/ADR-0018/ADR-0019 are referenced extensively in
  `backend/ai_gateway`'s own module docstrings but were never
  committed as files under `docs/adr/`; this phase does not backfill
  them (out of scope) and does not add a new ADR file either, since no
  new architectural decision in this phase was significant/contested
  enough to warrant one beyond what is already documented in the
  module docstrings and this changelog entry.
- **Deferred / explicitly out of scope for this phase:** real
  network-calling AI providers (OpenAI/Claude/Ollama); rewiring
  `POST /api/ai/query`'s default runtime provider away from
  `_UnavailableModelClient`; the Torque Recommendation Engine
  (v3.0.0-beta.1) and Engineering Reasoning Engine (v3.0.0-beta.2).

## v3.0.0-beta.1 — Torque Recommendation Engine — 2026-08-11

- Added `backend/torque_recommendation/` (`models.py`, `engine.py`,
  `validation.py`, `explainability.py`, `audit.py`): the first
  production-oriented torque recommendation surface. The recommended
  value always originates from the existing, unmodified
  `backend.calculation_engine.joint_analysis.analyze_joint`
  deterministic calculation stack -- no formula, coefficient, or
  standard is invented, and no AI/LLM provider can compute, adjust, or
  override a torque value in this phase.
- **Deterministic-first pipeline**: engineering inputs -> `analyze_joint`
  -> fail-closed engineering validation -> confidence/applicability
  classification -> deterministic explanation -> traceability record.
  A recommendation is withheld (`recommended_torque = null`) whenever
  `analyze_joint` reports a critical finding (e.g. a negative residual
  clamp load, an inverted torque window, a yield-utilization failure)
  even if a preliminary value was numerically computable; that raw
  value stays visible as `calculated_torque` for transparency.
- **Confidence classification** (`backend.torque_recommendation.
  validation.classify`): a closed, non-percentage vocabulary
  (`HIGH`/`MEDIUM`/`LOW`/`NOT_APPLICABLE`) derived only from
  `analyze_joint`'s own readiness, safety status, warnings, and
  formula validation status -- never an AI-assigned score.
- **Explainability** (`backend.torque_recommendation.explainability`):
  every successful recommendation carries `input_drivers`,
  `calculation_source` (formula trace), `assumptions`, `limitations`,
  and `warning_reasons`, built entirely from `analyze_joint`'s own
  output with plain string formatting -- no LLM call anywhere in this
  module.
- **Architecture boundary**: `backend/torque_recommendation` and
  `backend/api/routes/torque_recommendation.py` do not import
  `backend.ai_gateway` (verified by a static AST check in
  `tests/torque_recommendation/test_beta1_engine.py`, mirroring
  `tests/ai/test_dependency_direction.py`'s own technique). The
  existing one-way `backend.ai_gateway` dependency guard permits
  exactly one consumer (`backend/api/routes/ai_gateway.py`);
  expanding that allowlist to wire an LLM-based explanation
  enhancement into this engine is explicitly deferred to a later,
  separately-approved phase. Offline/deterministic operation therefore
  holds unconditionally in this phase, not as a runtime fallback
  behind a provider-availability check.
- **New HTTP surface**: `POST /api/ai/torque-recommendation`
  (`Depends(user)`, same authentication as every other endpoint).
  Malformed/out-of-domain inputs (e.g. an unsupported thread/pitch
  combination) map to `422`, mirroring
  `/api/engineering/joint-analysis`'s existing, already-tested error
  convention; a request with only missing optional inputs returns
  `200` with `status="not_applicable"` (not an error).
- **Traceability via the existing `audit_log` table** (no new
  table): `backend/torque_recommendation/audit.py` writes each
  recommendation as an ordinary `audit_log` row
  (`action="torque_recommendation"`), the same table/discriminator
  convention every other module already uses. A dedicated table was
  deliberately not created -- `audit_log.detail` is an unconstrained
  `TEXT` column with no existing precedent restricting it to
  single-line text, so the full minimum-reproducibility bundle
  (normalized request inputs, the deterministic result, validation
  outcome, confidence, warnings/critical findings, the recommended-
  or-withheld torque, and `provider_involved`, always `false` in this
  phase) fits cleanly as one canonical JSON payload in that column.
  The optional `X-Request-ID` header is stored in `audit_log.
  request_id`, matching every other authenticated write endpoint's
  convention. The caller-supplied free-text `engineering_context`
  request field is never persisted verbatim -- only its length is
  recorded. `backend.app.migrate()` was **not** touched by this
  phase -- `audit_log` already exists unconditionally.
- No proprietary/OEM-specific standard or name is exposed anywhere in
  this engine's request, response, or audit record (tested).
- `backend/app.py` touched minimally and additively: one new
  `include_router()` call, the same shape every other route module
  in this repository already uses.
- 37 new tests across `tests/torque_recommendation/
  test_beta1_engine.py` (engine-level: normal/missing/invalid inputs,
  unsupported domain, deterministic-failure propagation, confidence
  classification, warnings/assumptions, AI-independence explicitly
  proven across four provider states (not configured / enabled and
  succeeding / unavailable / actively failing), no-OEM-leak)
  and `tests/torque_recommendation/test_beta1_http_route.py`
  (HTTP-level: auth, response schema, 422 mapping, audit creation via
  the existing `audit_log` table, `X-Request-ID` correlation,
  non-regression of pre-existing `/api/ai/*` and
  `/api/engineering/joint-analysis` routes). Two pre-existing
  regression-guard tests were updated in place to reflect the new,
  legitimate route
  (`tests/ai/test_ai_disabled_noop.py::
  test_ai_gateway_package_import_registers_no_extra_routes`,
  `tests/test_faz_2_8_20_stage4_washer_resolution_closure_api.py::
  TestBackwardCompatibility::test_router_included_exactly_once`) --
  neither assertion was broadened or weakened, only its expected
  count/set extended by exactly the one new item. Full suite:
  3243/3243 passing (3206 baseline + 37 net new).
- **Note (pre-existing documentation gap, not introduced by this
  phase):** `docs/CHANGELOG.md` had no v3.0.0-alpha.6 entry before
  this phase (alpha.6 was frontend/docs/validation only); this phase
  does not backfill it, consistent with staying in its own scope.
- **Deferred / explicitly out of scope for this phase:** the
  Engineering Reasoning Engine (v3.0.0-beta.2); any LLM-based
  explanation enhancement for recommendations; automatic fastener
  selection; multi-joint optimization; OEM-specific rule exposure;
  performance/security hardening reserved for rc.1.

## v3.0.0-beta.2 — Engineering Reasoning Engine — 2026-08-12

- Added a deterministic **Engineering Reasoning Engine**
  (`backend/ai_gateway/reasoning/`) that explains an already-computed
  Faz v3.0.0-beta.1 Torque Recommendation result by `trace_id` --
  it never re-runs `backend.torque_recommendation.engine.
  recommend_torque` and never invokes any deterministic calculation
  core (`backend.calculation_engine`/`backend.vdi2230_core`/
  `backend.engineering_core`) itself. Every numeric field in
  `engineering_conclusion` is copied verbatim from the stored Beta.1
  audit payload; two AST-based tests (`test_evidence_adapter.py`,
  `test_engine.py`) statically prove the reasoning modules never
  import a recomputation path.
- Lives inside `backend.ai_gateway` (not a new top-level package, not
  inside `backend.torque_recommendation`) so it can consume Beta.1's
  output without any change to `tests/ai/
  test_dependency_direction.py`'s guarded-package list, and so
  `backend/api/routes/ai_gateway.py` -- already the sole sanctioned
  HTTP entry point for `backend.ai_gateway` -- remains the only
  consumer after this phase too.
- **Three closed reasoning states** (`backend.ai_gateway.reasoning.
  models.ReasoningState`, no numeric confidence score invented):
  `SUPPORTED` (Beta.1 produced a recommendation), `UNSUPPORTED`
  (Beta.1 withheld one, e.g. via a critical finding -- explainable,
  not an error), `INSUFFICIENT_EVIDENCE` (fail-closed: an unknown,
  corrupt, structurally incomplete, or evidence-empty stored payload
  never yields a guessed conclusion).
- **Reuses existing `backend.ai_gateway` infrastructure maximally,
  introduces no parallel architecture**: `evidence_checker.
  check_evidence` (via a new, pure data-shape
  `evidence_adapter.to_calculation_response` -- no calculation is
  performed by that adapter, only a formula-trace-to-
  `CalculationResponse` field mapping, with every per-formula
  `value` deliberately `None` since Beta.1's persisted payload does
  not retain one), `composer.compose`/`ResultLabel` (reused, not
  reimplemented, for CALCULATED/VALIDATED/ESTIMATED resolution),
  `context_builder.build_context`, the existing
  `providers.registry` singleton (no second registry), and
  `permission.ensure_active_user`/`ensure_read_only_action`.
- **Optional, structurally separate AI-generated wording layer**
  (`backend.ai_gateway.reasoning.wording`) -- the only module in the
  subpackage that ever imports an `AIModelClient`. Always fail-soft:
  an unavailable, unknown, or failing provider never affects HTTP
  status or any deterministic field, only leaves
  `ai_explanation`/`ai_explanation_provider` as `null`.
- **New HTTP surface**: `POST /api/ai/engineering-reasoning`
  (`Depends(user)`). Request body: `{trace_id, include_ai_wording,
  provider_name}` -- `trace_id` is the only required field; no raw
  engineering-parameter input path is exposed, so this endpoint
  cannot be used to duplicate Beta.1's own recommendation endpoint.
  Unknown `trace_id` -> `404`; a `trace_id` owned by a different,
  non-admin user -> `403` (ownership checked via a raw, JSON-parsing-
  free SQL lookup, so a corrupt stored payload can never block or
  leak past authorization); corrupt/incomplete stored evidence ->
  `200` with `reasoning_state="INSUFFICIENT_EVIDENCE"` (fail-closed,
  never `500`).
- **Traceability via the existing `ai_audit_records` table** (Faz
  v3.0.0-alpha.5) -- no new table, no new column. The Beta.1 source
  relationship is represented through the table's existing
  `evidence_source_ids` field:
  `[["torque_recommendation", "<beta1_trace_id>"]]`.
  `SQLiteAuditSink.record_with_latency` now additionally returns the
  new row's id (a pure return-value addition -- not part of the
  `AuditSink` ABC, no schema change, every existing caller ignores
  the return value and is unaffected) so the response can expose its
  own `reasoning_trace_id`. `X-Request-ID` is propagated into
  `ai_audit_records.correlation_id`, matching every other
  authenticated endpoint's convention.
- No proprietary/OEM-specific standard or name is exposed anywhere in
  this engine's request, response, or audit record (tested).
- 56 new tests: `tests/ai/reasoning/test_evidence_adapter.py` (9),
  `test_engine.py` (21, incl. deterministic-authority preservation,
  no-mutation, all three reasoning states, permission enforcement),
  `test_wording.py` (6, incl. provider independence and provider
  failure never raising), `test_http_route_reasoning.py` (26,
  incl. valid/unknown/cross-user/admin trace access, corrupt/
  incomplete stored evidence, no-recomputation idempotency, request-
  ID propagation, audit linkage, OEM-leak regression, Beta.1
  backward compatibility). One pre-existing regression-guard test
  was updated in place
  (`tests/ai/test_ai_disabled_noop.py::
  test_ai_gateway_package_import_registers_no_extra_routes`) to
  reflect the one new, legitimate route -- the assertion was not
  weakened, only its expected set extended by exactly this one item.
  Full suite: 3299/3299 passing (3243 baseline + 56 net new).
  flake8/`git diff --check` clean on every changed file.
- **Deviation from the Stage 0-approved design (bug found during
  implementation, not a redesign):** `backend/api/routes/
  ai_gateway.py`'s existing `_handle()` exception-mapping helper
  caught `HTTPException` in its own bare `except Exception` branch,
  which would have turned this phase's deliberate `404`/`403`
  responses into `500`. Fixed by adding an
  `except HTTPException: raise` pass-through as `_handle()`'s first
  clause -- purely additive; no other route's behaviour changes
  (verified against the full suite).
- **Deferred / explicitly out of scope for this phase:** a real,
  network-calling AI provider (only the existing offline-safe
  `deterministic` provider is exercised); reasoning support for any
  deterministic result other than Torque Recommendation (joint-
  analysis, friction, material intelligence, ...); a generic rule-
  engine implementation (`docs/08_RULE_ENGINE.md` remains a design
  spec only); a new RBAC role.

## v3.0.0-rc.1 — Performance, Security & Documentation — 2026-08-12

Release-candidate hardening phase. No new AI capability, no new
engineering engine, no product feature -- validation, security, and
documentation work only, built on the deterministic engineering core
and the Torque Recommendation / Engineering Reasoning Engines
delivered in Beta.1/Beta.2. Four commits, in order:

- **Documentation & Release Consistency**
  (`f435569db978fe338ee0b48c4ae2989b23ded43b`): `docs/314_Roadmap.md`
  synchronized with the actual repository state (Beta.1/Beta.2
  entries added, rc.1 marked in progress). `docs/07_API_SPECIFICATION.md`
  corrected: the document's original `/api/v1` target design was
  never implemented and no migration toward it is in progress or
  planned -- every real endpoint, including every one added since the
  document's baseline, uses the existing `/api/...` convention; a new
  section lists the actual current route surface, verified directly
  against `backend/api/routes/*.py` and `backend/governance/api.py`.
  `DOCUMENTATION_MANIFEST.json` checksum/metadata regenerated for the
  12 entries whose stored checksum no longer matched current file
  content.

- **Security Hardening Phase 1**
  (`5aa6f55dad0800e6c7b751901665342d72a8d1a0`): `TORQPRO_ALLOWED_HOSTS`
  (documented in `.env.example` since alpha but never read anywhere)
  is now enforced via Starlette's `TrustedHostMiddleware`, parsed as a
  comma-separated list; unset/empty keeps prior (unrestricted)
  behavior. `TORQPRO_ENV=production` now disables `/docs`, `/redoc`,
  and `/openapi.json` (FastAPI's native `docs_url`/`redoc_url`/
  `openapi_url`); every other environment, including the test suite's
  own (which never sets `TORQPRO_ENV`), is unaffected. Cross-user
  ownership regression coverage added for `calculations`/`projects`,
  which surfaced a real authorization gap: `POST /api/calculations`
  accepted any `project_id` without verifying the caller owned that
  project -- a foreign calculation could be silently attached to
  another user's project, inflating that project's
  `calculation_count` and leaking into that user's own
  `GET /api/projects/{id}/traceability` and release-package reports.
  Fixed by reusing the existing `_get_owned_project()` ownership
  check (already used by traceability/release-package) at creation
  time; no authorization semantics changed elsewhere. 34 new targeted
  tests.

- **Security Hardening Phase 2**
  (`5ce429dc3cc655af30843a548563b498fdb9e192`): a centralized,
  opt-in (`TORQPRO_API_RATE_LIMIT`, default off), per-authenticated-
  session sliding-window rate limiter for `/api/...` traffic,
  excluding `/api/login` (which keeps its own separate, stricter,
  per-username limiter, unchanged) and `/api/health`. A
  Content-Security-Policy header on every response --
  `'unsafe-inline'` for `script-src`/`style-src`, confirmed necessary
  by inspecting `frontend/index.html` (a single-file SPA: one inline
  `<script>` block, ~220 inline `style="..."` attributes) rather than
  assumed; everything else restricted to same-origin/none. A
  Strict-Transport-Security header added only when
  `TORQPRO_ENV=production`. Pre-existing `X-Content-Type-Options`/
  `X-Frame-Options`/`Referrer-Policy` unchanged. Four endpoints that
  echoed raw exception text into their client response
  (`GET /health/ready`, `GET /api/engineering/bolt-strength-classes`,
  `GET /api/engineering/nut-property-classes`,
  `POST /api/engineering/bolt-nut-compatibility`) now return a fixed,
  generic message while still logging the real exception
  server-side; every other `HTTPException(status, str(exc))` site in
  the repository was reviewed and found to already catch a specific,
  hand-authored-message domain exception type, not raw internal
  detail -- left unchanged. `pip-audit` added to
  `requirements-dev.txt` and to CI as a dedicated security-scan step;
  it reported zero known vulnerabilities against this repository's
  actual dependency set at the time of this release. 28 new targeted
  tests.

- **Performance & Reliability**
  (`245e2937863271af220308e1783302f4730f57b8`): a reusable, opt-in
  benchmark suite (`tests/performance/`, `TORQPRO_RUN_PERFORMANCE_TESTS=1`)
  measuring p50/p95/p99 latency and throughput across every critical
  path in this phase's scope -- calculation creation, project list/
  traceability/release-package, joint-analysis, the Torque
  Recommendation and Engineering Reasoning Engines, the AI gateway
  path, Question Bank retrieval, audit-log read, and health/
  readiness -- skipped by default (13 tests, ~0.06s) so the normal
  suite is unaffected. SQLite `journal_mode=WAL` and
  `busy_timeout=5000` enabled on the database connection
  (`backend/app.py`'s `conn()`/`migrate()`); WAL is set once at
  startup rather than re-checked on every connection, after measuring
  that re-issuing the pragma on an already-WAL database has a real,
  avoidable per-connection cost. Isolated (non-HTTP) micro-benchmarks
  measured a lower per-`INSERT+commit()` cost under WAL than under the
  prior default rollback-journal mode; end-to-end HTTP-level latency
  differences were within this sandbox's own run-to-run noise, which
  this changelog entry states plainly rather than extrapolating into
  a product-level performance claim. Concurrent read/write smoke
  tests (20 concurrent writers; a mixed 10-writer/10-reader scenario)
  against the real HTTP layer produced zero errors and zero lost or
  duplicated writes. Question Bank and washer-resolution JSON store
  full-file-rewrite behavior was measured at current (single-digit to
  low-hundreds of records) and synthetic larger scale; deferred as a
  redesign candidate, not a current-scale problem. No evidence of
  sync-route/threadpool saturation was found at the concurrency
  levels exercised; no `sync`→`async` rewrite was attempted. 10 new
  targeted tests (part of the normal suite, all deterministic -- no
  timing-based pass/fail assertions).

**Validation:** full suite 3371 passed, 13 skipped (the opt-in
benchmark suite) at the end of this phase, up from 3299 at the start
of rc.1 (72 new passing tests + 13 new opt-in benchmark tests).
`pip-audit` clean. `git diff --check` clean on every commit.

**Deferred / explicitly out of scope for this phase (post-v3.0):** a
strict, nonce/hash-based Content-Security-Policy (would require
restructuring `frontend/index.html`'s single inline `<script>` block
and ~220 inline `style="..."` attributes into external files); a
broad `sync`→`async` route rewrite; a JSON-to-SQLite persistence
redesign for the Question Bank/washer-resolution stores; a large
connection-count or query-shape refactor beyond the specific,
measured `journal_mode` fix above; and any hard, cross-machine
performance regression threshold (this phase's benchmark baseline is
explicitly local/informational, not a checked-in target).

## v3.0.0 — Stable Release — 2026-08-13

The stable release of TorqPro AI v3, closing the development cycle
that began at `v3.0.0-alpha.1`. This is a **release-metadata/version
transition only**: no engineering logic, no AI/reasoning behavior, no
API contract, and no security/performance control introduced in
Beta.1/Beta.2/rc.1 changed in this phase. `VERSION`,
`tests/test_version_centralization.py`, `README.md`,
`docs/314_Roadmap.md`, and this entry are the only substantive
changes, plus a narrow `.gitignore` addition for the opt-in benchmark
suite's generated `tests/performance/baseline_results.json` (hygiene,
not a feature).

**What v3.0.0 delivers, cumulatively across the full v3 cycle:**

- **Deterministic engineering core** (VDI 2230 threaded/bolted-joint
  analysis, `backend/vdi2230_core`/`backend/calculation_engine`/
  `backend/engineering_core`/`backend/standards`) remains the sole
  source of truth for every numeric engineering result -- unchanged
  and unmodifiable by any AI/reasoning layer, enforced structurally
  (AST-based dependency guards) and by test, not by convention alone.
- **Torque Recommendation Engine** (`v3.0.0-beta.1`,
  `backend/torque_recommendation/`) -- a deterministic,
  offline-capable recommendation layer over the engineering core,
  with fail-closed status/confidence classification and its own
  persisted audit trail.
- **Engineering Reasoning Engine** (`v3.0.0-beta.2`,
  `backend/ai_gateway/reasoning/`) -- explains an already-computed
  Torque Recommendation result by `trace_id`, never re-running the
  deterministic engine, with a closed three-state outcome vocabulary
  (`SUPPORTED`/`UNSUPPORTED`/`INSUFFICIENT_EVIDENCE`, no invented
  confidence score) and a structurally separate, optional,
  fail-soft AI-wording layer.
- **AI grounding, safety, explainability, and provider abstraction**
  (`v3.0.0-alpha.1`–`alpha.5`, `backend/ai_gateway/`) -- Question
  Bank-grounded retrieval, an evidence-sufficiency checker
  (PASS/WARN/FAIL), a result-label vocabulary
  (CALCULATED/VALIDATED/ESTIMATED/RECOMMENDED), a provider-abstraction
  registry with an always-available deterministic/offline provider,
  and a persistent, hash-only (never raw-text) audit trail
  (`ai_audit_records`).
- **Security hardening** (`v3.0.0-rc.1`) -- `TrustedHostMiddleware`
  via `TORQPRO_ALLOWED_HOSTS`, production-only disabling of
  `/docs`/`/redoc`/`/openapi.json`, a fixed cross-user project-
  ownership authorization gap, opt-in per-session API rate limiting,
  Content-Security-Policy on every response and
  Strict-Transport-Security in production, generic-message exception
  handling on four previously-leaking endpoints, and `pip-audit`
  wired into CI.
- **Performance validation** (`v3.0.0-rc.1`) -- an opt-in benchmark
  suite (`tests/performance/`, `TORQPRO_RUN_PERFORMANCE_TESTS=1`)
  covering every critical request path, SQLite WAL-mode tuning, and
  concurrent read/write smoke testing with zero errors/lost writes.
- **OEM/public-demo sanitization** -- no proprietary/OEM-specific
  standard name or identifier is exposed in any recommendation,
  reasoning, or audit output; verified by dedicated regression tests
  across Beta.1, Beta.2, and rc.1.
- **Documentation/release-readiness** -- `docs/314_Roadmap.md`,
  `docs/07_API_SPECIFICATION.md`, and `DOCUMENTATION_MANIFEST.json`
  synchronized with the actual repository state as of rc.1; this
  entry and `docs/releases/v3.0.0.md` close out the stable release
  record.

**Validation at stable:** full suite 3371 passed, 13 skipped (the
opt-in benchmark suite, unchanged from rc.1 since no engineering
logic changed) + 9/9 version-centralization tests passing against the
new `3.0.0` value. Opt-in benchmark suite 13/13 passed when run
explicitly. `pip-audit` clean. `git diff --check` clean.

**Deferred / explicitly out of scope (post-v3.0, unchanged from
rc.1's own deferral list):** a strict, nonce/hash-based
Content-Security-Policy; a broad `sync`→`async` route rewrite; a
JSON-to-SQLite persistence redesign for the Question Bank/washer-
resolution stores; a large connection-count or query-shape refactor;
any hard, cross-machine performance regression threshold. No new
major roadmap phase is defined as of this release.
