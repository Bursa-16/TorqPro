# Phase 2.8.13 — Completion Report
Governance Workspace Completion

- Status: **Complete** (Stages 1–5), as of 2026-07-31.
- Branch: `feature/faz-2.8.13-governance-workspace-completion`.
- Baseline HEAD: `cb20e69` (Faz 2.8.12 merge commit).
- Stage 1–4 HEAD: `763979bd5e70f36374c216ad39b673ca2863b2d0`.
- Contract: `docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`.
- Depends on: Faz 2.8.12 Stage 4.2 (`backend/governance/adapters/joint_revision.py`,
  complete, unwired to any production entry point until this phase).

## 1. Phase objective

Close a single, evidence-based visibility gap identified in the
approved pre-phase repository analysis: the Faz 2.8.12 Stage 4.2
`joint_revision` read-only governance projection adapter existed,
was tested, and was mechanically import-safety-verified, but had
**zero production consumers** — no API route, no frontend page. This
phase makes that existing projection reachable through one new
read-only API route and a minimal, additive extension of the existing
generic governance frontend workspace. It introduces no new
governance capability, no new projection logic, and no new source of
truth.

## 2. Scope

**In scope:**
- One new read-only API route exposing the existing
  `project_joint_revision()` adapter, unmodified.
- Correcting `backend/governance/adapters/__init__.py`'s stale
  package docstring/`__all__` (identified as a genuine documentation-
  drift defect during the pre-phase analysis), which had gone stale
  since Faz 2.8.12 Stage 2/3.
- A minimal, additive frontend lookup section inside the existing
  `page-governance` workspace.
- Focused backend and frontend test coverage for the new route and UI.

**Explicitly out of scope** (see Stage 1 contract, Section 11, and
the pre-phase repository analysis for the full rationale):
- New write endpoints, governance events, lifecycle transitions,
  database tables, or persistence mechanisms.
- A joint-revision synchronization service (no washer-resolution-
  style write path).
- A governance projection registry, a cross-mechanism consistency
  validator, or ownership-registry expansion — all assessed and
  deferred as premature at the current scale (two source mechanisms,
  one of which has a write path).
- Production Validation and legacy calculation-revision governance
  integration (Faz 2.8.12 Stage 4 NO-GO findings restated, not
  revisited).
- Any refactor, cleanup, or behavior change unrelated to this
  specific visibility gap.

## 3. Architecture summary

```
Frontend (frontend/index.html, page-governance)
   ↓  GET, apiRequest(), encodeURIComponent(revision_id)
Governance read API (backend/governance/api.py)
   GET /api/governance/joint-revision/{revision_id}
   ↓  one call, no store dependency
joint_revision governance adapter (backend/governance/adapters/joint_revision.py — UNCHANGED)
   project_joint_revision(revision_id) -> JointRevisionProjection
   ↓  deferred import, function-body only
authoritative joint revision mechanism (backend/joints/service.py, joint_revisions table — UNCHANGED)
```

The dependency direction is one-way and unchanged from Faz 2.8.12:
governance depends on the authoritative mechanism through the
existing adapter; nothing in `backend/joints/` imports governance.
The adapter's Faz 2.8.12 Stage 4.1-proven deferred-import mitigation
(`backend.joints.service` imported only inside `_joints_service()`,
never at module level) is preserved unmodified and re-verified under
this phase's new call path (route → adapter, and the real
ASGI/TestClient request path).

## 4. Stage 1 summary — Scope Lock and Integration Contract

Delivered `docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`
(bilingual EN/TR, 743 lines): purpose, current-gap evidence, authority/
ownership boundary, approved dependency direction, the full API
contract (exact route, outcome→HTTP-status mapping, response shape,
error-safety rules), the frontend contract, error mapping, test
contract, allowed/protected file lists, non-goals, and a five-stage
plan. No code or test changes this stage — documentation only,
committed as `106e30b`.

## 5. Stage 2 summary — Read-Only API Exposure

Added exactly one route, `GET /api/governance/joint-revision/{revision_id}`,
calling the existing `project_joint_revision()` unmodified. Outcome→
status mapping: `supported`/`unsupported_status`/`invalid_source_record`/
`source_unavailable` → 200 (all legitimate, already-classified adapter
results); `not_found` → 404. No `try/except` in the handler
(`project_joint_revision` is documented and tested to never raise);
no governance-store dependency (the route never reads or writes
governance state). Corrected `backend/governance/adapters/__init__.py`'s
stale docstring/`__all__` to accurately distinguish read-only
projection adapters, write-sync adapters, and reconciliation
utilities, and to export `joint_revision`'s stable public symbols —
empirically verified safe in a clean process (no circular-import
risk) before making the change. Added `tests/governance/test_joint_revision_api.py`
(16 tests) and 4 focused additions to `tests/governance/test_compatibility.py`
(route inventory extended, GET-only guard, no-write-route guard,
approved-import-direction guard, handler-calls-no-governance-write-
function guard). Governance suite: 253/253 (233 baseline + 20 new).
Full suite: 1871/1871. Committed as `013db43`.

## 6. Stage 3 summary — Frontend Workspace Visibility

Added a minimal, additive "Joint Revision Projection (read-only)"
card inside the existing `page-governance` div (no new standalone
page): a `revision_id` input, a "Look Up" button, and a result
container. `govLoadJointRevision()` calls the new route through the
existing `apiRequest` helper with `encodeURIComponent`, GET only.
Rendering distinguishes all five real outcomes directly from the
API's own fields — no second status-mapping table; unsupported/
invalid/unavailable/not-found states render as informational
(non-error) states with the backend's own `safe_reason` text.
16 new `gov.jr.*` translation keys added with full TR/EN parity.
Extended `tests/js/run_governance_workspace_tests.js` with 13 new
scenarios (98/98 assertions passing). Fixed one genuine bug
discovered during validation (an apostrophe forced a double-quoted
JS string, breaking the existing single-quote-only key/value
extraction regex in `tests/test_faz_2_8_11_stage4_frontend.py`) and
corrected that same file's stale hardcoded gov.\*/`sidebar.governance`
key-count constant (53 → 69), made obsolete directly by the required
new keys. Governance suite unchanged at 253/253 (confirming zero
backend files touched this stage). Committed as `763979b`.

## 7. Stage 4 summary — Full Regression and Integrity Verification

Verification-only stage; no code or documentation changes committed
(HEAD unchanged throughout). Confirmed: the full phase diff
(`cb20e69..HEAD`) touches exactly the 8 files expected, no more, no
less; all 15 architectural-boundary checks pass (adapter and
`backend/joints/` byte-identical to baseline, route handler is a
two-line pass-through with no store/service call, no new table/
migration/transition/ownership-registry entry, GET-only on both
router and full-app OpenAPI level, no reverse import, deferred-import
mitigation intact, no second status mapping, unsupported states stay
visible); source-data integrity (repository JSON files byte-identical
before/after, SHA256-verified) and governance-event-store integrity
(no production store file exists; all writes are per-test, temp-file,
non-persistent) both confirmed; import order verified in both
directions in clean subprocesses with no circular-import error; the
real HTTP request path confirmed via the actual runtime OpenAPI
schema — all 12 governance routes registered exactly once, no
duplication; an independent `git worktree` clean-clone reproduced
identical results (quality gate 6/6, governance suite 253/253, JS
harness 98/98, full suite 1871/1871). No regression found.

## 8. Changed files (complete phase, `cb20e69..HEAD`)

```
docs/phases/PHASE_2.8.13_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md   (added, 743 lines)
backend/governance/api.py                                          (modified, +68/-0)
backend/governance/adapters/__init__.py                             (modified, +85/-27)
tests/governance/test_compatibility.py                              (modified, +92/-4)
tests/governance/test_joint_revision_api.py                         (added, 351 lines)
frontend/index.html                                                 (modified, +165/-0)
tests/js/run_governance_workspace_tests.js                          (modified, +211/-4)
tests/test_faz_2_8_11_stage4_frontend.py                            (modified, +4/-4)
```

8 files changed, 1688 insertions(+), 31 deletions(-). No file outside
this list changed at any point in the phase (verified in Stage 4).

## 9. Commit history

```
106e30b docs: lock Phase 2.8.13 governance workspace scope
013db43 feat: expose joint revision governance projection
763979b feat: add joint revision governance workspace
```

All three commits are on `feature/faz-2.8.13-governance-workspace-completion`,
branched from `cb20e69`. None pushed, tagged, merged, rebased, or
squashed at any point in the phase.

## 10. API additions

Exactly one new route:

```http
GET /api/governance/joint-revision/{revision_id}
```

| `ProjectionOutcome` | HTTP status | Notes |
|---|---|---|
| `supported` | 200 | Full projection fields populated |
| `unsupported_status` | 200 | Legitimate result — record exists, status outside the closed vocabulary |
| `invalid_source_record` | 200 | Legitimate result — record exists, malformed |
| `source_unavailable` | 200 | Legitimate result — adapter's own safe, generic message |
| `not_found` | 404 | No such joint revision |

Authentication reuses the existing `backend.api.dependencies.user`
dependency (no new auth mechanism). Response body is the adapter's
existing `JointRevisionProjection.model_dump(mode="json")`, unmodified
— no field added, renamed, or removed. No `POST`/`PUT`/`PATCH`/`DELETE`
route exists for joint revisions; no query parameters.

## 11. Frontend additions

One additive card inside the existing `page-governance` workspace
(no new sidebar entry, no new standalone page): a revision-ID lookup
input, a lookup button, and a result area rendering all five outcomes
via the API's own fields. 16 new `gov.jr.*` i18n keys (EN+TR, full
parity). GET-only; no write action of any kind.

## 12. Test results

| Suite | Result |
|---|---|
| `tests/governance/test_joint_revision_api.py` (new) | 16/16 |
| `tests/governance/test_compatibility.py` (4 new + 30 existing) | 34/34 |
| `tests/governance/test_api.py` (unmodified) | 38/38 |
| Full governance suite | 253/253 (233 baseline + 20 new) |
| `tests/test_faz_2_8_11_stage4_frontend.py` | 42/42 |
| `tests/test_i18n_key_parity.py` | 6/6 |
| `run_governance_workspace_tests.js` (13 new + 24 existing scenarios) | 98/98 assertions |
| Other 5 JS harnesses (unmodified) | 44/44, 1097/1097, 45/45, 40/40, 32/32 |
| Full Python repository suite | 1871/1871 (1851 baseline + 20 new) |
| Quality gate (`tools/run_quality_gate.py`) | PASSED (6/6 gates) |
| `flake8 --max-line-length=100 backend/governance/ tests/governance/` | clean |
| `git diff --check` | clean |

## 13. Integrity verification results

- **Source data**: every repository-tracked JSON file under
  `backend/library/data/` SHA256-verified byte-identical before and
  after the full validation run.
- **Governance event store**: no production store file exists in the
  repository (`TORQPRO_GOVERNANCE_EVENT_STORE_PATH` unset → safe,
  documented "not configured" behavior); all test-exercised stores
  are per-test, temp-file, non-persistent, dependency-injected.
- **Protected files**: `backend/governance/adapters/joint_revision.py`,
  `store.py`, `service.py`, `events.py`, `transitions.py`,
  `backend/joints/`, `backend/engineering_core/`, `backend/vdi2230_core/`,
  `backend/calculation_engine/`, `backend/library/`,
  `backend/governance/ownership.py` — all byte-identical to the
  `cb20e69` baseline (`git diff --quiet`).
- **Import order**: both directions (`backend.app` → adapter; adapter/
  `governance.api` → `backend.app`, never touched) verified in clean
  subprocesses — no circular-import error in either order.
- **Real request path**: confirmed via the live OpenAPI schema — all
  12 governance routes registered exactly once; three repeated `GET`
  calls returned identical status codes and bodies (deterministic,
  side-effect-free).
- **Clean-clone reproduction**: an independent `git worktree` at the
  phase's final commit, with its own virtual environment and database,
  reproduced identical results for the quality gate, governance suite,
  JS harness, and full suite. Worktree removed after verification; the
  active branch was not modified by the process.

## 14. Known limitations

- The `not_found` outcome (HTTP 404) cannot carry the adapter's
  dynamic `safe_reason` text through the frontend's existing
  `apiRequest` helper, because that helper only extracts a `detail`
  field from non-2xx bodies and this route's 404 body has no `detail`
  field (it is the full `JointRevisionProjection`, matching the
  approved Stage 1 contract). The frontend substitutes a static,
  accurate translation of the adapter's own known, fixed `not_found`
  message rather than the literal per-request body text. This is a
  narrow, understood, and tested limitation of the shared `apiRequest`
  helper's error-handling convention — not a defect introduced by this
  phase, and not something this phase's scope permitted changing
  (`apiRequest` is a shared, whole-application utility).
- The joint-revision lookup is a manual, on-demand query (enter an ID,
  click "Look Up") — there is no list/browse view of joint revisions
  within the governance workspace. This matches the approved Stage 1
  scope exactly (visibility for the existing projection, nothing
  more) and was not a requested capability.

## 15. Deferred items

Restated from the approved pre-phase repository analysis and the
Stage 1 contract's non-goals — none newly introduced by this phase:

- A governance projection registry (low value at the current scale of
  two source mechanisms).
- A cross-mechanism consistency validator (premature — only one
  mechanism, washer resolution, has a write-integrated path today).
- Joint revision write synchronization (would follow the washer
  pattern, ADR-0015-equivalent, if ever separately approved).
- Production Validation and legacy calculation-revision governance
  integration (Faz 2.8.12 Stage 4 NO-GO findings, architectural, not
  merely unimplemented).
- `joints.status` → `PublicationStatus` (blocked on the source
  mechanism implementing its `supersede` transition).
- The pre-existing `README.md` phase-table and `VERSION` file
  documentation-currency gaps noted in the Faz 2.8.12 completion
  report remain unaddressed (pre-existing, not worsened by this
  phase, out of this phase's scope).

## 16. Next-phase recommendations

- If a second mechanism ever gains a governance write-integration
  path (beyond washer resolution), revisit the case for a governance
  projection registry and a cross-mechanism consistency validator —
  both were deferred specifically for being premature at two
  mechanisms, not rejected outright.
- If real usage of the joint-revision lookup surfaces a need for
  bulk/list visibility (rather than single-ID lookup), scope that as
  its own, separately-approved phase — this phase deliberately kept
  the surface area to the single approved route and matching UI.
- Consider, as an independent, separately-scoped documentation task
  (not implied or required by this phase), addressing the pre-existing
  `README.md` phase-table and `VERSION` file drift noted above and in
  the Faz 2.8.12 completion report.

## 17. Release recommendation

**GO for merge and release**, subject to the person's own review. No
tag, release, merge, or push was performed from this environment.

---

## Release and version audit

- Recommended branch name (already in use):
  `feature/faz-2.8.13-governance-workspace-completion`.
- Recommended commit title (single squash commit, if the project's PR
  convention squashes, matching prior phases' single merge-commit
  pattern): `feat(governance): read-only joint revision workspace exposure (Faz 2.8.13)`.
- Recommended tag: `v2.8.13`.
- Recommended release title: `TorqPro v2.8.13 — Governance Workspace Completion`.
- Recommended short release notes:

  > The existing, previously-unwired joint revision governance
  > projection (Faz 2.8.12 Stage 4.2) is now reachable through a new
  > read-only API route and a minimal addition to the governance
  > workspace UI. No new write path, governance event, database
  > table, or lifecycle transition was introduced. Unsupported or
  > malformed joint revision records remain visible and clearly
  > labeled rather than hidden or silently normalized.

No tag, release, merge, or push was performed from this environment.
