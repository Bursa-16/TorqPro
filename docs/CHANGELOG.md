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
