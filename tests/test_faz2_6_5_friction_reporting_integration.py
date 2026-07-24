"""Faz 2.6.5 -- Friction Condition Reporting and Integration.

Scope (see docs/phases/PHASE_2.6.5_FRICTION_REPORTING_INTEGRATION.md):

- build_friction_condition_report_section() formats the Faz 2.6.3/
  2.6.4 domain results into a structured, JSON-serializable report
  section. It computes no new engineering value.
- Safety labels are deterministic and field-derived.
- POST /api/friction-condition/report-preview is additive; every
  pre-existing route/response is unaffected.
- No report for any of the 18 live records may contain "recommended
  torque", "production approved", "certified ISO 16047", "best
  lubricant" or "best coating" language.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.calculation_engine.exceptions import CalculationInputError  # noqa: E402
from backend.calculation_engine.friction_report import (  # noqa: E402
    LABEL_DECOMPOSITION_UNAVAILABLE,
    LABEL_NOT_CERTIFIED,
    LABEL_NO_TIGHTENING_RECOMMENDATION,
    LABEL_PRODUCTION_APPROVAL_NOT_AVAILABLE,
    LABEL_REFERENCE_ONLY,
    build_friction_condition_report_section,
)
from backend.library import population  # noqa: E402

client = TestClient(app)

_FORBIDDEN_PHRASES = (
    "recommended torque", "production approved", "production-approved",
    "iso 16047 certified", "is a certified iso 16047", "best lubricant", "best coating",
    "torque reduction percentage",
)


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
# Report section content
# ---------------------------------------------------------------------

def test_report_section_contains_all_mandated_fields():
    section = build_friction_condition_report_section("FC-COAT-GEOMET")
    d = section.to_dict()
    for key in (
        "friction_condition_id", "coating_reference", "lubricant_reference",
        "friction_model", "overall_friction_coefficient_minimum",
        "overall_friction_coefficient_nominal_estimate",
        "overall_friction_coefficient_maximum", "nominal_policy", "source",
        "readiness", "engineering_warnings", "safety_labels", "intended_use",
        "comparison", "report_generated_at", "application_version",
    ):
        assert key in d


def test_nominal_policy_is_arithmetic_midpoint():
    section = build_friction_condition_report_section("FC-COAT-GEOMET")
    d = section.to_dict()
    lo = d["overall_friction_coefficient_minimum"]
    hi = d["overall_friction_coefficient_maximum"]
    nominal = d["overall_friction_coefficient_nominal_estimate"]
    assert nominal == pytest.approx((lo + hi) / 2)
    assert d["nominal_policy"] == "arithmetic_midpoint_of_reference_range"


def test_source_traceability_fields_present():
    section = build_friction_condition_report_section("FC-COAT-GEOMET")
    src = section.to_dict()["source"]
    assert src["source_reference"] != ""
    assert src["source_type"] != ""
    assert src["verification_status"] == "reference_only"
    assert src["record_checksum"] != ""
    assert src["data_version"] != ""


def test_readiness_summary_present_and_matches_recommendation_level():
    from backend.calculation_engine.friction_recommendations import assess_recommendation_readiness

    section = build_friction_condition_report_section("FC-COAT-GEOMET")
    expected = assess_recommendation_readiness("FC-COAT-GEOMET")
    assert section.readiness.recommendation_level == expected.recommendation_level


def test_no_decomposition_fields_present_in_report_model():
    """The report model has no thread_raising_torque/thread_friction_torque/
    etc. fields at all -- not even as None -- since Mode B is never
    reached; this is a structural guard, not just a value check."""
    section = build_friction_condition_report_section("FC-COAT-GEOMET")
    d = json.dumps(section.to_dict())
    for forbidden_field in (
        "thread_raising_torque", "thread_friction_torque",
        "bearing_friction_torque", "total_torque",
    ):
        assert forbidden_field not in d


# ---------------------------------------------------------------------
# Safety labels
# ---------------------------------------------------------------------

def test_reference_only_and_not_certified_labels_for_every_live_record():
    for fid in _all_friction_condition_ids():
        section = build_friction_condition_report_section(fid)
        assert LABEL_REFERENCE_ONLY in section.safety_labels
        assert LABEL_NOT_CERTIFIED in section.safety_labels


def test_decomposition_unavailable_label_for_every_live_record():
    for fid in _all_friction_condition_ids():
        section = build_friction_condition_report_section(fid)
        assert LABEL_DECOMPOSITION_UNAVAILABLE in section.safety_labels


def test_no_tightening_recommendation_label_for_every_live_record():
    for fid in _all_friction_condition_ids():
        section = build_friction_condition_report_section(fid)
        assert LABEL_NO_TIGHTENING_RECOMMENDATION in section.safety_labels


def test_production_approval_not_available_for_every_live_record():
    for fid in _all_friction_condition_ids():
        section = build_friction_condition_report_section(fid)
        assert LABEL_PRODUCTION_APPROVAL_NOT_AVAILABLE in section.safety_labels


def test_combined_friction_warnings_present_in_report():
    section = build_friction_condition_report_section("FC-COAT-GEOMET")
    assert (
        "Thread and bearing friction are not separately verified."
        in section.engineering_warnings
    )


# ---------------------------------------------------------------------
# Nothing forbidden appears in any of the 18 live reports
# ---------------------------------------------------------------------

def test_no_forbidden_language_in_any_live_report():
    for fid in _all_friction_condition_ids():
        section = build_friction_condition_report_section(fid)
        text = json.dumps(section.to_dict()).lower()
        for phrase in _FORBIDDEN_PHRASES:
            assert phrase not in text, f"{fid}: forbidden phrase {phrase!r} found"


# ---------------------------------------------------------------------
# Comparison reporting
# ---------------------------------------------------------------------

def test_comparison_report_overlapping_ranges():
    section = build_friction_condition_report_section(
        "FC-COAT-GEOMET", compare_with_id="FC-COAT-ZN",
    )
    assert section.comparison is not None
    assert section.comparison.range_relation in ("overlapping", "identical")
    assert section.comparison.is_self_comparison is False


def test_comparison_report_non_overlapping_ranges():
    section = build_friction_condition_report_section(
        "FC-LUBE-PTFE", compare_with_id="FC-LUBE-DRY",
    )
    assert section.comparison.range_relation in ("a_lower", "b_lower")


def test_comparison_report_identical_ranges_self_comparison_flagged():
    section = build_friction_condition_report_section(
        "FC-COAT-GEOMET", compare_with_id="FC-COAT-GEOMET",
    )
    assert section.comparison.is_self_comparison is True
    assert section.comparison.range_relation == "identical"


def test_comparison_report_never_contains_evaluative_language():
    forbidden = ("better", "safer", "superior", "preferred", "recommended")
    section = build_friction_condition_report_section(
        "FC-COAT-GEOMET", compare_with_id="FC-COAT-ZN",
    )
    text = " ".join(section.comparison.descriptive_statements).lower()
    for word in forbidden:
        assert word not in text


def test_no_comparison_when_compare_with_id_not_supplied():
    section = build_friction_condition_report_section("FC-COAT-GEOMET")
    assert section.comparison is None


# ---------------------------------------------------------------------
# Error behaviour
# ---------------------------------------------------------------------

def test_unknown_friction_condition_id_raises():
    with pytest.raises(CalculationInputError, match="unknown_friction_condition_id"):
        build_friction_condition_report_section("FC-NOPE")


def test_unknown_compare_with_id_raises():
    with pytest.raises(CalculationInputError, match="unknown_friction_condition_id"):
        build_friction_condition_report_section(
            "FC-COAT-GEOMET", compare_with_id="FC-NOPE",
        )


def test_broken_reference_raises(monkeypatch):
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
        build_friction_condition_report_section("FC-FAKE-BROKEN")


def test_missing_source_raises(monkeypatch):
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
        build_friction_condition_report_section("FC-FAKE-NOSRC")


def test_invalid_intended_use_raises():
    with pytest.raises(CalculationInputError, match="invalid_intended_use"):
        build_friction_condition_report_section(
            "FC-COAT-GEOMET", intended_use="not_a_real_use",
        )


def test_valid_intended_use_does_not_raise():
    section = build_friction_condition_report_section(
        "FC-COAT-GEOMET", intended_use="engineering_calculation",
    )
    assert section.intended_use == "engineering_calculation"


# ---------------------------------------------------------------------
# Deterministic order + JSON serialization
# ---------------------------------------------------------------------

def test_warning_order_is_deterministic_in_report():
    a = build_friction_condition_report_section("FC-COAT-GEOMET").engineering_warnings
    b = build_friction_condition_report_section("FC-COAT-GEOMET").engineering_warnings
    assert a == b


def test_report_section_is_json_serializable():
    section = build_friction_condition_report_section(
        "FC-COAT-GEOMET", compare_with_id="FC-COAT-ZN",
    )
    encoded = json.dumps(section.to_dict())
    decoded = json.loads(encoded)
    assert decoded["friction_condition_id"] == "FC-COAT-GEOMET"


# ---------------------------------------------------------------------
# API integration + backward compatibility
# ---------------------------------------------------------------------

def test_report_preview_endpoint_returns_full_section():
    payload = {"friction_condition_id": "FC-COAT-GEOMET"}
    r = client.post("/api/friction-condition/report-preview", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["friction_condition_id"] == "FC-COAT-GEOMET"
    assert "safety_labels" in d
    assert "readiness" in d


def test_report_preview_endpoint_with_comparison():
    payload = {
        "friction_condition_id": "FC-COAT-GEOMET",
        "compare_with_friction_condition_id": "FC-COAT-ZN",
    }
    r = client.post("/api/friction-condition/report-preview", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["comparison"] is not None


def test_report_preview_endpoint_unknown_id_returns_422():
    payload = {"friction_condition_id": "FC-NOPE"}
    r = client.post("/api/friction-condition/report-preview", json=payload, headers=_auth())
    assert r.status_code == 422


def test_report_preview_endpoint_invalid_intended_use_returns_422():
    payload = {"friction_condition_id": "FC-COAT-GEOMET", "friction_intended_use": "nonsense"}
    r = client.post("/api/friction-condition/report-preview", json=payload, headers=_auth())
    assert r.status_code == 422


def test_engineering_check_without_friction_condition_id_unchanged():
    """Pre-existing behaviour byte-for-byte: no report-related key
    leaks into /api/engineering/check's response."""
    r = client.post("/api/engineering/check", json=_base_payload(), headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert "friction_readiness" not in d
    assert "friction_recommendation_readiness" not in d
    assert "safety_labels" not in d
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]


def test_engineering_check_with_friction_condition_id_still_has_only_readiness_key():
    payload = _base_payload(friction_condition_id="FC-COAT-GEOMET")
    r = client.post("/api/engineering/check", json=payload, headers=_auth())
    d = r.json()
    assert "friction_readiness" in d
    assert "safety_labels" not in d["friction_readiness"]  # not duplicated from report layer


def test_friction_condition_assess_endpoint_still_works_unaffected():
    payload = {"friction_condition_id": "FC-COAT-GEOMET"}
    r = client.post("/api/friction-condition/assess", json=payload, headers=_auth())
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------
# Regression + import/smoke
# ---------------------------------------------------------------------

def test_full_regression_torque_monotonic():
    r = client.post("/api/engineering/check", json=_base_payload(), headers=_auth())
    d = r.json()
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]


def test_calculation_engine_friction_report_imports_cleanly():
    import backend.calculation_engine.friction_report  # noqa: F401


def test_backend_app_still_imports():
    import backend.app as app_module

    assert app_module.app is not None


def test_registry_population_integrity_clean():
    report = population.run_all_integrity_checks()
    assert report["broken_friction_condition_references"] == []
    assert report["checksum_mismatches"] == []
