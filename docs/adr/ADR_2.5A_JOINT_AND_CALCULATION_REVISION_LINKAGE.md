# ADR 2.5A — Joint/JointRevision Prerequisite and Calculation-Revision Linkage

> **Status:** Accepted
> **Date:** 2026-07-22
> **Related phase:** Faz 2.5A — Production Validation Foundation

## 1. Context

Faz 2.5A's `ValidationStudy` domain model requires `joint_id` and
`joint_revision_id` as mandatory foreign keys, per `docs/01_DOMAIN_MODEL.md`
and `docs/302_Measurement_Data_Model.md`. At the start of this phase, the
running code had no `Joint` or `JointRevision` table or domain object:
`backend/app.py` only has flat `projects` and `calculations` /
`calculation_revisions` tables. `docs/06_DATABASE_SPECIFICATION.md §11`
already anticipated this gap ("existing SQLite tables … remain operational
… compatibility adapters map existing project/calculation records into the
new domain until migration is complete"), but the adapter/migration itself
had not been built.

Per `docs/12_CLAUDE_CONTEXT.md §1` and `docs/README.md`, code/documentation
conflicts require stopping and raising the conflict rather than silently
inventing an architecture. This was raised before coding began. The product
owner's decision, recorded here, is the resolution.

## 2. Why nullable Joint fields were rejected

Making `joint_id` / `joint_revision_id` nullable would let a validation
study exist with no verifiable link to the bolted-joint engineering context
it validates. That defeats the traceability purpose of Faz 2.5A: a
production torque measurement without a joint reference cannot be
compared against the design intent it is supposed to confirm.

## 3. Why a temporary stub was rejected

A stub (an empty placeholder row with no lifecycle) would satisfy the FK
constraint but not the traceability requirement, and would need to be
reworked when the real Joint aggregate from `docs/01_DOMAIN_MODEL.md`
eventually lands — creating throwaway work and a second migration.

## 4. Decision: minimal, real Joint/JointRevision foundation

`backend/joints/` was added as a prerequisite package, in its own commits,
ahead of the production_validation domain:

- `joints(id, project_id, joint_code, name, description, status,
  current_revision_id, created_by, created_at, updated_at, archived_at)`
  — `UNIQUE(project_id, joint_code)`, FK to `projects(id)`.
- `joint_revisions(id, joint_id, revision_no, status, snapshot_json,
  change_summary, created_by, created_at, submitted_at, reviewed_by,
  reviewed_at, approved_at)` — `UNIQUE(joint_id, revision_no)`.
- Lifecycle: joint status `draft -> active -> superseded -> archived`
  (soft-delete only, no physical delete); revision status
  `draft -> review -> approved | rejected`, immutable once approved,
  self-approval blocked (mirrors the existing `calculation_revisions`
  approval pattern already in `backend/app.py`).

Explicitly out of scope for this prerequisite (see phase doc for full
list): full component tree/BOM, bolt/nut/washer selection UI, joint
calculation orchestration, geometry editor, and any change to the existing
`calculation_revisions` approval workflow. This is identity and revision
traceability only — enough for production_validation to reference a real,
queryable, and eventually re-approvable engineering context, not a
replacement for the target `JointRevision` aggregate described in
`docs/01_DOMAIN_MODEL.md`.

## 5. Why both `calculation_id` and `calculation_revision_id` are kept

The phase brief's `ValidationStudy.calculation_id` was expanded into two
fields:

- `calculation_id` → `calculations.id`: the stable "which calculation
  family/record" reference, useful for querying and grouping without
  caring which revision was current at validation time.
- `calculation_revision_id` → `calculation_revisions.id`: the exact,
  versioned, potentially-approved calculation result the validation study
  is actually checking against.

Using only `calculations.id` is insufficient: that row is mutable (there
is no revision concept at that table level) and does not by itself pin
down an approval/revision context — the same `calculation_id` can have
many revisions with different snapshots.

Using only `calculation_revision_id` is also insufficient on its own: it
would still resolve to a `calculation_id` via a join, but keeping the
direct FK avoids an extra join for the common "list validation studies for
calculation X" query and matches the same duplication already accepted for
`joint_id` + `joint_revision_id`.

A service-layer integrity rule (see §6) guarantees the two never diverge.

## 6. Referential integrity rules

Enforced in `backend/production_validation/service.py::create_study`
inside the same database transaction as the insert (SQLite does not carry
these particular cross-table equalities as declarative constraints):

```text
calculation_revision.calculation_id == validation_study.calculation_id
joint_revision.joint_id            == validation_study.joint_id
joint.project_id                   == validation_study.project_id
```

Plain FK constraints (existence) are declared at the schema level for all
five relationships; the three equality rules above are business rules
layered on top and checked before insert, with plain
`backend.production_validation.exceptions.ValidationDataError` on
violation. Indexes exist on all five FK columns (see
`backend/production_validation/repository.py::DDL`) to keep these joins
and the equality-check queries fast.

## 7. Immutable validation snapshot

At study creation, `SpecificationSnapshot` is written once, in the same
transaction as the study row, referencing:

- the resolved `calculation_revision_id` directly as
  `calculation_snapshot_id` — no separate "calculation snapshot" table was
  introduced, because `calculation_revisions.snapshot_json` (already
  written by the existing revision-creation flow in `backend/app.py`) is
  already an immutable, sufficient snapshot of the calculation state; and
- the tolerance/spec values (`lower_spec_limit`, `upper_spec_limit`,
  `nominal_value`, `target_value`, `characteristic_name`, `unit`) plus
  provenance (`source_standard`, `source_document`, `source_revision`,
  `rule_pack_version`) supplied at study-creation time.

A `snapshot_hash` (SHA-256 over the sorted JSON payload) is stored
alongside for tamper-evidence. Later changes to the underlying calculation
or specification data do not retroactively change a study's snapshot —
verified by `tests/production_validation/test_service.py
::test_specification_snapshot_immutable_after_later_changes`.

## 8. Consequences

- Faz 2.5A ships two extra commits (`feat(joints): …`) ahead of the
  production_validation commits; this is intentional and called out
  separately in the phase report, not folded into "production validation"
  scope.
- `backend/joints/` is a genuine, minimal, forward-compatible foundation.
  It does not need to be thrown away when the full `Joint` aggregate from
  `docs/01_DOMAIN_MODEL.md` is eventually implemented; it needs to be
  extended (component tree, interfaces, load cases, full approval
  workflow), not replaced.
- `docs/06_DATABASE_SPECIFICATION.md` and `docs/301-313` phase stubs are
  updated to reflect that `joints` / `joint_revisions` now exist in code,
  with an explicit note that they are a minimal subset of the target
  aggregate.
