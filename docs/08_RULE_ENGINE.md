# TorqPro Standards and Rule Engine


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Purpose

The rule engine evaluates versioned engineering, standard, OEM and internal policies without embedding rules in UI or route handlers.

## 2. Rule hierarchy

```text
Global safety invariants
-> Formula-pack constraints
-> International standard rule packs
-> OEM/customer rule packs
-> Organization policy
-> Project-specific controlled overrides
```

Conflicts are reported; overrides are never silent.

## 3. Rule model

A rule contains ID, pack/version, title, description, applicability expression, required inputs, evaluation function/formula reference, severity, message templates, source reference, implementation owner, validation status and tests.

Statuses: draft, reviewed, approved, retired. Validation: provisional, validated, certified-by-customer where applicable.

## 4. Result model

`pass`, `warn`, `fail`, `not_applicable`, `not_evaluable`. `not_evaluable` is used when evidence is missing; it cannot be automatically converted to pass.

## 5. Standard packs

Initial packs include ISO 898 material compatibility/properties, ISO 2320 prevailing-torque data requirements, ISO 16047 test-data metadata, FIAT 01391 quick forecast and FIAT 01393 validation rules where licensed. VDI 2230 packs are phased and cannot be called complete until validated.

## 6. Customer rules

Customer rule packs can define allowed fasteners, friction windows, target utilization, approval roles, report templates and manufacturing constraints. Each customer pack is isolated and versioned.

## 7. Execution

The engine receives calculation snapshot and selected packs, resolves applicability, validates required inputs, evaluates deterministically and returns rule results with values, limits, units, source and trace.

## 8. Governance

Only admin/data approver can activate rule packs. Activation records impact analysis. Existing calculations retain prior pack references. Full copyrighted standard text is not copied without permission.

## 9. Testing

Every rule has positive, boundary, negative and missing-input tests. Rule-pack release requires golden-case pass and reviewer approval.
