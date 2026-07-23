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
- **2.6.3 – Friction and Torque Decomposition Engine.** Percentage breakdown of thread friction / bearing friction / useful clamp-load generation on top of the existing `M_G`/`M_K` formula (`backend/engineering_core/torque.py`, `friction.py`) — additive reporting, no change to the underlying equation without a formula-spec ADR.
- **2.6.4 – Recommendation and Warning Engine.** Lubricant/friction-condition recommendation by bolt size, strength class, coating, environment, corrosion class, temperature, joint type; engineering warnings (dry-tightening scatter, anti-seize torque reduction, galling risk, etc.).
- **2.6.5 – Reporting and Integration.** PDF report sections, integration with Calculation Engine, Standards Engine, Joint Calculator without logic duplication.
- **2.6.6 – Frontend Friction Condition Workspace.** UI navigation item "Friction Condition"; sections: Overview, Lubrication, Surface Condition, Coatings, Friction Properties, Engineering Notes, References.
- **2.6.7 – Verification, Documentation and Release.** Full test coverage, ruff/black/mypy/pytest gate, documentation (SDS, API, User Guide, Developer Guide, architecture diagrams) updated.

**Compatibility constraint (all sub-phases):** the existing lubrication library is never renamed or restructured at the code/data level without a superseding ADR; no existing record or field is removed.

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
