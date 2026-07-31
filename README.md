# Current Version

| Item                          | Value                                         |
| ----------------------------- | --------------------------------------------- |
| Product                       | TorqPro                                       |
| **Current Version**           | **v2.8.14**                                   |
| **Version Date**              | **31 July 2026**                              |
| **Current Engineering Focus** | **Joint Revision Governance Bulk Visibility** |

---

# What's New in v2.8.14

## Joint Revision Governance Bulk Visibility

Phase **2.8.14** introduces deterministic, additive and read-only visibility for joint revision governance data.

This phase extends the existing governance infrastructure without modifying existing engineering libraries, persistence mechanisms, calculation engines or public write paths.

The implementation provides a complete end-to-end workflow covering:

* Source accessor layer
* Governance projection layer
* Read-only API layer
* Governance workspace frontend integration
* TR / EN localization support
* Regression and compatibility validation

---

## Scope

* Added `list_joint_revisions()` source accessor.
* Added `project_joint_revisions_bulk()` governance adapter.
* Added `GET /api/governance/joint-revisions`.
* Added optional `joint_id` filtering.
* Added deterministic revision ordering.
* Added frontend governance list integration.
* Added complete TR / EN support.
* Added architecture, compatibility and regression tests.
* Preserved existing engineering libraries, APIs and data sources.

---

# Changed Files

```text
backend/joints/service.py

backend/governance/adapters/joint_revision.py

backend/governance/adapters/__init__.py

backend/governance/api.py

frontend/index.html

tests/test_joints_foundation.py

tests/governance/adapters/test_joint_revision.py

tests/governance/test_compatibility.py

tests/governance/test_joint_revision_bulk_api.py

tests/js/run_governance_workspace_tests.js

tests/test_faz_2_8_11_stage4_frontend.py

tests/test_version_centralization.py
```

---

# Validation Results

| Item           | Result                                                |
| -------------- | ----------------------------------------------------- |
| Feature Branch | **feature/faz-2.8.14-joint-revision-bulk-visibility** |
| Feature Commit | **5aa8969**                                           |
| Working Tree   | Clean                                                 |
| Quality Gate   | **6 / 6 PASSED**                                      |

---

# Backward Compatibility

Phase 2.8.14 does **not** modify:

* Existing engineering libraries
* Existing engineering databases
* Existing washer-resolution workflows
* Existing governance write paths
* Existing report engine infrastructure
* Existing VDI 2230 calculations
* Existing REST API behaviour

The implementation is fully additive.

---

# Engineering Notes

The following items are intentionally outside the current scope:

* Pagination
* Client-side sorting
* Client-side search
* Export functions
* Bulk mutation operations
* Approval workflows
* Governance registry expansion
* Cross-mechanism validation

---

# Engineering Validation

Engineering quality is continuously verified using automated validation.

## Current Validation Summary

| Validation Area     | Result   |
| ------------------- | -------- |
| Unit Tests          | ✅ Passed |
| Integration Tests   | ✅ Passed |
| Governance Tests    | ✅ Passed |
| REST API            | ✅ Passed |
| Frontend            | ✅ Passed |
| Compatibility Tests | ✅ Passed |
| Quality Gate        | ✅ Passed |

---

# Test Results

| Test Group                 | Result                 |
| -------------------------- | ---------------------- |
| Full pytest Suite          | **1919 / 1919 Passed** |
| Governance Suite           | **292 / 292 Passed**   |
| Governance JS Harness      | **160 / 160 Passed**   |
| TR / EN Localization Tests | **6 / 6 Passed**       |

Continuous integration verifies every change before integration into the main branch.

---

# Development Status

| Phase            | Description                                   | Status                |
| ---------------- | --------------------------------------------- | --------------------- |
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
| **Phase 2.8.14** | **Joint Revision Governance Bulk Visibility** | ⭐ **Current Version** |

---

# Version History

| Version     | Highlights                                |
| ----------- | ----------------------------------------- |
| **v2.8.14** | Joint Revision Governance Bulk Visibility |
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

**v2.8.14**

Current engineering focus:

* Joint revision governance
* Read-only bulk visibility
* Governance projections
* Deterministic revision tracking
* Frontend governance integration
* TR / EN localization
* Compatibility validation
* Regression testing

---

## Candidate Next Phases

Potential future work areas:

* README and documentation maintenance
* Governance pagination
* Search and filtering support
* Export capabilities
* Governance registry expansion
* Cross-mechanism validation
* User experience improvements

No subsequent phase has been officially approved yet.
