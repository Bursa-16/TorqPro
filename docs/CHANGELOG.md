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
