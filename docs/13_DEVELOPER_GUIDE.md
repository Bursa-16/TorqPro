# TorqPro Developer Guide


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Workflow

Use feature branches. Small commits with meaningful messages. Pull request references backlog and ADR. Documentation changes accompany domain/API/formula changes.

## 2. Python

Type hints, Pydantic schemas, explicit Decimal where precision matters, no hidden globals in engineering core, dependency injection through constructors/functions, structured exceptions and UTC timestamps.

## 3. Database

Repository pattern or explicit data-access functions per module. Parameterized queries only. Transactions for multi-step state changes. Migrations mandatory.

## 4. API

Thin routes, resource naming, structured errors, idempotency for expensive creates, server-side permissions and immutable result resources.

## 5. Frontend

Do not embed formulas. Use API schemas. Show units, source and validation state. Keep Turkish/English labels centralized. Preserve PWA assets.

## 6. Engineering code

Pure functions, typed input/output, formula IDs, dimensional checks, no arbitrary fallback. Warnings are data, not console text. Rounding only at presentation/export.

## 7. Code quality

Target tools: Ruff, Black, mypy/pyright, pytest, coverage and pre-commit. Introduce incrementally without unrelated mass formatting.

## 8. Commit conventions

Examples: `docs: add SDS baseline`, `refactor: extract security module`, `feat(joints): add revision aggregate`, `test(engineering): add load-sharing golden cases`.

## 9. Definition of done

Code, tests, docs, migration, security review, backward-compatibility note and changelog are complete. Build/tests pass. No unsupported engineering claim.
