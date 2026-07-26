Current Version

Version

TorqPro v2.8.5

Version Date

26 July 2026

Current engineering focus

Washer Correction Workflow

Product Showcase

TorqPro provides an integrated engineering environment covering fastening design, engineering databases, manufacturing quality and validation workflows.

Dashboard

The central dashboard provides quick access to all engineering modules through a unified interface.

<p align="center">
<img src="docs/images/dashboard.png" width="1000">
</p>

The dashboard allows engineers to:

Navigate between engineering modules

Monitor project status

Access engineering libraries

Launch manufacturing quality tools

Open engineering reports

Torque Calculator

Professional tightening torque calculation for engineering applications.

<p align="center">
<img src="docs/images/torque_calculator.png" width="1000">
</p>

Main capabilities:

Engineering torque calculation

OEM torque estimation

Multiple tightening conditions

Engineering recommendations

Repeatable calculation workflow

Bolt / Nut Strength Classes

Engineering database for mechanical property selection and compatibility verification.

<p align="center">
<img src="docs/images/strength_classes.png" width="1000">
</p>

Included functionality:

ISO 898-1 Bolt Strength Classes

ISO 898-2 Nut Property Classes

ISO 3506 Stainless Steel Classes

Automatic compatibility verification

Diameter-range validation

Material-family validation

Standard-family validation

Friction Condition Workspace

Engineering workspace for friction management and fastening recommendations.

<p align="center">
<img src="docs/images/friction_workspace.png" width="1000">
</p>

Capabilities include:

Friction condition database

Intended-use classification

Recommendation engine

Validation warnings

Engineering notes

Source traceability

Engineering Library

Central engineering knowledge base shared across all TorqPro modules.

<p align="center">
<img src="docs/images/engineering_library.png" width="1000">
</p>

Engineering Library includes:

Thread Geometry

Bolt Strength Classes

Nut Property Classes

Washer & Joint Hardware

Friction Conditions

OEM References

Engineering Standards

Every engineering record contains validation and traceability information.

Report Engine

Engineering reports generated from validated project data.

<p align="center">
<img src="docs/images/report_engine.png" width="1000">
</p>

Report features:

Engineering summaries

Traceability information

Validation results

Compatibility analysis

Professional report layout

Designed for Professional Engineering

TorqPro has been developed as a single engineering platform rather than a collection of independent tools.

All engineering modules share:

Common engineering libraries

Unified validation framework

Shared engineering database

Consistent user interface

Centralized report infrastructure

Source traceability

Engineering confidence levels

This architecture helps engineering teams maintain consistency throughout the complete fastening engineering process.

Version Information

Current Version

Item

Value

Product

TorqPro

Current Version

v2.8.5

Version Date

26 July 2026

Status

Current Development Baseline

What's New in v2.8.5

Washer Correction Workflow

Phase 2.8.5 introduces a controlled washer correction workflow based on the Phase 2.8.4 washer provenance and verification-readiness foundation.

The purpose of this phase is to convert washer provenance findings into a deterministic, reviewable and testable correction workflow without directly replacing the washer library dataset outside the intended engineering process.

Scope

Added washer resolution ledger.

Added washer correction workflow logic.

Added washer resolution validation.

Added washer resolution report generation.

Added deterministic Phase 2.8.5 Markdown and JSON report outputs.

Added automated regression tests for the washer correction workflow.

Integrated washer correction readiness into the engineering library workflow.

Preserved API and frontend behaviour.

Preserved existing washer library geometry outside the intended correction workflow.

Changed Files

backend/library/data/washer_resolution_ledger.json

backend/library/washer_library.py

backend/library/washer_report.py

backend/library/washer_resolution.py

backend/library/washer_resolution_validator.py

docs/phase_2_8/phase_2_8_5_washer_resolution_report.json

docs/phase_2_8/phase_2_8_5_washer_resolution_report.md

tests/test_faz_2_8_5_washer_correction_workflow.py

tools/generate_faz_2_8_5_washer_resolution_ledger.py

Validation Results

GitHub Pull Request: PR #18 merged into main

GitHub check: Passed

Feature commit: c7befa8

Merge commit: dda02f1

Tag: v2.8.5

Local main synchronized with origin/main

Working tree clean after merge

Backward Compatibility

Phase 2.8.5 does not modify:

Frontend files

REST API files

Calculation algorithms

Torque coefficients

Engineering thresholds

VDI 2230-related calculation behaviour

Existing application routes

Existing user interface behaviour

washer_library.json outside the intended correction workflow

Engineering Notes

Phase 2.8.5 does not claim that every washer record has been fully verified against licensed ISO/DIN standards.

The workflow provides a controlled engineering mechanism for tracking, validating and reporting washer correction actions derived from the Phase 2.8.4 provenance findings.

Engineering Validation

Engineering quality is continuously verified using automated validation.

Current Validation Summary

Validation Area

Result

Unit Tests

✅ Passed

Integration Tests

✅ Passed

Engineering Libraries

✅ Passed

REST API

✅ Passed

Frontend

✅ Passed

Report Engine

✅ Passed

GitHub Actions

✅ Passed

Test Results

Current project validation passed through GitHub Actions after PR #18 merge.

Test Group

Result

Phase 2.8.5 Washer Correction Workflow

✅ Passed

Phase 2.8.4 Washer Provenance

✅ Passed

Phase 2.8.3 Strength Classes

✅ Passed

Phase 2.8.2 Thread Geometry Verification

✅ Passed

Overall Project

✅ Passed

Continuous Integration verifies every change before integration into the main branch.

Development Status

Phase

Description

Status

Phase 2.4

Engineering Database

✅ Completed

Phase 2.5

Production Validation Foundation

✅ Completed

Phase 2.6

Friction Condition Workspace

✅ Completed

Phase 2.6.9

Global Localization (TR / EN)

✅ Completed

Phase 2.7

Report Engine

✅ Completed

Phase 2.8.1

Engineering Library Audit

✅ Completed

Phase 2.8.2

Thread Geometry Verification

✅ Completed

Phase 2.8.3

Bolt / Nut Strength Classes

✅ Completed

Phase 2.8.4

Washer Library Provenance & Verification Readiness

✅ Completed

Phase 2.8.5

Washer Correction Workflow

⭐ Current Version

Phase 2.8.6

Next Engineering Module

Planned

Version History

Version

Highlights

v2.8.5

Washer Correction Workflow

v2.8.4

Washer Library Provenance & Verification Readiness

v2.8.3

Bolt / Nut Strength Classes

v2.8.2

Thread Geometry Verification & Confidence Upgrade

v2.8.1

Engineering Library Inventory & Gap Analysis

v2.7

Report Engine

v2.6.9

Global TR / EN Localization

v2.6

Friction Condition Workspace

v2.5

Production Validation Foundation

v2.4

Engineering Database

Roadmap

Current Version

v2.8.5

Current engineering focus:

Washer correction workflow

Washer resolution ledger

Controlled engineering correction process

Deterministic washer resolution reporting

Washer validation and regression testing

Engineering review traceability

Next Phase

Phase 2.8.6

Planned engineering work will be defined after review of the Phase 2.8.5 washer correction workflow results.

Potential scope includes:

Extended washer validation coverage

Controlled dimensional verification against authoritative sources

Additional washer/joint hardware engineering checks

Expanded traceability for engineering library updates

Broader integration with downstream calculation and reporting workflows
