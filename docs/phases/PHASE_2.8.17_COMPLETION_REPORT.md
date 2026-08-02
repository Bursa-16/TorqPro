# Faz 2.8.17 — Completion Report

**Joint Revision HTTP API & Idempotent Write Exposure**

Status: **Complete (Stages 0–3)**
Delivered: 2026-08-02
Branch: `feature/faz-2.8.17-joint-revision-http-api`
Final functional commit: `4ddb925719de7a0033817b944a9d1aa19d3c4547` (Stage 3)

---

## 1. Scope Summary

Faz 2.8.17 exposes the pre-existing, already-tested `backend.joints.service`
domain write layer (Faz 2.5A) over HTTP for the first time, and extends it
with idempotent-retry support for revision creation. It closes the
candidate gap the Faz 2.8.16 completion entry left open ("joint revision
write-path integration"), with one correction discovered during Stage 0:
the write path already existed and was already fully tested at the
service layer — the actual gap was the absence of any HTTP surface for
it. The phase was renamed from "Joint Revision Write-Path Integration"
to **"Joint Revision HTTP API & Idempotent Write Exposure"** to reflect
what was genuinely delivered.

### In scope (delivered)

* Idempotent joint revision creation foundation (Stage 1)
* Joint write HTTP API — 8 additive routes (Stage 2)
* `JointCreate` and `JointRevisionCreate` request models
* Domain exception → HTTP status mapping
* Deterministic `sqlite3.IntegrityError` concurrency recovery (non-threaded, monkeypatch-verified)
* Archived-joint replay semantics
* State-machine immutability regression coverage (Stage 3)
* Backward compatibility with every existing Faz 2.8.16 read-only behaviour

### Explicitly out of scope

* Frontend joint write UI (create / submit / approve / reject screens)
* `reason` / `source` audit metadata fields
* A new governance registry
* A new write workflow / mechanism
* An artificial `raise` site for `JointRevisionImmutableError`
* Any general, phase-unrelated refactor

---

## 2. Stage-by-Stage Summary

### Stage 0 — Scope and Integration Contract Analysis

Established that `backend/joints/service.py` (Faz 2.5A) already contains a
fully tested, transactional, audited write service
(`create_joint`, `create_joint_revision`, `submit_joint_revision`,
`approve_joint_revision`, `reject_joint_revision`) with zero HTTP callers
anywhere in the repository. Evaluated three integration options and
selected **Option A** — a thin HTTP adapter directly over the existing
service, mirroring `backend/api/routes/production_validation.py`'s
established pattern — as the minimal, lowest-risk, most evidence-based
choice. Rejected a general-purpose write CRUD API and a speculative
domain-event/adapter layer, neither of which had repository evidence
supporting the added complexity.

### Stage 1 — Persistent Idempotency Foundation

* Added an additive, nullable `idempotency_key TEXT` column to
  `joint_revisions`, backfilled onto pre-existing databases via the same
  `PRAGMA table_info` + conditional `ALTER TABLE ADD COLUMN` idiom already
  used in `backend/app.py::migrate()`.
* Added a partial unique index —
  `CREATE UNIQUE INDEX ux_joint_revisions_idempotency_key ON
  joint_revisions(joint_id, idempotency_key) WHERE idempotency_key IS NOT
  NULL` — chosen over a table-level `UNIQUE` constraint because SQLite has
  no `ALTER TABLE ... ADD CONSTRAINT`; a partial index achieves the same
  guarantee additively, without a full table rebuild, and leaves every
  pre-existing `NULL`-key row (and any future `idempotency_key=None` call)
  completely unrestricted.
* Extended `create_joint_revision()` with a keyword-only
  `idempotency_key: str | None = None` parameter. `idempotency_key is
  None` is byte-for-byte the pre-Stage-1 behaviour.
* Replay semantics: the same `(joint_id, idempotency_key)` pair with a
  semantically identical request (`snapshot` compared as a parsed dict,
  not a raw string — so key order never matters — plus `change_summary`
  and `created_by`) returns the existing revision; a mismatched request
  under the same key raises `JointRevisionConflictError` with a fixed,
  generic message that never echoes snapshot content, a file path, SQL,
  or a raw driver exception.
* Concurrency backstop: a `sqlite3.IntegrityError` raised by the partial
  unique index (a genuine race between the lookup and the insert) is
  caught, the transaction rolled back, and the row re-read and resolved
  exactly as a non-racing caller would be — the raw driver exception
  never propagates out of `create_joint_revision()`.
* 13 new service-layer tests added to `tests/test_joints_foundation.py`.

### Stage 2 — HTTP API

* Added `backend/joints/schemas.py`: `JointCreate`, `JointRevisionCreate`
  Pydantic request models. `idempotency_key` travels as an ordinary
  nullable request-body field — no HTTP header was invented for it, since
  Stage 0's contract never specified one.
* Added `backend/api/routes/joints.py`: 8 additive routes, following
  `backend/api/routes/production_validation.py`'s established pattern
  exactly (`APIRouter`, `Depends(user)`, a central `_handle()`
  domain-exception → `HTTPException` mapping helper, no business logic or
  SQL in the route layer).
* Mounted additively in `backend/app.py`, in the same deferred-import
  position (after `user`/`conn`/`audit` are defined) that
  `production_validation_router` and `governance_router` already use, for
  the same circular-import-avoidance reason.
* 19 new HTTP-level tests added in a new file, `tests/test_joints_api.py`,
  covering all 17 required scenarios (idempotency replay, conflicts,
  cross-joint key reuse, reordered-JSON-key equivalence, no-leak
  assertions, archived-joint replay/new-write/conflict, 404/401 cases, and
  a router-mount smoke test).
* 2 additional deterministic (non-threaded) `sqlite3.IntegrityError`
  race-recovery tests added to `tests/test_joints_foundation.py`, using a
  connection-wrapping `monkeypatch` technique instead of real threads —
  no flaky concurrency test was introduced.

### Stage 3 — State-Machine Immutability Regression Coverage

Analyzed every `UPDATE joint_revisions` statement in
`backend/joints/service.py` (three: `submit_joint_revision`,
`approve_joint_revision`, `reject_joint_revision`) and confirmed none of
them ever writes `snapshot_json` or `change_summary` — no function in the
current write surface (service layer or the Stage 2 HTTP routes) can
alter a revision's content after creation, in any status.

**`JointRevisionImmutableError` decision**: this exception is defined and
exported by `backend.joints.exceptions` / `backend.joints.service`, but
has **no reachable raise site** anywhere in the codebase, because no code
path exists that could attempt to mutate an approved revision's content
in the first place. Per the explicit Stage 3 instruction, no artificial
`raise` was added for it (that would be a fabricated call site with no
real precondition), and the exception was neither removed nor refactored
(out of scope). It is recorded here as a **known, accepted limitation**.

The invariant "immutable after approval" that this domain *does* provide
is enforced through a different, already-used exception —
`JointRevisionStateError`'s existing `status != "review"` /
`status != "draft"` guards in `submit_joint_revision` /
`approve_joint_revision` / `reject_joint_revision`. That enforcement had
no test coverage for its terminal-state corners before this Stage. 8 new
tests were added to `tests/test_joints_foundation.py` to close that gap:

1. Cannot approve an already-approved revision
2. Cannot reject an already-approved revision
3. Cannot approve a rejected revision
4. Cannot reject an already-rejected revision
5. Cannot approve a draft revision without submitting first
6. Cannot reject a draft revision without submitting first
7. An approved revision's content (snapshot/change_summary/revision_no/created_by) is byte-for-byte unchanged across every rejected further transition attempt
8. `JointRevisionImmutableError` is imported/exported but never raised anywhere in `backend.joints.service` — asserted as an executable, self-verifying fact, not only a prose claim

---

## 3. Models

* `JointCreate` (`backend/joints/schemas.py`)
* `JointRevisionCreate` (`backend/joints/schemas.py`)

## 4. Routes

| Method | Path                                          |
| ------ | ---------------------------------------------- |
| POST   | `/api/joints`                                   |
| GET    | `/api/joints`                                   |
| GET    | `/api/joints/{joint_id}`                        |
| POST   | `/api/joints/{joint_id}/revisions`              |
| GET    | `/api/joints/revisions/{revision_id}`           |
| POST   | `/api/joints/revisions/{revision_id}/submit`    |
| POST   | `/api/joints/revisions/{revision_id}/approve`   |
| POST   | `/api/joints/revisions/{revision_id}/reject`    |

---

## 5. Test Results

| Test Group                     | Result                 |
| -------------------------------- | ---------------------- |
| `tests/test_joints_api.py`       | **19 / 19 Passed**     |
| `tests/test_joints_foundation.py`| **41 / 41 Passed**     |
| Joint-related tests (all)        | **448 / 448 Passed**   |
| `tests/governance`                | **517 / 517 Passed**   |
| `tests/test_version_centralization.py` | **9 / 9 Passed**  |
| Full `pytest` suite              | **2201 / 2201 Passed** |
| Canonical quality gate           | **6 / 6 PASSED**       |

Governance suite unchanged from the Faz 2.8.16 baseline — no governance
mechanism code was touched. TR/EN key parity unchanged (6/6) — no new
translation keys were added, since no frontend code was touched.

---

## 6. Backward Compatibility

Verified unchanged:

* Every existing Faz 2.8.16 governance query/CSV read-only route
  (response shape, ordering, and query surface)
* The existing Faz 2.8.16 frontend Joint Revision List screen
* Existing washer-resolution workflows, engineering libraries, and
  calculation engines
* Existing submit/approve/reject state-machine business logic
* Every existing `backend/joints/service.py` call signature for
  `idempotency_key is None` (the pre-Stage-1 behaviour)

The implementation is fully additive: 8 new routes and 1 new nullable
column were added; no existing route's signature, response shape, or
persisted data changed.

---

## 7. Architectural Decision Record

**No new ADR was added.** This phase adds a thin HTTP adapter layer and
an additive idempotency column over an already-existing domain service
(`backend/joints/service.py`, Faz 2.5A) and its already-existing SQLite
tables. It introduces no new persistence mechanism, no new governance
concept, and no architectural pattern not already established by
`backend/api/routes/production_validation.py`. The same reasoning the
Faz 2.8.14/2.8.16 entries applied to the read-only query/CSV layer
applies here to the write layer.

---

## 8. Known Limitations

* No frontend write UI for joints in this release.
* No `reason`/`source` audit metadata fields (recorded as a backlog
  candidate, not scheduled).
* `JointRevisionImmutableError` has no reachable raise site (see §2,
  Stage 3, for the full analysis). This is a deliberate, evidence-based
  decision, not an oversight.
* `backend/app.py` carries one additional `E402` lint finding
  (`flake8 --max-line-length=100`), structurally identical to the two the
  `production_validation`/`governance` router-mount imports already have
  (a deferred import placed after `user`/`conn`/`audit` are defined, to
  avoid a circular import). Verified: baseline (`main`) had 2162 total
  `flake8` findings in `backend/app.py`; this branch has 2163 — a net +1,
  entirely accounted for by this one line. No general `app.py` refactor
  was performed in this phase.

---

## 9. Non-Goals (Explicitly Deferred)

* Frontend write UI for joints
* `reason`/`source` audit metadata fields
* A governance projection registry
* Cross-mechanism validation
* An artificial raise site for `JointRevisionImmutableError`
* Any general `backend/app.py` refactor

---

## 10. Possible Next-Phase Candidates (none approved by this report)

(A) Frontend write UI for joints — no approved need identified yet;
(B) `reason`/`source` audit metadata fields — recorded as a backlog
candidate; (C) governance registry / cross-mechanism validator — still
premature, unchanged from prior entries; (D) further governance
workspace UX refinements — only if real usage demonstrates an actual
need, none shown yet.
