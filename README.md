# TorqPro AI

> AI-powered fastener engineering, deterministic torque recommendation, engineering reasoning, validation, traceability, and knowledge platform.

---

## Overview

TorqPro AI is a professional engineering platform for the design, analysis, validation, optimization, and governance of threaded joints and tightening processes.

The platform combines deterministic engineering calculations, validated engineering knowledge, lifecycle management, traceability, deterministic engineering reasoning, and controlled AI-assisted engineering workflows.

The core engineering philosophy is simple:

> **Deterministic engineering calculations remain authoritative. AI is additive, explainable, traceable, and cannot override validated engineering results.**

---

# Key Features

## Fastener Engineering

* VDI 2230-based threaded joint engineering
* Torque and preload calculations
* Deterministic Torque Recommendation Engine
* Torque-window evaluation
* Friction condition and lubrication modelling
* Thread geometry and fastener calculations
* Bolt, nut and washer engineering libraries
* Joint definition and revision management
* Engineering formula validation
* Fastener Assembly Intelligence
* Torque Study workflows
* Production validation
* Fail-closed engineering recommendation logic

## Engineering Reasoning

* **Engineering Reasoning Engine**
* Beta.1 `trace_id` based reasoning
* Structured engineering evidence consumption
* Deterministic-result preservation
* No Torque Recommendation recomputation
* Structured reasoning states:

  * `SUPPORTED`
  * `INSUFFICIENT_EVIDENCE`
  * `UNSUPPORTED`
* Engineering fact / evidence / reasoning separation
* Fail-closed handling of insufficient evidence
* Optional AI-assisted explanation
* Provider-failure isolation
* Cross-user trace authorization
* Reasoning audit traceability
* OEM / proprietary output protection

## Engineering Knowledge

* Engineering Library
* Question Bank infrastructure
* Question retrieval
* Question creation and editing
* Lifecycle management
* Tagging and search
* Bulk lifecycle operations
* Import / export
* Statistics and dashboards
* Trend and history analysis
* Controlled engineering knowledge

## Quality & Governance

* Validation workflows
* Governance workflows
* Engineering traceability
* Auditability
* Version centralization
* Regression validation
* Multilingual UI validation
* Controlled engineering evidence
* Project ownership authorization controls
* Recommendation audit traceability
* Reasoning audit traceability
* Request correlation with `X-Request-ID`

## AI Architecture

* AI retrieval and grounding
* Explainability framework
* AI HTTP Gateway
* Persistent AI audit trail
* AI provider abstraction
* Deterministic / offline provider support
* Provider discovery
* Secure prompt / response hash traceability
* Fail-closed safety behaviour
* Controlled AI-to-engineering boundary
* Deterministic Torque Recommendation Engine
* Engineering Reasoning Engine
* AI/provider-independent numeric recommendation
* Optional AI wording layer
* Provider-failure isolation

---

# Current Version

| Item                       | Value                                                   |
| -------------------------- | ------------------------------------------------------- |
| Product                    | **TorqPro AI**                                          |
| Current Version            | **v3.0.0-rc.1**                                         |
| Release Stage              | **Release Candidate**                                   |
| Release Status             | **Pre-release**                                         |
| Current Engineering Focus  | **Release Validation / Stable Readiness**                |
| Final Commit               | `245e2937863271af220308e1783302f4730f57b8`              |
| rc.1 New Tests             | **72 passed** (+13 opt-in performance benchmarks, skipped by default) |
| Full Test Suite            | **3371 passed, 13 skipped**                             |
| Next Phase                 | **v3.0.0 — Stable Release**                             |

---

# What's New in v3.0.0-rc.1

TorqPro AI v3.0.0-rc.1 is a **release-hardening** phase — no new AI capability, no new engineering engine, and no product feature was added. Its purpose was to validate, secure, and document the platform ahead of a stable v3.0.0 release, building directly on the deterministic engineering core and the Torque Recommendation / Engineering Reasoning Engines delivered in Beta.1/Beta.2.

## Documentation & Release Consistency

* `docs/314_Roadmap.md` synchronized with the actual repository state (Beta.1/Beta.2 completion, rc.1 scope)
* `docs/07_API_SPECIFICATION.md` corrected to reflect the API surface actually implemented (the documented `/api/v1` namespace was never built; every real endpoint uses the existing `/api/...` convention)
* `DOCUMENTATION_MANIFEST.json` checksum/metadata brought back in sync with current file contents

## Security Hardening

* Allowed-host enforcement (`TORQPRO_ALLOWED_HOSTS`, via Starlette's `TrustedHostMiddleware`) — previously documented but never enforced
* Production API documentation restriction — `/docs`, `/redoc`, `/openapi.json` are disabled when `TORQPRO_ENV=production`
* A real cross-user authorization gap found and fixed during hardening: calculation creation now verifies project ownership before association, closing a path that could attach a calculation to another user's project
* General API rate limiting — centralized, opt-in, per-session sliding-window limiter for authenticated API traffic (default off; does not change behavior unless explicitly configured)
* Security response headers — Content-Security-Policy (with `'unsafe-inline'` for script/style, matching the current single-file frontend) and Strict-Transport-Security (production-only)
* Exception-detail leakage fixes — a small number of endpoints that echoed raw internal error text back to the client now return a fixed, safe message while still logging full detail server-side
* `pip-audit` dependency security scanning added to CI

## Performance & Reliability

* A reusable, opt-in performance benchmark suite (`tests/performance/`) covering every critical request path, producing p50/p95/p99 latency and throughput — skipped by default so the normal test suite is unaffected
* SQLite WAL journal mode and a `busy_timeout` enabled on the database connection, reducing commit overhead and lock-contention risk under concurrent access
* Concurrency validation — concurrent read/write smoke tests confirming no errors, no lost writes, and no data corruption under simultaneous requests
* Critical-path profiling across calculation creation, project traceability/release-package, the Torque Recommendation and Engineering Reasoning Engines, the AI gateway path, and Question Bank retrieval
* A reproducible local performance baseline for future comparison

---

# What's New in v3.0.0-beta.2

## Engineering Reasoning Engine

TorqPro AI v3.0.0-beta.2 introduces the **Engineering Reasoning Engine**, a structured and traceable reasoning layer built on top of validated deterministic engineering results.

Beta.2 extends TorqPro from deterministic recommendation generation into controlled engineering interpretation while preserving the deterministic engineering layer as the source of truth.

The reasoning workflow is:

```text
Beta.1 Deterministic Result
        │
        ▼
      trace_id
        │
        ▼
Stored Structured Result & Evidence
        │
        ▼
Engineering Reasoning Engine
        │
        ▼
Structured Reasoning Result
        │
        ▼
Optional AI Explanation
```

The Engineering Reasoning Engine does **not** rerun the Torque Recommendation Engine.

---

## Deterministic Engineering Authority

Beta.2 maintains a strict separation between:

1. **Deterministic engineering facts**
2. **Validated engineering rules and evidence**
3. **Derived engineering reasoning**
4. **Optional AI-assisted explanation**

The reasoning layer cannot:

* modify deterministic torque results;
* modify validated engineering outputs;
* override engineering validation;
* silently generate missing engineering inputs;
* recompute the Beta.1 Torque Recommendation;
* convert insufficient evidence into a supported conclusion.

The original deterministic engineering result remains authoritative and immutable.

---

## Beta.1 Trace Integration

Beta.2 consumes an existing Beta.1 Torque Recommendation through its `trace_id`.

This provides a controlled relationship between the original deterministic recommendation and the subsequent engineering reasoning process.

```text
Torque Recommendation
        │
        ▼
     trace_id
        │
        ▼
Stored Engineering Evidence
        │
        ▼
Engineering Reasoning
```

The existing structured Beta.1 result is retrieved and evaluated rather than recalculated.

This prevents parallel calculation paths and preserves a single engineering source of truth.

---

## Structured Reasoning States

Every reasoning result is classified into one of three explicit states:

| State                   | Meaning                                                                         |
| ----------------------- | ------------------------------------------------------------------------------- |
| `SUPPORTED`             | Available deterministic results and engineering evidence support the conclusion |
| `INSUFFICIENT_EVIDENCE` | Available evidence is insufficient to establish a supported conclusion          |
| `UNSUPPORTED`           | Available engineering evidence does not support the conclusion                  |

Beta.2 does not introduce an AI-generated numerical confidence score.

Missing or incomplete evidence therefore produces an explicit engineering state rather than a guessed conclusion.

---

## Fail-Closed Reasoning Behaviour

The Engineering Reasoning Engine follows TorqPro's fail-closed engineering philosophy.

If evidence is:

* missing;
* incomplete;
* corrupt;
* inaccessible;
* or insufficient,

the engine does not invent engineering information.

Instead, the result is explicitly classified according to the available evidence.

This preserves the distinction between:

> **What TorqPro knows, what the engineering evidence supports, and what cannot currently be concluded.**

---

## AI Explanation Boundary

AI-generated wording is optional and isolated from deterministic engineering reasoning.

The AI provider does not determine:

* torque;
* preload;
* engineering validation;
* reasoning state;
* deterministic engineering facts;
* recommendation applicability.

If an AI provider is unavailable or fails:

* deterministic engineering results remain unchanged;
* structured reasoning remains available;
* the optional AI explanation fails safely.

Engineering reasoning therefore does not depend on an external LLM being available.

---

## Evidence & Traceability

Beta.2 reuses TorqPro's existing audit infrastructure.

The relationship between a reasoning event and its original Beta.1 recommendation is preserved through structured evidence metadata referencing the source `trace_id`.

Conceptually:

```text
Reasoning Audit
      │
      └── torque_recommendation
                │
                └── Beta.1 trace_id
```

The existing `ai_audit_records` infrastructure is reused.

No separate reasoning database or database migration was introduced.

Traceability can include:

* source Torque Recommendation trace
* reasoning request
* evidence relationship
* reasoning state
* request correlation
* authenticated user context
* audit record
* optional AI provider information

---

## Authorization

Beta.2 protects stored engineering traces through ownership-aware authorization.

The reasoning API handles:

* valid owned traces;
* unknown traces;
* cross-user trace access;
* authorized administrative access;
* corrupt stored records;
* incomplete stored evidence.

Cross-user access to protected engineering traces is rejected.

---

## Engineering Reasoning API

Beta.2 introduces:

`POST /api/ai/engineering-reasoning`

The endpoint provides structured access to engineering reasoning based on an existing Beta.1 `trace_id`.

Request correlation continues to support:

`X-Request-ID`

The endpoint preserves TorqPro's deterministic engineering and authorization boundaries.

---

## OEM / Proprietary Information Protection

Beta.2 includes regression protection against unintended OEM or proprietary engineering-source exposure.

Public and controlled outputs remain separated from protected engineering-source information.

The reasoning layer does not create a new path for proprietary engineering-rule disclosure.

---

# Beta.1 Foundation

## Deterministic Torque Recommendation Engine

Beta.2 builds directly on the **Deterministic Torque Recommendation Engine** introduced in v3.0.0-beta.1.

Beta.1 established the workflow:

```text
Engineering Inputs
        │
        ▼
Deterministic Joint Analysis
        │
        ▼
Engineering Validation
        │
        ▼
Recommendation Candidate
        │
        ▼
Confidence / Applicability
        │
        ▼
Engineering Explainability
        │
        ▼
Audit / Traceability
```

The Torque Recommendation Engine is built on:

`backend/calculation_engine/joint_analysis.py::analyze_joint()`

Existing deterministic engineering outputs are reused, including:

* recommended torque calculation
* torque window
* preload-related engineering results
* safety status
* readiness
* engineering coverage
* warnings
* critical findings
* formula traceability

No parallel AI-generated torque calculation path has been introduced.

---

## Beta.1 Fail-Closed Recommendation Behaviour

If critical engineering findings are present:

* the underlying calculated result may remain visible for traceability;
* `recommended_torque` is withheld;
* applicability indicates that a usable recommendation cannot be issued;
* warnings and explanations identify the reason.

A calculated value therefore cannot automatically become an engineering recommendation when validation conditions are not satisfied.

---

## Deterministic Confidence Classification

Beta.1 recommendation confidence is determined using engineering conditions rather than AI-generated probability scores.

| Classification   | Purpose                                                       |
| ---------------- | ------------------------------------------------------------- |
| `HIGH`           | Strong engineering completeness and validation                |
| `MEDIUM`         | Valid recommendation with relevant assumptions or limitations |
| `LOW`            | Significant limitations or incomplete engineering support     |
| `NOT_APPLICABLE` | No usable engineering recommendation can be issued            |

The classification is derived from deterministic factors such as readiness, coverage, warnings, assumptions, and critical findings.

This Beta.1 confidence classification is separate from the Beta.2 reasoning-state model.

---

# Validation

TorqPro AI v3.0.0-beta.2 completed the following validation:

| Validation                                             | Result          |
| ------------------------------------------------------ | --------------- |
| New Beta.2 tests                                       | **56 passed**   |
| AI Gateway + Torque Recommendation targeted validation | **242 passed**  |
| Full test suite                                        | **3299 passed** |
| `flake8`                                               | **Clean**       |
| `git diff --check`                                     | **Clean**       |
| Bundle clone verification                              | **Passed**      |
| Bundle sanity validation                               | **93 passed**   |
| Patch replay verification                              | **Passed**      |
| Tree hash comparison                                   | **Exact match** |
| Beta.1 recomputation protection                        | **Passed**      |
| Provider failure isolation                             | **Passed**      |
| Cross-user authorization                               | **Passed**      |
| OEM/proprietary leakage regression                     | **Passed**      |
| Database migration                                     | **None**        |

---

# Development Roadmap

| Version           | Scope                                   | Status          |
| ----------------- | --------------------------------------- | --------------- |
| v3.0.0-alpha.1    | AI Architecture Foundation              | ✅ Completed     |
| v3.0.0-alpha.2    | Retrieval & Grounding                   | ✅ Completed     |
| v3.0.0-alpha.3    | Safety & Explainability                 | ✅ Completed     |
| v3.0.0-alpha.4    | AI HTTP Exposure                        | ✅ Completed     |
| v3.0.0-alpha.5    | Persistent Audit & Provider Abstraction | ✅ Completed     |
| v3.0.0-alpha.6    | Frontend AI Integration                 | ✅ Completed     |
| v3.0.0-beta.1     | Torque Recommendation Engine            | ✅ Completed     |
| v3.0.0-beta.2     | Engineering Reasoning Engine             | ✅ Completed     |
| **v3.0.0-rc.1**   | **Performance, Security & Documentation** | **✅ Completed** |
| v3.0.0            | Stable Release                          | ⏭️ Next         |

---

# Next Phase

## v3.0.0 — Stable Release

The next phase will finalize TorqPro AI v3.0.0 as a stable release, building on the release-candidate hardening completed in rc.1.

The deterministic engineering layer will continue to remain the source of truth.

No new AI capability should compromise the validated engineering boundaries established through the Alpha, Beta, and rc.1 phases.

---

# Release

**Current Release:** `v3.0.0-rc.1`

**Release Commit:**

`245e2937863271af220308e1783302f4730f57b8`

**Status:** Release Candidate / Pre-release

**Main Capability:** Release Validation / Stable Readiness

**Next Milestone:** `v3.0.0 — Stable Release`

---

## Engineering Principle

> **Calculate deterministically. Reason from evidence. Explain transparently. Preserve traceability.**
