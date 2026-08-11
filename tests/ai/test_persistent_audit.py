"""Faz v3.0.0-alpha.5 (Persistent Audit, ADR-0020).

Covers ``backend.ai_gateway.store`` in isolation: migration
idempotency, a pre-alpha.5 database opening without breaking, write/
read round-trips (success and failure shapes), reopen/reconnect
persistence, and the privacy guarantee that no raw prompt/response
text or secret is ever written.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.ai_gateway.audit import AIInteractionRecord
from backend.ai_gateway.store import (
    DDL,
    SQLiteAuditSink,
    get_audit_record,
    list_audit_records,
    migrate,
)


def _make_record(**overrides) -> AIInteractionRecord:
    base = dict(
        user_id=1,
        query_text_hash="deadbeef",
        evidence_source_ids=(("question_bank", "QB-0001"),),
        calculation_formula_ids=(),
        model_name="deterministic",
        had_sufficient_evidence=True,
        created_at="2026-08-09T00:00:00+00:00",
        retrieval_source_types_queried=("question_bank",),
        evidence_count_by_source_type=(("question_bank", 1),),
        evidence_status="PASS",
        result_label="VALIDATED",
    )
    base.update(overrides)
    return AIInteractionRecord(**base)


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "alpha5_audit_test.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ------------------------------------------------------------------- migration


def test_migrate_is_idempotent(db):
    migrate(db)
    migrate(db)
    migrate(db)  # third call, same connection -- must not raise
    tables = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "ai_audit_records" in tables


def test_migrate_never_alters_or_drops_existing_tables(db):
    """Simulates a pre-alpha.5 database: an unrelated table already
    exists before migrate() ever runs; migrate() must leave it
    completely untouched."""
    db.execute("CREATE TABLE pre_existing_table(id INTEGER PRIMARY KEY, note TEXT)")
    db.execute("INSERT INTO pre_existing_table(note) VALUES('untouched')")
    db.commit()

    migrate(db)

    row = db.execute("SELECT note FROM pre_existing_table WHERE id=1").fetchone()
    assert row["note"] == "untouched"


def test_fresh_database_migration_does_not_raise(db):
    """A completely fresh, empty database (no schema_info, no other
    TorqPro tables at all) must migrate cleanly -- this module makes
    no assumption about ``backend.app``'s own tables already existing."""
    migrate(db)
    assert db.execute("SELECT COUNT(*) FROM ai_audit_records").fetchone()[0] == 0


def test_ddl_only_creates_tables_and_indexes_no_data_mutation():
    assert "INSERT" not in DDL.upper()
    assert "UPDATE" not in DDL.upper()
    assert "DELETE" not in DDL.upper()
    assert "DROP" not in DDL.upper()


# --------------------------------------------------------------- write / read


def test_record_then_list_round_trip(db):
    migrate(db)
    sink = SQLiteAuditSink(db)
    sink.record(_make_record())

    records = list_audit_records(db, limit=10)
    assert len(records) == 1
    assert records[0].query_text_hash == "deadbeef"
    assert records[0].evidence_status == "PASS"
    assert records[0].success is True


def test_record_with_latency_persists_route_layer_metadata(db):
    migrate(db)
    sink = SQLiteAuditSink(db)
    sink.record_with_latency(
        _make_record(),
        latency_ms=123,
        user_role="engineer",
        correlation_id="req-abc",
        response_text_hash="resp-hash-xyz",
    )

    record = list_audit_records(db, limit=10)[0]
    assert record.latency_ms == 123
    assert record.user_role == "engineer"
    assert record.correlation_id == "req-abc"
    assert record.response_text_hash == "resp-hash-xyz"
    assert record.success is True
    assert record.error_category is None


def test_record_failure_persists_a_minimal_failure_row(db):
    migrate(db)
    sink = SQLiteAuditSink(db)
    sink.record_failure(
        user_id=7,
        query_text_hash="fail-hash",
        model_name="unavailable",
        created_at="2026-08-09T01:00:00+00:00",
        error_category="ModelUnavailableError",
        latency_ms=5,
        user_role="viewer",
        correlation_id="req-fail-1",
    )

    record = list_audit_records(db, limit=10)[0]
    assert record.success is False
    assert record.error_category == "ModelUnavailableError"
    assert record.had_sufficient_evidence is False
    assert record.evidence_status == "FAIL"
    assert record.result_label is None
    assert record.user_role == "viewer"
    assert record.correlation_id == "req-fail-1"


def test_list_audit_records_most_recent_first(db):
    migrate(db)
    sink = SQLiteAuditSink(db)
    sink.record(_make_record(query_text_hash="first"))
    sink.record(_make_record(query_text_hash="second"))
    sink.record(_make_record(query_text_hash="third"))

    records = list_audit_records(db, limit=10)
    assert [r.query_text_hash for r in records] == ["third", "second", "first"]


def test_list_audit_records_applies_exactly_the_given_limit(db):
    migrate(db)
    sink = SQLiteAuditSink(db)
    for i in range(5):
        sink.record(_make_record(query_text_hash=f"h{i}"))

    assert len(list_audit_records(db, limit=2)) == 2
    assert len(list_audit_records(db, limit=5)) == 5


def test_get_audit_record_returns_none_for_missing_id(db):
    migrate(db)
    assert get_audit_record(db, 99999) is None


def test_get_audit_record_returns_the_matching_row(db):
    migrate(db)
    sink = SQLiteAuditSink(db)
    sink.record(_make_record(query_text_hash="find-me"))

    listed = list_audit_records(db, limit=1)[0]
    fetched = get_audit_record(db, listed.id)
    assert fetched is not None
    assert fetched.query_text_hash == "find-me"


# ----------------------------------------------------------- reopen / reconnect


def test_audit_persists_after_reopening_the_connection(tmp_path):
    path = tmp_path / "alpha5_reopen_test.db"

    conn1 = sqlite3.connect(str(path))
    conn1.row_factory = sqlite3.Row
    migrate(conn1)
    SQLiteAuditSink(conn1).record(_make_record(query_text_hash="persisted-across-reopen"))
    conn1.close()

    conn2 = sqlite3.connect(str(path))
    conn2.row_factory = sqlite3.Row
    migrate(conn2)  # startup-time re-migration, must be a safe no-op
    records = list_audit_records(conn2, limit=10)
    conn2.close()

    assert len(records) == 1
    assert records[0].query_text_hash == "persisted-across-reopen"


# ------------------------------------------------------------------------ privacy


def test_no_raw_prompt_or_response_column_exists_in_schema(db):
    migrate(db)
    columns = {row["name"] for row in db.execute("PRAGMA table_info(ai_audit_records)")}
    # Only hash/identifier/structured-metadata columns are permitted --
    # no column named/shaped to hold raw free-text prompt or response
    # content.
    forbidden_substrings = (
        "prompt", "response_text", "raw", "secret", "token", "api_key", "credential",
    )
    for column in columns:
        lowered = column.lower()
        for forbidden in forbidden_substrings:
            if forbidden == "response_text":
                # response_text_HASH is fine; a raw response_text column is not.
                assert lowered != "response_text", (
                    f"Forbidden raw-content column found: {column}"
                )
                continue
            assert forbidden not in lowered, f"Forbidden column found: {column}"


def test_recording_never_stores_the_raw_query_text_anywhere(db):
    """AIInteractionRecord itself never carries raw query text (only
    query_text_hash) -- this proves the sink can't leak it even if it
    tried, since the raw text is structurally unavailable to it."""
    migrate(db)
    sink = SQLiteAuditSink(db)
    entry = _make_record(query_text_hash="only-a-hash-abc123")
    sink.record(entry)

    row = db.execute("SELECT * FROM ai_audit_records").fetchone()
    values = [str(v) for v in tuple(row)]
    assert "only-a-hash-abc123" in values  # the hash itself is present
    # No field on AIInteractionRecord ever carried raw text to begin
    # with, so there is nothing else to assert absence of here -- this
    # is a structural guarantee (see backend.ai_gateway.audit module
    # docstring), not a runtime scrub.


def test_no_secret_or_credential_field_exists_on_persisted_record(db):
    migrate(db)
    sink = SQLiteAuditSink(db)
    sink.record(_make_record())
    record = list_audit_records(db, limit=1)[0]

    field_names = {f for f in record.__dataclass_fields__}
    forbidden = {"secret", "api_key", "token", "password", "credential", "header"}
    assert not (field_names & forbidden)
