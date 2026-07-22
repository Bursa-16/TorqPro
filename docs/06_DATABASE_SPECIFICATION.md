# TorqPro Database Specification


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Objectives

The database supports local SQLite now and PostgreSQL later. It must preserve engineering history, provenance and immutable calculation snapshots.

## 2. Logical schemas

- `iam`: users, roles, sessions/audit.
- `org`: organization, license, deployment.
- `project`: projects, assemblies, joints, revisions, approvals.
- `library`: fasteners, threads, materials, coatings, lubricants, friction, tools.
- `engineering`: load cases, tightening specs, calculations, results, traces.
- `rules`: standards, editions, rule packs, rules, validation runs.
- `quality`: data packages/versions, calibration, golden cases, quality gates.
- `reporting`: reports, release packages and attachments.

SQLite may use table prefixes instead of schemas.

## 3. Core relational model

```text
organizations 1---n users
organizations 1---n projects
projects 1---n assemblies
assemblies 1---n joints
joints 1---n joint_revisions
joint_revisions 1---n joint_components
joint_revisions 1---n contact_interfaces
joint_revisions 1---n load_cases
joint_revisions 1---n tightening_specifications
joint_revisions 1---n calculation_runs
calculation_runs 1---n calculation_results
calculation_runs 1---n formula_trace_entries
calculation_runs 1---n validation_runs
validation_runs 1---n rule_results
calculation_runs 1---n reports
joint_revisions 1---n approval_records
```

## 4. Catalogue normalization

`fastener_definitions` are engineering masters. `supplier_parts` and `oem_part_approvals` implement many-to-many commercial relationships. Bolt/Nut/Washer shared fields are not duplicated without reason.

Material identity is separated from `material_property_sets`. Coating does not contain a universal friction factor. Friction is represented by `friction_conditions` with distributions and test provenance.

## 5. Key table sketches

### joint_revisions

- id UUID/integer
- joint_id FK
- revision_no
- status
- change_reason
- created_by/created_at
- submitted_at/approved_at/released_at
- row_version

Unique: `(joint_id, revision_no)`.

### calculation_runs

- id
- joint_revision_id
- engine_version
- formula_pack_version
- rule_pack_bundle_version
- input_snapshot_json
- input_snapshot_hash
- status
- started_at/completed_at
- created_by

Completed rows are immutable.

### calculation_results

- calculation_run_id
- result_code
- value_decimal
- unit_code
- status
- margin
- uncertainty_json
- explanation_summary

Unique: `(calculation_run_id, result_code, load_case_id)`.

### friction_conditions

- id
- thread_surface/coating/lubricant references
- counter-surface
- temperature/speed/reuse ranges
- mu_thread_min/nom/max
- mu_bearing_min/nom/max
- source_type/source_reference/test_report_id
- validation_status
- valid_from/to

## 6. Versioned reference data

Existing `data_packages` and `data_versions` are retained and expanded. A version activation is audited. Calculations store the exact active version IDs used. Rollback changes future active data only; it never changes prior calculation snapshots.

## 7. Attachments

Database stores metadata and hash; files are in controlled storage. Fields include original filename, media type, size, SHA-256, storage key, owner entity, classification and uploaded user/time.

## 8. Audit and immutability

Audit records are append-only. For released entities, application and database constraints prevent update/delete. Soft deletion is used for catalogue records referenced by history.

## 9. Indexes

Indexes cover project/customer/status, joint/revision, calculation timestamps, active data version, supplier/OEM part numbers, thread/diameter/property class, material grade/temperature, calibration expiry and audit entity/action/time.

## 10. Migration policy

Every schema change has numbered migration, forward transformation, rollback where safe and test. Migration history is shown in diagnostics. Direct production schema edits are prohibited.

## 11. Current-schema transition

The existing SQLite tables in `backend/app.py` remain operational. New tables are introduced incrementally. Compatibility adapters map existing project/calculation records into the new domain until migration is complete. No destructive migration occurs without backup/export test.

## 12. Faz 2.5A additions (2026-07-22)

Two new incremental table groups were added, both via the same
`backend/app.py::migrate()` idempotent-DDL convention described in §10-11
(no separate migration framework was introduced):

**Joint prerequisite** (`backend/joints/schema.py`) — minimal, real subset
of the target `joints`/`joint_revisions` model in §3, added ahead of
schedule as a dependency of production validation. See
`docs/adr/ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md` for why this
was built now instead of deferred or stubbed:

- `joints(id, project_id, joint_code, name, description, status, current_revision_id, created_by, created_at, updated_at, archived_at)`
- `joint_revisions(id, joint_id, revision_no, status, snapshot_json, change_summary, created_by, created_at, submitted_at, reviewed_by, reviewed_at, approved_at)`

**Production validation** (`backend/production_validation/repository.py`):

- `validation_studies` — references `projects`, `joints`, `joint_revisions`, `calculations`, `calculation_revisions`.
- `specification_snapshots` — immutable spec/tolerance snapshot per study; `calculation_snapshot_id` references `calculation_revisions.id` directly (no separate calculation-snapshot table — the existing `calculation_revisions.snapshot_json` already serves that role).
- `measurement_datasets`, `measurement_records` — versioned, lockable measurement storage; corrections are additive (`correction_of_id`), never overwrite.
- `tool_references` — minimal tightening/measurement tool identity; full calibration history remains future scope.

Full column list, indexes and constraints: see the `DDL` constants in the
two files above, and `docs/phases/PHASE_2.5A_PRODUCTION_VALIDATION_FOUNDATION.md`.
