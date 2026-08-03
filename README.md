# Current Version

| Item                          | Value                                                    |
| ----------------------------- | --------------------------------------------------------- |
| Product                       | TorqPro                                                    |
| **Current Version**           | **v2.8.18**                                                |
| **Version Date**              | **03 August 2026**                                         |
| **Current Engineering Focus** | **UI/UX Refactoring and Dashboard Improvements (Stages 1-5)** |

---

# What's New in v2.8.18

## UI/UX Refactoring and Dashboard Improvements (Stages 1-5)

Phase **2.8.18** completes the TorqPro UI/UX review improvements across Stages 1-5 (`feature/faz-stage5-final-acceptance-audit`, PR #31). Changes:

* Restricted `/api/runtime/status` to admin-only access (`Depends(admin)`) — a previously unauthenticated system-health endpoint is now access-controlled.
* Reorganized dashboard measurement KPIs.
* Added a tightening-class equipment drill-down view.
* Finalized dashboard acceptance labels.

Changed files: `backend/app.py`, `frontend/index.html`, `tests/js/run_i18n_tests.js`, plus a new authorization regression test (`tests/test_faz_stage2_system_health_authorization.py`).

This entry retroactively documents the `v2.8.18` tag/release, which had been published without an accompanying `VERSION`/README/test bump; this phase closes that gap (see `docs/CHANGELOG.md`).

---

# What's New in v2.8.17

## Joint Revision HTTP API & Idempotent Write Exposure

Phase **2.8.17** exposes the pre-existing, already-tested `backend.joints.service` domain write layer (Faz 2.5A foundation) over HTTP for the first time, and extends it with idempotent-retry support for revision creation — entirely additive, with every existing Faz 2.8.16 read-only governance endpoint and frontend screen left byte-for-byte unmodified.

This phase closes the candidate gap the Faz 2.8.16 completion record left open ("joint revision write-path integration"): the joint / joint-revision create -> submit -> approve/reject lifecycle already existed and was fully tested at the service layer (`backend/joints/service.py`), but had no HTTP surface at all.

The implementation was delivered across four controlled stages, each independently verified and committed:

* Stage 0 — scope and integration contract analysis
* Stage 1 — persistent idempotency foundation (additive schema column + partial unique index)
* Stage 2 — HTTP API (8 additive routes)
* Stage 3 — state-machine immutability regression coverage

---

## Scope

* Added an additive, nullable `idempotency_key` column to `joint_revisions`, backed by a partial unique index (`ON joint_revisions(joint_id, idempotency_key) WHERE idempotency_key IS NOT NULL`) — pre-existing rows and callers unaffected; multiple `NULL` keys remain unrestricted per joint.
* Extended `create_joint_revision()` with a keyword-only `idempotency_key` parameter (default `None`); omitting it preserves the exact pre-Stage-1 behaviour.
* Added deterministic idempotent-replay semantics: the same joint + same key + the same semantic request (snapshot compared as parsed JSON, not raw text, so key order never matters) returns the existing revision instead of creating a duplicate; a mismatched request under the same key raises a conflict instead of silently overwriting.
* Added a deterministic concurrency backstop: a genuine `sqlite3.IntegrityError` race between the idempotency lookup and the insert is recovered by re-reading and resolving the row the same way a non-racing caller would — the raw driver exception never reaches a caller.
* Added `backend/api/routes/joints.py`: 8 additive HTTP routes over the existing `backend.joints.service` layer (full list under Routes Added below).
* Added `backend/joints/schemas.py`: `JointCreate`, `JointRevisionCreate` Pydantic request models.
* Added domain-exception -> HTTP status mapping (404 / 409 / 400), following the same `_handle()` pattern already established by `backend/api/routes/production_validation.py`.
* Preserved archived-joint replay semantics: a replay of an already-successful key still returns the existing revision even after the joint is later archived; a genuinely new write against an archived joint is still rejected.
* Added 8 new domain regression tests closing a pre-existing coverage gap in the approve/reject state machine's terminal-state guards (re-approve, reject-after-approve, approve-without-review, reject-without-review, double-reject), and confirmed a revision's content is never altered once approved.
* Preserved all existing Faz 2.8.16 governance query/CSV/frontend read-only behaviour, unchanged.
* No frontend write UI was added in this release (explicitly out of scope).

---

## Routes Added

| Method | Path                                              |
| ------ | -------------------------------------------------- |
| POST   | `/api/joints`                                       |
| GET    | `/api/joints`                                       |
| GET    | `/api/joints/{joint_id}`                            |
| POST   | `/api/joints/{joint_id}/revisions`                  |
| GET    | `/api/joints/revisions/{revision_id}`               |
| POST   | `/api/joints/revisions/{revision_id}/submit`        |
| POST   | `/api/joints/revisions/{revision_id}/approve`       |
| POST   | `/api/joints/revisions/{revision_id}/reject`        |

---

# Changed Files

```text
backend/joints/schema.py
backend/joints/service.py
backend/joints/schemas.py
backend/api/routes/joints.py
backend/app.py

tests/test_joints_foundation.py
tests/test_joints_api.py
tests/test_version_centralization.py

docs/11_PRODUCT_BACKLOG.md
docs/phases/PHASE_2.8.17_COMPLETION_REPORT.md

VERSION
README.md
```

---

# Validation Results

| Item           | Result                                                                                                          |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| Feature Branch | **feature/faz-2.8.17-joint-revision-http-api**                                                                   |
| Feature Commit | **4ddb925** (final functional commit — the documentation stage adds only version/documentation metadata in the commit immediately following) |
| Working Tree   | Clean                                                                                                             |
| Quality Gate   | **6 / 6 PASSED**                                                                                                   |

---

# Backward Compatibility

Phase 2.8.17 does **not** modify:

* Existing engineering libraries
* Existing engineering databases
* Existing washer-resolution workflows
* Existing Faz 2.8.16 governance query/CSV read-only routes (response shape, ordering, and query surface all unchanged)
* Existing Faz 2.8.16 frontend Joint Revision List screen
* Existing report engine infrastructure
* Existing VDI 2230 calculations
* Existing submit/approve/reject state-machine business logic

The implementation is fully additive: 8 new routes were added; no existing route's signature, response shape, or behaviour changed.

---

# Engineering Notes

The following item, previously listed as a candidate in the Faz 2.8.16 completion entry, is now delivered:

* Joint / joint-revision HTTP write access (create, submit, approve, reject) with idempotent, retry-safe revision creation.

The following remain intentionally outside the current scope:

* Frontend write UI for joints (create, submit, approve, reject screens) — no frontend write UI in this release.
* `reason` / `source` audit metadata fields.
* A governance projection registry.
* Cross-mechanism validation.

**Known limitations** (see completion report for full detail):

* No frontend write UI.
* No `reason`/`source` audit fields.
* `JointRevisionImmutableError` has no reachable raise site in the current codebase — the write surface never mutates an approved revision's content, so an artificial `raise` was deliberately not added (see completion report, "JointRevisionImmutableError decision").
* One additional pre-existing-pattern `E402` lint finding in `backend/app.py`, structurally identical to the two the router-mount section already had (deferred import after `user`/`conn`/`audit` are defined, to avoid a circular import) — not a new category of issue, and no general `app.py` refactor was performed in this phase.

---

# Engineering Validation

Engineering quality is continuously verified using automated validation.

## Current Validation Summary

| Validation Area     | Result   |
| -------------------- | -------- |
| Unit Tests          | ✅ Passed |
| Integration Tests   | ✅ Passed |
| Governance Tests    | ✅ Passed |
| REST API            | ✅ Passed |
| Compatibility Tests | ✅ Passed |
| Quality Gate        | ✅ Passed |

---

# Test Results

| Test Group                  | Result                 |
| ----------------------------- | ---------------------- |
| Full pytest Suite             | **2201 / 2201 Passed** |
| Governance Suite              | **517 / 517 Passed**   |
| Joint-related Tests (all)     | **448 / 448 Passed**   |
| Joints API Tests              | **19 / 19 Passed**     |
| Joints Foundation Tests       | **41 / 41 Passed**     |
| TR / EN Localization Tests    | **6 / 6 Passed**       |

Continuous integration verifies every change before integration into the main branch.

---

# Development Status

| Phase            | Description                                | Status                |
| ---------------- | -------------------------------------------- | --------------------- |
| Phase 2.7        | Report Engine                                 | ✅ Completed           |
| Phase 2.8.1      | Engineering Library Audit                     | ✅ Completed           |
| Phase 2.8.2      | Thread Geometry Verification                  | ✅ Completed           |
| Phase 2.8.3      | Bolt / Nut Strength Classes                   | ✅ Completed           |
| Phase 2.8.4      | Washer Library Provenance                     | ✅ Completed           |
| Phase 2.8.5      | Washer Correction Workflow                    | ✅ Completed           |
| Phase 2.8.6      | Fastener Assembly Intelligence                | ✅ Completed           |
| Phase 2.8.7      | Joint Analysis & Torque Optimization          | ✅ Completed           |
| Phase 2.8.8      | Material Intelligence                         | ✅ Completed           |
| Phase 2.8.9      | Washer Resolution Workflow                    | ✅ Completed           |
| Phase 2.8.10     | Test Harness & Quality                        | ✅ Completed           |
| Phase 2.8.11     | Engineering Governance Architecture           | ✅ Completed           |
| Phase 2.8.12     | Governance Compatibility Layer                | ✅ Completed           |
| Phase 2.8.13     | Governance Workspace Integration              | ✅ Completed           |
| Phase 2.8.14     | Joint Revision Governance Bulk Visibility     | ✅ Completed           |
| Phase 2.8.15     | README / VERSION Maintenance                  | ✅ Completed           |
| Phase 2.8.16     | Joint Revision List UX Improvements           | ✅ Completed           |
| Phase 2.8.17      | Joint Revision HTTP API & Idempotent Write Exposure | ✅ Completed           |
| **Phase 2.8.18** | **UI/UX Refactoring and Dashboard Improvements (Stages 1-5)** | ⭐ **Current Version** |

---

# Version History

| Version     | Highlights                                             |
| ----------- | --------------------------------------------------------- |
| **v2.8.18** | UI/UX Refactoring and Dashboard Improvements (Stages 1-5)  |
| v2.8.17     | Joint Revision HTTP API & Idempotent Write Exposure        |
| v2.8.16     | Joint Revision List UX Improvements                       |
| v2.8.14     | Joint Revision Governance Bulk Visibility                 |
| v2.8.13     | Governance Workspace Integration                          |
| v2.8.12     | Governance Compatibility Layer                             |
| v2.8.11     | Engineering Governance Architecture                        |
| v2.8.10     | Test Harness & Quality                                      |
| v2.8.9      | Washer Resolution Workflow                                  |
| v2.8.8      | Material Intelligence                                       |
| v2.8.7      | Joint Analysis & Torque Optimization                        |

---

# Roadmap

## Current Version

**v2.8.18**

Current engineering focus:

* Dashboard measurement KPI reorganization
* Tightening-class equipment drill-down
* Admin-only restriction on `/api/runtime/status`
* Dashboard acceptance label finalization
* Retroactive version/documentation alignment for the previously-unversioned v2.8.18 tag

---

## Candidate Next Phases

Potential future work areas:

* Frontend write UI for joints (create / submit / approve / reject screens)
* `reason` / `source` audit metadata fields for joint revisions
* Governance registry expansion
* Cross-mechanism validation
* Further governance workspace UX refinements

No subsequent phase has been officially approved yet.
