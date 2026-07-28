# Current Version

| Item | Value |
|------|------|
| Product | TorqPro |
| **Current Version** | **v2.8.7** |
| **Version Date** | **28 July 2026** |
| **Current Engineering Focus** | **Joint Analysis & Torque Optimization** |

---

# What's New in v2.8.7

## Joint Analysis & Torque Optimization

Phase **2.8.7** introduces a comprehensive engineering workflow for bolted joint assessment by integrating the existing engineering libraries with the VDI 2230 calculation foundation.

The purpose of this phase is to provide a deterministic, traceable and bilingual engineering workflow for analysing complete bolted joints while preserving the additive architecture of TorqPro.

---

## Scope

- Added Joint Analysis engineering engine.
- Added Joint Analysis REST API endpoint.
- Added complete TR / EN Joint Analysis interface.
- Added preload calculation workflow.
- Added bolt stiffness calculation.
- Added joint stiffness calculation.
- Added load factor (Phi) calculation.
- Added residual clamp load estimation.
- Added torque window calculation.
- Added preload estimation from tightening torque.
- Added safety factor evaluation.
- Added engineering warnings and readiness evaluation.
- Added bilingual frontend integration.
- Added regression and frontend test suites.
- Preserved existing engineering libraries and APIs.

---

# Changed Files

```
backend/app.py

backend/calculation_engine/joint_analysis.py

frontend/index.html

tests/js/run_joint_analysis_tests.js

tests/test_faz_2_8_7_frontend.py

tests/test_faz_2_8_7_joint_analysis.py
```

---

# Validation Results

| Item | Result |
|------|--------|
| GitHub Pull Request | **PR #20 merged into main** |
| GitHub Checks | ✅ Passed |
| Feature Commit | **fcd8e3d** |
| Merge Commit | **6180496** |
| Tag | **v2.8.7** |
| Local main | Synchronized |
| Working Tree | Clean |

---

# Backward Compatibility

Phase 2.8.7 does **not** modify:

- Existing engineering libraries
- Existing REST API behaviour
- Existing engineering database
- Existing frontend modules
- Existing report engine architecture
- Existing engineering validation framework

The implementation is fully additive.

---

# Engineering Notes

The following calculations are currently provided as **PROVISIONAL** and are clearly identified within the application until independent engineering validation is completed.

- Residual Clamp Load
- Preload derived from Torque
- Safety Factor derivation

The following engineering effects are intentionally outside the current scope.

- Settlement
- Embedment
- Thermal effects
- Relaxation
- Torque-angle tightening
- Multi-stage tightening
- Tightening sequence optimisation
- Full VDI 2230 compliance
- Finite Element Analysis (FEA)
- AI / Machine Learning prediction

---

# Engineering Validation

Engineering quality is continuously verified using automated validation.

## Current Validation Summary

| Validation Area | Result |
|-----------------|--------|
| Unit Tests | ✅ Passed |
| Integration Tests | ✅ Passed |
| Engineering Libraries | ✅ Passed |
| REST API | ✅ Passed |
| Frontend | ✅ Passed |
| Report Engine | ✅ Passed |
| GitHub Actions | ✅ Passed |

---

# Test Results

| Test Group | Result |
|------------|--------|
| Full pytest Suite | **1256 / 1256 Passed** |
| Phase 2.8.7 Backend + Frontend | **55 / 55 Passed** |
| TR / EN Localization Tests | **1097 / 1097 Passed** |
| Joint Analysis JS Tests | **45 / 45 Passed** |

Continuous Integration verifies every change before integration into the main branch.

---

# Development Status

| Phase | Description | Status |
|------|-------------|--------|
| Phase 2.4 | Engineering Database | ✅ Completed |
| Phase 2.5 | Production Validation Foundation | ✅ Completed |
| Phase 2.6 | Friction Condition Workspace | ✅ Completed |
| Phase 2.6.9 | Global Localization (TR / EN) | ✅ Completed |
| Phase 2.7 | Report Engine | ✅ Completed |
| Phase 2.8.1 | Engineering Library Audit | ✅ Completed |
| Phase 2.8.2 | Thread Geometry Verification | ✅ Completed |
| Phase 2.8.3 | Bolt / Nut Strength Classes | ✅ Completed |
| Phase 2.8.4 | Washer Library Provenance | ✅ Completed |
| Phase 2.8.5 | Washer Correction Workflow | ✅ Completed |
| Phase 2.8.6 | Fastener Assembly Intelligence | ✅ Completed |
| **Phase 2.8.7** | **Joint Analysis & Torque Optimization** | ⭐ **Current Version** |
| Phase 2.8.8 | Material Intelligence & Engineering Formula Validation | Planned |

---

# Version History

| Version | Highlights |
|---------|------------|
| **v2.8.7** | Joint Analysis & Torque Optimization |
| v2.8.6 | Fastener Assembly Intelligence |
| v2.8.5 | Washer Correction Workflow |
| v2.8.4 | Washer Library Provenance & Verification Readiness |
| v2.8.3 | Bolt / Nut Strength Classes |
| v2.8.2 | Thread Geometry Verification & Confidence Upgrade |
| v2.8.1 | Engineering Library Inventory & Gap Analysis |
| v2.7 | Report Engine |
| v2.6.9 | Global TR / EN Localization |
| v2.6 | Friction Condition Workspace |
| v2.5 | Production Validation Foundation |
| v2.4 | Engineering Database |

---

# Roadmap

## Current Version

**v2.8.7**

Current engineering focus:

- Joint Analysis
- Torque Optimization
- Engineering preload workflow
- Joint stiffness evaluation
- Load factor calculation
- Torque window estimation
- Engineering warnings
- TR / EN engineering interface
- Engineering validation

---

## Next Phase

### Phase 2.8.8

**Material Intelligence & Engineering Formula Validation**

Planned engineering work:

- Validation of provisional engineering formulas
- Material compatibility intelligence
- OEM material compatibility rules
- Defence material recommendations
- Engineering recommendation improvements
- Extended validation datasets
- Documentation synchronisation
