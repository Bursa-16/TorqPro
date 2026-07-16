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
