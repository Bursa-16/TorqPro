# TorqPro Testing and Engineering Validation Strategy


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Test pyramid

- Unit tests: domain, units, formulas, rules.
- Integration tests: API/database/auth/versioning/report.
- Engineering regression: golden cases and boundary datasets.
- E2E: critical user workflows.
- Deployment: Docker, health, migration, PWA, DNS/go-live.

## 2. Existing coverage

The current package tests health, authentication, calculation storage, engineering pre-check monotonic torque, validation honesty, data packages/versions, engine library, quality gate, golden cases, release certificate, projects/release traceability, enterprise licensing, deployment/migration, PWA, cloud readiness and go-live profile.

These tests must be retained and reorganized, not discarded.

## 3. Engineering validation levels

Level 0 dimensional/unit checks. Level 1 hand-calculation unit cases. Level 2 golden cases from controlled references. Level 3 comparison with trusted software/test data. Level 4 independent reviewer sign-off and customer validation.

Only formulas reaching required level may be marked APPROVED.

## 4. Mandatory formula tests

- nominal and boundary values;
- monotonic behavior;
- unit conversions;
- zero/negative/invalid input;
- material/temperature validity;
- uncertainty deterministic seed;
- formula trace completeness;
- regression tolerance.

Load-sharing tests must prove service bolt force increases with separating load while residual clamp decreases by `(1-Phi)` share.

## 5. Rule tests

Pass, exact boundary, fail, missing input, not applicable, conflicting override and retired version.

## 6. Data governance tests

Invalid package cannot pass gate. Approval and activation are separate. Rollback affects future calculations only. Existing calculation trace retains old version.

## 7. Release gates

- all tests pass;
- no critical security issue;
- migrations tested from previous supported schema;
- golden cases within tolerance;
- documentation updated;
- release certificate truthfully reflects engineering maturity.

## 8. Test reports

CI/local release generates machine-readable and human summary with commit, environment, versions, pass/fail and known skipped validations.
