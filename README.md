# Current Version

| Item                          | Value                                         |
| ----------------------------- | --------------------------------------------- |
| Product                       | TorqPro                                       |
| **Current Version**           | **v2.8.16**                                   |
| **Version Date**              | **01 August 2026**                            |
| **Current Engineering Focus** | **Joint Revision List UX Improvements**       |

---

# What's New in v2.8.16

## Joint Revision List UX Improvements

Phase **2.8.16** adds server-side search, deterministic sorting, pagination, and CSV export to the existing Faz 2.8.14 joint revision governance list — entirely additive, with the pre-existing bare-array endpoint left byte-for-byte unmodified.

This phase closes the "pagination / search / export" gap the Faz 2.8.14 completion record explicitly left open, without altering any existing engineering library, persistence mechanism, calculation engine, or public write path.

The implementation was delivered across six controlled stages, each independently verified and committed:

* Stage 1 — backend query foundation (search, sort, pagination, validation)
* Stage 2 — additive, paginated API endpoint
* Stage 3 — CSV export endpoint
* Stage 4 — frontend UX (search, sort, pagination, export controls)
* Stage 5 — quality-gate integration and i18n hardening
* Stage 6 — full validation and release documentation

---

## Scope

* Added `query_joint_revision_projections()` / `query_all_joint_revision_projections()` domain query service.
* Added `GET /api/governance/joint-revisions/query` (paginated, searchable, sortable JSON endpoint).
* Added `GET /api/governance/joint-revisions/export.csv` (CSV export, UTF-8 with BOM, CSV-injection guarded).
* Added deterministic, allow-listed search/sort with an explicit tie-breaker.
* Added frontend search/sort/page-size/pagination/export controls to the existing Joint Revision List card.
* Added 24 new TR / EN `gov.jrlist.*` translation keys (full parity).
* Added a dedicated frontend regression harness (`run_joint_revision_list_ux_tests.js`), integrated into the canonical quality gate.
* Preserved the existing `GET /api/governance/joint-revisions` bare-array endpoint unchanged.
* Preserved all existing engineering libraries, APIs, and data sources.

---

# Changed Files

```text
backend/governance/joint_revision_query.py
backend/governance/joint_revision_csv.py
backend/governance/api.py

frontend/index.html

tests/governance/test_joint_revision_query.py
tests/governance/test_joint_revision_query_api.py
tests/governance/test_joint_revision_csv.py
tests/governance/test_joint_revision_csv_api.py
tests/governance/test_compatibility.py

tests/js/run_joint_revision_list_ux_tests.js
tests/js/run_governance_workspace_tests.js

tests/test_faz_2_8_11_stage4_frontend.py
tests/test_quality_gate_joint_revision_ux.py
tests/test_version_centralization.py

tools/run_quality_gate.py

docs/11_PRODUCT_BACKLOG.md
docs/phases/PHASE_2.8.16_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md
docs/phases/PHASE_2.8.16_STAGE2_API_CONTRACT.md
docs/phases/PHASE_2.8.16_STAGE3_CSV_EXPORT.md
docs/phases/PHASE_2.8.16_STAGE4_FRONTEND_UX.md
docs/phases/PHASE_2.8.16_STAGE5_FRONTEND_QUALITY_INTEGRATION.md
docs/phases/PHASE_2.8.16_COMPLETION_REPORT.md
```

---

# Validation Results

| Item           | Result                                         |
| -------------- | ----------------------------------------------- |
| Feature Branch | **feature/faz-2.8.16-joint-revision-list-ux** |
| Feature Commit | **e5de65b** (final functional commit — Stage 6 adds only version/documentation metadata in the commit immediately following) |
| Working Tree   | Clean                                          |
| Quality Gate   | **6 / 6 PASSED**                               |

---

# Backward Compatibility

Phase 2.8.16 does **not** modify:

* Existing engineering libraries
* Existing engineering databases
* Existing washer-resolution workflows
* Existing governance write paths
* Existing report engine infrastructure
* Existing VDI 2230 calculations
* The existing `GET /api/governance/joint-revisions` bare-array endpoint (response shape, ordering, and query surface all unchanged)

The implementation is fully additive: two new read-only routes were added; no existing route's signature, response shape, or behaviour changed.

---

# Engineering Notes

The following items, previously listed as out of scope for Faz 2.8.14, are now delivered (server-side, per Faz 2.8.16):

* Pagination
* Server-side sorting
* Server-side search
* CSV export

The following remain intentionally outside the current scope:

* Client-side filtering, sorting, or pagination (all search/sort/pagination stays server-side by design)
* Bulk mutation operations
* Approval workflows
* Governance registry expansion
* Cross-mechanism validation

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
| Frontend            | ✅ Passed |
| Compatibility Tests | ✅ Passed |
| Quality Gate        | ✅ Passed |

---

# Test Results

| Test Group                        | Result                 |
| ---------------------------------- | ---------------------- |
| Full pytest Suite                 | **2159 / 2159 Passed** |
| Governance Suite                  | **517 / 517 Passed**   |
| Governance Workspace JS Harness   | **160 / 160 Passed**   |
| Joint Revision List UX JS Harness | **152 / 152 Passed**   |
| TR / EN Localization Tests        | **6 / 6 Passed**       |

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
| **Phase 2.8.16** | **Joint Revision List UX Improvements**       | ⭐ **Current Version** |

---

# Version History

| Version     | Highlights                                |
| ----------- | ----------------------------------------- |
| **v2.8.16** | Joint Revision List UX Improvements       |
| v2.8.14     | Joint Revision Governance Bulk Visibility |
| v2.8.13     | Governance Workspace Integration          |
| v2.8.12     | Governance Compatibility Layer            |
| v2.8.11     | Engineering Governance Architecture       |
| v2.8.10     | Test Harness & Quality                    |
| v2.8.9      | Washer Resolution Workflow                |
| v2.8.8      | Material Intelligence                     |
| v2.8.7      | Joint Analysis & Torque Optimization      |
| v2.8.6      | Fastener Assembly Intelligence            |

---

# Roadmap

## Current Version

**v2.8.16**

Current engineering focus:

* Joint revision search and sorting
* Server-side pagination
* CSV export
* Frontend UX integration
* TR / EN localization
* Quality-gate integrated frontend regression testing
* Compatibility validation
* Regression testing

---

## Candidate Next Phases

Potential future work areas:

* Governance registry expansion
* Cross-mechanism validation
* Joint revision write-path integration
* Further governance workspace UX refinements

No subsequent phase has been officially approved yet.
