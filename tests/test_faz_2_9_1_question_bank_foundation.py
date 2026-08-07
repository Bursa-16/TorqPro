"""Faz 2.9.1 -- Question Bank hybrid persistence foundation.

Covers: JSON content validity, duplicate detection (question_id+
content_version and DB-level backstop), TR/EN parity, correct_answer
consistency, state-transition legality and authorization, audit-trail
append-only behaviour, transaction rollback, migration idempotency,
publishable-question visibility rules, and the ISO 16047 scope-misuse
guard.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from pydantic import ValidationError

from backend.app import conn
from backend.question_bank import service, store, validator
from backend.question_bank.errors import (
    ContentNotFoundError,
    ContentVersionUnchangedError,
    DuplicateContentVersionError,
    InvalidTransitionError,
    MissingRevisionReasonError,
    QuestionBankValidationError,
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
    StandardReference,
    TraceabilityLevel,
)
from backend.question_bank.transitions import ValidationStatus


# ---------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-TEST-00001",
        content_version=1,
        category=Category.TIGHTENING_TORQUE,
        subcategory=None,
        difficulty=Difficulty.BEGINNER,
        question_type=QuestionType.SINGLE_CHOICE,
        question_tr="Bu bir test sorusudur, en az on karakter." ,
        question_en="This is a test question, at least ten characters.",
        options_tr=["A", "B", "C"],
        options_en=["A", "B", "C"],
        correct_answer=0,
        technical_explanation_tr="Bu açıklama en az yirmi karakter uzunluğunda olmalıdır.",
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
    """Isolated JSON content file per test -- never touches the real
    demo fixture shipped with the repo."""
    path = tmp_path / "question_bank_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    """Direct SQLite connection to the already-migrated test DB
    (backend.app.migrate() -- called once at conftest import time --
    already ran backend.question_bank.store.migrate via the app.py
    wiring, so the tables exist)."""
    with conn() as c:
        yield c


def _register(c, path, record, actor="tester"):
    store.save_question_content(record, path=path)
    service.register_question(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )


# ---------------------------------------------------------------------
# 1. Valid JSON fixture (the shipped demo file itself)
# ---------------------------------------------------------------------


def test_shipped_demo_fixture_is_valid():
    records = store.load_all_question_content(store.DATA_PATH)
    assert len(records) >= 3
    for r in records:
        reasons = validator.validate_record_structure(r)
        assert reasons == [], f"{r.question_id}: {reasons}"
    duplicates = validator.find_duplicate_question_ids(records)
    assert duplicates == []


def test_shipped_demo_fixture_iso_16047_is_correctly_scoped():
    records = store.load_all_question_content(store.DATA_PATH)
    iso_q = next(r for r in records if r.question_id == "QB-ISO_16047_TESTING-00001")
    assert iso_q.category == Category.ISO_16047_TESTING
    assert validator.validate_record_structure(iso_q) == []


# ---------------------------------------------------------------------
# 2. Duplicate detection
# ---------------------------------------------------------------------


def test_duplicate_question_id_different_versions_is_not_flagged():
    r1 = _make_record(content_version=1)
    r2 = _make_record(content_version=2)
    dups = validator.find_duplicate_question_ids([r1, r2])
    assert dups == []


def test_duplicate_question_id_and_content_version_is_flagged():
    r1 = _make_record(content_version=1)
    r2 = _make_record(content_version=1)
    dups = validator.find_duplicate_question_ids([r1, r2])
    assert dups == ["QB-TEST-00001@v1"]


def test_json_store_rejects_silent_overwrite_of_same_version(qb_store_path):
    record = _make_record()
    store.save_question_content(record, path=qb_store_path)
    with pytest.raises(DuplicateContentVersionError):
        store.save_question_content(record, path=qb_store_path)


def test_json_store_allows_new_content_version(qb_store_path):
    store.save_question_content(_make_record(content_version=1), path=qb_store_path)
    store.save_question_content(_make_record(content_version=2), path=qb_store_path)
    all_records = store.load_all_question_content(qb_store_path)
    assert {r.content_version for r in all_records} == {1, 2}


def test_db_unique_constraint_backstop(db, qb_store_path):
    record = _make_record()
    _register(db, qb_store_path, record)
    # Bypass the service-layer check and hit the store function directly
    # to prove the *database* itself, not just application code, refuses
    # the duplicate.
    with pytest.raises(DuplicateContentVersionError):
        store.register_record(
            db,
            question_id=record.question_id,
            content_version=record.content_version,
            now_iso="2026-01-01T00:00:00+00:00",
        )


# ---------------------------------------------------------------------
# 3. TR/EN parity, missing content
# ---------------------------------------------------------------------


def test_missing_tr_or_en_question_text_is_a_schema_error():
    with pytest.raises(ValidationError):
        _make_record(question_tr="")


def test_missing_technical_explanation_is_a_schema_error():
    with pytest.raises(ValidationError):
        _make_record(technical_explanation_en="too short")


def test_option_count_mismatch_between_tr_and_en_is_flagged():
    record = _make_record(options_tr=["A", "B"], options_en=["A", "B", "C"])
    reasons = validator.validate_record_structure(record)
    assert any("uzunlukları eşleşmiyor" in r for r in reasons)


def test_empty_option_is_flagged():
    record = _make_record(options_tr=["A", ""], options_en=["A", "B"])
    reasons = validator.validate_record_structure(record)
    assert any("boş seçenek" in r for r in reasons)


def test_duplicate_option_is_flagged():
    record = _make_record(options_tr=["A", "A"], options_en=["A", "B"])
    reasons = validator.validate_record_structure(record)
    assert any("tekrarlanan seçenek" in r for r in reasons)


# ---------------------------------------------------------------------
# 4. correct_answer consistency
# ---------------------------------------------------------------------


def test_correct_answer_out_of_range_for_single_choice_is_flagged():
    record = _make_record(correct_answer=99)
    reasons = validator.validate_record_structure(record)
    assert any("sınırları dışında" in r for r in reasons)


def test_correct_answer_wrong_type_for_true_false_is_flagged():
    record = _make_record(
        question_type=QuestionType.TRUE_FALSE,
        options_tr=["Doğru", "Yanlış"],
        options_en=["True", "False"],
        correct_answer=1,  # should be bool, not int, for true_false
    )
    reasons = validator.validate_record_structure(record)
    assert any("bool olmalı" in r for r in reasons)


def test_numerical_without_tolerance_is_flagged():
    record = _make_record(
        question_type=QuestionType.NUMERICAL,
        options_tr=None,
        options_en=None,
        correct_answer=42.0,
        tolerance=None,
    )
    reasons = validator.validate_record_structure(record)
    assert any("tolerance zorunlu" in r for r in reasons)


# ---------------------------------------------------------------------
# 5. High-risk / OEM-estimation cross-field rules
# ---------------------------------------------------------------------


def test_high_risk_without_any_source_is_flagged():
    record = _make_record(
        engineering_risk_level=EngineeringRiskLevel.HIGH,
        source_reference=None,
        standard_reference=None,
    )
    reasons = validator.validate_record_structure(record)
    assert any("kaynaksız teknik iddia" in r for r in reasons)


def test_oem_estimation_with_standard_reference_is_flagged():
    record = _make_record(
        source_reference=SourceReference(source_type=SourceType.OEM_ESTIMATION, description="x"),
        standard_reference=StandardReference(name="ISO 898-2"),
    )
    reasons = validator.validate_record_structure(record)
    assert any("OEM tahmini ile standart gerekliliğinin karıştırılması" in r for r in reasons)


def test_iso_16047_labeled_as_thread_stripping_is_flagged():
    record = _make_record(
        category=Category.THREAD_STRIPPING_SHEAR_AREA,
        standard_reference=StandardReference(name="ISO 16047"),
        source_reference=SourceReference(
            source_type=SourceType.STANDARD_REQUIREMENT, description="x"
        ),
    )
    reasons = validator.validate_record_structure(record)
    assert any("ISO 16047" in r and "diş sıyırma" in r for r in reasons)


def test_iso_16047_in_correct_scope_is_not_flagged():
    record = _make_record(
        category=Category.ISO_16047_TESTING,
        standard_reference=StandardReference(name="ISO 16047"),
        source_reference=SourceReference(
            source_type=SourceType.STANDARD_REQUIREMENT, description="x"
        ),
    )
    reasons = validator.validate_record_structure(record)
    assert not any("ISO 16047" in r for r in reasons)


# ---------------------------------------------------------------------
# 6. State transitions -- legality
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "prev,new,expected",
    [
        (ValidationStatus.DRAFT, ValidationStatus.TECHNICAL_REVIEW, True),
        (ValidationStatus.TECHNICAL_REVIEW, ValidationStatus.VALIDATED, True),
        (ValidationStatus.TECHNICAL_REVIEW, ValidationStatus.REJECTED, True),
        (ValidationStatus.TECHNICAL_REVIEW, ValidationStatus.DRAFT, True),
        (ValidationStatus.REJECTED, ValidationStatus.DRAFT, True),
        (ValidationStatus.VALIDATED, ValidationStatus.DEPRECATED, True),
        (ValidationStatus.DRAFT, ValidationStatus.VALIDATED, False),
        (ValidationStatus.DEPRECATED, ValidationStatus.DRAFT, False),
        (ValidationStatus.VALIDATED, ValidationStatus.REJECTED, False),
    ],
)
def test_transition_legality_matrix(prev, new, expected):
    from backend.question_bank.transitions import is_valid_transition

    assert is_valid_transition(prev, new) is expected


def test_invalid_state_transition_raises(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-TRANSITIONS", content_version=1)
    _register(db, qb_store_path, record)
    # draft -> validated directly is illegal.
    with pytest.raises(InvalidTransitionError):
        service.validate_question(
            db,
            question_id=record.question_id,
            content_version=1,
            actor="reviewer1",
            actor_role="engineer",
            reviewed_by="reviewer1",
            review_date="2026-08-06",
            authorize=_allow_all,
        )


# ---------------------------------------------------------------------
# 7. Authorization
# ---------------------------------------------------------------------


def test_unauthorized_validation_is_rejected(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-AUTH-1", content_version=1)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    with pytest.raises(UnauthorizedTransitionError):
        service.validate_question(
            db,
            question_id=record.question_id,
            content_version=1,
            actor="viewer1",
            actor_role="viewer",
            reviewed_by="viewer1",
            review_date="2026-08-06",
            authorize=service.default_role_authorization,
        )


def test_unauthorized_return_to_draft_is_rejected(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-AUTH-2", content_version=1)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    with pytest.raises(UnauthorizedTransitionError):
        service.return_to_draft(
            db,
            question_id=record.question_id,
            content_version_before=1,
            content_version_after=2,
            actor="viewer1",
            actor_role="viewer",
            revision_reason="Bu gerekçe yirmi karakterden uzun olmalı, öyle de.",
            authorize=_deny_all,
        )


def test_authorized_validation_succeeds(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-AUTH-3", content_version=1)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    service.validate_question(
        db,
        question_id=record.question_id,
        content_version=1,
        actor="reviewer1",
        actor_role="engineer",
        reviewed_by="reviewer1",
        review_date="2026-08-06",
        authorize=service.default_role_authorization,
    )
    row = store.fetch_record(db, record.question_id, 1)
    assert row["validation_status"] == "validated"
    assert row["reviewed_by"] == "reviewer1"


# ---------------------------------------------------------------------
# 8. return_to_draft: revision_reason, content_version change, audit
# ---------------------------------------------------------------------


def test_return_to_draft_requires_revision_reason_min_20_chars(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-REVREASON", content_version=1)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    with pytest.raises(MissingRevisionReasonError):
        service.return_to_draft(
            db,
            question_id=record.question_id,
            content_version_before=1,
            content_version_after=2,
            actor="reviewer1",
            actor_role="engineer",
            revision_reason="çok kısa",  # < 20 chars
            authorize=_allow_all,
        )


def test_return_to_draft_rejects_unchanged_content_version(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-SAMEVER", content_version=1)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    with pytest.raises(ContentVersionUnchangedError):
        service.return_to_draft(
            db,
            question_id=record.question_id,
            content_version_before=1,
            content_version_after=1,
            actor="reviewer1",
            actor_role="engineer",
            revision_reason="Bu gerekçe yirmi karakterden kesinlikle uzun.",
            authorize=_allow_all,
        )


def test_return_to_draft_creates_audit_row_with_reason_and_versions(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-AUDIT-1", content_version=1)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    service.return_to_draft(
        db,
        question_id=record.question_id,
        content_version_before=1,
        content_version_after=2,
        actor="reviewer1",
        actor_role="engineer",
        revision_reason="Kaynak referansı eksik, lütfen standart adını ekleyin.",
        authorize=_allow_all,
    )
    history = service.get_status_history(db, record.question_id)
    last = history[-1]
    assert last["from_status"] == "technical_review"
    assert last["to_status"] == "draft"
    assert last["revision_reason"].startswith("Kaynak referansı")
    assert last["content_version_before"] == 1
    assert last["content_version_after"] == 2


# ---------------------------------------------------------------------
# 9. Transaction rollback
# ---------------------------------------------------------------------


def test_failed_transition_does_not_leave_partial_audit_row(db, qb_store_path, monkeypatch):
    record = _make_record(question_id="QB-TEST-ROLLBACK", content_version=1)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    history_before = service.get_status_history(db, record.question_id)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated failure after status history insert")

    # Patched on the `service` module's own namespace: service.py binds
    # `update_record_status` via `from .store import update_record_status`
    # at import time, so patching `store.update_record_status` would not
    # affect the name `service._transition` actually calls.
    monkeypatch.setattr(service, "update_record_status", _boom)
    with pytest.raises(RuntimeError):
        service.validate_question(
            db,
            question_id=record.question_id,
            content_version=1,
            actor="reviewer1",
            actor_role="engineer",
            reviewed_by="reviewer1",
            review_date="2026-08-06",
            authorize=_allow_all,
        )
    history_after = service.get_status_history(db, record.question_id)
    assert len(history_after) == len(history_before), "rollback should discard the audit insert too"
    row = store.fetch_record(db, record.question_id, 1)
    assert row["validation_status"] == "technical_review", "status must be unchanged after rollback"


# ---------------------------------------------------------------------
# 10. Migration idempotency
# ---------------------------------------------------------------------


def test_migration_is_idempotent(db):
    store.migrate(db)
    store.migrate(db)
    store.migrate(db)
    tables = {
        r["name"]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'question_bank_%'"
        ).fetchall()
    }
    # Faz 2.9.4 adds a fourth, purely additive table
    # (question_bank_lifecycle_audit -- see backend.question_bank.store's
    # DDL docstring for why soft-delete/restore/archive auditing lives
    # in its own table rather than being folded into
    # question_bank_status_history). This assertion is updated to
    # reflect that additive change; the idempotency behaviour itself
    # (repeated migrate() calls create nothing new) is unchanged.
    assert tables == {
        "question_bank_records",
        "question_bank_status_history",
        "question_bank_lifecycle_audit",
    }


# ---------------------------------------------------------------------
# 11. Publishable-question visibility rules
# ---------------------------------------------------------------------


def test_draft_question_is_not_publishable(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-PUB-DRAFT", content_version=1, is_active=True)
    _register(db, qb_store_path, record)
    ids = {r.question_id for r in service.get_publishable_questions(db)}
    assert record.question_id not in ids


def test_validated_and_active_question_is_publishable(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-PUB-VALID", content_version=1, is_active=True)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    service.validate_question(
        db,
        question_id=record.question_id,
        content_version=1,
        actor="reviewer1",
        actor_role="engineer",
        reviewed_by="reviewer1",
        review_date="2026-08-06",
        authorize=_allow_all,
    )
    ids = {r.question_id for r in service.get_publishable_questions(db)}
    assert record.question_id in ids


def test_deprecated_question_is_not_publishable(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-PUB-DEP", content_version=1, is_active=True)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    service.validate_question(
        db,
        question_id=record.question_id,
        content_version=1,
        actor="reviewer1",
        actor_role="engineer",
        reviewed_by="reviewer1",
        review_date="2026-08-06",
        authorize=_allow_all,
    )
    service.deprecate_question(
        db,
        question_id=record.question_id,
        content_version=1,
        actor="reviewer1",
        actor_role="engineer",
        authorize=_allow_all,
    )
    ids = {r.question_id for r in service.get_publishable_questions(db)}
    assert record.question_id not in ids


def test_validated_but_inactive_question_is_not_publishable(db, qb_store_path):
    record = _make_record(question_id="QB-TEST-PUB-INACTIVE", content_version=1, is_active=False)
    _register(db, qb_store_path, record)
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=1, actor="author1"
    )
    service.validate_question(
        db,
        question_id=record.question_id,
        content_version=1,
        actor="reviewer1",
        actor_role="engineer",
        reviewed_by="reviewer1",
        review_date="2026-08-06",
        authorize=_allow_all,
    )
    ids = {r.question_id for r in service.get_publishable_questions(db)}
    assert record.question_id not in ids


# ---------------------------------------------------------------------
# 12. JSON/SQLite question_id + content_version mismatch rejection
# ---------------------------------------------------------------------


def test_register_question_without_json_content_is_rejected(db, qb_store_path):
    with pytest.raises(ContentNotFoundError):
        service.register_question(
            db, question_id="QB-DOES-NOT-EXIST", content_version=1, actor="tester"
        )


# ---------------------------------------------------------------------
# 13. Windows-compatible persistence (no fcntl dependency)
# ---------------------------------------------------------------------


def test_store_module_does_not_depend_on_fcntl():
    import backend.question_bank.store as store_module

    source = open(store_module.__file__, encoding="utf-8").read()
    assert "import fcntl" not in source, (
        "question_bank.store must not import fcntl -- "
        "washer_resolution_decisions_store.py documents fcntl as non-functional on Windows"
    )
    assert not hasattr(store_module, "fcntl")


def test_json_write_is_atomic_replace(qb_store_path):
    """Confirms the write path goes through tempfile + os.replace (both
    atomic on POSIX and Windows), not an in-place open('w')."""
    import inspect

    source = inspect.getsource(store._write_raw)
    assert "os.replace" in source
    assert "tempfile" in source or "mkstemp" in source
