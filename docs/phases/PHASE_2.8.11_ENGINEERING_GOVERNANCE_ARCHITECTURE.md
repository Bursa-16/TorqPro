# Phase 2.8.11 — Engineering Governance Architecture and Decision
Workflow Standardization (Stage 1: Architecture & Documentation)

- Status: Stage 1 delivered, 2026-07-30. **This phase's
  implementation continued through Stage 5 and is now complete** —
  see `docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md` for the
  full, bilingual final report covering Stages 1–5. This file is kept
  unmodified below as the original Stage 1 record.
- ADR: `docs/adr/ADR-0014-engineering-governance-architecture.md`

## Why this phase exists

Before any Faz 2.8.11 code was written, a read-only repository
analysis (branch `main`, HEAD `acb6f96`, clean working tree) was
performed to check whether an "Engineering Decision Audit & Approval
Workflow" — the phase's original brief — already existed in some
form. It found four independent, already-shipped mechanisms doing
overlapping jobs with inconsistent vocabulary:

1. Production Validation workflow (`backend/production_validation/`,
   Faz 2.5A).
2. The legacy calculation-revision review/approve/reject workflow in
   `backend/app.py` (`calculation_revisions` table).
3. Joint revision lifecycle (`backend/joints/`, Faz 2.5A,
   `docs/adr/ADR-0003-joint-revision-root.md`).
4. Washer Resolution Decision Workflow (Faz 2.8.9,
   `docs/adr/ADR-0013-washer-resolution-decision-workflow.md`).

Building a fifth bespoke mechanism, as the original brief would have
produced, was assessed as a fragmentation risk rather than a fix. The
phase's scope was revised, before Stage 1 began, to:
**Engineering Governance Architecture and Decision Workflow
Standardization** — document, compare, and standardize the existing
mechanisms into one canonical vocabulary and transition model, with
no shared runtime implementation yet.

## Stage 1 scope (this delivery)

Documentation and architecture only. No table, JSON ledger, API
endpoint, enum, transition graph, or frontend string was added,
modified, or renamed. `backend/`, `frontend/`, and `tests/` are
byte-for-byte unchanged by this phase.

Delivered:

1. `docs/adr/ADR-0014-engineering-governance-architecture.md` — the
   canonical governance model: inventory of the four existing
   mechanisms, a status-vocabulary comparison table, precise
   definitions distinguishing review / approval / activation /
   resolution / revision / supersession / archival, fragmentation
   risks, a three-lifecycle-group canonical vocabulary (review,
   publication, resolution — deliberately never merged into one
   status field), canonical transition/audit/idempotency/revision-
   lineage principles, a canonical field-name table with required
   fields per transition, a compatibility strategy (nothing existing
   changes), a migration strategy (deferred, ordered by risk, not
   authorized by this ADR), rejected alternatives, consequences, and
   a Stage 2–5 plan.
2. `docs/11_PRODUCT_BACKLOG.md` §12D — this phase's backlog entry.
3. `docs/314_Roadmap.md` — forward-looking Stage 2–5 roadmap entry.
4. `docs/CHANGELOG.md` — Faz 2.8.11 (Stage 1) entry.
5. This file.

## What Stage 1 explicitly does not do

- Does not implement a shared governance data model, service, or API.
- Does not migrate, rename, or touch any field in mechanisms 1–4.
- Does not change `backend/library/washer_resolution*` or the Faz
  2.8.9 decision ledger in any way — mechanism 4 remains exactly as
  ADR-0013 defined it.
- Does not fix the pre-existing async test-harness gap in
  `tests/js/run_material_intelligence_tests.js` (Faz 2.8.8) — carried
  forward as a separate, tracked technical-debt item (first noted in
  ADR-0013's Consequences and `docs/11_PRODUCT_BACKLOG.md` §12B; not
  a blocker for this stage's documentation validation).
- Does not add or change any TR/EN UI translation key — no frontend
  surface was touched, so there is nothing new to keep in parity.
  (This phase's own documentation is English, consistent with every
  other `docs/adr/` and `docs/phases/` file in this repository; TR/EN
  parity in this project applies to user-facing UI strings, not to
  internal English-language design documentation — see
  `docs/README.md` and the existing ADR/phase-doc corpus.)

## Validation performed for this stage

- `git status` / `git diff --stat` confirm only the five files listed
  above under "Stage 1 scope" were added or changed; no file under
  `backend/`, `frontend/`, or `tests/` was touched.
- `git diff --check` run clean (no whitespace errors) across the
  changed files.
- Internal document references were checked by hand: every ADR/phase-
  doc/backlog cross-reference added in this stage points to a file
  that exists in this repository (`ADR-0013`, `ADR-0003`,
  `ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md`, `ADR-0008`,
  `docs/12_CLAUDE_CONTEXT.md`, `docs/README.md`).
- No documentation-generation or doc-linting test target exists in
  this repository's test suite (`tests/` contains only Python/JS
  functional tests; no markdown-link-checker or doc test was found
  during the earlier repository analysis), so no test command was run
  for this stage beyond the `git` checks above.

## Next steps

Stage 2 (shared governance contracts and typed domain models) is not
started and requires its own scoping approval before work begins, per
the project's standing "plan before execution" rule. See
ADR-0014's "Future-stage plan" section for the full Stage 2–5
outline.
