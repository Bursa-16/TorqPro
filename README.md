# TorqPro AI

> AI-powered fastener engineering, validation, traceability, and knowledge platform.

---

## Overview

TorqPro AI is a professional engineering platform for the design, analysis, validation, optimization, and governance of threaded joints and tightening processes.

The platform combines deterministic engineering calculations, validated engineering knowledge, lifecycle management, traceability, and AI-assisted engineering workflows.

---

## Key Features

- VDI 2230 implementation
- Torque and preload calculations
- Friction and lubrication modelling
- Threaded joint engineering
- Bolt, nut and washer libraries
- Question Bank infrastructure
- Validation workflows
- Governance workflows
- Production validation
- Engineering traceability
- AI retrieval and grounding
- Explainability and traceability framework
- AI HTTP gateway
- Persistent AI audit trail
- AI provider abstraction
- Deterministic/offline provider support
- Provider discovery
- Secure prompt/response hash traceability

---

# Current Version

| Item | Value |
| --- | --- |
| Product | TorqPro AI |
| Current Version | v3.0.0-alpha.5 |
| Release Status | Pre-release |
| Current Engineering Focus | Persistent Audit, Explainability & Provider Abstraction |

---

# What's New in v3.0.0-alpha.5

## Persistent Audit, Explainability & Provider Abstraction

Version 3.0.0-alpha.5 extends the TorqPro AI Gateway with persistent auditability, provider abstraction, and enhanced safe explainability while preserving the deterministic engineering boundary.

### Highlights

- Persistent AI audit trail
- Provider abstraction based on `AIModelClient`
- Deterministic/offline provider support
- Safe explainability and traceability metadata
- Success and failure audit records
- SHA-256 based prompt/response traceability
- Admin-only audit endpoints
- Provider discovery endpoint
- Cross-platform dependency guard validation
- Existing alpha.4 HTTP behaviour preserved

---

## AI Gateway API

| Endpoint | Purpose | Access |
| --- | --- | --- |
| `POST /api/ai/query` | AI-assisted engineering query | Authenticated user |
| `GET /api/ai/providers` | Registered provider discovery | Authenticated user |
| `GET /api/ai/audit` | Persistent AI audit records | Admin only |
| `GET /api/ai/audit/{audit_id}` | Individual AI audit record | Admin only |

---

## Security & Privacy

The AI Gateway follows a privacy-preserving audit model:

- Raw prompts are not persisted.
- Raw responses are not persisted.
- Prompt and response traceability uses SHA-256 hashes.
- API keys, tokens, secrets, and credentials are not stored in the audit trail.
- Internal reasoning and chain-of-thought are not exposed or persisted.
- Provider failures are recorded using safe error categories rather than raw exception messages.
- Audit access is restricted to authorized administrators.

---

## Engineering Safety Principles

The following principles are strictly enforced:

- Deterministic calculations remain authoritative.
- AI recommendations cannot override calculation results.
- Unsupported evidence cannot become validated output.
- Retrieval is restricted to approved engineering sources.
- Fail-closed behaviour is enabled by default.
- AI provider abstraction does not change the deterministic engineering authority boundary.

---

## Architectural Principles

### Numerical Calculations

The following values are never generated authoritatively by AI:

- Torque
- Clamp load
- Preload
- Friction coefficient
- Yield strength calculations
- Joint calculations

These values remain the responsibility of the deterministic engineering engine.

### AI Provider Abstraction

TorqPro AI now provides an abstraction layer based on `AIModelClient`.

The current architecture supports deterministic/offline operation and provider discovery while keeping the AI Gateway independent from individual external AI services.

Real external OpenAI, Claude, and Ollama integrations are not part of v3.0.0-alpha.5 and remain deferred.

---

## Retrieval Rules

The following content cannot be used as authoritative evidence:

- Deprecated content
- Rejected content
- Unverified content
- Unsupported sources

---

## Dependency Direction

```text
HTTP Gateway
        │
        ▼
AI Gateway
        │
        ▼
Retrieval Layer
        │
        ▼
Engineering Domain
        │
        ▼
Calculation Engine
```

The deterministic calculation engine remains authoritative. AI functionality is additive and cannot replace validated engineering calculations.

---

## Validation

| Item | Result |
| --- | --- |
| tests/ai | 149 passed |
| Full pytest suite | 3206 passed |
| New alpha.5 tests | 48 |
| Failed tests | 0 |
| Safety / dependency guards | Passed |
| Windows / Linux guard compatibility | Passed |
| flake8 | Passed |
| git diff --check | Passed |

---

## Release Information

| Item | Value |
| --- | --- |
| Feature Commit | `36fafba` |
| Final Release Commit | `d338d86` |
| Version | `3.0.0-alpha.5` |
| Status | Pre-release |

---

## Release Assets

```text
TorqPro-v3.0.0-alpha.5_1.bundle
TorqPro-v3.0.0-alpha.5_1.patch
SHA256SUMS_17.txt
```

---

# Development Status

| Phase | Description | Status |
| --- | --- | --- |
| Phase 3.0.0-alpha.1 | AI Architecture Foundation | Completed |
| Phase 3.0.0-alpha.2 | Retrieval and Grounding | Completed |
| Phase 3.0.0-alpha.3 | Safety, Validation and Explainability | Completed |
| Phase 3.0.0-alpha.4 | HTTP Gateway Exposure | Completed |
| Phase 3.0.0-alpha.5 | Persistent Audit, Explainability & Provider Abstraction | Completed |
| Phase 3.0.0-beta.1 | Torque Recommendation Engine | Next |
| Phase 3.0.0-beta.2 | Engineering Reasoning Engine | Planned |
| Phase 3.0.0-rc.1 | Performance, Security & Documentation | Planned |
| Phase 3.0.0 | Stable Release | Planned |

---

# Version History

| Version | Description |
| --- | --- |
| v3.0.0-alpha.5 | Persistent Audit, Explainability & Provider Abstraction |
| v3.0.0-alpha.4 | HTTP Gateway Exposure |
| v3.0.0-alpha.3 | Safety, Validation and Explainability |
| v3.0.0-alpha.2 | Retrieval and Grounding |
| v3.0.0-alpha.1 | AI Architecture Foundation |
| v2.9.13 | Question Bank Import/Export Hardening |
| v2.9.12 | Question Bank Statistics Trend History |
| v2.9.11 | Question Bank Statistics Dashboard |
| v2.9.10 | Question Bank Statistics API |

---

# Roadmap

## Current Version

```text
v3.0.0-alpha.5
```

## Next Phase

### v3.0.0-beta.1 — Torque Recommendation Engine

The next phase will introduce the controlled torque recommendation layer while preserving deterministic engineering authority, validation, traceability, and safety boundaries.

## Planned Phases

- v3.0.0-beta.1 — Torque Recommendation Engine
- v3.0.0-beta.2 — Engineering Reasoning Engine
- v3.0.0-rc.1 — Performance, Security & Documentation
- v3.0.0 — Stable Release

---

## Long-term Objectives

- Engineering reasoning
- Advanced retrieval
- Production hardening
- Enterprise deployment
- External AI provider integrations

---

## License

See the LICENSE file for details.
