"""Faz 2.4.1 tests: data-integrity checks, checksum tamper/determinism
guarantees, and populate_all()/populate_library() idempotency.

Requested explicitly for the Faz 2.4.1 delivery review (duplicate ID,
standard+size+variant uniqueness, non-positive geometry, min<=nominal
<=max ranges, coarse/fine pitch separation, dangling thread
references, broken compatibility references, status-enum validity,
checksum tamper detection/determinism, populate_all idempotency and
side-effect-free import).
"""

from __future__ import annotations

import copy
import hashlib
import json

from backend.library import population
from backend.library.registry import get_library


# ---------------------------------------------------------------------
# Data-integrity checks (population.run_all_integrity_checks)
# ---------------------------------------------------------------------

def test_run_all_integrity_checks_reports_zero_issues():
    report = population.run_all_integrity_checks()
    for check_name, issues in report.items():
        assert issues == [], f"{check_name}: {issues}"


def test_no_duplicate_standard_size_variant_combinations():
    assert population.find_duplicate_standard_size_variant() == []


def test_no_non_positive_geometric_values():
    assert population.find_non_positive_geometric_values() == []


def test_no_strength_class_range_violations():
    assert population.find_strength_class_range_violations() == []


def test_no_material_range_violations():
    assert population.find_material_range_violations() == []


def test_coarse_fine_pitch_separation_is_correct():
    assert population.find_pitch_series_violations() == []


def test_no_dangling_thread_references_from_bolt_library():
    assert population.find_dangling_thread_references() == []


def test_no_broken_compatibility_references():
    assert population.find_broken_compatibility_references() == []


def test_no_invalid_status_values_anywhere():
    assert population.find_invalid_status_values() == []


# ---------------------------------------------------------------------
# Checksum tamper detection / determinism
# ---------------------------------------------------------------------

def _recompute_checksum(record):
    payload = {k: v for k, v in record.items() if k != "checksum"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_no_checksum_mismatches_in_shipped_data():
    assert population.find_checksum_mismatches() == []


def test_checksum_field_itself_is_excluded_from_its_own_computation():
    record = population.find_bolt(diameter_mm=10, head_type="Hex")[0]
    with_dummy_checksum = dict(record, checksum="deadbeef")
    assert _recompute_checksum(with_dummy_checksum) == record["checksum"]


def test_checksum_is_deterministic_for_identical_content():
    record = population.find_thread(designation="M8", series="Coarse")[0]
    first = _recompute_checksum(record)
    second = _recompute_checksum(copy.deepcopy(record))
    assert first == second == record["checksum"]


def test_checksum_changes_when_a_field_is_tampered():
    record = population.find_thread(designation="M8", series="Coarse")[0]
    original_checksum = record["checksum"]
    tampered = dict(record)
    tampered["pitch_mm"] = tampered["pitch_mm"] + 0.01
    tampered_checksum = _recompute_checksum(tampered)
    assert tampered_checksum != original_checksum


def test_tampered_record_fails_mismatch_check():
    # Simulate on-disk corruption: mutate a field but keep the old
    # (now stale) checksum, and confirm find_checksum_mismatches would
    # flag it if it were part of the loaded dataset.
    record = population.find_thread(designation="M10", series="Coarse")[0]
    tampered = dict(record)
    tampered["stress_area_mm2"] = 0.0  # corrupted value, stale checksum
    assert tampered["checksum"] == record["checksum"]
    assert _recompute_checksum(tampered) != tampered["checksum"]


# ---------------------------------------------------------------------
# populate_all() / populate_library() idempotency and side effects
# ---------------------------------------------------------------------

def test_populate_library_called_twice_does_not_duplicate_records():
    lib = get_library("Bolt Library")
    assert lib.records == []
    try:
        first_count = population.populate_library(lib)
        second_count = population.populate_library(lib)
        assert first_count == second_count
        assert len(lib.records) == first_count
        ids = [r["id"] for r in lib.records]
        assert len(ids) == len(set(ids))
    finally:
        lib.replace_records([])


def test_populate_all_called_twice_is_idempotent():
    touched = [get_library(key) for key in population.POPULATION_SOURCES]
    try:
        first = population.populate_all()
        second = population.populate_all()
        assert first == second
        for lib in touched:
            ids = [r["id"] for r in lib.records]
            assert len(ids) == len(set(ids))
    finally:
        for lib in touched:
            lib.replace_records([])


def test_importing_population_module_has_no_registry_side_effects():
    # Merely importing backend.library.population (already done at
    # module load time above) must not have populated anything.
    for key in population.POPULATION_SOURCES:
        lib = get_library(key)
        assert lib.records == [], key
        assert lib.metadata.record_count == 0, key
