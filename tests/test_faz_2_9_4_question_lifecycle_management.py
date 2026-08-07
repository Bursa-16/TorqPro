"""Faz 2.9.4 -- Question Bank soft-delete / restore / archive lifecycle
management.

Covers: soft-delete (never a hard delete -- JSON content and SQLite
rows always survive), restore (clears only ``is_deleted``, never
``archived_at``/``archived_by``), archive (sets ``archived_at``/
``archived_by``, no unarchive route in this phase), default-retrieval
visibility rules (``is_deleted``/``archived_at`` both hidden by
default, independently of ``publishable_only``), the
``include_deleted``/``include_archived`` opt-back-in parameters,
all-content-versions-move-together transactional behaviour and
rollback safety, authorization reuse (no hard-coded role check),
the separate ``question_bank_lifecycle_audit`` trail (not a repurposed
``question_bank_status_history``), ``validation_status`` invariance
across every lifecycle action, and migration idempotency against both
a fresh database and a simulated pre-2.9.4 database.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.app import conn
from backend.question_bank import retrieval, service, store
from backend.question_bank.errors import (
    ContentNotFoundError,
    QuestionAlreadyArchivedError,
    QuestionAlreadyDeletedError,
    QuestionNotDeletedError,
    UnauthorizedTransitionError,
)
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
from backend.question_bank.transitions import ValidationStatus

# ---------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-TEST-00001",
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
        technical_explanation_en="This explanation must be at least twenty characters long.",
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


def _allow_all(role: str, action: str) -> bool:
    return True


def _deny_all(role: str, action: str) -> bool:
    return False


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    with conn() as c:
        yield c


@pytest.fixture()
def unique_qid(request):
    import hashlib

    return "QB-LC-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


def _register(c, path, record, actor="tester"):
    store.save_question_content(record, path=path)
    service.register_question(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )


def _register_two_versions(c, path, question_id, actor="tester"):
    """Registers content_version 1 and 2 for the same question_id --
    used by every "all content_versions move together" test."""
    v1 = _make_record(question_id=question_id, content_version=1)
    v2 = _make_record(
        question_id=question_id,
        content_version=2,
        question_tr="Bu ikinci versiyon sorusudur, en az on karakter.",
    )
    _register(c, path, v1, actor=actor)
    _register(c, path, v2, actor=actor)
    return v1, v2


def _sqlite_rows(c, question_id):
    return c.execute(
        "SELECT * FROM question_bank_records WHERE question_id=? ORDER BY content_version",
        (question_id,),
    ).fetchall()


def _status_of(c, question_id, content_version):
    row = c.execute(
        "SELECT validation_status FROM question_bank_records "
        "WHERE question_id=? AND content_version=?",
        (question_id, content_version),
    ).fetchone()
    return row["validation_status"] if row else None


def _lifecycle_audit_rows(c, question_id):
    return c.execute(
        "SELECT * FROM question_bank_lifecycle_audit WHERE question_id=? ORDER BY id",
        (question_id,),
    ).fetchall()


def _status_history_rows(c, question_id):
    return c.execute(
        "SELECT * FROM question_bank_status_history WHERE question_id=? ORDER BY id",
        (question_id,),
    ).fetchall()


# ---------------------------------------------------------------------
# 1. Soft delete is never a hard delete
# ---------------------------------------------------------------------


def test_delete_never_removes_json_content(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )

    # Content is still there in JSON -- retrievable directly, unfiltered.
    still_there = store.load_question_content(unique_qid, path=qb_store_path)
    assert still_there.question_id == unique_qid


def test_delete_never_removes_sqlite_row(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )

    rows = _sqlite_rows(db, unique_qid)
    assert len(rows) == 1
    assert rows[0]["is_deleted"] == 1


def test_delete_sets_modified_fields(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    service.delete_question(
        db, question_id=unique_qid, actor="deleter1", actor_role="admin", authorize=_allow_all
    )

    row = _sqlite_rows(db, unique_qid)[0]
    assert row["modified_by"] == "deleter1"
    assert row["modified_at"] is not None


def test_delete_unknown_question_id_raises_not_found(db):
    with pytest.raises(ContentNotFoundError):
        service.delete_question(
            db,
            question_id="QB-DOES-NOT-EXIST-LC",
            actor="tester",
            actor_role="admin",
            authorize=_allow_all,
        )


def test_deleting_already_deleted_question_raises(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )
    with pytest.raises(QuestionAlreadyDeletedError):
        service.delete_question(
            db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
        )


# ---------------------------------------------------------------------
# 2. validation_status invariance
# ---------------------------------------------------------------------


def test_delete_does_not_change_validation_status(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    before = _status_of(db, unique_qid, 1)

    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )

    assert _status_of(db, unique_qid, 1) == before == ValidationStatus.DRAFT.value


def test_archive_does_not_change_validation_status(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    before = _status_of(db, unique_qid, 1)

    service.archive_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )

    assert _status_of(db, unique_qid, 1) == before == ValidationStatus.DRAFT.value


def test_restore_does_not_change_validation_status(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )
    before = _status_of(db, unique_qid, 1)

    service.restore_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )

    assert _status_of(db, unique_qid, 1) == before


# ---------------------------------------------------------------------
# 3. Restore semantics: clears is_deleted only, never archived_at/by
# ---------------------------------------------------------------------


def test_restore_clears_is_deleted(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )

    service.restore_question(
        db, question_id=unique_qid, actor="restorer1", actor_role="admin", authorize=_allow_all
    )

    row = _sqlite_rows(db, unique_qid)[0]
    assert row["is_deleted"] == 0
    assert row["modified_by"] == "restorer1"


def test_restore_after_archive_does_not_clear_archived_at(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    service.archive_question(
        db, question_id=unique_qid, actor="archiver1", actor_role="admin", authorize=_allow_all
    )
    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
    )
    archived_at_before_restore = _sqlite_rows(db, unique_qid)[0]["archived_at"]
    assert archived_at_before_restore is not None

    service.restore_question(
        db, question_id=unique_qid, actor="restorer1", actor_role="admin", authorize=_allow_all
    )

    row = _sqlite_rows(db, unique_qid)[0]
    assert row["is_deleted"] == 0
    assert row["archived_at"] == archived_at_before_restore
    assert row["archived_by"] == "archiver1"


def test_restoring_not_deleted_question_raises(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    with pytest.raises(QuestionNotDeletedError):
        service.restore_question(
            db, question_id=unique_qid, actor="tester", actor_role="admin", authorize=_allow_all
        )


# ---------------------------------------------------------------------
# 4. Archive semantics: sets archived_at/by, no unarchive in this phase
# ---------------------------------------------------------------------


def test_archive_sets_archived_fields(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    service.archive_question(
        db, question_id=unique_qid, actor="archiver1", actor_role="admin", authorize=_allow_all
    )

    row = _sqlite_rows(db, unique_qid)[0]
    assert row["archived_at"] is not None
    assert row["archived_by"] == "archiver1"
    assert row["modified_by"] == "archiver1"


def test_archive_does_not_set_is_deleted(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    service.archive_question(
        db, question_id=unique_qid, actor="archiver1", actor_role="admin", authorize=_allow_all
    )

    assert _sqlite_rows(db, unique_qid)[0]["is_deleted"] == 0


def test_archiving_already_archived_question_raises(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.archive_question(
        db, question_id=unique_qid, actor="a1", actor_role="admin", authorize=_allow_all
    )
    with pytest.raises(QuestionAlreadyArchivedError):
        service.archive_question(
            db, question_id=unique_qid, actor="a2", actor_role="admin", authorize=_allow_all
        )


def test_no_unarchive_capability_exists():
    assert not hasattr(service, "unarchive_question")


# ---------------------------------------------------------------------
# 5. Default retrieval visibility
# ---------------------------------------------------------------------


def test_deleted_question_hidden_from_default_retrieval(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    listed = retrieval.list_questions(db, publishable_only=False)
    assert not any(r.question_id == unique_qid for r in listed)

    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, unique_qid, publishable_only=False)


def test_deleted_question_visible_with_include_deleted(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    listed = retrieval.list_questions(db, publishable_only=False, include_deleted=True)
    assert any(r.question_id == unique_qid for r in listed)

    got = retrieval.get_question(
        db, unique_qid, publishable_only=False, include_deleted=True
    )
    assert got.question_id == unique_qid


def test_archived_question_hidden_from_default_retrieval(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.archive_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    listed = retrieval.list_questions(db, publishable_only=False)
    assert not any(r.question_id == unique_qid for r in listed)

    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, unique_qid, publishable_only=False)


def test_archived_question_visible_with_include_archived(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.archive_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    listed = retrieval.list_questions(db, publishable_only=False, include_archived=True)
    assert any(r.question_id == unique_qid for r in listed)

    got = retrieval.get_question(
        db, unique_qid, publishable_only=False, include_archived=True
    )
    assert got.question_id == unique_qid


def test_archived_and_deleted_combination(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.archive_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )
    service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    # Neither flag alone is enough -- both flags must be opted back in.
    assert not any(
        r.question_id == unique_qid
        for r in retrieval.list_questions(db, publishable_only=False, include_deleted=True)
    )
    assert not any(
        r.question_id == unique_qid
        for r in retrieval.list_questions(db, publishable_only=False, include_archived=True)
    )
    assert any(
        r.question_id == unique_qid
        for r in retrieval.list_questions(
            db, publishable_only=False, include_deleted=True, include_archived=True
        )
    )


def test_default_hiding_is_independent_of_publishable_only(db, qb_store_path, unique_qid):
    """A validated + active + publishable question that gets soft-deleted
    must disappear from a publishable_only=False query too -- the
    is_deleted/archived_at filters are never conditioned on
    publishable_only (Faz 2.9.4 instruction)."""
    record = _make_record(question_id=unique_qid, is_active=True)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=unique_qid, content_version=1, actor="reviewer"
    )
    service.validate_question(
        db,
        question_id=unique_qid,
        content_version=1,
        actor="reviewer",
        actor_role="admin",
        reviewed_by="reviewer",
        review_date="2026-01-01",
        authorize=_allow_all,
    )
    assert retrieval.get_question(db, unique_qid, publishable_only=True).question_id == unique_qid

    service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, unique_qid, publishable_only=True)
    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, unique_qid, publishable_only=False)


def test_select_questions_respects_include_deleted(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    default_selection = retrieval.select_questions(
        db, count=50, seed=1, publishable_only=False
    )
    assert not any(r.question_id == unique_qid for r in default_selection)

    included_selection = retrieval.select_questions(
        db, count=50, seed=1, publishable_only=False, include_deleted=True
    )
    assert any(r.question_id == unique_qid for r in included_selection)


# ---------------------------------------------------------------------
# 6. All content_versions move together, in one transaction
# ---------------------------------------------------------------------


def test_delete_applies_to_all_content_versions(db, qb_store_path, unique_qid):
    _register_two_versions(db, qb_store_path, unique_qid)

    affected = service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    assert sorted(affected) == [1, 2]
    rows = _sqlite_rows(db, unique_qid)
    assert len(rows) == 2
    assert all(r["is_deleted"] == 1 for r in rows)


def test_archive_applies_to_all_content_versions(db, qb_store_path, unique_qid):
    _register_two_versions(db, qb_store_path, unique_qid)

    affected = service.archive_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    assert sorted(affected) == [1, 2]
    rows = _sqlite_rows(db, unique_qid)
    assert all(r["archived_at"] is not None for r in rows)


def test_restore_applies_to_all_content_versions(db, qb_store_path, unique_qid):
    _register_two_versions(db, qb_store_path, unique_qid)
    service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    affected = service.restore_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    assert sorted(affected) == [1, 2]
    rows = _sqlite_rows(db, unique_qid)
    assert all(r["is_deleted"] == 0 for r in rows)


# ---------------------------------------------------------------------
# 7. Transaction rollback prevents partial lifecycle changes
# ---------------------------------------------------------------------


def test_delete_rollback_leaves_no_partial_change(db, qb_store_path, unique_qid, monkeypatch):
    _register_two_versions(db, qb_store_path, unique_qid)

    call_count = {"n": 0}
    real_append = store.append_lifecycle_audit

    def _fail_on_second_audit_row(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise sqlite3.OperationalError("simulated failure mid-transaction")
        return real_append(*args, **kwargs)

    monkeypatch.setattr(service, "append_lifecycle_audit", _fail_on_second_audit_row)

    with pytest.raises(sqlite3.OperationalError):
        service.delete_question(
            db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
        )

    # Rollback must have reverted the UPDATE too -- neither version
    # ends up half-deleted.
    rows = _sqlite_rows(db, unique_qid)
    assert len(rows) == 2
    assert all(r["is_deleted"] == 0 for r in rows)
    assert _lifecycle_audit_rows(db, unique_qid) == []


def test_archive_rollback_leaves_no_partial_change(db, qb_store_path, unique_qid, monkeypatch):
    _register_two_versions(db, qb_store_path, unique_qid)

    call_count = {"n": 0}
    real_append = store.append_lifecycle_audit

    def _fail_on_second_audit_row(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise sqlite3.OperationalError("simulated failure mid-transaction")
        return real_append(*args, **kwargs)

    monkeypatch.setattr(service, "append_lifecycle_audit", _fail_on_second_audit_row)

    with pytest.raises(sqlite3.OperationalError):
        service.archive_question(
            db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
        )

    rows = _sqlite_rows(db, unique_qid)
    assert all(r["archived_at"] is None for r in rows)
    assert _lifecycle_audit_rows(db, unique_qid) == []


# ---------------------------------------------------------------------
# 8. Authorization (reused callback/policy architecture, not hard-coded)
# ---------------------------------------------------------------------


def test_delete_denied_by_authorization_callback_changes_nothing(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    with pytest.raises(UnauthorizedTransitionError):
        service.delete_question(
            db, question_id=unique_qid, actor="t", actor_role="viewer", authorize=_deny_all
        )

    row = _sqlite_rows(db, unique_qid)[0]
    assert row["is_deleted"] == 0
    assert row["modified_at"] is None
    assert _lifecycle_audit_rows(db, unique_qid) == []


def test_restore_denied_by_authorization_callback_changes_nothing(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )
    audit_count_before = len(_lifecycle_audit_rows(db, unique_qid))

    with pytest.raises(UnauthorizedTransitionError):
        service.restore_question(
            db, question_id=unique_qid, actor="t", actor_role="viewer", authorize=_deny_all
        )

    row = _sqlite_rows(db, unique_qid)[0]
    assert row["is_deleted"] == 1
    assert len(_lifecycle_audit_rows(db, unique_qid)) == audit_count_before


def test_archive_denied_by_authorization_callback_changes_nothing(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    with pytest.raises(UnauthorizedTransitionError):
        service.archive_question(
            db, question_id=unique_qid, actor="t", actor_role="viewer", authorize=_deny_all
        )

    row = _sqlite_rows(db, unique_qid)[0]
    assert row["archived_at"] is None
    assert _lifecycle_audit_rows(db, unique_qid) == []


def test_default_role_authorization_permits_lifecycle_actions_for_engineer():
    assert service.default_role_authorization("engineer", "soft_delete") is True
    assert service.default_role_authorization("engineer", "restore") is True
    assert service.default_role_authorization("engineer", "archive") is True


def test_default_role_authorization_denies_lifecycle_actions_for_viewer():
    assert service.default_role_authorization("viewer", "soft_delete") is False
    assert service.default_role_authorization("viewer", "restore") is False
    assert service.default_role_authorization("viewer", "archive") is False


# ---------------------------------------------------------------------
# 9. Separate audit trail: actor / action / timestamp, per content_version
# ---------------------------------------------------------------------


def test_audit_trail_records_actor_action_timestamp_per_version(db, qb_store_path, unique_qid):
    _register_two_versions(db, qb_store_path, unique_qid)

    service.delete_question(
        db, question_id=unique_qid, actor="alice", actor_role="admin", authorize=_allow_all
    )

    rows = _lifecycle_audit_rows(db, unique_qid)
    assert len(rows) == 2
    for row in rows:
        assert row["action"] == "soft_delete"
        assert row["actor"] == "alice"
        assert row["actor_role"] == "admin"
        assert row["created_at"] is not None
        assert row["previous_is_deleted"] == 0
        assert row["new_is_deleted"] == 1
    assert {row["content_version"] for row in rows} == {1, 2}


def test_audit_trail_is_append_only_across_multiple_actions(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    service.archive_question(
        db, question_id=unique_qid, actor="a1", actor_role="admin", authorize=_allow_all
    )
    service.delete_question(
        db, question_id=unique_qid, actor="a2", actor_role="admin", authorize=_allow_all
    )
    service.restore_question(
        db, question_id=unique_qid, actor="a3", actor_role="admin", authorize=_allow_all
    )

    rows = _lifecycle_audit_rows(db, unique_qid)
    assert [row["action"] for row in rows] == ["archive", "soft_delete", "restore"]
    assert [row["actor"] for row in rows] == ["a1", "a2", "a3"]


def test_lifecycle_audit_does_not_pollute_status_history(db, qb_store_path, unique_qid):
    """Faz 2.9.4 instruction 7: verify question_bank_status_history's
    semantics were not repurposed -- every to_status value in that
    table must remain a legal ValidationStatus member, never a
    lifecycle-action string."""
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)

    service.archive_question(
        db, question_id=unique_qid, actor="a1", actor_role="admin", authorize=_allow_all
    )
    service.delete_question(
        db, question_id=unique_qid, actor="a2", actor_role="admin", authorize=_allow_all
    )
    service.restore_question(
        db, question_id=unique_qid, actor="a3", actor_role="admin", authorize=_allow_all
    )

    history_rows = _status_history_rows(db, unique_qid)
    # Only the original registration's draft entry -- none of the three
    # lifecycle actions above wrote anything into this table.
    assert len(history_rows) == 1
    for row in history_rows:
        assert row["to_status"] in {s.value for s in ValidationStatus}

    audit_rows = _lifecycle_audit_rows(db, unique_qid)
    assert {row["action"] for row in audit_rows} == {"archive", "soft_delete", "restore"}


def test_get_lifecycle_audit_service_accessor(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    service.archive_question(
        db, question_id=unique_qid, actor="a1", actor_role="admin", authorize=_allow_all
    )

    rows = service.get_lifecycle_audit(db, unique_qid)
    assert len(rows) == 1
    assert rows[0]["action"] == "archive"


# ---------------------------------------------------------------------
# 10. Migration idempotency -- fresh DB and simulated pre-2.9.4 DB
# ---------------------------------------------------------------------


def test_migrate_is_idempotent_on_fresh_database():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    try:
        store.migrate(c)
        store.migrate(c)  # second call must not raise
        store.migrate(c)  # third call, for good measure
        columns = {row[1] for row in c.execute("PRAGMA table_info(question_bank_records)")}
        for column_name, _ in store._LIFECYCLE_MANAGEMENT_COLUMNS:
            assert column_name in columns
    finally:
        c.close()


def test_migrate_backfills_columns_on_pre_2_9_4_database():
    """Simulates a database created before Faz 2.9.4: the
    question_bank_records / question_bank_status_history tables exist
    with their pre-2.9.4 shape (no is_deleted/archived_at/archived_by/
    modified_at/modified_by columns, no question_bank_lifecycle_audit
    table at all). migrate() must backfill it into a fully-usable
    2.9.4 schema without dropping any pre-existing data."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    try:
        pre_2_9_4_ddl = """
        CREATE TABLE question_bank_records(
          id INTEGER PRIMARY KEY,
          question_id TEXT NOT NULL,
          content_version INTEGER NOT NULL,
          validation_status TEXT NOT NULL DEFAULT 'draft',
          reviewed_by INTEGER,
          review_date TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(question_id, content_version)
        );
        CREATE TABLE question_bank_status_history(
          id INTEGER PRIMARY KEY,
          question_id TEXT NOT NULL,
          from_status TEXT,
          to_status TEXT NOT NULL,
          revision_reason TEXT,
          actor TEXT NOT NULL,
          content_version_before INTEGER,
          content_version_after INTEGER,
          created_at TEXT NOT NULL
        );
        """
        c.executescript(pre_2_9_4_ddl)
        c.execute(
            "INSERT INTO question_bank_records"
            "(question_id,content_version,validation_status,created_at,updated_at)"
            " VALUES(?,?,?,?,?)",
            ("QB-PRE-EXISTING-00001", 1, "draft", "2025-01-01T00:00:00+00:00",
             "2025-01-01T00:00:00+00:00"),
        )
        c.commit()

        # Pre-migration: the new columns genuinely do not exist yet.
        pre_columns = {row[1] for row in c.execute("PRAGMA table_info(question_bank_records)")}
        assert "is_deleted" not in pre_columns

        store.migrate(c)  # first migration on an "old" DB
        store.migrate(c)  # idempotency: second call on the now-upgraded DB

        post_columns = {row[1] for row in c.execute("PRAGMA table_info(question_bank_records)")}
        for column_name, _ in store._LIFECYCLE_MANAGEMENT_COLUMNS:
            assert column_name in post_columns

        # Pre-existing row survived the migration, with sensible
        # backfilled defaults (never deleted/archived/modified).
        row = c.execute(
            "SELECT * FROM question_bank_records WHERE question_id=?",
            ("QB-PRE-EXISTING-00001",),
        ).fetchone()
        assert row["is_deleted"] == 0
        assert row["archived_at"] is None
        assert row["archived_by"] is None
        assert row["validation_status"] == "draft"

        # The new lifecycle-management functions now work against this
        # upgraded, previously-old database.
        store.set_records_deleted_flag(
            c,
            question_id="QB-PRE-EXISTING-00001",
            is_deleted=True,
            now_iso="2026-01-01T00:00:00+00:00",
            actor="migrator",
        )
        c.commit()
        upgraded_row = c.execute(
            "SELECT * FROM question_bank_records WHERE question_id=?",
            ("QB-PRE-EXISTING-00001",),
        ).fetchone()
        assert upgraded_row["is_deleted"] == 1
        assert upgraded_row["modified_by"] == "migrator"

        # question_bank_lifecycle_audit is now usable too.
        store.append_lifecycle_audit(
            c,
            question_id="QB-PRE-EXISTING-00001",
            content_version=1,
            action="soft_delete",
            actor="migrator",
            actor_role="admin",
            previous_is_deleted=False,
            new_is_deleted=True,
            previous_archived_at=None,
            new_archived_at=None,
            now_iso="2026-01-01T00:00:00+00:00",
        )
        c.commit()
        audit_rows = store.fetch_lifecycle_audit(c, "QB-PRE-EXISTING-00001")
        assert len(audit_rows) == 1
    finally:
        c.close()


def test_migrate_via_app_migrate_is_idempotent_on_shared_test_db(db):
    """The shared, already-migrated test DB (tests/conftest.py runs
    backend.app.migrate() once at import time) tolerates re-running
    backend.question_bank.store.migrate() any number of times more --
    no error, no data loss."""
    store.migrate(db)
    store.migrate(db)
    db.commit()
    columns = {row[1] for row in db.execute("PRAGMA table_info(question_bank_records)")}
    for column_name, _ in store._LIFECYCLE_MANAGEMENT_COLUMNS:
        assert column_name in columns


# ---------------------------------------------------------------------
# 11. Backward compatibility: pre-2.9.4 read/write paths still work
# ---------------------------------------------------------------------


def test_pre_2_9_4_register_and_read_paths_unaffected(db, qb_store_path, unique_qid):
    """A plain register + publishable-read cycle, exactly as Faz 2.9.1/
    2.9.2 tests already exercise it, must still work unchanged -- new
    columns default to "not deleted, not archived" and never surface
    unless explicitly requested."""
    record = _make_record(question_id=unique_qid, is_active=True)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=unique_qid, content_version=1, actor="reviewer"
    )
    service.validate_question(
        db,
        question_id=unique_qid,
        content_version=1,
        actor="reviewer",
        actor_role="admin",
        reviewed_by="reviewer",
        review_date="2026-01-01",
        authorize=_allow_all,
    )

    publishable = service.get_publishable_questions(db)
    assert any(r.question_id == unique_qid for r in publishable)

    listed_default = retrieval.list_questions(db)
    assert any(r.question_id == unique_qid for r in listed_default)


def test_pre_2_9_4_status_history_row_shape_unchanged(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, record)
    rows = _status_history_rows(db, unique_qid)
    assert len(rows) == 1
    assert rows[0]["from_status"] is None
    assert rows[0]["to_status"] == ValidationStatus.DRAFT.value


# ---------------------------------------------------------------------
# 12. HTTP API
# ---------------------------------------------------------------------


def _viewer_headers(client, auth_headers, login_as, suffix):
    username = f"lc_viewer_{suffix}"
    client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "display_name": "LC Viewer",
            "password": "viewerpass1",
            "role": "viewer",
        },
    )
    return login_as(username, "viewerpass1")


def test_api_delete_requires_authentication(client):
    r = client.delete("/api/question-bank/QB-DOES-NOT-EXIST")
    assert r.status_code == 401


def test_api_archive_requires_authentication(client):
    r = client.post("/api/question-bank/QB-DOES-NOT-EXIST/archive")
    assert r.status_code == 401


def test_api_restore_requires_authentication(client):
    r = client.post("/api/question-bank/QB-DOES-NOT-EXIST/restore")
    assert r.status_code == 401


def test_api_delete_success_then_hidden_from_default_get(
    client, auth_headers, db, qb_store_path
):
    record = _make_record(question_id="QB-API-LC-DEL-00001")
    _register(db, qb_store_path, record)

    r = client.delete(
        "/api/question-bank/QB-API-LC-DEL-00001", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["content_versions"] == [1]

    r_get = client.get(
        "/api/question-bank/questions/QB-API-LC-DEL-00001?publishable_only=false",
        headers=auth_headers,
    )
    assert r_get.status_code == 404

    r_get_included = client.get(
        "/api/question-bank/questions/QB-API-LC-DEL-00001"
        "?publishable_only=false&include_deleted=true",
        headers=auth_headers,
    )
    assert r_get_included.status_code == 200


def test_api_archive_success_then_hidden_from_default_list(
    client, auth_headers, db, qb_store_path
):
    record = _make_record(question_id="QB-API-LC-ARC-00001")
    _register(db, qb_store_path, record)

    r = client.post(
        "/api/question-bank/QB-API-LC-ARC-00001/archive", headers=auth_headers
    )
    assert r.status_code == 200, r.text

    r_list = client.get(
        "/api/question-bank/questions?publishable_only=false", headers=auth_headers
    )
    assert r_list.status_code == 200
    assert not any(
        q["question_id"] == "QB-API-LC-ARC-00001" for q in r_list.json()
    )

    r_list_included = client.get(
        "/api/question-bank/questions?publishable_only=false&include_archived=true",
        headers=auth_headers,
    )
    assert any(
        q["question_id"] == "QB-API-LC-ARC-00001" for q in r_list_included.json()
    )


def test_api_restore_after_delete(client, auth_headers, db, qb_store_path):
    record = _make_record(question_id="QB-API-LC-RES-00001")
    _register(db, qb_store_path, record)
    client.delete("/api/question-bank/QB-API-LC-RES-00001", headers=auth_headers)

    r = client.post(
        "/api/question-bank/QB-API-LC-RES-00001/restore", headers=auth_headers
    )
    assert r.status_code == 200, r.text

    r_get = client.get(
        "/api/question-bank/questions/QB-API-LC-RES-00001?publishable_only=false",
        headers=auth_headers,
    )
    assert r_get.status_code == 200


def test_api_delete_missing_question_is_404(client, auth_headers):
    r = client.delete(
        "/api/question-bank/QB-DOES-NOT-EXIST-LC-API", headers=auth_headers
    )
    assert r.status_code == 404


def test_api_delete_twice_is_409(client, auth_headers, db, qb_store_path):
    record = _make_record(question_id="QB-API-LC-DUP-00001")
    _register(db, qb_store_path, record)
    client.delete("/api/question-bank/QB-API-LC-DUP-00001", headers=auth_headers)

    r = client.delete(
        "/api/question-bank/QB-API-LC-DUP-00001", headers=auth_headers
    )
    assert r.status_code == 409


def test_api_restore_without_prior_delete_is_409(client, auth_headers, db, qb_store_path):
    record = _make_record(question_id="QB-API-LC-NODEL-00001")
    _register(db, qb_store_path, record)

    r = client.post(
        "/api/question-bank/QB-API-LC-NODEL-00001/restore", headers=auth_headers
    )
    assert r.status_code == 409


def test_api_archive_twice_is_409(client, auth_headers, db, qb_store_path):
    record = _make_record(question_id="QB-API-LC-ARCDUP-00001")
    _register(db, qb_store_path, record)
    client.post(
        "/api/question-bank/QB-API-LC-ARCDUP-00001/archive", headers=auth_headers
    )

    r = client.post(
        "/api/question-bank/QB-API-LC-ARCDUP-00001/archive", headers=auth_headers
    )
    assert r.status_code == 409


def test_api_delete_by_viewer_role_is_403(client, auth_headers, login_as, db, qb_store_path):
    record = _make_record(question_id="QB-API-LC-VIEWER-00001")
    _register(db, qb_store_path, record)
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "delete")

    r = client.delete(
        "/api/question-bank/QB-API-LC-VIEWER-00001", headers=viewer_headers
    )
    assert r.status_code == 403

    # Data must be unchanged after the denied attempt.
    r_get = client.get(
        "/api/question-bank/questions/QB-API-LC-VIEWER-00001?publishable_only=false",
        headers=auth_headers,
    )
    assert r_get.status_code == 200


def test_api_archive_by_viewer_role_is_403(client, auth_headers, login_as, db, qb_store_path):
    record = _make_record(question_id="QB-API-LC-VIEWER-00002")
    _register(db, qb_store_path, record)
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "archive")

    r = client.post(
        "/api/question-bank/QB-API-LC-VIEWER-00002/archive", headers=viewer_headers
    )
    assert r.status_code == 403


def test_api_delete_all_content_versions_together(client, auth_headers, db, qb_store_path):
    question_id = "QB-API-LC-MULTI-00001"
    _register_two_versions(db, qb_store_path, question_id)

    r = client.delete(f"/api/question-bank/{question_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert sorted(r.json()["content_versions"]) == [1, 2]
