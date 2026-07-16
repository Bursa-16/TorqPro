# TorqPro Advisory AI Architecture


> **Document set:** TorqPro Software Design Specification (SDS) v1.0  
> **Status:** Approved baseline for implementation planning; engineering equations marked PROVISIONAL are not approved for production calculations.  
> **Product owner:** İlhan Çekiç  
> **Last updated:** 2026-07-16  
> **Source of truth:** This repository. When code and documentation conflict, stop implementation and open an ADR/change request.

## 1. Boundary

AI is advisory. It cannot replace deterministic calculations, modify approved data, approve releases or invent standards coefficients.

## 2. Use cases

- Search and summarize approved project/library/report data.
- Explain calculation results in user language using formula trace.
- Recommend missing inputs or next workflow step.
- Suggest alternatives and trade-offs after deterministic recalculation.
- Classify field failure descriptions and retrieve similar cases.
- Detect anomalies in tightening/calibration datasets.
- Draft reports and review checklists.

## 3. Grounding

Responses are grounded in current joint context, approved formula trace, active rule packs, approved reference data and permission-filtered historical cases. Each answer cites internal record IDs and marks assumptions.

## 4. Safety controls

- No ungrounded numeric recommendation.
- No hidden calculation outside engineering core.
- No use of confidential data across organizations.
- Human approval for engineering actions.
- Prompt/input/output audit with sensitive-data controls.
- “Insufficient evidence” response when sources are unavailable.

## 5. Architecture

AI gateway -> permission/context builder -> retrieval -> deterministic engineering tools -> response composer -> evidence checker. Models are replaceable. The product must work without AI.

## 6. Future optimization

Optimization enumerates alternatives through deterministic engine and objective functions such as mass, cost, clamp margin and process capability. AI may explain Pareto alternatives but not fabricate results.
