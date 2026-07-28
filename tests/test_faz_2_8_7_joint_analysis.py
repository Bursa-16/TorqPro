"""Faz 2.8.7 tests: Joint Analysis & Torque Optimization.

Covers backend.calculation_engine.joint_analysis.analyze_joint
(nominal analysis, applied-torque -> preload, target-preload ->
required torque, torque window, insufficient-data behavior, invalid
input rejection, negative remaining clamp load, yield-utilization
warning/fail, deterministic output, formula-trace presence,
unsupported-effects reporting, existing-function reuse / no duplicate
formula implementation) and POST /api/engineering/joint-analysis
(successful POST, validation error, missing optional data, critical
warning response, stable JSON schema).

Does not modify backend.vdi2230_core, backend.engineering_core or any
existing endpoint's behaviour.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.calculation_engine import joint_analysis as ja  # noqa: E402
from backend.engineering_core import geometry as eg_geometry  # noqa: E402
from backend.engineering_core import torque as eg_torque  # noqa: E402
from backend.vdi2230_core import CalculationDomainError, CalculationInputError  # noqa: E402

client = TestClient(app)
ENDPOINT = "/api/engineering/joint-analysis"

BOLT_SEGMENTS = [{"length_mm": 30.0, "modulus_mpa": 210000.0, "area_mm2": 58.0}]
JOINT_SEGMENTS = [{"length_mm": 20.0, "modulus_mpa": 210000.0, "area_mm2": 150.0}]

NOMINAL_KWARGS = dict(
    diameter_mm=10.0,
    pitch_mm=1.5,
    rp02_mpa=900.0,
    target_yield_ratio=0.8,
    max_utilization_ratio=0.9,
    mu_thread_nom=0.12,
    mu_bearing_nom=0.12,
    effective_bearing_diameter_mm=14.0,
    bolt_segments=BOLT_SEGMENTS,
    joint_segments=JOINT_SEGMENTS,
    external_axial_load_n=5000.0,
    minimum_required_clamp_load_n=8000.0,
    applied_torque_nm=45.0,
    fail_threshold=1.0,
    warn_threshold=0.9,
)


def _auth():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


# ---------------------------------------------------------------------
# Backend: analyze_joint
# ---------------------------------------------------------------------


def test_nominal_successful_analysis_full_readiness():
    r = ja.analyze_joint(**NOMINAL_KWARGS)
    assert r.readiness == "full"
    assert r.coverage["coverage_percent"] == 100.0
    assert r.critical_findings == []
    assert r.safety["status"] == "pass"
    assert r.calculated_values["target_preload_n"] > 0
    assert r.calculated_values["recommended_torque_nm"] > 0


def test_applied_torque_to_preload():
    r = ja.analyze_joint(**NOMINAL_KWARGS)
    d2 = eg_geometry.pitch_diameter_mm(NOMINAL_KWARGS["diameter_mm"], NOMINAL_KWARGS["pitch_mm"])
    expected = ja._preload_from_torque_n(
        NOMINAL_KWARGS["applied_torque_nm"],
        d2,
        NOMINAL_KWARGS["pitch_mm"],
        NOMINAL_KWARGS["mu_thread_nom"],
        NOMINAL_KWARGS["mu_bearing_nom"],
        NOMINAL_KWARGS["effective_bearing_diameter_mm"],
    )
    assert r.calculated_values["preload_from_applied_torque_n"] == pytest.approx(expected)


def test_target_preload_to_required_torque_matches_existing_torque_formula():
    r = ja.analyze_joint(**NOMINAL_KWARGS)
    d2 = eg_geometry.pitch_diameter_mm(NOMINAL_KWARGS["diameter_mm"], NOMINAL_KWARGS["pitch_mm"])
    expected = eg_torque.tightening_torque_nm(
        r.calculated_values["target_preload_n"],
        d2,
        NOMINAL_KWARGS["pitch_mm"],
        NOMINAL_KWARGS["mu_thread_nom"],
        NOMINAL_KWARGS["mu_bearing_nom"],
        NOMINAL_KWARGS["effective_bearing_diameter_mm"],
    )
    assert r.calculated_values["recommended_torque_nm"] == pytest.approx(expected)
    assert r.torque_window["recommended_nm"] == pytest.approx(expected)


def test_preload_from_torque_round_trips_through_forward_formula():
    d2 = eg_geometry.pitch_diameter_mm(10.0, 1.5)
    preload = 40000.0
    torque_nm = eg_torque.tightening_torque_nm(preload, d2, 1.5, 0.12, 0.12, 14.0)
    recovered = ja._preload_from_torque_n(torque_nm, d2, 1.5, 0.12, 0.12, 14.0)
    assert recovered == pytest.approx(preload, rel=1e-9)


def test_torque_window_min_below_max_and_brackets_recommended():
    r = ja.analyze_joint(**NOMINAL_KWARGS)
    assert r.torque_window["min_nm"] < r.torque_window["recommended_nm"] < r.torque_window["max_nm"]


def test_torque_window_inverted_is_a_critical_finding():
    kwargs = dict(NOMINAL_KWARGS)
    # A very high minimum clamp requirement pushes the lower bound
    # above the yield-limited upper bound.
    kwargs["minimum_required_clamp_load_n"] = 100000.0
    r = ja.analyze_joint(**kwargs)
    assert r.torque_window["min_nm"] is not None and r.torque_window["max_nm"] is not None
    assert r.torque_window["min_nm"] > r.torque_window["max_nm"]
    assert any("torque_window_inverted" in c for c in r.critical_findings)


def test_insufficient_data_returns_no_fabricated_values():
    r = ja.analyze_joint()
    assert r.readiness == "insufficient_data"
    assert r.coverage["evaluated_count"] == 0
    assert all(v is None for v in r.calculated_values.values())
    assert r.torque_window["min_nm"] is None
    assert r.torque_window["max_nm"] is None
    assert "diameter_mm" in r.coverage["missing_inputs_for"]["stress_area_mm2"]
    assert "pitch_mm" in r.coverage["missing_inputs_for"]["stress_area_mm2"]


def test_partial_data_only_computes_what_is_supported():
    r = ja.analyze_joint(diameter_mm=10.0, pitch_mm=1.5)
    assert r.calculated_values["stress_area_mm2"] is not None
    assert r.calculated_values["target_preload_n"] is None
    assert r.calculated_values["bolt_stiffness_n_per_mm"] is None
    assert r.readiness in ("partial", "torque_window_partial")
    assert 0 < r.coverage["coverage_percent"] < 100.0


@pytest.mark.parametrize("diameter_mm", [0, -1, float("nan"), float("inf")])
def test_invalid_diameter_raises(diameter_mm):
    with pytest.raises(CalculationInputError):
        ja.analyze_joint(diameter_mm=diameter_mm, pitch_mm=1.5)


def test_invalid_pitch_too_large_for_diameter_raises_domain_error():
    with pytest.raises(CalculationDomainError):
        ja.analyze_joint(diameter_mm=2.0, pitch_mm=5.0)


def test_malformed_stiffness_segment_raises_input_error():
    with pytest.raises(CalculationInputError):
        ja.analyze_joint(bolt_segments=[{"length_mm": 10.0}])


def test_negative_remaining_clamp_load_is_critical():
    kwargs = dict(
        diameter_mm=10.0,
        pitch_mm=1.5,
        rp02_mpa=900.0,
        target_yield_ratio=0.3,
        mu_thread_nom=0.12,
        mu_bearing_nom=0.12,
        effective_bearing_diameter_mm=14.0,
        bolt_segments=BOLT_SEGMENTS,
        joint_segments=JOINT_SEGMENTS,
        external_axial_load_n=50000.0,
    )
    r = ja.analyze_joint(**kwargs)
    assert r.calculated_values["residual_clamp_load_n"] < 0
    assert any("residual_clamp_load_negative" in c for c in r.critical_findings)


def test_yield_utilization_warn_status():
    kwargs = dict(NOMINAL_KWARGS)
    kwargs["target_yield_ratio"] = 0.95
    kwargs["fail_threshold"] = 1.0
    kwargs["warn_threshold"] = 0.5
    r = ja.analyze_joint(**kwargs)
    assert r.safety["status"] == "warn"
    assert any("yield_utilization_warn" in w for w in r.warnings)


def test_yield_utilization_fail_is_critical():
    kwargs = dict(NOMINAL_KWARGS)
    kwargs["target_yield_ratio"] = 0.95
    kwargs["external_axial_load_n"] = 40000.0
    kwargs["fail_threshold"] = 0.5
    kwargs["warn_threshold"] = 0.3
    r = ja.analyze_joint(**kwargs)
    assert r.safety["status"] == "fail"
    assert any("yield_utilization_fail" in c for c in r.critical_findings)


def test_safety_factor_is_reciprocal_of_utilization_when_available():
    r = ja.analyze_joint(**NOMINAL_KWARGS)
    util = r.safety["utilization"]
    assert r.safety["safety_factor"] == pytest.approx(1.0 / util)


def test_safety_factor_none_when_thresholds_not_supplied():
    kwargs = dict(NOMINAL_KWARGS)
    kwargs["fail_threshold"] = None
    kwargs["warn_threshold"] = None
    r = ja.analyze_joint(**kwargs)
    assert r.safety["status"] == "missing_input"
    assert r.safety["safety_factor"] is None


def test_deterministic_output_for_identical_inputs():
    r1 = ja.analyze_joint(**NOMINAL_KWARGS).to_dict()
    r2 = ja.analyze_joint(**NOMINAL_KWARGS).to_dict()
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_formula_trace_present_and_references_real_sources():
    r = ja.analyze_joint(**NOMINAL_KWARGS)
    assert len(r.formula_trace) > 0
    formula_ids = {t["formula_id"] for t in r.formula_trace}
    assert "VDI2230_AS" in formula_ids
    assert "VDI2230_PRELOAD" in formula_ids
    assert "VDI2230_PHI" in formula_ids
    for trace in r.formula_trace:
        assert trace["source"]
        assert trace["validation_status"] in ("PROVISIONAL", "APPROVED")


def test_unsupported_effects_always_reported():
    for kwargs in ({}, NOMINAL_KWARGS):
        r = ja.analyze_joint(**kwargs)
        assert set(r.unsupported_effects) == set(ja.UNSUPPORTED_EFFECTS)
        assert "settlement_embedment" in r.unsupported_effects
        assert "torque_angle_tightening" in r.unsupported_effects
        assert "multi_step_tightening" in r.unsupported_effects
        assert "full_vdi2230_compliance" in r.unsupported_effects
        assert "fea" in r.unsupported_effects
        assert "ai_ml_torque_prediction" in r.unsupported_effects


def test_stiffness_reuses_vdi2230_core_series_compliance_no_duplicate():
    from backend.vdi2230_core import StiffnessSegment, series_compliance_stiffness_n_per_mm

    r = ja.analyze_joint(**NOMINAL_KWARGS)
    expected = series_compliance_stiffness_n_per_mm(
        [StiffnessSegment(**seg) for seg in BOLT_SEGMENTS]
    )
    assert r.calculated_values["bolt_stiffness_n_per_mm"] == pytest.approx(expected)


def test_recommended_torque_uses_engineering_core_torque_module_directly():
    # Regression guard against a duplicate torque formula living
    # inside joint_analysis.py itself.
    import inspect

    source = inspect.getsource(ja)
    assert "eg_torque.tightening_torque_nm(" in source
    # tan(helix+rho) construction should appear exactly once, inside
    # the documented algebraic inverse -- never re-derived for the
    # forward direction.
    assert source.count("math.tan(helix + rho)") == 1


def test_external_axial_load_default_is_noted_not_silent():
    kwargs = dict(NOMINAL_KWARGS)
    kwargs["external_axial_load_n"] = None
    r = ja.analyze_joint(**kwargs)
    assert any("external_axial_load_n not supplied" in w for w in r.warnings)


# ---------------------------------------------------------------------
# API: POST /api/engineering/joint-analysis
# ---------------------------------------------------------------------


def test_api_successful_post():
    r = client.post(ENDPOINT, json=NOMINAL_KWARGS, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    for key in (
        "calculated_values", "torque_window", "safety", "coverage",
        "readiness", "warnings", "critical_findings", "formula_trace",
        "unsupported_effects", "inputs",
    ):
        assert key in d
    assert d["readiness"] == "full"


def test_api_requires_auth():
    r = client.post(ENDPOINT, json=NOMINAL_KWARGS)
    assert r.status_code in (401, 403)


def test_api_validation_error_on_out_of_range_field():
    payload = dict(NOMINAL_KWARGS)
    payload["target_yield_ratio"] = 1.5  # > 1, rejected by Pydantic
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    assert r.status_code == 422


def test_api_validation_error_on_malformed_segment():
    payload = dict(NOMINAL_KWARGS)
    payload["bolt_segments"] = [{"length_mm": 10.0}]  # missing required fields
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    assert r.status_code == 422


def test_api_degenerate_geometry_maps_to_422():
    payload = {"diameter_mm": 2.0, "pitch_mm": 5.0}
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    assert r.status_code == 422


def test_api_missing_optional_data_still_returns_200():
    r = client.post(ENDPOINT, json={}, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["readiness"] == "insufficient_data"
    assert d["coverage"]["evaluated_count"] == 0


def test_api_critical_warning_response_negative_clamp_load():
    payload = {
        "diameter_mm": 10.0,
        "pitch_mm": 1.5,
        "rp02_mpa": 900.0,
        "target_yield_ratio": 0.3,
        "mu_thread_nom": 0.12,
        "mu_bearing_nom": 0.12,
        "effective_bearing_diameter_mm": 14.0,
        "bolt_segments": BOLT_SEGMENTS,
        "joint_segments": JOINT_SEGMENTS,
        "external_axial_load_n": 50000.0,
    }
    r = client.post(ENDPOINT, json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert any("residual_clamp_load_negative" in c for c in d["critical_findings"])


def test_api_stable_json_schema_across_calls():
    r1 = client.post(ENDPOINT, json=NOMINAL_KWARGS, headers=_auth())
    r2 = client.post(ENDPOINT, json=NOMINAL_KWARGS, headers=_auth())
    assert r1.status_code == r2.status_code == 200
    assert set(r1.json().keys()) == set(r2.json().keys())
    body1 = dict(r1.json())
    body2 = dict(r2.json())
    body1.pop("inputs", None)
    body2.pop("inputs", None)
    assert json.dumps(body1, sort_keys=True) == json.dumps(body2, sort_keys=True)


def test_api_does_not_break_existing_engineering_check_endpoint():
    payload = {
        "diameter_mm": 10, "pitch_mm": 1.5, "stress_area_mm2": 58.0, "rp02_mpa": 900,
        "target_yield_ratio": 0.75, "mu_thread_min": 0.10, "mu_thread_nom": 0.12,
        "mu_thread_max": 0.14, "mu_bearing_min": 0.10, "mu_bearing_nom": 0.12,
        "mu_bearing_max": 0.14, "effective_bearing_diameter_mm": 15.0,
        "engagement_mm": 10.0, "internal_rm_mpa": 500, "bolt_rm_mpa": 1000,
        "nut_proof_mpa": 830,
    }
    r = client.post("/api/engineering/check", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]
