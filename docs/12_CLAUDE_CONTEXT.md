# Mandatory AI Development Context


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Mandatory instruction

Before changing any code, read this file and all documents listed in `docs/README.md`. These documents are the source of truth. Do not redesign TorqPro from generic assumptions.

## 2. Product identity

TorqPro is a commercial bolted-joint engineering and tightening assurance platform. It is separate from DatumIQ, Spot Welding Platform, Spot Welding Parameter Analysis and OptiFactory. Never merge their physics, data or product scope.

## 3. Current repository

The current product is FastAPI + SQLite + single-page HTML/PWA. It has working features in authentication, calculations, engineering pre-check, reference-data governance, calibration, quality gate, projects/revisions/approval, release package, licensing, deployment, PWA and go-live checks. Preserve these.

## 4. Non-negotiable engineering rules

- AI never replaces deterministic calculations.
- Do not invent coefficients or standards rules.
- Do not use resistance-welding equations or terms.
- Correct load sharing is:
  - bolt increment = `Phi * external axial load`
  - clamp reduction = `(1-Phi) * external axial load`
  - service bolt force = preload + bolt increment
  - residual clamp = preload - clamp reduction
- Quick nut-factor equation includes nominal diameter: `M = K*d*F`.
- Prevailing torque is measured/test-derived unless an approved model says otherwise.
- Serial compliances are summed; serial stiffnesses are not directly added.
- Every formula has ID, units, classification, validity and source.
- Formula changes require documentation, ADR, tests and approval.

## 5. Development rules

- Implement one approved backlog item at a time.
- Business/engineering logic must not be placed in frontend or route handlers.
- Preserve API compatibility unless migration is documented.
- Write unit and integration tests.
- Do not mark provisional calculation as production-approved.
- Never delete history; create revisions.
- Do not copy full copyrighted standards into repository without authorization.

## 6. Required response before coding

Summarize:

1. documents read;
2. current architecture/features;
3. exact backlog item;
4. files to modify/create;
5. tests to run;
6. risks and assumptions.

Then wait for approval unless the user explicitly instructed immediate implementation.

## 7. Required delivery format

- Changed files
- What was implemented
- Engineering behavior
- Tests/build results
- Known limitations
- Technical debt
- Next backlog item
- Deliverable ZIP or commit-ready patch when requested

## 8. Current next action

Follow `11_PRODUCT_BACKLOG.md`, Sprint “Documentation-integrated foundation and safe modularization.” Do not begin detailed engineering formulas until the formula specification is validated.
