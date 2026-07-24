"""Faz 2.6.4 -- Friction Condition Recommendation and Warning Framework.

Scope (see docs/phases/PHASE_2.6.4_FRICTION_RECOMMENDATION_WARNING_FRAMEWORK.md):

- generate_friction_warnings(): deterministic, field-derived warnings
  only -- no ranking, no judgement.
- assess_recommendation_readiness(): reports a capability level
  (warnings_only / comparison_only) for every live record; NO live
  record reaches engineering_recommendation_ready or
  production_recommendation_ready.
- compare_friction_conditions(): purely descriptive comparison, never
  states which condition is "better".
- /api/friction-condition/assess is additive; /api/engineering/check
  is unaffected.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.calculation_engine.exceptions import CalculationInputError  # noqa: E402
from backend.calculation_engine.friction_recommendations import (  # noqa: E402
    LEVEL_COMPARISON_ONLY,
    LEVEL_ENGINEERING_RECOMMENDATION_READY,
    LEVEL_PRODUCTION_RECOMMENDATION_READY,
    LEVEL_WARNINGS_ONLY,
    RESTRICTED_LEGACY_WARNINGS,
    assess_recommendation_readiness,
    compare_friction_conditions,
    generate_friction_warnings,
)
from backend.library import population  # noqa: E402

client = TestClient(app)


def _auth():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def _base_payload(**overrides):
    payload = {
        "diameter_mm": 10, "pitch_mm": 1.5, "stress_area_mm2": 58.0, "rp02_mpa": 900,
        "target_yield_ratio": 0.75, "mu_thread_min": 0.10, "mu_thread_nom": 0.12,
        "mu_thread_max": 0.14, "mu_bearing_min": 0.10, "mu_bearing_nom": 0.12,
        "mu_bearing_max": 0.14, "effective_bearing_diameter_mm": 15.0,
        "engagement_mm": 10.0, "internal_rm_mpa": 500, "bolt_rm_mpa": 1000,
        "nut_proof_mpa": 830,
    }
    payload.update(overrides)
    return payload


def _all_friction_condition_ids():
    return [r["id"] for r in population.load_population_records("friction condition library")]


# ---------------------------------------------------------------------
# Deterministic warnings
# ---------------------------------------------------------------------

def test_combined_friction_warning_present_for_every_live_record():
    for fid in _all_friction_condition_ids():
        warnings = generate_friction_warnings(fid)
        assert "Thread and bearing friction are not separately verified." in warnings
        assert "Torque decomposition is unavailable." in warnings
        assert "This condition may only be used as a reference friction range." in warnings


def test_reference_only_warning_present_for_every_live_record():
    for fid in _all_friction_condition_ids():
        warnings = generate_friction_warnings(fid)
        assert (
            "The friction data is reference-only and is not a certified "
            "ISO 16047 test result." in warnings
        )
        assert "Production approval requires verified application-specific data." in warnings


def test_torque_calculation_warning_present_for_every_live_record():
    for fid in _all_friction_condition_ids():
        warnings = generate_friction_warnings(fid)
        assert "No torque recommendation can be generated from combined friction data." in warnings
        assert (
            "Verified nut factor or separated thread/bearing friction data "
            "is required." in warnings
        )


def test_restricted_legacy_warning_and_regulatory_text_preserved(monkeypatch):
    original = population.load_population_records

    def fake(key):
        if key == "friction condition library":
            return [{
                "id": "FC-FAKE-RESTRICTED", "coating_id": "COAT-FAKE-CADMIUM",
                "lubricant_id": "", "source_reference": "Some Source",
                "overall_friction_coefficient_min": 0.1,
                "overall_friction_coefficient_max": 0.2,
                "friction_model": "combined_or_unspecified",
                "verification_status": "reference_only",
            }]
        if key == "coating library":
            return [{
                "id": "COAT-FAKE-CADMIUM", "status": "restricted_legacy",
                "regulatory_warning": "Cadmium plating requires RoHS/ELV sign-off.",
            }]
        return original(key)

    monkeypatch.setattr(population, "load_population_records", fake)
    warnings = generate_friction_warnings("FC-FAKE-RESTRICTED")
    for text in RESTRICTED_LEGACY_WARNINGS:
        assert text in warnings
    assert "Cadmium plating requires RoHS/ELV sign-off." in warnings


def test_missing_source_blocks_warnings(monkeypatch):
    original = population.load_population_records

    def fake(key):
        if key == "friction condition library":
            return [{
                "id": "FC-FAKE-NOSRC", "coating_id": "", "lubricant_id": "",
                "source_reference": "", "friction_model": "combined_or_unspecified",
            }]
        return original(key)

    monkeypatch.setattr(population, "load_population_records", fake)
    with pytest.raises(CalculationInputError, match="missing_source_traceability"):
        generate_friction_warnings("FC-FAKE-NOSRC")


def test_unknown_id_blocks_warnings():
    with pytest.raises(CalculationInputError, match="unknown_friction_condition_id"):
        generate_friction_warnings("FC-DOES-NOT-EXIST")


def test_broken_reference_blocks_warnings(monkeypatch):
    original = population.load_population_records

    def fake(key):
        if key == "friction condition library":
            return [{
                "id": "FC-FAKE-BROKEN", "coating_id": "COAT-NOPE", "lubricant_id": "",
                "source_reference": "Src", "friction_model": "combined_or_unspecified",
            }]
        return original(key)

    monkeypatch.setattr(population, "load_population_records", fake)
    with pytest.raises(CalculationInputError, match="broken_reference"):
        generate_friction_warnings("FC-FAKE-BROKEN")


def test_warning_order_is_deterministic():
    a = generate_friction_warnings("FC-COAT-GEOMET")
    b = generate_friction_warnings("FC-COAT-GEOMET")
    assert a == b


# ---------------------------------------------------------------------
# Recommendation readiness
# ---------------------------------------------------------------------

def test_no_live_record_reaches_engineering_or_production_ready():
    """The critical assertion of this phase."""
    for fid in _all_friction_condition_ids():
        result = assess_recommendation_readiness(fid)
        assert result.recommendation_level != LEVEL_ENGINEERING_RECOMMENDATION_READY
        assert result.recommendation_level != LEVEL_PRODUCTION_RECOMMENDATION_READY


def test_every_live_record_is_warnings_only_or_comparison_only():
    for fid in _all_friction_condition_ids():
        result = assess_recommendation_readiness(fid)
        assert result.recommendation_level in (LEVEL_WARNINGS_ONLY, LEVEL_COMPARISON_ONLY)


def test_live_records_reach_comparison_only_since_overall_range_exists():
    result = assess_recommendation_readiness("FC-COAT-GEOMET")
    assert result.recommendation_level == LEVEL_COMPARISON_ONLY
    assert "reference_comparison" in result.available_capabilities


def test_incomplete_condition_both_ids_empty_is_warnings_only(monkeypatch):
    original = population.load_population_records

    def fake(key):
        if key == "friction condition library":
            return [{
                "id": "FC-FAKE-INCOMPLETE", "coating_id": "", "lubricant_id": "",
                "source_reference": "Src",
                "overall_friction_coefficient_min": 0.1,
                "overall_friction_coefficient_max": 0.2,
                "friction_model": "combined_or_unspecified",
            }]
        return original(key)

    monkeypatch.setattr(population, "load_population_records", fake)
    result = assess_recommendation_readiness("FC-FAKE-INCOMPLETE")
    assert result.recommendation_level == LEVEL_WARNINGS_ONLY
    assert result.recommendation_available is False
    assert any("incomplete_condition" in reason for reason in result.blocking_reasons)


def test_blocked_capabilities_never_include_lubricant_or_coating_recommendation():
    for fid in _all_friction_condition_ids():
        result = assess_recommendation_readiness(fid)
        assert "lubricant_recommendation" in result.blocked_capabilities
        assert "coating_recommendation" in result.blocked_capabilities
        assert "production_approval" in result.blocked_capabilities


def test_required_missing_data_lists_the_actual_gaps():
    result = assess_recommendation_readiness("FC-COAT-GEOMET")
    for item in ("verified_mu_thread", "verified_mu_bearing", "verified_k_factor",
                 "verified_corrosion_rating", "verified_reusability"):
        assert item in result.required_missing_data


def test_intended_use_annotates_gap_but_does_not_upgrade_level():
    result = assess_recommendation_readiness(
        "FC-COAT-GEOMET", intended_use="production_release",
    )
    assert result.recommendation_level == LEVEL_COMPARISON_ONLY  # unchanged
    assert any("intended_use" in w for w in result.engineering_warnings)


def test_intended_use_reference_comparison_no_gap_warning():
    result = assess_recommendation_readiness(
        "FC-COAT-GEOMET", intended_use="reference_comparison",
    )
    assert not any("intended_use=" in w for w in result.engineering_warnings)


# ---------------------------------------------------------------------
# Comparison capability -- purely descriptive
# ---------------------------------------------------------------------

def test_lower_higher_range_comparison():
    result = compare_friction_conditions("FC-LUBE-PTFE", "FC-LUBE-DRY")
    # PTFE (0.05-0.09) is strictly lower than Dry (0.14-0.22).
    assert result.range_relation == "a_lower"


def test_overlapping_ranges():
    result = compare_friction_conditions("FC-COAT-GEOMET", "FC-COAT-ZN")
    assert result.range_relation in ("overlapping", "identical")


def test_identical_ranges_detected():
    result = compare_friction_conditions("FC-COAT-GEOMET", "FC-COAT-GEOMET")
    assert result.range_relation == "identical"


def test_non_overlapping_ranges():
    result = compare_friction_conditions("FC-LUBE-ANTI_SEIZE", "FC-LUBE-DRY")
    assert result.range_relation in ("a_lower", "b_lower")


def test_comparison_never_states_better_or_safer():
    forbidden = ("better", "safer", "recommended", "superior", "worse")
    for fid_a, fid_b in [("FC-COAT-GEOMET", "FC-COAT-ZN"), ("FC-LUBE-PTFE", "FC-LUBE-DRY")]:
        result = compare_friction_conditions(fid_a, fid_b)
        text = " ".join(result.descriptive_statements).lower()
        for word in forbidden:
            assert word not in text


def test_comparison_always_states_no_tightening_recommendation():
    result = compare_friction_conditions("FC-COAT-GEOMET", "FC-COAT-ZN")
    assert (
        "No tightening recommendation can be derived from this comparison."
        in result.descriptive_statements
    )


def test_comparison_source_classification_coating_vs_lubricant():
    result = compare_friction_conditions("FC-COAT-GEOMET", "FC-LUBE-DRY")
    assert result.source_classification_a == "coating_based"
    assert result.source_classification_b == "lubricant_based"


def test_comparison_unknown_id_raises():
    with pytest.raises(CalculationInputError, match="unknown_friction_condition_id"):
        compare_friction_conditions("FC-COAT-GEOMET", "FC-NOPE")


# ---------------------------------------------------------------------
# API integration + backward compatibility
# ---------------------------------------------------------------------

def test_new_endpoint_returns_warnings_and_readiness():
    payload = {"friction_condition_id": "FC-COAT-GEOMET"}
    r = client.post("/api/friction-condition/assess", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["friction_condition_id"] == "FC-COAT-GEOMET"
    assert len(d["warnings"]) > 0
    assert d["recommendation_readiness"]["recommendation_level"] == LEVEL_COMPARISON_ONLY
    assert "comparison" not in d


def test_new_endpoint_with_compare_with_id_adds_comparison():
    payload = {"friction_condition_id": "FC-COAT-GEOMET", "compare_with_id": "FC-COAT-ZN"}
    r = client.post("/api/friction-condition/assess", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "comparison" in d
    assert d["comparison"]["friction_condition_id_a"] == "FC-COAT-GEOMET"


def test_new_endpoint_unknown_id_returns_422():
    payload = {"friction_condition_id": "FC-NOPE"}
    r = client.post("/api/friction-condition/assess", json=payload, headers=_auth())
    assert r.status_code == 422


def test_new_endpoint_with_intended_use():
    payload = {"friction_condition_id": "FC-COAT-GEOMET", "intended_use": "production_release"}
    r = client.post("/api/friction-condition/assess", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert any("intended_use" in w for w in d["recommendation_readiness"]["engineering_warnings"])


def test_engineering_check_unaffected_by_new_endpoint_existing():
    r = client.post("/api/engineering/check", json=_base_payload(), headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "friction_recommendation_readiness" not in d
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]


def test_engineering_check_with_friction_condition_id_still_works():
    payload = _base_payload(friction_condition_id="FC-COAT-GEOMET")
    r = client.post("/api/engineering/check", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    assert "friction_readiness" in r.json()


# ---------------------------------------------------------------------
# Regression + import/smoke
# ---------------------------------------------------------------------

def test_full_regression_torque_monotonic():
    r = client.post("/api/engineering/check", json=_base_payload(), headers=_auth())
    d = r.json()
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]
    assert d["internal_thread_sf"] > 0
    assert d["external_thread_sf"] > 0


def test_calculation_engine_package_imports_cleanly():
    import backend.calculation_engine.friction_recommendations  # noqa: F401


def test_backend_app_still_imports():
    import backend.app as app_module

    assert app_module.app is not None
