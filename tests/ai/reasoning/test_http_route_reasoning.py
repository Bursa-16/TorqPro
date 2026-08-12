"""Faz v3.0.0-beta.2 (Engineering Reasoning Engine) HTTP-layer tests --
``POST /api/ai/engineering-reasoning``
(``backend/api/routes/ai_gateway.py``).

Uses the shared session-scoped ``client``/``auth_headers``/``login_as``
fixtures from ``tests/conftest.py``, matching
``tests/torque_recommendation/test_beta1_http_route.py``'s and
``tests/ai/test_http_route_alpha5.py``'s own established pattern.

Every trace_id exercised here comes from a real, prior call to the
existing ``POST /api/ai/torque-recommendation`` endpoint -- this file
never fabricates a fake ``audit_log`` row for the "valid trace" cases,
so these tests also double as an end-to-end proof that Beta.2 reads
Beta.1's *actual* persisted output correctly.
"""

from __future__ import annotations

import json
import uuid

from backend.app import conn
from backend.api.routes import ai_gateway as route_module
from backend.torque_recommendation import audit as trq_audit

_REASONING_ENDPOINT = "/api/ai/engineering-reasoning"
_TORQUE_ENDPOINT = "/api/ai/torque-recommendation"

_SEGMENT = {"length_mm": 20, "modulus_mpa": 210000, "area_mm2": 200}

_SUPPORTED_PAYLOAD = {
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

# Empty payload: analyze_joint has nothing to evaluate -> Beta.1
# status="not_applicable" -- the UNSUPPORTED reasoning-state fixture.
_UNSUPPORTED_PAYLOAD: dict = {}


def _make_user(client, auth_headers, login_as, role: str = "engineer") -> dict:
    username = f"reasoning_{role}_{uuid.uuid4().hex[:8]}"
    password = "ReasoningTest1"
    r = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "display_name": f"Reasoning {role.title()} User",
            "password": password,
            "role": role,
        },
    )
    assert r.status_code == 200, r.text
    return login_as(username, password)


def _create_trace(client, headers, payload=_SUPPORTED_PAYLOAD) -> int:
    r = client.post(_TORQUE_ENDPOINT, json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return int(r.json()["trace_id"])


# ---------------------------------------------------------------------
# Registers a RaisingModelClient once, for provider-failure tests
# below, into the same shared _PROVIDER_REGISTRY the route itself
# resolves against (see backend/api/routes/ai_gateway.py's own
# _resolve_wording_provider -- this route deliberately has no
# dependency_overrides seam, matching ADR-0020's "provider selection
# is explicit, by name" design). Adding one extra, distinctly-named
# entry does not affect GET /api/ai/providers' existing assertions
# (tests/ai/test_http_route_alpha5.py only asserts "deterministic" is
# present, never an exact count).
# ---------------------------------------------------------------------

from backend.ai_gateway.llm_client import RaisingModelClient  # noqa: E402

_RAISING_PROVIDER_NAME = "beta2-raising-test-provider"


class _NamedRaisingModelClient(RaisingModelClient):
    name = _RAISING_PROVIDER_NAME


route_module._PROVIDER_REGISTRY.register(
    _NamedRaisingModelClient(RuntimeError("simulated provider outage"))
)


# ---------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------


def test_endpoint_requires_authentication(client):
    r = client.post(_REASONING_ENDPOINT, json={"trace_id": 1})
    assert r.status_code == 401


# ---------------------------------------------------------------------
# Valid trace -> SUPPORTED
# ---------------------------------------------------------------------


def test_valid_trace_returns_supported_state(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trace_id"] == trace_id
    assert body["reasoning_state"] == "SUPPORTED"
    assert body["engineering_conclusion"]["recommended_torque"] is not None
    assert body["evidence_status"] in ("PASS", "WARN")
    assert body["result_label"] == "CALCULATED"
    assert body["reasoning_trace_id"] is not None


def test_response_schema_has_every_required_field(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)
    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for field in (
        "trace_id",
        "reasoning_state",
        "engineering_conclusion",
        "reasoning_steps",
        "applied_rules",
        "assumptions",
        "warnings",
        "limitations",
        "evidence_status",
        "result_label",
        "ai_explanation",
        "ai_explanation_provider",
        "reasoning_trace_id",
    ):
        assert field in body, f"missing field: {field}"


# ---------------------------------------------------------------------
# UNSUPPORTED state (Beta.1 status == not_applicable)
# ---------------------------------------------------------------------


def test_unsupported_payload_yields_unsupported_reasoning_state(client, auth_headers):
    trace_id = _create_trace(client, auth_headers, _UNSUPPORTED_PAYLOAD)

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reasoning_state"] == "UNSUPPORTED"
    assert body["engineering_conclusion"]["recommended_torque"] is None


# ---------------------------------------------------------------------
# Unknown trace -> 404
# ---------------------------------------------------------------------


def test_unknown_trace_returns_404(client, auth_headers):
    r = client.post(_REASONING_ENDPOINT, json={"trace_id": 999999999}, headers=auth_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------
# Cross-user authorization
# ---------------------------------------------------------------------


def test_cross_user_trace_access_is_rejected(client, auth_headers, login_as):
    owner_headers = _make_user(client, auth_headers, login_as)
    other_headers = _make_user(client, auth_headers, login_as)
    trace_id = _create_trace(client, owner_headers)

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=other_headers)

    assert r.status_code == 403


def test_owner_can_access_their_own_trace(client, auth_headers, login_as):
    owner_headers = _make_user(client, auth_headers, login_as)
    trace_id = _create_trace(client, owner_headers)

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=owner_headers)

    assert r.status_code == 200, r.text


def test_admin_can_access_any_users_trace(client, auth_headers, login_as):
    owner_headers = _make_user(client, auth_headers, login_as)
    trace_id = _create_trace(client, owner_headers)

    # auth_headers is the default admin user (Protype Lab).
    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)

    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------
# Corrupt / incomplete stored evidence -> fail-closed 200 INSUFFICIENT_EVIDENCE
# ---------------------------------------------------------------------


def test_corrupt_stored_detail_json_yields_insufficient_evidence(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)

    with conn() as c:
        c.execute(
            "UPDATE audit_log SET detail=? WHERE id=?",
            ("{not-valid-json", trace_id),
        )
        c.commit()

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reasoning_state"] == "INSUFFICIENT_EVIDENCE"
    assert body["engineering_conclusion"] == {}
    assert body["evidence_status"] == "FAIL"


def test_incomplete_stored_detail_missing_result_key_yields_insufficient_evidence(
    client, auth_headers
):
    trace_id = _create_trace(client, auth_headers)

    with conn() as c:
        row = c.execute("SELECT detail FROM audit_log WHERE id=?", (trace_id,)).fetchone()
        detail = json.loads(row["detail"])
        del detail["result"]
        c.execute(
            "UPDATE audit_log SET detail=? WHERE id=?",
            (json.dumps(detail), trace_id),
        )
        c.commit()

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)

    assert r.status_code == 200, r.text
    assert r.json()["reasoning_state"] == "INSUFFICIENT_EVIDENCE"


def test_corrupt_evidence_ownership_check_still_enforced(client, auth_headers, login_as):
    """A corrupt row must still 403 for a non-owner -- authorization
    happens via raw SQL (never JSON-parsed) before the corrupt payload
    is ever touched (see ``_fetch_trace_owner``'s own docstring)."""
    owner_headers = _make_user(client, auth_headers, login_as)
    other_headers = _make_user(client, auth_headers, login_as)
    trace_id = _create_trace(client, owner_headers)

    with conn() as c:
        c.execute("UPDATE audit_log SET detail=? WHERE id=?", ("{not-valid-json", trace_id))
        c.commit()

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=other_headers)
    assert r.status_code == 403


# ---------------------------------------------------------------------
# No Beta.1 recomputation / no mutation
# ---------------------------------------------------------------------


def test_repeated_reasoning_calls_yield_identical_engineering_conclusion(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)

    r1 = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)
    r2 = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)

    assert r1.json()["engineering_conclusion"] == r2.json()["engineering_conclusion"]


def test_reasoning_call_does_not_alter_the_stored_beta1_audit_row(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)
    with conn() as c:
        before = trq_audit.get_recommendation_audit(c, trace_id)

    client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)

    with conn() as c:
        after = trq_audit.get_recommendation_audit(c, trace_id)
    assert before == after


# ---------------------------------------------------------------------
# Provider independence / provider failure (AI wording is optional)
# ---------------------------------------------------------------------


def test_default_no_ai_wording_requested(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai_explanation"] is None
    assert body["ai_explanation_provider"] is None
    # Deterministic fields are fully populated regardless.
    assert body["reasoning_state"] == "SUPPORTED"


def test_ai_wording_with_deterministic_provider_succeeds(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)

    r = client.post(
        _REASONING_ENDPOINT,
        json={"trace_id": trace_id, "include_ai_wording": True, "provider_name": "deterministic"},
        headers=auth_headers,
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai_explanation"] is not None
    assert body["ai_explanation_provider"] == "deterministic"


def test_unknown_provider_name_degrades_gracefully_without_affecting_deterministic_result(
    client, auth_headers
):
    trace_id = _create_trace(client, auth_headers)

    r = client.post(
        _REASONING_ENDPOINT,
        json={
            "trace_id": trace_id,
            "include_ai_wording": True,
            "provider_name": "not-a-real-provider",
        },
        headers=auth_headers,
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai_explanation"] is None
    assert body["ai_explanation_provider"] is None
    assert body["reasoning_state"] == "SUPPORTED"
    assert body["engineering_conclusion"]["recommended_torque"] is not None


def test_provider_failure_does_not_affect_deterministic_result_or_http_status(
    client, auth_headers
):
    trace_id = _create_trace(client, auth_headers)

    r = client.post(
        _REASONING_ENDPOINT,
        json={
            "trace_id": trace_id,
            "include_ai_wording": True,
            "provider_name": _RAISING_PROVIDER_NAME,
        },
        headers=auth_headers,
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai_explanation"] is None
    assert body["ai_explanation_provider"] is None
    assert body["reasoning_state"] == "SUPPORTED"
    assert body["engineering_conclusion"]["recommended_torque"] is not None


# ---------------------------------------------------------------------
# Audit / traceability
# ---------------------------------------------------------------------


def test_reasoning_creates_a_persisted_audit_record_linked_to_beta1_trace(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)
    assert r.status_code == 200, r.text
    reasoning_trace_id = r.json()["reasoning_trace_id"]
    assert reasoning_trace_id is not None

    with conn() as c:
        row = c.execute(
            "SELECT evidence_source_ids_json, evidence_status, result_label "
            "FROM ai_audit_records WHERE id=?",
            (reasoning_trace_id,),
        ).fetchone()
    assert row is not None
    evidence_source_ids = json.loads(row["evidence_source_ids_json"])
    assert evidence_source_ids == [["torque_recommendation", str(trace_id)]]
    assert row["evidence_status"] in ("PASS", "WARN")
    assert row["result_label"] == "CALCULATED"


def test_no_new_audit_table_or_column_was_introduced(client, auth_headers):
    """Stage 0 constraint: reuse ai_audit_records unchanged -- no new
    table, no new column. This test enumerates the actual live schema
    and pins it to the exact, pre-existing alpha.5 column set."""
    with conn() as c:
        cols = [r["name"] for r in c.execute("PRAGMA table_info(ai_audit_records)").fetchall()]
        tables = [
            r["name"]
            for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%reasoning%'"
            ).fetchall()
        ]
    assert cols == [
        "id",
        "user_id",
        "user_role",
        "correlation_id",
        "query_text_hash",
        "response_text_hash",
        "evidence_source_ids_json",
        "calculation_formula_ids_json",
        "model_name",
        "had_sufficient_evidence",
        "created_at",
        "retrieval_source_types_queried_json",
        "evidence_count_by_source_type_json",
        "evidence_status",
        "result_label",
        "latency_ms",
        "success",
        "error_category",
    ]
    assert tables == []


# ---------------------------------------------------------------------
# Request-ID propagation
# ---------------------------------------------------------------------


def test_x_request_id_header_is_stored_on_the_persisted_audit_row(client, auth_headers):
    trace_id = _create_trace(client, auth_headers)
    headers = dict(auth_headers, **{"X-Request-ID": "beta2-engineering-corr-test-id"})

    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=headers)
    assert r.status_code == 200, r.text
    reasoning_trace_id = r.json()["reasoning_trace_id"]

    with conn() as c:
        row = c.execute(
            "SELECT correlation_id FROM ai_audit_records WHERE id=?", (reasoning_trace_id,)
        ).fetchone()
    assert row["correlation_id"] == "beta2-engineering-corr-test-id"


# ---------------------------------------------------------------------
# OEM / proprietary leakage regression
# ---------------------------------------------------------------------


def test_reasoning_response_never_contains_oem_standard_name(client, auth_headers):
    from backend.standards.fiat import FIAT_9_55823

    trace_id = _create_trace(client, auth_headers)
    r = client.post(_REASONING_ENDPOINT, json={"trace_id": trace_id}, headers=auth_headers)
    assert r.status_code == 200, r.text
    haystack = r.text.lower()
    assert FIAT_9_55823.name.lower() not in haystack
    assert FIAT_9_55823.key.lower() not in haystack


# ---------------------------------------------------------------------
# Beta.1 backward compatibility
# ---------------------------------------------------------------------


def test_pre_existing_torque_recommendation_endpoint_still_works_unaffected(client, auth_headers):
    r = client.post(_TORQUE_ENDPOINT, json=_SUPPORTED_PAYLOAD, headers=auth_headers)
    assert r.status_code == 200, r.text


def test_pre_existing_ai_query_endpoint_still_works_unaffected(client, auth_headers):
    r = client.get("/api/ai/providers", headers=auth_headers)
    assert r.status_code == 200, r.text


def test_pre_existing_joint_analysis_endpoint_still_works_unaffected(client, auth_headers):
    r = client.post(
        "/api/engineering/joint-analysis", json=_SUPPORTED_PAYLOAD, headers=auth_headers
    )
    assert r.status_code == 200, r.text


def test_request_body_rejects_unknown_fields(client, auth_headers):
    r = client.post(
        _REASONING_ENDPOINT,
        json={"trace_id": 1, "unexpected_field": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_request_body_requires_trace_id(client, auth_headers):
    r = client.post(_REASONING_ENDPOINT, json={}, headers=auth_headers)
    assert r.status_code == 422


__all__: list = []
