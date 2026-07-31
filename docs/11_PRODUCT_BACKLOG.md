# TorqPro Product Backlog and Release Plan


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Prioritization

P0 protects engineering truth and creates a sellable Professional foundation. P1 builds competitive maturity. P2 adds enterprise scale and differentiation.

## 2. Release 24 documentation baseline

- Add complete SDS and AI-agent context.
- Preserve current application behavior.
- Record current endpoints/features and known limits.
- Establish ADR and change-control process.

Acceptance: all docs present, no placeholder-only files, README reading order, package builds/runs unchanged.

## 3. Epic P0-A: modularization

Stories:

- Extract configuration, database, security and audit from `app.py`.
- Create module packages without endpoint changes.
- Add migration framework.
- Add lint/type/test configuration.

Acceptance: existing tests pass; routes are thin; no engineering formula in route handlers.

## 4. Epic P0-B: canonical project/joint model

- Add assemblies, joints and joint revisions.
- Add components, interfaces and load cases.
- Enforce revision state and immutability.
- Migrate existing project/revision data with compatibility.

Acceptance: create/open/revise/submit/approve/release workflow and traceability tests.

**Partial delivery (Faz 2.5A, 2026-07-22):** minimal `joints` /
`joint_revisions` identity-and-revision-traceability layer delivered as a
prerequisite for the production validation domain — see
`docs/adr/ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md`. Assemblies,
components, interfaces, load cases and the full joint design workflow
remain open for a future phase.

## 5. Epic P0-C: unit-safe engineering core

- Define quantities and units.
- Create formula registry and trace.
- Wrap current engineering pre-check as `preliminary_v1` pack.
- Implement corrected load-sharing primitives.
- Mark all validation status.

Acceptance: dimensional tests, golden cases and no unsupported production claim.

## 6. Epic P0-D: library governance

- Normalize fastener/material/friction models.
- Import current JSON/XLSX through staged packages.
- Preserve source/version/approval.
- Calculation snapshot references active versions.

## 7. Epic P0-E: Professional report

- Detailed input/result/formula/rule/provenance sections.
- PDF/JSON output.
- Immutable calculation source.
- Approval and release package.

## 8. Epic P1-A: quick forecast packs

- FIAT 01391 forecast selector where licensed.
- Clear estimate warnings and assumptions.
- FIAT 01393/01 validation pack.
- Golden-case dataset.

## 9. Epic P1-B: detailed core

- Detailed torque decomposition.
- Bolt/clamped stiffness.
- preload range, residual clamp, service stress.
- separation, slip, bearing and thread checks.
- settlement and thermal modules after validation.

## 10. Epic P1-C: manufacturing quality

- Tool assets/calibration history.
- Tightening stages and sequence.
- capability/SPC import and dashboards.
- manufacturing instructions and process release.

**Partial delivery (Faz 2.5A, 2026-07-22):** production validation
measurement data model, CSV import, minimal `tool_references` and
audit/traceability delivered — see
`docs/phases/PHASE_2.5A_PRODUCTION_VALIDATION_FOUNDATION.md`. Capability
indices (Cp/Cpk/Pp/Ppk/Cmk), control limits and process release decisions
remain open for Faz 2.5B/2.5C.

## 11. Epic P2: enterprise and intelligence

- SSO/RBAC expansion.
- supplier/OEM collaboration.
- PLM/ERP/MES/tool adapters.
- advisory AI and optimization.
- private-cloud/on-premise governance.

## 12. Faz 2.6 – Friction Condition Module

**Naming (2026-07-23 rename directive):** the epic and module are named **Friction Condition**, not "Lubrication Module" / "Lubrication Engineering Module". Lubrication is a subsection of Friction Condition, not the module itself. "Lubrication Module"/"Lubrication Engineering Module" remain valid only when referring specifically to lubricant data (the existing `LUBRICATION_LIBRARY` dataset).

**Rationale:** the module must own the complete friction condition of a bolted joint — lubrication, coatings, surface condition/finish, thread and bearing friction behaviour, and their effect on preload/tightening torque — not lubricant selection alone. See `docs/adr/ADR-0009-friction-condition-module.md` and `docs/09_LIBRARY_SPECIFICATION.md` §10.

**Module responsibilities:** Lubrication; Surface Condition; Surface Finish; Coating; Thread Condition; Bearing Surface Condition; Friction Model; Overall Friction Coefficient; Thread Friction (future); Bearing Friction (future); Nut Factor (future); Scatter (future); Galling Risk; Corrosion Influence; Temperature Influence; Torque Correction; Engineering Warnings.

**Sub-phases:**

- **2.6.0 – Architecture & Specification.** Schema/architecture decision, `docs/09_LIBRARY_SPECIFICATION.md` and `docs/05_ENGINEERING_FORMULA_SPECIFICATION.md` updates, ADR-0009, source-traceability field design, Tablo 9.4-scoped reference data (15 records, combined coefficient only, no mu_thread/mu_bearing/K). **Delivered 2026-07-23** — see `docs/phases/PHASE_2.6.0_FRICTION_CONDITION_ARCHITECTURE.md`.
- **2.6.1 – Friction Condition Schema Extension (Lubrication subsection).** Any further schema work the Faz 2.6.0 ADR defers (e.g. Surface Condition/Coating as independent record types vs. free-text fields). **Delivered 2026-07-23** — see `docs/phases/PHASE_2.6.1_FRICTION_CONDITION_SCHEMA_EXTENSION.md`. Concept separation documented on `LubricationRecord` (8 concepts); 8 new opt-in validator checks added (`backend/library/validator.py`, `validate_lubrication_library`); no `FrictionCoefficientSet` model introduced yet (ADR-0009 trigger not met). Surface Condition/Coating independence still open.
- **2.6.2 – Verified Data Population.** Independently sourced mu_thread/mu_bearing/K/scatter/max-temperature/corrosion-resistance/reusability values per lubricant, each with a cited, approved source. No value added without one (`docs/12_CLAUDE_CONTEXT.md` §4).
  - **2.6.2A – Coating and Friction Data Ownership Decision.** **Delivered 2026-07-23** — see `docs/adr/ADR-0010-coating-lubrication-friction-data-ownership.md` and `docs/phases/PHASE_2.6.2A_COATING_FRICTION_DATA_OWNERSHIP.md`. Decision: Option D (hybrid) — `CoatingRecord`/`LubricationRecord` keep owning identity data (10/23 live records, unchanged); new `FrictionConditionRecord` (schema only, 0 live records) owns combination-dependent friction values going forward. Migration plan for the 15 Tablo 9.4 records defined, not executed.
  - **2.6.2B – Verified Data Population (execution).** **Delivered 2026-07-23** — see `docs/phases/PHASE_2.6.2B_VERIFIED_FRICTION_DATA_POPULATION.md`. 18 `FrictionConditionRecord`s populated, all deterministically re-homed from already-approved `CoatingRecord`/`LubricationRecord` ISO 16047/ISO 4042 ranges — no coefficient invented. Tablo 9.4 migration and independent mu_thread/mu_bearing/K/scatter/temperature data remain blocked on missing sources (see phase doc source matrix). Reference-integrity and duplicate-combination validators added.
- **2.6.3 – Friction and Torque Decomposition Engine.** **Delivered (readiness only) 2026-07-23** — see `docs/phases/PHASE_2.6.3_FRICTION_AWARE_TORQUE_MODEL.md`. Investigation finding: no formula in this codebase can consume a single combined friction coefficient without either deriving K or copying it into mu_thread/mu_bearing (both forbidden). New `backend.calculation_engine.friction_readiness` module added (additive): resolves `friction_condition_id`, reports calculation-mode readiness and a friction-coefficient min/nominal/max sensitivity range — computes no torque value. `/api/engineering/check` gains an optional `friction_condition_id` field (backward compatible). Mode B (separated model) has zero qualifying records; infrastructure only.
- **2.6.4 – Recommendation and Warning Engine.** **Delivered (deterministic warnings + readiness only, no recommendation engine) 2026-07-23** — see `docs/phases/PHASE_2.6.4_FRICTION_RECOMMENDATION_WARNING_FRAMEWORK.md`. New `backend.calculation_engine.friction_recommendations` module (additive): deterministic, field-derived engineering warnings (combined-friction, reference-only, restricted-legacy, missing-source, torque-calculation); recommendation-readiness levels (`warnings_only`/`comparison_only` for all 18 live records — none reaches `engineering_recommendation_ready`/`production_recommendation_ready`, asserted by test); purely descriptive comparison capability (never states which condition is "better"). New additive `POST /api/friction-condition/assess` endpoint; `/api/engineering/check` unaffected.
- **2.6.5 – Reporting and Integration.** **Delivered 2026-07-23** — see `docs/phases/PHASE_2.6.5_FRICTION_REPORTING_INTEGRATION.md`. Investigation finding: no PDF/HTML report generator exists yet in this codebase (`docs/310_Reporting.md` is a placeholder). New additive `backend.calculation_engine.friction_report` module formats Faz 2.6.3/2.6.4 results (readiness, warnings, comparison) into a JSON `FrictionConditionReportSection`, with source traceability (checksum, existing data-file version) and deterministic safety labels. New additive `POST /api/friction-condition/report-preview` endpoint (Option B, no existing report request model to extend). `/api/engineering/check` and `/api/friction-condition/assess` unaffected.
- **2.6.6 – Frontend Friction Condition Workspace.** **Delivered (minimal, single-workspace) 2026-07-23** — see `docs/phases/PHASE_2.6.6_FRICTION_CONDITION_FRONTEND_WORKSPACE.md`. Navigation item "Friction Condition" added to `frontend/index.html` (single-file structure preserved, no new framework/bundler); sections: Overview, Overall Friction Range, Recommendation Readiness, Engineering Warnings, Comparison, Source & Traceability/Report Preview, all as cards within one workspace page. New additive `GET /api/friction-condition` list endpoint. Browser-verified (Playwright, 1366×768/1024×768/390×844) with no console errors specific to this feature, no horizontal overflow, no clipped warning text.
- **2.6.7 – Verification, Documentation and Release.** Full test coverage, ruff/black/mypy/pytest gate, documentation (SDS, API, User Guide, Developer Guide, architecture diagrams) updated.

**Compatibility constraint (all sub-phases):** the existing lubrication library is never renamed or restructured at the code/data level without a superseding ADR; no existing record or field is removed.

## 12A. Faz 2.8.8 – Material Intelligence, Engineering Formula Validation and Recommendation Engine (TR/EN)

**Delivered** 2026-07-29 (approved 2026-07-28) — see `docs/adr/ADR-0012-material-intelligence-formula-validation.md` and `docs/phases/PHASE_2.8.8_MATERIAL_INTELLIGENCE_FORMULA_VALIDATION.md` for full detail, including the final verified test counts (81 dedicated backend tests, 28 JS harness assertions, 1337/1337 full pytest suite, zero regression) and TR/EN parity result (29/29 `mi.*` keys, 100% parity).

Investigation finding: `backend/library/material_library.py` is a Phase 1.3 metadata-only shell (`status="draft"`, `record_count=0`), but real data already exists and is wired through `backend.library.population.find_material()` — 8 real, sourced records in `backend/library/data/material_library.json` (`MaterialRecord` model, Faz 2.4.2B), every one `validation_status="reference_only"`, `approval_status="pending"`, `confidence=3`. `backend/calculation_engine/formula_registry.py` is an intentionally empty engine-level scaffold; the only populated formula catalog is `backend.vdi2230_core.trace` (7 entries, 2 `APPROVED` / 5 `PROVISIONAL`), kept independent by design. No recommendation engine of any kind exists.

Scope (additive only, no existing module modified except `backend/app.py` route registration and `frontend/index.html` navigation):

- **Material Intelligence** (`backend.calculation_engine.material_intelligence`): deterministic requirement-matching and comparison over the 8 existing `MaterialRecord`s — no new material data invented, no coefficient added.
- **Formula Validation** (`backend.calculation_engine.formula_validation`): read-only aggregation and validation of the existing `vdi2230_core.trace` and `calculation_engine.formula_registry` catalogs (via their existing public accessors). Never edits either catalog's classification.
- **Engineering Recommendation Engine** (part of `material_intelligence`): follows the Faz 2.6.4 readiness-gated philosophy exactly — a `MaterialRecommendationResult` states its `readiness_level`, which capabilities are available/blocked, and *why* a higher level is not reached (data is uniformly `reference_only`/`pending`), instead of guessing. Ranking is quantitative and deterministic (margin against a stated numeric requirement), always carries an explicit "engineering sign-off required before production use" disclaimer, and never claims a value it cannot support.
- **TR/EN from day one**: known limitation carried since Faz 2.6.8 (frontend comment, `frontend/index.html`) is that backend warning/report prose is free-text and English-only, deliberately left untranslated because there is no closed vocabulary. Faz 2.8.8 does not retrofit older phases, but its own new warnings/messages use a stable `code` plus a bilingual `{tr, en}` text pair from the start — the fix Faz 2.6.8 described as out of scope is applied here for all new content.
- **Reporting**: `material_intelligence_report` follows the `friction_report.py` / `strength_class_report.py` pattern (deterministic JSON + Markdown, no wall-clock timestamp, checksum-traceable, selected-language preserved in export).
- New additive endpoints: `GET /api/library/materials`, `GET /api/library/materials/{id}`, `POST /api/engineering/material-recommendation`, `GET /api/engineering/formula-validation`. No existing endpoint is changed.

## 12B. Faz 2.8.9 – Washer Resolution Decision Workflow (TR/EN)

**Delivered** 2026-07-29 — see
`docs/adr/ADR-0013-washer-resolution-decision-workflow.md` and
`docs/phases/PHASE_2.8.9_WASHER_RESOLUTION_DECISION_WORKFLOW.md` for
full detail, including final verified test counts (188/188 Faz 2.8.9
tests across 6 stages, 1525/1525 full pytest suite, zero regression,
32/32 Node harness, 1097/1097 existing i18n harness) and TR/EN parity
result (38/38 `wrr.*` keys, 100% parity).

Faz 2.8.5 left 76 washer correction/resolution records read-only (71
`open`, 5 `blocked_authoritative_source`); closing any of them
requires real evidence this codebase cannot invent
(`docs/12_CLAUDE_CONTEXT.md` §4). Faz 2.8.9 does not close any of
them — it adds the workflow mechanism that lets a human record such a
decision safely: an append-only decision ledger
(`washer_resolution_decisions.json`, separate from and never
overwriting the Faz 2.8.5 source ledger), a closed state machine (no
reopening a terminal decision, no deciding a blocked-source record
through this workflow), an idempotency-key-first decision API, and an
`effective_status` overlay computed from the two ledgers together
without ever mutating the source one. Reporting (Stage 4/5A) is
strictly read-only and additive to the existing
`washer_report.py`/`GET /api/library/washers/resolutions/*`
surface — no existing field renamed or removed, no effective-status
logic duplicated between the report, the API and the frontend. The
frontend workspace (`page-washerresolution`) never guesses a value
for an incomplete or malformed report response.

**Known follow-up (out of scope for this phase):** while building and
verifying this phase's own JS test harness
(`tests/js/run_washer_resolution_report_tests.js`), a pre-existing,
unrelated weakness was found in `tests/js/run_material_intelligence_tests.js`
(Faz 2.8.8): its asynchronous test scenarios are not awaited before
the harness process exits, so their assertions never actually run,
even though the harness reports a "clean" result. Not fixed here
(explicitly out of scope for Faz 2.8.9); a future phase should
refactor that harness into the same awaited `async function main()`
pattern this phase's own harness now uses.

## 12C. Faz 2.8.10 – Test Harness & Quality (TR/EN)

**Delivered** 2026-07-29 — see
`docs/phase_2_8/phase_2_8_10_completion_report.md` for full detail
(bilingual TR/EN), including the Stage 1 quality-audit findings, the
Stage 2 shared pytest fixtures, the Stage 3 shared JS harness module
and global TR/EN parity guard, the Stage 4 repository quality-gate
runner (`tools/run_quality_gate.py`), and final verified test counts
(1559/1559 full pytest suite, clean-clone-verified).

Test-infrastructure and quality-tooling phase — no production
calculation, API, or frontend behavior changed. No ADR was added for
this phase: it introduces no new architectural pattern or
irreversible design decision for future phases to reference, so the
completion report is the appropriate and sufficient record.

## 12D. Faz 2.8.11 – Engineering Governance Architecture and Decision
Workflow Standardization (Stages 1–5, complete)

**Delivered** 2026-07-30 — see
`docs/adr/ADR-0014-engineering-governance-architecture.md`,
`docs/phases/PHASE_2.8.11_ENGINEERING_GOVERNANCE_ARCHITECTURE.md`, and
`docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md` (bilingual
final report) for full detail.

A read-only repository analysis performed before this phase began
found four independent, already-shipped governance mechanisms with
overlapping responsibility and inconsistent vocabulary: the
Production Validation workflow (Faz 2.5A), the legacy calculation-
revision review/approve/reject workflow in `backend/app.py`, the
joint revision lifecycle (`backend/joints/`, ADR-0003), and the
Washer Resolution Decision Workflow (Faz 2.8.9, ADR-0013). Building a
fifth bespoke "Engineering Decision Audit & Approval Workflow" — the
phase's original framing — was assessed as a fragmentation risk, not
a fix. The phase scope was revised, before any code was written, to a
**standardization phase**, delivered across five stages:

- **Stage 1** (docs-only): ADR-0014 — the canonical model. Three
  independent lifecycle groups (review, publication/revision,
  resolution), a canonical field-name set, transition/audit/
  idempotency/revision-lineage principles, compatibility and
  migration strategy.
- **Stage 2**: `backend/governance/enums.py` (`ReviewStatus`,
  `PublicationStatus`, `ResolutionStatus`, `LifecycleGroup`, closed
  transition tables), `models.py` (`ReviewDecision`/
  `PublicationDecision`/`ResolutionDecision`, `extra="forbid"`,
  required-field validation per ADR-0014's table), `transitions.py`
  (shared fail-closed transition checking), `exceptions.py`.
- **Stage 3**: `backend/governance/events.py`
  (`GovernanceEvent`), `store.py` (`FileGovernanceEventStore` —
  append-only, atomic writes, Windows-compatible locking, corruption
  detection, no default data path), `service.py` (nine
  idempotency-first command functions + effective-status/history/
  latest-event read accessors; idempotency is resolved *before*
  transition validation so a legitimate retry survives state
  progression; `previous_status` is never caller-suppliable).
- **Stage 4**: `backend/governance/api.py` (11 additive routes under
  `/api/governance`, mounted onto `backend.app.app`, reusing the
  existing `user` auth dependency; `actor` derived from the
  authenticated user only; lazy `TORQPRO_GOVERNANCE_EVENT_STORE_PATH`
  store provider, safe 503 when unconfigured) and a generic,
  domain-agnostic bilingual `page-governance` frontend workspace
  (53/53 TR/EN key parity).
- **Stage 5**: one read-only compatibility adapter,
  `backend/governance/adapters/washer_resolution.py`, projecting the
  existing Faz 2.8.9 washer resolution workflow onto the canonical
  vocabulary (71 exact + 5 explicitly unsupported mappings across all
  76 real ledger records, zero guessed values); Production
  Validation, the legacy calculation-revision workflow, and joints
  were deliberately **not** adapted in this phase (all three require
  a live SQLite connection to read, which a first read-only adapter
  should not force into `backend/governance/`'s dependency graph);
  and the pre-existing async defect in
  `tests/js/run_material_intelligence_tests.js` (see below) was
  fixed.

**No existing table, JSON ledger, API endpoint, enum, or transition
graph was modified anywhere in this phase.** No data was migrated. No
field was renamed. The Faz 2.8.9 washer resolution workflow is
unchanged and was verified byte-identical before/after every adapter
call. No existing mechanism imports `backend.governance`, except the
one Stage 4-approved router mount in `backend/app.py`; no governance
module imports an existing mechanism, except the one Stage 5-approved
adapter file, which is read-only and exposes no mutation/persistence
method.

**Resolved follow-up:** the pre-existing async test-harness gap in
`tests/js/run_material_intelligence_tests.js` (Faz 2.8.8, first
documented in ADR-0013's Consequences and §12B above) is fixed as of
this phase — its 19 scenarios now run through an awaited
`async function main()`, matching the pattern already used by the
washer-resolution and governance-workspace harnesses. Fixed under a
narrow, test-file-only, no-production-code-touched change, with a
regression-guard assertion-count test and a deliberate-failure proof
performed before and after the fix.

## 12E. Faz 2.8.12 Stage 2 – Washer Governance Synchronization and
Reconciliation (TR/EN)

**Status: Stage 2, Stage 3, Stage 4 (assessment), Stage 4.1 (spike),
and Stage 4.2 (joint revision read-only adapter) complete
(2026-07-30). Stage 5 not started.**

Controlled adoption of the Faz 2.8.11 governance architecture for the
one existing mechanism whose decision workflow maps cleanly onto it:
washer resolution. Scope was corrected during Stage 1 assessment to
exclude every module without a real, existing decision/approval
workflow (Material Intelligence, Fastener Assembly Intelligence,
Recommendation logic, report modules, the Quality Harness, and future
VDI 2230 extensions) — see
`docs/adr/ADR-0015-washer-resolution-governance-integration.md` for
the full rationale.

Delivered this stage:

- `backend/governance/ownership.py` — closed aggregate-type registry
  + HTTP-only guard (409) preventing the generic governance write
  endpoints from becoming a second write path for washer-owned
  aggregates.
- `backend/governance/adapters/washer_resolution_sync.py` —
  `sync_washer_decision()`: best-effort, never-raising, deterministic
  synchronization, reusing the Stage 5 adapter's canonical status
  mapping (no second mapping table).
- `backend/governance/adapters/washer_resolution_reconciliation.py` —
  `reconcile()`: mandatory, idempotent, dry-run-capable batch
  reconciliation delegating every record to `sync_washer_decision()`.
- `tools/run_washer_governance_reconciliation.py` — explicitly
  invoked CLI, dry-run by default.
- `tests/governance/test_compatibility.py` updated to reflect
  ADR-0015's 3-file mechanism-import allowlist (was 1), with new
  AST-based tests proving the write path never bypasses
  `backend.governance.service` or duplicates its logic.

**Explicitly not done this stage** (Stage 3): wiring
`sync_washer_decision` into
`backend.library.washer_resolution_service.decide_resolution` or the
`POST /api/library/washers/resolutions/{resolution_id}/decide`
endpoint. `backend/app.py` and every washer production module are
unchanged.

**Stage 3 delivered** (same day): wired `sync_washer_decision_and_log`
into the real washer decide endpoint, immediately after the
authoritative washer decision succeeds. Public API contract
unchanged and verified (same URL/schema/status/error mapping — no
governance field added to the response). Safe structured logging via
the project's existing logger. `backend/app.py`'s governance-import
allowlist widened from 1 to 3 approved lines (documented, tested).
Washer production modules and the immutable ledger remain unchanged
(SHA256-verified). See
`docs/phases/PHASE_2.8.12_STAGE3_CONTROLLED_WRITE_INTEGRATION.md`.

**Stage 4 delivered** (assessment only, same day): evaluated
Production Validation, Legacy Calculation Revisions, and Joint
Revision Lifecycle against the governance architecture. Production
Validation and Legacy Calculation Revisions: **NO-GO** this phase
(overlapping review/publication status in one mutable column;
embedded raw SQL with no service-module boundary, respectively).
Joint Revision Lifecycle: **conditional GO**, `joint_revisions.status`
only, pending an isolated circular-import spike.

**Stage 4.1 delivered** (spike, same day): isolated PoC (disposable
clone, deleted after use) empirically proved a real circular-import
risk between any governance file and `backend.joints.service`, and
proved the existing `backend/api/dependencies.py` deferred-import
pattern mitigates it in every tested order.

**Stage 4.2 delivered** (same day): read-only
`backend/governance/adapters/joint_revision.py`, projecting
`joint_revisions.status` onto governance `ReviewStatus` using the
Stage 4.1-proven deferred-import mitigation. `joints.status`,
Production Validation, and Legacy Calculation Revisions remain
untouched. See
`docs/phases/PHASE_2.8.12_STAGE4_2_JOINT_REVISION_READ_ONLY_ADAPTER.md`.

**No existing table, JSON ledger, API endpoint, enum, or transition
graph was modified.** The washer resolution ledger and decision store
are unchanged (SHA256-verified before/after). `backend.governance`'s
mechanism-import boundary is explicitly widened from 1 to 4 approved
files across Stages 5/2/4.2 (ADR-0015's established pattern extended,
not silently loosened) — the widening is documented, tested, and the
allowlist remains closed and exact.

## 13. Next approved sprint

**Sprint goal:** Documentation-integrated foundation and safe modularization.

Tasks:

1. Commit this documentation package.
2. Add `CLAUDE.md` and Copilot instructions.
3. Run current test suite and record result.
4. Create branch `refactor/modular-foundation`.
5. Extract config/security/db helpers only; no feature redesign.
6. Add tests to ensure current endpoints remain compatible.

Out of scope: new formulas, VDI compliance claims, frontend rewrite and microservices.
