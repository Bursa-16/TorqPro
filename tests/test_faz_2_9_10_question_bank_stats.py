"""Faz 2.9.10 -- Question Bank statistics / coverage aggregation.

Covers: empty-bank baseline, total count, each of the four breakdowns
(``by_validation_status``/``by_category``/``by_difficulty``/
``by_question_type``) in isolation and combined, the deterministic
"unknown" bucket for a JSON-only record with no matching SQLite
lifecycle row (the one genuinely reachable "missing value" case --
see ``backend/question_bank/stats.py``'s own docstring), the fixed
deleted/archived exclusion semantics (excluded by default, matching
every other Question Bank read route's safe default), that the module
never invokes ``validate_publishable`` / applies any
``publishable_only`` filtering (no "publishable" count exists in the
response), the ``GET /api/question-bank/stats`` HTTP route's
authentication enforcement and response shape, that ``/stats`` is
never captured by the ``{question_id}``-shaped dynamic routes in this
module, and that no pre-existing Question Bank endpoint's behavior
regresses.

Same isolated-store pattern as
``tests/test_faz_2_9_{2,5,6,7,8,9}_question_bank_*.py``: every test
uses its own ``qb_store_path`` (never the shipped demo fixture) and a
per-test-unique ``question_id`` namespace (the shared SQLite test DB
from ``tests/conftest.py`` is never reset between tests).
"""

from __future__ import annotations

import hashlib

import pytest

from backend.app import conn
from backend.question_bank import retrieval, service, stats, store
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


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_stats_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    with conn() as c:
        yield c


@pytest.fixture()
def unique_qid(request):
    return "QB-C10-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


def _allow_all(role: str, action: str) -> bool:
    return True


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-C10-DEFAULT",
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


def _register_with_status(c, path, record, status: ValidationStatus, actor="tester"):
    """Same helper as ``tests/test_faz_2_9_2_question_bank_retrieval.py``'s
    own ``_register_with_status`` -- registers JSON content and drives
    the SQLite lifecycle row to ``status`` via legal transitions only."""
    store.save_question_content(record, path=path)
    service.register_question(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )
    if status == ValidationStatus.DRAFT:
        return
    service.submit_for_technical_review(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )
    if status == ValidationStatus.TECHNICAL_REVIEW:
        return
    if status == ValidationStatus.REJECTED:
        service.reject_question(
            c,
            question_id=record.question_id,
            content_version=record.content_version,
            actor=actor,
            actor_role="engineer",
            reason="Kaynak eksik, teknik olarak reddedildi.",
            authorize=_allow_all,
        )
        return
    service.validate_question(
        c,
        question_id=record.question_id,
        content_version=record.content_version,
        actor=actor,
        actor_role="engineer",
        reviewed_by="reviewer1",
        review_date="2026-08-08",
        authorize=_allow_all,
    )
    if status == ValidationStatus.VALIDATED:
        return
    if status == ValidationStatus.DEPRECATED:
        service.deprecate_question(
            c,
            question_id=record.question_id,
            content_version=record.content_version,
            actor=actor,
            actor_role="engineer",
            authorize=_allow_all,
        )
        return
    raise AssertionError(f"unsupported status in test helper: {status}")


# ---------------------------------------------------------------------
# 1. Module-level: compute_stats() -- empty bank, total, breakdowns.
# ---------------------------------------------------------------------


def test_empty_bank_returns_zero_total_and_empty_breakdowns(db, qb_store_path):
    result = stats.compute_stats(db)
    assert result == {
        "total": 0,
        "by_validation_status": {},
        "by_category": {},
        "by_difficulty": {},
        "by_question_type": {},
    }


def test_total_count_matches_number_of_registered_records(db, qb_store_path, unique_qid):
    for i in range(1, 4):
        r = _make_record(question_id=f"{unique_qid}-{i}", content_version=1)
        _register_with_status(db, qb_store_path, r, ValidationStatus.DRAFT)

    result = stats.compute_stats(db)
    assert result["total"] == 3


def test_by_validation_status_aggregation(db, qb_store_path, unique_qid):
    _register_with_status(
        db, qb_store_path, _make_record(question_id=f"{unique_qid}-D1", content_version=1),
        ValidationStatus.DRAFT,
    )
    _register_with_status(
        db, qb_store_path, _make_record(question_id=f"{unique_qid}-D2", content_version=1),
        ValidationStatus.DRAFT,
    )
    _register_with_status(
        db, qb_store_path, _make_record(question_id=f"{unique_qid}-V1", content_version=1),
        ValidationStatus.VALIDATED,
    )
    _register_with_status(
        db, qb_store_path, _make_record(question_id=f"{unique_qid}-R1", content_version=1),
        ValidationStatus.REJECTED,
    )

    result = stats.compute_stats(db)
    assert result["by_validation_status"] == {"draft": 2, "rejected": 1, "validated": 1}
    assert result["total"] == 4


def test_by_category_aggregation(db, qb_store_path, unique_qid):
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-1", category=Category.WASHERS),
        ValidationStatus.DRAFT,
    )
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-2", category=Category.WASHERS),
        ValidationStatus.DRAFT,
    )
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-3", category=Category.TIGHTENING_TORQUE),
        ValidationStatus.DRAFT,
    )

    result = stats.compute_stats(db)
    assert result["by_category"] == {
        "tightening_torque": 1,
        "washers": 2,
    }


def test_by_difficulty_aggregation(db, qb_store_path, unique_qid):
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-1", difficulty=Difficulty.EXPERT),
        ValidationStatus.DRAFT,
    )
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-2", difficulty=Difficulty.BEGINNER),
        ValidationStatus.DRAFT,
    )

    result = stats.compute_stats(db)
    assert result["by_difficulty"] == {"beginner": 1, "expert": 1}


def test_by_question_type_aggregation(db, qb_store_path, unique_qid):
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-1", question_type=QuestionType.NUMERICAL,
                     correct_answer=1.0, tolerance=0.1, options_tr=None, options_en=None),
        ValidationStatus.DRAFT,
    )
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-2", question_type=QuestionType.TRUE_FALSE,
                     correct_answer=True, options_tr=None, options_en=None),
        ValidationStatus.DRAFT,
    )
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-3", question_type=QuestionType.TRUE_FALSE,
                     correct_answer=False, options_tr=None, options_en=None),
        ValidationStatus.DRAFT,
    )

    result = stats.compute_stats(db)
    assert result["by_question_type"] == {"numerical": 1, "true_false": 2}


def test_mixed_records_all_four_breakdowns_consistent(db, qb_store_path, unique_qid):
    _register_with_status(
        db, qb_store_path,
        _make_record(
            question_id=f"{unique_qid}-1",
            category=Category.WASHERS,
            difficulty=Difficulty.ADVANCED,
            question_type=QuestionType.MULTIPLE_CHOICE,
            correct_answer=[0, 1],
        ),
        ValidationStatus.VALIDATED,
    )
    _register_with_status(
        db, qb_store_path,
        _make_record(
            question_id=f"{unique_qid}-2",
            category=Category.THREAD_GEOMETRY,
            difficulty=Difficulty.BEGINNER,
            question_type=QuestionType.SINGLE_CHOICE,
        ),
        ValidationStatus.DRAFT,
    )

    result = stats.compute_stats(db)
    assert result["total"] == 2
    assert result["by_validation_status"] == {"draft": 1, "validated": 1}
    assert result["by_category"] == {"thread_geometry": 1, "washers": 1}
    assert result["by_difficulty"] == {"advanced": 1, "beginner": 1}
    assert result["by_question_type"] == {"multiple_choice": 1, "single_choice": 1}


def test_missing_validation_status_falls_into_unknown_bucket(db, qb_store_path, unique_qid):
    """A JSON content record that was saved but never registered in
    SQLite (no lifecycle row at all) has no known ``validation_status``
    -- ``retrieval._status_map``'s own documented "no entry == unknown"
    convention. ``list_questions(publishable_only=False)`` still
    returns it (there is no status filter applied), so it must be
    counted under the deterministic unknown bucket rather than silently
    dropped."""
    record = _make_record(question_id=unique_qid, content_version=1)
    store.save_question_content(record, path=qb_store_path)
    # Deliberately never call service.register_question -- no SQLite row.

    result = stats.compute_stats(db)
    assert result["total"] == 1
    assert result["by_validation_status"] == {stats.UNKNOWN_BUCKET: 1}
    assert result["by_validation_status"] == {"unknown": 1}


# ---------------------------------------------------------------------
# 2. Deleted / archived semantics -- excluded by default, fixed by test.
# ---------------------------------------------------------------------


def test_soft_deleted_record_excluded_from_stats(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid, content_version=1)
    _register_with_status(db, qb_store_path, record, ValidationStatus.DRAFT)
    assert stats.compute_stats(db)["total"] == 1

    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin",
        authorize=_allow_all,
    )

    result = stats.compute_stats(db)
    assert result["total"] == 0
    assert result["by_validation_status"] == {}


def test_archived_record_excluded_from_stats(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid, content_version=1)
    _register_with_status(db, qb_store_path, record, ValidationStatus.DRAFT)
    assert stats.compute_stats(db)["total"] == 1

    service.archive_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin",
        authorize=_allow_all,
    )

    result = stats.compute_stats(db)
    assert result["total"] == 0


def test_restored_record_reappears_in_stats(db, qb_store_path, unique_qid):
    record = _make_record(question_id=unique_qid, content_version=1)
    _register_with_status(db, qb_store_path, record, ValidationStatus.DRAFT)

    service.delete_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin",
        authorize=_allow_all,
    )
    assert stats.compute_stats(db)["total"] == 0

    service.restore_question(
        db, question_id=unique_qid, actor="tester", actor_role="admin",
        authorize=_allow_all,
    )
    assert stats.compute_stats(db)["total"] == 1


# ---------------------------------------------------------------------
# 3. No "publishable" filtering -- draft/rejected/deprecated/inactive
#    records all counted, matching the explicit Faz 2.9.10 scope lock.
# ---------------------------------------------------------------------


def test_non_publishable_records_are_still_counted(db, qb_store_path, unique_qid):
    """Draft, rejected, deprecated, and inactive-but-validated records
    are all invisible to the default (``publishable_only=True``)
    listing route, but stats must still count every one of them --
    this module never applies ``publishable_only`` filtering."""
    _register_with_status(
        db, qb_store_path, _make_record(question_id=f"{unique_qid}-DRAFT"),
        ValidationStatus.DRAFT,
    )
    _register_with_status(
        db, qb_store_path, _make_record(question_id=f"{unique_qid}-REJ"),
        ValidationStatus.REJECTED,
    )
    _register_with_status(
        db, qb_store_path, _make_record(question_id=f"{unique_qid}-DEP"),
        ValidationStatus.DEPRECATED,
    )
    _register_with_status(
        db, qb_store_path,
        _make_record(question_id=f"{unique_qid}-INACTIVE", is_active=False),
        ValidationStatus.VALIDATED,
    )

    # Sanity: none of these are publishable via the existing route.
    publishable = retrieval.list_questions(db, publishable_only=True)
    publishable_ids = {r.question_id for r in publishable}
    assert not publishable_ids & {
        f"{unique_qid}-DRAFT", f"{unique_qid}-REJ", f"{unique_qid}-DEP", f"{unique_qid}-INACTIVE"
    }

    result = stats.compute_stats(db)
    assert result["total"] == 4
    assert result["by_validation_status"] == {
        "deprecated": 1, "draft": 1, "rejected": 1, "validated": 1
    }


def test_response_has_no_publishable_count(db, qb_store_path):
    result = stats.compute_stats(db)
    assert "publishable" not in result
    assert "publishable_count" not in result
    assert set(result.keys()) == {
        "total", "by_validation_status", "by_category", "by_difficulty", "by_question_type",
    }


# ---------------------------------------------------------------------
# 4. HTTP route -- GET /api/question-bank/stats
# ---------------------------------------------------------------------


def test_stats_route_requires_authentication(client):
    r = client.get("/api/question-bank/stats")
    assert r.status_code == 401


def test_stats_route_returns_expected_shape(client, auth_headers, qb_store_path, unique_qid):
    r = client.post(
        "/api/question-bank/questions",
        headers=auth_headers,
        json={
            "question_id": unique_qid,
            "content_version": 1,
            "category": Category.WASHERS.value,
            "subcategory": None,
            "difficulty": Difficulty.BEGINNER.value,
            "question_type": QuestionType.SINGLE_CHOICE.value,
            "question_tr": "Bu bir test sorusudur, en az on karakter.",
            "question_en": "This is a test question, at least ten characters.",
            "options_tr": ["A", "B", "C"],
            "options_en": ["A", "B", "C"],
            "correct_answer": 0,
            "tolerance": None,
            "technical_explanation_tr": "Bu açıklama en az yirmi karakter uzunluğundadır.",
            "technical_explanation_en": "This explanation must be at least twenty characters.",
            "standard_reference": None,
            "source_reference": {
                "source_type": SourceType.INTERNAL_ENGINE.value,
                "description": "test",
            },
            "source_locator": None,
            "traceability_level": TraceabilityLevel.PROVISIONAL.value,
            "tags": ["c10test"],
            "learning_objective": "Test amaçlı öğrenme hedefi metni.",
            "engineering_risk_level": EngineeringRiskLevel.LOW.value,
            "is_active": True,
        },
    )
    assert r.status_code == 201, r.text

    r = client.get("/api/question-bank/stats", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "total", "by_validation_status", "by_category", "by_difficulty", "by_question_type",
    }
    assert isinstance(body["total"], int)
    assert body["total"] >= 1
    assert body["by_category"].get("washers", 0) >= 1
    assert body["by_difficulty"].get("beginner", 0) >= 1
    assert body["by_question_type"].get("single_choice", 0) >= 1
    assert body["by_validation_status"].get("draft", 0) >= 1


def test_stats_route_not_shadowed_by_question_id_route(client, auth_headers):
    """``GET /api/question-bank/stats`` must resolve to the stats
    aggregation, never be captured as ``question_id="stats"`` by any
    ``{question_id}``-shaped dynamic route in this module."""
    r = client.get("/api/question-bank/stats", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # A question_id lookup response would have a "question_tr" field
    # and no "total" field; the stats response must have neither of
    # that shape's markers and must have this one.
    assert "question_tr" not in body
    assert "total" in body


# ---------------------------------------------------------------------
# 5. Regression -- pre-existing endpoints unaffected.
# ---------------------------------------------------------------------


def test_existing_list_questions_route_unaffected(client, auth_headers, qb_store_path):
    r = client.get("/api/question-bank/questions", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_existing_export_route_unaffected(client, auth_headers, qb_store_path):
    r = client.get("/api/question-bank/export", headers=auth_headers, params={
        "publishable_only": "false",
    })
    assert r.status_code == 200
    body = r.json()
    assert "schema_version" in body and "questions" in body
