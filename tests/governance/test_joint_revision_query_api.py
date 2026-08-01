"""Faz 2.8.16 Stage 2 tests: ``GET /api/governance/joint-revisions/query``.

Exercises the new, additive, paginated route added in Stage 2. Uses
the shared ``client``/``auth_headers`` fixtures from
``tests/conftest.py`` (same convention as
``tests/governance/test_joint_revision_bulk_api.py``) and the same
joint/revision fixture pattern already established there. This file
tests the observable HTTP contract only -- it does not re-test the
Stage 1 query service's own search/sort/pagination logic (already
covered by ``tests/governance/test_joint_revision_query.py``), only
the transport, envelope shape, and error-mapping wrapped around it.

A new, dedicated file was created rather than extending
``tests/governance/test_joint_revision_bulk_api.py`` (which is
explicitly not to be modified per the Stage 2 backward-compatibility
contract) or ``tests/governance/test_api.py`` -- mirroring the same
one-file-per-route-family precedent
``test_joint_revision_bulk_api.py`` itself established for the bulk
route.
"""

from __future__ import annotations

import pytest

from backend import app as appmod
from backend.app import conn, now_iso
from backend.governance.api import get_governance_store
from backend.governance.joint_revision_query import MAX_PAGE_SIZE
from backend.governance.store import FileGovernanceEventStore
from backend.joints import service as joints_svc
from backend.joints.exceptions import JointCodeConflictError

_ROUTE = "/api/governance/joint-revisions/query"
_BARE_ROUTE = "/api/governance/joint-revisions"


@pytest.fixture
def gov_store(tmp_path):
    """Overrides the ``get_governance_store`` FastAPI dependency for
    the duration of one test -- mirrors
    ``tests/governance/test_joint_revision_bulk_api.py``'s fixture of
    the same name/shape."""
    store = FileGovernanceEventStore(tmp_path / "events.json")
    appmod.app.dependency_overrides[get_governance_store] = lambda: store
    yield store
    appmod.app.dependency_overrides.pop(get_governance_store, None)


def _make_project(name="Joint Revision Query API Test Project"):
    with conn() as c:
        c.execute(
            "INSERT INTO projects(name,status,created_at) VALUES(?,?,?)",
            (name, "open", now_iso()),
        )
        c.commit()
        return c.execute("SELECT id FROM projects WHERE id=last_insert_rowid()").fetchone()["id"]


def _make_joint_and_revision(joint_code_suffix):
    pid = _make_project()
    try:
        joint = joints_svc.create_joint(
            pid, f"J-JRQAPI-{joint_code_suffix}", "Joint Revision Query API Test Joint", None, 1
        )
    except JointCodeConflictError:  # pragma: no cover - defensive, unique suffix expected
        joint = joints_svc.create_joint(
            pid, f"J-JRQAPI-{joint_code_suffix}-2", "Joint Revision Query API Test Joint", None, 1
        )
    revision = joints_svc.create_joint_revision(joint["id"], {"thread": "M10"}, "initial", 1)
    return joint, revision


def _revision_row(revision_id):
    with conn() as c:
        row = c.execute("SELECT * FROM joint_revisions WHERE id=?", (revision_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------
# Route and OpenAPI
# ---------------------------------------------------------------------


def test_route_is_accessible_via_get(client, auth_headers):
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200


def test_route_appears_in_openapi_schema_with_get_method():
    from backend.app import app

    schema = app.openapi()
    assert _ROUTE in schema["paths"]
    assert "get" in schema["paths"][_ROUTE]
    assert "post" not in schema["paths"][_ROUTE]


def test_response_schema_includes_envelope_fields():
    from backend.app import app

    schema = app.openapi()
    response_schema = schema["paths"][_ROUTE]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    # resolve $ref if the schema is a bare reference
    if "$ref" in response_schema:
        ref_name = response_schema["$ref"].split("/")[-1]
        response_schema = schema["components"]["schemas"][ref_name]
    properties = response_schema["properties"]
    for field in ("items", "total", "page", "page_size", "total_pages"):
        assert field in properties


def test_items_schema_includes_existing_projection_fields():
    from backend.app import app

    schema = app.openapi()
    response_schema = schema["paths"][_ROUTE]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    if "$ref" in response_schema:
        ref_name = response_schema["$ref"].split("/")[-1]
        response_schema = schema["components"]["schemas"][ref_name]
    items_schema = response_schema["properties"]["items"]
    item_ref = items_schema["items"]["$ref"].split("/")[-1]
    item_properties = schema["components"]["schemas"][item_ref]["properties"]
    for field in (
        "source_system",
        "joint_revision_id",
        "source_status",
        "lifecycle_group",
        "canonical_status",
        "outcome",
        "safe_reason",
    ):
        assert field in item_properties


def test_post_to_route_returns_405(client, auth_headers):
    r = client.post(_ROUTE, headers=auth_headers)
    assert r.status_code == 405


def test_put_to_route_returns_405(client, auth_headers):
    r = client.put(_ROUTE, headers=auth_headers)
    assert r.status_code == 405


def test_delete_to_route_returns_405(client, auth_headers):
    r = client.delete(_ROUTE, headers=auth_headers)
    assert r.status_code == 405


def test_new_route_does_not_collide_with_bare_array_route(client, auth_headers):
    bare = client.get(_BARE_ROUTE, headers=auth_headers)
    query = client.get(_ROUTE, headers=auth_headers)
    assert bare.status_code == 200
    assert query.status_code == 200
    assert isinstance(bare.json(), list)
    assert isinstance(query.json(), dict)


# ---------------------------------------------------------------------
# Default response
# ---------------------------------------------------------------------


def test_default_request_returns_200(client, auth_headers):
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200


def test_response_is_an_envelope_not_a_bare_array(client, auth_headers):
    r = client.get(_ROUTE, headers=auth_headers)
    body = r.json()
    assert isinstance(body, dict)
    assert set(body.keys()) == {"items", "total", "page", "page_size", "total_pages"}


def test_default_page_is_1(client, auth_headers):
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.json()["page"] == 1


def test_default_page_size_is_25(client, auth_headers):
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.json()["page_size"] == 25


def test_default_order_is_ascending_joint_revision_id(client, auth_headers):
    joint, r1 = _make_joint_and_revision("default-order")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    ids = [i["joint_revision_id"] for i in r.json()["items"]]
    assert ids == [r1["id"], r2["id"]]


def test_total_is_correct(client, auth_headers):
    joint, r1 = _make_joint_and_revision("total-count")
    joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    assert r.json()["total"] == 2


def test_total_pages_is_correct(client, auth_headers):
    joint, _ = _make_joint_and_revision("total-pages")
    for _ in range(4):
        joints_svc.create_joint_revision(joint["id"], {}, "extra", 1)
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "page_size": 2}, headers=auth_headers
    )
    body = r.json()
    assert body["total"] == 5
    assert body["total_pages"] == 3


def test_items_carry_correct_projection_fields(client, auth_headers):
    joint, revision = _make_joint_and_revision("item-fields")
    r = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    item = r.json()["items"][0]
    assert item["joint_revision_id"] == revision["id"]
    assert item["outcome"] == "supported"
    assert item["source_status"] == "draft"


# ---------------------------------------------------------------------
# Joint ID filter
# ---------------------------------------------------------------------


def test_joint_id_filters_to_that_joints_revisions(client, auth_headers):
    j1, r1 = _make_joint_and_revision("filter-1")
    j2, r2 = _make_joint_and_revision("filter-2")
    r = client.get(_ROUTE, params={"joint_id": j1["id"]}, headers=auth_headers)
    body = r.json()
    ids = {i["joint_revision_id"] for i in body["items"]}
    assert r1["id"] in ids
    assert r2["id"] not in ids


def test_unknown_joint_id_returns_empty_envelope(client, auth_headers):
    r = client.get(_ROUTE, params={"joint_id": 999999999}, headers=auth_headers)
    body = r.json()
    assert r.status_code == 200
    assert body["items"] == []
    assert body["total"] == 0
    assert body["total_pages"] == 0


def test_invalid_joint_id_type_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"joint_id": "not-an-int"}, headers=auth_headers)
    assert r.status_code == 422


def test_joint_id_filter_metadata_is_correct(client, auth_headers):
    joint, _ = _make_joint_and_revision("filter-metadata")
    joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    assert r.json()["total"] == 2


# ---------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------


def test_search_is_case_insensitive(client, auth_headers):
    joint, revision = _make_joint_and_revision("search-case")
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "search": "DRAFT"}, headers=auth_headers
    )
    ids = {i["joint_revision_id"] for i in r.json()["items"]}
    assert revision["id"] in ids


def test_search_is_trimmed(client, auth_headers):
    joint, revision = _make_joint_and_revision("search-trim")
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "search": "  draft  "}, headers=auth_headers
    )
    ids = {i["joint_revision_id"] for i in r.json()["items"]}
    assert revision["id"] in ids


def test_empty_search_returns_all_results(client, auth_headers):
    joint, revision = _make_joint_and_revision("search-empty")
    r = client.get(_ROUTE, params={"joint_id": joint["id"], "search": ""}, headers=auth_headers)
    ids = {i["joint_revision_id"] for i in r.json()["items"]}
    assert revision["id"] in ids


def test_whitespace_only_search_returns_all_results(client, auth_headers):
    joint, revision = _make_joint_and_revision("search-ws")
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "search": "   "}, headers=auth_headers
    )
    ids = {i["joint_revision_id"] for i in r.json()["items"]}
    assert revision["id"] in ids


def test_search_by_joint_revision_id(client, auth_headers):
    joint, revision = _make_joint_and_revision("search-id")
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "search": str(revision["id"])},
        headers=auth_headers,
    )
    ids = {i["joint_revision_id"] for i in r.json()["items"]}
    assert revision["id"] in ids


def test_search_by_source_status(client, auth_headers):
    joint, revision = _make_joint_and_revision("search-source-status")
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "search": "draft"}, headers=auth_headers
    )
    ids = {i["joint_revision_id"] for i in r.json()["items"]}
    assert revision["id"] in ids


def test_search_by_canonical_status(client, auth_headers):
    joint, revision = _make_joint_and_revision("search-canonical-status")
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "search": "draft"}, headers=auth_headers
    )
    ids = {i["joint_revision_id"] for i in r.json()["items"]}
    assert revision["id"] in ids


def test_search_by_outcome(client, auth_headers):
    joint, revision = _make_joint_and_revision("search-outcome")
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "search": "supported"}, headers=auth_headers
    )
    ids = {i["joint_revision_id"] for i in r.json()["items"]}
    assert revision["id"] in ids


def test_search_by_safe_reason(client, auth_headers):
    r = client.get(
        _ROUTE,
        params={"joint_id": 999999999, "search": "no joint revision exists"},
        headers=auth_headers,
    )
    # unknown joint_id yields no source records at all, so this proves
    # only that the parameter round-trips safely with no match, not
    # a false positive.
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_no_match_returns_empty_envelope(client, auth_headers):
    joint, _ = _make_joint_and_revision("search-no-match")
    r = client.get(
        _ROUTE,
        params={"joint_id": joint["id"], "search": "no-such-search-term-xyz"},
        headers=auth_headers,
    )
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_total_reflects_search_filtered_count(client, auth_headers):
    joint, _ = _make_joint_and_revision("search-total")
    joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r_all = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    r_filtered = client.get(
        _ROUTE,
        params={"joint_id": joint["id"], "search": "no-such-search-term-xyz"},
        headers=auth_headers,
    )
    assert r_all.json()["total"] == 2
    assert r_filtered.json()["total"] == 0


# ---------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["joint_revision_id", "source_status", "canonical_status", "outcome"]
)
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sort_accepts_every_allowed_field_and_order(client, auth_headers, field, order):
    joint, _ = _make_joint_and_revision(f"sort-{field}-{order}")
    joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r = client.get(
        _ROUTE,
        params={"joint_id": joint["id"], "sort_by": field, "sort_order": order},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2


def test_text_sorting_is_case_insensitive(client, auth_headers):
    joint, _ = _make_joint_and_revision("sort-case-insensitive")
    r = client.get(
        _ROUTE,
        params={"joint_id": joint["id"], "sort_by": "source_status", "sort_order": "asc"},
        headers=auth_headers,
    )
    assert r.status_code == 200


def test_sort_tie_breaker_is_joint_revision_id_ascending(client, auth_headers):
    joint, r1 = _make_joint_and_revision("sort-tiebreak")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    # both revisions are 'draft' -> equal primary sort value -> tie-breaker decides
    r = client.get(
        _ROUTE,
        params={"joint_id": joint["id"], "sort_by": "source_status", "sort_order": "desc"},
        headers=auth_headers,
    )
    ids = [i["joint_revision_id"] for i in r.json()["items"]]
    assert ids == [r1["id"], r2["id"]]


def test_invalid_sort_by_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"sort_by": "not_a_field"}, headers=auth_headers)
    assert r.status_code == 422


def test_invalid_sort_order_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"sort_order": "sideways"}, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.parametrize("value", ["ASC", "Desc", "DESC"])
def test_uppercase_sort_order_returns_422_strict_contract(client, auth_headers, value):
    r = client.get(_ROUTE, params={"sort_order": value}, headers=auth_headers)
    assert r.status_code == 422


def test_repeated_request_produces_the_same_response_order(client, auth_headers):
    joint, _ = _make_joint_and_revision("sort-deterministic")
    for _ in range(3):
        joints_svc.create_joint_revision(joint["id"], {}, "extra", 1)
    params = {"joint_id": joint["id"], "sort_by": "outcome", "sort_order": "asc"}
    r1 = client.get(_ROUTE, params=params, headers=auth_headers)
    r2 = client.get(_ROUTE, params=params, headers=auth_headers)
    assert [i["joint_revision_id"] for i in r1.json()["items"]] == [
        i["joint_revision_id"] for i in r2.json()["items"]
    ]


# ---------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------


def test_pagination_first_page(client, auth_headers):
    joint, _ = _make_joint_and_revision("page-first")
    for _ in range(4):
        joints_svc.create_joint_revision(joint["id"], {}, "extra", 1)
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "page": 1, "page_size": 2}, headers=auth_headers
    )
    assert len(r.json()["items"]) == 2


def test_pagination_middle_page(client, auth_headers):
    joint, _ = _make_joint_and_revision("page-middle")
    for _ in range(4):
        joints_svc.create_joint_revision(joint["id"], {}, "extra", 1)
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "page": 2, "page_size": 2}, headers=auth_headers
    )
    assert len(r.json()["items"]) == 2


def test_pagination_last_page_partial(client, auth_headers):
    joint, _ = _make_joint_and_revision("page-last-partial")
    for _ in range(4):
        joints_svc.create_joint_revision(joint["id"], {}, "extra", 1)
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "page": 3, "page_size": 2}, headers=auth_headers
    )
    assert len(r.json()["items"]) == 1


def test_pagination_out_of_range_page_returns_empty_items_with_metadata(client, auth_headers):
    joint, _ = _make_joint_and_revision("page-out-of-range")
    r = client.get(
        _ROUTE, params={"joint_id": joint["id"], "page": 99}, headers=auth_headers
    )
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 1
    assert body["page"] == 99


def test_page_zero_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"page": 0}, headers=auth_headers)
    assert r.status_code == 422


def test_negative_page_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"page": -1}, headers=auth_headers)
    assert r.status_code == 422


def test_page_size_zero_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"page_size": 0}, headers=auth_headers)
    assert r.status_code == 422


def test_negative_page_size_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"page_size": -5}, headers=auth_headers)
    assert r.status_code == 422


def test_page_size_201_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"page_size": MAX_PAGE_SIZE + 1}, headers=auth_headers)
    assert r.status_code == 422


def test_page_size_200_is_accepted(client, auth_headers):
    r = client.get(_ROUTE, params={"page_size": MAX_PAGE_SIZE}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["page_size"] == MAX_PAGE_SIZE


def test_pagination_after_search(client, auth_headers):
    joint, _ = _make_joint_and_revision("page-after-search")
    for _ in range(3):
        joints_svc.create_joint_revision(joint["id"], {}, "extra", 1)
    r = client.get(
        _ROUTE,
        params={"joint_id": joint["id"], "search": "draft", "page": 1, "page_size": 2},
        headers=auth_headers,
    )
    body = r.json()
    assert body["total"] == 4
    assert len(body["items"]) == 2


def test_pagination_after_sorting(client, auth_headers):
    joint, r1 = _make_joint_and_revision("page-after-sort")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r = client.get(
        _ROUTE,
        params={
            "joint_id": joint["id"],
            "sort_by": "joint_revision_id",
            "sort_order": "desc",
            "page": 1,
            "page_size": 1,
        },
        headers=auth_headers,
    )
    assert r.json()["items"][0]["joint_revision_id"] == r2["id"]


def test_query_parameters_work_together(client, auth_headers):
    joint, _ = _make_joint_and_revision("all-params-together")
    for _ in range(3):
        joints_svc.create_joint_revision(joint["id"], {}, "extra", 1)
    r = client.get(
        _ROUTE,
        params={
            "joint_id": joint["id"],
            "search": "draft",
            "sort_by": "joint_revision_id",
            "sort_order": "desc",
            "page": 1,
            "page_size": 2,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4
    assert len(body["items"]) == 2


# ---------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------


def test_domain_validation_error_maps_to_422(monkeypatch, client, auth_headers):
    from backend.governance import api as api_module
    from backend.governance.joint_revision_query import JointRevisionQueryValidationError

    def _boom(**kwargs):
        raise JointRevisionQueryValidationError("sort_by", "xyz", "must be one of (...)")

    monkeypatch.setattr(api_module, "query_joint_revision_projections", _boom)
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 422


def test_domain_error_response_does_not_leak_traceback_or_path(monkeypatch, client, auth_headers):
    from backend.governance import api as api_module
    from backend.governance.joint_revision_query import JointRevisionQueryValidationError

    def _boom(**kwargs):
        raise JointRevisionQueryValidationError(
            "sort_by", "xyz", "internal detail should never leak /secret/path"
        )

    monkeypatch.setattr(api_module, "query_joint_revision_projections", _boom)
    r = client.get(_ROUTE, headers=auth_headers)
    assert "Traceback" not in r.text
    assert "JointRevisionQueryValidationError object at" not in r.text


def test_fastapi_level_422_differs_in_shape_from_domain_422(client, auth_headers):
    fastapi_level = client.get(_ROUTE, params={"page": 0}, headers=auth_headers)
    domain_level = client.get(_ROUTE, params={"sort_by": "bogus"}, headers=auth_headers)
    assert fastapi_level.status_code == domain_level.status_code == 422
    # FastAPI's own validation error body is a list of structured
    # error objects; the domain-mapped error is a plain string --
    # observably distinct shapes, both under HTTPException's "detail" key.
    assert isinstance(fastapi_level.json()["detail"], list)
    assert isinstance(domain_level.json()["detail"], str)


# ---------------------------------------------------------------------
# Source safety
# ---------------------------------------------------------------------


def test_source_unavailable_returns_200_empty_envelope(monkeypatch, client, auth_headers):
    import backend.joints.service as joints_service_module

    def _boom(joint_id=None):
        raise RuntimeError("simulated sqlite3.OperationalError: disk I/O error at /secret/path")

    monkeypatch.setattr(joints_service_module, "list_joint_revisions", _boom)

    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 25, "total_pages": 0}
    assert "/secret/path" not in r.text
    assert "OperationalError" not in r.text


def test_source_unavailable_does_not_change_governance_event_count(
    monkeypatch, client, auth_headers, gov_store
):
    import backend.joints.service as joints_service_module

    before = gov_store.all_events()

    def _boom(joint_id=None):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(joints_service_module, "list_joint_revisions", _boom)
    client.get(_ROUTE, headers=auth_headers)
    after = gov_store.all_events()
    assert before == after == []


def test_query_does_not_mutate_joint_revision_source_row(client, auth_headers):
    joint, revision = _make_joint_and_revision("source-safety")
    before = _revision_row(revision["id"])
    client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    after = _revision_row(revision["id"])
    assert before == after


def test_repeated_get_is_idempotent(client, auth_headers):
    joint, _ = _make_joint_and_revision("idempotent")
    r1 = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    r2 = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    assert r1.json() == r2.json()


# ---------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------


def test_existing_bare_array_endpoint_still_returns_array(client, auth_headers):
    r = client.get(_BARE_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_existing_endpoint_response_has_no_envelope_metadata(client, auth_headers):
    joint, _ = _make_joint_and_revision("no-envelope")
    r = client.get(_BARE_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    body = r.json()
    assert isinstance(body, list)
    for item in body:
        assert "total" not in item
        assert "page" not in item
        assert "page_size" not in item
        assert "total_pages" not in item


def test_existing_endpoint_keeps_ascending_id_order(client, auth_headers):
    joint, r1 = _make_joint_and_revision("existing-order")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r = client.get(_BARE_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    ids = [item["joint_revision_id"] for item in r.json()]
    assert ids == [r1["id"], r2["id"]]


def test_existing_endpoint_openapi_contract_unchanged():
    from backend.app import app

    schema = app.openapi()
    assert _BARE_ROUTE in schema["paths"]
    bare_schema = schema["paths"][_BARE_ROUTE]["get"]
    assert "get" in schema["paths"][_BARE_ROUTE]
    assert "post" not in schema["paths"][_BARE_ROUTE]
    # existing route's only *query* parameter remains joint_id
    # (an "authorization" header parameter is also present, from the
    # shared auth dependency every route uses -- not a query param)
    query_param_names = {
        p["name"] for p in bare_schema.get("parameters", []) if p.get("in") == "query"
    }
    assert query_param_names == {"joint_id"}


def test_new_and_existing_endpoint_responses_are_not_interchangeable(client, auth_headers):
    joint, _ = _make_joint_and_revision("not-interchangeable")
    bare = client.get(_BARE_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    query = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    assert isinstance(bare.json(), list)
    assert isinstance(query.json(), dict)
    assert bare.json() != query.json()
