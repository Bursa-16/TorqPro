# Phase 2.8.12 — Completion Report
Governance Integration & Controlled Adoption

- Status: **Complete** (Stages 1–5, including sub-stages 4.1/4.2), as
  of 2026-07-30.
- Current branch: `main` (all Phase 2.8.12 work is currently
  **uncommitted working-tree changes** — no feature branch has been
  created in this environment; see "Release and version audit" below
  for the recommended branch/commit sequence).
- Current HEAD: `54345b33bb76ff37ff027e0204fbcfee2f3a2ff5` ("Merge pull
  request #24 from Bursa-16/feature/faz-2.8.11-engineering-governance-architecture")
  — this is the Faz 2.8.11 merge commit; Phase 2.8.12 has not been
  committed on top of it yet.
- ADRs: `docs/adr/ADR-0014-engineering-governance-architecture.md`
  (canonical model), `docs/adr/ADR-0015-washer-resolution-governance-integration.md`
  (write-path synchronization and reconciliation).
- Depends on: Faz 2.8.11 (governance package foundation, complete).

## 1. Phase objective

Controlled adoption of the Faz 2.8.11 governance architecture:
connect existing modules to the governance layer where — and only
where — a real, existing decision workflow justifies it, while
preserving backward compatibility, additive architecture, and the
single-source-of-truth principle. Not a mandate to maximize
governance coverage.

## 2. Stage-by-stage summary

| Stage | Deliverable | Outcome |
|---|---|---|
| 1 | Repository assessment, gap analysis, scope correction | Scoped to washer resolution (write) + joint revisions (read-only); Material Intelligence, Assembly Intelligence, Recommendation logic, report modules, Quality Harness, VDI 2230 extensions ruled out (no existing decision workflow) |
| 2 | Washer ownership registry, sync contract, structured outcomes, reconciliation, HTTP ownership guard | Complete, unwired to production |
| 3 | Controlled washer decision write-path integration | Complete, wired into the real decide endpoint |
| 4 | Assessment: Production Validation, legacy calculation revisions, joint revisions | Production Validation/legacy: **NO-GO**. Joints: conditional GO pending spike |
| 4.1 | Circular-import spike (isolated, disposable clone) | Real risk empirically confirmed; established deferred-import mitigation empirically confirmed effective |
| 4.2 | Read-only joint revision adapter | Complete: `joint_revisions.status` → `ReviewStatus` only |
| 5 | Consolidation, audit, documentation, release readiness | This report |

## 3. Final architecture

```
backend/governance/
  ownership.py                          Faz 2.8.12 Stage 2 — closed aggregate-type registry
  adapters/
    washer_resolution.py                Faz 2.8.11 Stage 5 — read-only projection
    washer_resolution_sync.py           Faz 2.8.12 Stage 2 — best-effort write sync
    washer_resolution_reconciliation.py Faz 2.8.12 Stage 2 — idempotent batch recovery
    joint_revision.py                   Faz 2.8.12 Stage 4.2 — read-only projection
  api.py                                + Stage 2 ownership guard, Stage 3 resolve_governance_store()
  enums.py / events.py / models.py / service.py / store.py / transitions.py / exceptions.py
                                         Unchanged since Faz 2.8.11

backend/app.py
  washer_resolution_decide_endpoint     + Stage 3: 2 local imports, 1 best-effort sync call

tools/run_washer_governance_reconciliation.py   Faz 2.8.12 Stage 2 — explicit CLI, dry-run default
```

## 4. Source-of-truth hierarchy

1. `washer_resolution_ledger.json` — immutable reference population.
2. `washer_resolution_decisions.json` — append-only, **sole
   authoritative** washer business-decision record.
3. `joint_revisions` (SQLite) — **sole authoritative** joint revision
   record (read-only projection only; no write integration exists or
   was implemented).
4. Governance event store — append-only, **derived** audit/lifecycle
   projection for washer resolution only. Never authoritative for any
   source mechanism's business decision. Never initiates or overwrites
   a source decision.

## 5. Ownership model

`backend/governance/ownership.py`: `RESTRICTED_AGGREGATE_TYPES =
{"washer_resolution"}`. Enforced at the single choke point shared by
all nine generic governance HTTP write endpoints
(`backend.governance.api._run_command`) — `409` for
`aggregate_type="washer_resolution"`, HTTP-surface only; internal
service calls are the sole legitimate write path. No `joint_revision`
entry exists (Stage 4.2 created no write path, so there is nothing to
restrict).

## 6. Supported mechanisms

- **Washer resolution** — full read + write integration
  (synchronize + reconcile), live in production.
- **Joint revisions** (`joint_revisions.status` only) — read-only
  projection to `ReviewStatus`, not wired to any production endpoint
  or write path.

## 7. Explicitly unsupported mechanisms (NO-GO, not incomplete)

- **Production Validation** — NO-GO this phase. `ValidationStudy.status`
  mixes review- and publication-lifecycle concepts in one mutable
  SQLite column (`draft→data_collection→completed→under_review→
  approved|rejected→archived`, with `rejected→data_collection`
  reopening) with no append-only decision ledger — architecturally
  incompatible with the canonical three-independent-lifecycle-group
  principle at the source, not merely unimplemented.
- **Legacy Calculation Revisions** — NO-GO this phase. No separate
  service/repository module exists; the logic is raw SQL embedded
  directly in `backend/app.py` route handlers. An additive adapter is
  not architecturally possible without a pre-refactor, which itself
  would violate this phase's additive-only mandate.
- **`joints.status` → `PublicationStatus`** — out of scope this
  phase. The `superseded` transition is declared in
  `JOINT_STATUSES` but has zero live code path in
  `backend/joints/service.py` today; a projection would be
  incomplete/misleading.

These are documented architectural findings, not deferred
implementation work items expected to "complete" a future stage of
this same design.

## 8. Live synchronization flow (washer resolution)

1. `washer_resolution_decide_endpoint` calls
   `svc.decide_resolution(...)` — authoritative, complete, unchanged
   since Faz 2.8.9.
2. Only if that succeeds: two local imports, then
   `sync_washer_decision_and_log(decision, resolve_governance_store())`
   — synchronous, best-effort, never raises.
3. Endpoint returns its unchanged response regardless of step 2's
   outcome.

## 9. Reconciliation flow

`reconcile(store, dry_run=...)` scans every washer decision
(`washer_resolution_decisions_store.list_decisions()`, read-only) and
calls `sync_washer_decision` — the **same function** the live
integration uses (no second, independently-written synchronization
algorithm). Deterministic counters with a tested invariant:
`scanned == synchronized + already_synchronized + would_synchronize +
not_representable + skipped_open + failed +
governance_store_unconfigured`.

## 10. Structured outcome model

`SyncOutcome`: `synchronized` / `already_synchronized` /
`would_synchronize` / `skipped_open` / `not_representable` /
`governance_store_unconfigured` / `failed` (sub-categorized:
`idempotency_conflict`, `decision_id_collision`, `invalid_transition`,
`missing_required_field`, `store_corruption`, `store_io_error`,
`unexpected_error`).

`ProjectionOutcome` (joint revisions, distinct vocabulary — no
partial-mapping case exists for this mechanism): `supported` /
`not_found` / `unsupported_status` / `invalid_source_record` /
`source_unavailable`.

## 11. API compatibility evidence

Washer decide endpoint: same URL, request schema, response schema
(`{"decision","created"}` — no governance field added, tested),
success status code, and error mapping (every existing `except`
clause untouched — governance sync code runs only after that block).
No second idempotency mechanism at the HTTP layer. No production API
route was added, modified, or removed for joint revisions (the
adapter is not wired to any endpoint).

## 12. Import-safety evidence (delayed-import invariant)

Empirically proven (Stage 4.1 spike, disposable clone) and
mechanically enforced (AST + subprocess tests,
`tests/governance/test_compatibility.py`):

- `backend.joints.service` (imports `conn`/`audit`/`now_iso` from
  `backend.app` at its own module level) is imported **only** inside
  a function body in `adapters/joint_revision.py` — never at module
  level anywhere in `backend/governance/`.
- `backend.governance.api` remains directly importable in a clean
  Python process that has never imported `backend.app` (re-verified
  this stage, manually and via the automated test suite).
- The joint revision adapter itself remains importable and callable
  in the same clean-process condition.
- `reload()` of the adapter module is safe.

## 13. Test coverage (this stage's targeted re-run)

| Suite | Result |
|---|---|
| Phase 2.8.12 targeted (ownership + sync + reconciliation + joint_revision + CLI) | 56/56 |
| Washer resolution (all files, `-k washer`) | 250/250 |
| Joint revision (existing foundation + new adapter) | 24/24 |
| Compatibility (`test_compatibility.py`) | 30/30 |
| Full governance suite | 233/233 |
| Full Python repository suite | 1851/1851 |
| JS harnesses (6) | 44 / 58 / 1097 / 45 / 40 / 32 — all unchanged |
| Existing quality gate (`tools/run_quality_gate.py`) | PASSED (6/6 gates) |

No test count differs from the Stage 4.2 baseline — Stage 5 added no
new tests (audit/consolidation only), except the two ADR/docstring
edits, which are documentation, not code, and required no new test.

## 14. Integrity evidence

SHA256, compared against the state immediately before any Phase
2.8.12 work began (Stage 1):

| File | Result |
|---|---|
| `washer_resolution_ledger.json` | **Identical** |
| `washer_resolution_decisions.json` | **Identical** |
| `backend/library/washer_resolution_service.py` | **Identical** |
| `backend/library/washer_resolution_decisions.py` | **Identical** |
| `backend/library/washer_resolution_decisions_store.py` | **Identical** |
| `backend/joints/*.py` (all 4 files) | **Identical** (`git diff --quiet`) |
| `backend/production_validation/*.py` (all 8 files) | **Identical** (`git diff --quiet`) |
| `backend/app.py` | **Changed** — the one intentional, approved Stage 3 diff (+19 lines) |

Full-phase `git diff --stat`/`git status --short`: 10 files modified
(`backend/app.py`, `backend/governance/__init__.py`,
`backend/governance/api.py`, `docs/11_PRODUCT_BACKLOG.md`,
`docs/314_Roadmap.md`, `docs/CHANGELOG.md`,
`docs/adr/ADR-0014-engineering-governance-architecture.md`,
`tests/governance/test_api.py`, `tests/governance/test_compatibility.py`,
`tests/test_faz_2_8_9_stage3_api.py`), **15** files added (4
production modules + 1 CLI tool + 10 test/doc files — corrected from
an earlier miscount of 12; see Sec. "Added files" below for the exact
list), 0 files deleted. **Zero** migrations, **zero** database schema
changes, **zero** production API routes added.

### Added files (exact, 15)

```
backend/governance/adapters/joint_revision.py
backend/governance/adapters/washer_resolution_reconciliation.py
backend/governance/adapters/washer_resolution_sync.py
backend/governance/ownership.py
docs/adr/ADR-0015-washer-resolution-governance-integration.md
docs/phases/PHASE_2.8.12_COMPLETION_REPORT.md
docs/phases/PHASE_2.8.12_STAGE2_INTEGRATION_CONTRACT.md
docs/phases/PHASE_2.8.12_STAGE3_CONTROLLED_WRITE_INTEGRATION.md
docs/phases/PHASE_2.8.12_STAGE4_2_JOINT_REVISION_READ_ONLY_ADAPTER.md
tests/governance/adapters/test_joint_revision.py
tests/governance/adapters/test_washer_resolution_reconciliation.py
tests/governance/adapters/test_washer_resolution_sync.py
tests/governance/test_ownership.py
tests/test_run_washer_governance_reconciliation.py
tools/run_washer_governance_reconciliation.py
```

### Modified files (exact, 10)

```
backend/app.py
backend/governance/__init__.py
backend/governance/api.py
docs/11_PRODUCT_BACKLOG.md
docs/314_Roadmap.md
docs/CHANGELOG.md
docs/adr/ADR-0014-engineering-governance-architecture.md
tests/governance/test_api.py
tests/governance/test_compatibility.py
tests/test_faz_2_8_9_stage3_api.py
```

Deleted files: 0.

## 15. Known risks

- The delayed-import invariant (joints) is mechanically tested but
  remains a convention a future contributor could violate without
  running the full suite first — no import-time guard prevents a bad
  edit from being written, only from merging.
- Washer reconciliation has not yet been exercised against a
  real, multi-record dataset (the repository's actual washer decision
  ledger currently has zero recorded decisions) — synthetic test
  coverage is comprehensive, but a first real production run is the
  genuine end-to-end proof.
- `README.md`'s phase table has not tracked completed phases since
  approximately Faz 2.8.7 (predates this phase) — a pre-existing
  documentation gap, not introduced or worsened by Phase 2.8.12, left
  unfixed per the "don't reinterpret unrelated gaps as this phase's
  defect" instruction.
- `VERSION` file (currently `2.6.9`) has not tracked releases since
  approximately v2.6.9 — git tags are the actual, current versioning
  practice (confirmed: `v2.8.11` is the latest tag, `VERSION` predates
  it by many phases). Not touched this stage (no single, currently-
  followed version source to update against).

## 16. Deferred backlog

- Production Validation and legacy calculation-revision governance
  integration: not planned under the current architecture; would
  require either a source-side refactor (legacy revisions) or a
  reconciled review/publication split (Production Validation) as
  its own, separately-scoped, separately-approved phase.
- `joints.status` → `PublicationStatus`: blocked on the source
  mechanism actually implementing its `supersede` transition.
- Joint revision write synchronization: not scoped by this phase;
  would follow the washer pattern (ADR-0015-equivalent design) if
  ever approved.

## 17. Release recommendation

See the separate release/version audit below. **GO for merge and
release**, subject to the branch/commit/tag recommendations in that
section and the person's own review.

---

## Release and version audit

- Current application version source: `VERSION` file (`2.6.9`) drives
  `backend.app.APP_VERSION` at runtime, but has not been bumped in
  step with any phase since approximately v2.6.9 — many shipped
  phases (2.8.1 through 2.8.11) did not update it. **Not a single,
  currently-followed version source** — left untouched, per
  instruction, rather than guessed.
- Latest Git tag: `v2.8.11` (annotated/lightweight not distinguished
  here; matches this repository's plain `vX.Y.Z` convention used for
  every 2.8.x phase except `v2.8.10-test-harness-quality`, which
  carried a descriptive suffix).
- Latest release: no GitHub Release object was inspected (outside
  this environment's access); the latest merged PR is #24 (Faz
  2.8.11), per `git log`.
- Expected next version: **`v2.8.12`**, consistent with the
  established plain-`vX.Y.Z` pattern for the majority of 2.8.x tags.
- Recommended branch name:
  `feature/faz-2.8.12-governance-integration-controlled-adoption`
  (matches the phase's own stated name and the repo's existing
  `feature/faz-2.8.X-<kebab-case-description>` convention).
- Recommended commit title (single squash commit, if the project's PR
  convention squashes — matching prior phases' single merge-commit
  pattern):
  `feat(governance): controlled washer write integration and read-only joint revision adapter (Faz 2.8.12)`
- Recommended tag: `v2.8.12`.
- Recommended release title: `TorqPro v2.8.12 — Governance Integration & Controlled Adoption`.
- Recommended short release notes:

  > Washer resolution decisions now synchronize into the governance
  > event store automatically (best-effort, never affecting the
  > washer API's own success response), with a mandatory reconciliation
  > tool for recovery. Joint revision review status
  > (`draft`/`review`/`approved`/`rejected`) is now available through
  > a read-only governance projection. Production Validation, legacy
  > calculation revisions, and joint publication status were assessed
  > and intentionally left out of this integration (see ADR-0014/
  > ADR-0015 and the phase completion report for the architectural
  > reasons). No existing API, ledger, or database schema was
  > modified.

No tag, release, merge, or push was performed from this environment.
