# TorqPro System Architecture


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Current architecture

TorqPro_24 is a compact FastAPI application serving a single HTML/PWA frontend and using SQLite. The backend currently combines identity, calculations, engineering pre-check, data governance, calibration, projects/revisions, release packaging, licensing and deployment administration in `backend/app.py`.

This implementation is deployable and testable, but the file concentration creates maintenance and verification risk. The approved next step is controlled modularization without breaking endpoints or data.

## 2. Target architecture: modular monolith

```text
Frontend/PWA
    |
FastAPI Application
    ├── identity
    ├── organizations
    ├── projects
    ├── joints
    ├── libraries
    ├── calculations
    ├── standards_rules
    ├── validations
    ├── reports_release
    ├── calibration_quality
    ├── data_governance
    ├── licensing
    └── deployment
         |
Application Services / Use Cases
         |
Domain Models and Engineering Ports
         |
Infrastructure: SQLite -> PostgreSQL, files/object storage, queues, integrations
```

The engineering core is a pure deterministic Python library with no FastAPI, database or UI dependency.

## 3. Proposed repository layout

```text
TorqPro_24/
  backend/
    app.py                    # composition root during migration
    api/v1/
    core/                     # config, security, errors, units
    modules/
      identity/
      projects/
      joints/
      libraries/
      calculations/
      rules/
      reports/
      calibration/
      governance/
      deployment/
    engineering/
      models/
      formulas/
      solvers/
      traces/
      validation/
    infrastructure/
      db/
      repositories/
      files/
      jobs/
  frontend/
  data/
  docs/
  tests/
    unit/
    integration/
    engineering_regression/
    e2e/
  migrations/
  scripts/
```

## 4. Layer responsibilities

### API layer

Authentication, request parsing, schema validation, response mapping and HTTP errors. No formulas or SQL.

### Application layer

Orchestrates use cases such as create revision, run calculation, activate data version and generate release package. Enforces permissions and transactions.

### Domain layer

Entities, value objects, invariants and domain services. No web or database imports.

### Engineering core

Unit-safe calculations, formula registry, intermediate results and trace generation. Coefficients enter through typed inputs and validated libraries; no hidden constants.

### Infrastructure layer

SQLite/PostgreSQL repositories, file storage, JWT, background jobs, export/import and external adapters.

## 5. Technology decisions

- Backend: Python + FastAPI retained.
- Current persistence: SQLite retained for local MVP; migration path to PostgreSQL.
- Frontend: current HTML/PWA retained while functionality is stabilized; React/TypeScript migration is optional and requires ADR.
- Background jobs: FastAPI background tasks for initial report/Monte Carlo; later RQ/Celery if operational need is proven.
- Deployment: Windows launcher, Docker and on-premise first; cloud later.
- Documentation: Markdown in repository is authoritative.

## 6. Calculation isolation

The calculation engine exposes a Python API such as:

```python
result = calculate_joint(snapshot, profile, formula_pack)
```

It returns typed results, warnings and formula traces. It cannot read global mutable JSON directly. Reference data is resolved and snapshotted before execution.

## 7. Security architecture

- Secrets must come from environment or secret manager; no production default.
- Passwords are salted and hashed.
- JWT includes user ID, role, issue/expiry and token version.
- RBAC checks occur server-side.
- Audit records cover login, data activation, calculations, approvals, exports, imports, license and deployment changes.
- Uploads have content/size/schema limits and are stored outside executable paths.
- Production uses HTTPS via reverse proxy.

## 8. Observability

Structured logs include request ID, user ID, action and calculation/project IDs without leaking sensitive payloads. Health endpoints distinguish liveness and readiness. Future metrics include request latency, calculation duration, job queue, failures, active data versions and report generation.

## 9. Evolution triggers

A module becomes a separate service only when independent scaling, security boundary, deployment ownership or integration load justifies it. Kafka/NATS, Neo4j, Elasticsearch and Kubernetes are future options, not MVP requirements.

## 10. Migration plan

1. Freeze existing behavior with tests.
2. Extract config/security/database utilities.
3. Extract identity/admin module.
4. Extract data governance and engine-library module.
5. Extract projects/revisions/release module.
6. Introduce engineering-core package and adapters for current pre-check.
7. Add joint revision domain and resource-oriented API.
8. Migrate schema with versioned migrations.
9. Keep compatibility endpoints until frontend is migrated.
