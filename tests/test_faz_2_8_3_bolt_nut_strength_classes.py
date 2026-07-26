"""Faz 2.8.3 tests: bolt/nut strength class engineering.

Covers: typed data/model layer, ISO 898 designation parser, business
validation, library filtering, strength-class compatibility engine,
manual-override resolution, the 5 new API endpoints, and the
strength-class report collector/renderer. Reuses existing fixtures/
conventions (tests/conftest.py's isolated TestClient DB, the
"Protype Lab" / "A1234" seeded login used across other API tests).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import app
from backend.calculation_engine import strength_class_report as report_module
from backend.library import strength_classes as sc
from backend.library import strength_compatibility as compat
from backend.library import strength_validator as sv

client = TestClient(app)


def auth():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def auth_headers():
    return auth()


def _raw_records():
    with open(sc.DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------
# Data / model tests
# ---------------------------------------------------------------------

class TestDataAndModels:
    def test_bolt_record_count_is_12(self):
        assert len(sc.list_bolt_strength_classes()) == 12

    def test_nut_record_count_is_8(self):
        assert len(sc.list_nut_property_classes()) == 8

    def test_total_record_count_is_20(self):
        assert len(sc.list_bolt_strength_classes()) + len(sc.list_nut_property_classes()) == 20

    def test_iso898_1_bolt_count_is_9(self):
        bolts = [b for b in sc.list_bolt_strength_classes() if b.standard == "ISO 898-1"]
        assert len(bolts) == 9
        assert {b.designation for b in bolts} == {
            "4.6", "4.8", "5.6", "5.8", "6.8", "8.8", "9.8", "10.9", "12.9",
        }

    def test_iso3506_1_bolt_count_is_3(self):
        bolts = [b for b in sc.list_bolt_strength_classes() if b.standard == "ISO 3506-1"]
        assert len(bolts) == 3
        assert {b.designation for b in bolts} == {"A2-70", "A4-70", "A4-80"}

    def test_iso898_2_nut_count_is_8(self):
        nuts = [n for n in sc.list_nut_property_classes() if n.standard == "ISO 898-2"]
        assert len(nuts) == 8

    def test_04_designation_preserved_as_string(self):
        raw = _raw_records()
        rec = next(r for r in raw["nut_records"] if r["designation"] == "04")
        assert isinstance(rec["designation"], str)
        assert rec["designation"] == "04"
        typed = sc.get_nut_property_class("04")
        assert isinstance(typed.designation, str)
        assert typed.designation == "04"

    def test_bolt_records_parse_as_bolt_strength_class_record(self):
        for b in sc.list_bolt_strength_classes():
            assert isinstance(b, sc.BoltStrengthClassRecord)

    def test_nut_records_parse_as_nut_property_class_record(self):
        for n in sc.list_nut_property_classes():
            assert isinstance(n, sc.NutPropertyClassRecord)

    def test_bolt_record_rejected_by_nut_model(self):
        raw = _raw_records()
        assert sv.bolt_record_cannot_parse_as_nut(raw["bolt_records"][0])

    def test_nut_record_rejected_by_bolt_model(self):
        raw = _raw_records()
        assert sv.nut_record_cannot_parse_as_bolt(raw["nut_records"][0])

    def test_bolt_records_json_serializable(self):
        for b in sc.list_bolt_strength_classes():
            json.dumps(b.model_dump(mode="json"))

    def test_nut_records_json_serializable(self):
        for n in sc.list_nut_property_classes():
            json.dumps(n.model_dump(mode="json"))

    def test_every_record_has_source_and_verification_status(self):
        for b in sc.list_bolt_strength_classes():
            assert b.source
            assert b.verification_status is not None
        for n in sc.list_nut_property_classes():
            assert n.source
            assert n.verification_status is not None

    def test_generic_legacy_strength_class_library_unaffected(self):
        from backend.library.strength_class_library import STRENGTH_CLASS_LIBRARY
        from backend.library.models import StrengthClassRecord

        assert STRENGTH_CLASS_LIBRARY.metadata.name == "Strength Class Library"
        assert StrengthClassRecord is not None


# ---------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------

class TestIso898Parser:
    @pytest.mark.parametrize("designation,rm,ratio,ry", [
        ("4.6", 400.0, 0.6, 240.0),
        ("8.8", 800.0, 0.8, 640.0),
        ("10.9", 1000.0, 0.9, 900.0),
        ("12.9", 1200.0, 0.9, 1080.0),
    ])
    def test_valid_designations(self, designation, rm, ratio, ry):
        result = sc.parse_iso898_bolt_designation(designation)
        assert result["nominal_tensile_strength_mpa"] == rm
        assert result["yield_ratio"] == ratio
        assert result["nominal_yield_strength_mpa"] == ry

    @pytest.mark.parametrize("bad", ["", "8", "8.", ".8", "8.8.1", "abc", "0.8", "8.0"])
    def test_invalid_designations_rejected(self, bad):
        with pytest.raises(sc.Iso898DesignationError):
            sc.parse_iso898_bolt_designation(bad)

    def test_a2_70_not_derived_by_iso898_parser(self):
        with pytest.raises(sc.Iso898DesignationError):
            sc.parse_iso898_bolt_designation("A2-70")

    def test_a4_80_not_derived_by_iso898_parser(self):
        with pytest.raises(sc.Iso898DesignationError):
            sc.parse_iso898_bolt_designation("A4-80")


# ---------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------

class TestValidation:
    def test_negative_value_rejected(self):
        issues = sv.find_negative_or_invalid_values([
            {"min_tensile_strength_mpa": -10}
        ])
        assert any(i.code == "non_positive_value" for i in issues)

    def test_empty_designation_rejected(self):
        issues = sv.find_empty_designations([{"designation": ""}])
        assert any(i.code == "empty_designation" for i in issues)

    def test_diameter_min_gt_max_rejected(self):
        issues = sv.find_diameter_range_violations([
            {"diameter_min_mm": 40, "diameter_max_mm": 5}
        ])
        assert any(i.code == "diameter_range_inverted" for i in issues)

    def test_hardness_min_gt_max_rejected(self):
        issues = sv.find_hardness_range_violations([
            {"hardness_min": 400, "hardness_max": 200}
        ])
        assert any(i.code == "hardness_range_inverted" for i in issues)

    def test_min_yield_gt_min_tensile_rejected(self):
        issues = sv.find_yield_tensile_violations([
            {"min_yield_strength_mpa": 900, "min_tensile_strength_mpa": 800}
        ])
        assert any(i.code == "yield_exceeds_tensile" for i in issues)

    def test_invalid_yield_ratio_rejected(self):
        issues = sv.find_yield_ratio_violations([{"yield_ratio": 1.5}])
        assert any(i.code == "yield_ratio_out_of_range" for i in issues)
        issues0 = sv.find_yield_ratio_violations([{"yield_ratio": 0}])
        assert any(i.code == "yield_ratio_out_of_range" for i in issues0)

    def test_invalid_material_family_rejected_by_model(self):
        with pytest.raises(ValidationError):
            sc.BoltStrengthClassRecord.model_validate({
                "id": "X", "designation": "8.8", "standard": "ISO 898-1",
                "material_family": "not_a_real_family",
                "verification_status": "reference_only",
            })

    def test_invalid_verification_status_rejected(self):
        issues = sv.find_invalid_verification_status([{"verification_status": "made_up"}])
        assert any(i.code == "invalid_verification_status" for i in issues)
        with pytest.raises(ValidationError):
            sc.BoltStrengthClassRecord.model_validate({
                "id": "X", "designation": "8.8", "standard": "ISO 898-1",
                "material_family": "carbon_alloy_steel",
                "verification_status": "made_up",
            })

    def test_duplicate_standard_designation_overlapping_range_rejected(self):
        issues = sv.find_duplicate_standard_designation_diameter([
            {"standard": "ISO 898-1", "designation": "8.8",
             "diameter_min_mm": 5, "diameter_max_mm": 39},
            {"standard": "ISO 898-1", "designation": "8.8",
             "diameter_min_mm": 10, "diameter_max_mm": 20},
        ])
        assert any(i.code == "duplicate_overlapping_range" for i in issues)

    def test_actual_dataset_has_zero_validation_issues(self):
        raw = _raw_records()
        assert sv.validate_bolt_strength_class_records(raw["bolt_records"]) == []
        assert sv.validate_nut_property_class_records(raw["nut_records"]) == []


# ---------------------------------------------------------------------
# Library filter tests
# ---------------------------------------------------------------------

class TestLibraryFilters:
    def test_standard_filter(self):
        result = sc.list_bolt_strength_classes(standard="ISO 3506-1")
        assert len(result) == 3
        assert all(b.standard == "ISO 3506-1" for b in result)

    def test_material_family_filter(self):
        result = sc.list_bolt_strength_classes(material_family="stainless_a4")
        assert {b.designation for b in result} == {"A4-70", "A4-80"}

    def test_designation_filter(self):
        result = sc.list_bolt_strength_classes(designation="8.8")
        assert len(result) == 1
        assert result[0].designation == "8.8"

    def test_diameter_filter(self):
        result = sc.list_bolt_strength_classes(diameter_mm=20)
        assert len(result) == 12  # all bolt records use the M5-M39 range
        result_oor = sc.list_bolt_strength_classes(diameter_mm=200)
        assert result_oor == []

    def test_verification_status_filter(self):
        result = sc.list_bolt_strength_classes(verification_status="provisional")
        assert {b.designation for b in result} == {"A2-70", "A4-70", "A4-80"}

    def test_combined_filters(self):
        result = sc.list_bolt_strength_classes(standard="ISO 898-1", diameter_mm=10)
        assert len(result) == 9

    def test_empty_string_filter_is_not_none(self):
        # "" is a literal (non-matching) filter value, never silently
        # treated the same as "no filter".
        assert sc.list_bolt_strength_classes(designation="") == []
        assert sc.list_bolt_strength_classes(designation=None) != []

    def test_88_lookup(self):
        r = sc.get_bolt_strength_class("8.8")
        assert r is not None and r.designation == "8.8"

    def test_04_lookup(self):
        r = sc.get_nut_property_class("04")
        assert r is not None and r.designation == "04"

    def test_a2_70_lookup(self):
        r = sc.get_bolt_strength_class("A2-70")
        assert r is not None and r.material_family == sc.StrengthClassMaterialFamily.STAINLESS_A2

    def test_unknown_designation_returns_none(self):
        assert sc.get_bolt_strength_class("99.9") is None
        assert sc.get_nut_property_class("99") is None


# ---------------------------------------------------------------------
# Compatibility tests
# ---------------------------------------------------------------------

class TestCompatibility:
    def _check(self, bolt, nut, **kw):
        return compat.check_bolt_nut_strength_compatibility(bolt, nut, **kw)

    def test_8_8_plus_nut_8_compatible(self):
        r = self._check("8.8", "8")
        assert r.status == "compatible"
        assert r.compatible is True

    def test_10_9_plus_nut_8_not_compatible(self):
        r = self._check("10.9", "8")
        assert r.status == "not_compatible"
        assert r.compatible is False

    def test_10_9_plus_nut_10_compatible(self):
        r = self._check("10.9", "10")
        assert r.status == "compatible"

    def test_12_9_plus_nut_12_compatible(self):
        r = self._check("12.9", "12")
        assert r.status == "compatible"

    def test_unknown_bolt_is_unknown(self):
        r = self._check("99.9", "8")
        assert r.status == "unknown"
        assert r.compatible is False

    def test_unknown_nut_is_unknown(self):
        r = self._check("8.8", "99")
        assert r.status == "unknown"

    def test_diameter_out_of_range_conditionally_compatible(self):
        r = self._check("8.8", "8", nominal_diameter_mm=200)
        assert r.status == "conditionally_compatible"
        assert "diameter_out_of_range" in r.warning_codes

    def test_stainless_bolt_carbon_nut_not_directly_compatible(self):
        r = self._check("A2-70", "8")
        assert r.status == "not_compatible"
        assert r.compatible is False

    def test_iso898_and_iso898_1_same_family(self):
        r = self._check("8.8", "8", standard="ISO 898")
        assert not any("standard_mismatch_input" in c for c in r.warning_codes)
        assert r.status == "compatible"

    def test_iso898_and_iso3506_different_family(self):
        r = self._check("A2-70", "8")
        assert any("Cross-standard-family" in reason for reason in r.reasons)

    def test_material_family_mismatch_warns(self):
        r = self._check("8.8", "8", material_family="stainless_a2")
        assert "material_family_mismatch_input" in r.warning_codes

    def test_real_nut_strength_deficiency_stays_not_compatible(self):
        r = self._check("12.9", "8")
        assert r.status == "not_compatible"

    def test_warning_code_order_deterministic(self):
        r1 = self._check("8.8", "8", nominal_diameter_mm=200)
        r2 = self._check("8.8", "8", nominal_diameter_mm=200)
        assert r1.warning_codes == r2.warning_codes

    def test_same_input_same_output(self):
        r1 = self._check("10.9", "8")
        r2 = self._check("10.9", "8")
        assert r1.model_dump() == r2.model_dump()

    def test_compatible_boolean_only_true_when_status_compatible(self):
        for bolt, nut in [("8.8", "8"), ("10.9", "8"), ("A2-70", "8"), ("99.9", "8")]:
            r = self._check(bolt, nut)
            assert r.compatible == (r.status == "compatible")


# ---------------------------------------------------------------------
# Manual override / resolve_strength_properties tests
# ---------------------------------------------------------------------

class TestManualOverride:
    def test_library_derived_values(self):
        result = sc.resolve_strength_properties("8.8")
        assert result["min_tensile_strength_mpa"] == 830.0
        assert result["sources"]["min_tensile_strength_mpa"] == "library_record"

    def test_manual_override_values_applied(self):
        result = sc.resolve_strength_properties(
            "8.8", manual_values={"min_yield_strength_mpa": 700},
        )
        assert result["min_yield_strength_mpa"] == 700
        assert result["sources"]["min_yield_strength_mpa"] == "manual_override"

    def test_manual_value_not_silently_overwritten(self):
        result = sc.resolve_strength_properties("8.8", manual_values={"proof_stress_mpa": 500})
        assert result["proof_stress_mpa"] == 500
        # library record's own proof_stress_mpa (660) must not leak through
        assert result["proof_stress_mpa"] != 660.0

    def test_field_level_source_tracked(self):
        result = sc.resolve_strength_properties("8.8", manual_values={"yield_ratio": 0.75})
        assert result["sources"]["yield_ratio"] == "manual_override"
        assert result["sources"]["min_tensile_strength_mpa"] == "library_record"

    def test_manual_override_flag_semantics_in_report_snapshot(self):
        snap_no_override = report_module.collect_strength_class_snapshot("8.8", "8")
        assert snap_no_override.manual_override is False
        snap_override = report_module.collect_strength_class_snapshot(
            "8.8", "8", manual_values={"min_yield_strength_mpa": 700},
        )
        assert snap_override.manual_override is True

    def test_unknown_designation_resolves_safely(self):
        result = sc.resolve_strength_properties("99.9")
        assert result["has_library_record"] is False
        assert all(v is None for k, v in result.items() if k in sc._RESOLVABLE_FIELDS)

    def test_legacy_calculation_source_value_supported(self):
        assert sc.StrengthValueSource.LEGACY_CALCULATION.value == "legacy_calculation"


# ---------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------

class TestApi:
    def test_list_bolt_endpoint(self, auth_headers):
        r = client.get("/api/engineering/bolt-strength-classes", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 12

    def test_list_bolt_endpoint_with_filter(self, auth_headers):
        r = client.get(
            "/api/engineering/bolt-strength-classes",
            params={"standard": "ISO 3506-1"}, headers=auth_headers,
        )
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_list_nut_endpoint(self, auth_headers):
        r = client.get("/api/engineering/nut-property-classes", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 8

    @pytest.mark.parametrize("designation", ["8.8", "04", "A2-70"])
    def test_detail_endpoints_known_designations(self, auth_headers, designation):
        if designation == "04":
            r = client.get(
                f"/api/engineering/nut-property-classes/{designation}", headers=auth_headers,
            )
        else:
            r = client.get(
                f"/api/engineering/bolt-strength-classes/{designation}", headers=auth_headers,
            )
        assert r.status_code == 200
        assert r.json()["designation"] == designation

    def test_unknown_designation_returns_404(self, auth_headers):
        r = client.get("/api/engineering/bolt-strength-classes/99.9", headers=auth_headers)
        assert r.status_code == 404
        assert "detail" in r.json()

    def test_unknown_nut_designation_returns_404(self, auth_headers):
        r = client.get("/api/engineering/nut-property-classes/99", headers=auth_headers)
        assert r.status_code == 404

    def test_invalid_query_returns_400(self, auth_headers):
        r = client.get(
            "/api/engineering/bolt-strength-classes",
            params={"diameter_mm": "not-a-number"}, headers=auth_headers,
        )
        assert r.status_code in (400, 422)  # FastAPI query-type coercion -> 422 before handler

    def test_compatibility_endpoint(self, auth_headers):
        r = client.post(
            "/api/engineering/bolt-nut-compatibility",
            json={"bolt_strength_class": "8.8", "nut_property_class": "8"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "compatible"
        assert "warning_codes" in body
        assert "checks" in body

    def test_compatibility_endpoint_missing_fields_defaults_to_unknown(self, auth_headers):
        r = client.post("/api/engineering/bolt-nut-compatibility", json={}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "unknown"

    def test_negative_diameter_controlled_response(self, auth_headers):
        r = client.post(
            "/api/engineering/bolt-nut-compatibility",
            json={"bolt_strength_class": "8.8", "nut_property_class": "8",
                  "nominal_diameter_mm": -5},
            headers=auth_headers,
        )
        assert r.status_code == 200  # negative diameter is out-of-range, not a crash
        assert "traceback" not in json.dumps(r.json()).lower()

    def test_no_traceback_leaks_on_any_endpoint(self, auth_headers):
        r = client.get(
            "/api/engineering/bolt-strength-classes/does-not-exist", headers=auth_headers,
        )
        text = r.text.lower()
        assert "traceback" not in text
        assert "file \"" not in text

    def test_response_schema_deterministic(self, auth_headers):
        r1 = client.get("/api/engineering/bolt-strength-classes/8.8", headers=auth_headers)
        r2 = client.get("/api/engineering/bolt-strength-classes/8.8", headers=auth_headers)
        assert r1.json() == r2.json()

    def test_requires_authentication(self):
        r = client.get("/api/engineering/bolt-strength-classes")
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------
# Report engine tests
# ---------------------------------------------------------------------

class TestReportEngine:
    def test_full_snapshot(self):
        snap = report_module.collect_strength_class_snapshot("8.8", "8", nominal_diameter_mm=12)
        d = snap.to_dict()
        assert d["bolt_strength_class"] == "8.8"
        assert d["compatibility_status"] == "compatible"
        assert d["mechanical_properties"]["min_tensile_strength_mpa"] == 830.0

    def test_missing_legacy_snapshot_renders_safely(self):
        rendered = report_module.render_strength_class_snapshot({"some_old_field": "x"})
        assert rendered["has_strength_class_data"] is False
        assert rendered["bolt_strength_class"] is None

    def test_none_snapshot_renders_without_exception(self):
        rendered = report_module.render_strength_class_snapshot(None)
        assert rendered["has_strength_class_data"] is False
        assert rendered["compatibility_warnings"] == []
        assert rendered["mechanical_properties"] == {}

    def test_manual_override_reflected_in_snapshot(self):
        snap = report_module.collect_strength_class_snapshot(
            "8.8", "8", manual_values={"min_yield_strength_mpa": 700},
        )
        assert snap.manual_override is True
        assert snap.mechanical_properties["min_yield_strength_mpa"] == 700

    def test_compatibility_warnings_in_snapshot(self):
        snap = report_module.collect_strength_class_snapshot("8.8", "8", nominal_diameter_mm=200)
        assert snap.compatibility_status == "conditionally_compatible"
        assert len(snap.compatibility_warnings) >= 1

    def test_snapshot_json_serializable(self):
        snap = report_module.collect_strength_class_snapshot("8.8", "8")
        json.dumps(snap.to_dict())

    def test_renderer_does_not_recompute_domain_logic(self):
        # Feed the renderer a snapshot claiming a status that would be
        # wrong for this bolt/nut pair -- if the renderer re-ran the
        # domain calculation it would "correct" this; it must not.
        fake_snapshot = {
            "bolt_strength_class": "10.9", "nut_property_class": "8",
            "compatibility_status": "compatible",  # actually not_compatible in reality
            "compatibility_warnings": [],
        }
        rendered = report_module.render_strength_class_snapshot(fake_snapshot)
        assert rendered["compatibility_status"] == "compatible"  # passed through verbatim

    def test_collector_and_renderer_are_separate_functions(self):
        assert (
            report_module.collect_strength_class_snapshot
            is not report_module.render_strength_class_snapshot
        )

    def test_empty_snapshot_all_fields_present(self):
        rendered = report_module.render_strength_class_snapshot({})
        for field_name in report_module.STRENGTH_SNAPSHOT_FIELDS:
            assert field_name in rendered


# ---------------------------------------------------------------------
# Baseline problem (re-verification, Faz 2.8.3 scope)
# ---------------------------------------------------------------------

class TestBaselineProblem:
    def test_faz_2_8_2_test_file_present_but_its_dependency_is_not(self):
        import pathlib
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        test_file = repo_root / "tests" / "test_faz_2_8_2_thread_geometry_verification.py"
        dependency = repo_root / "tools" / "audit_engineering_library.py"
        assert test_file.exists(), (
            "tests/test_faz_2_8_2_thread_geometry_verification.py is expected to "
            "exist in this base commit (19bbe5c) -- if this assertion starts "
            "failing, the pre-existing-baseline-problem description in the Faz "
            "2.8.3 delivery report is stale and must be updated."
        )
        assert not dependency.exists(), (
            "tools/audit_engineering_library.py now exists in this base commit -- "
            "if this assertion starts failing, tests/test_faz_2_8_2_thread_geometry_"
            "verification.py should collect successfully again and the "
            "pre-existing-baseline-problem note in the Faz 2.8.3 report is stale."
        )
