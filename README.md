# TorqPro AI

> AI-powered fastener engineering, deterministic torque recommendation, validation, traceability, and knowledge platform.

---

## Overview

TorqPro AI is a professional engineering platform for the design, analysis, validation, optimization, and governance of threaded joints and tightening processes.

The platform combines deterministic engineering calculations, validated engineering knowledge, lifecycle management, traceability, and controlled AI-assisted engineering workflows.

The core engineering philosophy is simple:

> **Deterministic engineering calculations remain authoritative. AI is additive, explainable, traceable, and cannot override validated engineering results.**

---

# Key Features

## Fastener Engineering

- VDI 2230-based threaded joint engineering
- Torque and preload calculations
- **Deterministic Torque Recommendation Engine**
- Torque-window evaluation
- Friction condition and lubrication modelling
- Thread geometry and fastener calculations
- Bolt, nut and washer engineering libraries
- Joint definition and revision management
- Engineering formula validation
- Fastener Assembly Intelligence
- Torque Study workflows
- Production validation
- Fail-closed engineering recommendation logic

## Engineering Knowledge

- Engineering Library
- Question Bank infrastructure
- Question retrieval
- Question creation and editing
- Lifecycle management
- Tagging and search
- Bulk lifecycle operations
- Import / export
- Statistics and dashboards
- Trend and history analysis
- Controlled engineering knowledge

## Quality & Governance

- Validation workflows
- Governance workflows
- Engineering traceability
- Auditability
- Version centralization
- Regression validation
- Multilingual UI validation
- Controlled engineering evidence
- Project ownership authorization controls
- Recommendation audit traceability
- Request correlation with `X-Request-ID`

## AI Architecture

- AI retrieval and grounding
- Explainability framework
- AI HTTP Gateway
- Persistent AI audit trail
- AI provider abstraction
- Deterministic / offline provider support
- Provider discovery
- Secure prompt / response hash traceability
- Fail-closed safety behaviour
- Controlled AI-to-engineering boundary
- **Torque Recommendation Engine — deterministic-first, explainable and auditable**
- AI/provider-independent numeric recommendation

---

# Current Version

| Item | Value |
|---|---|
| Product | **TorqPro AI** |
| Current Version | **v3.0.0-beta.1** |
| Release Stage | **Beta** |
| Release Status | **Pre-release** |
| Main Capability | **Deterministic Torque Recommendation Engine** |
| Final Commit | `89f8f5135629d0812a7aa3936e0057ab5a88a2b9` |
| Beta.1 Tests | **37 passed** |
| Full Test Suite | **3243 passed** |
| Next Phase | **v3.0.0-beta.2 — Engineering Reasoning Engine** |

---

# What's New in v3.0.0-beta.1

## Deterministic Torque Recommendation Engine

TorqPro v3.0.0-beta.1 introduces the first production-oriented **Torque Recommendation Engine**.

The recommendation workflow is:

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

Engineering Source of Truth

The Torque Recommendation Engine is built on:

backend/calculation_engine/joint_analysis.py::analyze_joint()

Existing deterministic engineering outputs are reused, including:

recommended torque calculation
torque window
preload-related engineering results
safety status
readiness
engineering coverage
warnings
critical findings
formula traceability

No parallel AI-generated torque calculation path has been introduced.

Fail-Closed Recommendation Behaviour

Beta.1 introduces explicit fail-closed recommendation behaviour.

If critical engineering findings are present:

the underlying calculated result may remain visible for traceability;
recommended_torque is withheld;
applicability indicates that a usable recommendation cannot be issued;
warnings and explanations identify the reason.

A calculated value therefore cannot automatically become an engineering recommendation when validation conditions are not satisfied.

Deterministic Confidence Classification

Recommendation confidence is determined using engineering conditions rather than AI-generated probability scores.

Supported classifications:

Classification	Purpose
HIGH	Strong engineering completeness and validation
MEDIUM	Valid recommendation with relevant assumptions or limitations
LOW	Significant limitations or incomplete engineering support
NOT_APPLICABLE	No usable engineering recommendation can be issued

The classification is derived from deterministic factors such as readiness, coverage, warnings, assumptions and critical findings.

AI Safety Boundary

The numerical recommendation is independent of the AI provider layer.

AI providers cannot:

independently calculate torque;
modify deterministic torque results;
override engineering validation;
convert an invalid result into an approved recommendation.

The Torque Recommendation Engine remains operational even when an AI provider is:

enabled;
unavailable;
failing;
or not configured.

Regression tests verify that identical engineering inputs produce identical numeric recommendation results across these provider states.

Engineering Explainability

Each recommendation can provide structured engineering context including:

calculated engineering result
recommended torque
applicable torque range
validation status
confidence
assumptions
warnings
limitations
calculation references
traceability information

Explainability therefore remains available without requiring an external LLM.

Audit & Traceability

Torque recommendation events reuse TorqPro's existing audit infrastructure.

Traceability can include:

normalized request inputs
deterministic calculation outcome
recommendation status
confidence classification
warnings
critical findings
recommended or withheld state
authenticated user context
request correlation information

No separate torque-recommendation audit database is required.

Torque Recommendation API

Beta.1 introduces the authenticated endpoint:

POST /api/ai/torque-recommendation

The endpoint provides structured access to the deterministic recommendation workflow.

Request correlation is supported through:

X-Request-ID

The API preserves TorqPro's engineering validation boundary and does not expose proprietary engineering-rule sources.

Validation

TorqPro v3.0.0-beta.1 passed the following validation:

Validation	Result
Beta.1 targeted tests	37 passed
Full test suite	3243 passed
git diff --check	Clean
Bundle clone verification	Passed
Patch replay verification	Passed
Tree hash comparison	Exact match
AI/provider independence	Passed
Fail-closed recommendation	Passed
Development Roadmap
Version	Scope	Status
v3.0.0-alpha.1	AI Architecture Foundation	✅ Completed
v3.0.0-alpha.2	Retrieval & Grounding	✅ Completed
v3.0.0-alpha.3	Safety & Explainability	✅ Completed
v3.0.0-alpha.4	AI HTTP Exposure	✅ Completed
v3.0.0-alpha.5	Persistent Audit & Provider Abstraction	✅ Completed
v3.0.0-alpha.6	Frontend AI Integration	✅ Completed
v3.0.0-beta.1	Torque Recommendation Engine	✅ Completed
v3.0.0-beta.2	Engineering Reasoning Engine	⏭️ Next
v3.0.0-rc.1	Performance, Security & Documentation	Planned
v3.0.0	Stable Release	Planned
Next Phase
v3.0.0-beta.2 — Engineering Reasoning Engine

The next phase will extend TorqPro with controlled engineering reasoning around validated engineering results.

Beta.2 will build on:

deterministic engineering calculations
grounded engineering evidence
structured assumptions
warnings and limitations
engineering traceability
controlled AI explanation and reasoning

The deterministic engineering calculation layer will continue to remain the source of truth.

Release

Current Release: v3.0.0-beta.1

Release Commit:

89f8f5135629d0812a7aa3936e0057ab5a88a2b9

Status: Beta / Pre-release

Next Milestone: v3.0.0-beta.2 — Engineering Reasoning Engine
