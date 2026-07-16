# TorqPro API Specification


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. General conventions

Base path for new endpoints: `/api/v1`. JSON, UTF-8, JWT bearer authentication. Resource names are plural. IDs are opaque. Timestamps are ISO 8601 UTC. Every write response includes audit/request identifiers where applicable.

Existing `/api/...` endpoints remain as compatibility API during migration.

## 2. Error format

```json
{
  "code": "validation.invalid_field",
  "message": "Diameter must be positive",
  "field": "fastener.nominal_diameter",
  "details": {},
  "request_id": "..."
}
```

HTTP 422 is for structurally/physically unprocessable input, not an engineering FAIL result. A completed calculation with failed safety checks returns 200 with `engineering_status: fail`.

## 3. Core endpoints

```text
POST /api/v1/projects
GET  /api/v1/projects
GET  /api/v1/projects/{project_id}
POST /api/v1/projects/{project_id}/assemblies
POST /api/v1/assemblies/{assembly_id}/joints
POST /api/v1/joints/{joint_id}/revisions
GET  /api/v1/joint-revisions/{revision_id}
POST /api/v1/joint-revisions/{revision_id}/submit
POST /api/v1/joint-revisions/{revision_id}/approve
POST /api/v1/joint-revisions/{revision_id}/reject
```

### Joint configuration

```text
POST /api/v1/joint-revisions/{id}/components
POST /api/v1/joint-revisions/{id}/interfaces
POST /api/v1/joint-revisions/{id}/load-cases
POST /api/v1/joint-revisions/{id}/tightening-specifications
```

### Calculations

```text
POST /api/v1/joint-revisions/{id}/calculations
GET  /api/v1/calculations/{calculation_id}
GET  /api/v1/calculations/{calculation_id}/trace
POST /api/v1/calculations/{calculation_id}/validations
POST /api/v1/calculations/{calculation_id}/reports
```

Request example:

```json
{
  "load_case_ids": ["LC-1"],
  "calculation_profile": "detailed_vdi_candidate",
  "formula_pack_version": "1.0.0-provisional",
  "rule_pack_ids": ["ISO898-1@2022"],
  "include_sensitivity": true,
  "execution": {"mode":"async", "monte_carlo_samples":1000},
  "client_request_id":"uuid"
}
```

The service resolves the revision and libraries, creates immutable input snapshot, then runs. It does not accept a large mutable project payload as the authoritative source.

## 4. Library endpoints

```text
GET /api/v1/fastener-definitions
GET /api/v1/fastener-definitions/{id}
GET /api/v1/supplier-parts
GET /api/v1/oem-approvals
GET /api/v1/threads
GET /api/v1/materials
GET /api/v1/materials/{id}/property-sets
GET /api/v1/coatings
GET /api/v1/lubricants
GET /api/v1/friction-conditions
GET /api/v1/tools
GET /api/v1/tools/{id}/calibrations
```

Every engineering property includes value, unit, temperature/condition, source and validation status.

## 5. Rules and reports

```text
GET  /api/v1/standards
GET  /api/v1/rule-packs
GET  /api/v1/validation-runs/{id}
GET  /api/v1/reports/{id}
POST /api/v1/joint-revisions/{id}/release-packages
```

Report generation requires a completed immutable calculation. Re-running from a full payload is not allowed inside report endpoint.

## 6. Jobs

Detailed simulation/report jobs return 202:

```text
GET /api/v1/jobs/{job_id}
POST /api/v1/jobs/{job_id}/cancel
```

Job output references calculation/report resources. Job records include progress and structured error.

## 7. Idempotency

Create calculation/report/release operations accept `Idempotency-Key` or `client_request_id`. Reuse with different payload hash returns 409.

## 8. Traceability response

Every calculation exposes engine version, formula pack, rule packs, active data versions, input hash, creator and timestamp. Formula trace uses corrected load-sharing equations and never embeds rejected formulas.

## 9. Authorization scopes

- `project:read/write`
- `calculation:read/run`
- `validation:run`
- `report:create`
- `approval:review`
- `library:manage`
- `data:approve/activate`
- `admin:system`

## 10. OpenAPI and compatibility

FastAPI OpenAPI is generated and checked in CI. Existing endpoints such as `/api/engineering/check`, `/api/projects`, `/api/admin/data-versions` and deployment endpoints remain documented as legacy v0 until frontend migration.
