"""Faz 2.8.16 Stage 1 tests: backend.governance.joint_revision_query.

Domain/service-layer tests only -- no ``TestClient``, no HTTP, no
auth. Uses the same joint/revision fixture pattern already
established by ``tests/governance/adapters/test_joint_revision.py``
and ``tests/governance/test_joint_revision_bulk_api.py`` for
baseline/pagination/source-safety scenarios (real, migrated temp
SQLite DB via ``tests/conftest.py``'s shared ``TORQPRO_DB_PATH``),
plus directly-constructed ``JointRevisionProjection`` instances
(monkeypatching ``project_joint_revisions_bulk`` at the point this
module imports it) for deterministic, fast search/sort scenarios that
would otherwise need many real DB records to exercise every outcome
value.

This file never asserts against ``backend.governance.api`` (no route
exists yet for this query function -- that is Stage 2's scope) and
never re-tests ``project_joint_revisions_bulk``'s own mapping logic
(already covered by ``tests/governance/adapters/test_joint_revision.py``
and ``tests/governance/test_joint_revision_bulk_api.py``).
"""

from __future__ import annotations

import pytest

from backend.app import conn, now_iso
from backend.governance import joint_revision_query as jrq
from backend.governance.adapters.joint_revision import JointRevisionProjection
from backend.governance.enums import LifecycleGroup
from backend.governance.joint_revision_query import (
    ALLOWED_SORT_FIELDS,
    ALLOWED_SORT_ORDERS,
    MAX_PAGE_SIZE,
    JointRevisionQueryValidationError,
    query_joint_revision_projections,
)
from backend.joints import service as joints_svc
from backend.joints.exceptions import JointCodeConflictError

# ---------------------------------------------------------------------
# Real-DB fixture helpers (baseline / pagination / joint_id / source
# safety scenarios) -- mirrors tests/governance/adapters/test_joint_revision.py
# and tests/governance/test_joint_revision_bulk_api.py exactly.
# ---------------------------------------------------------------------


def _make_project(name="Joint Revision Query Test Project"):
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
            pid, f"J-JRQ-{joint_code_suffix}", "Joint Revision Query Test Joint", None, 1
        )
    except JointCodeConflictError:  # pragma: no cover - defensive, unique suffix expected
        joint = joints_svc.create_joint(
            pid, f"J-JRQ-{joint_code_suffix}-2", "Joint Revision Query Test Joint", None, 1
        )
    revision = joints_svc.create_joint_revision(joint["id"], {"thread": "M10"}, "initial", 1)
    return joint, revision


# ---------------------------------------------------------------------
# Controlled-projection helpers (search / sort scenarios) -- patches
# the name this module imported, exactly as
# tests/governance/test_joint_revision_bulk_api.py's own
# test_route_calls_the_bulk_adapter_exactly_once monkeypatches
# backend.joints.service.list_joint_revisions at the point *its*
# target module imported it.
# ---------------------------------------------------------------------


def _projection(
    joint_revision_id,
    outcome="supported",
    source_status=None,
    canonical_status=None,
    lifecycle_group=None,
    safe_reason=None,
):
    return JointRevisionProjection(
        joint_revision_id=joint_revision_id,
        outcome=outcome,
        source_status=source_status,
        canonical_status=canonical_status,
        lifecycle_group=lifecycle_group,
        safe_reason=safe_reason,
    )


def _patch_bulk(monkeypatch, projections):
    calls = {"n": 0, "joint_id": "unset"}

    def _fake_bulk(joint_id=None):
        calls["n"] += 1
        calls["joint_id"] = joint_id
        return list(projections)

    monkeypatch.setattr(jrq, "project_joint_revisions_bulk", _fake_bulk)
    return calls


_SUPPORTED_APPROVED = _projection(
    1, outcome="supported", source_status="approved", canonical_status="approved",
    lifecycle_group=LifecycleGroup.REVIEW,
)
_SUPPORTED_DRAFT = _projection(
    2, outcome="supported", source_status="draft", canonical_status="draft",
    lifecycle_group=LifecycleGroup.REVIEW,
)
_SUPPORTED_REJECTED = _projection(
    3, outcome="supported", source_status="rejected", canonical_status="rejected",
    lifecycle_group=LifecycleGroup.REVIEW,
)
_NOT_FOUND = _projection(
    404, outcome="not_found", safe_reason="No joint revision exists with this id.",
)
_SOURCE_UNAVAILABLE = _projection(
    500, outcome="source_unavailable",
    safe_reason="Joint revision source data could not be read.",
)

_MIXED_SET = (
    _SUPPORTED_APPROVED,
    _SUPPORTED_DRAFT,
    _SUPPORTED_REJECTED,
    _NOT_FOUND,
    _SOURCE_UNAVAILABLE,
)


# ---------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------


def test_default_query_returns_ascending_joint_revision_id_order():
    joint, r1 = _make_joint_and_revision("baseline-order")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    r3 = joints_svc.create_joint_revision(joint["id"], {}, "third", 1)

    result = query_joint_revision_projections(joint_id=joint["id"])
    ids = [item.joint_revision_id for item in result.items]
    assert ids == [r1["id"], r2["id"], r3["id"]]


def test_default_page_and_page_size():
    result = query_joint_revision_projections()
    assert result.page == jrq.DEFAULT_PAGE == 1
    assert result.page_size == jrq.DEFAULT_PAGE_SIZE == 25


def test_empty_source_produces_correct_metadata(monkeypatch):
    _patch_bulk(monkeypatch, [])
    result = query_joint_revision_projections()
    assert result.items == ()
    assert result.total == 0
    assert result.total_pages == 0


def test_unknown_joint_id_produces_empty_result():
    result = query_joint_revision_projections(joint_id=999999999)
    assert result.items == ()
    assert result.total == 0


def test_joint_id_filter_is_forwarded_to_bulk_adapter(monkeypatch):
    calls = _patch_bulk(monkeypatch, [])
    query_joint_revision_projections(joint_id=42)
    assert calls["joint_id"] == 42
    assert calls["n"] == 1


# ---------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------


def test_search_none_returns_all_records(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search=None)
    assert result.total == len(_MIXED_SET)


def test_search_empty_string_returns_all_records(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="")
    assert result.total == len(_MIXED_SET)


def test_search_whitespace_only_returns_all_records(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="   ")
    assert result.total == len(_MIXED_SET)


def test_search_is_trimmed(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="  approved  ")
    assert result.total == 1
    assert result.items[0].joint_revision_id == 1


def test_search_is_case_insensitive(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="APPROVED")
    assert result.total == 1
    assert result.items[0].joint_revision_id == 1


def test_search_finds_by_joint_revision_id_partial_string(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="40")
    ids = {item.joint_revision_id for item in result.items}
    assert 404 in ids


def test_search_finds_by_source_status(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="draft")
    ids = {item.joint_revision_id for item in result.items}
    assert ids == {2}


def test_search_finds_by_canonical_status(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="rejected")
    ids = {item.joint_revision_id for item in result.items}
    assert ids == {3}


def test_search_finds_by_outcome(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="source_unavailable")
    ids = {item.joint_revision_id for item in result.items}
    assert ids == {500}


def test_search_finds_by_safe_reason(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="could not be read")
    ids = {item.joint_revision_id for item in result.items}
    assert ids == {500}


def test_search_match_in_multiple_fields_is_not_duplicated(monkeypatch):
    # "approved" would match both source_status and canonical_status
    # on the same record -- must still appear exactly once.
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="approved")
    matching_ids = [item.joint_revision_id for item in result.items]
    assert matching_ids.count(1) == 1


def test_search_no_match_returns_empty_result_with_correct_metadata(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="no-such-term-xyz")
    assert result.items == ()
    assert result.total == 0
    assert result.total_pages == 0


def test_search_none_field_is_not_matched_by_literal_none_text(monkeypatch):
    # _SUPPORTED_APPROVED has no safe_reason (None); searching "none"
    # must not match it via a stringified "None".
    _patch_bulk(monkeypatch, [_SUPPORTED_APPROVED])
    result = query_joint_revision_projections(search="none")
    assert result.total == 0


def test_search_does_not_mutate_source_list(monkeypatch):
    source = list(_MIXED_SET)
    _patch_bulk(monkeypatch, source)
    query_joint_revision_projections(search="approved")
    assert source == list(_MIXED_SET)


# ---------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------


@pytest.mark.parametrize("field", ALLOWED_SORT_FIELDS)
def test_sort_ascending_and_descending_for_every_allowed_field(monkeypatch, field):
    _patch_bulk(monkeypatch, _MIXED_SET)
    asc_result = query_joint_revision_projections(sort_by=field, sort_order="asc")
    desc_result = query_joint_revision_projections(sort_by=field, sort_order="desc")
    assert len(asc_result.items) == len(desc_result.items) == len(_MIXED_SET)
    # every id present in both, order need not be a pure reversal
    # because of the None-always-last rule -- covered by dedicated
    # tests below.
    assert {i.joint_revision_id for i in asc_result.items} == {
        i.joint_revision_id for i in desc_result.items
    }


def test_sort_by_joint_revision_id_ascending():
    joint, r1 = _make_joint_and_revision("sort-id-asc")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    result = query_joint_revision_projections(
        joint_id=joint["id"], sort_by="joint_revision_id", sort_order="asc"
    )
    ids = [i.joint_revision_id for i in result.items]
    assert ids == sorted(ids) == [r1["id"], r2["id"]]


def test_sort_by_joint_revision_id_descending():
    joint, r1 = _make_joint_and_revision("sort-id-desc")
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "second", 1)
    result = query_joint_revision_projections(
        joint_id=joint["id"], sort_by="joint_revision_id", sort_order="desc"
    )
    ids = [i.joint_revision_id for i in result.items]
    assert ids == [r2["id"], r1["id"]]


def test_sort_by_source_status_case_insensitive(monkeypatch):
    lower = _projection(10, source_status="approved", outcome="supported")
    upper = _projection(11, source_status="DRAFT", outcome="supported")
    _patch_bulk(monkeypatch, [lower, upper])
    result = query_joint_revision_projections(sort_by="source_status", sort_order="asc")
    ids = [i.joint_revision_id for i in result.items]
    # "approved" < "draft" case-insensitively
    assert ids == [10, 11]


def test_sort_none_values_sort_last_ascending(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(sort_by="source_status", sort_order="asc")
    ids = [i.joint_revision_id for i in result.items]
    # _NOT_FOUND (404) and _SOURCE_UNAVAILABLE (500) have no source_status
    assert ids[-2:] == sorted([404, 500])


def test_sort_none_values_sort_last_descending(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(sort_by="source_status", sort_order="desc")
    ids = [i.joint_revision_id for i in result.items]
    # None-values still last even when sort_order is desc
    assert ids[-2:] == sorted([404, 500])


def test_sort_tie_breaker_is_always_joint_revision_id_ascending(monkeypatch):
    same_status_a = _projection(20, outcome="supported", source_status="approved")
    same_status_b = _projection(21, outcome="supported", source_status="approved")
    same_status_c = _projection(19, outcome="supported", source_status="approved")
    _patch_bulk(monkeypatch, [same_status_a, same_status_b, same_status_c])

    asc_result = query_joint_revision_projections(sort_by="source_status", sort_order="asc")
    desc_result = query_joint_revision_projections(sort_by="source_status", sort_order="desc")

    # equal primary value on every record -> tie-breaker alone decides
    # order, in both directions.
    assert [i.joint_revision_id for i in asc_result.items] == [19, 20, 21]
    assert [i.joint_revision_id for i in desc_result.items] == [19, 20, 21]


def test_sort_is_deterministic_across_repeated_calls(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    first = query_joint_revision_projections(sort_by="outcome", sort_order="asc")
    second = query_joint_revision_projections(sort_by="outcome", sort_order="asc")
    assert [i.joint_revision_id for i in first.items] == [
        i.joint_revision_id for i in second.items
    ]


def test_sort_does_not_mutate_source_list(monkeypatch):
    source = list(_MIXED_SET)
    _patch_bulk(monkeypatch, source)
    query_joint_revision_projections(sort_by="outcome", sort_order="desc")
    assert source == list(_MIXED_SET)


def test_invalid_sort_by_raises_validation_error():
    with pytest.raises(JointRevisionQueryValidationError) as exc_info:
        query_joint_revision_projections(sort_by="not_a_real_field")
    assert exc_info.value.parameter == "sort_by"


def test_invalid_sort_order_raises_validation_error():
    with pytest.raises(JointRevisionQueryValidationError) as exc_info:
        query_joint_revision_projections(sort_order="ascending")
    assert exc_info.value.parameter == "sort_order"


@pytest.mark.parametrize("value", ["ASC", "Asc", "DESC", "Desc"])
def test_sort_order_is_strict_and_does_not_normalize_case(value):
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(sort_order=value)


def test_allowed_sort_orders_are_exactly_asc_and_desc():
    assert ALLOWED_SORT_ORDERS == ("asc", "desc")


def test_allowed_sort_fields_are_exactly_the_documented_set():
    assert ALLOWED_SORT_FIELDS == (
        "joint_revision_id",
        "source_status",
        "canonical_status",
        "outcome",
    )


# ---------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------


def test_pagination_first_page(monkeypatch):
    projections = [_projection(i) for i in range(1, 11)]
    _patch_bulk(monkeypatch, projections)
    result = query_joint_revision_projections(page=1, page_size=4)
    assert [i.joint_revision_id for i in result.items] == [1, 2, 3, 4]
    assert result.total == 10
    assert result.total_pages == 3


def test_pagination_middle_page(monkeypatch):
    projections = [_projection(i) for i in range(1, 11)]
    _patch_bulk(monkeypatch, projections)
    result = query_joint_revision_projections(page=2, page_size=4)
    assert [i.joint_revision_id for i in result.items] == [5, 6, 7, 8]


def test_pagination_last_page_partial(monkeypatch):
    projections = [_projection(i) for i in range(1, 11)]
    _patch_bulk(monkeypatch, projections)
    result = query_joint_revision_projections(page=3, page_size=4)
    assert [i.joint_revision_id for i in result.items] == [9, 10]
    assert result.total_pages == 3


def test_pagination_page_beyond_range_returns_empty_items(monkeypatch):
    projections = [_projection(i) for i in range(1, 11)]
    _patch_bulk(monkeypatch, projections)
    result = query_joint_revision_projections(page=99, page_size=4)
    assert result.items == ()
    assert result.total == 10
    assert result.page == 99


def test_pagination_after_search(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = query_joint_revision_projections(search="supported", page=1, page_size=2)
    # only the three "supported" outcomes carry that literal text
    assert result.total == 3
    assert len(result.items) == 2


def test_pagination_after_sorting(monkeypatch):
    projections = [_projection(i) for i in range(1, 6)]
    _patch_bulk(monkeypatch, projections)
    result = query_joint_revision_projections(
        sort_by="joint_revision_id", sort_order="desc", page=1, page_size=2
    )
    assert [i.joint_revision_id for i in result.items] == [5, 4]


def test_total_pages_zero_when_total_zero(monkeypatch):
    _patch_bulk(monkeypatch, [])
    result = query_joint_revision_projections()
    assert result.total == 0
    assert result.total_pages == 0


def test_page_zero_raises_validation_error():
    with pytest.raises(JointRevisionQueryValidationError) as exc_info:
        query_joint_revision_projections(page=0)
    assert exc_info.value.parameter == "page"


def test_negative_page_raises_validation_error():
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(page=-1)


def test_page_size_zero_raises_validation_error():
    with pytest.raises(JointRevisionQueryValidationError) as exc_info:
        query_joint_revision_projections(page_size=0)
    assert exc_info.value.parameter == "page_size"


def test_negative_page_size_raises_validation_error():
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(page_size=-5)


def test_page_size_over_max_raises_validation_error():
    with pytest.raises(JointRevisionQueryValidationError) as exc_info:
        query_joint_revision_projections(page_size=MAX_PAGE_SIZE + 1)
    assert exc_info.value.parameter == "page_size"


def test_page_size_at_max_is_accepted(monkeypatch):
    _patch_bulk(monkeypatch, [])
    result = query_joint_revision_projections(page_size=MAX_PAGE_SIZE)
    assert result.page_size == MAX_PAGE_SIZE


def test_boolean_page_is_rejected():
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(page=True)


def test_boolean_page_size_is_rejected():
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(page_size=False)


def test_float_page_is_rejected():
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(page=1.5)


def test_float_page_size_is_rejected():
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(page_size=25.0)


def test_string_page_is_rejected():
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(page="1")


def test_validation_happens_before_source_is_read(monkeypatch):
    calls = _patch_bulk(monkeypatch, [])
    with pytest.raises(JointRevisionQueryValidationError):
        query_joint_revision_projections(page=0)
    assert calls["n"] == 0


# ---------------------------------------------------------------------
# Source safety
# ---------------------------------------------------------------------


def test_source_read_exception_produces_safe_empty_result(monkeypatch):
    import backend.joints.service as joints_service_module

    def _boom(joint_id=None):
        raise RuntimeError("simulated sqlite3.OperationalError: disk I/O error at /secret/path")

    monkeypatch.setattr(joints_service_module, "list_joint_revisions", _boom)

    result = query_joint_revision_projections()
    assert result.items == ()
    assert result.total == 0
    assert result.total_pages == 0


def test_source_read_exception_does_not_leak_traceback_or_path(monkeypatch):
    import backend.joints.service as joints_service_module

    def _boom(joint_id=None):
        raise RuntimeError("simulated sqlite3.OperationalError: disk I/O error at /secret/path")

    monkeypatch.setattr(joints_service_module, "list_joint_revisions", _boom)

    result = query_joint_revision_projections()
    rendered = repr(result)
    assert "/secret/path" not in rendered
    assert "OperationalError" not in rendered


def test_query_does_not_write_governance_event(monkeypatch, tmp_path):
    # query_joint_revision_projections() never receives or constructs a
    # governance event store reference at all (no dependency-injection
    # parameter, unlike the write routes in backend/governance/api.py),
    # so an independently-created store must stay empty across the
    # call -- there is no code path by which this function could
    # reach it.
    from backend.governance.store import FileGovernanceEventStore

    store = FileGovernanceEventStore(tmp_path / "events.json")
    before = store.all_events()
    _patch_bulk(monkeypatch, _MIXED_SET)
    query_joint_revision_projections(search="approved", sort_by="outcome", page=1)
    after = store.all_events()
    assert before == after == []


def test_query_does_not_mutate_authoritative_joint_revision_data():
    joint, revision = _make_joint_and_revision("source-safety")

    def _snapshot():
        with conn() as c:
            row = c.execute(
                "SELECT * FROM joint_revisions WHERE id=?", (revision["id"],)
            ).fetchone()
            return dict(row)

    before = _snapshot()
    query_joint_revision_projections(joint_id=joint["id"])
    after = _snapshot()
    assert before == after


# ---------------------------------------------------------------------
# Faz 2.8.16 Stage 3 regression tests: query_all_joint_revision_projections
# (additive; query_joint_revision_projections is refactored to call it
# internally -- every test above proves that refactor is behavior-
# preserving; these tests cover the new function's own contract).
# ---------------------------------------------------------------------


def test_query_all_returns_every_filtered_sorted_record_unpaginated(monkeypatch):
    many = [
        _projection(i, outcome="supported", source_status="approved") for i in range(1, 251)
    ]
    _patch_bulk(monkeypatch, many)
    result = jrq.query_all_joint_revision_projections()
    assert len(result) == 250
    assert len(result) > jrq.MAX_PAGE_SIZE


def test_query_all_is_not_capped_at_max_page_size(monkeypatch):
    many = [_projection(i) for i in range(1, jrq.MAX_PAGE_SIZE + 51)]
    _patch_bulk(monkeypatch, many)
    result = jrq.query_all_joint_revision_projections()
    assert len(result) == jrq.MAX_PAGE_SIZE + 50


def test_query_all_applies_search(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = jrq.query_all_joint_revision_projections(search="approved")
    assert len(result) == 1
    assert result[0].joint_revision_id == 1


def test_query_all_applies_sort_ascending_and_descending(monkeypatch):
    projections = [_projection(i) for i in range(1, 6)]
    _patch_bulk(monkeypatch, projections)
    asc = jrq.query_all_joint_revision_projections(
        sort_by="joint_revision_id", sort_order="asc"
    )
    desc = jrq.query_all_joint_revision_projections(
        sort_by="joint_revision_id", sort_order="desc"
    )
    assert [p.joint_revision_id for p in asc] == [1, 2, 3, 4, 5]
    assert [p.joint_revision_id for p in desc] == [5, 4, 3, 2, 1]


def test_query_all_applies_joint_id_filter(monkeypatch):
    calls = _patch_bulk(monkeypatch, [])
    jrq.query_all_joint_revision_projections(joint_id=77)
    assert calls["joint_id"] == 77


def test_query_all_invalid_sort_by_raises_before_source_read(monkeypatch):
    calls = _patch_bulk(monkeypatch, [])
    with pytest.raises(JointRevisionQueryValidationError):
        jrq.query_all_joint_revision_projections(sort_by="not_a_field")
    assert calls["n"] == 0


def test_query_all_invalid_sort_order_raises(monkeypatch):
    _patch_bulk(monkeypatch, [])
    with pytest.raises(JointRevisionQueryValidationError):
        jrq.query_all_joint_revision_projections(sort_order="sideways")


def test_query_all_returns_tuple_type(monkeypatch):
    _patch_bulk(monkeypatch, _MIXED_SET)
    result = jrq.query_all_joint_revision_projections()
    assert isinstance(result, tuple)


def test_paginated_query_and_query_all_agree_on_filtered_order(monkeypatch):
    projections = [_projection(i) for i in range(1, 11)]
    _patch_bulk(monkeypatch, projections)
    all_items = jrq.query_all_joint_revision_projections(
        sort_by="joint_revision_id", sort_order="desc"
    )
    paginated = query_joint_revision_projections(
        sort_by="joint_revision_id", sort_order="desc", page=1, page_size=jrq.MAX_PAGE_SIZE
    )
    assert [p.joint_revision_id for p in all_items] == [
        p.joint_revision_id for p in paginated.items
    ]
