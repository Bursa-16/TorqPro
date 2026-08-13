# TorqPro AI

> **AI-powered fastener engineering, deterministic torque recommendation, validation, traceability, and knowledge platform.**

---

## Overview

TorqPro AI is a professional engineering platform for the design, analysis, validation, optimization, and governance of threaded joints and tightening processes.

The platform combines deterministic engineering calculations, validated engineering knowledge, lifecycle management, traceability, and controlled AI-assisted engineering workflows.

The core engineering philosophy is simple:

> **Deterministic engineering calculations remain authoritative. AI is additive, explainable, traceable, and cannot override validated engineering results.**

TorqPro AI is designed to support engineering decision-making without replacing validated engineering logic.

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

---

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
* Controlled engineering knowledge management

---

## AI-Assisted Engineering

TorqPro AI provides a controlled AI assistance layer built around deterministic engineering authority.

Capabilities include:

* Engineering reasoning support
* Grounded engineering responses
* Evidence-aware answer composition
* Explainability
* Correlation and request traceability
* Persistent AI audit records
* Provider abstraction
* Provider discovery
* External AI provider integration
* Fail-closed AI behavior
* Advisory AI output separated from authoritative calculations

AI-generated text does not replace or modify validated deterministic engineering results.

---

# Engineering Architecture

TorqPro AI separates engineering authority from AI-assisted reasoning.

The architecture is designed around the following principle:

```text
Engineering Input
      │
      ▼
Deterministic Engineering Engine
      │
      ├── Authoritative calculations
      ├── Engineering limits
      ├── Validation rules
      └── Traceable results
      │
      ▼
AI Context / Grounding Layer
      │
      ├── Engineering evidence
      ├── Calculation context
      ├── Approved knowledge
      └── Traceability context
      │
      ▼
AI Provider
      │
      ▼
Evidence / Safety / Explainability
      │
      ▼
Advisory Engineering Explanation
```

The AI layer cannot replace deterministic numeric output.

---

# AI Engineering Principles

TorqPro AI follows several core engineering rules.

### Deterministic Authority

Validated engineering calculations remain the authoritative source for engineering results.

### AI Is Advisory

AI may explain, contextualize, summarize, or reason from validated engineering information.

It cannot override an authoritative calculation.

### Grounding

AI responses are designed to use controlled engineering context and approved evidence.

### Explainability

Engineering reasoning must remain understandable and traceable.

### Auditability

AI operations are designed to support correlation IDs, audit records, provider metadata, result hashes, and safe error categorization.

### Fail-Closed Behavior

When required engineering evidence or provider capability is unavailable, TorqPro does not fabricate an authoritative result.

---

# Production AI Provider Architecture

Starting with `v3.1.0-alpha.1`, TorqPro includes its first production-oriented external AI provider integration.

The provider layer remains separated from deterministic engineering logic.

## Provider Abstraction

External AI providers implement the TorqPro `AIModelClient` abstraction.

This enables providers to be integrated without introducing provider-specific logic into the engineering calculation layer.

The architecture supports:

* provider registration
* provider discovery
* provider availability checks
* explicit provider selection where supported
* provider-independent orchestration
* controlled future provider expansion

Automatic provider fallback is not enabled in `v3.1.0-alpha.1`.

---

# OpenAI Provider

`v3.1.0-alpha.1` introduces the first external AI provider implementation.

## Integration

* `OpenAIModelClient`
* OpenAI Responses API
* direct `httpx` transport
* non-streaming request model
* environment-based provider configuration
* bounded timeout behavior
* bounded retry handling
* strict response validation
* malformed-response fail-safe behavior

The implementation does not introduce OpenAI-specific logic into deterministic engineering calculations.

---

## OpenAI Configuration

The provider is configured through environment variables:

```text
TORQPRO_OPENAI_API_KEY
TORQPRO_OPENAI_MODEL
TORQPRO_OPENAI_TIMEOUT_S
TORQPRO_OPENAI_MAX_RETRIES
```

`TORQPRO_OPENAI_API_KEY` and `TORQPRO_OPENAI_MODEL` are required for the OpenAI provider to be considered available.

No OpenAI model is hardcoded as the TorqPro product default.

Timeout and retry settings use bounded behavior.

---

# Provider Transport Layer

External AI network communication is isolated through a provider-agnostic transport layer.

The transport layer is responsible for:

* HTTP requests
* timeout enforcement
* bounded retry behavior
* transient-error handling
* safe transport exceptions

It contains no TorqPro engineering calculation logic.

Retry behavior is restricted to transient failures such as:

* connection errors
* timeout errors
* HTTP `429`
* selected HTTP `5xx` responses

Normal non-429 `4xx` responses are not automatically retried.

---

# Privacy and Provider Safety

The external provider integration is designed to avoid accidental exposure of sensitive runtime information.

The provider/transport layer does not intentionally log or persist:

* API keys
* Authorization headers
* raw provider error bodies
* raw prompts through the transport layer
* raw provider responses through the transport layer

Existing TorqPro audit mechanisms retain only safe metadata according to the platform's audit architecture.

---

# Torque Recommendation Engine

The deterministic Torque Recommendation Engine evaluates engineering inputs and produces controlled torque recommendations.

The engine is designed around:

* deterministic calculations
* explicit engineering limits
* traceable recommendation logic
* controlled validation
* fail-closed behavior
* audit support

AI cannot replace the deterministic recommendation.

AI may be used later to explain an already validated recommendation.

---

# Engineering Reasoning Engine

The Engineering Reasoning Engine builds explainable reasoning around deterministic engineering results.

Its purpose is to answer:

* What was calculated?
* Why was this recommendation produced?
* Which engineering evidence supports it?
* What requires engineering validation?
* What assumptions or constraints are relevant?

The reasoning layer does not become the source of authoritative numeric engineering output.

---

# Grounding and Evidence

TorqPro's AI architecture includes controlled grounding and evidence checking.

The pipeline is designed around:

```text
Permission
   ↓
Context Builder
   ↓
Retrieval
   ↓
Optional Engineering Tools
   ↓
AI Provider
   ↓
Evidence Checker
   ↓
Composer
   ↓
Audit
```

Grounding and evidence validation remain provider-independent.

---

# Audit and Traceability

TorqPro AI includes persistent audit infrastructure for AI-assisted workflows.

Audit capabilities include controlled metadata such as:

* correlation ID
* provider identity
* model identifier
* success/failure state
* latency
* safe error category
* response hash where applicable

Raw secrets are not part of the audit contract.

---

# Current Version

| Item                      | Value                                                                           |
| ------------------------- | ------------------------------------------------------------------------------- |
| Product                   | **TorqPro AI**                                                                  |
| Current Version           | **v3.1.0-alpha.1**                                                              |
| Release Stage             | **Alpha / Pre-release**                                                         |
| Release Status            | **Production AI Provider Integration**                                          |
| Current Engineering Focus | **External AI Provider Integration + Deterministic Engineering + AI Reasoning** |
| Stable Baseline           | `v3.0.0`                                                                        |
| Release Commit            | `b0332e2e0054d8d3775732e49592d49746173907`                                      |
| Full Test Suite           | **3395 passed, 13 skipped**                                                     |
| New Tests                 | **24**                                                                          |
| Existing-Test Regressions | **0**                                                                           |
| Next Phase                | **Provider wiring / AI workflow expansion — scope TBD**                         |

---

# Development Roadmap

| Version            | Scope                                   | Status          |
| ------------------ | --------------------------------------- | --------------- |
| v3.0.0-alpha.1     | AI Architecture Foundation              | ✅ Completed     |
| v3.0.0-alpha.2     | Retrieval & Grounding                   | ✅ Completed     |
| v3.0.0-alpha.3     | Safety & Explainability                 | ✅ Completed     |
| v3.0.0-alpha.4     | AI HTTP Exposure                        | ✅ Completed     |
| v3.0.0-alpha.5     | Persistent Audit & Provider Abstraction | ✅ Completed     |
| v3.0.0-alpha.6     | Frontend AI Integration                 | ✅ Completed     |
| v3.0.0-beta.1      | Torque Recommendation Engine            | ✅ Completed     |
| v3.0.0-beta.2      | Engineering Reasoning Engine            | ✅ Completed     |
| v3.0.0-rc.1        | Performance, Security & Documentation   | ✅ Completed     |
| v3.0.0             | Stable Release                          | ✅ Completed     |
| **v3.1.0-alpha.1** | **Production AI Provider Integration**  | **✅ Completed** |

---

# Release

**Current Release:** `v3.1.0-alpha.1`

**Status:** Alpha / Pre-release

**Stable Baseline:** `v3.0.0`

**Main Capability:** Production-oriented external AI provider integration while preserving deterministic engineering calculations as authoritative.

---

## v3.1.0-alpha.1 Highlights

* Added `OpenAIModelClient`
* Added OpenAI Responses API integration
* Added provider-agnostic HTTP transport using `httpx`
* Added environment-based API key and model configuration
* Added bounded timeout and retry handling
* Added safe handling of malformed and empty AI responses
* Integrated OpenAI with the existing provider registry
* Added provider discovery support
* Preserved grounding and evidence-checking architecture
* Preserved explainability
* Preserved persistent audit and traceability
* Preserved fail-closed behavior
* Deterministic engineering calculations remain authoritative
* AI output remains advisory
* AI cannot override validated deterministic engineering results
* No automatic provider fallback introduced
* No hardcoded OpenAI product-default model introduced

---

# Deferred

The following items are intentionally outside the scope of `v3.1.0-alpha.1`:

* Additional external AI providers
* Automatic provider fallback
* Default OpenAI wiring for `POST /api/ai/query`
* Broader AI workflow expansion
* Joint Analysis AI expansion
* Friction / lubrication AI reasoning
* Material intelligence AI integration
* New AI-specific RBAC roles
* AI write or approval actions

The scope of the next development phase will be defined separately before implementation.

---

# Validation

`v3.1.0-alpha.1` completed the full validation process.

| Validation Item              | Result                      |
| ---------------------------- | --------------------------- |
| Full Test Suite              | **3395 passed, 13 skipped** |
| AI Test Suite                | **229 passed**              |
| New Tests                    | **24**                      |
| Existing-Test Regressions    | **0**                       |
| Dependency-Direction Tests   | **Passed**                  |
| Safety / Static Guards       | **Passed**                  |
| Numeric-Literal Safety Guard | **Passed**                  |
| Flake8                       | **Clean**                   |
| `git diff --check`           | **Clean**                   |
| Bundle Clone Validation      | **Passed**                  |
| Patch Application Validation | **Passed**                  |
| Release Tree Equivalence     | **Confirmed**               |
| Working Tree                 | **Clean**                   |
| VERSION                      | **3.1.0-alpha.1**           |

---

# Known Limitation

No live OpenAI API request was executed during sandbox validation.

The external provider integration was validated using mocked HTTP transport with zero live external network calls.

Live provider validation requires:

* valid OpenAI credentials
* configured `TORQPRO_OPENAI_MODEL`
* network access to the OpenAI API
* deployment-environment validation

This limitation does not affect the deterministic TorqPro engineering calculation layer.

---

# Release Integrity

The `v3.1.0-alpha.1` release was validated using:

* full repository bundle
* clean bundle-clone verification
* release patch
* independent patch-application verification
* tree-hash equivalence
* SHA256 artifact verification
* full test-suite execution from a clean bundle clone

The validated release tree hash is:

```text
455ff7e05fd02eaafc1a8362161350a57d5c0e9a
```

---

# Product Direction

TorqPro AI is being developed as an engineering decision-support and governance platform for threaded joints and tightening processes.

The product direction combines:

1. **Deterministic Engineering**

   * authoritative calculations
   * validated formulas
   * engineering limits
   * controlled recommendation logic

2. **Engineering Knowledge**

   * structured engineering content
   * lifecycle management
   * controlled retrieval
   * traceability

3. **AI-Assisted Reasoning**

   * grounded explanation
   * engineering-context awareness
   * controlled provider integration
   * explainability
   * auditability

4. **Engineering Governance**

   * validation
   * lifecycle control
   * revision traceability
   * production support

AI capability is developed around the deterministic engineering system rather than replacing it.

---

# Engineering Principle

> **Calculate deterministically. Reason from evidence. Explain transparently. Preserve traceability.**

---

# Release Philosophy

TorqPro development follows a controlled release process:

```text
Scope Discovery
      ↓
Architecture / Risk Review
      ↓
Implementation
      ↓
Targeted Validation
      ↓
Full Regression Validation
      ↓
Release Metadata
      ↓
Commit / Tag
      ↓
Bundle / Patch Verification
      ↓
Release
```

New AI capabilities must preserve deterministic engineering authority and must pass existing engineering safety, dependency-direction, and regression safeguards before release.

---

**TorqPro AI — Engineering first. AI where it adds controlled, explainable value.**
