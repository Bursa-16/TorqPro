"""Faz v3.0.0-beta.1 (Torque Recommendation Engine) - HTTP-layer
tests.

Covers ``POST /api/ai/torque-recommendation``
(``backend/api/routes/torque_recommendation.py``) end-to-end through
the real FastAPI app: route registration, authentication, response
schema, deterministic-error mapping (422), and audit/traceability
persistence. Uses the shared session-scoped ``client``/``auth_headers``
fixtures from ``tests/conftest.py`` (same pattern as
``tests/ai/test_http_route.py``).
"""

from __future__ import annotations

from backend.app import conn
from backend.torque_recommendation import audit as trq_audit

_ENDPOINT = "/api/ai/torque-recommendation"

_SEGMENT = {"length_mm": 20, "modulus_mpa": 210000, "area_mm2": 200}

_FULL_PAYLOAD = {
    "diameter_mm": 10,
    "pitch_mm": 1.5,
    "rp02_mpa": 900,
    "target_yield_ratio": 0.5,
    "max_utilization_ratio": 0.9,
    "mu_thread_nom": 0.12,
    "mu_bearing_nom": 0.10,
    "effective_bearing_diameter_mm": 14,
    "bolt_segments": [_SEGMENT],
    "joint_segments": [_SEGMENT],
    "minimum_required_clamp_load_n": 1000,
    "external_axial_load_n": 500,
    "fail_threshold": 0.95,
    "warn_threshold": 0.80,
}


# ---------------------------------------------------------------------
# Authentication / authorization
# ---------------------------------------------------------------------


def test_endpoint_requires_authentication(client):
    r = client.post(_ENDPOINT, json=_FULL_PAYLOAD)
    assert r.status_code == 401


def test_endpoint_rejects_invalid_token(client):
    r = client.post(
        _ENDPOINT, json=_FULL_PAYLOAD, headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert r.status_code == 401


def test_endpoint_succeeds_with_valid_token(client, auth_headers):
    r = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=auth_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------
# API response schema
# ---------------------------------------------------------------------


def test_response_schema_has_every_required_field(client, auth_headers):
    r = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for field in (
        "recommended_torque",
        "unit",
        "calculated_torque",
        "allowable_range",
        "preload_n",
        "status",
        "confidence",
        "warnings",
        "assumptions",
        "explanation",
        "calculation_source",
        "trace_id",
        "readiness",
        "coverage_percent",
        "critical_findings",
    ):
        assert field in body, f"missing field: {field}"
    assert body["unit"] == "Nm"
    assert body["status"] in ("recommended", "not_applicable")
    assert body["confidence"] in ("HIGH", "MEDIUM", "LOW", "NOT_APPLICABLE")
    assert isinstance(body["allowable_range"], dict)
    assert set(body["allowable_range"].keys()) == {"min_nm", "max_nm"}
    assert isinstance(body["explanation"], dict)
    for key in ("input_drivers", "calculation_source", "assumptions", "limitations",
                "warning_reasons"):
        assert key in body["explanation"]


def test_response_recommended_torque_matches_calculated_torque_on_success(client, auth_headers):
    r = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=auth_headers)
    body = r.json()
    if body["status"] == "recommended":
        assert body["recommended_torque"] == body["calculated_torque"]
    else:
        assert body["recommended_torque"] is None


# ---------------------------------------------------------------------
# Deterministic calculation failure -> 422
# ---------------------------------------------------------------------


def test_unsupported_thread_pitch_domain_maps_to_422(client, auth_headers):
    payload = dict(_FULL_PAYLOAD, diameter_mm=4, pitch_mm=5)
    r = client.post(_ENDPOINT, json=payload, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_invalid_friction_coefficient_rejected_before_engine_runs(client, auth_headers):
    payload = dict(_FULL_PAYLOAD, mu_thread_nom=-0.1)
    r = client.post(_ENDPOINT, json=payload, headers=auth_headers)
    # Pydantic field validation (ge=0) rejects this before the route
    # body even runs -- FastAPI's standard 422, not the engine's own
    # domain-error mapping.
    assert r.status_code == 422, r.text


def test_missing_inputs_returns_200_not_applicable_not_an_error(client, auth_headers):
    r = client.post(_ENDPOINT, json={}, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "not_applicable"
    assert body["confidence"] == "NOT_APPLICABLE"
    assert body["recommended_torque"] is None


# ---------------------------------------------------------------------
# Audit / traceability creation
# ---------------------------------------------------------------------


def test_successful_recommendation_creates_an_audit_record(client, auth_headers):
    r = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trace_id"] is not None

    with conn() as c:
        record = trq_audit.get_recommendation_audit(c, int(body["trace_id"]))
    assert record is not None
    assert record["status"] == body["status"]
    assert record["confidence"] == body["confidence"]
    assert record["readiness"] == body["readiness"]
    assert record["provider_involved"] == 0


def test_failed_domain_validation_creates_no_audit_record(client, auth_headers):
    with conn() as c:
        before = c.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action=?", (trq_audit.ACTION,)
        ).fetchone()["c"]

    payload = dict(_FULL_PAYLOAD, diameter_mm=4, pitch_mm=5)
    r = client.post(_ENDPOINT, json=payload, headers=auth_headers)
    assert r.status_code == 422

    with conn() as c:
        after = c.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action=?", (trq_audit.ACTION,)
        ).fetchone()["c"]
    assert after == before


def test_recommendation_audit_reuses_existing_audit_log_table(client, auth_headers):
    """Architecture decision (revised): no dedicated
    torque_recommendation_audit table exists -- every recommendation
    is recorded as an ordinary audit_log row with
    action='torque_recommendation', the same table/discriminator
    convention every other module in this repository already uses."""
    r = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    with conn() as c:
        row = c.execute(
            "SELECT user_id, action FROM audit_log WHERE id=?", (int(body["trace_id"]),)
        ).fetchone()
    assert row is not None
    assert row["action"] == "torque_recommendation"


def test_x_request_id_header_is_stored_on_the_audit_row(client, auth_headers):
    headers = dict(auth_headers, **{"X-Request-ID": "trq-test-correlation-id"})
    r = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    with conn() as c:
        row = c.execute(
            "SELECT request_id FROM audit_log WHERE id=?", (int(body["trace_id"]),)
        ).fetchone()
    assert row["request_id"] == "trq-test-correlation-id"


def test_engineering_context_is_not_persisted_verbatim(client, auth_headers):
    payload = dict(_FULL_PAYLOAD, engineering_context="internal-project-label-XYZ")
    r = client.post(_ENDPOINT, json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    with conn() as c:
        record = trq_audit.get_recommendation_audit(c, int(body["trace_id"]))
    assert "engineering_context" not in record["request_json"]
    assert "internal-project-label-XYZ" not in str(record)
    assert record["engineering_context_length"] == len("internal-project-label-XYZ")


# ---------------------------------------------------------------------
# Deterministic output regardless of AI-gateway state
# ---------------------------------------------------------------------


def test_repeated_calls_yield_identical_engineering_output(client, auth_headers):
    r1 = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=auth_headers)
    r2 = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=auth_headers)
    b1, b2 = r1.json(), r2.json()
    b1.pop("trace_id", None)
    b2.pop("trace_id", None)
    assert b1 == b2


def test_pre_existing_ai_query_endpoint_still_works_unaffected(client, auth_headers):
    """Non-regression: adding this route must not disturb the
    pre-existing /api/ai/query route (registration order, dependency
    wiring, etc.)."""
    r = client.get("/api/ai/providers", headers=auth_headers)
    assert r.status_code == 200, r.text


def test_pre_existing_joint_analysis_endpoint_still_works_unaffected(client, auth_headers):
    r = client.post(
        "/api/engineering/joint-analysis", json=_FULL_PAYLOAD, headers=auth_headers
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------
# Proprietary / OEM names not leaked (HTTP layer)
# ---------------------------------------------------------------------


def test_http_response_never_contains_oem_standard_name(client, auth_headers):
    from backend.standards.fiat import FIAT_9_55823

    r = client.post(_ENDPOINT, json=_FULL_PAYLOAD, headers=auth_headers)
    assert r.status_code == 200, r.text
    haystack = r.text.lower()
    assert FIAT_9_55823.name.lower() not in haystack
    assert FIAT_9_55823.key.lower() not in haystack


__all__: list = []
