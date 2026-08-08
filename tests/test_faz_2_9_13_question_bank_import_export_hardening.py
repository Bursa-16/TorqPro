"""Faz 2.9.13 -- Question Bank Import/Export Hardening & Audit.

This is a discovery/regression pass over the Faz 2.9.9 import/export
implementation (``backend/question_bank/import_export.py`` +
``backend/api/routes/question_bank.py``'s ``export_questions_route`` /
``import_questions_route``), not a new feature. Every edge case listed
in the Faz 2.9.13 scope was checked directly against the running
implementation before writing these assertions; no gap and no
protection failure was found -- every test below locks in already-
correct behaviour as an explicit regression, closing coverage gaps
``tests/test_faz_2_9_9_question_bank_import_export.py`` left open
rather than changing any production code. See this repo's
``backend/question_bank/import_export.py`` module docstring for the
full created/skipped/rejected contract these tests exercise.

Areas covered here that the Faz 2.9.9 test file did not already
exercise: enum/type rejections for every closed-vocabulary field
(category, difficulty, tags-shape, content_version bounds), an
unexpected extra field within one import item, cross-field structural
validator.py rejections reached through the HTTP import route
(correct_answer out of range, numerical-without-tolerance), an
unexpected top-level field on the request body itself, the exact
``MAX_BULK_ITEMS`` boundary (accepted, not just ``+1`` rejected),
same-batch duplicates whose *content* differs (not just identical
duplicates), Unicode/TR-EN character round-tripping through
import -> export, full export -> fresh-store re-import round-trip
consistency, deterministic export ordering under a combined filter
set, the ``publishable_only``/``validation_status`` interaction
documented in ``retrieval.list_questions`` as it applies to the export
route specifically, audit-trail (status-history) correctness for an
imported record, and that import never bypasses the draft-only
lifecycle/authorization gate a single-item create already enforces.
"""

from __future__ import annotations

import copy
import hashlib

import pytest

from backend.app import conn
from backend.question_bank import import_export as qb_import_export
from backend.question_bank import store
from backend.question_bank.bulk import MAX_BULK_ITEMS
from backend.question_bank.schema import (
    Category,
    Difficulty,
    EngineeringRiskLevel,
    QuestionType,
    SourceType,
    TraceabilityLevel,
)

# ---------------------------------------------------------------------
# Fixtures / helpers -- identical pattern to
# tests/test_faz_2_9_9_question_bank_import_export.py, duplicated
# (not imported) so this file stays independently runnable/removable,
# matching this suite's existing per-phase-file convention.
# ---------------------------------------------------------------------


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
    return "QB-C13-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


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
        "tags": ["c13test"],
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


def _import(client, auth_headers, questions):
    return client.post(
        "/api/question-bank/import", headers=auth_headers, json={"questions": questions}
    )


# ---------------------------------------------------------------------
# 1. Import -- closed-vocabulary / type / structural rejections not
#    already covered by the Faz 2.9.9 file (which only covers a
#    missing required field and a wrong scalar type).
# ---------------------------------------------------------------------


def test_import_invalid_category_enum_is_rejected(client, auth_headers, qb_store_path, unique_qid):
    payload = _valid_payload(unique_qid, category="not_a_real_category")
    r = _import(client, auth_headers, [payload])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rejected_count"] == 1
    assert body["created_count"] == 0
    assert "category" in body["rejected"][0]["reasons"][0]


def test_import_invalid_difficulty_enum_is_rejected(
    client, auth_headers, qb_store_path, unique_qid
):
    payload = _valid_payload(unique_qid, difficulty="impossible")
    r = _import(client, auth_headers, [payload])
    body = r.json()
    assert body["rejected_count"] == 1
    assert body["created_count"] == 0


def test_import_tags_wrong_shape_is_rejected(client, auth_headers, qb_store_path, unique_qid):
    """``tags`` must be a list -- a bare string (even one that looks
    like a comma-separated tag list) is a structural failure, not
    silently split/coerced."""
    payload = _valid_payload(unique_qid, tags="not-a-list")
    r = _import(client, auth_headers, [payload])
    body = r.json()
    assert body["rejected_count"] == 1
    assert body["created_count"] == 0
    assert "tags" in body["rejected"][0]["reasons"][0]


def test_import_content_version_zero_is_rejected(client, auth_headers, qb_store_path, unique_qid):
    payload = _valid_payload(unique_qid, content_version=0)
    r = _import(client, auth_headers, [payload])
    body = r.json()
    assert body["rejected_count"] == 1
    assert body["created_count"] == 0


def test_import_content_version_negative_is_rejected(
    client, auth_headers, qb_store_path, unique_qid
):
    payload = _valid_payload(unique_qid, content_version=-1)
    r = _import(client, auth_headers, [payload])
    body = r.json()
    assert body["rejected_count"] == 1


def test_import_unexpected_extra_field_within_item_is_rejected(
    client, auth_headers, qb_store_path, unique_qid
):
    """``QuestionRecord``'s ``extra='forbid'`` must reach import items
    too, not just single-item create -- an unknown key is a rejection,
    never silently dropped or silently accepted."""
    payload = _valid_payload(unique_qid)
    payload["this_field_does_not_exist"] = "x"
    r = _import(client, auth_headers, [payload])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rejected_count"] == 1
    assert body["created_count"] == 0
    assert any("this_field_does_not_exist" in reason for reason in body["rejected"][0]["reasons"])


def test_import_unexpected_top_level_field_is_422(client, auth_headers):
    """Unlike a malformed *item* (individually classified), an
    unexpected field on the request body itself must still fail fast
    with a standard 422 -- ``ImportQuestionsBody`` is
    ``extra='forbid'`` at the top level."""
    r = client.post(
        "/api/question-bank/import",
        headers=auth_headers,
        json={"questions": [], "unexpected_top_level_field": "x"},
    )
    assert r.status_code == 422


def test_import_correct_answer_out_of_range_is_rejected(
    client, auth_headers, qb_store_path, unique_qid
):
    """Cross-field validation from ``validator.validate_record_structure``
    (not just Pydantic shape) must also be reachable through the
    import path -- a structurally well-typed but semantically invalid
    ``correct_answer`` index must be rejected, not created."""
    payload = _valid_payload(unique_qid, correct_answer=99)  # options list only has 3 entries
    r = _import(client, auth_headers, [payload])
    body = r.json()
    assert body["rejected_count"] == 1
    assert body["created_count"] == 0
    assert "correct_answer" in body["rejected"][0]["reasons"][0]

    fetched = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    )
    assert fetched.status_code == 404


def test_import_numerical_without_tolerance_is_rejected(
    client, auth_headers, qb_store_path, unique_qid
):
    payload = _valid_payload(
        unique_qid, question_type=QuestionType.NUMERICAL.value, correct_answer=5.0, tolerance=None
    )
    r = _import(client, auth_headers, [payload])
    body = r.json()
    assert body["rejected_count"] == 1
    assert "tolerance" in body["rejected"][0]["reasons"][0]


# ---------------------------------------------------------------------
# 2. Batch-size boundary -- Faz 2.9.9 only tests MAX_BULK_ITEMS + 1;
#    the boundary itself (exactly MAX_BULK_ITEMS) must succeed.
# ---------------------------------------------------------------------


def test_import_exactly_max_bulk_items_is_accepted(client, auth_headers, qb_store_path, unique_qid):
    items = [_valid_payload(f"{unique_qid}-{i}") for i in range(MAX_BULK_ITEMS)]
    r = _import(client, auth_headers, items)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == MAX_BULK_ITEMS
    assert body["created_count"] == MAX_BULK_ITEMS
    assert body["rejected_count"] == 0
    assert body["skipped_count"] == 0


# ---------------------------------------------------------------------
# 3. Same-batch duplicates whose content differs -- Faz 2.9.9 only
#    tests two byte-identical duplicate items; a batch where the
#    second item shares (question_id, content_version) with the first
#    but carries genuinely different content must still be skipped,
#    never silently applied as an overwrite of the first item's
#    already-created content.
# ---------------------------------------------------------------------


def test_import_same_batch_duplicate_with_different_content_is_skipped_not_merged(
    client, auth_headers, qb_store_path, unique_qid
):
    first = _valid_payload(unique_qid, question_tr="İlk soru metni burada, on karakterden uzun.")
    second = _valid_payload(
        unique_qid, question_tr="İkinci ve farklı soru metni burada, tamamen değişik."
    )
    r = _import(client, auth_headers, [first, second])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_count"] == 1
    assert body["skipped_count"] == 1
    assert body["rejected_count"] == 0

    fetched = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false", headers=auth_headers
    )
    assert fetched.json()["question_tr"] == first["question_tr"], (
        "the second batch item's differing content must never overwrite the first"
    )


# ---------------------------------------------------------------------
# 4. Unicode / TR-EN character safety through the full import ->
#    export round trip (not just at the JSON-store layer, which
#    backend/question_bank/store.py's own ensure_ascii=False tests
#    already cover elsewhere -- this exercises the HTTP layer too).
# ---------------------------------------------------------------------


def test_import_export_roundtrip_preserves_unicode_content(
    client, auth_headers, qb_store_path, unique_qid
):
    tr_text = "Özgün soru metni: çğıöşü İĞÜŞÖÇ ĞŞ 中文字符 emoji 🔧🛠️ testi, on karakterden uzun."
    payload = _valid_payload(unique_qid, question_tr=tr_text)
    r = _import(client, auth_headers, [payload])
    assert r.json()["created_count"] == 1

    r2 = client.get(
        "/api/question-bank/export", headers=auth_headers, params={"publishable_only": "false"}
    )
    matches = [q for q in r2.json()["questions"] if q["question_id"] == unique_qid]
    assert len(matches) == 1
    assert matches[0]["question_tr"] == tr_text


# ---------------------------------------------------------------------
# 5. Full round-trip consistency: export a validated question, then
#    re-import the exact exported payload into a completely fresh
#    (empty) store -- must create cleanly with byte-for-byte content
#    parity, proving export's output is always valid import input.
# ---------------------------------------------------------------------


def test_export_output_is_valid_reimport_input_in_a_fresh_store(
    client, auth_headers, tmp_path, monkeypatch, unique_qid
):
    """Export from the session's shared store, then re-import the
    exact exported payload against a genuinely fresh SQLite connection
    (its own in-memory DB, migrated from scratch) and a genuinely
    fresh JSON content path -- not just a fresh JSON path against the
    same shared SQLite lifecycle DB, which would spuriously collide on
    the (question_id, content_version) pair already registered by this
    same test's own setup. Proves export's output is valid,
    self-contained import input in a truly independent environment."""
    import sqlite3

    source_path = tmp_path / "source_store.json"
    monkeypatch.setattr(store, "DATA_PATH", source_path)
    _create(client, auth_headers, unique_qid)
    _submit(client, auth_headers, unique_qid)
    _validate(client, auth_headers, unique_qid)

    exported = client.get(
        "/api/question-bank/export", headers=auth_headers, params={"publishable_only": "true"}
    ).json()
    assert exported["count"] == 1
    exported_question = exported["questions"][0]

    fresh_path = tmp_path / "fresh_store.json"
    monkeypatch.setattr(store, "DATA_PATH", fresh_path)
    fresh_db = sqlite3.connect(":memory:")
    try:
        store.migrate(fresh_db)
        result = qb_import_export.import_questions(
            fresh_db, records=[exported_question], actor="tester"
        )
    finally:
        fresh_db.close()

    assert len(result.created) == 1
    assert len(result.rejected) == 0
    assert result.created[0].question_id == unique_qid

    reimported = store.load_question_content(unique_qid, 1, path=fresh_path)
    assert reimported.question_tr == exported_question["question_tr"]


# ---------------------------------------------------------------------
# 6. Filter-combination and ordering guarantees at the export route
#    itself (not just at the underlying retrieval.list_questions unit
#    level, which is exercised by other phases' test files) -- these
#    lock in the public export contract this phase governs.
# ---------------------------------------------------------------------


def test_export_combined_filters_apply_as_logical_and(
    client, auth_headers, qb_store_path, unique_qid
):
    matching = unique_qid + "-MATCH"
    wrong_difficulty = unique_qid + "-WRONGDIFF"
    wrong_tag = unique_qid + "-WRONGTAG"

    _create(
        client,
        auth_headers,
        matching,
        difficulty=Difficulty.ADVANCED.value,
        tags=[unique_qid.lower(), "shared"],
    )
    _create(
        client,
        auth_headers,
        wrong_difficulty,
        difficulty=Difficulty.BEGINNER.value,
        tags=[unique_qid.lower(), "shared"],
    )
    _create(
        client,
        auth_headers,
        wrong_tag,
        difficulty=Difficulty.ADVANCED.value,
        tags=["unrelated-tag"],
    )

    r = client.get(
        "/api/question-bank/export",
        headers=auth_headers,
        params={
            "publishable_only": "false",
            "category": Category.TIGHTENING_TORQUE.value,
            "difficulty": Difficulty.ADVANCED.value,
            "tags": unique_qid.lower(),
        },
    )
    assert r.status_code == 200, r.text
    ids = {q["question_id"] for q in r.json()["questions"]}
    assert ids == {matching}


def test_export_deterministic_ordering_under_filters(
    client, auth_headers, qb_store_path, unique_qid
):
    for suffix in ("-Z", "-A", "-M"):
        _create(client, auth_headers, unique_qid + suffix, tags=[unique_qid.lower()])

    r1 = client.get(
        "/api/question-bank/export",
        headers=auth_headers,
        params={"publishable_only": "false", "tags": unique_qid.lower()},
    )
    r2 = client.get(
        "/api/question-bank/export",
        headers=auth_headers,
        params={"publishable_only": "false", "tags": unique_qid.lower()},
    )
    assert r1.text == r2.text
    ids = [q["question_id"] for q in r1.json()["questions"]]
    assert ids == sorted(ids)


def test_export_validation_status_filter_ignored_when_publishable_only_true(
    client, auth_headers, qb_store_path, unique_qid
):
    """Locks in ``retrieval.list_questions``'s documented contract
    (``publishable_only=True`` ignores an explicit ``validation_status``
    filter, since publishable already implies ``validated``) as it
    applies to the export route specifically -- passing a
    ``validation_status`` that could never coexist with
    ``publishable_only=True`` must not silently produce an
    always-empty result the caller can't explain."""
    _create(client, auth_headers, unique_qid)
    _submit(client, auth_headers, unique_qid)
    _validate(client, auth_headers, unique_qid)

    r = client.get(
        "/api/question-bank/export",
        headers=auth_headers,
        params={"publishable_only": "true", "validation_status": "draft"},
    )
    assert r.status_code == 200, r.text
    # publishable_only=True already means validated; the (contradictory)
    # validation_status='draft' filter is documented as ignored, not
    # ANDed in -- the validated question must still be present.
    ids = {q["question_id"] for q in r.json()["questions"]}
    assert unique_qid in ids


def test_export_validation_status_filter_applies_when_publishable_only_false(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)  # left in draft

    r = client.get(
        "/api/question-bank/export",
        headers=auth_headers,
        params={"publishable_only": "false", "validation_status": "validated"},
    )
    assert r.status_code == 200, r.text
    ids = {q["question_id"] for q in r.json()["questions"]}
    assert unique_qid not in ids  # still draft, not validated

    r2 = client.get(
        "/api/question-bank/export",
        headers=auth_headers,
        params={"publishable_only": "false", "validation_status": "draft"},
    )
    ids2 = {q["question_id"] for q in r2.json()["questions"]}
    assert unique_qid in ids2


# ---------------------------------------------------------------------
# 7. Audit-trail consistency and lifecycle/authorization non-bypass:
#    an imported question must produce exactly the same status-history
#    audit record a single-item create would, and must always land in
#    'draft' -- never any other lifecycle status, and never skipping
#    the authenticated actor's identity in the audit trail.
# ---------------------------------------------------------------------


def test_import_produces_correct_status_history_audit_record(
    client, auth_headers, qb_store_path, unique_qid
):
    r = _import(client, auth_headers, [_valid_payload(unique_qid)])
    assert r.json()["created_count"] == 1

    history = client.get(
        f"/api/question-bank/questions/{unique_qid}/status-history", headers=auth_headers
    )
    assert history.status_code == 200, history.text
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["from_status"] is None
    assert entries[0]["to_status"] == "draft"
    assert entries[0]["content_version_before"] is None
    assert entries[0]["content_version_after"] == 1
    assert entries[0]["actor"], "the audit record must attribute the authenticated importer"


def test_import_never_creates_a_record_outside_draft_status(
    client, auth_headers, qb_store_path, unique_qid
):
    """An imported record must always require the normal
    submit-for-review -> validate lifecycle afterwards -- import must
    never itself perform (or imply) a lifecycle transition beyond the
    initial draft registration every single-item create already does."""
    r = _import(client, auth_headers, [_valid_payload(unique_qid)])
    assert r.json()["created_count"] == 1

    # Not publishable yet (draft, not validated) -- proves import did
    # not sneak the record past submit-for-review/validate.
    exported = client.get(
        "/api/question-bank/export", headers=auth_headers, params={"publishable_only": "true"}
    ).json()
    assert unique_qid not in {q["question_id"] for q in exported["questions"]}

    # A lifecycle transition still requires the normal explicit calls --
    # import grants no shortcut around them.
    submit = client.post(
        f"/api/question-bank/questions/{unique_qid}/submit-for-review",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert submit.status_code == 200, submit.text


# ---------------------------------------------------------------------
# 8. Module-level: same-batch duplicate with different content,
#    exercised directly against import_questions (mirrors the Faz
#    2.9.9 file's own module-level transaction-safety tests) so the
#    guarantee is pinned independently of the HTTP layer too.
# ---------------------------------------------------------------------


def test_import_questions_module_level_duplicate_content_never_overwrites(qb_store_path, db):
    question_id = "QB-C13-MODULE-NOOVERWRITE"
    first = _valid_payload(question_id, question_tr="Orijinal içerik metni burada, uzun yeter.")
    second = _valid_payload(
        question_id, question_tr="Tamamen farklı ikinci içerik metni burada, uzun yeter."
    )

    result = qb_import_export.import_questions(db, records=[first, second], actor="tester")

    assert len(result.created) == 1
    assert len(result.skipped) == 1
    assert len(result.rejected) == 0

    stored = store.load_question_content(question_id, 1, path=qb_store_path)
    assert stored.question_tr == first["question_tr"]


def test_import_questions_empty_payload_returns_empty_result(qb_store_path, db):
    result = qb_import_export.import_questions(db, records=[], actor="tester")
    assert result.created == []
    assert result.skipped == []
    assert result.rejected == []


def test_import_questions_deepcopy_of_payload_does_not_affect_classification(
    qb_store_path, db
):
    """Sanity check that classification depends only on the item's own
    content, not on object identity -- a deep-copied duplicate of an
    already-imported record must still be recognized as a duplicate."""
    question_id = "QB-C13-DEEPCOPY"
    original = _valid_payload(question_id)
    qb_import_export.import_questions(db, records=[original], actor="tester")

    copy_of_original = copy.deepcopy(original)
    result = qb_import_export.import_questions(db, records=[copy_of_original], actor="tester")
    assert len(result.skipped) == 1
    assert len(result.created) == 0
