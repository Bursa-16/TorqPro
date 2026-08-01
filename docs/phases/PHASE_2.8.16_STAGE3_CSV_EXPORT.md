# Phase 2.8.16 Stage 3 — Joint Revision List UX Improvements: CSV Export

- Status: **Stage 3 complete** (CSV export only). Phase 2.8.16 as a
  whole is **not** complete — Stages 4–6 remain (frontend UX,
  frontend harness/i18n, full validation and documentation). Do not
  read this document as a phase completion report.
- Depends on:
  `docs/phases/PHASE_2.8.16_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`,
  `docs/phases/PHASE_2.8.16_STAGE2_API_CONTRACT.md`.
- Baseline: branch `feature/faz-2.8.16-joint-revision-list-ux`, HEAD
  `36e6c62` (Stage 2 commit) at the time Stage 3 work began. Working
  tree clean. Full suite 2053/2053, quality gate 6/6, governance
  workspace harness 160/160 — all reconfirmed before Stage 3 work
  began.

## 1. Stage 3 Objective

Add a read-only, deterministic, security-conscious CSV export of the
same search/sort surface Stage 2 exposed as JSON — independent of
pagination, so every filtered/sorted record is exported regardless of
how many there are.

## 2. Export Endpoint

**`GET /api/governance/joint-revisions/export.csv`** — a distinct
static path segment, cannot collide with `/joint-revisions` or
`/joint-revisions/query`. Route function:
`governance_joint_revisions_export_csv`. `POST`/`PUT`/`DELETE` all
return `405` (verified).

## 3. Query Parameters

```
joint_id:    Optional[int] = None
search:      Optional[str] = None
sort_by:     str = DEFAULT_SORT_BY   ("joint_revision_id")
sort_order:  str = DEFAULT_SORT_ORDER ("asc")
```

**No `page`/`page_size`** — export is pagination-independent by
construction. Sending them anyway is harmless: FastAPI silently
ignores query parameters a handler does not declare (no
unknown-parameter-rejection mechanism exists anywhere else in this
codebase, so none was newly introduced for this one handler); a test
proves identical response bytes with and without them, and that
neither appears in the route's OpenAPI parameter list.

## 4. Query Service Reuse

**Decision: Option C**, extended — a new, additive, unpaginated
sibling function was added to the Stage 1 module,
`query_all_joint_revision_projections`, which
`query_joint_revision_projections` (the paginated function) is
refactored to call internally for its own validate/read/search/sort
step. Option A (call the paginated function with
`page_size=MAX_PAGE_SIZE`) was rejected: `MAX_PAGE_SIZE` is `200`, and
a dataset with more than 200 matching records would then be silently
truncated — exactly the "eksik export" the Stage 0/Stage 3 contract
forbids. Option B (extract a reusable primitive) is effectively what
was done, expressed as one new public function rather than several
smaller ones, minimizing the Stage 1 file's public surface growth.

This is a **minimal, additive, behavior-preserving** change to
`backend/governance/joint_revision_query.py`:

- `query_joint_revision_projections`'s public signature, return type,
  and every documented behavior are unchanged.
- All 62 existing Stage 1 tests pass **unmodified**.
- 9 new regression tests were added to
  `tests/governance/test_joint_revision_query.py` covering the new
  function directly (unpaginated result size beyond `MAX_PAGE_SIZE`,
  search/sort/`joint_id` reuse, validate-before-read, tuple return
  type, and agreement with the paginated function's own filtered
  order).
- No search/sort/validation logic was duplicated — both public
  functions now share one implementation of that pipeline.

The new CSV module (`backend/governance/joint_revision_csv.py`) calls
only `query_all_joint_revision_projections` — never the paginated
function, never `project_joint_revisions_bulk` directly.

## 5. CSV Column Contract

Fixed order, independent of the Stage 2 JSON field order:

```
joint_revision_id, source_system, source_status, lifecycle_group,
canonical_status, outcome, safe_reason
```

Header row always present, including for an empty result (header-only
document). One data row per projection. `None` values render as an
empty string, never the literal text `"None"`. `joint_revision_id`
renders as a plain decimal string. `lifecycle_group` (an enum field)
renders via its own `.value` — the same safe string the Stage 2 JSON
API already uses for it, never a Python `repr()` or qualified enum
name. Row order matches the Stage 1/3 deterministic sort exactly (no
independent sorting in this module).

## 6. CSV Encoding and BOM

Python's standard library `csv` module is used exclusively (no manual
comma-joining); quoting is `csv.QUOTE_MINIMAL` (the module default,
left unmodified — not overridden). Line terminator is RFC 4180 `\r\n`
throughout, including after the final row.

**Single, explicit contract**: `serialize_joint_revision_projections_csv`
builds plain CSV text (`str`) internally, then encodes to UTF-8 and
prepends exactly one UTF-8 BOM (`UTF8_BOM = b"\xef\xbb\xbf"`),
returning `bytes`. This is the **only** place in the module the BOM
is added — `export_joint_revision_projections_csv` calls it exactly
once and never adds a second prefix, making a double-BOM structurally
impossible. **Decision: UTF-8 with BOM** — chosen for Excel
compatibility given TorqPro's Turkish-language content (`safe_reason`
values may contain Turkish characters); verified with a direct
Unicode round-trip test. A caller decoding with `"utf-8-sig"` (used
throughout this Stage's own tests) sees the BOM stripped
transparently; a caller decoding with plain `"utf-8"` sees a leading
`\ufeff` character, which is expected and documented here rather than
silently surprising.

`bytes` (not `str`) was chosen for both serializer functions'
contracts specifically to avoid a second encode/decode step at the
API layer — the route returns the bytes directly as the HTTP response
body.

## 7. CSV Injection Protection

Guarded fields: `source_system`, `source_status`, `lifecycle_group`,
`canonical_status`, `outcome`, `safe_reason` (every text field).
**Not** guarded: `joint_revision_id` (numeric; a formula-trigger check
on an `int` is meaningless, per the Stage 3 contract).

Trigger characters: `=`, `+`, `-`, `@`. Detection is performed **after
stripping leading whitespace** (space, tab, CR, LF, ...) from the
value — a leading tab or carriage return placed in front of a genuine
trigger character is a documented spreadsheet formula-injection
bypass technique, not a reason to skip the check; `.lstrip()` already
strips all of these, so no separate tab/CR-specific branch was
needed. When triggered, a single `'` is prepended to the **original,
unstripped** text, guarding the whole cell (any leading whitespace the
attacker included stays inside the quoted-as-text value, not
significant to Excel once the leading apostrophe forces text
interpretation). Normal text and the empty string are returned
unchanged. The guard is applied only during CSV serialization
(`_safe_csv_cell`), never mutates the source `JointRevisionProjection`
object, and has no effect on the Stage 2 JSON response (a completely
separate code path).

## 8. Empty and Source Failure Behaviour

An empty filtered result produces a header-only CSV document (never a
zero-byte body). A source read failure (verified via `monkeypatch` on
`backend.joints.service.list_joint_revisions`) flows through the same
existing, already-tested Stage 1 safe-empty-result contract
unchanged, producing a header-only CSV — never an error row, never a
leaked exception message or file path, in either the response body or
its headers. No additional `except Exception` was added anywhere in
this Stage's code.

## 9. HTTP Response Contract

```
Status: 200
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="joint-revisions-export.csv"
```

**Filename is `EXPORT_FILENAME = "joint-revisions-export.csv"`,
always this exact string** — no timestamp, no random suffix, no
`joint_id`-dependent variation (verified: identical
`Content-Disposition` header across different filter parameters). A
plain FastAPI `Response(content=bytes, media_type=..., headers=...)`
is used — the in-memory CSV is small enough that `StreamingResponse`
would add complexity with no benefit, per the Stage 0 guidance.

## 10. Read-Only Guarantees

No governance event store dependency injected (matches every other
read route in this file). No mutation of `joints`/`joint_revisions`
rows (verified via before/after row snapshot). No filesystem write —
the CSV is built entirely in memory. Two consecutive identical `GET`
requests return byte-identical bodies (idempotency verified).

## 11. Backward Compatibility

`GET /api/governance/joint-revisions` (bare array) and
`GET /api/governance/joint-revisions/query` (JSON envelope) are both
**unmodified** — re-verified by their own existing, unmodified test
suites, plus new cross-endpoint tests in this Stage's own file
proving all three routes coexist with distinct, non-interchangeable
`Content-Type`s and response shapes.

**Same documented exception as Stage 2**: the route-enumeration scope
guard in `tests/governance/test_compatibility.py`
(`test_governance_api_defines_only_the_nine_approved_write_routes_and_five_read_routes`
→ `..._six_read_routes`) was updated again, exactly per its own
established per-phase-addition precedent (Faz 2.8.13, Faz 2.8.14, Faz
2.8.16 Stage 2) — the new, approved `/joint-revisions/export.csv`
path was added to its expected set and the test renamed. No other
assertion in that file, and no other test file, required a change.

## 12. OpenAPI Contract

The route declares `response_class=Response` and an explicit
`responses={200: {"content": {"text/csv": {}}, ...}}` — without this,
FastAPI's default OpenAPI generation would advertise
`application/json` for a plain `Response`-typed handler even though
the actual response is CSV; verified directly against
`app.openapi()["paths"][...]["responses"]["200"]`, which shows
`text/csv` only (no spurious `application/json` entry). `page`/
`page_size` are confirmed absent from the route's OpenAPI parameter
list.

## 13. Out of Scope

Frontend (Stage 4). i18n keys (Stage 5). VERSION/README/CHANGELOG
(Stage 6, per the Stage 0 timing decision). Any change to the
existing bare-array or `/query` JSON endpoints.

## 14. Stage 4 Frontend Integration Boundary

Stage 4 is expected to add a "Export CSV" action to the existing
Joint Revision List UX card, triggering a browser download of
`GET /api/governance/joint-revisions/export.csv` with the current
search/sort state (never the current page/page_size, which this
endpoint does not accept) — the exact UI affordance (link vs button,
loading state) is Stage 4's own decision, not predetermined here.

## 15. Test Strategy

- `tests/governance/test_joint_revision_csv.py` — 40 tests, domain
  serializer/service only (no HTTP): header/serialization, quoting,
  CSV-injection protection, query reuse, determinism.
- `tests/governance/test_joint_revision_csv_api.py` — 42 tests,
  `TestClient`-based, mirroring
  `tests/governance/test_joint_revision_query_api.py`'s conventions:
  route/OpenAPI, headers, body, query behavior, safety, backward
  compatibility.
- 9 new regression tests added to the existing Stage 1 file for
  `query_all_joint_revision_projections` (see §4).
- `tests/governance/test_joint_revision_bulk_api.py` and
  `tests/governance/test_joint_revision_query_api.py` were **not**
  modified.

## 16. Acceptance Criteria

- HTTP-independent CSV service/serializer module created; no FastAPI
  import.
- Stage 1/3 search and sort reused with zero duplicated logic.
- Every filtered/sorted record exported, never capped at
  `MAX_PAGE_SIZE`.
- Fixed CSV column order; header always present; empty result is
  header-only; no field ever renders as the literal text `"None"`.
- CSV quoting via the standard library `csv` module only; RFC 4180
  `\r\n`; Unicode preserved.
- UTF-8 with a single BOM; CSV-injection guard on every text field,
  never on `joint_revision_id`; original projection never mutated.
- New additive `GET` endpoint; correct `Content-Type`/
  `Content-Disposition`; deterministic filename.
- Domain validation mapped to HTTP `422`; source failure produces a
  safe header-only `200`, never a leak.
- Existing bare-array and `/query` endpoints unmodified.
- New tests, governance suite, full suite, quality gate, and JS
  harness all pass — see the Stage 3 final report for exact figures.
