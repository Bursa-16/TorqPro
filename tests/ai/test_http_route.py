"""HTTP-layer tests for Faz v3.0.0-alpha.4 (AI Gateway HTTP Exposure).

Covers ``POST /api/ai/query`` (``backend/api/routes/ai_gateway.py``)
end-to-end through the real FastAPI app -- route registration,
authentication, the default "model unavailable" runtime provider,
``FakeModelClient``-overridden happy path, structured safety-field
exposure, permission denial, read-only enforcement, AI-gateway error
mapping, and non-leaking generic-error handling. Also proves every
pre-existing, non-AI route is unaffected by this phase.

Uses the shared session-scoped ``client``/``auth_headers`` fixtures
from ``tests/conftest.py`` (same pattern as
``tests/ai/test_ai_disabled_noop.py``).
"""

from __future__ import annotations

import uuid

import pytest

from backend import app as app_module
from backend.ai_gateway.exceptions import PermissionDeniedError
from backend.ai_gateway.llm_client import FakeModelClient
from backend.api.dependencies import user as user_dependency
from backend.api.routes import ai_gateway as route_module
from backend.app import conn
from backend.question_bank import service, store
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

_ENDPOINT = "/api/ai/query"


def _allow_all(role: str, action: str) -> bool:
    return True


def _make_record(**overrides) -> QuestionRecord:
    unique_suffix = uuid.uuid4().hex[:8].upper()
    base = dict(
        question_id=f"QB-AI-HTTP-{unique_suffix}",
        content_version=1,
        category=Category.TIGHTENING_TORQUE,
        subcategory=None,
        difficulty=Difficulty.BEGINNER,
        question_type=QuestionType.SINGLE_CHOICE,
        question_tr="torqpro-ai-http-route-test sorgusu için soru metni, en az on karakter.",
        question_en="torqpro-ai-http-route-test question text, at least ten characters.",
        options_tr=["A", "B", "C"],
        options_en=["A", "B", "C"],
        correct_answer=0,
        technical_explanation_tr="Bu açıklama en az yirmi karakter uzunluğunda olmalıdır.",
        technical_explanation_en="This explanation must be at least twenty characters long.",
        standard_reference=None,
        source_reference=SourceReference(
            source_type=SourceType.INTERNAL_ENGINE, description="ai-gateway-http-route-test"
        ),
        source_locator=None,
        traceability_level=TraceabilityLevel.PROVISIONAL,
        tags=["ai-gateway-http-route-test"],
        learning_objective="HTTP route testi için öğrenme hedefi metni.",
        engineering_risk_level=EngineeringRiskLevel.LOW,
        is_active=True,
    )
    base.update(overrides)
    return QuestionRecord(**base)


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_ai_http_route_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def seeded_evidence(qb_store_path):
    """Registers, submits, and validates one publishable question so
    a keyword-matching query yields non-empty evidence (mirrors
    ``tests/ai/test_orchestrator_boundary.py``'s own fixture-free
    setup, adapted to a reusable fixture for this file's several
    happy-path tests)."""
    record = _make_record()
    store.save_question_content(record, path=qb_store_path)
    with conn() as c:
        service.register_question(
            c, question_id=record.question_id, content_version=record.content_version, actor="t"
        )
        service.submit_for_technical_review(
            c, question_id=record.question_id, content_version=record.content_version, actor="t"
        )
        service.validate_question(
            c,
            question_id=record.question_id,
            content_version=record.content_version,
            actor="t",
            actor_role="admin",
            reviewed_by="t",
            review_date="2026-08-09",
            authorize=_allow_all,
        )
    return record


@pytest.fixture()
def fake_model_override():
    """Overrides the route's default (always-failing) model-client
    dependency with ``FakeModelClient`` for the duration of one test --
    the only sanctioned way ``FakeModelClient`` reaches this route (see
    ``backend/api/routes/ai_gateway.py`` module docstring)."""
    fake = FakeModelClient(fixed_text="TorqPro AI HTTP route test response.")
    app_module.app.dependency_overrides[route_module.get_model_client] = lambda: fake
    yield fake
    del app_module.app.dependency_overrides[route_module.get_model_client]


# --------------------------------------------------------------- 1. route registration


def test_route_is_registered_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert _ENDPOINT in paths
    assert "post" in paths[_ENDPOINT]


# ------------------------------------------------- 2/3. happy path + structured fields


def test_authenticated_happy_path_with_fake_model_override(
    client, auth_headers, seeded_evidence, fake_model_override
):
    response = client.post(
        _ENDPOINT,
        json={"query_text": "torqpro-ai-http-route-test"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()

    # Structured safety fields (ADR-0019), exposed verbatim -- no new
    # vocabulary invented by this route.
    assert body["insufficient_evidence"] is False
    assert body["result_label"] in ("CALCULATED", "VALIDATED", "ESTIMATED", "RECOMMENDED")
    assert isinstance(body["validation_required"], bool)
    assert body["model_name"] == fake_model_override.name
    assert body["calculation_result"] is None
    assert len(body["evidence"]) >= 1
    assert body["evidence"][0]["source_type"] == "question_bank"
    assert len(fake_model_override.calls) == 1


def test_insufficient_evidence_query_still_returns_structured_fields(
    client, auth_headers, fake_model_override
):
    response = client.post(
        _ENDPOINT,
        json={"query_text": "tamamen-ilgisiz-bir-sorgu-xyz-http-route-test"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is True
    assert body["evidence"] == []
    assert body["result_label"] is None
    assert body["validation_required"] is False


# --------------------------------------------------------- 4. default provider -> 503


def test_default_provider_returns_503_without_override(client, auth_headers):
    # No dependency_overrides active here -- exercises the real,
    # production default (_UnavailableModelClient).
    response = client.post(
        _ENDPOINT,
        json={"query_text": "herhangi bir soru"},
        headers=auth_headers,
    )

    assert response.status_code == 503
    assert "detail" in response.json()


# ------------------------------------------------------------- 5. permission denial


def test_inactive_user_context_is_denied_with_403(client, fake_model_override):
    def _inactive_user_override():
        return {
            "id": 999999,
            "username": "inactive-ai-http-test",
            "display_name": "Inactive",
            "is_active": 0,
            "role": "engineer",
        }

    app_module.app.dependency_overrides[user_dependency] = _inactive_user_override
    try:
        response = client.post(
            _ENDPOINT,
            json={"query_text": "herhangi bir soru"},
            headers={"Authorization": "Bearer placeholder"},
        )
    finally:
        del app_module.app.dependency_overrides[user_dependency]

    assert response.status_code == 403
    assert fake_model_override.calls == []


def test_missing_auth_header_is_rejected(client):
    response = client.post(_ENDPOINT, json={"query_text": "herhangi bir soru"})
    assert response.status_code == 401


# ---------------------------------------------------------- 6. read-only enforcement


def test_read_only_action_guard_is_actually_invoked(
    client, auth_headers, seeded_evidence, fake_model_override, monkeypatch
):
    """Proves ``ensure_read_only_action`` genuinely gates the request
    path (not dead code): forcing it to reject even this route's own
    fixed, always-read action name must surface as 403, never a 200."""

    def _always_reject(action: str) -> None:
        raise PermissionDeniedError(f"forced rejection for action={action!r}")

    monkeypatch.setattr(route_module, "ensure_read_only_action", _always_reject)

    response = client.post(
        _ENDPOINT,
        json={"query_text": "torqpro-ai-http-route-test"},
        headers=auth_headers,
    )

    assert response.status_code == 403


# ------------------------------------------------------- 7. known-error mapping (400)


def test_empty_query_text_is_rejected_with_400(client, auth_headers):
    response = client.post(_ENDPOINT, json={"query_text": "   "}, headers=auth_headers)
    assert response.status_code == 400


def test_oversized_query_text_is_rejected_with_400(client, auth_headers):
    response = client.post(
        _ENDPOINT,
        json={"query_text": "x" * (route_module._MAX_QUERY_TEXT_LENGTH + 1)},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_missing_query_text_field_is_rejected(client, auth_headers):
    response = client.post(_ENDPOINT, json={}, headers=auth_headers)
    assert response.status_code == 422


def test_unknown_field_is_rejected(client, auth_headers):
    response = client.post(
        _ENDPOINT,
        json={"query_text": "geçerli soru", "action": "delete"},
        headers=auth_headers,
    )
    assert response.status_code == 422


# --------------------------------------------------- 8. no internal detail leakage


def test_unexpected_error_returns_generic_500_without_internal_detail(
    client, auth_headers, monkeypatch
):
    def _boom(*args, **kwargs):
        raise ValueError("some very specific internal secret detail: DB_PATH=/tmp/x")

    monkeypatch.setattr(route_module, "_run_query", _boom)

    response = client.post(
        _ENDPOINT,
        json={"query_text": "herhangi bir soru"},
        headers=auth_headers,
    )

    assert response.status_code == 500
    body = response.json()
    assert "DB_PATH" not in str(body)
    assert "some very specific internal secret detail" not in str(body)


# -------------------------------------------------- 9. non-AI routes unaffected


def test_existing_health_and_library_routes_still_work(client, auth_headers):
    health = client.get("/api/health")
    assert health.status_code == 200

    materials = client.get("/api/library/materials", headers=auth_headers)
    assert materials.status_code == 200


def test_existing_question_bank_route_unaffected(client, auth_headers):
    response = client.get("/api/question-bank/questions", headers=auth_headers)
    assert response.status_code == 200
