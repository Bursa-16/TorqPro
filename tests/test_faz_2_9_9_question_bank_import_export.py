"""Faz 2.9.9 -- Question Bank JSON Import/Export.

Covers: HTTP wiring for ``GET /api/question-bank/export`` and
``POST /api/question-bank/import`` (authentication, filter forwarding,
deterministic output, request-size cap, malformed-request-body 422);
per-record import classification (valid/missing-required-field/
duplicate-in-store/duplicate-within-batch/mixed batches); the
created/skipped/rejected result-count contract; that a partially
invalid import never mutates or removes any pre-existing record; and
the per-item JSON/SQLite transaction-safety (compensating delete on a
mid-import SQLite failure), tested directly against
``backend.question_bank.import_export.import_questions`` the same way
``tests/test_faz_2_9_1_question_bank_foundation.py`` tests transaction
rollback directly against the service layer.

No new persistence, no new content schema, no new validation rule is
introduced by this file's own assertions -- every test here exercises
Faz 2.9.9 code that itself only reuses
``backend.question_bank.retrieval.list_questions`` (export) and
``backend.question_bank.service.register_question_content`` /
``register_question`` (import), exactly as
``backend/question_bank/import_export.py``'s own module docstring
documents. See ``tests/test_faz_2_9_9_question_bank_import_export_
frontend.py`` for the Export/Import UI + TR/EN parity coverage.
"""

from __future__ import annotations

import hashlib

import pytest

from backend.app import conn
from backend.question_bank import import_export as qb_import_export
from backend.question_bank import store
from backend.question_bank.errors import ContentNotFoundError
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
# tests/test_faz_2_9_{5,6,7,8}_question_bank_*.py.
# ---------------------------------------------------------------------


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    """Direct SQLite connection to the already-migrated test DB, same
    as tests/test_faz_2_9_1_question_bank_foundation.py's own ``db``
    fixture -- used by the module-level (non-HTTP) transaction-safety
    test below."""
    with conn() as c:
        yield c


@pytest.fixture()
def unique_qid(request):
    return "QB-C9-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


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
        "tags": ["c9test"],
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


def _validate(client, auth_headers, question_id):
    return client.post(
        f"/api/question-bank/questions/{question_id}/validate",
        headers=auth_headers,
        json={"content_version": 1, "reviewed_by": "reviewer1", "review_date": "2026-01-01"},
    )


def _get_export(client, auth_headers, **params):
    r = client.get("/api/question-bank/export", headers=auth_headers, params=params)
    assert r.status_code == 200, r.text
    return r


# ---------------------------------------------------------------------
# 1. Export -- authentication, valid export, deterministic output,
#    filter forwarding.
# ---------------------------------------------------------------------


def test_export_requires_authentication(client):
    r = client.get("/api/question-bank/export")
    assert r.status_code == 401


def test_valid_export_includes_validated_question(client, auth_headers, qb_store_path, unique_qid):
    _create(client, auth_headers, unique_qid)
    _submit(client, auth_headers, unique_qid)
    _validate(client, auth_headers, unique_qid)

    r = _get_export(client, auth_headers, publishable_only="true")
    body = r.json()
    assert body["schema_version"] == 1
    assert body["count"] == 1
    assert body["questions"][0]["question_id"] == unique_qid
    assert body["questions"][0]["content_version"] == 1


def test_export_default_publishable_only_hides_draft(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)  # left in draft, never submitted/validated

    r = _get_export(client, auth_headers)  # publishable_only defaults true
    assert r.json()["count"] == 0

    r2 = _get_export(client, auth_headers, publishable_only="false")
    assert r2.json()["count"] == 1
    assert r2.json()["questions"][0]["question_id"] == unique_qid


def test_export_never_mutates_existing_records(client, auth_headers, qb_store_path, unique_qid):
    _create(client, auth_headers, unique_qid)
    before = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    ).json()

    _get_export(client, auth_headers, publishable_only="false")
    _get_export(client, auth_headers, publishable_only="false")

    after = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    ).json()
    assert before == after


def test_export_respects_tag_filter(client, auth_headers, qb_store_path, unique_qid):
    tagged_id, untagged_id = unique_qid + "-TAGGED", unique_qid + "-PLAIN"
    _create(client, auth_headers, tagged_id, tags=[unique_qid.lower(), "extra-tag"])
    _create(client, auth_headers, untagged_id, tags=["some-other-tag"])

    r = _get_export(client, auth_headers, tags=unique_qid.lower(), publishable_only="false")
    ids = {q["question_id"] for q in r.json()["questions"]}
    assert ids == {tagged_id}


def test_export_is_deterministic_across_repeated_calls(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid + "-A")
    _create(client, auth_headers, unique_qid + "-B")
    _create(client, auth_headers, unique_qid + "-C")

    r1 = _get_export(client, auth_headers, publishable_only="false")
    r2 = _get_export(client, auth_headers, publishable_only="false")
    r3 = _get_export(client, auth_headers, publishable_only="false")

    assert r1.text == r2.text == r3.text
    assert [q["question_id"] for q in r1.json()["questions"]] == sorted(
        q["question_id"] for q in r1.json()["questions"]
    )


# ---------------------------------------------------------------------
# 2. Import -- authentication, empty batch, invalid request body,
#    valid import, missing required fields, duplicates, mixed
#    batches, result counts, existing-records-preserved.
# ---------------------------------------------------------------------


def test_import_requires_authentication(client):
    r = client.post("/api/question-bank/import", json={"questions": []})
    assert r.status_code == 401


def test_import_empty_questions_list_is_a_valid_noop(client, auth_headers):
    r = client.post("/api/question-bank/import", headers=auth_headers, json={"questions": []})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "created_count": 0,
        "skipped_count": 0,
        "rejected_count": 0,
        "total": 0,
        "created": [],
        "skipped": [],
        "rejected": [],
    }


def test_import_malformed_json_request_body_is_422(client, auth_headers):
    headers = dict(auth_headers)
    headers["Content-Type"] = "application/json"
    r = client.post("/api/question-bank/import", headers=headers, content=b"{not valid json")
    assert r.status_code == 422


def test_import_non_list_questions_field_is_422(client, auth_headers):
    r = client.post(
        "/api/question-bank/import", headers=auth_headers, json={"questions": "not-a-list"}
    )
    assert r.status_code == 422


def test_import_too_many_items_is_422(client, auth_headers):
    from backend.question_bank.bulk import MAX_BULK_ITEMS

    items = [_valid_payload(f"QB-C9-CAP-{i}") for i in range(MAX_BULK_ITEMS + 1)]
    r = client.post("/api/question-bank/import", headers=auth_headers, json={"questions": items})
    assert r.status_code == 422


def test_valid_import_creates_new_question(client, auth_headers, qb_store_path, unique_qid):
    r = client.post(
        "/api/question-bank/import",
        headers=auth_headers,
        json={"questions": [_valid_payload(unique_qid)]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_count"] == 1
    assert body["skipped_count"] == 0
    assert body["rejected_count"] == 0
    assert body["total"] == 1
    assert body["created"] == [{"question_id": unique_qid, "content_version": 1}]

    fetched = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["question_tr"] == _valid_payload(unique_qid)["question_tr"]


def test_import_missing_required_field_is_rejected(client, auth_headers, qb_store_path, unique_qid):
    payload = _valid_payload(unique_qid)
    del payload["question_tr"]  # required field (min_length=10)

    r = client.post(
        "/api/question-bank/import", headers=auth_headers, json={"questions": [payload]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_count"] == 0
    assert body["rejected_count"] == 1
    assert body["total"] == 1
    assert "question_tr" in body["rejected"][0]["reasons"][0]

    fetched = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    )
    assert fetched.status_code == 404


def test_import_invalid_field_type_is_rejected(client, auth_headers, qb_store_path, unique_qid):
    payload = _valid_payload(unique_qid, content_version="not-an-int")
    r = client.post(
        "/api/question-bank/import", headers=auth_headers, json={"questions": [payload]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rejected_count"] == 1
    assert body["created_count"] == 0


def test_import_duplicate_of_existing_record_is_skipped(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    before = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    ).json()

    r = client.post(
        "/api/question-bank/import",
        headers=auth_headers,
        json={
            "questions": [
                _valid_payload(unique_qid, question_tr="Farklı bir soru metni burada.")
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_count"] == 0
    assert body["skipped_count"] == 1
    assert body["rejected_count"] == 0
    assert body["skipped"][0]["question_id"] == unique_qid

    after = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    ).json()
    assert before == after, (
        "the existing record must be completely untouched by a skipped import item"
    )


def test_import_duplicate_within_same_batch_is_skipped(
    client, auth_headers, qb_store_path, unique_qid
):
    payload = _valid_payload(unique_qid)
    r = client.post(
        "/api/question-bank/import",
        headers=auth_headers,
        json={"questions": [payload, dict(payload)]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_count"] == 1
    assert body["skipped_count"] == 1
    assert body["total"] == 2


def test_import_mixed_valid_invalid_duplicate_records(
    client, auth_headers, qb_store_path, unique_qid
):
    existing_id = unique_qid + "-EXISTING"
    new_id = unique_qid + "-NEW"
    invalid_id = unique_qid + "-INVALID"
    _create(client, auth_headers, existing_id)

    invalid_payload = _valid_payload(invalid_id)
    del invalid_payload["technical_explanation_en"]

    r = client.post(
        "/api/question-bank/import",
        headers=auth_headers,
        json={
            "questions": [
                _valid_payload(new_id),
                _valid_payload(existing_id),
                invalid_payload,
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_count"] == 1
    assert body["skipped_count"] == 1
    assert body["rejected_count"] == 1
    assert body["total"] == 3
    assert body["total"] == body["created_count"] + body["skipped_count"] + body["rejected_count"]
    assert body["created"][0]["question_id"] == new_id
    assert body["skipped"][0]["question_id"] == existing_id
    assert body["rejected"][0]["question_id"] == invalid_id


def test_import_result_counts_always_sum_to_total(client, auth_headers, qb_store_path, unique_qid):
    existing_id = unique_qid + "-DUP"
    _create(client, auth_headers, existing_id)
    bad = _valid_payload(unique_qid + "-BAD")
    del bad["learning_objective"]

    r = client.post(
        "/api/question-bank/import",
        headers=auth_headers,
        json={
            "questions": [
                _valid_payload(unique_qid + "-GOOD1"),
                _valid_payload(unique_qid + "-GOOD2"),
                _valid_payload(existing_id),
                bad,
            ]
        },
    )
    body = r.json()
    assert body["total"] == 4
    assert body["created_count"] + body["skipped_count"] + body["rejected_count"] == body["total"]
    assert body["created_count"] == 2
    assert body["skipped_count"] == 1
    assert body["rejected_count"] == 1


def test_import_does_not_disturb_unrelated_pre_existing_records(
    client, auth_headers, qb_store_path, unique_qid
):
    """A batch containing an invalid item must not affect any other,
    unrelated, already-existing record -- not just the record with the
    same question_id (covered by the duplicate test above)."""
    bystander_id = unique_qid + "-BYSTANDER"
    _create(client, auth_headers, bystander_id)
    before = client.get(
        f"/api/question-bank/questions/{bystander_id}?publishable_only=false", headers=auth_headers
    ).json()

    bad = _valid_payload(unique_qid + "-BAD2")
    del bad["question_en"]
    r = client.post(
        "/api/question-bank/import", headers=auth_headers, json={"questions": [bad]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["rejected_count"] == 1

    after = client.get(
        f"/api/question-bank/questions/{bystander_id}?publishable_only=false", headers=auth_headers
    ).json()
    assert before == after


# ---------------------------------------------------------------------
# 3. Transaction-safety: a mid-import SQLite registration failure must
#    compensate (delete) that item's own just-written JSON content --
#    never leave an orphan, never touch any other record. Exercised
#    directly against import_export.import_questions (not via HTTP),
#    the same way tests/test_faz_2_9_1_question_bank_foundation.py's
#    own "9. Transaction rollback" section tests service.py directly.
# ---------------------------------------------------------------------


def test_import_compensates_json_write_on_sqlite_registration_failure(qb_store_path, db):
    question_id = "QB-C9-ROLLBACK-TARGET"
    content_version = 1

    # Simulate a pre-existing orphaned SQLite lifecycle row for this
    # exact (question_id, content_version) with NO matching JSON
    # content -- store.register_record's own UNIQUE(question_id,
    # content_version) backstop will then reject import_questions'
    # own register_question() call for the same pair, even though the
    # JSON store legitimately does not have it yet (so Stage 1's
    # register_question_content() succeeds and only Stage 2 fails).
    store.register_record(
        db,
        question_id=question_id,
        content_version=content_version,
        now_iso="2026-01-01T00:00:00+00:00",
    )
    db.commit()

    result = qb_import_export.import_questions(
        db, records=[_valid_payload(question_id, content_version)], actor="tester"
    )

    assert len(result.created) == 0
    assert len(result.skipped) == 0
    assert len(result.rejected) == 1
    assert result.rejected[0].question_id == question_id

    # The compensating delete must have removed Stage 1's JSON write --
    # no orphan content_version left behind.
    with pytest.raises(ContentNotFoundError):
        store.load_question_content(question_id, content_version, path=qb_store_path)


def test_import_earlier_batch_item_survives_a_later_items_failure(qb_store_path, db):
    """Per-item atomicity, not whole-batch atomicity: an already
    created earlier item in the same import call must remain created
    even though a later item in that same call fails."""
    ok_id = "QB-C9-ROLLBACK-OK"
    bad_id = "QB-C9-ROLLBACK-BAD"

    # Pre-seed a conflicting SQLite row for `bad_id` only, so the
    # second item's Stage 2 registration fails while the first item's
    # Stage 1+2 both succeed normally.
    store.register_record(
        db, question_id=bad_id, content_version=1, now_iso="2026-01-01T00:00:00+00:00"
    )
    db.commit()

    result = qb_import_export.import_questions(
        db,
        records=[_valid_payload(ok_id), _valid_payload(bad_id)],
        actor="tester",
    )

    assert [o.question_id for o in result.created] == [ok_id]
    assert [o.question_id for o in result.rejected] == [bad_id]
    # The first item's content is genuinely committed, not compensated.
    assert store.load_question_content(ok_id, 1, path=qb_store_path).question_id == ok_id


def test_import_never_overwrites_existing_json_content(qb_store_path, db):
    """Belt-and-braces: even at the module level (bypassing the API's
    own duplicate skip), a second import attempt for the same
    (question_id, content_version) must never silently change the
    already-stored content -- it must be skipped, not merged/overwritten."""
    question_id = "QB-C9-NO-OVERWRITE"
    first = _valid_payload(
        question_id, question_tr="Orijinal soru metni burada, on karakterden uzun."
    )
    qb_import_export.import_questions(db, records=[first], actor="tester")

    second = _valid_payload(
        question_id, question_tr="Değiştirilmiş soru metni, farklı bir içerik burada."
    )
    result = qb_import_export.import_questions(db, records=[second], actor="tester")

    assert len(result.skipped) == 1
    stored = store.load_question_content(question_id, 1, path=qb_store_path)
    assert stored.question_tr == first["question_tr"]
