"""Faz 2.4.1C tests: joint hardware library infrastructure (shell).

Covers the ``JointHardwareRecord`` schema, its ``LIBRARY_RECORD_MODELS``
registration, the empty data file, the population/search/validator
wiring and the facade. No real engineering record exists yet for this
domain (see ``backend/library/joint_hardware_library.py``), so every
non-trivial check here runs against hand-built fixtures rather than
the (empty) live data file -- this suite tests that the
*infrastructure* behaves correctly, not any dimensional data.
"""

from __future__ import annotations

from backend.library import population, validator
from backend.library.facade import library_registry
from backend.library.joint_hardware_library import (
    JOINT_HARDWARE_LIBRARY,
    KNOWN_HARDWARE_TYPES,
)
from backend.library.models import (
    JointHardwareRecord,
    LIBRARY_RECORD_MODELS,
    find_schema_violations,
    get_record_model,
)
from backend.library.registry import get_library


def setup_module(_module):
    population.clear_cache()


# ---------------------------------------------------------------------
# 1: JointHardwareRecord parse test
# ---------------------------------------------------------------------


def test_joint_hardware_record_parses_minimal_dict():
    record = JointHardwareRecord.model_validate({"id": "JH-1", "designation": "Test"})
    assert record.id == "JH-1"
    assert record.hardware_type == ""
    assert record.compatible_bolt_sizes == []
    assert record.inner_diameter_mm is None


def test_joint_hardware_record_parses_full_dict():
    raw = {
        "id": "JH-DOWEL-M6",
        "source_standard": "ISO 8734",
        "designation": "Dowel pin M6",
        "hardware_type": "Dowel pin",
        "standard_organization": "ISO",
        "inner_diameter_mm": None,
        "outer_diameter_mm": 6.0,
        "length_mm": 20.0,
        "material": "Steel",
        "compatible_bolt_sizes": ["M6"],
        "operating_temperature_min_c": -20.0,
        "operating_temperature_max_c": 80.0,
    }
    record = JointHardwareRecord.model_validate(raw)
    assert record.hardware_type == "Dowel pin"
    assert record.outer_diameter_mm == 6.0
    assert record.compatible_bolt_sizes == ["M6"]


def test_known_hardware_types_advisory_vocabulary_is_nonempty():
    assert "Dowel pin" in KNOWN_HARDWARE_TYPES
    assert "Bushing" in KNOWN_HARDWARE_TYPES


# ---------------------------------------------------------------------
# 2: schema map test
# ---------------------------------------------------------------------


def test_joint_hardware_library_registered_in_schema_map():
    assert LIBRARY_RECORD_MODELS["joint hardware library"] is JointHardwareRecord
    assert get_record_model("joint hardware library") is JointHardwareRecord


def test_schema_map_still_has_eleven_domains_total():
    # 9 original domain shells + OEM (adapter-only) + joint hardware
    # (Faz 2.4.1C, shell only) = 11.
    assert len(LIBRARY_RECORD_MODELS) == 11


# ---------------------------------------------------------------------
# 3: empty JSON loading test
# ---------------------------------------------------------------------


def test_joint_hardware_data_file_loads_as_empty_list():
    records = population.load_population_records("joint hardware library")
    assert records == []


def test_joint_hardware_empty_records_satisfy_schema():
    assert find_schema_violations("joint hardware library", []) == []


def test_joint_hardware_library_shell_has_zero_records():
    lib = get_library("Joint Hardware Library")
    assert lib is JOINT_HARDWARE_LIBRARY
    assert lib.records == []
    assert lib.metadata.record_count == 0
    assert lib.metadata.status == "draft"


# ---------------------------------------------------------------------
# 4: search on empty library
# ---------------------------------------------------------------------


def test_find_joint_hardware_by_type_on_empty_library_returns_empty_list():
    assert population.find_joint_hardware_by_type("Dowel pin") == []


def test_find_joint_hardware_by_standard_on_empty_library_returns_empty_list():
    assert population.find_joint_hardware_by_standard("ISO 8734") == []


def test_find_joint_hardware_functions_do_not_raise_on_empty_library():
    # Both functions must degrade gracefully (empty list), never KeyError/None.
    assert isinstance(population.find_joint_hardware_by_type("Bushing"), list)
    assert isinstance(population.find_joint_hardware_by_standard("DIN 6325"), list)


# ---------------------------------------------------------------------
# 5: duplicate rejection (fixture)
# ---------------------------------------------------------------------


def test_duplicate_joint_hardware_id_detected_on_fixture():
    records = [
        {"id": "JH-X", "designation": "Spacer A"},
        {"id": "JH-X", "designation": "Spacer B"},
    ]
    issues = validator.find_duplicate_ids(records)
    assert len(issues) == 1
    assert issues[0].code == "duplicate_id"


def test_no_duplicates_on_empty_live_data():
    records = population.load_population_records("joint hardware library")
    assert validator.find_duplicate_ids(records) == []


# ---------------------------------------------------------------------
# 6: invalid positive dimension check (fixture)
# ---------------------------------------------------------------------


def test_non_positive_joint_hardware_dimension_detected():
    records = [
        {"id": "JH-1", "inner_diameter_mm": 0, "outer_diameter_mm": 10, "length_mm": 5},
        {"id": "JH-2", "inner_diameter_mm": 3, "outer_diameter_mm": -5, "length_mm": 5},
        {"id": "JH-3", "inner_diameter_mm": 3, "outer_diameter_mm": 5, "length_mm": -1},
    ]
    issues = validator.find_non_positive_joint_hardware_dimensions(records)
    assert len(issues) == 3
    assert all(i.code == "non_positive_joint_hardware_dimension" for i in issues)


def test_positive_dimensions_pass():
    records = [
        {"id": "JH-1", "inner_diameter_mm": 3, "outer_diameter_mm": 6, "length_mm": 10}
    ]
    assert validator.find_non_positive_joint_hardware_dimensions(records) == []


def test_missing_designation_or_standard_detected():
    records = [{"id": "JH-1", "designation": "", "source_standard": ""}]
    issues = validator.find_missing_hardware_identity(records)
    codes = {i.code for i in issues}
    assert codes == {"missing_designation", "missing_source_standard"}


# ---------------------------------------------------------------------
# 7: temperature min/max check (fixture)
# ---------------------------------------------------------------------


def test_temperature_range_violation_detected_for_joint_hardware_fixture():
    records = [
        {
            "id": "JH-1",
            "operating_temperature_min_c": 100.0,
            "operating_temperature_max_c": 20.0,
        },
    ]
    issues = validator.find_temperature_range_violations(records)
    assert len(issues) == 1
    assert issues[0].code == "temperature_range_violation"


def test_temperature_range_ok_passes():
    records = [
        {
            "id": "JH-1",
            "operating_temperature_min_c": -20.0,
            "operating_temperature_max_c": 100.0,
        },
    ]
    assert validator.find_temperature_range_violations(records) == []


# ---------------------------------------------------------------------
# aggregate validator + population entry point
# ---------------------------------------------------------------------


def test_validate_joint_hardware_library_aggregate_on_fixture():
    records = [
        {"id": "JH-1", "id2": "dup-check-placeholder"},
        {
            "id": "JH-1",  # duplicate id
            "designation": "",  # missing designation
            "source_standard": "",  # missing source
            "inner_diameter_mm": -1,  # non-positive
            "operating_temperature_min_c": 50.0,
            "operating_temperature_max_c": 10.0,  # min > max
        },
    ]
    report = validator.validate_joint_hardware_library(records)
    codes = {i.code for i in report.issues}
    assert "duplicate_id" in codes
    assert "missing_designation" in codes
    assert "missing_source_standard" in codes
    assert "non_positive_joint_hardware_dimension" in codes
    assert "temperature_range_violation" in codes
    assert "missing_source" in codes


def test_validate_joint_hardware_library_clean_on_empty_live_data():
    assert population.validate_joint_hardware_library_records() == []


# ---------------------------------------------------------------------
# 8: facade access
# ---------------------------------------------------------------------


def test_facade_exposes_joint_hardware_search_methods():
    assert library_registry.find_joint_hardware_by_type("Dowel pin") == []
    assert library_registry.find_joint_hardware_by_standard("ISO 8734") == []


def test_facade_get_returns_joint_hardware_library():
    lib = library_registry.get("Joint Hardware Library")
    assert lib is JOINT_HARDWARE_LIBRARY


# ---------------------------------------------------------------------
# 9: backward compatibility
# ---------------------------------------------------------------------


def test_other_nine_domains_still_populate_normally():
    for key in ("bolt library", "nut library", "washer library", "thread library"):
        assert len(population.load_population_records(key)) > 0


def test_bolt_schema_unaffected_by_joint_hardware_addition():
    records = population.load_population_records("bolt library")
    assert find_schema_violations("bolt library", records) == []


def test_list_libraries_includes_joint_hardware_without_breaking_existing_entries():
    from backend.library.registry import list_libraries

    names = {lib.metadata.name for lib in list_libraries()}
    assert "Joint Hardware Library" in names
    assert "Bolt Library" in names
    assert "Washer Library" in names
