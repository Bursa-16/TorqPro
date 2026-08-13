# Current Version

| Item                      | Value                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------ |
| Product                   | **TorqPro AI**                                                                       |
| Current Version           | **v3.0.1**                                                                           |
| Release Stage             | **Stable**                                                                           |
| Release Status            | **Stable Maintenance Release**                                                       |
| Current Engineering Focus | **Contextual AI UX + Deterministic Engineering + AI Reasoning**                      |
| Stable Baseline           | `v3.0.0`                                                                             |
| AI UX Integration Commit  | `25aca30edd724f6055d36f7a50aa78a057814631`                                           |
| v3.0.1 Release Commit     | `a49941e`                                                                            |
| Full Test Suite           | **3408 passed, 13 skipped**                                                          |
| Next Phase                | **Torque “Explain with AI” / trace_id integration & calculation-path consolidation** |

---

# Development Roadmap

| Version        | Scope                                   | Status          |
| -------------- | --------------------------------------- | --------------- |
| v3.0.0-alpha.1 | AI Architecture Foundation              | ✅ Completed     |
| v3.0.0-alpha.2 | Retrieval & Grounding                   | ✅ Completed     |
| v3.0.0-alpha.3 | Safety & Explainability                 | ✅ Completed     |
| v3.0.0-alpha.4 | AI HTTP Exposure                        | ✅ Completed     |
| v3.0.0-alpha.5 | Persistent Audit & Provider Abstraction | ✅ Completed     |
| v3.0.0-alpha.6 | Frontend AI Integration                 | ✅ Completed     |
| v3.0.0-beta.1  | Torque Recommendation Engine            | ✅ Completed     |
| v3.0.0-beta.2  | Engineering Reasoning Engine            | ✅ Completed     |
| v3.0.0-rc.1    | Performance, Security & Documentation   | ✅ Completed     |
| v3.0.0         | Stable Release                          | ✅ Completed     |
| **v3.0.1**     | **Contextual AI UX Integration**        | **✅ Completed** |

---

# Release

**Current Release:** `v3.0.1`

**Status:** Stable Maintenance Release

**Main Capability:** Contextual TorqPro AI access across selected engineering workflows while preserving deterministic engineering calculations as authoritative.

### v3.0.1 Highlights

* Global **✨ TorqPro AI** access in the application topbar
* **✨ Ask TorqPro AI** integration in Joint Analysis
* **✨ Ask TorqPro AI** integration in Question Bank
* **✨ AI Review** integration in the Validation panel
* Active-screen and engineering-context awareness
* Reuse of the existing grounded AI backend through `POST /api/ai/query`
* TR/EN localization for the new AI UX
* Safe handling of provider unavailability and AI HTTP errors
* Deterministic engineering workflows remain fully available when AI is unavailable
* No AI override of deterministic engineering results
* No automatic validation approval/rejection by AI

---

## Deferred

Torque Recommendation **“Explain with AI”** is intentionally deferred.

The current frontend torque-calculation semantics do not yet map safely to the existing `trace_id`-based Engineering Reasoning workflow.

The next development phase will address:

* `trace_id` architecture
* calculation-path consolidation
* deterministic frontend/backend consistency
* safe integration of `POST /api/ai/torque-recommendation`
* contextual use of `POST /api/ai/engineering-reasoning`

No duplicate deterministic calculation path or fabricated `trace_id` has been introduced in v3.0.1.

---

## Validation

**Full Test Suite:** `3408 passed, 13 skipped`

**git diff --check:** Clean

**Working Tree:** Clean

**VERSION:** `3.0.1`

---

## Engineering Principle

> **Calculate deterministically. Reason from evidence. Explain transparently. Preserve traceability.**
