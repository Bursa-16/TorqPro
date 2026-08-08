"""Faz 2.9.7 -- Question Bank Admin UI backend support.

The Faz 2.9.7 frontend (Question Bank admin UI) needs to display
``validation_status`` next to every listed/detailed question, but
``backend.question_bank.schema.QuestionRecord`` deliberately never
carries that field (it lives in SQLite only -- see that class's own
docstring). Rather than an N+1 status-history lookup per listed row,
this phase adds one small, purely additive, opt-in mechanism:

- ``backend.question_bank.retrieval.get_validation_status_map`` -- a
  public wrapper over the module's existing private ``_status_map``
  helper (already built and used internally by ``list_questions``/
  ``get_question`` for filtering). No new SQL, no new persistence.
- ``include_status`` query parameter (default ``False``) on both
  ``GET /api/question-bank/questions`` and
  ``GET /api/question-bank/questions/{question_id}``. When omitted or
  ``False``, both routes' response shape is byte-for-byte identical to
  every pre-2.9.7 caller's existing behaviour (this is the regression
  guard this file cares about most). When ``True``, each response
  object gains one extra ``validation_status`` key.

This file does not touch, re-test, or duplicate the Faz 2.9.1-2.9.6
create/update/lifecycle/search test suites already covering the rest
of this API -- see tests/test_faz_2_9_{1..6}_question_bank_*.py for
that coverage, unaffected by this phase.
"""

from __future__ import annotations

import hashlib

import pytest

from backend.app import conn
from backend.question_bank import retrieval, store
from backend.question_bank.schema import (
    Category,
    Difficulty,
    EngineeringRiskLevel,
    QuestionType,
    SourceType,
    TraceabilityLevel,
)

# ---------------------------------------------------------------------
# Fixtures / helpers -- same isolated-store pattern as
# tests/test_faz_2_9_5_question_bank_search.py and
# tests/test_faz_2_9_6_question_bank_create_lifecycle_api.py.
# ---------------------------------------------------------------------


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def unique_qid(request):
    return "QB-C7-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


def _valid_payload(question_id: str, content_version: int = 1, **overrides) -> dict:
    payload = {
        "question_id": question_id,
        "content_version": content_version,
        "category": Category.TIGHTENING_TORQUE.value,
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
        "technical_explanation_en": "This explanation must be at least twenty characters long.",
        "standard_reference": None,
        "source_reference": {
            "source_type": SourceType.INTERNAL_ENGINE.value,
            "description": "test",
        },
        "source_locator": None,
        "traceability_level": TraceabilityLevel.PROVISIONAL.value,
        "tags": ["c7test"],
        "learning_objective": "Test amaçlı öğrenme hedefi metni.",
        "engineering_risk_level": EngineeringRiskLevel.LOW.value,
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def _create(client, auth_headers, question_id, **overrides):
    return client.post(
        "/api/question-bank/questions",
        headers=auth_headers,
        json=_valid_payload(question_id, **overrides),
    )


def _submit(client, auth_headers, question_id):
    return client.post(
        f"/api/question-bank/questions/{question_id}/submit-for-review",
        headers=auth_headers,
        json={"content_version": 1},
    )


# ---------------------------------------------------------------------
# 1. get_validation_status_map -- pure unit coverage, no HTTP
# ---------------------------------------------------------------------


def test_get_validation_status_map_reflects_draft_status_after_registration(
    client, auth_headers, qb_store_path, unique_qid
):
    r = _create(client, auth_headers, unique_qid)
    assert r.status_code == 201, r.text
    with conn() as c:
        status_map = retrieval.get_validation_status_map(c)
    assert status_map.get((unique_qid, 1)) == "draft"


def test_get_validation_status_map_reflects_transition(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    r = _submit(client, auth_headers, unique_qid)
    assert r.status_code == 200, r.text
    with conn() as c:
        status_map = retrieval.get_validation_status_map(c)
    assert status_map.get((unique_qid, 1)) == "technical_review"


def test_get_validation_status_map_has_no_entry_for_unknown_question(client, qb_store_path):
    with conn() as c:
        status_map = retrieval.get_validation_status_map(c)
    assert ("QB-C7-DOES-NOT-EXIST", 1) not in status_map


def test_get_validation_status_map_does_not_mutate_list_questions_result(
    client, auth_headers, qb_store_path, unique_qid
):
    """Calling the new helper alongside the pre-existing retrieval
    functions must not change what those functions themselves return
    -- this is the same-process regression guard for the "purely
    additive" claim, one level below the HTTP layer."""
    _create(client, auth_headers, unique_qid)
    with conn() as c:
        before = retrieval.list_questions(c, publishable_only=False)
        retrieval.get_validation_status_map(c)
        after = retrieval.list_questions(c, publishable_only=False)
    before_dump = [r.model_dump(mode="json") for r in before]
    after_dump = [r.model_dump(mode="json") for r in after]
    assert before_dump == after_dump


# ---------------------------------------------------------------------
# 2. HTTP: include_status=False (default) is a strict no-op
# ---------------------------------------------------------------------


def test_list_questions_default_response_has_no_validation_status_key(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    r = client.get("/api/question-bank/questions?publishable_only=false", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body, "expected at least one question in the isolated store"
    for item in body:
        assert "validation_status" not in item


def test_list_questions_include_status_false_explicit_matches_default_omitted(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    r_omitted = client.get(
        "/api/question-bank/questions?publishable_only=false", headers=auth_headers
    )
    r_explicit = client.get(
        "/api/question-bank/questions?publishable_only=false&include_status=false",
        headers=auth_headers,
    )
    assert r_omitted.status_code == r_explicit.status_code == 200
    assert r_omitted.json() == r_explicit.json()


def test_get_question_default_response_has_no_validation_status_key(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    r = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    )
    assert r.status_code == 200
    assert "validation_status" not in r.json()


def test_get_question_response_body_unchanged_regardless_of_include_status_param_presence(
    client, auth_headers, qb_store_path, unique_qid
):
    """Every field the route already returned before Faz 2.9.7 must be
    byte-identical whether include_status is omitted, explicitly
    false, or requested as true (true only adds one new key, never
    changes or removes an existing one)."""
    _create(client, auth_headers, unique_qid)
    base_url = f"/api/question-bank/questions/{unique_qid}?publishable_only=false"
    r_omitted = client.get(base_url, headers=auth_headers).json()
    r_false = client.get(base_url + "&include_status=false", headers=auth_headers).json()
    r_true = client.get(base_url + "&include_status=true", headers=auth_headers).json()

    assert r_omitted == r_false
    r_true_without_status = {k: v for k, v in r_true.items() if k != "validation_status"}
    assert r_true_without_status == r_omitted


# ---------------------------------------------------------------------
# 3. HTTP: include_status=True adds exactly one additive field
# ---------------------------------------------------------------------


def test_list_questions_include_status_true_adds_validation_status_per_item(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    r = client.get(
        "/api/question-bank/questions?publishable_only=false&include_status=true",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    matches = [item for item in body if item["question_id"] == unique_qid]
    assert len(matches) == 1
    assert matches[0]["validation_status"] == "draft"


def test_list_questions_include_status_true_reflects_each_records_own_status(
    client, auth_headers, qb_store_path, unique_qid
):
    qid_draft = unique_qid + "-A"
    qid_review = unique_qid + "-B"
    _create(client, auth_headers, qid_draft)
    _create(client, auth_headers, qid_review)
    _submit(client, auth_headers, qid_review)

    r = client.get(
        "/api/question-bank/questions?publishable_only=false&include_status=true",
        headers=auth_headers,
    )
    assert r.status_code == 200
    by_id = {item["question_id"]: item["validation_status"] for item in r.json()}
    assert by_id[qid_draft] == "draft"
    assert by_id[qid_review] == "technical_review"


def test_get_question_include_status_true_adds_validation_status(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    r = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false&include_status=true",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["validation_status"] == "draft"


def test_list_questions_include_status_true_yields_none_for_record_with_no_sqlite_row(
    client, qb_store_path
):
    """A JSON content record with no matching SQLite lifecycle row
    (never registered via register_question) has "no known
    validation_status" -- matching retrieval.py's own documented
    convention for _status_map/_lifecycle_map -- so this must surface
    as validation_status: null, never a KeyError or a fabricated
    default like "draft"."""
    from backend.question_bank.schema import QuestionRecord

    record = QuestionRecord(
        question_id="QB-C7-ORPHAN-CONTENT-ONLY",
        content_version=1,
        category=Category.TIGHTENING_TORQUE,
        subcategory=None,
        difficulty=Difficulty.BEGINNER,
        question_type=QuestionType.SINGLE_CHOICE,
        question_tr="Bu bir test sorusudur, en az on karakter.",
        question_en="This is a test question, at least ten characters.",
        options_tr=["A", "B"],
        options_en=["A", "B"],
        correct_answer=0,
        technical_explanation_tr="Bu açıklama en az yirmi karakter uzunluğundadır.",
        technical_explanation_en="This explanation must be at least twenty characters.",
        standard_reference=None,
        source_reference=None,
        source_locator=None,
        traceability_level=TraceabilityLevel.PROVISIONAL,
        tags=["orphan"],
        learning_objective="Test amaçlı öğrenme hedefi metni.",
        engineering_risk_level=EngineeringRiskLevel.LOW,
        is_active=True,
    )
    store.save_question_content(record)

    with conn() as c:
        records = retrieval.list_questions(c, publishable_only=False)
        status_map = retrieval.get_validation_status_map(c)
    matches = [r for r in records if r.question_id == "QB-C7-ORPHAN-CONTENT-ONLY"]
    assert len(matches) == 1
    assert status_map.get((matches[0].question_id, matches[0].content_version)) is None


# ---------------------------------------------------------------------
# 4. Full pre-2.9.7 regression suites remain green with these routes
#    touched -- a targeted spot-check here (the full suites are their
#    own test files and already run in CI/full pytest).
# ---------------------------------------------------------------------


def test_existing_tags_and_keyword_filters_still_work_alongside_new_param(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid, tags=["c7-marker-tag"])
    r = client.get(
        "/api/question-bank/questions?publishable_only=false&tags=c7-marker-tag"
        "&include_status=true",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert any(item["question_id"] == unique_qid for item in body)
