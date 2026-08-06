# TorqPro

> Professional Fastener Engineering Platform

TorqPro is a professional engineering platform for the design, analysis, validation and optimization of threaded joints and tightening processes.

## Key Features

- VDI 2230 implementation
- Torque and preload calculation
- Friction and lubrication modelling
- Threaded joint engineering
- Fastener libraries
- Manufacturing quality analytics
- Engineering traceability
- AI-ready architecture

# Current Version

| Item                          | Value                                                    |
| ----------------------------- | --------------------------------------------------------- |
| Product                       | TorqPro                                                    |
| **Current Version**           | **v2.8.22**                                                |
| **Version Date**              | **06 August 2026**                                         |
| **Current Engineering Focus** | **Torque Study UI/UX Messaging and CI Stage-Boundary Reliability** |

---

# What's New in v2.8.22

## Torque Study UI/UX Messaging and CI Reliability

Phase **2.8.22** is a focused maintenance and release phase. It does not redesign the engineering calculation core introduced and governed in v2.8.21.

* **Example Torque Study UI/UX messaging updated.** User-facing messages in the torque-study workflow were clarified and aligned for a more consistent TR/EN experience.
* **Historical stage-boundary tests hardened in CI.** GitHub Actions now fetches full repository history so tests that depend on historical commit boundaries can run reliably.
* **Engineering core preserved.** No engineering formula, coefficient, or numerical result was intentionally changed by this maintenance phase.
* **Release metadata updated.** The canonical product version was advanced to **v2.8.22** after the feature work was merged into `main`.
* **Validation.** The recorded full regression result for this release line is **2546 passed, 0 failed**.

Relevant release commits on `main`:

```text
75a5612  chore(release): bump version to 2.8.22
97fab79  Merge pull request #36 from Bursa-16/feature/faz-2.8.22-torque-study-ui-messaging
0f2860c  ci: fetch full history for stage boundary tests
40f7b1b  Faz 2.8.22: Örnek Tork Çalışması UI/UX mesajı düzeltmeleri
```

---

# What's New in v2.8.21

## Engineering Formula Traceability and Governance Foundation

Phase **2.8.21** is governance and visibility only -- no engineering formula, coefficient, or numerical result changed. It gives the 10 live `backend.engineering_core` formulas (torque, thread friction, pitch/minor diameter, helix angle, thread shear area, material shear strength, preload, proof-load utilization, and the composite joint check behind `/api/engineering/check`) the same kind of APPROVED/PROVISIONAL/EXPERIMENTAL/DEPRECATED/UNVERIFIED traceability already proven out in `backend.vdi2230_core.trace` -- reusing that architecture, not duplicating it (`APPROVED`/`PROVISIONAL` are imported, not redefined).

* **`backend/engineering_core/trace.py` (new).** 10 formulas registered: 0 APPROVED, 9 PROVISIONAL, 1 UNVERIFIED. Torsional stress, von Mises equivalent stress, bearing/contact pressure, and a standalone tensile-stress (F/A) function were investigated and confirmed genuinely absent from the codebase -- deliberately given **no** placeholder entry.
* **`internal_thread_sf`/`external_thread_sf` now traceable.** Both previously carried no visible status. They now report PROVISIONAL, LOW confidence, the `d2`/`d3` diameter basis, the `0.5` coefficient, and a fixed list of prohibited compliance claims (ISO 16224, VDI 2230, FCA C2001, ASME) -- via an additive `formula_governance` key on `/api/engineering/check` and via the existing `/api/engineering/formula-validation` endpoint (extended, not replaced).
* **Frontend visibility.** The "Hızlı Hesap" screen -- found this phase to compute its own thread-strip safety factors independently in client-side JavaScript, never calling the backend endpoint above -- gained a small "Provisional model" / "Geçici model (Provisional)" label next to both values, using the existing i18n mechanism.
* **Thread-stripping model unchanged.** `0.5*pi*d_effective*Le` (via `d2` for internal, `d3` for external capacity) remains PROVISIONAL, confidence LOW, per the source-validation review that preceded this phase. Not redesigned.
* **36 new governance tests**, including a numerical-regression baseline locking `evaluate_joint()`'s output bit-for-bit against its pre-phase behaviour.

See `docs/phases/PHASE_2.8.21_ENGINEERING_CORE_TRACEABILITY.md` for the full delivery report.

---

# What's New in v2.8.20

## Washer Resolution Evidence & Controlled Closure (Stages 1-5)

Phase **2.8.20** adds a structured evidence trail and a controlled, evidence-backed closure workflow on top of the Faz 2.8.9/2.8.19 washer resolution decision system, delivered across five additive, independently-committed stages plus a small set of follow-up test-maintenance commits.

* **Stage 1 — Evidence domain model.** `WasherResolutionEvidence`: an immutable, checksummed Pydantic model with a closed `EvidenceType` vocabulary (authoritative standard, manufacturer document, approved engineering source, internal measurement, comparison analysis, legacy provenance reference, other) and an `EvidenceVerificationStatus` (unverified/verified/rejected). No persistence, no API, no readiness logic at this stage.
* **Stage 2 — Evidence persistence.** An append-only, locked, atomically-written evidence ledger mirroring the existing Faz 2.8.9 decision ledger's own proven file-I/O pattern exactly. No `resolution_id` validation and no idempotency at this layer (both are the service layer's job).
* **Stage 3 — Controlled closure service.** A `WasherResolutionClosure` domain model, its own append-only ledger, and orchestration (`record_resolution_evidence`, `evaluate_closure_readiness`, `close_resolution`, `get_resolution_closure`) requiring a terminal decision and at least one *verified* evidence record before a resolution can be closed. Corrupted evidence blocks closure rather than being silently dropped. No reopen mechanism anywhere.
* **Stage 4 — REST API.** Five new endpoints under `/api/library/washers/resolutions/{resolution_id}/(evidence|closure-readiness|close|closure)`, following the existing modular-router convention (`APIRouter`, `Depends(user)`, a central exception-mapping helper). `GET .../closure` returns `200 {"closure": null}`, not 404, before anything has been closed.
* **Stage 5 — Frontend workflow.** Additive Evidence List/Form, Closure Readiness, and Close Form/Result cards inside the existing washer resolution detail screen; verification status is shown, never changed, from this screen. New TR/EN translation keys and a dependency-free JS regression harness registered in the canonical quality gate, plus a short follow-up series hardening test portability and harness robustness.

**No reopen, governance sync, or reporting/export UI exists anywhere in this phase.** No backend business rule, checksum algorithm, or readiness rule was duplicated across layers -- each new layer calls the one beneath it unchanged.

**Important:** this phase delivers the *workflow*, not closed records. As of this release, the evidence and closure ledgers are both empty -- no washer resolution has been evidenced or closed by this phase; doing so remains a separate, ongoing human task using the new UI.

---

# What's New in v2.8.19

## Washer Resolution Decision Workflow Integration (Stages 1-5)

Phase **2.8.19** connects the Faz 2.8.9 washer resolution decision backend (built but never wired to any UI) to a full frontend workflow, delivered across five additive, independently-committed stages:

* **Stage 1** — additive `GET /api/library/washers/resolutions/{resolution_id}` detail endpoint, reusing `get_washer_resolution()` and `resolution_queue()` unmodified; no new business logic, no duplicated effective-status formula.
* **Stage 2** — read-only Resolution Queue + Detail frontend, listing all 76 washer resolution records with their effective status and a per-record detail lookup.
* **Stage 3** — additive decision-entry form, submitting only user-typed values to the existing, already-tested `POST /{resolution_id}/decide` endpoint (Faz 2.8.9). No status, evidence, or confidence value is inferred, suggested, or computed. Idempotency-key handling, double-submit prevention, and blocked/terminal-record disabling all read only from backend-provided fields.
* **Stage 4** — read-only Decision History view, using the existing `GET /{resolution_id}/decisions` endpoint. No edit, delete, rollback, or replay of any kind.
* **Stage 5** — this closure: VERSION/README/CHANGELOG/backlog alignment, completion report, and full regression + quality gate verification.

**No backend or API behavior changed in this phase.** All Stage 1-4 endpoints were either newly exposed as thin, additive read adapters (Stage 1) or reused verbatim from Faz 2.8.9 (Stages 2-4). No engineering value, evidence, or decision was invented anywhere in this workflow — every decision recorded through it is a human's own input, submitted through a form that only transports what was typed.

**Important:** this phase delivers the *workflow*, not resolved records. As of this release, `backend/library/data/washer_resolution_decisions.json` still contains **zero recorded decisions**, and all **76** washer resolution records in `backend/library/data/washer_resolution_ledger.json` remain unresolved (**71** `open`, **5** `blocked_authoritative_source`). None of them were closed automatically by this phase — closing any of them still requires a human to open the record in this new UI and submit their own evidence-backed decision.

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

| Test Group                 | Result                           |
| -------------------------- | -------------------------------- |
| Full pytest Suite          | **2546 / 2546 Passed**           |
| Failed Tests               | **0**                            |
| Quality Gate               | **Passed**                       |
| Historical Boundary Checks | **Passed with full Git history** |
| TR / EN UI Messaging       | **Validated**                    |

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
| Phase 2.8.18      | UI/UX Refactoring and Dashboard Improvements (Stages 1-5) | ✅ Completed           |
| Phase 2.8.19      | Washer Resolution Decision Workflow Integration (Stages 1-5) | ✅ Completed           |
| Phase 2.8.20     | Washer Resolution Evidence & Controlled Closure (Stages 1-5) | ✅ Completed           |
| Phase 2.8.21 | Engineering Formula Traceability and Governance Foundation | ✅ Completed |
| **Phase 2.8.22** | **Torque Study UI/UX Messaging and CI Stage-Boundary Reliability** | ⭐ **Current Version** |

---

# Version History

| Version     | Highlights                                             |
| ----------- | --------------------------------------------------------- |
| **v2.8.22** | Torque Study UI/UX Messaging and CI Stage-Boundary Reliability |
| v2.8.21     | Engineering Formula Traceability and Governance Foundation |
| v2.8.20     | Washer Resolution Evidence & Controlled Closure (Stages 1-5) |
| v2.8.19     | Washer Resolution Decision Workflow Integration (Stages 1-5) |
| v2.8.18     | UI/UX Refactoring and Dashboard Improvements (Stages 1-5)  |
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

**v2.8.22**

Current engineering focus:

* Example Torque Study user-facing messages refined for clearer TR/EN communication
* CI checkout configured to fetch full Git history for historical stage-boundary validation
* v2.8.21 engineering formula governance and traceability foundation preserved
* Full regression record: **2546 passed, 0 failed**
* Release version aligned to **v2.8.22**

The engineering limitations documented for v2.8.21 remain unchanged unless a later phase explicitly closes them. No ISO 16224/VDI 2230/FCA C2001/FED-STD calculation engine, torsional-stress model, von Mises equivalent-stress model, or bearing/contact-pressure implementation is claimed by this maintenance release.

---

## Candidate Next Phases

Potential future work areas:

* Frontend write UI for joints (create / submit / approve / reject screens)
* `reason` / `source` audit metadata fields for joint revisions
* Governance registry expansion
* Cross-mechanism validation
* Further governance workspace UX refinements

The next phase after v2.8.22 has not yet been formally approved in this README.
