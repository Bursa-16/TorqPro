# TorqPro Product Vision and Scope


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Executive summary

TorqPro is a commercial **bolted-joint engineering and tightening assurance platform**. It is not merely a torque lookup table, a generic calculator, a document viewer or a React/FastAPI demonstration. Its purpose is to connect design intent, bolted-joint calculations, fastener and friction data, standards-based validation, manufacturing release, calibration, production evidence and lifecycle feedback.

The product must answer five questions defensibly:

1. What assembly preload and residual clamp force are required?
2. Which fastener, surface condition and tightening method can achieve them?
3. Is the joint safe under assembly and service loads?
4. Which standard, customer rule, assumption and source supports each result?
5. Can the decision be reproduced, approved, released and audited later?

## 2. Product vision

TorqPro shall become a trusted engineering decision-support environment for automotive, aerospace, rail, energy, defence and heavy-machinery organizations. It shall combine deterministic mechanical calculations, curated engineering libraries, explainable validation, revision control and manufacturing traceability in one product.

TorqPro competes on **engineering confidence**, not visual polish alone. The strategic differentiators are:

- deterministic and explainable calculations;
- quick OEM forecast values and detailed engineering modes in the same workflow;
- versioned FIAT/Stellantis and future OEM rule packs;
- friction, coating and lubrication evidence rather than single hard-coded coefficients;
- immutable calculation snapshots and report traceability;
- design-to-manufacturing and supplier-quality workflows;
- advisory AI grounded in approved formulas, standards metadata and historical cases.

## 3. Product principles

### 3.1 Engineering truth before automation

The system must not claim compliance or production readiness without validated formulas, approved reference data and passing golden cases. “Unknown” and “not validated” are valid product outputs.

### 3.2 Joint-centred domain model

The central object is the **Joint Revision**, not a bolt row. The joint contains the fastener system, clamped parts, interfaces, loads, tightening strategy, standards profile, calculations, validation, reports and approvals.

### 3.3 Two calculation experiences

**Quick estimation** provides rapid preliminary values such as FIAT 01391-style forecast torque where licensed and configured. It is clearly labelled as an estimate with assumptions and limitations.

**Detailed engineering** uses explicit geometry, separate thread/bearing friction, stiffness, load sharing, preload losses, service checks, uncertainty and standards rules. It cannot silently fall back to quick equations.

### 3.4 Explainability by design

Every derived result must show formula identifier, inputs, units, source, intermediate results, assumptions, engine version and warnings. The system shall never present an opaque number as an approved engineering decision.

### 3.5 Versioning and traceability

Projects, joint revisions, reference data, formula packs, rule packs, calibration records, calculations and reports are versioned. Released records are immutable. Corrections create new revisions.

### 3.6 Modular monolith first

The next product stage shall use a modular monolith, not premature microservices. Domain boundaries must nevertheless be explicit so reporting, standards, calculations and integrations can later be separated.

## 4. Target users

- Design engineer: defines joint and verifies strength, clamp and fatigue margins.
- Manufacturing/process engineer: defines tightening strategy, tools, sequence and process limits.
- Quality/SQE engineer: verifies supplier data, certificates, calibration, capability and release evidence.
- Engineering approver: reviews assumptions, rule results and revision history.
- Administrator: manages users, organization, licenses, datasets, active versions and deployment.
- Supplier engineer: provides fastener, coating, lubricant and test data.
- OEM/customer reviewer: applies customer rule packs and approves evidence packages.
- Service engineer: records field failures, loosening, maintenance and lessons learned.

## 5. Target industries and profiles

### Automotive

OEM rule packs, high-volume tightening, torque-angle strategies, tool capability, production traceability, supplier approvals, PPAP/APQP evidence and fast revision cycles.

### Aerospace and defence

Material pedigree, controlled configuration, strict review, secure/on-premise deployment, fatigue and environmental effects, export-control awareness and long retention.

### Rail

Vibration, fatigue, safety-critical classification, maintenance intervals, field inspection and long-life configuration control.

### Energy

Flanges, gaskets, pressure boundaries, temperature gradients, creep/relaxation and long-term clamp retention.

### Heavy machinery

Large fasteners, severe loads, field tightening, hydraulic tools, service re-tightening and harsh environments.

## 6. Product scope

### In scope

- Projects, assemblies, joints and revision lifecycle.
- Fastener, nut, washer, thread, material, coating, lubricant, friction and tool libraries.
- Quick forecast and detailed calculation profiles.
- Torque/preload, stiffness, load sharing, residual clamp, assembly/service stress, separation, slip, bearing pressure, thread stripping, settlement, thermal and fatigue modules as they become validated.
- Standards and customer rule packs with version/provenance.
- Reports, approvals, release packages and audit.
- Calibration and process capability records.
- Import/export, API and future PLM/ERP/MES/tool integrations.
- Advisory AI for search, explanation, recommendations and anomaly detection.

### Explicitly out of scope for the current release

- Resistance spot welding, nugget-quality or electrode physics.
- Claims of certified VDI 2230 compliance before independent validation.
- Autonomous AI calculation or approval.
- Full finite-element contact simulation in the near-term MVP.
- Storing unlicensed full standards text in the public repository.

## 7. Current product baseline

The TorqPro_24 package already provides:

- FastAPI application and SQLite persistence;
- JWT authentication, password changes and role administration;
- calculation records and CSV export;
- engineering pre-check with torque range and thread safety outputs;
- validation datasets and compatibility pre-checks;
- data-package upload, review, approval, version activation and rollback;
- reference-data traceability and impact analysis;
- calibration-case records and summary;
- golden cases, quality gate and honest release certificate;
- projects, revisions, review/approval queue and release packages;
- organization and license configuration;
- deployment profile, system export/import and diagnostics;
- PWA/mobile access, Docker, health/readiness, cloud readiness and DNS/go-live checks.

This baseline is valuable and shall be evolved rather than discarded. The next work is to modularize the code, formalize the domain model, strengthen test evidence and replace provisional equations only through approved formula packs.

## 8. Commercial editions

The long-term portfolio may include Community, Professional, OEM, Supplier, Factory, Enterprise, Cloud, Academic and Defence editions. All editions share the same verified engineering core; packaging differs by standards, collaboration, deployment, integration, governance, usage limits and support.

The first sellable target is **TorqPro Professional**: project/joint workflow, curated fastener and friction libraries, quick forecast, validated core calculation profile, explainable report and revision traceability.

## 9. Non-functional requirements

- Calculation reproducibility: identical approved snapshot and version set produces identical result.
- Unit safety: internal SI base units and explicit display conversion.
- Availability: local/offline operation for sensitive customers; health/readiness endpoints.
- Security: strong secret, password hashing, RBAC, audit and secure deployment defaults.
- Performance: quick calculations under one second; detailed Monte Carlo asynchronous when necessary.
- Accessibility: keyboard navigation, readable contrast, labelled fields and error summaries.
- Localization: Turkish and English first; architecture supports additional languages.
- Auditability: released records cannot be edited; all approvals and version changes recorded.
- Portability: Windows local launch, Docker and on-premise deployment; future private cloud.

## 10. Success metrics

Engineering: golden-case pass rate, formula coverage, reference-data provenance, uncertainty visibility and defect escape rate.

Product: time to create a joint, time to approved report, repeat usage, report acceptance, user task completion and reduction of manual spreadsheet work.

Commercial: paid pilots, conversion to Professional/Factory, supplier participation, enterprise expansion and renewal.

## 11. Long-term roadmap

1. Foundation: domain model, modularization, unit system, reference-data governance and documentation.
2. Professional engineering core: validated quick/detailed calculations, explainability and reports.
3. Standards and OEM packs: VDI/ISO/FIAT implementation packs with test evidence.
4. Manufacturing assurance: tools, calibration, capability, sequence and work instructions.
5. Enterprise: supplier/OEM workflows, SSO, PLM/ERP/MES integration and governance.
6. Intelligence: grounded AI, optimization, lifecycle learning and digital-thread analytics.
