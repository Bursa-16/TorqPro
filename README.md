# TorqPro v2.8.2

Professional Fastening Engineering Platform for Automotive, Defense and Industrial Manufacturing

TorqPro is an engineering platform developed for bolt, nut and threaded joint analysis. It combines engineering calculations, OEM standards, friction condition management, capability analysis and manufacturing quality tools in a single application.

**Current Stable Release:** v2.8.2

---

# Features

## Fastening Engineering

- OEM Torque Estimation
- Torque Calculator
- Advanced Joint Analysis
- Fastener Engineering Database
- Bolt & Nut Library
- Washer & Joint Hardware Library

## Manufacturing Quality

- Cp / Cpk Capability Analysis
- Tool Tracking
- Problem Management
- FMEA Failure Catalog
- System Health Dashboard

## Engineering Reference

- OEM Norm Query
- Friction Condition Workspace
- Norm Guide
- Engineering Recommendations

## Localization

- Turkish / English Interface
- Runtime Language Switching
- Centralized Version Management

---

# Engineering Library

## Thread Geometry Library

- ISO Metric Coarse / Fine / Extra Fine thread geometry (M1-M100)
- Major / pitch / minor diameter per ISO 724 / ISO 68-1 basic-profile formulas
- Tensile stress area per ISO 898-1 formula
- Independently re-verified for the Fine (M3-M100), Extra Fine (M8-M100) and
  Coarse M68-M100 record set in Phase 2.8.2

## Confidence Grades (G1-G4)

- **G1** - highest confidence, directly sourced from a primary standard
- **G2** - validated against a primary standard table
- **G3** - reference_only, corroborated by independent secondary
  engineering references (not a primary-standard lookup)
- **G4** - provisional / unverified

## Source Traceability

- Every library record carries `source` / `source_standard` provenance
  fields plus a `validation_status` / `approval_status` pair
- Confidence upgrades require independently verifiable source evidence;
  no value or confidence grade is assigned by assumption or interpolation

## Library Integrity Validation

- Schema validation, duplicate-id detection and checksum verification
  across all registered library records
- Read-only audit tooling (`tools/audit_engineering_library.py`,
  `tools/verify_thread_geometry_faz_2_8_2.py`) reused across phases
  instead of parallel validation logic

---

# Thread Geometry Verification (Phase 2.8.2)

- 72 Thread Geometry records reviewed (Fine 35, Extra Fine 29, Coarse M68-M100 8)
- 5 records upgraded from G4 to G3 ("reference_only"), corroborated by
  independent secondary engineering references
- No geometric value changed (nominal diameter, pitch, major/pitch/minor
  diameter, stress area all unchanged)
- 0 regressions -- full test suite green after the phase

---

# Current Development Status

| Phase | Status |
|-------|--------|
| Phase 2.4 Engineering Database | ✅ Completed |
| Phase 2.5 Production Validation Foundation | ✅ Completed |
| Phase 2.6 Friction Condition Workspace | ✅ Completed |
| Phase 2.6.9 Global TR/EN Localization | ✅ Current Stable Release |
| Phase 2.7 Report Engine | 🚧 In Progress |
| Phase 2.8.1 Engineering Library Inventory & Gap Analysis | ✅ Completed |
| Phase 2.8.2 Thread Geometry Verification & Confidence Upgrade | ✅ Completed |
| Phase 2.8 Demo Mode | Planned |

---

# Test Status

**900 / 900 tests passing**

---

# Installation

Clone the repository

```bash
git clone https://github.com/Bursa-16/TorqPro.git
cd TorqPro
```

Create virtual environment

```bash
python -m venv .venv
```

Activate

Windows

```bash
.venv\Scripts\activate
```

Install requirements

```bash
pip install -r requirements.txt
```

---

# Run

Windows

Double-click

```
TorqPro_24_Baslat.bat
```

or run manually

```bash
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Application URL

```
http://127.0.0.1:8000
```

---

# Technologies

- Python
- FastAPI
- SQLite
- HTML5
- CSS3
- JavaScript
- GitHub Actions
- GitHub Pages

---

# Main Modules

- Dashboard
- OEM Torque Estimate
- Torque Calculator
- Check List
- Capability Analysis
- Problem Management
- OEM Norm Query
- Friction Condition
- Norm Guide
- FMEA Catalog

---

# Version

Current Release

**v2.8.2**

Release Date

**25 July 2026**

---

# Roadmap

Completed

- ✅ Phase 2.4 Engineering Database
- ✅ Phase 2.5 Production Validation Foundation
- ✅ Phase 2.6 Friction Condition Workspace
- ✅ Phase 2.6.9 Global TR/EN Localization
- ✅ Phase 2.8.1 Engineering Library Inventory & Gap Analysis
- ✅ Phase 2.8.2 Thread Geometry Verification & Confidence Upgrade

Next

- → Phase 2.8.3 Bolt / Nut Strength Classes
- Phase 2.7 Report Engine
- Phase 2.8 Demo Mode
- PDF Report Generator
- Digital Twin Support
- Advanced Engineering Simulation

---

# Project

TorqPro is developed as an engineering platform for professional fastening analysis and manufacturing quality applications.

Target industries include:

- Automotive
- Defense
- Heavy Equipment
- Aerospace
- Industrial Manufacturing

---

# Repository

https://github.com/Bursa-16/TorqPro

---

© 2026 TorqPro Project
