# TorqPro UI Screen Tree and Interaction Specification


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Application shell

- Top bar: product, project/joint breadcrumb, global search, notifications, language, user.
- Left navigation: Home, Projects, Libraries, Calculations, Approvals, Quality, Administration.
- Main workspace: wizard/cockpit.
- Right properties panel: context-dependent values, source and validation state.
- Bottom status: engine/formula/rule/data versions, units, save state and system status.

## 2. Screen tree

```text
Login
Home
Projects
  Project List
  Project Workspace
    Overview
    Assemblies
    Documents
    Revisions
    Release Packages
  Assembly Workspace
  Joint Wizard
    Joint Definition
    Component Stack
    Fastener Selection
    Material Assignment
    Interfaces/Friction
    Load Cases
    Tightening Strategy
    Calculation Setup
  Results Cockpit
    Summary
    Preload and Clamp
    Stress and Strength
    Separation and Slip
    Settlement/Thermal/Fatigue
    Uncertainty
    Formula Trace
    Validation
  Reports
  Approval
Libraries
  Fasteners
  Threads
  Materials
  Coatings
  Lubricants
  Friction Conditions
  Tools and Calibration
  Standards and Rule Packs
Quality
  Data Packages
  Versions and Rollback
  Golden Cases
  Quality Gate
  Calibration Cases
  Release Certificate
Administration
  Users and Roles
  Organization
  License and Usage
  Deployment Profile
  Import/Export
  Diagnostics
  Mobile/PWA
  Cloud Readiness
  Go-Live and DNS
```

## 3. Interaction rules

- Required fields show reason and downstream dependency.
- Every coefficient displays source, validity and status.
- Units are visible in field labels; conversions never alter stored base value.
- Warnings distinguish missing evidence, assumption, provisional formula and failed check.
- “Calculate” is disabled only for structural invalidity; engineering fail results are calculated and shown.
- Back navigation preserves draft values.
- Released revisions are read-only with “Create new revision.”

## 4. Joint Wizard details

Step 1 identifies joint and criticality. Step 2 builds stack with reorderable parts. Step 3 selects fastener system. Step 4 maps material property sets. Step 5 creates contact interfaces and friction conditions. Step 6 defines loads. Step 7 defines method/tool/sequence. Step 8 reviews completeness and runs calculation.

Each step provides compact 2D schematic and an assumptions panel. 3D is optional and never blocks core engineering workflow.

## 5. Results cockpit

Top cards: target/achieved preload range, residual clamp, maximum bolt load, yield utilization, separation/slip status and confidence.

Graphs: torque contribution, preload distribution, load-line diagram, torque-angle when applicable, sensitivity tornado and Monte Carlo histogram.

Formula trace uses expandable nodes with equation ID, symbols, units, source and intermediate values.

## 6. Accessibility and localization

Keyboard navigation, focus states, labelled controls, non-colour status indicators, Turkish/English terminology glossary, decimal separator handling and screen-reader-compatible error summary are mandatory.

## 7. Existing frontend migration

The current single-page UI shall remain operational while screens are progressively mapped to modules. Visual redesign must not precede domain/API stabilization. Existing administration, data versioning, quality gate, licensing, deployment and PWA functions are retained.
