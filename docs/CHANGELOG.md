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
