"""HTTP-layer tests for Faz v3.0.0-alpha.5 (Persistent Audit,
Explainability, Provider Abstraction, ADR-0020).

Covers the three new endpoints (``GET /api/ai/providers``,
``GET /api/ai/audit``, ``GET /api/ai/audit/{audit_id}``), the
persistent-audit write path for both the successful and the
provider-failure branch of ``POST /api/ai/query``, and proves the
pre-existing alpha.4 ``POST /api/ai/query`` behavior (default-
unavailable provider, structured fields, permission handling) is
completely unchanged.

Uses the shared session-scoped ``client``/``auth_headers``/``login_as``
fixtures from ``tests/conftest.py``, matching
``tests/test_faz_stage2_system_health_authorization.py``'s
create-a-fresh-non-admin-user pattern for authorization checks.
"""

from __future__ import annotations

import uuid

import pytest

from backend import app as app_module
from backend.ai_gateway.llm_client import FakeModelClient
from backend.api.routes import ai_gateway as route_module

_QUERY_ENDPOINT = "/api/ai/query"
_PROVIDERS_ENDPOINT = "/api/ai/providers"
_AUDIT_LIST_ENDPOINT = "/api/ai/audit"


def _make_user(client, auth_headers, login_as, role: str) -> dict:
    username = f"alpha5_{role}_{uuid.uuid4().hex[:8]}"
    password = "Alpha5Test1"
    r = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "display_name": f"Alpha5 {role.title()} User",
            "password": password,
            "role": role,
        },
    )
    assert r.status_code == 200, r.text
    return login_as(username, password)


@pytest.fixture()
def fake_model_override():
    fake = FakeModelClient(fixed_text="TorqPro AI alpha.5 HTTP test response.")
    app_module.app.dependency_overrides[route_module.get_model_client] = lambda: fake
    yield fake
    del app_module.app.dependency_overrides[route_module.get_model_client]


# --------------------------------------------------------------- GET /api/ai/providers


def test_providers_endpoint_is_registered(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert _PROVIDERS_ENDPOINT in paths
    assert "get" in paths[_PROVIDERS_ENDPOINT]


def test_providers_endpoint_requires_authentication(client):
    response = client.get(_PROVIDERS_ENDPOINT)
    assert response.status_code in (401, 403)


def test_providers_endpoint_accessible_to_any_authenticated_role(client, auth_headers, login_as):
    viewer_headers = _make_user(client, auth_headers, login_as, "viewer")

    response = client.get(_PROVIDERS_ENDPOINT, headers=viewer_headers)

    assert response.status_code == 200


def test_providers_endpoint_lists_deterministic_provider_with_no_secret_field(
    client, auth_headers
):
    response = client.get(_PROVIDERS_ENDPOINT, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    names = [p["name"] for p in body["providers"]]
    assert "deterministic" in names
    for provider in body["providers"]:
        assert set(provider.keys()) == {"name", "model_identifier", "available"}


# --------------------------------------------------------- GET /api/ai/audit(/id)


def test_audit_list_endpoint_requires_admin(client, auth_headers, login_as):
    viewer_headers = _make_user(client, auth_headers, login_as, "viewer")

    response = client.get(_AUDIT_LIST_ENDPOINT, headers=viewer_headers)

    assert response.status_code == 403


def test_audit_detail_endpoint_requires_admin(client, auth_headers, login_as):
    viewer_headers = _make_user(client, auth_headers, login_as, "viewer")

    response = client.get("/api/ai/audit/1", headers=viewer_headers)

    assert response.status_code == 403


def test_audit_list_endpoint_accessible_to_admin(client, auth_headers):
    response = client.get(_AUDIT_LIST_ENDPOINT, headers=auth_headers)
    assert response.status_code == 200
    assert "records" in response.json()


def test_audit_detail_returns_404_for_unknown_id(client, auth_headers):
    response = client.get("/api/ai/audit/99999999", headers=auth_headers)
    assert response.status_code == 404


def test_audit_list_limit_query_param_is_bounded(client, auth_headers):
    # ge=1, le=500 -- 0 and 501 should both fail FastAPI validation (422).
    too_low = client.get(_AUDIT_LIST_ENDPOINT + "?limit=0", headers=auth_headers)
    too_high = client.get(_AUDIT_LIST_ENDPOINT + "?limit=501", headers=auth_headers)
    assert too_low.status_code == 422
    assert too_high.status_code == 422


# --------------------------------------------- persistent audit write path (success)


def test_successful_query_is_persisted_and_retrievable_via_audit_detail(
    client, auth_headers, fake_model_override
):
    correlation_id = f"alpha5-corr-{uuid.uuid4().hex[:8]}"
    query_response = client.post(
        _QUERY_ENDPOINT,
        json={"query_text": "alpha5-http-persistence-test-query"},
        headers={**auth_headers, "X-Request-ID": correlation_id},
    )
    assert query_response.status_code == 200

    list_response = client.get(_AUDIT_LIST_ENDPOINT, headers=auth_headers)
    assert list_response.status_code == 200
    records = list_response.json()["records"]
    matching = [r for r in records if r["correlation_id"] == correlation_id]
    assert len(matching) == 1

    detail_response = client.get(f"/api/ai/audit/{matching[0]['audit_id']}", headers=auth_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["success"] is True
    assert detail["error_category"] is None
    assert detail["latency_ms"] is not None
    assert detail["query_text_hash"]
    assert detail["response_text_hash"]


def test_successful_query_audit_never_carries_raw_query_or_response_text(
    client, auth_headers, fake_model_override
):
    raw_query = "gizli-anahtar-icermeyen-ama-benzersiz-sorgu-alpha5-xyz-987"
    response = client.post(
        _QUERY_ENDPOINT, json={"query_text": raw_query}, headers=auth_headers
    )
    assert response.status_code == 200
    response_text = response.json()["text"]

    list_response = client.get(_AUDIT_LIST_ENDPOINT + "?limit=500", headers=auth_headers)
    body_text = list_response.text
    assert raw_query not in body_text
    assert response_text not in body_text


# ---------------------------------------------- persistent audit write path (failure)


def test_provider_failure_query_is_persisted_as_a_failure_record(client, auth_headers):
    # No fake_model_override -> default _UnavailableModelClient -> 503,
    # exactly like the pre-existing alpha.4 behavior.
    correlation_id = f"alpha5-fail-corr-{uuid.uuid4().hex[:8]}"
    response = client.post(
        _QUERY_ENDPOINT,
        json={"query_text": "alpha5-provider-failure-test-query"},
        headers={**auth_headers, "X-Request-ID": correlation_id},
    )
    assert response.status_code == 503

    list_response = client.get(_AUDIT_LIST_ENDPOINT, headers=auth_headers)
    records = list_response.json()["records"]
    matching = [r for r in records if r["correlation_id"] == correlation_id]
    assert len(matching) == 1
    assert matching[0]["success"] is False
    assert matching[0]["error_category"] == "ModelUnavailableError"
    assert matching[0]["response_text_hash"] is None


def test_provider_failure_error_category_never_leaks_exception_message(
    client, auth_headers
):
    """error_category is always the exception's class name, never its
    message string -- a provider error message could carry a header/
    token/URL fragment (see backend.ai_gateway.store module
    docstring, Privacy)."""
    correlation_id = f"alpha5-fail-detail-{uuid.uuid4().hex[:8]}"
    client.post(
        _QUERY_ENDPOINT,
        json={"query_text": "alpha5-provider-failure-detail-test"},
        headers={**auth_headers, "X-Request-ID": correlation_id},
    )

    list_response = client.get(_AUDIT_LIST_ENDPOINT, headers=auth_headers)
    matching = [
        r for r in list_response.json()["records"] if r["correlation_id"] == correlation_id
    ]
    assert matching[0]["error_category"] == "ModelUnavailableError"
    # Never the full RuntimeError message _UnavailableModelClient.complete() raises.
    assert "No AI model provider is configured" not in matching[0]["error_category"]


# ----------------------------------------------------- alpha.4 regression (unchanged)


def test_default_provider_still_returns_503_without_override(client, auth_headers):
    response = client.post(
        _QUERY_ENDPOINT,
        json={"query_text": "alpha5-regression-default-provider-test"},
        headers=auth_headers,
    )
    assert response.status_code == 503


def test_happy_path_response_shape_is_unchanged_by_alpha5(
    client, auth_headers, fake_model_override
):
    response = client.post(
        _QUERY_ENDPOINT,
        json={"query_text": "alpha5-regression-response-shape-test"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "text",
        "insufficient_evidence",
        "result_label",
        "validation_required",
        "model_name",
        "citations",
        "evidence",
        "calculation_result",
    }


def test_empty_query_text_still_returns_400(client, auth_headers):
    response = client.post(_QUERY_ENDPOINT, json={"query_text": "   "}, headers=auth_headers)
    assert response.status_code == 400


def test_unauthenticated_query_still_returns_401_or_403(client):
    response = client.post(_QUERY_ENDPOINT, json={"query_text": "no-auth-test"})
    assert response.status_code in (401, 403)
