# Phase 2.8.16 Stage 4 — Joint Revision List UX Improvements: Frontend UX

- Status: **Stage 4 complete** (frontend UX only). Phase 2.8.16 as a
  whole is **not** complete — Stages 5–6 remain (frontend harness/
  i18n depth + quality-gate integration, full validation and
  documentation). Do not read this document as a phase completion
  report.
- Depends on:
  `docs/phases/PHASE_2.8.16_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`,
  `docs/phases/PHASE_2.8.16_STAGE2_API_CONTRACT.md`,
  `docs/phases/PHASE_2.8.16_STAGE3_CSV_EXPORT.md`.
- Baseline: branch `feature/faz-2.8.16-joint-revision-list-ux`, HEAD
  `bb28bc7` (Stage 3 commit) at the time Stage 4 work began. Working
  tree clean. Full suite 2144/2144, quality gate 6/6, governance
  workspace harness 160/160 — all reconfirmed before Stage 4 work
  began.

## 1. Stage 4 Objective

Add search/sort/pagination/CSV-export UI to the existing "Joint
Revision List (read-only)" card, consuming the Stage 2 paginated
query endpoint and the Stage 3 CSV export endpoint — entirely
client-side/presentation work, no backend change.

## 2. Existing Frontend Reused

- `apiRequest()` — used for the query endpoint (JSON), unchanged.
- `govEsc()` — HTML-escaping + `None`/`undefined`/`''` -> em dash,
  reused unchanged for every dynamic value rendered.
- `govStatusLabel()`, `govGroupLabel()`, `govJrOutcomeLabel()` —
  reused unchanged; no second status/outcome-label mapping was
  defined.
- `govIsWellFormedJointRevisionListItem()` — reused unchanged inside
  the new envelope validator (see Section 11) for each item's own
  shape.
- `exportArchiveCSV()`'s existing fetch -> blob -> temporary-anchor ->
  click -> revoke pattern — followed exactly for the new CSV export
  handler (this app's auth is always a bearer token via
  `Authorization` header, never a cookie/session, so a direct
  `<a href>` link would not carry auth — confirmed by inspecting
  `apiRequest()` and the existing `exportArchiveCSV()` precedent
  before choosing this approach).
- `govInit()`/`govReapplyLanguage()` — both extended with one
  additive line each (see Section 4/13); no existing line in either
  was removed or altered.
- CSS classes: `table`, `form-group`, `form-label`, `form-input`,
  `form-select`, `form-row`, `form-row3`, `btn`, `btn-primary`,
  `btn-secondary`, `fc-muted`, `alert alert-danger` — all pre-existing
  (verified present in `frontend/index.html` before use); no new CSS
  rule and no new class were added.

## 3. Frontend State Model

**`govJointRevisionListState`** — single, plain object:

```js
{ search, sortBy, sortOrder, page, pageSize, total, totalPages, items, loading, error }
```

Lives entirely in this new section; never shared with or mutated by
the legacy `GOV_JRLIST_LAST_RESULT`/`govLoadJointRevisions()` code
path, which remains fully intact and unused by the new UX (its own
result container, `#gov-jrlist-result`, is untouched).

## 4. Query Endpoint Integration

Endpoint: **`GET /api/governance/joint-revisions/query`**. URL
builder: **`govJointRevisionListBuildQueryUrl()`** — `URLSearchParams`
only, reads `search`/`sortBy`/`sortOrder`/`page`/`pageSize` from state
and `joint_id` from the **same, shared** `#gov_jrlist_joint_id` input
the legacy list above already uses (per the Stage 4 contract's "use
the existing filter/input if one exists" rule — no second joint-ID
input was added). Empty search and empty joint_id are both omitted
from the URL entirely (never sent as `search=`/`joint_id=`); `sort_by`/
`sort_order`/`page`/`page_size` are always included, even at their
default value. Load function: **`govLoadJointRevisionsQuery()`**.
Render function: **`govRenderJointRevisionQueryResult()`**.

Initial load: one additive line in `govInit()` (the existing
`showPage('governance')` -> `govInit()` hook already used by every
other governance sub-section) — `govInit()`'s two existing lines are
unchanged.

## 5. Search UX

Text input (`#gov_jrlist_query_search`) + **Search** button
(`govJointRevisionQuerySearch()`) + **Clear** button
(`govJointRevisionQueryClearSearch()`) + Enter-key binding on the
input itself. Trimmed client-side before being written to
`state.search` (matches backend semantics: whitespace-only becomes
`''`, meaning "no filter"). No debounce/auto-search-on-keypress was
added (no existing debounce precedent found in the repository to
follow, and the Stage 4 contract explicitly does not require one).
Search always resets `state.page` to `1` before reloading.

## 6. Sorting UX

Two `<select>` controls: `#gov_jrlist_query_sort_by`
(`govJointRevisionQuerySortChange()`) and
`#gov_jrlist_query_sort_order` (`govJointRevisionQueryOrderChange()`).
Options for the former are restricted to the four backend-allow-listed
values (`joint_revision_id`, `source_status`, `canonical_status`,
`outcome`) with translated display labels — the technical field names
themselves are never shown to the user. A client-side copy of this
allow-list (`GOV_JRLIST_QUERY_SORT_FIELDS`) exists only to populate
the `<select>` and defensively fall back to the default if an
unexpected value ever appears; the backend's own `422` remains the
real, single source of truth for what is actually accepted. Both
changes reset `state.page` to `1`.

## 7. Pagination UX

**Previous**/**Next** buttons rendered inside the result area
(`govJointRevisionQueryPrevPage()`/`govJointRevisionQueryNextPage()`),
disabled at page 1 / the last page / whenever `total_pages === 0`
(verified). A page-size `<select>` (10/25/50/100/200, default 25 —
the same ceiling as `MAX_PAGE_SIZE`, no larger option offered) resets
`state.page` to `1` on change. Pagination is 100% server-side: this
section never slices, re-sorts, or re-filters the `items` array it
receives — it renders exactly what the API returned, in the order the
API returned it (verified by a dedicated harness test with
out-of-numeric-order ids).

## 8. Result Count and Metadata

`"{total} {results} — {pageLabel}"` summary line, shown above the
table, using the existing `fc-muted` style — matches the legacy
list's own `result_count_prefix` convention rather than inventing a
new layout. `govJointRevisionQueryPageLabel()` builds `"Page {page} of
{totalPages}"` (`gov.jrlist.pageOf`) using the same `{placeholder}` +
`.replace()` convention already used elsewhere in this file (e.g.
`library.demo_full_version_note`), not a newly invented templating
mechanism.

## 9. CSV Export UX

**Export CSV** button (`#gov_jrlist_query_export_btn`) ->
**`govJointRevisionQueryExportCsv()`**. URL builder:
**`govJointRevisionListBuildExportUrl()`** — same `search`/`sort_by`/
`sort_order`/`joint_id` extraction as the query builder, **never**
`page`/`page_size` (verified: the export URL never matches a `page=`
pattern). Uses `fetch()` directly (not `apiRequest()`, which would
decode/re-encode the CSV's UTF-8 BOM via its JSON/text branching) with
an explicit `Authorization: Bearer ${AUTH_TOKEN}` header, mirroring
the existing `exportArchiveCSV()` precedent exactly: response ->
`.blob()` (never `.text()`/`.arrayBuffer()`, so the fetched bytes are
never read or transformed) -> `URL.createObjectURL()` -> a temporary
`<a>` with `download="joint-revisions-export.csv"` -> `appendChild` ->
`.click()` -> `.remove()` -> `URL.revokeObjectURL()`. The export
button is disabled and its label swapped to `gov.jrlist.exporting`
for the duration of the request, and always restored in a `finally`
block regardless of success or failure.

## 10. Loading, Empty and Error States

- **Loading**: `state.loading` gates the render function's first
  branch — `fc-muted` "Loading..." message; Previous/Next/Search/
  Clear/Export controls are all disabled via
  `govRenderJointRevisionQueryControlsState()` while `true`.
- **Empty**: `total === 0`/`items.length === 0` -> the result-count
  summary line plus a `fc-muted` "No matching joint revisions found."
  message — no empty `<table>` is ever rendered. Pagination controls
  are simply absent (not rendered) rather than rendered-and-disabled,
  since there is nothing to paginate. **Export is not disabled** in
  this state: a header-only CSV export of zero matching records is a
  legitimate, already-tested backend behavior (Stage 3), so disabling
  the button would prevent a real, valid use case (a user confirming
  "yes, this filter really has no results" via the CSV itself) for no
  safety benefit.
- **Error**: any thrown exception (network failure, non-2xx via
  `apiRequest()`'s own error-throwing convention, or a failed envelope
  shape check) sets `state.error` to a generic, translated
  (`gov.jrlist.error`) message — **never** the raw thrown message
  text — and renders it via the existing `alert alert-danger`
  convention. Loading is unconditionally set back to `false` before
  every render call on both the success and failure paths.

## 11. Response Validation

**`govIsWellFormedJointRevisionQueryEnvelope()`** — checks `items` is
an array (of well-formed items, reusing
`govIsWellFormedJointRevisionListItem()` unchanged), and that
`total`/`page`/`page_size`/`total_pages` are all `Number.isInteger`.
An invalid shape never reaches the table renderer — it is treated
identically to a thrown network error (generic translated message,
loading cleared). Note: the guard checks *integer-ness*, not
*non-negativity* — range validation is deliberately left to the
backend (already covered by Stage 1/2's own `422` tests), matching
the "no second independent business rule" contract; this is
explicitly pinned by a dedicated harness test rather than left
implicit.

## 12. Accessibility

Every new form control has an associated `<label class="form-label">`
(matching the existing card's own convention). Buttons carry
translated, human-readable text (never a raw technical value).
Disabled state is applied via the native `disabled` attribute
(`govRenderJointRevisionQueryControlsState()`), not a CSS-only visual
cue. Pagination always shows the current page number explicitly
(`"Page X of Y"`), never only relative arrows. An out-of-range page
never crashes the UI: the render function operates purely on whatever
`items`/`total`/`page`/`total_pages` the state currently holds, with
no assumption that `page <= total_pages`.

## 13. i18n Keys Added

**24 new keys**, added identically to both `en` and `tr` blocks (full
parity verified): `gov.jrlist.query_section_sub`, `searchLabel`,
`searchPlaceholder`, `searchButton`, `clearButton`, `sortBy`,
`sortOrder`, `ascending`, `descending`, `pageSize`, `previous`, `next`,
`results`, `pageOf`, `exportCsv`, `exporting`, `loading`, `empty`,
`error`, `export_error`, `sortJointRevisionId`, `sortSourceStatus`,
`sortCanonicalStatus`, `sortOutcome`. All 14 pre-existing
`gov.jrlist.*` keys are unchanged and unremoved.

`govReapplyLanguage()` gained one additive line calling
`govRenderJointRevisionQueryResult()` — re-renders the **already-held**
state on a language switch, exactly like every other section in this
function; no re-fetch is ever triggered by a language change (verified
by a dedicated harness test).

## 14. Frontend Test Harness

**`tests/js/run_joint_revision_list_ux_tests.js`** (new, dedicated —
Option B) — 136 assertions across state defaults, URL builders (query
+ export), state transitions, response validation, query lifecycle,
rendering, export lifecycle, event-binding markup checks, and i18n
parity. Built on the same `tests/js/harness_common.js` extraction/
DOM-stub/checker infrastructure every other harness in this repository
already uses; no real network call, no real browser, no external test
framework — pure Node + `vm`, non-zero exit on any failure.

`tests/js/run_governance_workspace_tests.js` required a **minimal,
necessary** update: extending `govReapplyLanguage()` (a function that
harness already extracts and actually *invokes* in
`testLanguageSwitchReappliesGovernanceLabels`) to call the new
`govRenderJointRevisionQueryResult()` made that pre-existing test
throw `ReferenceError` until the new symbols were added to the
harness's own `CONST_NAMES`/`FUNCTION_NAMES` extraction lists
(`govJointRevisionListState`, `govJointRevisionQueryPageLabel`,
`govRenderJointRevisionQueryControlsState`,
`govRenderJointRevisionQueryResult`). This is purely additive to that
file (3 lines) — no existing assertion, scenario, or extracted symbol
was removed or altered, and the original **160 assertions all still
pass**, confirmed after the change.

## 15. Backward Compatibility

The legacy simple list (`#gov_jrlist_joint_id` + **List** button +
`#gov-jrlist-result`, powered by `govLoadJointRevisions()` /
`govJointRevisionListBuildUrl()` / `govRenderJointRevisionList()` /
`GOV_JRLIST_LAST_RESULT`) is **completely unmodified** — same
functions, same markup, same bare-array endpoint call. The new UX
lives in its own, separate result container
(`#gov-jrlist-query-result`) and never touches the legacy path's
functions or state. `GET /api/governance/joint-revisions` (bare
array) is untouched at the backend, and the new frontend UX never
calls it.

## 16. Read-Only and Source Safety

Every new control triggers only `GET` requests (query endpoint or
export endpoint); no write/mutation call was added anywhere. No
frontend code writes to `localStorage`/`sessionStorage` for this
section's state (in-memory only). The CSV export never modifies the
fetched bytes (verified: no `.text()`/`.arrayBuffer()` call on the
blob).

## 17. Out of Scope

Backend routes/query service/CSV serializer (all three Stage 1–3
files verified byte-unchanged). Comprehensive i18n test-harness
coverage beyond what Stage 4 itself needed to prove parity (deepened
in Stage 5). Quality-gate integration of the new harness (Stage 5).
New CSS framework or general frontend refactor (none was added).

## 18. Stage 5 Boundary

Stage 5 is expected to: add `run_joint_revision_list_ux_tests.js` to
`tools/run_quality_gate.py`'s JS harness list (this Stage
deliberately left that file untouched, per the Stage 4 contract), and
deepen i18n/harness coverage as needed. This Stage's 136 assertions
and the governance harness's 160 already give Stage 5 a complete,
passing baseline to build on, not a partial one.

## 19. Test Strategy

New dedicated harness (136 assertions, see Section 14). Existing
governance harness re-verified at 160/160 after its minimal,
necessary extraction-list update. Backend regression suite for all
Stage 1–3 files (245 tests, unmodified, all passing). Full governance
suite (517, unchanged from Stage 3 baseline — no backend Python file
touched). Full pytest suite (2144, unchanged in count from Stage 3 —
one pre-existing test's hardcoded key-count constant was updated per
its own established per-phase-addition precedent, not a new test —
see the Stage 4 final report for the exact figures and file).
Canonical quality gate (6/6, `tools/run_quality_gate.py` itself
untouched).

## 20. Acceptance Criteria

- New UX additive to the existing card; legacy list/functions/state
  fully intact and unused by the new UX.
- Query endpoint used; search/sort/pagination fully server-side; no
  client-side re-filter/re-sort/re-paginate.
- Search/sort-field/sort-order/page-size changes all reset `page` to
  `1`; Previous/Next respect page-1/last-page/`total_pages===0`
  boundaries.
- Loading/empty/error states all present, using existing CSS classes
  only; loading always clears.
- Response envelope validated before use; every dynamic value
  HTML-escaped via the existing `govEsc()`.
- CSV export uses only `search`/`sort_by`/`sort_order`/`joint_id`,
  never `page`/`page_size`; deterministic filename; blob/object-URL
  lifecycle fully cleaned up; button state restored after completion.
- 24/24 EN/TR key parity; every used key resolves; language switch
  re-renders held state without a re-fetch.
- Dedicated harness (136) and existing governance harness (160) both
  pass; backend regression (245), governance suite (517), and full
  suite (2144) all pass; quality gate 6/6.
- No backend file, no `tools/run_quality_gate.py`, no VERSION/README/
  CHANGELOG changed.
