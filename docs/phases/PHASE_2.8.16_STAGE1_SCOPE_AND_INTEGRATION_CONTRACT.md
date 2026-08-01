# Phase 2.8.16 Stage 1 — Joint Revision List UX Improvements: Backend Query Foundation Scope and Integration Contract

- Status: **Stage 1 complete** (backend query foundation only). Phase
  2.8.16 as a whole is **not** complete — Stages 2–6 remain (API
  contract, CSV export, frontend UX, frontend harness/i18n, full
  validation and documentation). Do not read this document as a
  phase completion report.
- Depends on: `docs/adr/ADR-0014-engineering-governance-architecture.md`,
  `docs/phases/PHASE_2.8.14_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`,
  `docs/phases/PHASE_2.8.14_COMPLETION_REPORT.md`,
  `docs/11_PRODUCT_BACKLOG.md` §12G.
- Baseline: branch `main`, HEAD `0f7b638` at the time
  `feature/faz-2.8.16-joint-revision-list-ux` was cut. Working tree
  clean. Full suite 1919/1919, quality gate 6/6, governance workspace
  harness 160/160 — all reconfirmed immediately before Stage 1 work
  began.

## 1. Stage 1 Objective

Add a read-only, deterministic search/sort/pagination query layer
over the existing Faz 2.8.14 joint revision governance projection
(`project_joint_revisions_bulk`), as a pure Python domain/service
function with no HTTP dependency. This is the foundation Stage 2 (API
contract) will expose and Stage 4 (frontend UX) will consume — Stage
1 itself adds no route and no UI.

## 2. In Scope

- `backend/governance/joint_revision_query.py`: the new module.
- `query_joint_revision_projections(...)`: the single query entry
  point (search + sort + paginate).
- `JointRevisionQueryResult`: typed, immutable result model.
- `JointRevisionQueryValidationError`: domain validation exception.
- `tests/governance/test_joint_revision_query.py`: unit/service
  tests.
- This scope document.

## 3. Out of Scope

- **No new API endpoint.** `backend/governance/api.py` is unmodified.
- **No change to the existing endpoint.** `GET
  /api/governance/joint-revisions` is byte-for-byte behaviorally
  identical to Faz 2.8.14 — same bare-array response, same ordering,
  same `joint_id`-only query surface.
- **CSV export** — Stage 3.
- **Frontend** — Stage 4. `frontend/index.html` is unmodified.
- **i18n keys** — Stage 5.
- **VERSION / README / CHANGELOG** — untouched; see Stage 0 report
  §13 for the version-update timing decision (Stage 6, not now).
- **HTTP status-code mapping** for
  `JointRevisionQueryValidationError` — Stage 2's responsibility.
  This module raises no HTTP status and has no FastAPI import.

## 4. Existing Architecture Reused

- `backend.governance.adapters.joint_revision.project_joint_revisions_bulk(joint_id=None)`
  is called exactly once per query, unchanged, as the sole source of
  projection data. No projection/mapping logic is duplicated or
  re-derived.
- `backend.governance.adapters.joint_revision.JointRevisionProjection`
  is reused unchanged as the item type inside the new result model.
- `backend.governance.exceptions.GovernanceError` is the base class
  for the new `JointRevisionQueryValidationError`, consistent with
  every other governance domain exception in
  `backend/governance/exceptions.py`.
- Module placement: flat under `backend/governance/` (alongside
  `service.py`, `store.py`, `enums.py`), not a new `services/`
  sub-package — the existing package has no such sub-package
  anywhere, and one module does not warrant introducing one.

## 5. Query Pipeline

Fixed order, every call:

1. Validate `page`, `page_size`, `sort_by`, `sort_order` — **before**
   any source read.
2. Read + project source data (`project_joint_revisions_bulk`,
   optionally filtered by `joint_id`).
3. Search (substring, case-insensitive).
4. Sort (allow-listed field, explicit tie-breaker).
5. Compute `total` (post-search, pre-pagination).
6. Slice the requested page.

## 6. Search Contract

Fields searched, in order: `joint_revision_id` (as a partial numeric
string), `source_status`, `canonical_status`, `outcome`,
`safe_reason`. Case-insensitive, trimmed, Unicode-safe (plain Python
`str.lower()`/substring, no locale assumptions beyond what the
standard library already provides). `None`/empty/whitespace-only
search means "no filter" (all records match). A `None` field value is
skipped entirely when building the searchable text, never rendered as
the literal string `"None"`.

**`lifecycle_group` is excluded from search.** Evidence: within this
mechanism's data, `lifecycle_group` is `None` for every
non-`SUPPORTED` outcome and the single constant value `LifecycleGroup.REVIEW`
(`"review"`) for every `SUPPORTED` one — every joint revision this
adapter projects belongs to the same governance lifecycle group by
construction (see `backend/governance/adapters/joint_revision.py`,
`project_joint_revision`). A field with exactly one possible non-null
value carries no discriminating search value beyond what `outcome`
already provides, so including it would add a search field a user
could never use to narrow results.

## 7. Sorting Contract

Allow-listed `sort_by`: `joint_revision_id`, `source_status`,
`canonical_status`, `outcome`. Allow-listed `sort_order`: `asc`,
`desc` (strict — `ASC`/`Desc`/other casing is rejected, not
normalized; no repository-wide normalization convention was found to
follow instead).

**`lifecycle_group` is excluded from sorting**, for the identical
reason given in §6 (a single-value field produces no meaningful
ordering). **`safe_reason` is excluded from sorting**: it is a
free-text diagnostic message populated only for the four non-`SUPPORTED`
outcomes, `None` for the common `SUPPORTED` case; alphabetizing a
mostly-`None`, variable-length diagnostic sentence field provides no
actionable ordering for a user browsing revisions, and search (§6)
already covers the "find by reason text" use case this field exists
for.

Determinism rules:
- `None` values always sort **last**, in both `asc` and `desc`.
- Tie-breaker (equal primary value, and among all `None` values) is
  always `joint_revision_id asc`, **even when the primary
  `sort_order` is `desc`** — implemented via two chained stable
  sorts (ascending-id pass, then value pass), never a single reversed
  tuple key, which would also reverse the tie-breaker.
- Text comparison is case-insensitive (`str.lower()`).
- Sorting by `joint_revision_id` uses a single pass with no duplicate
  key (it is itself the tie-breaker and is never `None`).
- The input list is never mutated (`sorted()`/comprehensions only,
  never `list.sort()` on a caller-visible list).

## 8. Pagination Contract

Defaults: `page=1`, `page_size=25`. `MAX_PAGE_SIZE = 200` — a new,
Stage-1-local constant; no existing pagination limit was found
anywhere else in `backend/` to reuse instead. `page < 1`,
`page_size < 1`, and `page_size > MAX_PAGE_SIZE` all raise
`JointRevisionQueryValidationError`. `bool` and `float` values are
explicitly rejected for both `page` and `page_size` (Python's `bool`
is an `int` subclass — checked and excluded first). `total` reflects
the post-search count; `total_pages = ceil(total / page_size)`, `0`
when `total == 0`. A `page` beyond the last available page is not an
error — it returns an empty `items` tuple with the correctly
computed `total`/`total_pages`, and echoes the requested `page` back
unchanged.

## 9. Validation Contract

`JointRevisionQueryValidationError(parameter, value, reason)` —
subclasses `GovernanceError`, HTTP-independent, deterministic
message, never a file path or traceback. Raised strictly before
`project_joint_revisions_bulk` is ever called (verified by
`test_validation_happens_before_source_is_read`, which asserts the
patched adapter received zero calls). Stage 2 maps this exception to
an HTTP `422` response; this module defines no such mapping itself.

## 10. Source Safety and Read-Only Guarantees

`project_joint_revisions_bulk` is documented and tested (Faz 2.8.14)
to never raise — an internal source read failure returns `[]`. This
module adds no `try/except` around that call and relies on the
existing contract unchanged: a source failure flows through as
`items=(), total=0, total_pages=0`, never a fabricated error item and
never a leaked exception message. The module never writes to the
`joints`/`joint_revisions` tables, never constructs or writes a
governance event, and never mutates a source-derived list in place.

## 11. Backward Compatibility

`backend/governance/api.py` and `frontend/index.html` are byte-for-byte
unmodified. `GET /api/governance/joint-revisions`'s bare-array
response, ascending-id default order, and `joint_id`-only query
surface are all unchanged and re-verified by the existing
`tests/governance/test_joint_revision_bulk_api.py` suite, which
passes unmodified. The new module is purely additive: nothing in the
existing codebase imports it yet.

## 12. Stage 2 Integration Boundary

Stage 2 is expected to: add a new, additive API route (not modify the
existing bare-array one — Stage 0's Option B decision), map
`JointRevisionQueryValidationError` to HTTP `422`, decide the exact
query-parameter names at the HTTP layer (may pass through unchanged),
and decide the new response envelope shape (`items`/`total`/`page`/
`page_size`/`total_pages`, mirroring `JointRevisionQueryResult`
directly or via a dedicated FastAPI response model — this module's
result type is not itself a FastAPI response model and Stage 2 is
free to adapt it).

## 13. Test Strategy

`tests/governance/test_joint_revision_query.py`, domain/service-layer
only (no `TestClient`, no auth) — two fixture styles, matching the
existing precedent in `tests/governance/adapters/test_joint_revision.py`
and `tests/governance/test_joint_revision_bulk_api.py`:

- Real, migrated temp-SQLite-backed joint/revision records (via
  `backend.joints.service`) for baseline, `joint_id`-filter,
  pagination, and source-safety scenarios.
- Directly-constructed `JointRevisionProjection` instances, injected
  by monkeypatching `project_joint_revisions_bulk` at the point this
  module imported it, for deterministic search/sort scenarios
  covering every outcome value without needing many real DB records.

62 new tests; no existing test file was modified.

## 14. Acceptance Criteria

- Query service additive; no existing file modified.
- Search works on the five documented fields, case-insensitive,
  trimmed, no false match on `None`-as-text.
- Sorting allow-list enforced; deterministic; explicit
  `joint_revision_id asc` tie-breaker in every case; `None` always
  last.
- Pagination produces correct `total`/`total_pages`/`items` in every
  documented edge case; validation happens before any source read.
- `JointRevisionQueryValidationError` is domain-level, HTTP-independent.
- Source read failures degrade to a safe empty result; no traceback
  or path leak.
- No mutation, no governance event, no persistence.
- New tests, full governance suite, full pytest suite, quality gate,
  and the governance workspace JS harness all pass — see the Stage 1
  final report for exact figures.
