"""Faz 2.4.1A tests: ISO metric thread database field extension.

Covers what test_golden_records.py / test_data_integrity.py /
test_search.py / test_library_validation.py did not already cover
before this phase: M12 coarse, fine/extra-fine examples, the new
search filters, the new thread-specific validation checks (via
fixtures -- these are deliberately NOT run against the live 134-record
dataset, which already passes validate_thread_library() cleanly; see
test_library_validation.py / test_registry.py for that), and the
ISO_METRIC vs. non-metric record-count split.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.library import population, validator
from backend.library.models import THREAD_SCHEMA_VERSION, ThreadRecord
from backend.library.registry import get_library

# ---------------------------------------------------------------------
# Golden records (real ISO 724 values, independently checkable)
# ---------------------------------------------------------------------


def test_golden_m12_coarse_thread():
    rec = population.find_thread(designation="M12", pitch_type="coarse")[0]
    assert rec["pitch_mm"] == 1.75
    assert rec["pitch_diameter_mm"] == 10.8634
    assert rec["minor_diameter_mm"] == 10.1056
    # Widely-published ISO 898-1 tensile stress area for M12 is 84.3 mm^2.
    assert round(rec["stress_area_mm2"], 1) == 84.3
    assert rec["thread_series"] == "ISO_METRIC"
    assert rec["major_diameter_mm"] == 12
    assert rec["minor_diameter_internal_mm"] == 10.1056
    # d3 = 12 - 1.226869*1.75 = 9.853... (ISO 724 rounded-root minor
    # diameter, newly derived in this phase -- not present before).
    assert rec["minor_diameter_external_mm"] == pytest.approx(9.853, abs=0.001)


def test_at_least_three_fine_pitch_examples():
    fine = population.find_thread(pitch_type="fine", thread_series="ISO_METRIC")
    assert len(fine) >= 3
    designations = {r["designation"] for r in fine}
    assert {"M6x0.8", "M10x1.25", "M12x1.5"} <= designations
    for rec in fine:
        assert rec["pitch_type"] == "fine"
        assert rec["series"] == "Fine"


def test_extra_fine_pitch_example():
    rec = population.find_thread(designation="M10x1", pitch_type="extra_fine")[0]
    assert rec["series"] == "Extra Fine"
    assert rec["thread_series"] == "ISO_METRIC"
    assert rec["pitch_mm"] == 1.0


# ---------------------------------------------------------------------
# Record counts: 106 ISO metric + 28 non-metric, and registry parity
# ---------------------------------------------------------------------


def test_106_iso_metric_and_28_non_metric_counts():
    assert population.count_iso_metric_thread_records() == 106
    assert population.count_non_iso_metric_thread_records() == 28


def test_total_thread_record_count_is_134():
    records = population.load_population_records("thread library")
    assert len(records) == 134
    assert (
        population.count_iso_metric_thread_records()
        + population.count_non_iso_metric_thread_records()
        == 134
    )


def test_registry_record_count_matches_loaded_total_after_populate():
    lib = get_library("thread library")
    assert lib.records == []
    try:
        population.populate_library(lib)
        records = population.load_population_records("thread library")
        assert lib.metadata.record_count == len(records) == 134
    finally:
        lib.replace_records([])
    assert lib.records == []
    assert lib.metadata.record_count == 0


# ---------------------------------------------------------------------
# Search: new filters, combined, and backward-compat alias
# ---------------------------------------------------------------------


def test_find_thread_by_nominal_diameter_and_pitch_combined():
    results = population.find_thread(nominal_diameter_mm=10, pitch_mm=1.5)
    assert len(results) == 1
    assert results[0]["designation"] == "M10"
    assert results[0]["series"] == "Coarse"


def test_find_thread_by_thread_series_scope():
    iso_metric = population.find_thread(thread_series="ISO_METRIC")
    non_metric = population.find_thread(thread_series="UNC")
    assert len(iso_metric) == 106
    assert len(non_metric) == 5
    assert all(r["thread_series"] == "ISO_METRIC" for r in iso_metric)


def test_find_thread_series_parameter_still_works_backward_compat():
    # Pre-existing 'series' filter, unchanged/not deprecated.
    by_series = population.find_thread(series="Coarse")
    by_pitch_type = population.find_thread(pitch_type="coarse", thread_series="ISO_METRIC")
    assert len(by_series) == 42
    assert len(by_pitch_type) == 42
    assert {r["id"] for r in by_series} == {r["id"] for r in by_pitch_type}


def test_find_thread_no_match_returns_empty_list():
    assert population.find_thread(designation="M999") == []


# ---------------------------------------------------------------------
# Validation: negative fixtures for every Faz 2.4.1A thread check
# ---------------------------------------------------------------------


def _base_iso_metric_record(**overrides):
    record = {
        "id": "THR-TEST-1",
        "designation": "M8",
        "nominal_diameter_mm": 8,
        "pitch_mm": 1.25,
        "series": "Coarse",
        "pitch_type": "coarse",
        "thread_series": "ISO_METRIC",
        "schema_version": THREAD_SCHEMA_VERSION,
        "pitch_diameter_mm": 7.1881,
        "minor_diameter_mm": 6.6468,
        "minor_diameter_internal_mm": 6.6468,
        "minor_diameter_external_mm": 6.4664,
        "stress_area_mm2": 36.609,
        "source_standard": "ISO 724 / ISO 261",
    }
    record.update(overrides)
    return record


def test_duplicate_designation_pitch_negative_fixture():
    records = [
        _base_iso_metric_record(id="THR-A"),
        _base_iso_metric_record(id="THR-B"),  # same designation+pitch
    ]
    issues = validator.find_duplicate_thread_designation_pitch(records)
    assert len(issues) == 1
    assert issues[0].code == "duplicate_thread_designation_pitch"


def test_zero_and_negative_dimension_negative_fixture():
    records = [
        _base_iso_metric_record(id="THR-ZERO", pitch_mm=0),
        _base_iso_metric_record(id="THR-NEG", nominal_diameter_mm=-8),
    ]
    issues = validator.find_non_positive_thread_dimensions(records)
    codes = [i.code for i in issues]
    assert codes.count("non_positive_dimension") == 2


def test_designation_nominal_diameter_mismatch_negative_fixture():
    records = [_base_iso_metric_record(designation="M8", nominal_diameter_mm=10)]
    issues = validator.find_thread_designation_diameter_mismatches(records)
    assert len(issues) == 1
    assert issues[0].code == "designation_diameter_mismatch"


def test_pitch_type_series_mismatch_negative_fixture():
    records = [_base_iso_metric_record(pitch_type="fine")]  # series says Coarse
    issues = validator.find_thread_pitch_type_classification_mismatches(records)
    assert len(issues) == 1
    assert issues[0].code == "pitch_type_series_mismatch"


def test_unknown_field_negative_fixture():
    records = [_base_iso_metric_record(bogus_field="nope")]
    issues = validator.find_thread_unknown_fields(records)
    assert len(issues) == 1
    assert issues[0].code == "unknown_field"
    assert issues[0].field == "bogus_field"
    # Same rejection at the Pydantic layer (extra="forbid" on ThreadRecord).
    with pytest.raises(ValidationError):
        ThreadRecord(**records[0])


def test_schema_version_mismatch_negative_fixture():
    records = [_base_iso_metric_record(schema_version="0.9")]
    issues = validator.find_thread_schema_version_issues(records)
    assert len(issues) == 1
    assert issues[0].code == "schema_version_mismatch"


def test_unknown_thread_series_negative_fixture():
    records = [_base_iso_metric_record(thread_series="METRIC_ISO")]  # typo
    issues = validator.find_thread_series_scope_issues(records)
    assert len(issues) == 1
    assert issues[0].code == "unknown_thread_series"


def test_minor_diameter_tolerance_negative_fixture():
    records = [_base_iso_metric_record(minor_diameter_external_mm=999.0)]
    issues = validator.find_thread_minor_diameter_tolerance_violations(records)
    assert len(issues) == 1
    assert issues[0].code == "minor_diameter_tolerance"


def test_stress_area_tolerance_negative_fixture():
    records = [_base_iso_metric_record(stress_area_mm2=999.0)]
    issues = validator.find_thread_stress_area_tolerance_violations(records)
    assert len(issues) == 1
    assert issues[0].code == "stress_area_tolerance"


def test_non_iso_metric_records_skipped_by_metric_geometry_checks():
    # A UNC-series record with an intentionally "wrong" metric-style
    # designation/diameter pairing must NOT be flagged by the
    # ISO_METRIC-only checks -- it is out of that scope by design.
    records = [
        _base_iso_metric_record(
            id="THR-UNC-TEST",
            designation="1/4-20 UNC",
            thread_series="UNC",
            pitch_type=None,
            nominal_diameter_mm=6.35,
            pitch_mm=1.27,
            minor_diameter_external_mm=None,
            minor_diameter_internal_mm=None,
        )
    ]
    assert validator.find_thread_designation_diameter_mismatches(records) == []
    assert validator.find_thread_pitch_type_classification_mismatches(records) == []
    assert validator.find_thread_minor_diameter_tolerance_violations(records) == []
    assert validator.find_thread_stress_area_tolerance_violations(records) == []


def test_validate_thread_library_clean_over_live_dataset():
    records = population.load_population_records("thread library")
    report = validator.validate_thread_library(records)
    assert report.issues == []


def test_validate_thread_library_records_population_wrapper():
    assert population.validate_thread_library_records() == []
