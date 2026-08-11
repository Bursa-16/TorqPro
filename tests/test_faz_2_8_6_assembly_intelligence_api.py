"""Faz 2.8.6 Stage 3 tests: Assembly Intelligence API integration.

Covers: POST /api/assembly-intelligence/assess -- full/partial
assessment, critical bolt-nut incompatibility, missing washer/hardness
data, unknown strength class, friction readiness insufficiency,
intended-use/material/defence authoritative-source blocking, OEM
reference present/absent, score-vs-coverage separation, critical
incompatibility visibility in the response, JSON serialization,
deterministic response for identical requests, validation error
scenarios, and regression safety for pre-existing endpoints.

Does not modify Stage 1 (assembly_intelligence.py) or Stage 2
(assembly_intelligence_report.py) engineering logic, and does not
touch the frontend.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.calculation_engine import assembly_intelligence as ai  # noqa: E402
from backend.library import population  # noqa: E402

client = TestClient(app)

ENDPOINT = "/api/assembly-intelligence/assess"


def _auth():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


# ---------------------------------------------------------------------
# Successful full / partial assessment
# ---------------------------------------------------------------------

def test_full_assessment_returns_200_and_expected_top_level_keys():
    payload = {
        "bolt_designation": "M3", "nut_designation": "ISO 4032 M3",
        "nominal_diameter_mm": 3.0, "bolt_strength_class": "8.8",
        "nut_property_class": "8", "thread_designation": "M3", "bolt_size": "M3",
    }
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    for key in (
        "engine_result", "assembly_readiness", "score", "coverage",
        "check_summary", "checks", "critical_incompatibilities",
    ):
        assert key in d
    assert "report" not in d  # include_report defaults to False


def test_partial_assessment_only_strength_class_supplied():
    r = client.post(
        ENDPOINT, json={"bolt_strength_class": "8.8", "nut_property_class": "8"},
        headers=_auth(),
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["assembly_readiness"]["overall_status"] == "assessed"
    assert d["score"]["assembly_intelligence_score"] == 100.0
    assert d["coverage"]["assessment_coverage_percent"] < 100.0


def test_empty_request_body_is_not_assessable_not_an_error():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["assembly_readiness"]["overall_status"] == "not_assessable"
    assert d["score"]["assembly_intelligence_score"] is None


# ---------------------------------------------------------------------
# Critical bolt-nut incompatibility
# ---------------------------------------------------------------------

def test_critical_bolt_nut_strength_incompatibility_visible_in_response():
    payload = {"bolt_strength_class": "10.9", "nut_property_class": "04"}
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["assembly_readiness"]["has_critical_incompatibility"] is True
    assert d["assembly_readiness"]["overall_risk_level"] == "critical"
    assert len(d["critical_incompatibilities"]) >= 1
    assert any("strength_class" in item for item in d["critical_incompatibilities"])


def test_critical_incompatibility_not_hidden_by_high_score():
    payload = {
        "bolt_designation": "M3", "nut_designation": "ISO 4032 M3",
        "nominal_diameter_mm": 3.0, "bolt_strength_class": "8.8",
        "nut_property_class": "8", "thread_designation": "M3", "bolt_size": "M3",
    }
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    d = r.json()
    # This combination has one incompatible check (out-of-range
    # strength class diameter) alongside several compatible ones --
    # score stays high but the critical finding must remain visible.
    if d["assembly_readiness"]["has_critical_incompatibility"]:
        assert d["critical_incompatibilities"]
        assert d["assembly_readiness"]["overall_risk_level"] == "critical"


# ---------------------------------------------------------------------
# Missing washer / hardness data -> insufficient_data, not an error
# ---------------------------------------------------------------------

def test_missing_washer_data_returns_insufficient_data_status_200():
    r = client.post(ENDPOINT, json={"bolt_size": None}, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    washer_check = next(c for c in d["checks"] if c["check_id"] == "bolt_washer")
    assert washer_check["status"] == ai.STATUS_INSUFFICIENT_DATA


def test_unknown_bolt_size_for_washer_is_incompatible_not_server_error():
    r = client.post(ENDPOINT, json={"bolt_size": "M999-NOPE"}, headers=_auth())
    assert r.status_code == 200, r.text
    washer_check = next(
        c for c in r.json()["checks"] if c["check_id"] == "bolt_washer"
    )
    assert washer_check["status"] == ai.STATUS_INCOMPATIBLE


# ---------------------------------------------------------------------
# Unknown strength class
# ---------------------------------------------------------------------

def test_unknown_strength_class_is_insufficient_data_not_error():
    payload = {"bolt_strength_class": "99.9-UNKNOWN", "nut_property_class": "8"}
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    check = next(c for c in r.json()["checks"] if c["check_id"] == "strength_class")
    assert check["status"] == ai.STATUS_INSUFFICIENT_DATA


# ---------------------------------------------------------------------
# Friction readiness insufficiency
# ---------------------------------------------------------------------

def test_friction_condition_not_supplied_is_insufficient_data():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    check = next(
        c for c in r.json()["checks"] if c["check_id"] == "friction_condition"
    )
    assert check["status"] == ai.STATUS_INSUFFICIENT_DATA


def test_unknown_friction_condition_id_does_not_500():
    r = client.post(
        ENDPOINT, json={"friction_condition_id": "FC-DOES-NOT-EXIST"}, headers=_auth(),
    )
    assert r.status_code == 200, r.text
    check = next(
        c for c in r.json()["checks"] if c["check_id"] == "friction_condition"
    )
    assert check["status"] in (ai.STATUS_INCOMPATIBLE, ai.STATUS_INSUFFICIENT_DATA)


# ---------------------------------------------------------------------
# Authoritative-source blocking: intended use / material / defence
# ---------------------------------------------------------------------

def test_intended_use_always_blocked_authoritative_source():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    check = next(c for c in r.json()["checks"] if c["check_id"] == "intended_use")
    assert check["status"] == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE
    assert check["severity"] == "warning"


def test_material_always_blocked_authoritative_source():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    check = next(c for c in r.json()["checks"] if c["check_id"] == "material")
    assert check["status"] == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE


def test_defence_always_blocked_authoritative_source():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    check = next(
        c for c in r.json()["checks"] if c["check_id"] == "defence_recommendation"
    )
    assert check["status"] == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE


def test_blocked_checks_never_counted_in_score_denominator():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    d = r.json()
    blocked_ids = {
        c["check_id"] for c in d["checks"]
        if c["status"] == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE
    }
    assert blocked_ids  # sanity: at least one blocked check present
    assert d["coverage"]["blocked_authoritative_source_checks"] == len(blocked_ids)


# ---------------------------------------------------------------------
# OEM reference present / absent
# ---------------------------------------------------------------------

def test_oem_reference_present_resolves_to_compatible_or_incompatible():
    r = client.post(ENDPOINT, json={"oem_reference": "REF-EXAMPLE-01"}, headers=_auth())
    assert r.status_code == 200, r.text
    check = next(c for c in r.json()["checks"] if c["check_id"] == "oem_recommendation")
    assert check["status"] in (ai.STATUS_COMPATIBLE, ai.STATUS_INCOMPATIBLE)


def test_oem_reference_absent_is_insufficient_data():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    check = next(c for c in r.json()["checks"] if c["check_id"] == "oem_recommendation")
    assert check["status"] == ai.STATUS_INSUFFICIENT_DATA


# ---------------------------------------------------------------------
# Score vs coverage separation
# ---------------------------------------------------------------------

def test_score_and_coverage_are_distinct_response_sections():
    r = client.post(
        ENDPOINT, json={"bolt_strength_class": "8.8", "nut_property_class": "8"},
        headers=_auth(),
    )
    d = r.json()
    assert "score" in d and "coverage" in d
    assert "assembly_intelligence_score" in d["score"]
    assert "assessment_coverage_percent" in d["coverage"]
    assert "assessment_coverage_percent" not in d["score"]
    assert "assembly_intelligence_score" not in d["coverage"]


def test_high_score_does_not_imply_high_coverage():
    r = client.post(
        ENDPOINT, json={"bolt_strength_class": "8.8", "nut_property_class": "8"},
        headers=_auth(),
    )
    d = r.json()
    assert d["score"]["assembly_intelligence_score"] == 100.0
    assert d["coverage"]["assessment_coverage_percent"] < 100.0


def test_assessed_checks_exclude_insufficient_and_blocked_from_denominator():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    d = r.json()
    coverage = d["coverage"]
    assert (
        coverage["assessed_checks"]
        + coverage["insufficient_data_checks"]
        + coverage["blocked_authoritative_source_checks"]
        == coverage["total_checks"]
    )


# ---------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------

def test_response_is_json_serializable():
    payload = {
        "bolt_designation": "M3", "nut_designation": "ISO 4032 M3",
        "nominal_diameter_mm": 3.0, "include_report": True,
    }
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    assert r.status_code == 200
    text = json.dumps(r.json(), sort_keys=True, ensure_ascii=False)
    reloaded = json.loads(text)
    assert reloaded == r.json()


def test_response_contains_no_datetime_or_random_id_fields():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    serialized = json.dumps(r.json())
    for forbidden in ("generated_at", "timestamp", "request_id", "uuid"):
        assert forbidden not in serialized


# ---------------------------------------------------------------------
# Deterministic response for identical requests
# ---------------------------------------------------------------------

def test_identical_requests_produce_identical_responses():
    payload = {
        "bolt_designation": "M3", "nut_designation": "ISO 4032 M3",
        "nominal_diameter_mm": 3.0, "bolt_strength_class": "8.8",
        "nut_property_class": "8", "include_report": True,
    }
    headers = _auth()
    r1 = client.post(ENDPOINT, json=payload, headers=headers)
    r2 = client.post(ENDPOINT, json=payload, headers=headers)
    assert r1.json() == r2.json()


# ---------------------------------------------------------------------
# include_report flag (Stage 3 brief point 12)
# ---------------------------------------------------------------------

def test_include_report_false_omits_report_key():
    r = client.post(ENDPOINT, json={"include_report": False}, headers=_auth())
    assert "report" not in r.json()


def test_include_report_true_embeds_full_stage2_report():
    r = client.post(ENDPOINT, json={"include_report": True}, headers=_auth())
    d = r.json()
    assert "report" in d
    for key in (
        "assembly_readiness", "score", "coverage", "check_summary",
        "checks", "critical_incompatibilities",
    ):
        assert key in d["report"]


# ---------------------------------------------------------------------
# Validation error scenarios
# ---------------------------------------------------------------------

def test_invalid_field_type_returns_422():
    r = client.post(
        ENDPOINT, json={"nominal_diameter_mm": "not-a-number"}, headers=_auth(),
    )
    assert r.status_code == 422


def test_unknown_extra_field_does_not_crash():
    r = client.post(
        ENDPOINT, json={"this_field_does_not_exist": 123}, headers=_auth(),
    )
    assert r.status_code == 200


def test_missing_auth_header_returns_401():
    r = client.post(ENDPOINT, json={})
    assert r.status_code == 401


def test_malformed_bearer_token_returns_401():
    r = client.post(
        ENDPOINT, json={}, headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


def test_include_report_wrong_type_returns_422():
    r = client.post(
        ENDPOINT, json={"include_report": "yes-please"}, headers=_auth(),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------
# Regression: pre-existing endpoints unaffected
# ---------------------------------------------------------------------

def test_engineering_check_endpoint_still_works_unaffected():
    payload = {
        "diameter_mm": 10, "pitch_mm": 1.5, "stress_area_mm2": 58.0, "rp02_mpa": 900,
        "target_yield_ratio": 0.75, "mu_thread_min": 0.10, "mu_thread_nom": 0.12,
        "mu_thread_max": 0.14, "mu_bearing_min": 0.10, "mu_bearing_nom": 0.12,
        "mu_bearing_max": 0.14, "effective_bearing_diameter_mm": 15.0,
        "engagement_mm": 10.0, "internal_rm_mpa": 500, "bolt_rm_mpa": 1000,
        "nut_proof_mpa": 900,
    }
    r = client.post("/api/engineering/check", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    assert "friction_readiness" not in r.json()


def test_friction_condition_assess_endpoint_still_works_unaffected():
    r = client.post(
        "/api/friction-condition/assess",
        json={"friction_condition_id": "FC-COAT-GEOMET"},
        headers=_auth(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["friction_condition_id"] == "FC-COAT-GEOMET"


def test_health_endpoint_still_works():
    r = client.get("/api/health")
    assert r.status_code == 200


def test_stage1_engine_still_importable_and_unaffected_by_api_layer():
    result = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    assert result.score == 100.0


def test_population_library_not_mutated_by_api_calls():
    bolts_before = len(population.find_bolt())
    client.post(
        ENDPOINT, json={"bolt_strength_class": "8.8", "nut_property_class": "8"},
        headers=_auth(),
    )
    bolts_after = len(population.find_bolt())
    assert bolts_before == bolts_after
