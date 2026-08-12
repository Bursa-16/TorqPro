# TorqPro API Specification


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-08-12 (§1, §10 corrected and §12 added to reflect the actual implemented `/api/...` surface; the original §3–§9 `/api/v1` target design is unchanged and explicitly marked unimplemented)
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. General conventions

`/api/v1` below describes this document's original (2026-07-16) target design for new endpoints. As of this update, no `/api/v1` route has ever been implemented: every endpoint added since the SDS baseline -- including all of §11 (Faz 2.5A), the Question Bank, Governance, AI Gateway, Torque Recommendation, and Engineering Reasoning surfaces -- has used the `/api/...` convention documented in §11 and §12. JSON, UTF-8, JWT bearer authentication. Resource names are plural. IDs are opaque. Timestamps are ISO 8601 UTC. Every write response includes audit/request identifiers where applicable.

`/api/...` is the actual, current API surface, not a temporary compatibility layer during a migration -- no such migration has started since this document's baseline.

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

> Sections 3–9 describe the original `/api/v1` target design as proposed in the 2026-07-16 baseline. None of the `/api/v1/...` paths below have been implemented; they are not verified against the running code. For the actual, currently implemented API surface, see §11 (Faz 2.5A) and §12 below, both of which use the real `/api/...` convention.

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

FastAPI's built-in OpenAPI generation is available at runtime (`/openapi.json`, `/docs`, `/redoc`). It is not checked as a standalone CI step, but `app.openapi()`'s registered-paths output is inspected by regression tests that do run in CI via `pytest -q` (e.g. `tests/ai/test_ai_disabled_noop.py`'s route-set assertions). Endpoints such as `/api/engineering/check`, `/api/projects`, `/api/admin/data-versions` and the deployment endpoints are the actual, current API -- as of this update there is no `/api/v1` implementation and no evidence of an active or planned migration to one.

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

## 12. Dedicated route modules added since §11 (verified against `backend/api/routes/`)

All under the same legacy-v0 `/api/...` convention as §11 -- still no
`/api/v1` namespace anywhere in the running code. Listed by module,
not by phase narrative (see `docs/CHANGELOG.md` for phase-level detail
and request/response schemas):

```text
backend/api/routes/joints.py
  POST   /api/joints
  GET    /api/joints
  GET    /api/joints/{joint_id}
  POST   /api/joints/{joint_id}/revisions
  GET    /api/joints/revisions/{revision_id}
  POST   /api/joints/revisions/{revision_id}/submit
  POST   /api/joints/revisions/{revision_id}/approve
  POST   /api/joints/revisions/{revision_id}/reject

backend/api/routes/question_bank.py
  GET    /api/question-bank/stats
  POST   /api/question-bank/stats/snapshot
  GET    /api/question-bank/stats/history
  POST   /api/question-bank/questions/select
  GET    /api/question-bank/questions
  POST   /api/question-bank/questions
  GET    /api/question-bank/questions/{question_id}
  PATCH  /api/question-bank/questions/{question_id}
  POST   /api/question-bank/{question_id}/archive
  POST   /api/question-bank/{question_id}/restore
  DELETE /api/question-bank/{question_id}
  POST   /api/question-bank/questions/{question_id}/submit-for-review
  POST   /api/question-bank/questions/{question_id}/validate
  POST   /api/question-bank/questions/{question_id}/reject
  POST   /api/question-bank/questions/{question_id}/deprecate
  GET    /api/question-bank/questions/{question_id}/audit
  GET    /api/question-bank/questions/{question_id}/status-history
  POST   /api/question-bank/questions/bulk/transition
  POST   /api/question-bank/questions/bulk/tags
  GET    /api/question-bank/export
  POST   /api/question-bank/import

backend/api/routes/washer_resolution_closure.py
  POST   /api/library/washers/resolutions/{resolution_id}/evidence
  GET    /api/library/washers/resolutions/{resolution_id}/evidence
  GET    /api/library/washers/resolutions/{resolution_id}/closure-readiness
  POST   /api/library/washers/resolutions/{resolution_id}/close
  GET    /api/library/washers/resolutions/{resolution_id}/closure

backend/api/routes/ai_gateway.py  (v3.0.0-alpha.1 through beta.2)
  POST   /api/ai/query
  GET    /api/ai/providers
  GET    /api/ai/audit
  GET    /api/ai/audit/{audit_id}
  POST   /api/ai/engineering-reasoning

backend/api/routes/torque_recommendation.py  (v3.0.0-beta.1)
  POST   /api/ai/torque-recommendation
```

Governance workspace routes (Faz 2.8.11–2.8.13) live in their own
router module, `backend/governance/api.py` (prefix `/api/governance`,
`app.include_router(governance_router)` in `backend/app.py`):

```text
backend/governance/api.py
  GET    /api/governance/{aggregate_id}/history
  GET    /api/governance/{aggregate_id}/status
  GET    /api/governance/joint-revision/{revision_id}
  GET    /api/governance/joint-revisions
  GET    /api/governance/joint-revisions/query
  POST   /api/governance/review/{aggregate_id}/submit
  POST   /api/governance/review/{aggregate_id}/approve
  POST   /api/governance/review/{aggregate_id}/reject
  POST   /api/governance/publication/{aggregate_id}/activate
  POST   /api/governance/publication/{aggregate_id}/supersede
  POST   /api/governance/publication/{aggregate_id}/archive
  POST   /api/governance/resolution/{aggregate_id}/resolve
  POST   /api/governance/resolution/{aggregate_id}/reject
  POST   /api/governance/resolution/{aggregate_id}/waive
```

See the corresponding `docs/314_Roadmap.md` entries for phase-level
scope detail.
