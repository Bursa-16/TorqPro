# TorqPro Documentation Index


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## Reading order

All developers and AI coding agents must read the documents in this order before changing code:

1. `12_CLAUDE_CONTEXT.md`
2. `00_PROJECT_VISION.md`
3. `01_DOMAIN_MODEL.md`
4. `02_SYSTEM_ARCHITECTURE.md`
5. `03_ENGINEERING_WORKFLOW.md`
6. `05_ENGINEERING_FORMULA_SPECIFICATION.md`
7. `06_DATABASE_SPECIFICATION.md`
8. `07_API_SPECIFICATION.md`
9. `11_PRODUCT_BACKLOG.md`
10. `13_DEVELOPER_GUIDE.md` and `14_TESTING_STRATEGY.md`

## Document map

| Document | Purpose |
|---|---|
| `00_PROJECT_VISION.md` | Product purpose, scope, users, commercial direction and boundaries |
| `01_DOMAIN_MODEL.md` | Canonical domain concepts and relationships |
| `02_SYSTEM_ARCHITECTURE.md` | Approved modular-monolith architecture and evolution path |
| `03_ENGINEERING_WORKFLOW.md` | End-to-end user and engineering lifecycle |
| `04_UI_SCREEN_TREE.md` | Complete screen tree and interaction rules |
| `05_ENGINEERING_FORMULA_SPECIFICATION.md` | Formula catalogue, symbols, units, validity and validation status |
| `06_DATABASE_SPECIFICATION.md` | Logical and physical data model |
| `07_API_SPECIFICATION.md` | Resource-oriented API contract |
| `08_RULE_ENGINE.md` | Versioned standards and customer-rule execution model |
| `09_LIBRARY_SPECIFICATION.md` | Fastener, material, coating, friction and tool libraries |
| `10_AI_ENGINE.md` | Advisory AI boundaries and architecture |
| `11_PRODUCT_BACKLOG.md` | Delivery epics, priorities and acceptance criteria |
| `12_CLAUDE_CONTEXT.md` | Mandatory instructions for Claude/Copilot/Blackbox and other agents |
| `13_DEVELOPER_GUIDE.md` | Coding, branching, review and documentation rules |
| `14_TESTING_STRATEGY.md` | Unit, integration, regression, engineering validation and release gates |
| `15_DEPLOYMENT.md` | Local, Docker, on-premise and future cloud deployment |
| `CHANGELOG.md` | Documentation and architecture changes |
| `adr/` | Architecture Decision Records |

## Current implementation truth

TorqPro_24 is a FastAPI + SQLite + single-page HTML/PWA application. It already includes authentication, users and roles, project/revision/approval records, calculation storage, an engineering pre-check endpoint, reference-data packages and version activation, calibration cases, quality gates, release packages, enterprise licensing, deployment diagnostics, PWA support, Docker and go-live/DNS checks.

As of Faz 2.5A (2026-07-22), it also includes a minimal `backend/joints/` identity-and-revision layer (prerequisite for production validation — see `docs/adr/ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md`) and a `backend/production_validation/` module (`ValidationStudy`, `MeasurementDataset`, `MeasurementRecord`, `SpecificationSnapshot`, `ToolReference`) with its own thin API router at `backend/api/routes/production_validation.py`. Process capability math (Cp/Cpk/Pp/Ppk/Cmk), SPC and automated production approval are **not** implemented — see `docs/phases/PHASE_2.5A_PRODUCTION_VALIDATION_FOUNDATION.md`.

The current calculation capability is an **engineering pre-evaluation**, not a certified VDI 2230 solver. Existing reports explicitly distinguish between “approved production release” and “engineering preliminary evaluation.” This honesty must be preserved.

## Repository policy

- Do not store copyrighted standards in full unless licensing permits it.
- Store standard identifiers, editions, derived implementation rules, provenance and test evidence.
- Never silently change an engineering formula or reference dataset.
- Every calculation must be reproducible from an immutable input snapshot, engine version, formula-pack version and rule-pack version.
- AI output is advisory. Deterministic code remains the calculation authority.
