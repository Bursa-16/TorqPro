"""Faz 2.9.3 -- Question Bank content update ("PATCH") workflow.

Covers: partial-update merge semantics (only provided fields change,
omitted fields keep their current value), the append-only revision
model (a real change always creates a brand-new, immutable
``content_version = current + 1`` -- no existing ``(question_id,
content_version)`` row, JSON or SQLite, is ever mutated), no-op
detection (no new version/history when nothing actually changed),
structural/schema validation reuse (empty and whitespace-only text,
invalid enum values), immutable-field protection (``question_id``/
``content_version``/lifecycle fields have no field to write to on the
patch payload at all), 404 for an unknown question, 409 for a
concurrent-write race on the same target version, the empty-patch
422, the SQLite-partial-failure path (JSON appended, SQLite rolled
back), and the read-only HTTP PATCH route (auth, success, partial
update, validation error, not-found, conflict, and an immediate
retrieval of the new content afterwards).

Deliberately does NOT touch or expand the shipped 4-record demo
fixture (``backend/question_bank/data/question_bank.v1.json``) --
every test here uses its own isolated ``qb_store_path`` (same pattern
as ``tests/test_faz_2_9_1_question_bank_foundation.py`` and
``tests/test_faz_2_9_2_question_bank_retrieval.py``).
"""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from backend.app import conn
from backend.question_bank import retrieval, service, store
from backend.question_bank.errors import (
    ContentNotFoundError,
    DuplicateContentVersionError,
    PartialUpdateFailureError,
    QuestionBankValidationError,
)
from backend.question_bank.patch import EDITABLE_FIELDS, IMMUTABLE_FIELDS, QuestionPatch
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
# Fixtures
# ---------------------------------------------------------------------


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-UPD-00001",
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


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_update_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    with conn() as c:
        yield c


@pytest.fixture()
def unique_qid(request):
    """A per-test-unique question_id.

    The underlying SQLite database (``question_bank_records``) is the
    shared, session-scoped test DB from ``tests/conftest.py`` -- it is
    never reset between tests, so two tests reusing the exact same
    literal ``question_id`` would collide against the store's own
    silent-overwrite/unique-constraint guard (a correctness guarantee
    this suite must not work around). Same pattern as
    ``tests/test_faz_2_9_2_question_bank_retrieval.py``'s
    ``seeded_dataset`` fixture."""
    import hashlib

    return "QB-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:16].upper()


def _register(c, path, record, actor="tester"):
    store.save_question_content(record, path=path)
    service.register_question(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )


def _status_of(c, question_id, content_version):
    row = c.execute(
        "SELECT validation_status FROM question_bank_records "
        "WHERE question_id=? AND content_version=?",
        (question_id, content_version),
    ).fetchone()
    return row["validation_status"] if row else None


def _history_rows(c, question_id):
    return c.execute(
        "SELECT * FROM question_bank_status_history WHERE question_id=? ORDER BY id",
        (question_id,),
    ).fetchall()


# ---------------------------------------------------------------------
# 1. Patch model shape: immutable / editable field split
# ---------------------------------------------------------------------


def test_patch_model_has_no_immutable_fields():
    assert IMMUTABLE_FIELDS.isdisjoint(EDITABLE_FIELDS)
    assert "question_id" in IMMUTABLE_FIELDS
    assert "content_version" in IMMUTABLE_FIELDS


def test_patch_model_rejects_question_id():
    with pytest.raises(ValidationError):
        QuestionPatch(question_id="QB-SHOULD-NOT-BE-SETTABLE")


def test_patch_model_rejects_content_version():
    with pytest.raises(ValidationError):
        QuestionPatch(content_version=99)


def test_patch_model_rejects_lifecycle_field():
    # validation_status lives only in SQLite, never on QuestionRecord --
    # QuestionPatch has no field for it at all, so any attempt to set it
    # is an unknown-field rejection (extra="forbid"), not a value error.
    with pytest.raises(ValidationError):
        QuestionPatch(validation_status="validated")


# ---------------------------------------------------------------------
# 2. Service: successful partial update, versioning, unchanged fields
# ---------------------------------------------------------------------


def test_update_one_field_creates_new_content_version(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    updated = service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(difficulty=Difficulty.ADVANCED),
        actor="editor1",
    )

    assert updated.content_version == 2
    assert updated.difficulty == Difficulty.ADVANCED
    # Every other field carried over unchanged from v1.
    assert updated.question_tr == original.question_tr
    assert updated.tags == original.tags

    # v1 is untouched, still loadable exactly as it was.
    v1 = store.load_question_content(original.question_id, 1, path=qb_store_path)
    assert v1.difficulty == Difficulty.BEGINNER
    assert v1 == original


def test_update_multiple_fields(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    updated = service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(
            difficulty=Difficulty.EXPERT,
            tags=["updated", "torque"],
            is_active=False,
        ),
        actor="editor1",
    )

    assert updated.content_version == 2
    assert updated.difficulty == Difficulty.EXPERT
    assert updated.tags == ["updated", "torque"]
    assert updated.is_active is False
    assert updated.question_tr == original.question_tr  # omitted -> unchanged


def test_omitted_fields_remain_unchanged(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid, subcategory="torque_preload_relationship")
    _register(db, qb_store_path, original)

    updated = service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(learning_objective="Yeni öğrenme hedefi metni buradadır."),
        actor="editor1",
    )

    assert updated.subcategory == "torque_preload_relationship"
    assert updated.category == original.category
    assert updated.options_tr == original.options_tr
    assert updated.correct_answer == original.correct_answer


def test_explicit_null_clears_nullable_field(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid, subcategory="torque_preload_relationship")
    _register(db, qb_store_path, original)

    updated = service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(subcategory=None),
        actor="editor1",
    )
    # subcategory was explicitly provided as null -> cleared, and that
    # alone is a real change, so a new version is created.
    assert updated.content_version == 2
    assert updated.subcategory is None


# ---------------------------------------------------------------------
# 3. No-op update
# ---------------------------------------------------------------------


def test_noop_update_creates_no_new_version_or_history(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    result = service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(difficulty=Difficulty.BEGINNER),  # same as current
        actor="editor1",
    )

    assert result.content_version == 1
    assert result == original

    all_versions = [
        r.content_version
        for r in store.load_all_question_content(qb_store_path)
        if r.question_id == original.question_id
    ]
    assert all_versions == [1]
    assert len(_history_rows(db, original.question_id)) == 1  # just the initial draft


def test_noop_update_with_multiple_fields_all_matching_current(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid, tags=["a", "b"])
    _register(db, qb_store_path, original)

    result = service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(tags=["a", "b"], is_active=True),
        actor="editor1",
    )
    assert result.content_version == 1


# ---------------------------------------------------------------------
# 4. Not found
# ---------------------------------------------------------------------


def test_update_unknown_question_id_raises_not_found(db, qb_store_path):
    with pytest.raises(ContentNotFoundError):
        service.update_question(
            db,
            question_id="QB-DOES-NOT-EXIST",
            patch=QuestionPatch(is_active=False),
            actor="editor1",
        )


# ---------------------------------------------------------------------
# 5. Validation
# ---------------------------------------------------------------------


def test_update_empty_question_tr_is_rejected(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    with pytest.raises(QuestionBankValidationError):
        service.update_question(
            db,
            question_id=original.question_id,
            patch=QuestionPatch(question_tr=""),
            actor="editor1",
        )


def test_update_whitespace_only_question_tr_is_rejected(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    with pytest.raises(QuestionBankValidationError):
        service.update_question(
            db,
            question_id=original.question_id,
            patch=QuestionPatch(question_tr="              "),  # 14 chars, passes min_length
            actor="editor1",
        )


def test_update_invalid_enum_value_is_rejected_by_pydantic():
    with pytest.raises(ValidationError):
        QuestionPatch(difficulty="not_a_real_difficulty")


def test_update_numerical_without_tolerance_is_rejected(db, qb_store_path, unique_qid):
    original = _make_record(
        question_id=unique_qid,
        question_type=QuestionType.NUMERICAL,
        correct_answer=12.5,
        tolerance=0.5,
        options_tr=None,
        options_en=None,
    )
    _register(db, qb_store_path, original)

    # Clearing tolerance while staying numerical violates
    # validator.validate_record_structure's "numerical requires tolerance > 0" rule.
    with pytest.raises(QuestionBankValidationError):
        service.update_question(
            db,
            question_id=original.question_id,
            patch=QuestionPatch(tolerance=None),
            actor="editor1",
        )


# ---------------------------------------------------------------------
# 6. Duplicate content-version conflict (race condition)
# ---------------------------------------------------------------------


def test_two_updates_from_same_current_version_second_raises_conflict(
    db, qb_store_path, unique_qid, monkeypatch
):
    """Faz 2.9.3 kritik kontrol: aynı current version'dan (v1) başlayan
    iki bağımsız update denemesi -- ilki gerçekten v1 -> v2'ye başarıyla
    ilerler, ikincisi (aynı v1 taban alınarak, örn. iki mühendisin aynı
    anda v1'i açması senaryosu) v2'yi tekrar claim etmeye çalışır ve
    store'un append-only guard'ı yüzünden DuplicateContentVersionError
    ile çakışır -- silent overwrite asla olmaz."""
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    # First update: a genuine, unmodified call -- real v1 -> v2.
    first_result = service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(is_active=False),
        actor="writer-a",
    )
    assert first_result.content_version == 2

    # Second update is a *different* attempt that was also based on v1
    # (its own read happened before writer-a's write landed) -- simulate
    # that stale "current" resolution directly, since load_question_content
    # always resolves to the JSON store's true latest version and a
    # second real call would legitimately see v2, not reproduce the race.
    monkeypatch.setattr(
        service,
        "load_question_content_validated",
        lambda question_id, content_version=None: original,
    )

    with pytest.raises(DuplicateContentVersionError):
        service.update_question(
            db,
            question_id=original.question_id,
            patch=QuestionPatch(is_active=False, tags=["writer-b-edit"]),
            actor="writer-b",
        )

    # writer-a's v2 remains the one and only successful revision --
    # writer-b's conflicting attempt left no trace.
    all_versions = sorted(
        r.content_version
        for r in store.load_all_question_content(qb_store_path)
        if r.question_id == original.question_id
    )
    assert all_versions == [1, 2]


# ---------------------------------------------------------------------
# 7. Empty patch
# ---------------------------------------------------------------------


def test_empty_patch_is_rejected(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    with pytest.raises(QuestionBankValidationError):
        service.update_question(
            db,
            question_id=original.question_id,
            patch=QuestionPatch(),
            actor="editor1",
        )


# ---------------------------------------------------------------------
# 8. New version's lifecycle state, history, and version-before/-after
# ---------------------------------------------------------------------


def test_new_version_is_registered_as_draft_with_history_entry(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)
    service.submit_for_technical_review(
        db, question_id=original.question_id, content_version=1, actor="tester"
    )
    service.validate_question(
        db,
        question_id=original.question_id,
        content_version=1,
        actor="tester",
        actor_role="engineer",
        reviewed_by="reviewer1",
        review_date="2026-08-07",
        authorize=lambda role, action: True,
    )
    assert _status_of(db, original.question_id, 1) == ValidationStatus.VALIDATED.value

    service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(is_active=False),
        actor="editor1",
    )

    # v1's own lifecycle status is completely untouched by the update.
    assert _status_of(db, original.question_id, 1) == ValidationStatus.VALIDATED.value
    # v2 starts fresh as draft, exactly like any other newly registered version.
    assert _status_of(db, original.question_id, 2) == ValidationStatus.DRAFT.value

    rows = _history_rows(db, original.question_id)
    last = rows[-1]
    assert last["from_status"] is None
    assert last["to_status"] == ValidationStatus.DRAFT.value
    assert last["content_version_before"] == 1
    assert last["content_version_after"] == 2
    assert last["actor"] == "editor1"


# ---------------------------------------------------------------------
# 9. Retrieval reflects the update immediately
# ---------------------------------------------------------------------


def test_retrieval_reflects_updated_content_immediately(db, qb_store_path, unique_qid):
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(learning_objective="Güncellenmiş öğrenme hedefi."),
        actor="editor1",
    )

    # New draft version isn't publishable yet (safe default)...
    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, original.question_id, content_version=2, publishable_only=True)

    # ...but is immediately visible to a reviewer workspace that opts out
    # of the publishable-only default.
    fetched = retrieval.get_question(
        db, original.question_id, content_version=2, publishable_only=False
    )
    assert fetched.learning_objective == "Güncellenmiş öğrenme hedefi."

    # And list_questions(publishable_only=False) picks it up too.
    listed = retrieval.list_questions(db, publishable_only=False)
    v2 = [
        r
        for r in listed
        if r.question_id == original.question_id and r.content_version == 2
    ]
    assert len(v2) == 1
    assert v2[0].learning_objective == "Güncellenmiş öğrenme hedefi."


# ---------------------------------------------------------------------
# 10. JSON/SQLite partial-failure safety
# ---------------------------------------------------------------------


def test_sqlite_failure_triggers_json_compensation_no_orphan_remains(
    db, qb_store_path, monkeypatch, unique_qid
):
    """Faz 2.9.3 kritik kontrol: JSON append başarılı olur, SQLite
    lifecycle creation kontrollü olarak fail eder, operasyon
    PartialUpdateFailureError ile döner -- ve ardından JSON store'da
    yeni version'ın KALMADIĞI, lifecycle DB'de de yeni version
    olmadığı, eski latest version'ın (v1) değişmeden kaldığı ispatlanır
    (best-effort JSON compensation delete)."""
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    real_register_record = service.register_record

    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("simulated SQLite failure")

    monkeypatch.setattr(service, "register_record", _boom)

    with pytest.raises(PartialUpdateFailureError):
        service.update_question(
            db,
            question_id=original.question_id,
            patch=QuestionPatch(is_active=False),
            actor="editor1",
        )

    # No orphan in JSON: v2 was compensated away, only v1 remains.
    all_versions = [
        r.content_version
        for r in store.load_all_question_content(qb_store_path)
        if r.question_id == original.question_id
    ]
    assert all_versions == [1]
    with pytest.raises(ContentNotFoundError):
        store.load_question_content(original.question_id, 2, path=qb_store_path)

    # No lifecycle row and no status-history entry for v2 either.
    assert _status_of(db, original.question_id, 2) is None
    history = _history_rows(db, original.question_id)
    assert all(row["content_version_after"] != 2 for row in history)

    # The old latest version (v1) is completely unchanged.
    v1_after = store.load_question_content(original.question_id, 1, path=qb_store_path)
    assert v1_after == original

    # Restore the real register_record before retrying -- the simulated
    # failure above must not affect this recovery step (a targeted
    # setattr, not monkeypatch.undo(), since undo() would also revert
    # this test's qb_store_path JSON-isolation patch).
    monkeypatch.setattr(service, "register_record", real_register_record)

    # Since nothing was ever registered for v2, a fresh update call now
    # cleanly resolves "current" back to v1 and proceeds normally
    # (proves the compensation didn't leave the store in a state where
    # v2 shadows v1 or blocks future writes).
    retried = service.update_question(
        db,
        question_id=original.question_id,
        patch=QuestionPatch(is_active=False),
        actor="editor2",
    )
    assert retried.content_version == 2
    assert retried.is_active is False


def test_sqlite_failure_with_compensation_also_failing_is_reported_as_orphan_risk(
    db, qb_store_path, monkeypatch, unique_qid
):
    """Double-failure edge case: SQLite write fails AND the JSON
    compensating delete also fails. True cross-store atomicity is not
    achievable here -- this must not be hidden. The function still
    raises PartialUpdateFailureError (never swallows the failure), and
    the resulting orphan stays inert: it has no SQLite row, so it is
    excluded from every publishable-only read path by construction."""
    original = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, original)

    def _boom_sqlite(*args, **kwargs):
        raise sqlite3.OperationalError("simulated SQLite failure")

    def _boom_compensation(*args, **kwargs):
        raise OSError("simulated filesystem failure during compensation")

    monkeypatch.setattr(service, "register_record", _boom_sqlite)
    monkeypatch.setattr(service, "_delete_question_content_version", _boom_compensation)

    with pytest.raises(PartialUpdateFailureError):
        service.update_question(
            db,
            question_id=original.question_id,
            patch=QuestionPatch(is_active=False),
            actor="editor1",
        )

    # The orphan does exist this time (compensation itself failed)...
    v2_content = store.load_question_content(original.question_id, 2, path=qb_store_path)
    assert v2_content.is_active is False
    assert _status_of(db, original.question_id, 2) is None

    # ...but is still provably inert: never publishable, never returned
    # by a default (publishable_only=True) read.
    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, original.question_id, content_version=2, publishable_only=True)
    listed_default = retrieval.list_questions(db, publishable_only=True)
    assert not any(
        r.question_id == original.question_id and r.content_version == 2
        for r in listed_default
    )


# ---------------------------------------------------------------------
# 11. HTTP API
# ---------------------------------------------------------------------


def test_api_patch_requires_authentication(client):
    r = client.patch("/api/question-bank/questions/QB-DOES-NOT-EXIST", json={"is_active": False})
    assert r.status_code == 401


def test_api_patch_success(client, auth_headers, db, qb_store_path):
    original = _make_record(question_id="QB-API-UPD-00001")
    _register(db, qb_store_path, original)

    r = client.patch(
        f"/api/question-bank/questions/{original.question_id}",
        json={"difficulty": "advanced"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["content_version"] == 2
    assert body["difficulty"] == "advanced"
    assert body["question_tr"] == original.question_tr


def test_api_patch_partial_update_only_changes_given_fields(
    client, auth_headers, db, qb_store_path
):
    original = _make_record(question_id="QB-API-UPD-00002", tags=["a", "b"])
    _register(db, qb_store_path, original)

    r = client.patch(
        f"/api/question-bank/questions/{original.question_id}",
        json={"tags": ["c"]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tags"] == ["c"]
    assert body["technical_explanation_tr"] == original.technical_explanation_tr


def test_api_patch_invalid_body_is_422(client, auth_headers, db, qb_store_path):
    original = _make_record(question_id="QB-API-UPD-00003")
    _register(db, qb_store_path, original)

    r = client.patch(
        f"/api/question-bank/questions/{original.question_id}",
        json={"question_tr": ""},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_api_patch_empty_body_is_422(client, auth_headers, db, qb_store_path):
    original = _make_record(question_id="QB-API-UPD-00004")
    _register(db, qb_store_path, original)

    r = client.patch(
        f"/api/question-bank/questions/{original.question_id}",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_api_patch_immutable_field_in_body_is_422(client, auth_headers, db, qb_store_path):
    original = _make_record(question_id="QB-API-UPD-00005")
    _register(db, qb_store_path, original)

    r = client.patch(
        f"/api/question-bank/questions/{original.question_id}",
        json={"question_id": "QB-SHOULD-NOT-CHANGE", "is_active": False},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_api_patch_missing_id_is_404(client, auth_headers):
    r = client.patch(
        "/api/question-bank/questions/QB-DOES-NOT-EXIST-AT-ALL",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_api_patch_conflict_is_409(client, auth_headers, db, qb_store_path, monkeypatch):
    original = _make_record(question_id="QB-API-UPD-00006")
    _register(db, qb_store_path, original)
    other_v2 = original.model_copy(update={"content_version": 2, "is_active": False})
    store.save_question_content(other_v2, path=qb_store_path)
    service.register_question(
        db, question_id=other_v2.question_id, content_version=2, actor="other-writer"
    )
    # See test_concurrent_update_race_raises_duplicate_content_version's
    # comment for why a stale "current" read must be simulated directly.
    monkeypatch.setattr(
        service,
        "load_question_content_validated",
        lambda question_id, content_version=None: original,
    )

    r = client.patch(
        f"/api/question-bank/questions/{original.question_id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_api_get_after_patch_returns_updated_content(client, auth_headers, db, qb_store_path):
    original = _make_record(question_id="QB-API-UPD-00007")
    _register(db, qb_store_path, original)

    r = client.patch(
        f"/api/question-bank/questions/{original.question_id}",
        json={"learning_objective": "API üzerinden güncellenmiş hedef."},
        headers=auth_headers,
    )
    assert r.status_code == 200

    r_get = client.get(
        f"/api/question-bank/questions/{original.question_id}",
        params={"content_version": 2, "publishable_only": "false"},
        headers=auth_headers,
    )
    assert r_get.status_code == 200
    assert r_get.json()["learning_objective"] == "API üzerinden güncellenmiş hedef."
