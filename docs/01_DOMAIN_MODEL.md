# TorqPro Canonical Domain Model


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Domain boundaries

The canonical bounded contexts are:

- Identity and Organization
- Project and Joint Lifecycle
- Engineering Libraries
- Tightening and Tooling
- Calculation and Explainability
- Standards and Validation
- Reporting and Approval
- Data Governance
- Calibration and Manufacturing Quality
- Deployment and Licensing

## 2. Aggregate hierarchy

```text
Organization
└── Project
    └── Assembly
        └── Joint
            └── JointRevision
                ├── JointComponent
                ├── ContactInterface
                ├── LoadCase
                ├── TighteningSpecification
                ├── CalculationRun
                ├── ValidationRun
                ├── Report
                └── ApprovalRecord
```

`JointRevision` is the engineering aggregate root. Draft revisions may change. Submitted, approved and released revisions are immutable.

## 3. Core entities

### Organization

Represents the customer/tenant. Attributes include name, report title, deployment policy, default unit system, industry profile and data-retention policy.

### User and Role

Roles initially include admin, engineer, reviewer and viewer. Future roles may include quality, manufacturing, supplier and OEM reviewer. Permissions are capability-based rather than inferred from UI visibility.

### Project

A commercial or engineering work container. Fields: project code, name, customer, product/program, industry profile, description, owner, status and dates.

### Assembly

A product or subassembly containing one or more joints. Supports hierarchy and CAD/PLM references.

### Joint

Stable identity of a bolted connection across revisions. Fields: joint code, name, type, criticality, quantity in product and lifecycle state.

### JointRevision

Immutable engineering configuration once released. References component assignments, interfaces, load cases, tightening specification, selected standards/rules and attachments. It stores revision number, status, author, change reason and effective dates.

### JointComponent

An occurrence in the joint, not a catalogue master. Roles include bolt, stud, nut, washer, insert, gasket and clamped part. It references a master definition plus occurrence-specific dimensions and orientation.

### ContactInterface

Represents a specific interface: thread pair, under-head/washer, nut/washer, washer/clamped part or clamped-part interface. It links surfaces, coating, lubricant and a validated friction condition.

### LoadCase

Defines axial, shear, bending, torsional, thermal and cyclic service conditions with units, direction, combination rule, source and confidence. A joint revision may contain assembly, nominal, maximum, thermal and fatigue load cases.

### TighteningSpecification

Defines method, stages, targets, limits, prevailing-torque treatment, sequence, tool capability and required calibration state.

### CalculationRun

Immutable execution record. Contains joint revision, input snapshot hash, engine version, formula-pack version, rule-pack version, unit-system version, timestamps, status and outputs.

### FormulaTrace

Directed evidence graph for each result: formula ID, classification, inputs, intermediate outputs, units, source and warnings.

### ValidationRun

Executes one or more versioned rule packs against a calculation. Produces pass/warn/fail/not-applicable results; a failed engineering check is a completed validation, not an API failure.

### Report and ReleasePackage

Reports are generated only from immutable calculations. Release packages combine approved report, calculation snapshot, validation evidence, approvals, reference-data versions and attachments.

### ApprovalRecord

Reviewer decision, role, timestamp, comment and signature metadata. Decisions: approved, rejected, needs revision.

## 4. Library entities

### FastenerDefinition

Standardized engineering definition independent of supplier and OEM. Type: bolt, screw, stud, nut, washer, insert or locking element. Links geometry, thread and property class.

### SupplierPart

Commercial part supplied by a vendor. Links supplier part number, fastener definition, coating specification, certificates, status and validity.

### OEMPartApproval

Many-to-many approval linking OEM, supplier part, OEM part number, applicable programs, approval status and validity.

### ThreadDefinition

Nominal diameter, pitch, profile, flank angle, pitch diameter references, tolerance class and standard edition.

### MaterialSpecification and PropertySet

Material identity is separated from mechanical properties. Property sets carry condition, temperature, source, validation status, yield/proof/tensile strength, modulus, Poisson ratio, CTE, hardness and optional fatigue data.

### CoatingSpecification

Coating identity, process, thickness range, corrosion information and source. It does not contain a universal friction coefficient.

### SurfaceSpecification

Roughness, hardness, finish, manufacturing process and evidence.

### LubricantSpecification

Type, application, temperature range, supplier and compatibility. It does not alone determine friction.

### FrictionCondition

Validated combination of thread pair, coating, lubricant, counter-surface, temperature, speed and reuse cycle. Stores separate thread and bearing friction distributions and source/test evidence.

### ToolDefinition, ToolAsset and CalibrationRecord

Definition describes model capability; asset is a physical serial-numbered tool; calibration is a historical event with certificate and points. CalibrationDate is never stored as a single overwriteable tool field.

## 5. Standards and rules

`Standard` identifies a family. `StandardEdition` identifies edition/date. `RulePack` is TorqPro's versioned implementation. `Rule` contains applicability, severity, formula/reference and result logic. `CustomerRuleOverride` is explicit and versioned.

No rule pack shall imply that the repository contains the full copyrighted standard. Provenance must identify licensed source, internal interpretation owner and validation evidence.

## 6. State models

Joint revision states:

```text
DRAFT -> UNDER_REVIEW -> APPROVED -> RELEASED -> SUPERSEDED
             |              |
             v              v
          REJECTED      NEEDS_REVISION
```

Data package states:

```text
DRAFT -> REVIEWED -> APPROVED -> VERSION_CREATED -> ACTIVE -> RETIRED
```

Calculation states:

```text
QUEUED -> RUNNING -> COMPLETED | FAILED | CANCELLED
```

## 7. Invariants

- Released revisions and completed calculations are immutable.
- A calculation references exactly one input snapshot and engine/formula/rule versions.
- A report references a completed calculation; it cannot accept an arbitrary mutable payload.
- A friction coefficient used in detailed mode must include provenance and validity context.
- A physical engineering failure produces result status FAIL, not necessarily a transport error.
- An AI recommendation cannot alter released engineering data or approve a revision.
