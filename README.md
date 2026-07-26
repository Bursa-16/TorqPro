<p align="center">

TorqPro

Professional Fastening Engineering Platform

Engineering software for fastening design, threaded joint analysis, torque calculation and manufacturing quality.

Automotive • Defense • Aerospace • Railway • Heavy Equipment • Industrial Manufacturing

</p>

<p align="center">













</p>

Overview

TorqPro is a professional engineering platform developed for fastening engineering.

It combines engineering calculations, engineering databases, ISO standards, manufacturing quality tools and engineering validation into a single software platform.

Instead of offering only a torque calculator, TorqPro provides an integrated engineering environment covering the complete fastening workflow—from thread geometry and bolt selection to friction management, engineering validation and production quality.

The platform is intended for engineering teams working in:

Automotive

Defense

Aerospace

Railway Systems

Heavy Equipment

Industrial Manufacturing

Why TorqPro?

Modern fastening engineering involves much more than calculating tightening torque.

Engineering teams need validated engineering data, standard compliance, traceability and manufacturing quality information throughout the complete product lifecycle.

TorqPro was developed to bring these engineering disciplines together within a single application.

The objective is to reduce engineering effort, improve data consistency and provide a reliable engineering environment for product development, industrialization and production.

Engineering Philosophy

TorqPro follows several core engineering principles.

Engineering before assumptions

Engineering data is derived from recognized standards and validated engineering references wherever possible.

Traceability

Engineering records contain source information, validation status and confidence levels, allowing engineers to understand where data originates.

Validation

Every engineering phase is accompanied by automated validation to reduce regression risk during future development.

Maintainability

New engineering modules are designed to integrate with the existing architecture instead of creating parallel implementations.

Professional Engineering Workflow

TorqPro is designed as an engineering platform—not as a collection of independent calculators.

Engineering modules share common validation logic, engineering libraries and reporting infrastructure.

Current Version

Version

TorqPro v2.8.4

Version Date

26 July 2026

Current engineering focus

Washer Library Provenance & Verification Readiness

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

Engineering Library

The Engineering Library is the core knowledge base of TorqPro.

Unlike standalone engineering calculators, TorqPro centralizes validated engineering data in reusable libraries that are shared across the entire platform.

This architecture provides consistency, traceability and maintainability throughout all engineering workflows.

Thread Geometry Library

The Thread Geometry Library contains validated ISO metric thread geometry used by fastening calculations and engineering validation modules.

Supported standards include:

ISO 68-1

ISO 724

ISO 261

ISO 262

ISO 965 (reference where applicable)

Supported thread families:

Metric Coarse

Metric Fine

Metric Extra Fine

Engineering data includes:

Nominal Diameter

Pitch

Major Diameter

Pitch Diameter

Minor Diameter

Tensile Stress Area

The library is designed for engineering calculations rather than catalog lookup.

Bolt Strength Classes

TorqPro includes an engineering library for ISO bolt strength classes.

Supported standard:

ISO 898-1

Current implementation includes:

Class 4.6

Class 4.8

Class 5.8

Class 6.8

Class 8.8

Class 9.8

Class 10.9

Class 12.9

Additional engineering classifications where implemented

Each record contains engineering properties such as:

Yield Strength

Tensile Strength

Proof Strength (where available)

Material Family

Heat Treatment Information (where available)

Source Information

Validation Status

Nut Property Classes

Nut engineering data is managed independently from bolt data.

Supported standard:

ISO 898-2

Current implementation includes:

Class 04

Class 4

Class 5

Class 6

Class 8

Class 9

Class 10

Class 12

This separation allows engineering compatibility to be evaluated independently without coupling bolt and nut data models.

Stainless Steel Fasteners

TorqPro also includes engineering data for stainless steel fastening applications.

Supported standard:

ISO 3506-1

Current implementation includes:

A2-70

A4-70

A4-80

These records are maintained separately from carbon and alloy steel fasteners because they follow different engineering standards and material classifications.

Engineering Compatibility Engine

TorqPro includes a deterministic engineering compatibility engine for bolt and nut selection.

Compatibility evaluation considers:

Strength Class

Material Family

Standard Family

Diameter Range

Possible engineering results include:

Compatible

Conditionally Compatible

Not Compatible

Unknown

Engineering decisions are deterministic and fully traceable.

Source Traceability

Engineering reliability depends on knowing where engineering data originates.

Every engineering record may include:

Source

Source Standard

Validation Status

Approval Status

Confidence Grade

This allows engineering teams to distinguish validated information from provisional or reference-only data.

Confidence Grades

Engineering data is classified according to validation confidence.

Grade

Meaning

G1

Directly derived from a primary engineering standard

G2

Validated against an authoritative engineering source

G3

Supported by independent engineering references

G4

Provisional engineering data requiring further validation

Confidence grades help engineering teams understand the maturity of each engineering record.

Engineering Validation

Engineering libraries are continuously validated to improve long-term reliability.

Validation includes:

Schema Validation

Duplicate Detection

Data Integrity Verification

Library Consistency Checks

Source Verification

Read-only Audit Tools

Engineering validation is integrated into the development workflow and verified through automated testing.

Engineering Principles

TorqPro engineering libraries follow several design principles.

Reusability

Engineering data is defined once and reused across multiple engineering modules.

Traceability

Engineering records preserve source information and validation metadata.

Deterministic Behaviour

Engineering calculations produce repeatable results for identical inputs.

Maintainability

New engineering modules extend the existing architecture instead of introducing parallel implementations.

Standard Compliance

Engineering libraries are organized around internationally recognized standards whenever applicable.

Technology Stack

TorqPro is built using modern, lightweight technologies with a focus on engineering performance, maintainability and long-term extensibility.

Backend

Technology

Purpose

Python

Core application logic

FastAPI

REST API and backend services

SQLite

Engineering data storage

Pydantic

Data validation and domain models

Uvicorn

ASGI application server

Frontend

Technology

Purpose

HTML5

User interface

CSS3

Responsive layout and styling

JavaScript (ES6)

Client-side engineering workflows

Development

Technology

Purpose

Git

Version control

GitHub

Source code hosting

GitHub Actions

Continuous Integration

GitHub Pages

Project documentation and demo pages

System Architecture

TorqPro follows a modular engineering architecture.

                    ┌────────────────────┐
                    │     Frontend       │
                    │ HTML • CSS • JS    │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │      FastAPI       │
                    │ REST API Layer     │
                    └─────────┬──────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
 Engineering Library   Calculation Engine   Report Engine
          │                   │                   │
          └──────────────┬────────────────────────┘
                         ▼
                    SQLite Database

The architecture separates presentation, business logic and engineering data while allowing engineering modules to share common libraries and validation infrastructure.

Project Structure

TorqPro/

├── backend/
│   ├── calculation_engine/
│   ├── library/
│   ├── reports/
│   └── app.py
│
├── frontend/
│
├── tests/
│   ├── js/
│   └── ...
│
├── tools/
│
├── docs/
│
├── requirements.txt
│
└── README.md

The repository is organized to keep engineering libraries, calculation logic, frontend components and validation tooling clearly separated.

Installation

Clone the Repository

git clone https://github.com/Bursa-16/TorqPro.git

cd TorqPro

Create a Virtual Environment

python -m venv .venv

Activate the Environment

Windows

.venv\Scripts\activate

Linux / macOS

source .venv/bin/activate

Install Dependencies

pip install -r requirements.txt

Run the Application

Option 1 (Recommended)

Start the application using the supplied launcher:

TorqPro_24_Baslat.bat

Option 2

Run manually:

python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000

Open the Application

http://127.0.0.1:8000

Development Workflow

The recommended workflow is based on feature branches and Pull Requests.

main
 │
 ├── feature/...
 │
 ├── hotfix/...
 │
 └── release

Every engineering phase is developed in an isolated feature branch, validated through automated tests and merged into the main branch after successful review.

Quality Assurance

Engineering quality is supported through automated validation.

Current validation includes:

Unit Tests

Integration Tests

Engineering Library Validation

API Validation

Frontend Validation

Report Validation

Continuous Integration (GitHub Actions)

All changes are verified before integration into the main branch.

Documentation

Project documentation includes:

Engineering Libraries

Development Roadmap

Engineering Validation Reports

Version Notes

Version Tags

Additional documentation will be expanded as new engineering modules are completed.

Version Information

Current Version

Item

Value

Product

TorqPro

Current Version

v2.8.4

Version Date

26 July 2026

Status

Current Development Baseline

What's New in v2.8.4

Washer Library Provenance & Verification Readiness

Phase 2.8.4 introduces a deterministic provenance and verification-readiness framework for the washer engineering library.

The purpose of this phase is to make the evidence status of the existing washer dataset traceable, reviewable and testable. It does not claim that all washer dimensions have been verified against licensed ISO/DIN standards.

Scope

Reviewed all 223 washer library records.

Added a provenance evidence manifest covering every washer record exactly once.

Added deterministic Markdown and JSON provenance reports.

Added explicit evidence categories and review reason codes.

Added 29 automated regression tests.

Preserved all existing engineering geometry and calculation behaviour.

Evidence Classification

Category

Records

standard_verified

0

secondary_source_only

8

generated_from_unverified_source

0

no_external_evidence

139

action_needed

76

Total

223

action_needed does not mean that a washer record is definitively incorrect. It identifies an evidence gap, a secondary-source divergence, an unresolved standard identity or a metadata inconsistency that requires engineering review.

Added Files

backend/library/data/washer_provenance_evidence.json

tools/generate_faz_2_8_4_washer_provenance_manifest.py

tools/washer_provenance_report_faz_2_8_4.py

tests/test_faz_2_8_4_washer_provenance.py

docs/phase_2_8/phase_2_8_4_washer_provenance_report.md

docs/phase_2_8/phase_2_8_4_washer_provenance_report.json

Validation Results

Phase 2.8.4 tests: 29 / 29 passed

Full project test suite: 1014 / 1014 passed

Population integrity checks: 0 findings

Deterministic report generation: byte-identical Markdown and JSON outputs

Backward Compatibility

Phase 2.8.4 does not modify:

washer_library.json

Washer dimensions or technical values

Confidence or validation-status fields

Domain models or schemas

Calculation algorithms, coefficients or thresholds

VDI 2230-related calculation behaviour

REST API behaviour

Frontend behaviour

Future Verification

The provenance framework prepares the library for future comparison against licensed or otherwise authoritative ISO/DIN dimensional sources. The proposed future comparison layer is documented, but no unused verification adapter or automatic geometry-correction mechanism was added in this phase.

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

1014 / 1014 Tests Passing

Test Group

Result

Phase 2.8.4 Washer Provenance

✅ 29 Passed

Phase 2.8.3 Strength Classes

✅ 100 Passed

Phase 2.8.2 Thread Geometry Verification

✅ 29 Passed

Overall Project

✅ 1014 Passed

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

⭐ Current Version

Phase 2.8.5

Next Engineering Module

Planned

Version History

Version

Highlights

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

v2.8.4

Current engineering focus:

Washer-library provenance

Evidence classification

Deterministic verification-readiness reporting

Source traceability

Engineering review prioritization

Next Phase

Phase 2.8.5

Planned engineering work will be defined after review of the Phase 2.8.4 provenance findings. Potential scope includes:

Authoritative ISO/DIN source integration

Washer dimensional and tolerance verification

Controlled correction workflow for confirmed data issues

Extended library validation coverage

Future Roadmap

The following items are under long-term evaluation:

Digital Twin integration

Advanced engineering simulation

AI-assisted engineering workflows

Extended reporting capabilities

Additional international engineering standards

These items represent future planning only and are not part of the current release.

Project Quality

TorqPro follows a controlled engineering development process.

Every engineering phase includes:

Architecture review

Engineering implementation

Automated validation

Code review

Continuous Integration

Release verification

Documentation updates

This process helps maintain engineering consistency and long-term maintainability across the platform.

Version Tags and Documentation

Version milestones may be identified with Git tags. A separate GitHub Release page is optional and is created only when a packaged public release is required.

Version documentation may include:

Engineering summary

Implemented capabilities

Validation results

Known limitations

Provenance and verification reports

This approach preserves traceability between source-code milestones and engineering documentation without requiring a GitHub Release for every development phase.

License

Copyright © 2026 TorqPro Project.

All rights reserved.

Unless otherwise stated, the source code, engineering libraries, documentation and related project assets are protected by applicable copyright laws.

This repository is provided for evaluation, demonstration and engineering collaboration purposes.

Commercial use, redistribution or incorporation into proprietary products requires prior written permission from the project owner.

Contributing

At this stage, TorqPro is developed under a controlled engineering workflow.

Engineering changes are introduced through dedicated feature branches and validated before integration into the main branch.

The development process includes:

Architecture Review

Engineering Implementation

Automated Testing

Code Review

Continuous Integration

Documentation Update

Release Verification

This workflow helps maintain engineering quality and long-term maintainability.

Documentation

Project documentation includes:

Engineering Libraries

Version Notes

Validation Reports

Development Roadmap

Technical Documentation

Version Tags

Additional documentation will be published as new engineering modules become available.

Support

For questions regarding the project, engineering concepts or reported issues, please use GitHub Issues.

Engineering feedback and suggestions are welcome.

Repository

GitHub Repository

https://github.com/Bursa-16/TorqPro

Acknowledgements

TorqPro has been developed by combining engineering experience from automotive and defense industries with modern software development practices.

The project emphasizes:

Engineering accuracy

Traceability

Validation

Maintainability

Professional software engineering

Vision

TorqPro aims to become a comprehensive engineering platform for fastening applications.

The long-term vision is to provide a unified environment where engineering calculations, validated reference data, manufacturing quality tools and engineering documentation are managed within a single ecosystem.

The platform is being developed incrementally, with each release expanding engineering capability while preserving reliability and traceability.

Disclaimer

Engineering calculations and reference data should always be reviewed by qualified engineers before being used in production environments.

Although TorqPro is continuously validated through automated testing and engineering review, the user remains responsible for verifying suitability for a specific application.

Contact

For project updates and future releases, please follow the GitHub repository.

Repository:

https://github.com/Bursa-16/TorqPro

<p align="center">

TorqPro

Professional Fastening Engineering Platform

Automotive • Defense • Aerospace • Railway • Heavy Equipment • Industrial Manufacturing

Current Version

v2.8.4

Designed and developed for professional engineering applications.

© 2026 TorqPro Project

</p>
