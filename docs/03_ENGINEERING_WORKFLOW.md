# TorqPro Engineering Workflow


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. End-to-end lifecycle

```text
Home
-> Project
-> Assembly
-> Joint Wizard
-> Fastener System
-> Materials
-> Interfaces, Coating and Lubrication
-> Load Cases
-> Tightening Strategy
-> Calculation Setup
-> Results and Explainability
-> Engineering Validation
-> Standards Compliance
-> Engineering Review
-> Report
-> Approval
-> Release
-> Manufacturing Instructions
-> Tool and Calibration
-> Production Traceability
-> Service Feedback
-> Archive/Supersede
```

## 2. Home

Shows recent projects, new/open actions, pending approvals, data-version warnings, calibration alerts, release status, license and system health. Home does not perform engineering calculations.

## 3. Project and assembly

The user defines project code, customer, product/program, industry, owner, dates and reference documents. An assembly groups joints. Templates may preselect industry profile, standards and report package.

## 4. Joint Wizard

The wizard defines joint type, criticality, number/layout of fasteners, clamped-part stack, holes, grip, interfaces and design intent. It performs completeness checks but does not invent missing engineering data.

## 5. Fastener system

The user selects bolt/screw/stud, nut, washers, locking elements and supplier/OEM part mappings. Compatibility checks cover thread, property class, geometry and approved source status.

## 6. Materials and interfaces

Materials are assigned with temperature/condition-specific property sets. Interfaces define coating, surface, lubricant and friction condition separately for thread, bearing and clamped interfaces.

## 7. Load cases

Assembly and service load cases are defined with axial, shear, bending, torsion, thermal and cyclic data. Source, unit, confidence and combination rules are mandatory for critical joints.

## 8. Tightening strategy

Methods include torque control, torque-angle, turn-of-nut, yield control, tension control and multi-stage. Tool, accuracy, calibration, prevailing torque treatment, sequence and acceptance window are specified.

## 9. Calculation setup

The user selects quick or detailed profile, formula pack, rule packs, load cases, uncertainty method and output scope. The setup screen lists missing data and indicates which modules are validated, provisional or unavailable.

## 10. Results

Results separate assembly preload, service bolt load and residual clamp force. Views include summary, formula trace, load cases, safety checks, torque distribution, uncertainty and warnings. Results never hide whether a value is estimated, detailed, empirical or test-derived.

## 11. Validation and review

Engineering validation checks mechanical limits. Standards compliance applies versioned rule packs. Process validation checks tool/calibration/capability. A reviewer inspects assumptions and evidence before report generation.

## 12. Report, approval and release

Reports are generated from immutable calculations. Approval requires authorized roles and captures comments. Release produces a package with revision, calculation snapshot, formula/rule versions, validation, approvals, data provenance and manufacturing instructions.

## 13. Manufacturing and lifecycle

Manufacturing receives target, tolerance, stages, sequence, tool requirements and reaction notes. Calibration/process qualification evidence is linked. Production results and field/service feedback close the loop without changing the original released calculation.

## 14. Gates

- Calculation gate: required inputs and unit checks pass.
- Validation gate: calculation completed and rule packs executed.
- Report gate: engineering review completed or explicit controlled override.
- Approval gate: required roles and no unresolved critical failures.
- Release gate: approved revision, valid report, approved reference-data versions and required calibration evidence.

## 15. Draft and revision behavior

Users may save and continue later. Changing released configuration creates a new joint revision. Recalculation creates a new calculation run; previous results remain available.
