# TorqPro Engineering Library Specification


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Library principles

Libraries accelerate work but never hide provenance. Master definitions, supplier parts, OEM approvals and joint occurrences are separate.

## 2. Fastener library

Supports bolts, screws, studs, nuts, washers, inserts and locking elements. Required fields depend on type. Common data: designation, standards edition, thread, geometry, property class, material specification and validation status.

Bolt geometry includes nominal diameter, pitch, length, shank/thread lengths, head/bearing geometry and stress-area source. Nut geometry includes style, height, thread, bearing geometry and proof class. Washer includes inner/outer diameter, thickness, hardness and type.

## 3. Material library

Properties are temperature/condition specific. Each property set includes proof/yield/tensile strength, modulus, Poisson ratio, CTE, hardness and source. Property class is not confused with raw material identity.

## 4. Surface/coating/lubricant library

Coating and lubricant records are descriptive specifications. Friction values live in validated friction conditions with separate thread and bearing distributions, counter-surface, speed, temperature and reuse context.

## 5. Tool library

Tool definition: manufacturer/model/type/range/accuracy/angle capability/control strategy. Tool asset: serial/site/status. Calibration: date, due date, procedure, certificate, points, uncertainty and pass/fail.

## 6. OEM and supplier data

Supplier parts link catalogue definition, supplier part number, batch/certificates, coating and validity. OEM approvals map many suppliers/parts to OEM part numbers/programs and approval status.

## 7. Data quality

Every record has source type, reference, confidence, validation status, owner, created/updated timestamps and version. Approved records cannot be overwritten; superseding creates a new version.

## 8. Import

JSON/CSV/XLSX imports are staged as data packages. Parsing does not activate data. Quality gate checks required fields, ranges, duplicates, units and references. Review, approval and activation are separate.

## 9. Current assets

The package contains `torqpro_library_v3_1.json`, `Baglanti_Elemanlari_Kutuphanesi_v3_1.xlsx` and active JSON datasets for nut proof loads, bolt-nut compatibility, washer pressure, friction and technical sources. These are migration sources, not automatically production-approved truth.

## 10. Friction Condition module (Faz 2.6)

**Naming (Faz 2.6 rename, 2026-07-23):** the module is named **Friction Condition**, not "Lubrication Module" / "Lubrication Engineering Module". "Lubrication" is a subsection of Friction Condition, not the module itself. "Lubrication Module"/"Lubrication Engineering Module" may still be used only when referring specifically to lubricant data (e.g. the existing `LUBRICATION_LIBRARY` / `lubrication_library.json` dataset).

### 10.1 Rationale

The module governs the complete friction condition of a bolted joint -- lubrication, coatings, surface condition/finish and friction behaviour affecting preload and tightening torque -- not lubricant selection alone. Framing it as "Friction Condition" from Faz 2.6.0 onward lets Geomet, Dacromet, PTFE coating, surface roughness, mu_thread, mu_bearing, K-factor and scatter join the same module later without a rename.

### 10.2 Module responsibilities

- Lubrication
- Surface Condition
- Surface Finish
- Coating
- Thread Condition
- Bearing Surface Condition
- Friction Model
- Overall Friction Coefficient
- Thread Friction (future)
- Bearing Friction (future)
- Nut Factor (future)
- Scatter (future)
- Galling Risk
- Corrosion Influence
- Temperature Influence
- Torque Correction
- Engineering Warnings

### 10.3 Architecture

- Lubrication is a child component of Friction Condition, not the module itself.
- Surface finish and coatings are independent components alongside Lubrication, not folded into it.
- The schema is designed so future VDI 2230 and ISO 16047 friction models integrate without a further module rename (see ADR-0009).
- Current backend implementation status (Faz 2.6.0): `backend.library.models.LubricationRecord` (file `lubrication_library.py`, unchanged names -- see ADR-0009 for why) carries the Lubrication subsection's data, now extended with Friction-Condition-level fields (`overall_friction_coefficient_min/max`, `friction_model`, `mu_thread_min/max`, `mu_bearing_min/max`, `k_factor_min/max`, `scatter_percent`, `max_temperature_c`, `corrosion_resistance`, `reusability`, `recommended_standards`, `surface_condition`, and per-record source traceability: `source_reference`, `source_type`, `source_page_or_table`, `verification_status`, `applicability`, `engineering_notes`). Surface Condition, Coatings, Friction Model as independent domain concepts remain schema-only / not yet split into their own record types (Faz 2.6.1 decision).
- `backend/engineering_core/friction.py` and `backend/engineering_core/torque.py` already implement independent `mu_thread`/`mu_bearing` tightening-torque calculation (VDI-style decomposition), currently fed by direct API input, not by the library. Connecting library-sourced friction values to this calculation path is Faz 2.6.3 scope, not yet implemented.

### 10.4 Suggested UI sections (Faz 2.6.6, not yet implemented)

Navigation item: **Friction Condition**. Internal sections: Overview, Lubrication, Surface Condition, Coatings, Friction Properties, Engineering Notes, References.

### 10.5 Compatibility

No existing lubrication data was renamed, removed or restructured by the Faz 2.6 rename. `LUBRICATION_LIBRARY`, `lubrication_library.py`, `lubrication_library.json` and every field/record id predating Faz 2.6 are unchanged. See ADR-0009.

### 10.6 Faz 2.6.1 status (2026-07-23)

Schema extension confirmed as additive-flat (no nested `FrictionCoefficientSet` yet — ADR-0009 addendum). The 8-concept separation (surface condition, coating, lubricant, overall/combined coefficient, thread friction, bearing friction, nut factor, scatter) is documented on `LubricationRecord`'s docstring. Data-quality validation strengthened via `backend/library/validator.py::validate_lubrication_library` (8 checks), wired into `population.run_all_integrity_checks()`. No engineering coefficient value populated. Coating/Surface-Condition independence (whether they become their own record types) remains open for a later sub-phase.

