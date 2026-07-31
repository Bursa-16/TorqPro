# Phase 2.8.12 Stage 4.2 — Read-Only Joint Revision Governance Adapter

- Status: **Stage 4.2 complete** (2026-07-30). Phase 2.8.12 as a whole
  is **not** complete — Production Validation and Legacy Calculation
  Revisions remain assessment-only (Stage 4 findings: NO-GO this
  phase); `joints.status` → `PublicationStatus` was explicitly not
  implemented (out of scope per this stage's instructions); Stage 5
  (final phase-wide release pass) has not started.
- Depends on: `docs/adr/ADR-0014-engineering-governance-architecture.md`,
  `docs/adr/ADR-0015-washer-resolution-governance-integration.md`,
  the Stage 4 assessment and Stage 4.1 spike (chat-recorded; no
  standalone doc — see this document's Sec. 1 for the reproduced
  evidence).

## 1. Stage 4.1 circular-import evidence (reproduced here for record)

`backend.joints.service` imports `conn`/`audit`/`now_iso` from
`backend.app` **at its own module level**. `backend.app` imports
`backend.governance.api` at its own module level (the Stage
4/2.8.11-approved router mount, `backend/app.py` line 1814). An
isolated spike (disposable clone, deleted after use — no production
code was ever modified) proved empirically:

- Importing a joints-dependent adapter shape **before** anything else
  → succeeds (the joints import transitively loads all of
  `backend.app`, which itself already loads `backend.governance.api`
  as part of its own execution).
- Importing `backend.governance.api` directly, in a process that has
  never touched `backend.app`, **while a joints-dependent module is
  wired in at `governance/api.py`'s own module level** → **real,
  deterministic `ImportError`**: `cannot import name 'router' from
  partially initialized module 'backend.governance.api' (most likely
  due to a circular import)`.
- The same scenario with the joints import moved to a **deferred
  (function-body) import** → succeeds, in every tested order
  (adapter-first, `governance.api`-first, normal `backend.app`-first,
  pytest-collection order, clean `__pycache__`, `importlib.reload`).

This is the same mitigation `backend/api/dependencies.py`'s own
module docstring already documents and uses for the identical problem
with `backend.app.conn`.

## 2. Delayed-import invariant

`backend/governance/adapters/joint_revision.py`:

- Module level: `from backend.joints.exceptions import
  JointRevisionNotFoundError` and `from backend.joints.schema import
  JOINT_REVISION_STATUSES` — both files have **zero** dependency on
  `backend.app` (verified: neither contains any import beyond `from
  __future__ import annotations`), so both are safe at module level.
- `backend.joints.service` is imported **only** inside
  `_joints_service()`, called once per `project_joint_revision()`
  invocation — never at module level.
- Mechanically enforced (not just documented) by
  `tests/governance/test_compatibility.py`:
  `test_joint_revision_adapter_module_level_imports_are_safe_only`,
  `test_joint_revision_service_is_imported_only_inside_a_function_body`,
  plus three subprocess-based clean-process regression tests
  (`test_governance_api_importable_in_a_clean_process`,
  `test_joint_revision_adapter_importable_and_callable_in_a_clean_process`,
  `test_joint_revision_adapter_safe_after_normal_app_initialization`)
  and a reload-safety test.

## 3. Exact projection mapping

Source of truth: `backend.joints.schema.JOINT_REVISION_STATUSES =
("draft", "review", "approved", "rejected")`. Verified against the
current repository (not assumed from documentation).

| Source (`joint_revisions.status`) | Governance (`ReviewStatus`) |
|---|---|
| `draft` | `DRAFT` |
| `review` | `UNDER_REVIEW` |
| `approved` | `APPROVED` |
| `rejected` | `REJECTED` |

An import-time assertion (`assert set(JOINT_REVISION_STATUSES) ==
set(_STATUS_MAP)`) fails loudly if the source schema and this
module's mapping table ever drift apart — no silent gap possible.

## 4. Authority boundary

`joint_revisions` (SQLite, via `backend.joints.service`) remains the
sole authoritative source. This adapter:

- never writes to `joints`/`joint_revisions`,
- never calls a governance transition command
  (`submit_review`/`approve_review`/`reject_review`/etc.),
- never calls `store.append()` or imports
  `backend.governance.store`/`backend.governance.service`,
- exposes no `create_`/`submit_`/`approve_`/`reject_`/`resolve_`/
  `waive_`/`append(`/`write(`/`save(`/`update(`/`delete(` function
  (tested directly, mirroring the Stage 5 washer adapter's own
  guarantee),
- contains no raw SQL (tested directly — `SELECT `/`INSERT `/
  `UPDATE `/`DELETE `/`conn()` all absent from the file).

The existing "a reviewer cannot approve their own revision" rule
(`backend/joints/service.py::approve_joint_revision`) remains entirely
within the source mechanism — the adapter does not observe, enforce,
or weaken it; it is exercised as a regression guard in this stage's
own test suite
(`test_existing_self_approval_rule_still_enforced_independently_of_governance`).

## 5. Unsupported / error behaviour

`ProjectionOutcome` (closed, purpose-built — not washer's
`MappingQuality`, since joint revisions have no partial-mapping case):

| Outcome | When |
|---|---|
| `supported` | Status is one of the four known values |
| `not_found` | No `joint_revisions` row with this id |
| `unsupported_status` | Row exists, `status` is a well-formed but unrecognized string |
| `invalid_source_record` | Row exists but `status` is missing, `None`, or non-string; or the record itself isn't a dict |
| `source_unavailable` | The read itself failed (import failure, SQLite error, or any other read-path exception) |

Never guesses a canonical status for `unsupported_status`/
`invalid_source_record`. Never leaks a filesystem path, raw SQL,
traceback, or internal exception string for `source_unavailable`
(tested directly with a deliberately distinctive path/exception-type
substring planted in a simulated failure).

## 6. Intentionally excluded (this stage)

- `joints.status` → `PublicationStatus` — not implemented (per this
  stage's explicit scope; `superseded` has no live code path in
  `backend/joints/service.py` today, making that projection
  incomplete/misleading if attempted).
- Production Validation — NO-GO per Stage 4 assessment (overlapping
  review/publication concepts in one mutable `status` column; no
  append-only decision ledger).
- Legacy Calculation Revisions — NO-GO per Stage 4 assessment (no
  separate service module; logic embedded directly in
  `backend/app.py` route handlers; an adapter would require a
  pre-refactor, which violates additive-only).
- No write synchronization of any kind for joint revisions (that
  would be a separate, future, explicitly-approved stage — not
  implied by this one).
- No `joint_revision` entry added to
  `backend/governance/ownership.py`'s `RESTRICTED_AGGREGATE_TYPES` —
  this stage creates no write path, so there is nothing to protect
  against.
- No production API route added or modified.

## 7. Files intentionally unchanged

`backend/joints/service.py`, `schema.py`, `exceptions.py`,
`__init__.py` (byte-identical — verified via `git diff --quiet`),
`backend/production_validation/*.py` (byte-identical), `backend/app.py`
(unchanged beyond the pre-existing Stage 3 washer-sync call site —
zero new diff from Stage 4.2), `backend/governance/ownership.py`,
`enums.py`, `events.py`, `models.py`, `service.py`, `store.py`,
`transitions.py`, `exceptions.py`, `api.py`,
`backend/governance/adapters/washer_resolution.py`,
`washer_resolution_sync.py`, `washer_resolution_reconciliation.py`.
