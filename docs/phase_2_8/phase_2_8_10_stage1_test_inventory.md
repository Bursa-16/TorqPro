# Phase 2.8.10 — Stage 1: Test Inventory

**Baseline commit:** `d80046a`. Generated via `pytest --collect-only -q` and direct inspection; not hand-estimated.

**Totals:** 81 Python test files + 5 Node JS harnesses = **86 test artifacts**, **1525 pytest test cases**, all passing, 0 skipped in a fully-provisioned environment (Node present).

## 1. Core engineering library & standards (VDI 2230, models, migration)

| File | Tests | Covers |
|---|---:|---|
| `tests/test_vdi2230_core.py` | 94 | VDI 2230 core formulas: stress area, preload, stiffness, load factor, units, trace |
| `tests/test_vdi2230_provider.py` | 28 | VDI2230 calculation-engine provider adapter |
| `tests/test_library_migration.py` | 53 | Legacy → Pydantic library migration path |
| `tests/test_faz2_4_2b_library_schema_completion.py` | 72 | Faz 2.4.2B schema completion across all domain models |
| `tests/test_faz2_4_1b_bolt_nut_engineering_database.py` | 63 | Bolt/nut engineering database population (Faz 2.4.1B) |
| `tests/test_faz2_4_1c_washer_engineering_database.py` | 35 | Washer engineering database (Faz 2.4.1C) |
| `tests/test_faz2_4_1c_joint_hardware_infrastructure.py` | 25 | Joint hardware infrastructure (Faz 2.4.1C) |
| `tests/test_thread_database_faz2_4_1a.py` | 22 | Thread geometry database (Faz 2.4.1A) |
| `tests/test_library_models.py` | 12 | Pydantic domain models |
| `tests/test_library_validation.py` | 6 | `validate_library()` structural checks |
| `tests/test_library_validator_schema.py` | 3 | `validate_schema()` typed-schema bridge |
| `tests/test_library_loader_typed.py` | 3 | `load_typed()` |
| `tests/test_library_registry_typed.py` | 7 | Typed registry |
| `tests/test_library_oem_adapter.py` | 6 | `oem_library.py` adapter |
| `tests/test_typed_record_cache.py` | 13 | Typed record caching layer |
| `tests/test_loader.py` | 7 | Base loader |
| `tests/test_registry.py` | 5 | `BaseLibrary`/`LibraryMetadata` |
| `tests/test_search.py` | 12 | Library search |
| `tests/test_standards_engine.py` | 9 | Standards registry (ISO/DIN/EN/FIAT/VDI2230) |
| `tests/test_oem_reference_errors.py` | 7 | OEM reference error handling |
| `tests/test_population.py` | 8 | `population.py` data-loading orchestration |
| `tests/test_metadata.py` | 9 | Library metadata |
| `tests/test_golden_records.py` | 7 | Golden-record regression fixtures |
| `tests/test_version_centralization.py` | 9 | Version-string centralization |
| `tests/test_engineering_library.py` | 18 | Engineering library facade |
| `tests/test_calculation_engine_scaffold.py` | 10 | Calculation-engine scaffold/provider contract |
| `tests/test_joints_foundation.py` | 9 | Joint domain foundation |
| **Subtotal** | **527** | |

## 2. Faz 2.6.x — Friction / lubrication architecture

| File | Tests | Covers |
|---|---:|---|
| `tests/test_faz2_6_0_lubrication_architecture.py` | 24 | Lubrication architecture (Faz 2.6.0) |
| `tests/test_faz2_6_2a_coating_friction_data_ownership.py` | 17 | Coating/friction data ownership (ADR-0010) |
| `tests/test_faz2_6_2b_verified_friction_data_population.py` | 23 | Verified Friction Condition population |
| `tests/test_faz2_6_3_friction_aware_torque_model.py` | 21 | Friction-aware torque model |
| `tests/test_faz2_6_4_friction_recommendation_warnings.py` | 33 | Friction recommendation/warning framework |
| `tests/test_faz2_6_5_friction_reporting_integration.py` | 35 | Friction reporting integration |
| `tests/test_faz2_6_6_friction_condition_frontend_workspace.py` | 27 | Friction Condition frontend workspace (incl. `node --check` syntax gate) |
| `tests/test_faz2_6_8_friction_condition_i18n.py` | 4 | Wraps `tests/js/run_i18n_tests.js` (JS harness, see §7) |
| **Subtotal** | **184** | |

## 3. Faz 2.8.2–2.8.5 — Thread geometry, strength classes, washer provenance/correction

| File | Tests | Covers |
|---|---:|---|
| `tests/test_faz_2_8_2_thread_geometry_verification.py` | 29 | ISO 724/68-1 thread geometry verification |
| `tests/test_faz_2_8_3_bolt_nut_strength_classes.py` | 100 | Largest single suite. Bolt/nut strength classes, compatibility engine, validation |
| `tests/test_faz_2_8_4_washer_provenance.py` | 29 | Washer provenance manifest/report |
| `tests/test_faz_2_8_5_washer_correction_workflow.py` | 64 | Washer correction workflow (ledger, report, business rules) |
| **Subtotal** | **222** | |

## 4. Faz 2.8.6–2.8.8 — Assembly intelligence, joint analysis, material intelligence

| File | Tests | Covers |
|---|---:|---|
| `tests/test_faz_2_8_6_fastener_assembly_intelligence.py` | 34 | Deterministic assembly-intelligence engine |
| `tests/test_faz_2_8_6_assembly_intelligence_api.py` | 34 | Assembly intelligence API endpoints |
| `tests/test_faz_2_8_6_assembly_intelligence_report.py` | 35 | Assembly intelligence report generation |
| `tests/test_faz_2_8_6_stage4_frontend.py` | 20 | Wraps `tests/js/run_assembly_intelligence_tests.js` |
| `tests/test_faz_2_8_7_joint_analysis.py` | 34 | Joint analysis & torque optimization engine |
| `tests/test_faz_2_8_7_frontend.py` | 21 | Wraps `tests/js/run_joint_analysis_tests.js` |
| `tests/test_faz_2_8_8_material_intelligence.py` | 42 | Material intelligence engine |
| `tests/test_faz_2_8_8_formula_validation.py` | 16 | Formula validation module |
| `tests/test_faz_2_8_8_frontend.py` | 23 | Wraps `tests/js/run_material_intelligence_tests.js` |
| **Subtotal** | **259** | |

## 5. Faz 2.8.9 — Washer resolution decision workflow

| File | Tests | Covers |
|---|---:|---|
| `tests/test_faz_2_8_9_washer_resolution_workflow.py` | 47 | Decision domain model, state machine, append-only ledger schema (Stage 1) |
| `tests/test_faz_2_8_9_stage2_persistence.py` | 20 | Append-only persistence, checksum integrity, idempotency (Stage 2) |
| `tests/test_faz_2_8_9_stage3_api.py` | 32 | API endpoints, orchestration, error mapping (Stage 3) |
| `tests/test_faz_2_8_9_stage4_report.py` | 26 | Bilingual resolution report (Stage 4) |
| `tests/test_faz_2_8_9_stage5_backend.py` | 27 | Report-status expansion backend (Stage 5) |
| `tests/test_faz_2_8_9_stage5_frontend.py` | 36 | Wraps `tests/js/run_washer_resolution_report_tests.js` (Stage 5) |
| **Subtotal** | **188** | |

## 6. Production Validation module (`tests/production_validation/`)

| File | Tests | Covers |
|---|---:|---|
| `tests/production_validation/test_api.py` | 11 | Validation-study/dataset API |
| `tests/production_validation/test_csv_import.py` | 10 | CSV measurement-data import |
| `tests/production_validation/test_models.py` | 5 | Pydantic models |
| `tests/production_validation/test_repository.py` | 5 | Repository/persistence layer |
| `tests/production_validation/test_service.py` | 7 | Service orchestration |
| `tests/production_validation/test_state_transitions.py` | 10 | Study/dataset state machine |
| `tests/production_validation/test_traceability.py` | 8 | Traceability linkage |
| `tests/production_validation/test_validators.py` | 8 | Business-rule validators |
| **Subtotal** | **64** | Has its own `conftest.py` with fixtures + shared builder functions — the best-organized corner of the suite (see Gap Report §2.2). |

## 7. JS regression harnesses (Node, invoked directly or via pytest subprocess wrapper)

| File | Assertions (approx., self-reported) | Wrapped by |
|---|---:|---|
| `tests/js/run_i18n_tests.js` | 4174 lines, largest harness | `tests/test_faz2_6_8_friction_condition_i18n.py` |
| `tests/js/run_assembly_intelligence_tests.js` | 576 lines | `tests/test_faz_2_8_6_stage4_frontend.py` |
| `tests/js/run_joint_analysis_tests.js` | 562 lines | `tests/test_faz_2_8_7_frontend.py` |
| `tests/js/run_material_intelligence_tests.js` | 511 lines | `tests/test_faz_2_8_8_frontend.py` |
| `tests/js/run_washer_resolution_report_tests.js` | 450 lines | `tests/test_faz_2_8_9_stage5_frontend.py` |

All five extract the *live* `<script>` block from `frontend/index.html` (never a committed copy) via brace/paren counting and execute it in Node's `vm` module against a hand-built DOM/localStorage stub — no npm dependencies, no jsdom, no browser. This is a deliberate, consistently-applied technique across every frontend phase since Faz 2.6.8.

## 8. Legacy / early-generation platform tests (root `tests/`, pre-Faz-2.4 style)

Per `docs/14_TESTING_STRATEGY.md` §2, these **must be retained and reorganized, not discarded** — they are not obsolete, they are the original platform/deployment/licensing coverage that predates the Pydantic-library architecture:

| File | Tests | Covers |
|---|---:|---|
| `tests/test_smoke.py` | 3 | Health, admin/system, basic calculation |
| `tests/test_validation.py` | 2 | Validation-summary honesty, compatibility precheck |
| `tests/test_engine_library.py` | 2 | Engine-library exposure of active data-package records |
| `tests/test_engineering.py` | 1 | Engineering-check monotonic torque |
| `tests/test_data_versions.py` | 1 | Data-package version activation |
| `tests/test_golive_wizard.py` | 1 | Go-live profile |
| `tests/test_release_package.py` | 2 | Release package readiness, traceability |
| `tests/test_mobile_pwa.py` | 2 | Manifest, service worker, mobile access info |
| `tests/test_data_upload_calibration.py` | 2 | Upload/approval policy, calibration case |
| `tests/test_cloud_deployment.py` | 2 | Health endpoints, cloud readiness |
| `tests/test_enterprise_license.py` | 3 | Organization settings, license activation |
| `tests/test_deployment_migration.py` | 3 | Deployment profile, system export/import, diagnostics |
| `tests/test_quality_gate_release.py` | 3 | Quality gate, golden case, release certificate |
| `tests/test_data_integrity.py` | 17 | Cross-cutting data-integrity checks |
| `tests/test_exception_isolation.py` | 8 | Exception isolation across the API |
| `tests/test_projects_revisions.py` | 4 | Projects/calculation revisions |
| **Subtotal** | **56** | |

## 9. Coverage-to-code map (from `pytest --cov=backend`, see Gap Report §2.1 for the gap analysis)

93% overall (6625 stmts / 444 missed). Full per-module table is in the Quality Gap Report; not duplicated here.

## 10. Duplicate / obsolete test check — result

**No duplicate or obsolete test file was identified for removal.** Every file maps to a distinct phase or module with no fully-overlapping counterpart. The only duplication found is architectural (shared boilerplate/fixture code, not shared test logic) — documented in the Quality Gap Report §2.2 and addressed in the Recommended Test Architecture.
