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
- Explainability framework
- AI HTTP gateway

---

# Current Version

| Item | Value |
|------|------|
| Product | TorqPro AI |
| Current Version | v3.0.0-alpha.4 |
| Release Status | Pre-release |
| Current Engineering Focus | AI HTTP Gateway Exposure |

---

# What's New in v3.0.0-alpha.4

## HTTP Gateway Exposure

Version 3.0.0-alpha.4 introduces the first externally accessible HTTP exposure layer for TorqPro AI.

### Highlights

- AI HTTP gateway exposure
- Dependency injection support
- Retrieval safety preservation
- Explainability preservation
- Fail-closed behaviour
- Dependency-direction enforcement
- Full regression validation

---

## Engineering safety principles

The following principles are strictly enforced:

- Deterministic calculations remain authoritative.
- AI recommendations cannot override calculation results.
- Unsupported evidence cannot become validated output.
- Retrieval is restricted to approved engineering sources.
- Fail-closed behaviour is enabled by default.

---

## Architectural principles

### Numerical calculations

The following values are never generated authoritatively by AI:

- Torque
- Clamp load
- Preload
- Friction coefficient
- Yield strength calculations
- Joint calculations

These values remain the responsibility of the deterministic engineering engine.

---

## Retrieval rules

The following content cannot be used as authoritative evidence:

- Deprecated content
- Rejected content
- Unverified content
- Unsupported sources

---

## Dependency direction

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

---

## Validation

| Item | Result |
|------|------|
| tests/ai | 101 passed |
| Full pytest suite | 3158 passed |
| Failed tests | 0 |
| flake8 | Passed |
| git diff --check | Passed |

---

## Release Information

| Item | Value |
|------|------|
| Feature Commit | f3a9f28 |
| Release Commit | 179c890 |
| Version | 3.0.0-alpha.4 |
| Status | Pre-release |

---

## Release Assets

```text
torqpro-v3.0.0-alpha.4-release.bundle
0001-torqpro-v3.0.0-alpha.4.patch
SHA256SUMS.txt
```

---

# Development Status

| Phase | Description | Status |
|------|------|------|
| Phase 3.0.0-alpha.1 | AI Architecture Foundation | Completed |
| Phase 3.0.0-alpha.2 | Retrieval and Grounding | Completed |
| Phase 3.0.0-alpha.3 | Safety, Validation and Explainability | Completed |
| Phase 3.0.0-alpha.4 | HTTP Gateway Exposure | Current |

---

# Version History

| Version | Description |
|------|------|
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
v3.0.0-alpha.4
```

## Candidate Next Phases

- v3.0.0-alpha.5
- v3.0.0-beta.1
- v3.0.0-beta.2
- v3.0.0-rc.1
- v3.0.0

---

## Long-term objectives

- Persistent audit storage
- Explainability expansion
- Engineering reasoning
- Advanced retrieval
- Production hardening
- Enterprise deployment

---

## License

See the LICENSE file for details.
