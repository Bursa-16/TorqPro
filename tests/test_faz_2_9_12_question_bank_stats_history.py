"""Faz 2.9.12 -- Question Bank statistics Trend / History.

Covers: ``question_bank_stats_snapshots`` migration (table creation +
idempotency), :func:`backend.question_bank.stats_history.create_snapshot`
(persists the exact same payload
:func:`backend.question_bank.stats.compute_stats` returns),
:func:`backend.question_bank.stats_history.list_snapshots` (chronological
ordering, ``limit`` behavior, empty history, malformed stored row ->
:class:`backend.question_bank.errors.SnapshotDataError`), the two new
HTTP routes (``POST /api/question-bank/stats/snapshot``, ``GET
/api/question-bank/stats/history``), and a regression check that
``GET /api/question-bank/stats`` (Faz 2.9.10) is completely unaffected.

Public-API / observable-behavior focus throughout: assertions target
returned dicts/HTTP responses, never SQL text or internal row
shapes (row access needed for the deliberate-corruption test uses only
the already-public ``store.migrate``/``backend.app.conn`` surface, not
any private helper).

Same isolated-store pattern as
``tests/test_faz_2_9_10_question_bank_stats.py``: every test uses its
own ``qb_store_path`` (never the shipped demo fixture) and a
per-test-unique ``question_id`` namespace (the shared SQLite test DB
from ``tests/conftest.py`` is never reset between tests, so the
snapshots table accumulates rows across the whole session -- tests
that care about an exact count/order create their own fresh
sub-selection via ``limit`` or by diffing against a baseline taken at
the start of the test, rather than assuming the table starts empty).
"""

from __future__ import annotations

import hashlib

import pytest

from backend.app import conn
from backend.question_bank import service, stats, stats_history, store
from backend.question_bank.errors import SnapshotDataError
from backend.question_bank.schema import (
    Category,
    Difficulty,
    EngineeringRiskLevel,
    QuestionRecord,
    QuestionType,
    SourceReference,
    SourceType,
    TraceabilityLevel,
)

# ---------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_stats_history_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    with conn() as c:
        yield c


@pytest.fixture()
def unique_qid(request):
    return "QB-C12-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-C12-DEFAULT",
        content_version=1,
        category=Category.TIGHTENING_TORQUE,
        subcategory=None,
        difficulty=Difficulty.BEGINNER,
        question_type=QuestionType.SINGLE_CHOICE,
        question_tr="Bu bir test sorusudur, en az on karakter.",
        question_en="This is a test question, at least ten characters.",
        options_tr=["A", "B", "C"],
        options_en=["A", "B", "C"],
        correct_answer=0,
        technical_explanation_tr="Bu açıklama en az yirmi karakter uzunluğundadır.",
        technical_explanation_en="This explanation must be at least twenty characters.",
        standard_reference=None,
        source_reference=SourceReference(
            source_type=SourceType.INTERNAL_ENGINE, description="test"
        ),
        source_locator=None,
        traceability_level=TraceabilityLevel.PROVISIONAL,
        tags=["test"],
        learning_objective="Test amaçlı öğrenme hedefi metni.",
        engineering_risk_level=EngineeringRiskLevel.LOW,
        is_active=True,
    )
    base.update(overrides)
    return QuestionRecord(**base)


def _register_draft(c, path, record, actor="tester"):
    store.save_question_content(record, path=path)
    service.register_question(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )


# ---------------------------------------------------------------------
# 1. Migration -- table creation + idempotency
# ---------------------------------------------------------------------


def test_migrate_creates_stats_snapshots_table(db):
    store.migrate(db)
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "question_bank_stats_snapshots" in tables


def test_migrate_is_idempotent(db):
    # Calling migrate() repeatedly must never raise (CREATE TABLE IF
    # NOT EXISTS / CREATE INDEX IF NOT EXISTS throughout), and the
    # snapshots table must still be usable afterwards -- the public
    # observable behavior that matters, not the DDL text itself.
    store.migrate(db)
    store.migrate(db)
    store.migrate(db)
    before = len(stats_history.list_snapshots(db))
    stats_history.create_snapshot(db)
    after = len(stats_history.list_snapshots(db))
    assert after == before + 1


# ---------------------------------------------------------------------
# 2. create_snapshot() -- persists compute_stats()'s exact payload
# ---------------------------------------------------------------------


def test_create_snapshot_returns_id_created_at_and_stats(db, qb_store_path):
    snap = stats_history.create_snapshot(db)
    assert isinstance(snap["id"], int)
    assert isinstance(snap["created_at"], str) and snap["created_at"]
    assert isinstance(snap["stats"], dict)
    assert set(snap["stats"].keys()) == {
        "total", "by_validation_status", "by_category", "by_difficulty", "by_question_type",
    }


def test_create_snapshot_stores_exact_compute_stats_result(db, qb_store_path, unique_qid):
    _register_draft(db, qb_store_path, _make_record(question_id=unique_qid, content_version=1))

    expected = stats.compute_stats(db)
    snap = stats_history.create_snapshot(db)
    assert snap["stats"] == expected

    # And it round-trips through persistence, not just the in-memory
    # return value of create_snapshot() itself.
    history = stats_history.list_snapshots(db, limit=1)
    assert history[-1]["stats"] == expected
    assert history[-1]["id"] == snap["id"]


def test_create_snapshot_reflects_bank_state_at_call_time(db, qb_store_path, unique_qid):
    """Two snapshots taken before/after a new record is registered
    must differ in ``total`` by exactly one -- each snapshot is an
    independent point-in-time read, not a cached/shared value."""
    snap_before = stats_history.create_snapshot(db)
    _register_draft(db, qb_store_path, _make_record(question_id=unique_qid, content_version=1))
    snap_after = stats_history.create_snapshot(db)
    assert snap_after["stats"]["total"] == snap_before["stats"]["total"] + 1


# ---------------------------------------------------------------------
# 3. list_snapshots() -- chronological ordering, limit, empty history
# ---------------------------------------------------------------------


def test_list_snapshots_empty_history_returns_empty_list(db):
    # A dedicated fresh DB (not the shared session DB, which may
    # already have rows from earlier tests in this file) proves the
    # true-empty case without depending on test execution order.
    import sqlite3

    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    store.migrate(fresh)
    assert stats_history.list_snapshots(fresh) == []


def test_list_snapshots_deterministic_chronological_order(db, qb_store_path):
    ids_in_creation_order = [stats_history.create_snapshot(db)["id"] for _ in range(4)]
    history = stats_history.list_snapshots(db)
    returned_ids = [snap["id"] for snap in history]
    # Every id created in this test must appear in the same relative
    # order it was created in (oldest-first) -- checked as a
    # subsequence rather than assuming the whole table starts empty,
    # since the shared session DB may carry rows from earlier tests.
    positions = [returned_ids.index(i) for i in ids_in_creation_order]
    assert positions == sorted(positions)


def test_list_snapshots_limit_returns_most_recent_n_in_chronological_order(db, qb_store_path):
    created_ids = [stats_history.create_snapshot(db)["id"] for _ in range(5)]
    last_three = stats_history.list_snapshots(db, limit=3)
    assert [snap["id"] for snap in last_three] == created_ids[-3:]


def test_list_snapshots_limit_larger_than_history_returns_everything_available(db, qb_store_path):
    import sqlite3

    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    store.migrate(fresh)
    stats_history.create_snapshot(fresh)
    stats_history.create_snapshot(fresh)
    result = stats_history.list_snapshots(fresh, limit=1000)
    assert len(result) == 2


def test_list_snapshots_non_positive_limit_returns_empty_list(db, qb_store_path):
    stats_history.create_snapshot(db)
    assert stats_history.list_snapshots(db, limit=0) == []
    assert stats_history.list_snapshots(db, limit=-1) == []


# ---------------------------------------------------------------------
# 4. Malformed stored snapshot -> SnapshotDataError
# ---------------------------------------------------------------------


def test_malformed_stats_json_raises_snapshot_data_error(db):
    import sqlite3

    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    store.migrate(fresh)
    fresh.execute(
        "INSERT INTO question_bank_stats_snapshots(created_at, stats_json) VALUES(?,?)",
        ("2026-01-01T00:00:00+00:00", "{not valid json"),
    )
    with pytest.raises(SnapshotDataError):
        stats_history.list_snapshots(fresh)


def test_stats_json_missing_expected_keys_raises_snapshot_data_error(db):
    import json
    import sqlite3

    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    store.migrate(fresh)
    fresh.execute(
        "INSERT INTO question_bank_stats_snapshots(created_at, stats_json) VALUES(?,?)",
        ("2026-01-01T00:00:00+00:00", json.dumps({"unexpected": "shape"})),
    )
    with pytest.raises(SnapshotDataError):
        stats_history.list_snapshots(fresh)


def test_stats_json_valid_json_but_not_a_dict_raises_snapshot_data_error(db):
    import json
    import sqlite3

    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    store.migrate(fresh)
    fresh.execute(
        "INSERT INTO question_bank_stats_snapshots(created_at, stats_json) VALUES(?,?)",
        ("2026-01-01T00:00:00+00:00", json.dumps([1, 2, 3])),
    )
    with pytest.raises(SnapshotDataError):
        stats_history.list_snapshots(fresh)


# ---------------------------------------------------------------------
# 5. HTTP routes -- POST .../stats/snapshot, GET .../stats/history
# ---------------------------------------------------------------------


def test_snapshot_route_requires_authentication(client):
    r = client.post("/api/question-bank/stats/snapshot")
    assert r.status_code == 401


def test_history_route_requires_authentication(client):
    r = client.get("/api/question-bank/stats/history")
    assert r.status_code == 401


def test_snapshot_route_creates_and_returns_a_snapshot(client, auth_headers):
    r = client.post("/api/question-bank/stats/snapshot", headers=auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body.keys()) == {"id", "created_at", "stats"}
    assert set(body["stats"].keys()) == {
        "total", "by_validation_status", "by_category", "by_difficulty", "by_question_type",
    }


def test_history_route_returns_list_shape(client, auth_headers):
    client.post("/api/question-bank/stats/snapshot", headers=auth_headers)
    r = client.get("/api/question-bank/stats/history", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    for entry in body:
        assert set(entry.keys()) == {"id", "created_at", "stats"}


def test_history_route_respects_limit_query_param(client, auth_headers):
    client.post("/api/question-bank/stats/snapshot", headers=auth_headers)
    client.post("/api/question-bank/stats/snapshot", headers=auth_headers)
    r = client.get("/api/question-bank/stats/history", headers=auth_headers, params={"limit": 1})
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1


def test_history_route_chronological_order_via_http(client, auth_headers):
    r1 = client.post("/api/question-bank/stats/snapshot", headers=auth_headers)
    r2 = client.post("/api/question-bank/stats/snapshot", headers=auth_headers)
    id1, id2 = r1.json()["id"], r2.json()["id"]
    history = client.get(
        "/api/question-bank/stats/history", headers=auth_headers, params={"limit": 2}
    ).json()
    returned_ids = [entry["id"] for entry in history]
    assert returned_ids == [id1, id2]


def test_snapshot_route_not_shadowed_by_question_id_routes(client, auth_headers):
    """``POST /api/question-bank/stats/snapshot`` must resolve to
    snapshot creation, never be captured by any ``{question_id}``-
    shaped dynamic route in this module."""
    r = client.post("/api/question-bank/stats/snapshot", headers=auth_headers)
    assert r.status_code == 201, r.text
    assert "stats" in r.json()


# ---------------------------------------------------------------------
# 6. Regression -- GET /api/question-bank/stats (Faz 2.9.10) unaffected
# ---------------------------------------------------------------------


def test_existing_stats_route_unaffected(client, auth_headers):
    r = client.get("/api/question-bank/stats", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "total", "by_validation_status", "by_category", "by_difficulty", "by_question_type",
    }


def test_existing_stats_route_shape_matches_snapshot_stats_field(client, auth_headers):
    """The live ``/stats`` response and a freshly-created snapshot's
    ``stats`` field must have the identical key set -- the snapshot
    mechanism must never drift from the live aggregation contract."""
    live = client.get("/api/question-bank/stats", headers=auth_headers).json()
    snap = client.post("/api/question-bank/stats/snapshot", headers=auth_headers).json()
    assert set(live.keys()) == set(snap["stats"].keys())


def test_existing_list_questions_route_unaffected(client, auth_headers, qb_store_path):
    r = client.get("/api/question-bank/questions", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
