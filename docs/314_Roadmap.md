# Roadmap
Future expansion.

## Faz 2.8.11 — Engineering Governance Architecture and Decision Workflow Standardization

**Complete (Stages 1–5)**, delivered 2026-07-30 — see
`docs/adr/ADR-0014-engineering-governance-architecture.md`,
`docs/11_PRODUCT_BACKLOG.md` §12D, and
`docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md` for full detail.
Defined and implemented a canonical governance vocabulary (review /
publication / resolution lifecycles) as a standalone, additive
`backend/governance/` package with typed contracts (Stage 2), an
append-only event store and idempotency-first service layer
(Stage 3), a bilingual API and workspace (Stage 4), and one read-only
compatibility adapter for washer resolution (Stage 5) — without
modifying any of the four existing, independently-evolved mechanisms
(Production Validation, legacy calculation revisions, joint revision
lifecycle, Faz 2.8.9 washer resolution decisions).

Deferred to a future, separately-scoped phase: Production Validation,
legacy calculation-revision, and joint-revision compatibility
adapters (all three require a live database connection to read,
which this phase's first, narrowly-scoped adapter deliberately did
not take on), and any write-path integration connecting the
canonical governance workflow to a real TorqPro record type.
