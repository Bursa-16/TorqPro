"""Faz 2.9.8 -- Question Bank Bulk Lifecycle Transition + Bulk Tag
Add/Remove HTTP API.

Covers: bulk submit-for-review/validate/reject/deprecate/archive over
several ``(question_id, content_version)`` items in one request;
authorization checked once up front for gated actions (an unauthorized
actor's request touches zero items, never a partial application);
per-item partial success/failure (one item's 404/409-equivalent
failure never aborts the rest of the batch); action-specific required
fields (reviewed_by/review_date for validate, reason for reject,
content_version for every non-archive action) enforced as 422 before
any DB access; bulk tag add/remove over several question_ids sharing
the exact versioning/no-op semantics of the existing single-item PATCH
route; unauthenticated (401) access to both new routes; and the
request-size cap (``backend.question_bank.bulk.MAX_BULK_ITEMS``).

No new persistence, no new transition rule, no new authorization
mechanism -- every test below exercises HTTP routes that are thin
sequencing wrappers over the exact same
backend.question_bank.service functions Faz 2.9.1/2.9.3/2.9.4/2.9.6's
own tests already cover individually (submit_for_technical_review,
validate_question, reject_question, deprecate_question,
archive_question, update_question). This file does not re-test those
functions' own single-item behaviour -- see
tests/test_faz_2_9_{3,4,6}_question_bank_*.py for that coverage,
unaffected by this phase.
"""

from __future__ import annotations

import hashlib

import pytest

from backend.question_bank import store
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
# tests/test_faz_2_9_{5,6,7}_question_bank_*.py.
# ---------------------------------------------------------------------


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def unique_qid(request):
    return "QB-C8-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


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
        "tags": ["c8test"],
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


def _create_submit_validate(client, auth_headers, question_id):
    _create(client, auth_headers, question_id)
    _submit(client, auth_headers, question_id)
    return client.post(
        f"/api/question-bank/questions/{question_id}/validate",
        headers=auth_headers,
        json={"content_version": 1, "reviewed_by": "reviewer1", "review_date": "2026-01-01"},
    )


def _viewer_headers(client, auth_headers, login_as, suffix):
    username = f"c8_viewer_{suffix}"
    client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "display_name": "Faz 2.9.8 Viewer",
            "password": "viewerpass1",
            "role": "viewer",
        },
    )
    return login_as(username, "viewerpass1")


def _status_of(client, auth_headers, question_id):
    r = client.get(
        f"/api/question-bank/questions/{question_id}"
        "?publishable_only=false&include_status=true",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["validation_status"]


# ---------------------------------------------------------------------
# 1. Bulk transition -- authentication
# ---------------------------------------------------------------------


def test_bulk_transition_requires_authentication(client, unique_qid):
    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        json={
            "action": "submit-for-review",
            "items": [{"question_id": unique_qid, "content_version": 1}],
        },
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------
# 2. Bulk submit-for-review -- ungated, all-success + partial-success
# ---------------------------------------------------------------------


def test_bulk_submit_for_review_all_succeed(client, auth_headers, qb_store_path, unique_qid):
    qid_a, qid_b = unique_qid + "-A", unique_qid + "-B"
    _create(client, auth_headers, qid_a)
    _create(client, auth_headers, qid_b)

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "submit-for-review",
            "items": [
                {"question_id": qid_a, "content_version": 1},
                {"question_id": qid_b, "content_version": 1},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["succeeded_count"] == 2
    assert body["failed_count"] == 0
    assert {o["question_id"] for o in body["succeeded"]} == {qid_a, qid_b}
    assert _status_of(client, auth_headers, qid_a) == "technical_review"
    assert _status_of(client, auth_headers, qid_b) == "technical_review"


def test_bulk_submit_for_review_partial_success(client, auth_headers, qb_store_path, unique_qid):
    qid_ok, qid_already = unique_qid + "-OK", unique_qid + "-ALREADY"
    _create(client, auth_headers, qid_ok)
    _create(client, auth_headers, qid_already)
    _submit(client, auth_headers, qid_already)  # already technical_review before the bulk call

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "submit-for-review",
            "items": [
                {"question_id": qid_ok, "content_version": 1},
                {"question_id": qid_already, "content_version": 1},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["succeeded_count"] == 1
    assert body["failed_count"] == 1
    assert body["succeeded"][0]["question_id"] == qid_ok
    assert body["failed"][0]["question_id"] == qid_already
    assert "error" in body["failed"][0]
    # The already-submitted question's state must be unaffected by the
    # failed re-submission attempt.
    assert _status_of(client, auth_headers, qid_already) == "technical_review"


def test_bulk_transition_unknown_question_id_is_a_failed_item_not_an_http_404(
    client, auth_headers, qb_store_path, unique_qid
):
    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "submit-for-review",
            "items": [{"question_id": "QB-C8-DOES-NOT-EXIST", "content_version": 1}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded_count"] == 0
    assert body["failed_count"] == 1


def test_bulk_transition_empty_items_is_422(client, auth_headers):
    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={"action": "submit-for-review", "items": []},
    )
    assert r.status_code == 422


def test_bulk_transition_missing_content_version_is_422(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={"action": "submit-for-review", "items": [{"question_id": unique_qid}]},
    )
    assert r.status_code == 422


def test_bulk_transition_too_many_items_is_422(client, auth_headers):
    from backend.question_bank.bulk import MAX_BULK_ITEMS

    items = [
        {"question_id": f"QB-C8-BULK-{i}", "content_version": 1} for i in range(MAX_BULK_ITEMS + 1)
    ]
    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={"action": "submit-for-review", "items": items},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------
# 3. Bulk validate -- gated, requires reviewed_by/review_date
# ---------------------------------------------------------------------


def test_bulk_validate_all_succeed(client, auth_headers, qb_store_path, unique_qid):
    qid_a, qid_b = unique_qid + "-A", unique_qid + "-B"
    _create(client, auth_headers, qid_a)
    _submit(client, auth_headers, qid_a)
    _create(client, auth_headers, qid_b)
    _submit(client, auth_headers, qid_b)

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "validate",
            "items": [
                {"question_id": qid_a, "content_version": 1},
                {"question_id": qid_b, "content_version": 1},
            ],
            "reviewed_by": "reviewer1",
            "review_date": "2026-01-01",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded_count"] == 2
    assert _status_of(client, auth_headers, qid_a) == "validated"
    assert _status_of(client, auth_headers, qid_b) == "validated"


def test_bulk_validate_missing_reviewed_by_is_422(client, auth_headers, qb_store_path, unique_qid):
    _create(client, auth_headers, unique_qid)
    _submit(client, auth_headers, unique_qid)
    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "validate",
            "items": [{"question_id": unique_qid, "content_version": 1}],
            "review_date": "2026-01-01",
        },
    )
    assert r.status_code == 422


def test_bulk_validate_by_viewer_role_is_403_and_touches_zero_items(
    client, auth_headers, login_as, qb_store_path, unique_qid
):
    qid_a, qid_b = unique_qid + "-A", unique_qid + "-B"
    _create(client, auth_headers, qid_a)
    _submit(client, auth_headers, qid_a)
    _create(client, auth_headers, qid_b)
    _submit(client, auth_headers, qid_b)
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "bulkvalidate")

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=viewer_headers,
        json={
            "action": "validate",
            "items": [
                {"question_id": qid_a, "content_version": 1},
                {"question_id": qid_b, "content_version": 1},
            ],
            "reviewed_by": "reviewer1",
            "review_date": "2026-01-01",
        },
    )
    assert r.status_code == 403

    # Neither item may have been touched -- both must remain
    # technical_review, not validated.
    assert _status_of(client, auth_headers, qid_a) == "technical_review"
    assert _status_of(client, auth_headers, qid_b) == "technical_review"


# ---------------------------------------------------------------------
# 4. Bulk reject -- gated, requires reason
# ---------------------------------------------------------------------


def test_bulk_reject_all_succeed(client, auth_headers, qb_store_path, unique_qid):
    _create(client, auth_headers, unique_qid)
    _submit(client, auth_headers, unique_qid)

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "reject",
            "items": [{"question_id": unique_qid, "content_version": 1}],
            "reason": "Teknik inceleme kriterlerini karşılamıyor.",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["succeeded_count"] == 1
    assert _status_of(client, auth_headers, unique_qid) == "rejected"


def test_bulk_reject_missing_reason_is_422(client, auth_headers, qb_store_path, unique_qid):
    _create(client, auth_headers, unique_qid)
    _submit(client, auth_headers, unique_qid)
    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={"action": "reject", "items": [{"question_id": unique_qid, "content_version": 1}]},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------
# 5. Bulk deprecate -- gated
# ---------------------------------------------------------------------


def test_bulk_deprecate_all_succeed(client, auth_headers, qb_store_path, unique_qid):
    _create_submit_validate(client, auth_headers, unique_qid)

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "deprecate",
            "items": [{"question_id": unique_qid, "content_version": 1}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["succeeded_count"] == 1
    assert _status_of(client, auth_headers, unique_qid) == "deprecated"


def test_bulk_deprecate_by_viewer_role_is_403(
    client, auth_headers, login_as, qb_store_path, unique_qid
):
    _create_submit_validate(client, auth_headers, unique_qid)
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "bulkdeprecate")

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=viewer_headers,
        json={"action": "deprecate", "items": [{"question_id": unique_qid, "content_version": 1}]},
    )
    assert r.status_code == 403
    assert _status_of(client, auth_headers, unique_qid) == "validated"


# ---------------------------------------------------------------------
# 6. Bulk archive -- whole-question action, content_version not required
# ---------------------------------------------------------------------


def test_bulk_archive_all_succeed_without_content_version(
    client, auth_headers, qb_store_path, unique_qid
):
    qid_a, qid_b = unique_qid + "-A", unique_qid + "-B"
    _create(client, auth_headers, qid_a)
    _create(client, auth_headers, qid_b)

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "archive",
            "items": [{"question_id": qid_a}, {"question_id": qid_b}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded_count"] == 2

    r_get = client.get(
        f"/api/question-bank/questions/{qid_a}?publishable_only=false&include_archived=true",
        headers=auth_headers,
    )
    assert r_get.status_code == 200


def test_bulk_archive_by_viewer_role_is_403_and_touches_zero_items(
    client, auth_headers, login_as, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "bulkarchive")

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=viewer_headers,
        json={"action": "archive", "items": [{"question_id": unique_qid}]},
    )
    assert r.status_code == 403

    r_audit = client.get(
        f"/api/question-bank/questions/{unique_qid}/audit", headers=auth_headers
    )
    assert r_audit.json() == []


def test_bulk_archive_partial_success_one_already_archived(
    client, auth_headers, qb_store_path, unique_qid
):
    qid_fresh, qid_archived = unique_qid + "-FRESH", unique_qid + "-ARCHIVED"
    _create(client, auth_headers, qid_fresh)
    _create(client, auth_headers, qid_archived)
    r_pre_archive = client.post(
        f"/api/question-bank/{qid_archived}/archive", headers=auth_headers
    )
    assert r_pre_archive.status_code == 200, r_pre_archive.text

    r = client.post(
        "/api/question-bank/questions/bulk/transition",
        headers=auth_headers,
        json={
            "action": "archive",
            "items": [{"question_id": qid_fresh}, {"question_id": qid_archived}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded_count"] == 1
    assert body["failed_count"] == 1
    assert body["succeeded"][0]["question_id"] == qid_fresh
    assert body["failed"][0]["question_id"] == qid_archived


# ---------------------------------------------------------------------
# 7. Bulk tags -- authentication, add/remove, partial success
# ---------------------------------------------------------------------


def test_bulk_tags_requires_authentication(client, unique_qid):
    r = client.post(
        "/api/question-bank/questions/bulk/tags",
        json={"question_ids": [unique_qid], "add": ["iso"]},
    )
    assert r.status_code == 401


def test_bulk_tags_add_succeeds_for_multiple_questions(
    client, auth_headers, qb_store_path, unique_qid
):
    qid_a, qid_b = unique_qid + "-A", unique_qid + "-B"
    _create(client, auth_headers, qid_a, tags=["existing"])
    _create(client, auth_headers, qid_b, tags=[])

    r = client.post(
        "/api/question-bank/questions/bulk/tags",
        headers=auth_headers,
        json={"question_ids": [qid_a, qid_b], "add": ["iso16047", "torque"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded_count"] == 2
    by_id = {o["question_id"]: o for o in body["succeeded"]}
    assert set(t.lower() for t in by_id[qid_a]["tags"]) >= {"existing", "iso16047", "torque"}
    assert set(t.lower() for t in by_id[qid_b]["tags"]) == {"iso16047", "torque"}

    # New content_version created for each (a real content change).
    assert by_id[qid_a]["content_version"] == 2
    assert by_id[qid_b]["content_version"] == 2


def test_bulk_tags_remove_succeeds(client, auth_headers, qb_store_path, unique_qid):
    _create(client, auth_headers, unique_qid, tags=["remove-me", "keep-me"])

    r = client.post(
        "/api/question-bank/questions/bulk/tags",
        headers=auth_headers,
        json={"question_ids": [unique_qid], "remove": ["remove-me"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded_count"] == 1
    assert body["succeeded"][0]["tags"] == ["keep-me"]


def test_bulk_tags_add_is_case_insensitive_no_op_when_already_present(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid, tags=["ISO 16047"])

    r = client.post(
        "/api/question-bank/questions/bulk/tags",
        headers=auth_headers,
        json={"question_ids": [unique_qid], "add": ["iso 16047"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded_count"] == 1
    # No-op: stored casing is unchanged, no new content_version.
    assert body["succeeded"][0]["tags"] == ["ISO 16047"]
    assert body["succeeded"][0]["content_version"] == 1


def test_bulk_tags_neither_add_nor_remove_is_422(client, auth_headers, unique_qid):
    r = client.post(
        "/api/question-bank/questions/bulk/tags",
        headers=auth_headers,
        json={"question_ids": [unique_qid]},
    )
    assert r.status_code == 422


def test_bulk_tags_empty_question_ids_is_422(client, auth_headers):
    r = client.post(
        "/api/question-bank/questions/bulk/tags",
        headers=auth_headers,
        json={"question_ids": [], "add": ["iso"]},
    )
    assert r.status_code == 422


def test_bulk_tags_partial_success_one_unknown_question(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid, tags=[])

    r = client.post(
        "/api/question-bank/questions/bulk/tags",
        headers=auth_headers,
        json={"question_ids": [unique_qid, "QB-C8-DOES-NOT-EXIST"], "add": ["iso"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded_count"] == 1
    assert body["failed_count"] == 1
    assert body["succeeded"][0]["question_id"] == unique_qid
    assert body["failed"][0]["question_id"] == "QB-C8-DOES-NOT-EXIST"


def test_bulk_tags_not_role_gated_any_authenticated_user_may_call(
    client, auth_headers, login_as, qb_store_path, unique_qid
):
    """Matches the existing single-item PATCH route's own behaviour --
    content editing (including tags) has never been role-gated in this
    module; only lifecycle *transitions* are (see
    backend.question_bank.service.AUTHORIZATION_REQUIRED_TRANSITIONS,
    which has no PATCH-equivalent entry)."""
    _create(client, auth_headers, unique_qid, tags=[])
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "bulktags")

    r = client.post(
        "/api/question-bank/questions/bulk/tags",
        headers=viewer_headers,
        json={"question_ids": [unique_qid], "add": ["viewer-added"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["succeeded_count"] == 1


# ---------------------------------------------------------------------
# 8. Full pre-2.9.8 regression: single-item PATCH/tags behaviour
#    untouched by the new bulk tag path sharing update_question().
# ---------------------------------------------------------------------


def test_single_item_patch_route_unaffected_by_bulk_tags_addition(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid, tags=["a"])
    r = client.patch(
        f"/api/question-bank/questions/{unique_qid}",
        headers=auth_headers,
        json={"tags": ["a", "b"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["a", "b"]
    assert r.json()["content_version"] == 2
