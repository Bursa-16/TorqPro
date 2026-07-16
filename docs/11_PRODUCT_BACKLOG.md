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

## 11. Epic P2: enterprise and intelligence

- SSO/RBAC expansion.
- supplier/OEM collaboration.
- PLM/ERP/MES/tool adapters.
- advisory AI and optimization.
- private-cloud/on-premise governance.

## 12. Next approved sprint

**Sprint goal:** Documentation-integrated foundation and safe modularization.

Tasks:

1. Commit this documentation package.
2. Add `CLAUDE.md` and Copilot instructions.
3. Run current test suite and record result.
4. Create branch `refactor/modular-foundation`.
5. Extract config/security/db helpers only; no feature redesign.
6. Add tests to ensure current endpoints remain compatible.

Out of scope: new formulas, VDI compliance claims, frontend rewrite and microservices.
