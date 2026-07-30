# Roadmap
Future expansion.

## Faz 2.8.11 — Engineering Governance Architecture and Decision Workflow Standardization

**Stage 1 (Architecture & Documentation)** delivered 2026-07-30 — see
`docs/adr/ADR-0014-engineering-governance-architecture.md` and
`docs/11_PRODUCT_BACKLOG.md` §12D. Defined a canonical governance
vocabulary (review / publication / resolution lifecycles) unifying
the four existing, independently-evolved mechanisms (Production
Validation, legacy calculation revisions, joint revision lifecycle,
Faz 2.8.9 washer resolution decisions) without changing any of them.

Remaining stages, each requiring its own scoping approval before
work begins:

- **Stage 2 — Shared governance contracts and typed domain models.**
  Additive Pydantic models for the three canonical lifecycle groups;
  no existing mechanism depends on them yet.
- **Stage 3 — Append-only governance event store and service layer.**
  Generalizes the Faz 2.8.9 append-only decision-ledger pattern into
  a reusable service with the closed transition tables, idempotency,
  and actor/timestamp rules ADR-0014 defines.
- **Stage 4 — Additive API and TR/EN governance workspace.** New
  read/write governance endpoints and a frontend workspace, built
  additively with full TR/EN parity from the start.
- **Stage 5 — Compatibility adapters, tests and completion report.**
  Optional, explicitly-authorized read-through adapters for
  mechanisms 1–4, full test coverage, and a standard delivery-
  protocol completion report (branch → full suite pass → patch +
  bundle + SHA256SUMS verified on an independent clean clone).
