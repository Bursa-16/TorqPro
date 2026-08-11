# TorqPro AI

> AI-powered fastener engineering, validation, traceability, and knowledge platform.

---

## Overview

TorqPro AI is a professional engineering platform for the design, analysis, validation, optimization, and governance of threaded joints and tightening processes.

The platform combines deterministic engineering calculations, validated engineering knowledge, lifecycle management, traceability, and AI-assisted engineering workflows.

The core engineering philosophy is simple:

> **Deterministic engineering calculations remain authoritative. AI is additive, explainable, traceable, and cannot override validated engineering results.**

---

# Key Features

## Fastener Engineering

* VDI 2230 implementation
* Torque and preload calculations
* Friction condition and lubrication modelling
* Threaded joint engineering
* Bolt, nut and washer engineering libraries
* Joint revision management
* Engineering formula validation
* Fastener Assembly Intelligence
* Torque Study workflows
* Production validation

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

## Quality & Governance

* Validation workflows
* Governance workflows
* Engineering traceability
* Auditability
* Version centralization
* Regression validation
* Multilingual UI validation
* Controlled engineering evidence

## AI Architecture

* AI retrieval and grounding
* Explainability framework
* AI HTTP Gateway
* Persistent AI audit trail
* AI provider abstraction
* Deterministic/offline provider support
* Provider discovery
* Secure prompt/response hash traceability
* Fail-closed safety behaviour
* Controlled AI-to-engineering boundary

---

# Current Version

| Item                      | Value                                          |
| ------------------------- | ---------------------------------------------- |
| Product                   | TorqPro AI                                     |
| Current Version           | **v3.0.0-alpha.6**                             |
| Release Status            | **Pre-release**                                |
| Current Engineering Focus | Frontend, Documentation & Validation Hardening |
| Full Regression Baseline  | **3212 passed / 0 failed**                     |
| Release Commit            | `8f07383`                                      |

---

# What's New in v3.0.0-alpha.6

## Frontend, Documentation & Validation Hardening

Version `3.0.0-alpha.6` strengthens the TorqPro v3.0 foundation through frontend integration improvements, engineering documentation alignment, version consistency, and expanded regression validation.

The release preserves the deterministic engineering authority and AI safety boundaries established during the previous v3.0 alpha releases.

### Highlights

* Improved frontend integration and user-facing behaviour
* Updated engineering formula specifications
* Updated Rule Engine documentation
* Product backlog aligned with the current v3.0 development state
* Strengthened centralized version handling
* Improved Torque Study UI messaging
* Improved Fastener Assembly Intelligence validation
* Expanded internationalization (`i18n`) validation
* Expanded regression coverage
* Preserved AI Gateway safety boundaries
* Preserved deterministic engineering authority

---

# AI Gateway API

| Endpoint                       | Purpose                       | Access             |
| ------------------------------ | ----------------------------- | ------------------ |
| `POST /api/ai/query`           | AI-assisted engineering query | Authenticated user |
| `GET /api/ai/providers`        | Registered provider discovery | Authenticated user |
| `GET /api/ai/audit`            | Persistent AI audit records   | Admin only         |
| `GET /api/ai/audit/{audit_id}` | Individual AI audit record    | Admin only         |

---

# Security & Privacy

The AI Gateway follows a privacy-preserving audit model.

* Raw prompts are not persisted.
* Raw responses are not persisted.
* Prompt and response traceability uses SHA-256 hashes.
* API keys, tokens, secrets, and credentials are not stored in the audit trail.
* Internal reasoning and chain-of-thought are not exposed or persisted.
* Provider failures use safe error categories rather than raw exception messages.
* Audit access is restricted to authorized administrators.
* AI functionality operates within controlled engineering boundaries.

---

# Engineering Safety Principles

TorqPro AI follows strict engineering safety principles.

* Deterministic calculations remain authoritative.
* AI recommendations cannot override calculation results.
* Unsupported evidence cannot become validated engineering output.
* Retrieval is restricted to approved engineering sources.
* Fail-closed behaviour is enabled by default.
* AI provider abstraction does not change the engineering authority boundary.
* Traceability must be maintained across AI-assisted workflows.
* Engineering validation remains independent from generative AI output.

---

# Architectural Principles

## Numerical Calculations

The following values are never generated authoritatively by AI:

* Torque
* Clamp load
* Preload
* Friction coefficient
* Yield strength calculations
* Joint calculations
* Safety-critical engineering results

These values remain the responsibility of the deterministic engineering engine.

AI may assist with explanation, retrieval, interpretation, and engineering workflow support, but it cannot replace the deterministic calculation layer.

---

## AI Provider Abstraction

TorqPro AI provides an abstraction layer based on `AIModelClient`.

The architecture supports deterministic/offline operation and provider discovery while keeping the AI Gateway independent from individual external AI services.

This allows external AI providers to be integrated later without changing the engineering authority boundary.

Real external OpenAI, Claude, and Ollama integrations remain deferred from the current alpha release.

---

# Retrieval Rules

Only controlled engineering evidence may be used by the AI retrieval layer.

The following content cannot be treated as authoritative evidence:

* Deprecated content
* Rejected content
* Unverified content
* Unsupported sources
* Uncontrolled engineering data

Validated and approved engineering knowledge remains the authoritative source.

---

# Architecture

```text
User / Frontend
       │
       ▼
HTTP Gateway
       │
       ▼
AI Gateway
       │
       ├──────────────► Audit / Traceability
       │
       ▼
Retrieval & Grounding Layer
       │
       ▼
Engineering Domain
       │
       ▼
Rule / Validation Layer
       │
       ▼
Deterministic Calculation Engine
```

The deterministic calculation engine remains authoritative.

AI functionality is additive and cannot replace validated engineering calculations.

---

# Validation — v3.0.0-alpha.6

| Validation Item                           | Result          |
| ----------------------------------------- | --------------- |
| Full pytest suite                         | **3212 passed** |
| Failed tests                              | **0**           |
| `git diff --check`                        | Passed          |
| Version validation                        | Passed          |
| Frontend validation                       | Passed          |
| i18n validation                           | Passed          |
| Engineering regression validation         | Passed          |
| Fastener Assembly Intelligence validation | Passed          |
| Torque Study UI validation                | Passed          |

---

# Release Information

| Item           | Value                  |
| -------------- | ---------------------- |
| Version        | `3.0.0-alpha.6`        |
| Tag            | `v3.0.0-alpha.6`       |
| Release Commit | `8f07383`              |
| Status         | Pre-release            |
| Test Baseline  | 3212 passed / 0 failed |

---

# Release Assets

```text
TorqPro-v3.0.0-alpha.6.bundle
TorqPro-v3.0.0-alpha.6.patch
```

The release artifacts provide a reproducible backup and patch representation of the Alpha.6 release.

---

# Development Status

| Phase               | Description                                             | Status      |
| ------------------- | ------------------------------------------------------- | ----------- |
| Phase 3.0.0-alpha.1 | AI Architecture Foundation                              | ✅ Completed |
| Phase 3.0.0-alpha.2 | Retrieval & Grounding                                   | ✅ Completed |
| Phase 3.0.0-alpha.3 | Safety, Validation & Explainability                     | ✅ Completed |
| Phase 3.0.0-alpha.4 | HTTP Gateway Exposure                                   | ✅ Completed |
| Phase 3.0.0-alpha.5 | Persistent Audit, Explainability & Provider Abstraction | ✅ Completed |
| Phase 3.0.0-alpha.6 | Frontend, Documentation & Validation Hardening          | ✅ Completed |
| Phase 3.0.0-beta.1  | Torque Recommendation Engine                            | ▶️ Next     |
| Phase 3.0.0-beta.2  | Engineering Reasoning Engine                            | Planned     |
| Phase 3.0.0-rc.1    | Performance, Security & Documentation                   | Planned     |
| Phase 3.0.0         | Stable Release                                          | Planned     |

---

# Version History

## v3.0 — AI Transformation

| Version            | Description                                             |
| ------------------ | ------------------------------------------------------- |
| **v3.0.0-alpha.6** | Frontend, Documentation & Validation Hardening          |
| **v3.0.0-alpha.5** | Persistent Audit, Explainability & Provider Abstraction |
| **v3.0.0-alpha.4** | HTTP Gateway Exposure                                   |
| **v3.0.0-alpha.3** | Safety, Validation & Explainability                     |
| **v3.0.0-alpha.2** | Retrieval & Grounding                                   |
| **v3.0.0-alpha.1** | AI Architecture Foundation                              |

---

## v2.9 — Question Bank Evolution

| Version     | Description                              |
| ----------- | ---------------------------------------- |
| **v2.9.13** | Question Bank Import / Export Hardening  |
| **v2.9.12** | Question Bank Statistics Trend & History |
| **v2.9.11** | Question Bank Statistics Dashboard       |
| **v2.9.10** | Question Bank Statistics API             |
| **v2.9.9**  | Question Bank Import / Export            |
| **v2.9.8**  | Question Bank Bulk Lifecycle Operations  |
| **v2.9.7**  | Question Bank Administration UI          |
| **v2.9.6**  | Question Creation & Lifecycle API        |
| **v2.9.5**  | Question Tagging & Search                |
| **v2.9.4**  | Question Lifecycle Management            |
| **v2.9.3**  | Question Bank Release Documentation      |
| **v2.9.2**  | Question Update & Editing                |
| **v2.9.1**  | Question Retrieval API                   |
| **v2.9.0**  | Question Bank Foundation                 |

---

## v2.8 — Engineering Intelligence & Quality

| Version     | Description                           |
| ----------- | ------------------------------------- |
| **v2.8.15** | README / Version Alignment            |
| **v2.8.14** | Joint Revision Visibility             |
| **v2.8.10** | Quality Harness & Validation          |
| **v2.8.6**  | Fastener Assembly Intelligence        |
| **v2.8.1**  | Engineering Library Audit & Expansion |

---

## v2.7 — Reporting

| Version  | Description               |
| -------- | ------------------------- |
| **v2.7** | Engineering Report Engine |

---

## v2.6 — Friction Engineering

| Version  | Description                      |
| -------- | -------------------------------- |
| **v2.6** | Friction Condition & Lubrication |

---

# Major Evolution

```text
v2.6
Friction Condition & Lubrication
        │
        ▼
v2.7
Engineering Report Engine
        │
        ▼
v2.8.x
Engineering Library
Fastener Assembly Intelligence
Quality & Joint Revision Visibility
        │
        ▼
v2.9.x
Question Bank
Lifecycle
Search
Import / Export
Statistics
Trend Analysis
        │
        ▼
v3.0.0-alpha.1
AI Architecture Foundation
        │
        ▼
v3.0.0-alpha.2
Retrieval & Grounding
        │
        ▼
v3.0.0-alpha.3
Safety & Explainability
        │
        ▼
v3.0.0-alpha.4
HTTP Gateway
        │
        ▼
v3.0.0-alpha.5
Persistent Audit
Provider Abstraction
        │
        ▼
v3.0.0-alpha.6
Frontend
Documentation
Validation Hardening
        │
        ▼
v3.0.0-beta.1
Torque Recommendation Engine
```

---

# Roadmap

## Current Release

```text
v3.0.0-alpha.6
```

Status:

```text
COMPLETED
```

---

## Next Phase

### v3.0.0-beta.1 — Torque Recommendation Engine

The next major development phase will introduce the controlled Torque Recommendation Engine.

The objective is to provide engineering-assisted torque recommendations while preserving:

* deterministic calculation authority
* engineering validation
* traceability
* evidence grounding
* safety boundaries
* explainability
* auditability

AI-generated recommendations must remain subordinate to validated engineering calculations and controlled engineering rules.

---

## Planned Phases

### v3.0.0-beta.1

**Torque Recommendation Engine**

Focus:

* controlled torque recommendation
* deterministic calculation integration
* engineering evidence
* confidence and validation boundaries
* traceable recommendations

### v3.0.0-beta.2

**Engineering Reasoning Engine**

Focus:

* engineering reasoning workflows
* structured evidence synthesis
* multi-source engineering retrieval
* explainable engineering assistance
* controlled decision support

### v3.0.0-rc.1

**Performance, Security & Documentation**

Focus:

* performance hardening
* security validation
* production readiness
* architecture review
* documentation completion
* deployment validation

### v3.0.0

**Stable Release**

Focus:

* production-ready AI-assisted engineering platform
* stable engineering APIs
* validated deterministic calculation boundary
* complete traceability
* enterprise deployment readiness

---

# Long-Term Objectives

TorqPro AI is being developed toward a broader engineering intelligence platform.

Long-term objectives include:

* Advanced engineering reasoning
* Advanced engineering retrieval
* Controlled AI recommendations
* Production hardening
* Enterprise deployment
* External AI provider integrations
* Extended engineering knowledge libraries
* Advanced fastener engineering analytics
* Engineering decision support
* Full lifecycle traceability

---

# Engineering Philosophy

TorqPro AI is designed around the principle that artificial intelligence should **support engineering — not replace engineering authority**.

```text
Engineering Standards
        +
Validated Knowledge
        +
Deterministic Calculations
        +
Engineering Rules
        +
Traceability
        +
Controlled AI Assistance
        =
TorqPro AI
```

---

# License

See the `LICENSE` file for details.
