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

## 11. Faz 2.5A — Production Validation endpoints (2026-07-22)

Added under the existing legacy-v0 `/api/...` convention (not `/api/v1`,
consistent with how `/api/projects` and `/api/revisions` are already
implemented; no `/api/v1` namespace exists in the running code yet):

```text
POST   /api/validation-studies
GET    /api/validation-studies
GET    /api/validation-studies/{study_id}
PATCH  /api/validation-studies/{study_id}
POST   /api/validation-studies/{study_id}/datasets
GET    /api/validation-studies/{study_id}/datasets
GET    /api/measurement-datasets/{dataset_id}
PATCH  /api/measurement-datasets/{dataset_id}
POST   /api/measurement-datasets/{dataset_id}/lock
POST   /api/measurement-datasets/{dataset_id}/records
POST   /api/measurement-datasets/{dataset_id}/records/bulk
GET    /api/measurement-datasets/{dataset_id}/records
POST   /api/measurement-records/{record_id}/invalidate
POST   /api/validation-studies/{study_id}/complete
POST   /api/validation-studies/{study_id}/submit
POST   /api/validation-studies/{study_id}/approve
POST   /api/validation-studies/{study_id}/reject
POST   /api/validation-studies/{study_id}/archive
```

Implemented in `backend/api/routes/production_validation.py` (first
dedicated route module in the repository — thin handlers only, all logic
in `backend/production_validation/service.py`). Error codes: 404 not
found, 409 conflict (duplicate code / duplicate CSV import), 400 locked or
invalid state transition, 422 data-integrity or CSV row-validation
failure. See `docs/phases/PHASE_2.5A_PRODUCTION_VALIDATION_FOUNDATION.md`
for the full state machine and validation rules.
