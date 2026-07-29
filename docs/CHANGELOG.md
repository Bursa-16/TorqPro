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
