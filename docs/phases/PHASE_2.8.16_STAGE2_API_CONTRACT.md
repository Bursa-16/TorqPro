# Phase 2.8.16 Stage 2 — Joint Revision List UX Improvements: Additive API Contract

- Status: **Stage 2 complete** (additive API endpoint only). Phase
  2.8.16 as a whole is **not** complete — Stages 3–6 remain (CSV
  export, frontend UX, frontend harness/i18n, full validation and
  documentation). Do not read this document as a phase completion
  report.
- Depends on:
  `docs/phases/PHASE_2.8.16_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`,
  `docs/phases/PHASE_2.8.14_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md`.
- Baseline: branch `feature/faz-2.8.16-joint-revision-list-ux`, HEAD
  `09d1569` (Stage 1 commit) at the time Stage 2 work began. Working
  tree clean. Full suite 1981/1981, quality gate 6/6, governance
  workspace harness 160/160 — all reconfirmed before Stage 2 work
  began.

## 1. Stage 2 Objective

Expose the Stage 1 domain query service
(`query_joint_revision_projections`) through a new, additive,
read-only HTTP endpoint with a typed pagination envelope — without
modifying the existing bare-array `GET /api/governance/joint-revisions`
endpoint in any way.

## 2. Endpoint Path and Method

**`GET /api/governance/joint-revisions/query`** — the Stage 0-default
path. Chosen over `/joint-revisions/search` and
`/joint-revision-query`: it is a distinct static path segment
appended to the existing plural resource path (mirrors the
established convention of `/joint-revision/{revision_id}` vs
`/joint-revisions` — a static-segment suffix, not a path parameter),
cannot collide with either existing route under Starlette's exact
literal-segment matching, and reads naturally as "the query view of
the joint-revisions resource." No path parameter is used. `POST`,
`PUT`, `DELETE` all return `405` (verified).

## 3. Query Parameters

```
joint_id:    Optional[int] = None
search:      Optional[str] = None
sort_by:     str = "joint_revision_id"   (DEFAULT_SORT_BY)
sort_order:  str = "asc"                 (DEFAULT_SORT_ORDER)
page:        int = Query(default=1, ge=1)
page_size:   int = Query(default=25, ge=1, le=200)  (MAX_PAGE_SIZE)
```

Every parameter is passed straight through to
`query_joint_revision_projections` — no search/sort/pagination logic
is duplicated in the route handler, and the `sort_by`/`sort_order`
allow-lists are not redefined at the API layer.

Two independent, intentional validation layers:

- `page`/`page_size` use FastAPI's own `Query(ge=..., le=...)` — an
  out-of-range value is rejected by FastAPI itself (its own `422`
  body shape, a structured `detail` list), before the handler body
  or the Stage 1 service ever runs.
- `sort_by`/`sort_order` carry no FastAPI-level constraint (per
  Stage 1's "single source of truth" contract); an invalid value
  reaches the service, which raises
  `JointRevisionQueryValidationError`, mapped to `HTTPException(422, str(exc))`
  (a plain string `detail`).

`test_fastapi_level_422_differs_in_shape_from_domain_422` proves both
paths return `422` but with observably different `detail` shapes
(list vs string) — this is intentional, not a defect: the two layers
never disagree on the status code, only on which layer caught the
problem.

## 4. Response Envelope

```json
{
  "items": [ { "source_system": "...", "joint_revision_id": 0, "source_status": null,
               "lifecycle_group": null, "canonical_status": null,
               "outcome": "...", "safe_reason": null } ],
  "total": 0, "page": 1, "page_size": 25, "total_pages": 0
}
```

**Option A** (Stage 0's recommendation) was used: `JointRevisionQueryResult`
(Stage 1's own Pydantic model) is used directly as
`response_model=JointRevisionQueryResult` — no separate API-layer
response model, no manual field mapping, no drift risk. All seven
existing `JointRevisionProjection` fields are preserved unchanged
inside `items`; no field was renamed and no field was added.

## 5. Validation and HTTP 422 Mapping

`except JointRevisionQueryValidationError as exc: raise HTTPException(422, str(exc))`
— the single line doing the mapping, placed in the route handler
itself, mirroring this file's existing `_run_command` convention
(`except SomeError as exc: raise HTTPException(422, str(exc))`,
already used by every write route in this module). No new global
exception-handler framework was introduced. The message is
deterministic, contains no file path or traceback, and safely
echoes only the parameter name/value/reason
`JointRevisionQueryValidationError.__str__` already produces.

## 6. Source Failure Behaviour

Unchanged from Stage 1: `project_joint_revisions_bulk` never raises
on a source read failure — it returns `[]`, which flows through
`query_joint_revision_projections` unchanged as
`items=(), total=0, total_pages=0`. The route adds no additional
`try/except` around this case (only around
`JointRevisionQueryValidationError`, per §5), matching the existing
bulk route's own "no defensive `except Exception`" convention.
Verified end-to-end via `monkeypatch` on
`backend.joints.service.list_joint_revisions`: `200`, the exact empty
envelope shown in §4, no leaked path/exception text.

## 7. Read-Only Guarantees

No governance event store dependency is injected (like the existing
bulk route, and unlike every write route in this module) — the
handler has no reference to any event store, so it structurally
cannot write one. No mutation of `joints`/`joint_revisions` rows
(verified by before/after row snapshot). Two consecutive identical
`GET` requests return byte-identical JSON (idempotency verified).

## 8. Backward Compatibility

`backend/governance/api.py`'s existing
`governance_joint_revisions_bulk` function signature is **unchanged**
— zero new parameters, zero behavior change. Re-verified with the
existing, unmodified `tests/governance/test_joint_revision_bulk_api.py`
suite (all passing) plus new, dedicated regression tests in this
Stage's own file: bare-array response type preserved, no envelope
metadata leaks into existing items, ascending-id default order
preserved, and the existing route's OpenAPI parameter set is still
exactly `{joint_id}` at the query-parameter level.

**One pre-existing test required an update, not a weakening**:
`tests/governance/test_compatibility.py::test_governance_api_defines_only_the_nine_approved_write_routes_and_four_read_routes`
is a route-enumeration scope guard that has been extended once per
prior phase that added an approved route (Faz 2.8.13 Stage 2, Faz
2.8.14 Stage 3) — by design, not by oversight, this guard fails
whenever *any* new route is added, approved or not, so that an
unapproved route addition is always caught. Since this phase's new
route *is* approved (Stage 0/Stage 2 scope), the guard was updated
to include `/api/governance/joint-revisions/query` in its expected
set and renamed
(`..._four_read_routes` → `..._five_read_routes`), exactly mirroring
the prior two phases' own precedent for the same test. No other
assertion in the test suite required a change; no test was weakened.

## 9. OpenAPI Contract

`GET /api/governance/joint-revisions/query` appears in
`app.openapi()["paths"]` with only a `get` operation (`post` absent).
Response schema exposes `items`/`total`/`page`/`page_size`/`total_pages`;
`items`' element schema exposes all seven existing projection fields.
The route's own docstring (used as the OpenAPI description) states:
read-only, additive alternative to the bare-array endpoint; supports
search/sort/pagination; never mutates.

## 10. Stage 1 Service Reuse

The route imports `DEFAULT_PAGE`, `DEFAULT_PAGE_SIZE`, `DEFAULT_SORT_BY`,
`DEFAULT_SORT_ORDER`, `MAX_PAGE_SIZE`, `JointRevisionQueryResult`,
`JointRevisionQueryValidationError`, and
`query_joint_revision_projections` from
`backend.governance.joint_revision_query` — no constant, allow-list,
or default value is redefined at the API layer.
`backend/governance/joint_revision_query.py` was **not** modified.

## 11. Out of Scope

CSV export (Stage 3). Frontend (Stage 4). i18n keys (Stage 5).
VERSION/README/CHANGELOG (Stage 6, per the Stage 0 timing decision).
Any change to the existing bare-array endpoint's signature, response
shape, or ordering.

## 12. Stage 3 Export Integration Boundary

Stage 3's CSV export is expected to reuse
`query_joint_revision_projections` directly (same search/sort
filters, but independent of pagination — exporting all filtered
records per the Stage 0 CSV contract), not this Stage's HTTP route.
Whether Stage 3 adds its own new route or is served from a query
parameter on this route is an open decision for Stage 3, not
predetermined here.

## 13. Test Strategy

`tests/governance/test_joint_revision_query_api.py` — `TestClient` +
shared `client`/`auth_headers` fixtures (`tests/conftest.py`), same
joint/revision fixture pattern as `test_joint_revision_bulk_api.py`.
Tests the observable HTTP contract only; does not re-test Stage 1's
own search/sort/pagination correctness (already covered by
`tests/governance/test_joint_revision_query.py`). 72 new tests;
`tests/governance/test_joint_revision_bulk_api.py` was not modified.

## 14. Acceptance Criteria

- New additive `GET` endpoint exists at the documented path.
- Existing bare-array endpoint unmodified (signature, response,
  ordering, OpenAPI contract).
- Typed envelope response; no field renamed or added beyond the
  documented five envelope keys plus the seven existing projection
  fields.
- Stage 1 service reused with zero duplicated search/sort/pagination
  logic.
- FastAPI-level and domain-level `422` both function and are
  observably distinguishable.
- Source failure produces a safe empty envelope, no leak.
- No mutation, no governance event.
- New tests, governance suite, full suite, quality gate, and JS
  harness all pass — see the Stage 2 final report for exact figures.
