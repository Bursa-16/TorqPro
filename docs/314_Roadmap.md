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

## Faz 2.8.12 — Governance Integration & Controlled Adoption

**Stage 2, Stage 3, Stage 4 (assessment), Stage 4.1 (spike), and
Stage 4.2 (joint revision read-only adapter) complete**, delivered
2026-07-30 — see
`docs/adr/ADR-0015-washer-resolution-governance-integration.md`,
`docs/11_PRODUCT_BACKLOG.md` §12E, and
`docs/phases/PHASE_2.8.12_STAGE2_INTEGRATION_CONTRACT.md` for full
detail. Scope corrected during Stage 1 assessment to washer
resolution only — the one existing mechanism with a real decision
workflow the canonical governance model can represent without
inventing new lifecycle states; Production Validation, legacy
calculation revisions, and joint revisions remain assessment-only
(Stage 4, not yet done); Material Intelligence, Fastener Assembly
Intelligence, Recommendation logic, report modules, the Quality
Harness, and future VDI 2230 extensions were explicitly ruled out of
scope (no existing decision workflow to govern).

Stage 2 delivered the washer resolution integration contract: an
"authoritative-write-then-synchronous-best-effort-sync" pattern plus
a mandatory, idempotent reconciliation mechanism
(`backend/governance/adapters/washer_resolution_sync.py`,
`.../washer_resolution_reconciliation.py`,
`tools/run_washer_governance_reconciliation.py`), an HTTP-only
aggregate-ownership guard (`backend/governance/ownership.py`), and no
background worker/scheduler/queue of any kind.

Stage 3 wired that contract into production: the real washer decide
endpoint now triggers synchronous best-effort governance
synchronization immediately after the authoritative washer decision
succeeds, with a verified-unchanged public API contract (same URL,
schema, status codes, error mapping) and safe structured logging.

Stage 4 assessed the three remaining ADR-0014 mechanisms: Production
Validation and Legacy Calculation Revisions returned NO-GO this phase
(source-side architectural mismatch and missing service-module
boundary, respectively); Joint Revision Lifecycle returned a
conditional GO for `joint_revisions.status` only, pending a
circular-import spike. Stage 4.1 (spike) empirically proved the risk
and its mitigation (deferred import, mirroring
`backend/api/dependencies.py`'s own established pattern). Stage 4.2
delivered the read-only adapter: `joint_revisions.status` →
governance `ReviewStatus`, with the deferred-import mitigation
mechanically enforced by AST-based and subprocess-based tests.
`joints.status` → `PublicationStatus` remains unimplemented (the
`superseded` transition has no live code path in the source
mechanism today).

Deferred: Stage 5 (final quality/documentation/release pass across
the whole phase). Production Validation and Legacy Calculation
Revisions governance integration remain out of scope unless a future,
separately-scoped phase revisits their source-side architecture.

## Faz 2.8.13 — Governance Workspace Completion

**Complete (Stages 1–5)**, delivered 2026-07-31 — see
`docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`,
`docs/11_PRODUCT_BACKLOG.md` §12F, and
`docs/phases/PHASE_2.8.13_COMPLETION_REPORT.md` for full detail.

Closed the one visibility gap identified in the approved pre-phase
repository analysis: the Faz 2.8.12 Stage 4.2 `joint_revision`
read-only governance projection adapter existed, was tested, and was
import-safety-verified, but had zero production consumers. Added
exactly one new read-only route,
`GET /api/governance/joint-revision/{revision_id}`, exposing the
existing adapter unmodified, and a minimal, additive extension of the
existing generic governance workspace UI — no new page, no write
action, no second status-mapping table, no new governance capability.

Stage 1 delivered the bilingual scope-lock and integration contract.
Stage 2 delivered the API route and corrected the governance adapters
package's stale docstring/exports (accurate only through Faz 2.8.11
Stage 5, not updated through Faz 2.8.12 Stage 2/3). Stage 3 delivered
the frontend lookup card with full TR/EN parity, fixing one
apostrophe-quoting bug and one stale hardcoded key-count constant in
a pre-existing structural test file along the way. Stage 4 performed
a full architectural-boundary, integrity, import-order, and
clean-clone verification pass with no regression found.

`backend/governance/adapters/joint_revision.py` and `backend/joints/`
remain byte-identical to their pre-phase state. No new database
table, migration, lifecycle transition, governance event, or
ownership-registry entry was introduced. Deferred, consistent with
the approved Stage 1 scope: a governance projection registry, a
cross-mechanism consistency validator, joint-revision write
synchronization, and Production Validation/legacy calculation-revision
governance integration (all previously assessed, not revisited).
