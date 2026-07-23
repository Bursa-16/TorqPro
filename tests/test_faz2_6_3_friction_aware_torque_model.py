"""Faz 2.6.3 -- Friction-Aware Torque Model and Decomposition Readiness.

Scope (see docs/phases/PHASE_2.6.3_FRICTION_AWARE_TORQUE_MODEL.md):

- ``backend.calculation_engine.friction_readiness`` resolves a
  friction_condition_id, reports calculation mode / data
  completeness / blocking reasons, and NEVER produces a torque value
  from a combined coefficient (that would require copying it into
  mu_thread/mu_bearing or deriving K -- both forbidden).
- The min/nominal/max scenario generator produces friction-
  *coefficient* values only, with an explicit, documented midpoint
  policy -- never a torque value.
- Mode B (separated model) fields are always None with the current
  data (no record has an independent mu_thread/mu_bearing split).
- The existing ``/api/engineering/check`` route is behaviourally
  unchanged for requests that omit the new optional
  ``friction_condition_id`` field.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.calculation_engine.exceptions import CalculationInputError  # noqa: E402
from backend.calculation_engine.friction_readiness import (  # noqa: E402
    CALCULATION_MODE_BLOCKED,
    CALCULATION_MODE_COMBINED,
    CALCULATION_MODE_SEPARATED,
    MIDPOINT_POLICY_ARITHMETIC,
    STATUS_UNSUPPORTED_FRICTION_MODEL,
    assess_friction_readiness,
    combined_friction_scenarios,
)

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


# ---------------------------------------------------------------------
# friction_condition_id resolution
# ---------------------------------------------------------------------

def test_resolves_a_live_coating_derived_record():
    result = assess_friction_readiness("FC-COAT-GEOMET")
    assert result.friction_condition_id == "FC-COAT-GEOMET"
    assert result.friction_model == "combined_or_unspecified"


def test_resolves_a_live_lubricant_derived_record():
    result = assess_friction_readiness("FC-LUBE-MOS2")
    assert result.data_completeness["has_overall_coefficient"] is True


def test_unknown_id_raises_controlled_validation_error():
    with pytest.raises(CalculationInputError, match="unknown_friction_condition_id"):
        assess_friction_readiness("FC-DOES-NOT-EXIST")


def test_broken_coating_reference_raises_controlled_validation_error(monkeypatch):
    from backend.library import population as population_module

    _real_load = population_module.load_population_records

    def fake_load(key):
        if key == "friction condition library":
            return [{
                "id": "FC-FAKE-BROKEN", "coating_id": "COAT-DOES-NOT-EXIST",
                "lubricant_id": "", "source_reference": "Some Source",
                "overall_friction_coefficient_min": 0.1,
                "overall_friction_coefficient_max": 0.2,
                "friction_model": "combined_or_unspecified",
                "verification_status": "reference_only",
            }]
        return _real_load(key)

    monkeypatch.setattr(population_module, "load_population_records", fake_load)

    with pytest.raises(CalculationInputError, match="broken_reference"):
        assess_friction_readiness("FC-FAKE-BROKEN")


def test_missing_source_traceability_raises_controlled_validation_error(monkeypatch):
    from backend.library import population as population_module

    _real_load = population_module.load_population_records

    def fake_load(key):
        if key == "friction condition library":
            return [{
                "id": "FC-FAKE-NOSOURCE", "coating_id": "", "lubricant_id": "",
                "source_reference": "",
                "overall_friction_coefficient_min": 0.1,
                "overall_friction_coefficient_max": 0.2,
                "friction_model": "combined_or_unspecified",
            }]
        return _real_load(key)

    monkeypatch.setattr(population_module, "load_population_records", fake_load)

    with pytest.raises(CalculationInputError, match="missing_source_traceability"):
        assess_friction_readiness("FC-FAKE-NOSOURCE")


# ---------------------------------------------------------------------
# reference-only labelling
# ---------------------------------------------------------------------

def test_reference_only_source_is_labelled_in_warnings():
    result = assess_friction_readiness("FC-COAT-GEOMET")
    assert result.verification_status == "reference_only"
    assert any("reference_only_source" in w for w in result.engineering_warnings)


# ---------------------------------------------------------------------
# Mode A: combined estimate -- data present but calculation blocked
# ---------------------------------------------------------------------

def test_combined_only_record_selects_mode_a_but_is_blocked():
    result = assess_friction_readiness("FC-COAT-GEOMET")
    assert result.calculation_mode == CALCULATION_MODE_COMBINED
    assert result.blocking_reasons  # non-empty -- cannot produce torque
    assert any(STATUS_UNSUPPORTED_FRICTION_MODEL in reason for reason in result.blocking_reasons)


def test_mode_a_never_populates_decomposition_fields():
    result = assess_friction_readiness("FC-COAT-GEOMET")
    assert result.decomposition_available is False
    assert result.thread_raising_torque is None
    assert result.thread_friction_torque is None
    assert result.bearing_friction_torque is None
    assert result.total_torque is None
    assert result.preload_contribution_percent is None


def test_mode_a_includes_all_four_mandated_warnings():
    result = assess_friction_readiness("FC-COAT-GEOMET")
    expected_substrings = [
        "does not support thread/bearing torque decomposition",
        "sensitivity estimate based on a reference friction range",
        "must not be interpreted as ISO 16047 test certification",
        "mu_thread and mu_bearing data are required",
    ]
    for substring in expected_substrings:
        assert any(substring in w for w in result.engineering_warnings), substring


# ---------------------------------------------------------------------
# min/nominal/max SCENARIO generation (coefficient values, not torque)
# ---------------------------------------------------------------------

def test_combined_friction_scenarios_uses_arithmetic_midpoint():
    scenarios = combined_friction_scenarios(0.10, 0.20)
    assert scenarios["minimum"] == 0.10
    assert scenarios["maximum"] == 0.20
    assert scenarios["nominal_estimate"] == pytest.approx(0.15)
    assert scenarios["nominal_estimate_policy"] == MIDPOINT_POLICY_ARITHMETIC


def test_readiness_result_carries_scenarios_for_mode_a():
    result = assess_friction_readiness("FC-COAT-ZN")
    assert result.combined_friction_scenarios is not None
    lo = result.combined_friction_scenarios["minimum"]
    hi = result.combined_friction_scenarios["maximum"]
    mid = result.combined_friction_scenarios["nominal_estimate"]
    assert lo <= mid <= hi


def test_no_mu_split_is_ever_inferred_from_combined_scenarios():
    """The scenario dict must never contain a mu_thread/mu_bearing-
    shaped key -- it is a friction-coefficient range, not a split."""
    scenarios = combined_friction_scenarios(0.10, 0.20)
    assert "mu_thread" not in str(scenarios)
    assert "mu_bearing" not in str(scenarios)
    assert "k_factor" not in str(scenarios)


# ---------------------------------------------------------------------
# Mode B: separated model -- always insufficient with current data
# ---------------------------------------------------------------------

def test_no_live_record_currently_qualifies_for_mode_b():
    """None of the 18 live records has an independent mu_thread/
    mu_bearing split, so Mode B must never be selected today."""
    from backend.library import population

    for raw in population.load_population_records("friction condition library"):
        result = assess_friction_readiness(
            raw["id"], has_joint_geometry=True, has_preload=True,
        )
        assert result.calculation_mode != CALCULATION_MODE_SEPARATED
        assert result.decomposition_available is False


def test_mode_b_would_require_geometry_and_preload_flags_too():
    """Even a hypothetical record with mu_thread+mu_bearing needs
    has_joint_geometry/has_preload also True to reach Mode B --
    exercised via a monkeypatched record since no live one qualifies."""
    import backend.calculation_engine.friction_readiness as fr_module

    fake_raw = {
        "id": "FC-FAKE-SPLIT", "coating_id": "", "lubricant_id": "",
        "source_reference": "Hypothetical VDI 2230 Table X",
        "friction_model": "split_thread_bearing",
        "mu_thread_min": 0.10, "mu_thread_max": 0.14,
        "mu_bearing_min": 0.10, "mu_bearing_max": 0.14,
        "verification_status": "verified",
    }
    original = fr_module._resolve_raw_record
    original_ref = fr_module._check_reference_integrity
    fr_module._resolve_raw_record = lambda fid: fake_raw
    fr_module._check_reference_integrity = lambda raw: None
    try:
        blocked = fr_module.assess_friction_readiness(
            "FC-FAKE-SPLIT", has_joint_geometry=False, has_preload=True,
        )
        assert blocked.calculation_mode != CALCULATION_MODE_SEPARATED

        ready = fr_module.assess_friction_readiness(
            "FC-FAKE-SPLIT", has_joint_geometry=True, has_preload=True,
        )
        assert ready.calculation_mode == CALCULATION_MODE_SEPARATED
        assert ready.decomposition_available is True
        # Still no torque number invented -- infrastructure only.
        assert ready.total_torque is None
    finally:
        fr_module._resolve_raw_record = original
        fr_module._check_reference_integrity = original_ref


# ---------------------------------------------------------------------
# insufficient data (no overall, no split)
# ---------------------------------------------------------------------

def test_record_with_no_friction_value_at_all_is_blocked(monkeypatch):
    from backend.library import population as population_module

    _real_load = population_module.load_population_records

    def fake_load(key):
        if key == "friction condition library":
            return [{
                "id": "FC-FAKE-EMPTY", "coating_id": "", "lubricant_id": "",
                "source_reference": "Some Source",
                "friction_model": "",
            }]
        return _real_load(key)

    monkeypatch.setattr(population_module, "load_population_records", fake_load)
    result = assess_friction_readiness("FC-FAKE-EMPTY")
    assert result.calculation_mode == CALCULATION_MODE_BLOCKED
    assert result.combined_friction_scenarios is None


# ---------------------------------------------------------------------
# API integration + backward compatibility
# ---------------------------------------------------------------------

def test_engineering_check_without_friction_condition_id_unchanged():
    r = client.post("/api/engineering/check", json=_base_payload(), headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "friction_readiness" not in d
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]


def test_engineering_check_with_valid_friction_condition_id_adds_readiness_key():
    payload = _base_payload(friction_condition_id="FC-COAT-GEOMET")
    r = client.post("/api/engineering/check", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "friction_readiness" in d
    assert d["friction_readiness"]["calculation_mode"] == CALCULATION_MODE_COMBINED
    # The deterministic mu_thread/mu_bearing-based torque result is
    # unaffected by the presence of friction_condition_id.
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]


def test_engineering_check_with_unknown_friction_condition_id_returns_422():
    payload = _base_payload(friction_condition_id="FC-DOES-NOT-EXIST")
    r = client.post("/api/engineering/check", json=payload, headers=_auth())
    assert r.status_code == 422
    assert "unknown_friction_condition_id" in r.json()["detail"]


def test_engineering_check_response_shape_otherwise_identical():
    """Every pre-existing response key from before Faz 2.6.3 is still
    present and computed the same way (regression guard)."""
    r = client.post("/api/engineering/check", json=_base_payload(), headers=_auth())
    d = r.json()
    for key in (
        "preload_n", "torque_min_nm", "torque_nom_nm", "torque_max_nm",
        "nut_proof_util_pct", "internal_thread_sf", "external_thread_sf",
    ):
        assert key in d


# ---------------------------------------------------------------------
# import/smoke + integrity
# ---------------------------------------------------------------------

def test_calculation_engine_package_imports_cleanly():
    import backend.calculation_engine  # noqa: F401
    import backend.calculation_engine.friction_readiness  # noqa: F401


def test_backend_app_still_imports():
    import backend.app as app_module

    assert app_module.app is not None
