# TorqPro Deployment and Operations


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Supported modes

1. Local Windows via `TorqPro_24_Baslat.bat`.
2. Docker Compose for on-premise evaluation.
3. Reverse-proxy HTTPS with provided nginx baseline.
4. Future PostgreSQL/private-cloud deployment after migration.

## 2. Configuration

Secrets and environment-specific values reside in environment variables. `.env.example` contains placeholders only. Production requires strong `TORQPRO_SECRET_KEY`, configured origin/host policy, backup path and HTTPS.

## 3. Health

`/health/live` checks process. `/health/ready` checks database/schema/dependencies. `/api/health` and diagnostics provide administrative detail. Health must not leak secrets.

## 4. Data durability

Before upgrades: system export, database backup and migration test. Attachments and database are backed up together. Restore is tested periodically.

## 5. Docker

Images run as non-root where possible, pin supported dependencies, use healthcheck and mount persistent data. Reverse proxy terminates TLS. Do not expose database publicly.

## 6. Go-live checklist

- organization/license configured;
- admin password changed;
- strong secret set;
- HTTPS and DNS verified;
- readiness green;
- backup/restore tested;
- active data versions reviewed;
- quality gate and release certificate reviewed;
- logging/retention configured;
- user roles validated.

## 7. Cloud readiness

Cloud deployment is not equivalent to enterprise readiness. PostgreSQL, object storage, secret manager, centralized logs, job workers, tenant isolation and operational SLA must be completed before SaaS claims.

## 8. Mobile/PWA

PWA supports convenient access, not unrestricted offline engineering approval. Sensitive cached data and authentication behavior require security review.
