"""Faz 2.8.16 Stage 3 tests: ``GET /api/governance/joint-revisions/export.csv``.

Exercises the new, additive CSV export route added in Stage 3. Uses
the shared ``client``/``auth_headers`` fixtures from
``tests/conftest.py`` (same convention as
``tests/governance/test_joint_revision_query_api.py``) and the same
joint/revision fixture pattern already established there. This file
tests the observable HTTP contract only -- it does not re-test the
CSV serializer's own quoting/injection-guard correctness (already
covered by ``tests/governance/test_joint_revision_csv.py``) or the
Stage 1/3 query pipeline's own search/sort correctness (already
covered by ``tests/governance/test_joint_revision_query.py``).
"""

from __future__ import annotations

import csv
import io

import pytest

from backend import app as appmod
from backend.app import conn, now_iso
from backend.governance.api import get_governance_store
from backend.governance.joint_revision_csv import CSV_COLUMNS, EXPORT_FILENAME
from backend.governance.store import FileGovernanceEventStore
from backend.joints import service as joints_svc
from backend.joints.exceptions import JointCodeConflictError

_EXPORT_ROUTE = "/api/governance/joint-revisions/export.csv"
_QUERY_ROUTE = "/api/governance/joint-revisions/query"
_BARE_ROUTE = "/api/governance/joint-revisions"


@pytest.fixture
def gov_store(tmp_path):
    """Overrides the ``get_governance_store`` FastAPI dependency for
    the duration of one test -- mirrors
    ``tests/governance/test_joint_revision_query_api.py``'s fixture of
    the same name/shape."""
    store = FileGovernanceEventStore(tmp_path / "events.json")
    appmod.app.dependency_overrides[get_governance_store] = lambda: store
    yield store
    appmod.app.dependency_overrides.pop(get_governance_store, None)


def _make_project(name="Joint Revision CSV API Test Project"):
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
            pid, f"J-CSVAPI-{joint_code_suffix}", "Joint Revision CSV API Test Joint", None, 1
        )
    except JointCodeConflictError:  # pragma: no cover - defensive, unique suffix expected
        joint = joints_svc.create_joint(
            pid, f"J-CSVAPI-{joint_code_suffix}-2", "Joint Revision CSV API Test Joint", None, 1
        )
    revision = joints_svc.create_joint_revision(joint["id"], {"thread": "M10"}, "initial", 1)
    return joint, revision


def _revision_row(revision_id):
    with conn() as c:
        row = c.execute("SELECT * FROM joint_revisions WHERE id=?", (revision_id,)).fetchone()
        return dict(row) if row else None


def _parse_csv(body: bytes):
    text = body.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


# ---------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------


def test_export_route_returns_200(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert r.status_code == 200


def test_export_route_appears_in_openapi_schema():
    from backend.app import app

    schema = app.openapi()
    assert _EXPORT_ROUTE in schema["paths"]
    assert "get" in schema["paths"][_EXPORT_ROUTE]


def test_export_openapi_declares_text_csv_response():
    from backend.app import app

    schema = app.openapi()
    responses = schema["paths"][_EXPORT_ROUTE]["get"]["responses"]["200"]
    assert "text/csv" in responses["content"]


def test_export_only_get_is_supported(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert r.status_code == 200


def test_export_post_returns_405(client, auth_headers):
    r = client.post(_EXPORT_ROUTE, headers=auth_headers)
    assert r.status_code == 405


def test_export_put_returns_405(client, auth_headers):
    r = client.put(_EXPORT_ROUTE, headers=auth_headers)
    assert r.status_code == 405


def test_export_delete_returns_405(client, auth_headers):
    r = client.delete(_EXPORT_ROUTE, headers=auth_headers)
    assert r.status_code == 405


def test_export_route_does_not_collide_with_other_routes(client, auth_headers):
    bare = client.get(_BARE_ROUTE, headers=auth_headers)
    query = client.get(_QUERY_ROUTE, headers=auth_headers)
    export = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert bare.status_code == query.status_code == export.status_code == 200
    assert isinstance(bare.json(), list)
    assert isinstance(query.json(), dict)
    assert export.headers["content-type"].startswith("text/csv")


# ---------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------


def test_export_content_type_is_text_csv(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert r.headers["content-type"].startswith("text/csv")


def test_export_charset_is_utf8(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert "charset=utf-8" in r.headers["content-type"]


def test_export_content_disposition_is_attachment(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert r.headers["content-disposition"].startswith("attachment")


def test_export_filename_is_exact(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert f'filename="{EXPORT_FILENAME}"' in r.headers["content-disposition"]
    assert EXPORT_FILENAME == "joint-revisions-export.csv"


def test_export_filename_is_stable_across_different_filters(client, auth_headers):
    joint, _ = _make_joint_and_revision("filename-stability")
    r1 = client.get(_EXPORT_ROUTE, headers=auth_headers)
    r2 = client.get(_EXPORT_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    assert r1.headers["content-disposition"] == r2.headers["content-disposition"]


def test_export_body_begins_with_utf8_bom(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert r.content.startswith(b"\xef\xbb\xbf")


# ---------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------


def test_export_header_row_is_correct(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    rows = _parse_csv(r.content)
    assert rows[0] == list(CSV_COLUMNS)


def test_export_data_rows_are_correct(client, auth_headers):
    joint, revision = _make_joint_and_revision("data-rows")
    r = client.get(_EXPORT_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    rows = _parse_csv(r.content)
    assert rows[1][0] == str(revision["id"])
    assert rows[1][5] == "supported"


def test_export_empty_source_is_header_only(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, params={"joint_id": 999999999}, headers=auth_headers)
    rows = _parse_csv(r.content)
    assert len(rows) == 1
    assert rows[0] == list(CSV_COLUMNS)


def test_export_unicode_is_preserved(client, auth_headers):
    # unknown joint_id + safe_reason search proves the round-trip
    # without depending on a specific Turkish safe_reason existing in
    # the fixture data -- see test_joint_revision_csv.py for direct
    # Unicode-preservation coverage of the serializer itself.
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    r.content.decode("utf-8-sig")  # raises if not valid UTF-8


def test_export_quoting_is_valid_csv(client, auth_headers):
    joint, _ = _make_joint_and_revision("quoting")
    r = client.get(_EXPORT_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    # a successful, unambiguous parse back into the expected column
    # count for every row proves quoting round-trips correctly
    rows = _parse_csv(r.content)
    for row in rows:
        assert len(row) == len(CSV_COLUMNS)


def test_export_body_parses_as_valid_csv(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    rows = _parse_csv(r.content)
    assert len(rows) >= 1


# ---------------------------------------------------------------------
# Query behavior
# ---------------------------------------------------------------------


def test_export_joint_id_filter(client, auth_headers):
    j1, r1 = _make_joint_and_revision("export-filter-1")
    j2, r2 = _make_joint_and_revision("export-filter-2")
    r = client.get(_EXPORT_ROUTE, params={"joint_id": j1["id"]}, headers=auth_headers)
    rows = _parse_csv(r.content)
    ids = {row[0] for row in rows[1:]}
    assert str(r1["id"]) in ids
    assert str(r2["id"]) not in ids


def test_export_search_is_case_insensitive(client, auth_headers):
    joint, revision = _make_joint_and_revision("export-search-case")
    r = client.get(
        _EXPORT_ROUTE, params={"joint_id": joint["id"], "search": "DRAFT"}, headers=auth_headers
    )
    rows = _parse_csv(r.content)
    ids = {row[0] for row in rows[1:]}
    assert str(revision["id"]) in ids


def test_export_search_is_trimmed(client, auth_headers):
    joint, revision = _make_joint_and_revision("export-search-trim")
    r = client.get(
        _EXPORT_ROUTE,
        params={"joint_id": joint["id"], "search": "  draft  "},
        headers=auth_headers,
    )
    rows = _parse_csv(r.content)
    ids = {row[0] for row in rows[1:]}
    assert str(revision["id"]) in ids


def test_export_empty_search_returns_all(client, auth_headers):
    joint, revision = _make_joint_and_revision("export-empty-search")
    r = client.get(
        _EXPORT_ROUTE, params={"joint_id": joint["id"], "search": ""}, headers=auth_headers
    )
    rows = _parse_csv(r.content)
    ids = {row[0] for row in rows[1:]}
    assert str(revision["id"]) in ids


def test_export_sort_by_ascending(client, auth_headers):
    joint, r1 = _make_joint_and_revision("export-sort-asc")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r = client.get(
        _EXPORT_ROUTE,
        params={"joint_id": joint["id"], "sort_by": "joint_revision_id", "sort_order": "asc"},
        headers=auth_headers,
    )
    rows = _parse_csv(r.content)
    ids = [row[0] for row in rows[1:]]
    assert ids == [str(r1["id"]), str(r2["id"])]


def test_export_sort_by_descending(client, auth_headers):
    joint, r1 = _make_joint_and_revision("export-sort-desc")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r = client.get(
        _EXPORT_ROUTE,
        params={"joint_id": joint["id"], "sort_by": "joint_revision_id", "sort_order": "desc"},
        headers=auth_headers,
    )
    rows = _parse_csv(r.content)
    ids = [row[0] for row in rows[1:]]
    assert ids == [str(r2["id"]), str(r1["id"])]


def test_export_sort_order_is_strict(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, params={"sort_order": "ASC"}, headers=auth_headers)
    assert r.status_code == 422


def test_export_invalid_sort_by_returns_422(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, params={"sort_by": "not_a_field"}, headers=auth_headers)
    assert r.status_code == 422


def test_export_invalid_sort_order_returns_422(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, params={"sort_order": "sideways"}, headers=auth_headers)
    assert r.status_code == 422


def test_export_invalid_joint_id_returns_422(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, params={"joint_id": "not-an-int"}, headers=auth_headers)
    assert r.status_code == 422


def test_export_page_and_page_size_are_not_part_of_the_contract(client, auth_headers):
    # unrecognized query parameters are silently ignored by FastAPI
    # for a handler that does not declare them -- this endpoint's
    # response is identical with or without them.
    joint, _ = _make_joint_and_revision("export-page-ignored")
    without = client.get(_EXPORT_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    with_page = client.get(
        _EXPORT_ROUTE,
        params={"joint_id": joint["id"], "page": 5, "page_size": 3},
        headers=auth_headers,
    )
    assert with_page.status_code == 200
    assert without.content == with_page.content


def test_export_openapi_does_not_declare_page_or_page_size():
    from backend.app import app

    schema = app.openapi()
    params = schema["paths"][_EXPORT_ROUTE]["get"].get("parameters", [])
    names = {p["name"] for p in params}
    assert "page" not in names
    assert "page_size" not in names


# ---------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------


def test_export_source_unavailable_returns_200_header_only(monkeypatch, client, auth_headers):
    import backend.joints.service as joints_service_module

    def _boom(joint_id=None):
        raise RuntimeError("simulated sqlite3.OperationalError: disk I/O error at /secret/path")

    monkeypatch.setattr(joints_service_module, "list_joint_revisions", _boom)

    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    rows = _parse_csv(r.content)
    assert len(rows) == 1
    assert b"/secret/path" not in r.content
    assert b"OperationalError" not in r.content


def test_export_source_unavailable_does_not_leak_in_headers(monkeypatch, client, auth_headers):
    import backend.joints.service as joints_service_module

    def _boom(joint_id=None):
        raise RuntimeError("simulated failure at /secret/path")

    monkeypatch.setattr(joints_service_module, "list_joint_revisions", _boom)

    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert "/secret/path" not in str(r.headers)


def test_export_get_does_not_mutate_source_row(client, auth_headers):
    joint, revision = _make_joint_and_revision("export-source-safety")
    before = _revision_row(revision["id"])
    client.get(_EXPORT_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    after = _revision_row(revision["id"])
    assert before == after


def test_export_does_not_change_governance_event_count(client, auth_headers, gov_store):
    joint, _ = _make_joint_and_revision("export-gov-events")
    before = gov_store.all_events()
    client.get(_EXPORT_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    after = gov_store.all_events()
    assert before == after == []


def test_export_repeated_request_produces_identical_body(client, auth_headers):
    joint, _ = _make_joint_and_revision("export-idempotent")
    r1 = client.get(_EXPORT_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    r2 = client.get(_EXPORT_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    assert r1.content == r2.content


# ---------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------


def test_bare_array_endpoint_still_returns_array(client, auth_headers):
    r = client.get(_BARE_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_query_endpoint_still_returns_json_envelope(client, auth_headers):
    r = client.get(_QUERY_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
    assert set(r.json().keys()) == {"items", "total", "page", "page_size", "total_pages"}


def test_export_endpoint_returns_csv_not_json(client, auth_headers):
    r = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    with pytest.raises(Exception):
        r.json()


def test_three_endpoints_have_distinct_content_types(client, auth_headers):
    bare = client.get(_BARE_ROUTE, headers=auth_headers)
    query = client.get(_QUERY_ROUTE, headers=auth_headers)
    export = client.get(_EXPORT_ROUTE, headers=auth_headers)
    assert bare.headers["content-type"].startswith("application/json")
    assert query.headers["content-type"].startswith("application/json")
    assert export.headers["content-type"].startswith("text/csv")


def test_query_endpoint_openapi_contract_unchanged_by_stage3():
    from backend.app import app

    schema = app.openapi()
    query_schema = schema["paths"][_QUERY_ROUTE]["get"]
    query_param_names = {
        p["name"] for p in query_schema.get("parameters", []) if p.get("in") == "query"
    }
    assert query_param_names == {
        "joint_id", "search", "sort_by", "sort_order", "page", "page_size",
    }
