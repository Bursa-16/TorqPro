"""Faz 2.9.6 -- Question Bank create workflow + lifecycle-transition
(submit-for-review / validate / reject / deprecate) + audit /
status-history HTTP API.

Covers: successful question creation over HTTP, invalid-payload
rejection (structural Pydantic validation, both FastAPI's own
request-body validation and backend.question_bank.service's
QuestionBankValidationError -> 422 path), duplicate-creation 409,
unauthenticated (401) and wrong-role (403) access to every new write
route, the full draft -> technical_review -> validated -> deprecated
happy path, illegal transitions (409, e.g. validating a still-draft
question or deprecating one that was never validated), 404 for an
unregistered question_id on every new route, and both new read-only
routes (audit trail, status-history trail) including their "question
exists but the trail is legitimately empty" vs "question_id does not
exist at all" distinction.

No new persistence, no new schema -- every test below exercises HTTP
routes that are thin wrappers over the exact same
backend.question_bank.service functions Faz 2.9.1/2.9.4's own
non-HTTP tests already cover (register_question,
submit_for_technical_review, validate_question, reject_question,
deprecate_question, get_lifecycle_audit, get_status_history).
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
# Fixtures / helpers -- mirrors tests/test_faz_2_9_4_question_lifecycle_
# management.py's own local fixtures exactly, so this file has no
# import-order or fixture-sharing dependency on that one.
# ---------------------------------------------------------------------


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def unique_qid(request):
    return "QB-C6-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


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
        "tags": ["test"],
        "learning_objective": "Test amaçlı öğrenme hedefi metni.",
        "engineering_risk_level": EngineeringRiskLevel.LOW.value,
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def _viewer_headers(client, auth_headers, login_as, suffix):
    username = f"c6_viewer_{suffix}"
    client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "display_name": "Faz 2.9.6 Viewer",
            "password": "viewerpass1",
            "role": "viewer",
        },
    )
    return login_as(username, "viewerpass1")


def _create(client, auth_headers, question_id, **overrides):
    return client.post(
        "/api/question-bank/questions",
        headers=auth_headers,
        json=_valid_payload(question_id, **overrides),
    )


def _create_and_submit(client, auth_headers, question_id):
    _create(client, auth_headers, question_id)
    return client.post(
        f"/api/question-bank/questions/{question_id}/submit-for-review",
        headers=auth_headers,
        json={"content_version": 1},
    )


def _create_submit_validate(client, auth_headers, question_id):
    _create_and_submit(client, auth_headers, question_id)
    return client.post(
        f"/api/question-bank/questions/{question_id}/validate",
        headers=auth_headers,
        json={
            "content_version": 1,
            "reviewed_by": "reviewer1",
            "review_date": "2026-01-01",
        },
    )


# ---------------------------------------------------------------------
# 1. Create -- success, invalid payload, duplicate, authentication
# ---------------------------------------------------------------------


def test_api_create_requires_authentication(client, qb_store_path, unique_qid):
    # No Authorization header at all.
    r = client.post("/api/question-bank/questions", json=_valid_payload(unique_qid))
    assert r.status_code == 401


def test_api_create_success(client, auth_headers, qb_store_path, unique_qid):
    r = _create(client, auth_headers, unique_qid)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["question_id"] == unique_qid
    assert body["content_version"] == 1

    r_get = client.get(
        f"/api/question-bank/questions/{unique_qid}?publishable_only=false",
        headers=auth_headers,
    )
    assert r_get.status_code == 200
    assert r_get.json()["question_id"] == unique_qid


def test_api_create_invalid_payload_missing_required_field(
    client, auth_headers, qb_store_path, unique_qid
):
    payload = _valid_payload(unique_qid)
    del payload["question_tr"]
    r = client.post("/api/question-bank/questions", headers=auth_headers, json=payload)
    assert r.status_code == 422


def test_api_create_invalid_payload_explanation_too_short(
    client, auth_headers, qb_store_path, unique_qid
):
    r = _create(
        client, auth_headers, unique_qid, technical_explanation_tr="çok kısa"
    )
    assert r.status_code == 422


def test_api_create_invalid_payload_bad_category_enum(
    client, auth_headers, qb_store_path, unique_qid
):
    r = _create(client, auth_headers, unique_qid, category="not_a_real_category")
    assert r.status_code == 422


def test_api_create_duplicate_is_409(client, auth_headers, qb_store_path, unique_qid):
    r1 = _create(client, auth_headers, unique_qid)
    assert r1.status_code == 201, r1.text

    r2 = _create(client, auth_headers, unique_qid)
    assert r2.status_code == 409


# ---------------------------------------------------------------------
# 2. submit-for-review
# ---------------------------------------------------------------------


def test_api_submit_for_review_requires_authentication(client, unique_qid):
    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/submit-for-review",
        json={"content_version": 1},
    )
    assert r.status_code == 401


def test_api_submit_for_review_success(client, auth_headers, qb_store_path, unique_qid):
    r = _create_and_submit(client, auth_headers, unique_qid)
    assert r.status_code == 200, r.text
    assert r.json()["validation_status"] == "technical_review"


def test_api_submit_for_review_not_found_is_404(client, auth_headers):
    r = client.post(
        "/api/question-bank/questions/QB-C6-DOES-NOT-EXIST/submit-for-review",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert r.status_code == 404


def test_api_submit_for_review_invalid_transition_is_409(
    client, auth_headers, qb_store_path, unique_qid
):
    # Already technical_review -- submitting a second time is illegal
    # (technical_review -> technical_review is not in the transition
    # table).
    _create_and_submit(client, auth_headers, unique_qid)

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/submit-for-review",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert r.status_code == 409


def test_api_submit_for_review_invalid_payload_is_422(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)
    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/submit-for-review",
        headers=auth_headers,
        json={},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------
# 3. validate
# ---------------------------------------------------------------------


def test_api_validate_requires_authentication(client, unique_qid):
    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/validate",
        json={"content_version": 1, "reviewed_by": "x", "review_date": "2026-01-01"},
    )
    assert r.status_code == 401


def test_api_validate_success(client, auth_headers, qb_store_path, unique_qid):
    r = _create_submit_validate(client, auth_headers, unique_qid)
    assert r.status_code == 200, r.text
    assert r.json()["validation_status"] == "validated"

    r_get = client.get(
        f"/api/question-bank/questions/{unique_qid}", headers=auth_headers
    )
    assert r_get.status_code == 200


def test_api_validate_invalid_transition_is_409(
    client, auth_headers, qb_store_path, unique_qid
):
    # Still draft -- never submitted for review.
    _create(client, auth_headers, unique_qid)

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/validate",
        headers=auth_headers,
        json={"content_version": 1, "reviewed_by": "x", "review_date": "2026-01-01"},
    )
    assert r.status_code == 409


def test_api_validate_not_found_is_404(client, auth_headers):
    r = client.post(
        "/api/question-bank/questions/QB-C6-DOES-NOT-EXIST/validate",
        headers=auth_headers,
        json={"content_version": 1, "reviewed_by": "x", "review_date": "2026-01-01"},
    )
    assert r.status_code == 404


def test_api_validate_invalid_payload_missing_fields_is_422(
    client, auth_headers, qb_store_path, unique_qid
):
    _create_and_submit(client, auth_headers, unique_qid)
    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/validate",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert r.status_code == 422


def test_api_validate_by_viewer_role_is_403(
    client, auth_headers, login_as, qb_store_path, unique_qid
):
    _create_and_submit(client, auth_headers, unique_qid)
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "validate")

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/validate",
        headers=viewer_headers,
        json={"content_version": 1, "reviewed_by": "x", "review_date": "2026-01-01"},
    )
    assert r.status_code == 403

    # Status must be unchanged after the denied attempt.
    r_history = client.get(
        f"/api/question-bank/questions/{unique_qid}/status-history",
        headers=auth_headers,
    )
    assert r_history.json()[-1]["to_status"] == "technical_review"


# ---------------------------------------------------------------------
# 4. reject
# ---------------------------------------------------------------------


def test_api_reject_requires_authentication(client, unique_qid):
    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/reject",
        json={"content_version": 1, "reason": "yetersiz"},
    )
    assert r.status_code == 401


def test_api_reject_success(client, auth_headers, qb_store_path, unique_qid):
    _create_and_submit(client, auth_headers, unique_qid)

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/reject",
        headers=auth_headers,
        json={"content_version": 1, "reason": "Teknik inceleme kriterlerini karşılamıyor."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["validation_status"] == "rejected"


def test_api_reject_invalid_transition_is_409(client, auth_headers, qb_store_path, unique_qid):
    _create(client, auth_headers, unique_qid)  # still draft

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/reject",
        headers=auth_headers,
        json={"content_version": 1, "reason": "Teknik inceleme kriterlerini karşılamıyor."},
    )
    assert r.status_code == 409


def test_api_reject_by_viewer_role_is_403(
    client, auth_headers, login_as, qb_store_path, unique_qid
):
    _create_and_submit(client, auth_headers, unique_qid)
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "reject")

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/reject",
        headers=viewer_headers,
        json={"content_version": 1, "reason": "Teknik inceleme kriterlerini karşılamıyor."},
    )
    assert r.status_code == 403


def test_api_reject_not_found_is_404(client, auth_headers):
    r = client.post(
        "/api/question-bank/questions/QB-C6-DOES-NOT-EXIST/reject",
        headers=auth_headers,
        json={"content_version": 1, "reason": "Teknik inceleme kriterlerini karşılamıyor."},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------
# 5. deprecate
# ---------------------------------------------------------------------


def test_api_deprecate_requires_authentication(client, unique_qid):
    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/deprecate",
        json={"content_version": 1},
    )
    assert r.status_code == 401


def test_api_deprecate_success(client, auth_headers, qb_store_path, unique_qid):
    _create_submit_validate(client, auth_headers, unique_qid)

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/deprecate",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert r.status_code == 200, r.text
    assert r.json()["validation_status"] == "deprecated"


def test_api_deprecate_invalid_transition_is_409(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)  # still draft, never validated

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/deprecate",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert r.status_code == 409


def test_api_deprecate_by_viewer_role_is_403(
    client, auth_headers, login_as, qb_store_path, unique_qid
):
    _create_submit_validate(client, auth_headers, unique_qid)
    viewer_headers = _viewer_headers(client, auth_headers, login_as, "deprecate")

    r = client.post(
        f"/api/question-bank/questions/{unique_qid}/deprecate",
        headers=viewer_headers,
        json={"content_version": 1},
    )
    assert r.status_code == 403


def test_api_deprecate_not_found_is_404(client, auth_headers):
    r = client.post(
        "/api/question-bank/questions/QB-C6-DOES-NOT-EXIST/deprecate",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------
# 6. audit trail
# ---------------------------------------------------------------------


def test_api_audit_requires_authentication(client, unique_qid):
    r = client.get(
        f"/api/question-bank/questions/{unique_qid}/audit"
    )
    assert r.status_code == 401


def test_api_audit_not_found_is_404(client, auth_headers):
    r = client.get(
        "/api/question-bank/questions/QB-C6-DOES-NOT-EXIST/audit", headers=auth_headers
    )
    assert r.status_code == 404


def test_api_audit_empty_for_never_archived_question(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)

    r = client.get(
        f"/api/question-bank/questions/{unique_qid}/audit", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json() == []


def test_api_audit_populated_after_archive(client, auth_headers, qb_store_path, unique_qid):
    _create(client, auth_headers, unique_qid)
    r_archive = client.post(
        f"/api/question-bank/{unique_qid}/archive", headers=auth_headers
    )
    assert r_archive.status_code == 200, r_archive.text

    r = client.get(
        f"/api/question-bank/questions/{unique_qid}/audit", headers=auth_headers
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["action"] == "archive"
    assert rows[0]["question_id"] == unique_qid


# ---------------------------------------------------------------------
# 7. status-history trail
# ---------------------------------------------------------------------


def test_api_status_history_requires_authentication(client, unique_qid):
    r = client.get(
        f"/api/question-bank/questions/{unique_qid}/status-history"
    )
    assert r.status_code == 401


def test_api_status_history_not_found_is_404(client, auth_headers):
    r = client.get(
        "/api/question-bank/questions/QB-C6-DOES-NOT-EXIST/status-history",
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_api_status_history_single_entry_after_create(
    client, auth_headers, qb_store_path, unique_qid
):
    _create(client, auth_headers, unique_qid)

    r = client.get(
        f"/api/question-bank/questions/{unique_qid}/status-history", headers=auth_headers
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["from_status"] is None
    assert rows[0]["to_status"] == "draft"


def test_api_status_history_reflects_full_lifecycle(
    client, auth_headers, qb_store_path, unique_qid
):
    _create_submit_validate(client, auth_headers, unique_qid)
    client.post(
        f"/api/question-bank/questions/{unique_qid}/deprecate",
        headers=auth_headers,
        json={"content_version": 1},
    )

    r = client.get(
        f"/api/question-bank/questions/{unique_qid}/status-history", headers=auth_headers
    )
    assert r.status_code == 200
    rows = r.json()
    to_statuses = [row["to_status"] for row in rows]
    assert to_statuses == ["draft", "technical_review", "validated", "deprecated"]


# ---------------------------------------------------------------------
# 8. End-to-end happy path via the API only (no direct service calls)
# ---------------------------------------------------------------------


def test_api_full_lifecycle_end_to_end(client, auth_headers, qb_store_path, unique_qid):
    r_create = _create(client, auth_headers, unique_qid)
    assert r_create.status_code == 201

    r_submit = client.post(
        f"/api/question-bank/questions/{unique_qid}/submit-for-review",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert r_submit.status_code == 200

    r_validate = client.post(
        f"/api/question-bank/questions/{unique_qid}/validate",
        headers=auth_headers,
        json={"content_version": 1, "reviewed_by": "reviewer1", "review_date": "2026-01-01"},
    )
    assert r_validate.status_code == 200

    # A validated, is_active question must now be publishable.
    r_list = client.get(
        "/api/question-bank/questions", headers=auth_headers
    )
    assert r_list.status_code == 200
    assert any(q["question_id"] == unique_qid for q in r_list.json())

    r_deprecate = client.post(
        f"/api/question-bank/questions/{unique_qid}/deprecate",
        headers=auth_headers,
        json={"content_version": 1},
    )
    assert r_deprecate.status_code == 200

    # No longer publishable once deprecated.
    r_list_after = client.get(
        "/api/question-bank/questions", headers=auth_headers
    )
    assert not any(q["question_id"] == unique_qid for q in r_list_after.json())
