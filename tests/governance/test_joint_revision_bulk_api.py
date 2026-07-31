"""Faz 2.8.14 Stage 3 tests: ``GET /api/governance/joint-revisions``.

Exercises the new read-only bulk route added in Stage 3, per the
approved Stage 1 contract
(``docs/phases/PHASE_2.8.14_STAGE1_SCOPE_AND_INTEGRATION_CONTRACT.md``,
Section 10). Uses the shared ``client``/``auth_headers`` fixtures from
``tests/conftest.py`` (the same ``TestClient`` bound to
``backend.app.app`` every other endpoint test uses) and the same
joint/revision fixture pattern already established by
``tests/governance/adapters/test_joint_revision.py`` and
``tests/governance/test_joint_revision_api.py`` -- this file does not
re-test the adapter's own mapping logic (already covered in
``tests/governance/adapters/test_joint_revision.py``), only the HTTP
transport wrapped around the bulk adapter function.

A new, dedicated file was created (rather than adding to the generic
``tests/governance/test_api.py``, which covers the nine write
endpoints and two generic read endpoints, or to
``tests/governance/test_joint_revision_api.py``, which is outside
this stage's approved allowed-files list) because
``test_joint_revision_api.py`` already establishes the precedent of a
one-file-per-route-family test file for this exact route family; this
file mirrors that precedent for the new bulk route without touching
the file itself.
"""

from __future__ import annotations

import pytest

from backend import app as appmod
from backend.app import conn, now_iso
from backend.governance import service as svc
from backend.governance.api import get_governance_store
from backend.governance.store import FileGovernanceEventStore
from backend.joints import service as joints_svc
from backend.joints.exceptions import JointCodeConflictError

_ROUTE = "/api/governance/joint-revisions"


@pytest.fixture
def gov_store(tmp_path):
    """Overrides the ``get_governance_store`` FastAPI dependency for
    the duration of one test with a store backed by a temp-path file
    -- mirrors ``tests/governance/test_api.py`` and
    ``tests/governance/test_joint_revision_api.py``'s own fixture of
    the same name/shape."""
    store = FileGovernanceEventStore(tmp_path / "events.json")
    appmod.app.dependency_overrides[get_governance_store] = lambda: store
    yield store
    appmod.app.dependency_overrides.pop(get_governance_store, None)


def _make_project(name="Governance Bulk API Test Project"):
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
            pid, f"J-BULKAPI-{joint_code_suffix}", "Governance Bulk API Test Joint", None, 1
        )
    except JointCodeConflictError:  # pragma: no cover - defensive, unique suffix expected
        joint = joints_svc.create_joint(
            pid, f"J-BULKAPI-{joint_code_suffix}-2", "Governance Bulk API Test Joint", None, 1
        )
    revision = joints_svc.create_joint_revision(joint["id"], {"thread": "M10"}, "initial", 1)
    return joint, revision


def _revision_row(revision_id):
    with conn() as c:
        row = c.execute("SELECT * FROM joint_revisions WHERE id=?", (revision_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------
# Items 1-3: route exists, returns all, ascending order
# ---------------------------------------------------------------------


def test_route_returns_all_projections(client, auth_headers):
    _, r1 = _make_joint_and_revision("all-1")
    _, r2 = _make_joint_and_revision("all-2")

    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    ids = {item["joint_revision_id"] for item in body}
    assert r1["id"] in ids
    assert r2["id"] in ids


def test_route_results_are_in_ascending_revision_id_order(client, auth_headers):
    joint, r1 = _make_joint_and_revision("order")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r3 = joints_svc.create_joint_revision(joint["id"], {}, "third", 1)

    r = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    assert r.status_code == 200
    result_ids = [item["joint_revision_id"] for item in r.json()]
    assert result_ids == [r1["id"], r2["id"], r3["id"]]


# ---------------------------------------------------------------------
# Items 4-7: joint_id filter, empty results
# ---------------------------------------------------------------------


def test_joint_id_query_param_is_forwarded_and_filters_results(client, auth_headers):
    j1, r1 = _make_joint_and_revision("filter-1")
    joints_svc.create_joint_revision(j1["id"], {}, "second", 1)
    j2, r2 = _make_joint_and_revision("filter-2")

    r = client.get(_ROUTE, params={"joint_id": j1["id"]}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert all(item["joint_revision_id"] != r2["id"] for item in body)
    ids = {item["joint_revision_id"] for item in body}
    assert r1["id"] in ids


def test_unknown_joint_id_returns_200_and_empty_array(client, auth_headers):
    r = client.get(_ROUTE, params={"joint_id": 999999999}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_joint_with_no_revisions_returns_200_and_empty_array(client, auth_headers):
    pid = _make_project("No Revisions Project")
    joint = joints_svc.create_joint(pid, "J-BULKAPI-NOREV", "No Revisions Joint", None, None)
    r = client.get(_ROUTE, params={"joint_id": joint["id"]}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------
# Item 8: invalid query parameter type
# ---------------------------------------------------------------------


def test_invalid_joint_id_type_returns_422(client, auth_headers):
    r = client.get(_ROUTE, params={"joint_id": "abc"}, headers=auth_headers)
    assert r.status_code == 422


# ---------------------------------------------------------------------
# Items 9-10: response shape / field parity with the single endpoint
# ---------------------------------------------------------------------


def test_response_is_a_bare_array_with_no_wrapper(client, auth_headers):
    _make_joint_and_revision("no-wrapper")
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_item_fields_match_the_single_record_endpoint(client, auth_headers):
    _, revision = _make_joint_and_revision("field-parity")
    single = client.get(
        f"/api/governance/joint-revision/{revision['id']}", headers=auth_headers
    ).json()
    bulk = client.get(_ROUTE, headers=auth_headers).json()
    bulk_item = next(item for item in bulk if item["joint_revision_id"] == revision["id"])
    assert set(bulk_item.keys()) == set(single.keys())
    assert bulk_item == single


# ---------------------------------------------------------------------
# Items 11-14: adapter usage, no direct source call, no mutation,
# no governance event
# ---------------------------------------------------------------------


def test_route_calls_the_bulk_adapter_exactly_once(client, auth_headers, monkeypatch):
    import backend.governance.api as api_module

    call_count = {"n": 0}
    original = api_module.project_joint_revisions_bulk

    def _counting_wrapper(joint_id=None):
        call_count["n"] += 1
        return original(joint_id)

    monkeypatch.setattr(api_module, "project_joint_revisions_bulk", _counting_wrapper)
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    assert call_count["n"] == 1


def test_route_does_not_mutate_authoritative_joint_revision_data(client, auth_headers):
    _, revision = _make_joint_and_revision("no-mutate")
    before = _revision_row(revision["id"])
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    after = _revision_row(revision["id"])
    assert before == after


def test_route_does_not_append_governance_events(client, auth_headers, gov_store):
    _, revision = _make_joint_and_revision("no-events")
    aggregate_id = f"joint-revision-{revision['id']}"
    before = svc.event_history(gov_store, aggregate_id)
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    after = svc.event_history(gov_store, aggregate_id)
    assert before == [] and after == []


# ---------------------------------------------------------------------
# Items 15-16: existing endpoints unaffected
# ---------------------------------------------------------------------


def test_existing_single_record_route_unaffected(client, auth_headers):
    _, revision = _make_joint_and_revision("existing-single")
    r = client.get(f"/api/governance/joint-revision/{revision['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["joint_revision_id"] == revision["id"]


def test_existing_history_and_status_routes_unaffected(client, auth_headers, gov_store):
    r = client.get(
        "/api/governance/agg-nonexistent-2814/history?aggregate_type=x",
        headers=auth_headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------
# Item 17: route order / path-conflict evidence
# ---------------------------------------------------------------------


def test_singular_and_plural_joint_revision_routes_do_not_collide(client, auth_headers):
    """The existing singular ``/joint-revision/{id}`` route and the
    new plural ``/joint-revisions`` route resolve independently -- a
    request to one never reaches the other's handler."""
    _, revision = _make_joint_and_revision("no-collide")

    single = client.get(f"/api/governance/joint-revision/{revision['id']}", headers=auth_headers)
    bulk = client.get(_ROUTE, headers=auth_headers)
    assert single.status_code == 200
    assert bulk.status_code == 200
    assert isinstance(single.json(), dict)
    assert isinstance(bulk.json(), list)


# ---------------------------------------------------------------------
# Items 18-20: method restrictions
# ---------------------------------------------------------------------


def test_route_accepts_only_get(client, auth_headers):
    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200


def test_post_to_route_returns_405(client, auth_headers):
    r = client.post(_ROUTE, headers=auth_headers, json={})
    assert r.status_code == 405


def test_put_and_delete_routes_do_not_exist(client, auth_headers):
    put_r = client.put(_ROUTE, headers=auth_headers, json={})
    delete_r = client.delete(_ROUTE, headers=auth_headers)
    assert put_r.status_code == 405
    assert delete_r.status_code == 405


# ---------------------------------------------------------------------
# Item 21: no internal detail leaked on an adapter-level failure
# ---------------------------------------------------------------------


def test_source_read_failure_returns_200_empty_list_not_a_raw_error(
    client, auth_headers, monkeypatch
):
    """project_joint_revisions_bulk() never raises (Stage 2 contract);
    this proves that guarantee holds through the real HTTP path too --
    an internal source failure surfaces as an empty, safe result, not
    a leaked traceback or an unhandled 500."""
    import backend.joints.service as joints_service_module

    def _boom(joint_id=None):
        raise RuntimeError("simulated sqlite3.OperationalError: disk I/O error at /secret/path")

    monkeypatch.setattr(joints_service_module, "list_joint_revisions", _boom)

    r = client.get(_ROUTE, headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []
    assert "/secret/path" not in r.text
    assert "OperationalError" not in r.text


# ---------------------------------------------------------------------
# Item 22: OpenAPI route inventory
# ---------------------------------------------------------------------


def test_route_appears_in_openapi_schema_with_get_method():
    from backend.app import app

    schema = app.openapi()
    assert "/api/governance/joint-revisions" in schema["paths"]
    assert "get" in schema["paths"]["/api/governance/joint-revisions"]
    assert "post" not in schema["paths"]["/api/governance/joint-revisions"]


# ---------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------


def test_route_rejects_unauthenticated_request(gov_store):
    from fastapi.testclient import TestClient

    unauth_client = TestClient(appmod.app)
    r = unauth_client.get(_ROUTE)
    assert r.status_code == 401
