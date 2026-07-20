"""Faz 2.4.1B tests: bolt/nut engineering database.

Covers what pre-existing test files did not already cover: the
Faz 2.4.1B structured bolt/nut fields, the new bolt/nut validators,
the extended search API (search_bolts/search_nuts), the bolt<->nut
compatibility service, and the data generator's idempotency/legacy-
preservation guarantees. Generator tests run entirely against
temporary copies of the data files -- the real
``backend/library/data/*.json`` files are never touched by this
suite.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from backend.library import population, validator
from backend.library.compatibility_engine import (
    CompatibilityResult,
    check_bolt_nut_compatibility,
)
from backend.library.facade import library_registry
from backend.library.models import find_schema_violations
from backend.library.registry import get_library

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "backend" / "library" / "data"
GENERATOR_PATH = REPO_ROOT / "tools" / "generate_faz2_4_1b_bolt_nut_records.py"


def _load_generator_module():
    """Import the generator script as a standalone module (it lives
    under ``tools/``, outside the ``backend`` package)."""
    spec = importlib.util.spec_from_file_location(
        "faz2_4_1b_generator", GENERATOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record_checksum(record: dict) -> str:
    payload = {k: v for k, v in record.items() if k != "checksum"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------
# 1-3: data loading, schema, record counts
# ---------------------------------------------------------------------


def test_bolt_data_loading():
    records = population.load_population_records("bolt library")
    assert len(records) == 176
    assert all("id" in r and "designation" in r for r in records)


def test_nut_data_loading():
    records = population.load_population_records("nut library")
    assert len(records) == 211
    assert all("id" in r and "designation" in r for r in records)


def test_bolt_records_satisfy_pydantic_schema():
    records = population.load_population_records("bolt library")
    assert find_schema_violations("bolt library", records) == []


def test_nut_records_satisfy_pydantic_schema():
    records = population.load_population_records("nut library")
    assert find_schema_violations("nut library", records) == []


# ---------------------------------------------------------------------
# 4-5: duplicate id / duplicate designation+standard+dimension
# ---------------------------------------------------------------------


def test_no_duplicate_bolt_ids_in_live_data():
    records = population.load_population_records("bolt library")
    assert validator.find_duplicate_ids(records) == []


def test_duplicate_id_detected_on_fixture():
    records = [
        {"id": "BOLT-X", "designation": "M8"},
        {"id": "BOLT-X", "designation": "M10"},
    ]
    issues = validator.find_duplicate_ids(records)
    assert len(issues) == 1
    assert issues[0].code == "duplicate_id"


def test_no_duplicate_designation_standard_dimension_in_live_data():
    bolts = population.load_population_records("bolt library")
    nuts = population.load_population_records("nut library")
    assert validator.find_duplicate_designation_standard_dimension(bolts) == []
    assert validator.find_duplicate_designation_standard_dimension(nuts) == []


def test_duplicate_designation_standard_dimension_detected_on_fixture():
    records = [
        {"id": "A", "designation": "M8", "source_standard": "ISO 4017", "diameter_mm": 8},
        {"id": "B", "designation": "M8", "source_standard": "ISO 4017", "diameter_mm": 8},
    ]
    issues = validator.find_duplicate_designation_standard_dimension(records)
    assert len(issues) == 1
    assert issues[0].code == "duplicate_designation_standard_dimension"


# ---------------------------------------------------------------------
# 6-7: source traceability, checksum verification
# ---------------------------------------------------------------------


def test_no_missing_source_in_live_data():
    bolts = population.load_population_records("bolt library")
    nuts = population.load_population_records("nut library")
    assert validator.find_missing_source(bolts) == []
    assert validator.find_missing_source(nuts) == []


def test_missing_source_detected_on_fixture():
    records = [{"id": "X", "source": "", "source_standard": ""}]
    issues = validator.find_missing_source(records)
    assert len(issues) == 1
    assert issues[0].code == "missing_source"


def test_every_bolt_record_checksum_matches_content():
    records = population.load_population_records("bolt library")
    mismatches = [r["id"] for r in records if r.get("checksum") != _record_checksum(r)]
    assert mismatches == []


def test_every_nut_record_checksum_matches_content():
    records = population.load_population_records("nut library")
    mismatches = [r["id"] for r in records if r.get("checksum") != _record_checksum(r)]
    assert mismatches == []


def test_checksum_is_deterministic_for_identical_content():
    record = {"id": "X", "designation": "M8", "value": 3.14}
    assert _record_checksum(record) == _record_checksum(copy.deepcopy(record))


# ---------------------------------------------------------------------
# 8: generator idempotency (runs against temp copies only)
# ---------------------------------------------------------------------


@pytest.fixture()
def isolated_generator(tmp_path):
    """A generator module instance pointed at temp copies of the
    bolt/nut/thread data files -- never touches the real repo data."""
    tmp_data = tmp_path / "data"
    tmp_data.mkdir()
    for name in ("bolt_library.json", "nut_library.json", "thread_library.json"):
        shutil.copy(DATA_DIR / name, tmp_data / name)

    module = _load_generator_module()
    module.BOLT_PATH = str(tmp_data / "bolt_library.json")
    module.NUT_PATH = str(tmp_data / "nut_library.json")
    module.THREAD_PATH = str(tmp_data / "thread_library.json")
    return module, tmp_data


def test_generator_does_not_touch_real_repo_files(isolated_generator):
    real_bolt_before = (DATA_DIR / "bolt_library.json").read_bytes()
    real_nut_before = (DATA_DIR / "nut_library.json").read_bytes()

    module, _ = isolated_generator
    module.main()

    assert (DATA_DIR / "bolt_library.json").read_bytes() == real_bolt_before
    assert (DATA_DIR / "nut_library.json").read_bytes() == real_nut_before


def test_generator_is_byte_for_byte_idempotent(isolated_generator):
    module, tmp_data = isolated_generator
    module.main()
    first_bolt = (tmp_data / "bolt_library.json").read_bytes()
    first_nut = (tmp_data / "nut_library.json").read_bytes()

    module.main()
    second_bolt = (tmp_data / "bolt_library.json").read_bytes()
    second_nut = (tmp_data / "nut_library.json").read_bytes()

    assert first_bolt == second_bolt
    assert first_nut == second_nut


def test_generator_does_not_duplicate_records_across_runs(isolated_generator):
    module, tmp_data = isolated_generator
    module.main()
    module.main()
    bolts = json.loads((tmp_data / "bolt_library.json").read_text())["records"]
    nuts = json.loads((tmp_data / "nut_library.json").read_text())["records"]
    bolt_ids = [r["id"] for r in bolts]
    nut_ids = [r["id"] for r in nuts]
    assert len(bolt_ids) == len(set(bolt_ids))
    assert len(nut_ids) == len(set(nut_ids))
    assert len(bolts) == 176
    assert len(nuts) == 211


def test_generator_preserves_faz_2_4_1a_legacy_records(isolated_generator):
    module, tmp_data = isolated_generator
    before_bolts = json.loads((tmp_data / "bolt_library.json").read_text())["records"]
    before_ids = {r["id"] for r in before_bolts if r.get("version") == "2.4.1"}
    assert before_ids  # sanity: legacy records exist before generation

    module.main()
    after_bolts = json.loads((tmp_data / "bolt_library.json").read_text())["records"]
    after_ids = {r["id"] for r in after_bolts}
    assert before_ids <= after_ids


def test_generator_preserves_manually_added_foreign_records(isolated_generator):
    module, tmp_data = isolated_generator
    bolt_payload = json.loads((tmp_data / "bolt_library.json").read_text())
    manual_record = {
        "id": "BOLT-MANUAL-TEST", "version": "manual", "designation": "M8",
        "source_standard": "Custom", "source": "Custom", "diameter_mm": 8,
        "property_class": "8.8",
    }
    bolt_payload["records"].append(manual_record)
    (tmp_data / "bolt_library.json").write_text(json.dumps(bolt_payload))

    module.main()
    after_bolts = json.loads((tmp_data / "bolt_library.json").read_text())["records"]
    after_ids = {r["id"] for r in after_bolts}
    assert "BOLT-MANUAL-TEST" in after_ids


# ---------------------------------------------------------------------
# 9-11: nominal diameter / pitch / pitch-designation validation
# ---------------------------------------------------------------------


def test_non_positive_nominal_diameter_detected_on_fixture():
    records = [{"id": "X", "nominal_diameter_mm": 0}, {"id": "Y", "nominal_diameter_mm": -5}]
    issues = validator.find_non_positive_nominal_diameter(records)
    assert len(issues) == 2


def test_non_positive_nominal_diameter_skips_records_without_the_field():
    assert validator.find_non_positive_nominal_diameter([{"id": "X"}]) == []


def test_non_positive_pitch_detected_on_fixture():
    records = [{"id": "X", "pitch_mm": 0}, {"id": "Y", "pitch_mm": -1.5}]
    issues = validator.find_non_positive_pitch(records)
    assert len(issues) == 2


def test_pitch_designation_mismatch_detected_on_fixture():
    records = [{"id": "X", "thread": "M8", "pitch_mm": 999.0}]
    issues = validator.find_pitch_designation_mismatches(records)
    assert len(issues) == 1
    assert issues[0].code == "pitch_designation_mismatch"


def test_pitch_designation_explicit_fine_pitch_matches():
    records = [{"id": "X", "thread": "M10x1.25", "pitch_mm": 1.25}]
    assert validator.find_pitch_designation_mismatches(records) == []


def test_no_pitch_designation_mismatches_in_live_data():
    bolts = population.load_population_records("bolt library")
    nuts = population.load_population_records("nut library")
    assert validator.find_pitch_designation_mismatches(bolts) == []
    assert validator.find_pitch_designation_mismatches(nuts) == []


# ---------------------------------------------------------------------
# 12: strength/property class format
# ---------------------------------------------------------------------


def test_invalid_bolt_strength_class_format_detected():
    records = [{"id": "X", "property_class": "eight-eight"}]
    issues = validator.find_invalid_bolt_strength_class_format(records)
    assert len(issues) == 1


def test_valid_bolt_strength_classes_pass():
    records = [{"id": "X", "property_class": "10.9"}]
    assert validator.find_invalid_bolt_strength_class_format(records) == []


def test_invalid_nut_strength_class_format_detected():
    records = [{"id": "X", "property_class": "99"}]
    issues = validator.find_invalid_nut_strength_class_format(records)
    assert len(issues) == 1


# ---------------------------------------------------------------------
# 13-16: strength ordering, hardness, temperature, geometry consistency
# ---------------------------------------------------------------------


def test_strength_ordering_violation_detected():
    records = [{
        "id": "X", "proof_strength_mpa": 900.0,
        "yield_strength_mpa": 640.0, "minimum_tensile_strength_mpa": 800.0,
    }]
    issues = validator.find_strength_ordering_violations(records)
    assert len(issues) >= 1
    assert all(i.code == "strength_ordering_violation" for i in issues)


def test_strength_ordering_holds_for_live_bolt_data():
    records = population.load_population_records("bolt library")
    assert validator.find_strength_ordering_violations(records) == []


def test_hardness_range_violation_detected():
    records = [{"id": "X", "hardness_range": "335-255 HV"}]
    issues = validator.find_hardness_range_violations(records)
    assert len(issues) == 1
    assert issues[0].code == "hardness_range_violation"


def test_temperature_range_violation_detected():
    records = [{
        "id": "X", "operating_temperature_min_c": 150.0,
        "operating_temperature_max_c": -50.0,
    }]
    issues = validator.find_temperature_range_violations(records)
    assert len(issues) == 1


def test_bolt_head_geometry_inconsistency_detected():
    records = [{
        "id": "X", "head_type": "Hex",
        "head_across_flats_mm": 20.0, "head_across_corners_mm": 15.0,
    }]
    issues = validator.find_bolt_head_geometry_inconsistencies(records)
    assert len(issues) == 1


def test_bolt_head_geometry_check_skips_socket_heads():
    # Socket head cap screws legitimately reuse these field names for
    # a different geometric concept -- see validator docstring.
    records = [{
        "id": "X", "head_type": "Socket",
        "head_across_flats_mm": 13.0, "head_across_corners_mm": 12.0,
    }]
    assert validator.find_bolt_head_geometry_inconsistencies(records) == []


def test_nut_width_geometry_inconsistency_detected():
    records = [{"id": "X", "width_across_flats_mm": 20.0, "width_across_corners_mm": 15.0}]
    issues = validator.find_nut_width_geometry_inconsistencies(records)
    assert len(issues) == 1


def test_geometry_consistency_holds_for_live_data():
    bolts = population.load_population_records("bolt library")
    nuts = population.load_population_records("nut library")
    assert validator.find_bolt_head_geometry_inconsistencies(bolts) == []
    assert validator.find_nut_width_geometry_inconsistencies(nuts) == []


# ---------------------------------------------------------------------
# 17-18: lock nut / prevailing torque nut requirements
# ---------------------------------------------------------------------


def test_lock_nut_missing_locking_principle_detected():
    records = [{"id": "X", "nut_family": "All-metal lock nut", "locking_principle": ""}]
    issues = validator.find_lock_nut_missing_locking_principle(records)
    assert len(issues) == 1


def test_lock_nut_with_locking_principle_passes():
    records = [{
        "id": "X", "nut_family": "Nylon insert lock nut",
        "locking_principle": "Nylon insert prevailing torque",
    }]
    assert validator.find_lock_nut_missing_locking_principle(records) == []


def test_prevailing_torque_nut_missing_reuse_info_detected():
    records = [{"id": "X", "prevailing_torque_category": "Nylon insert", "reusable": None}]
    issues = validator.find_prevailing_torque_nut_missing_reuse_info(records)
    assert len(issues) == 1


def test_lock_nut_and_prevailing_torque_checks_clean_on_live_data():
    nuts = population.load_population_records("nut library")
    assert validator.find_lock_nut_missing_locking_principle(nuts) == []
    assert validator.find_prevailing_torque_nut_missing_reuse_info(nuts) == []


# ---------------------------------------------------------------------
# 19-22: search API (bolt, nut, verified-only, designation text)
# ---------------------------------------------------------------------


def test_search_bolts_by_standard_and_family():
    results = population.search_bolts(standard="DIN 912", family="Socket head cap screw")
    assert results
    assert all(r["source_standard"] == "DIN 912" for r in results)
    assert all(r["bolt_family"] == "Socket head cap screw" for r in results)


def test_search_bolts_by_diameter_pitch_and_strength_class():
    results = population.search_bolts(nominal_diameter=12, strength_class="10.9")
    assert results
    assert all(r["nominal_diameter_mm"] == 12 for r in results)
    assert all(r["property_class"] == "10.9" for r in results)


def test_search_bolts_by_coating_and_coarse_fine():
    results = population.search_bolts(coating="zinc flake", coarse_or_fine="coarse")
    assert results
    for r in results:
        assert any("zinc flake" in c.lower() for c in r["coating_compatibility"])
        assert r["coarse_or_fine"] == "coarse"


def test_search_nuts_by_standard_and_family():
    results = population.search_nuts(standard="ISO 7042", family="All-metal lock nut")
    assert results
    assert all(r["source_standard"] == "ISO 7042" for r in results)


def test_search_nuts_by_locking_principle():
    results = population.search_nuts(locking_principle="nylon insert")
    assert results
    assert all("nylon insert" in r["locking_principle"].lower() for r in results)


def test_search_verified_only_filters_bolts():
    all_results = population.search_bolts(standard="ISO 4017")
    verified = population.search_bolts(standard="ISO 4017", verified_only=True)
    assert len(verified) < len(all_results)
    assert all(r["verification_status"] == "verified" for r in verified)


def test_search_designation_text_search():
    results = population.search_bolts(designation="M10")
    assert results
    assert all("m10" in r["designation"].lower() for r in results)


def test_search_bolts_no_match_returns_empty():
    assert population.search_bolts(standard="NONEXISTENT-STANDARD") == []


# ---------------------------------------------------------------------
# 23-24: registry / facade integration
# ---------------------------------------------------------------------


def test_registry_populate_bolt_and_nut_libraries():
    bolt_lib = get_library("bolt library")
    nut_lib = get_library("nut library")
    assert bolt_lib.records == []
    assert nut_lib.records == []
    try:
        n_bolts = population.populate_library(bolt_lib)
        n_nuts = population.populate_library(nut_lib)
        assert n_bolts == bolt_lib.metadata.record_count == 176
        assert n_nuts == nut_lib.metadata.record_count == 211
    finally:
        bolt_lib.replace_records([])
        nut_lib.replace_records([])


def test_facade_search_bolts_and_nuts():
    bolts = library_registry.search_bolts(nominal_diameter=12, standard="EN 14399-3")
    nuts = library_registry.search_nuts(nominal_diameter=12, standard="EN 14399-4")
    assert [r["id"] for r in bolts] == ["BOLT-EN14399-M12"]
    assert [r["id"] for r in nuts] == ["NUT-EN14399-M12"]


# ---------------------------------------------------------------------
# 25-33: bolt<->nut compatibility service
# ---------------------------------------------------------------------


def _get_bolt(**kwargs):
    results = population.search_bolts(**kwargs)
    assert results, f"no bolt found for {kwargs}"
    return results[0]


def _get_nut(**kwargs):
    results = population.search_nuts(**kwargs)
    assert results, f"no nut found for {kwargs}"
    return results[0]


def test_compatible_pair_returns_no_errors():
    bolt = _get_bolt(standard="ISO 4017", nominal_diameter=10, designation="M10")
    nut = _get_nut(standard="ISO 4032", nominal_diameter=10)
    result = check_bolt_nut_compatibility(bolt, nut)
    assert isinstance(result, CompatibilityResult)
    assert result.compatible is True
    assert result.errors == []


def test_diameter_mismatch_is_an_error():
    bolt = _get_bolt(standard="ISO 4017", nominal_diameter=12, designation="M12")
    nut = _get_nut(standard="ISO 4032", nominal_diameter=10)
    result = check_bolt_nut_compatibility(bolt, nut)
    assert result.compatible is False
    assert any("diameter" in e.lower() for e in result.errors)


def test_pitch_mismatch_is_an_error():
    bolt = _get_bolt(standard="EN 14399-3", nominal_diameter=12)  # coarse
    fine_nut = next(
        r for r in population.search_nuts(nominal_diameter=12)
        if r.get("coarse_or_fine") == "fine"
    )
    result = check_bolt_nut_compatibility(bolt, fine_nut)
    assert result.compatible is False
    assert any("pitch" in e.lower() for e in result.errors)


def test_strength_class_mismatch_is_an_error():
    # 10.9 bolt with a nut class weaker than the ISO 898-2 minimum (10).
    bolt = _get_bolt(standard="EN 14399-3", nominal_diameter=12)
    weak_nut = _get_nut(standard="ISO 4032", nominal_diameter=12)  # class "8"
    result = check_bolt_nut_compatibility(bolt, weak_nut)
    assert result.compatible is False
    assert any("nut property class" in e.lower() for e in result.errors)


def test_temperature_mismatch_produces_warning_not_error():
    bolt = _get_bolt(standard="ISO 4017", nominal_diameter=10, designation="M10")
    nut = _get_nut(standard="ISO 4032", nominal_diameter=10)
    bolt = dict(bolt, operating_temperature_min_c=200.0, operating_temperature_max_c=250.0)
    result = check_bolt_nut_compatibility(bolt, nut)
    assert any("temperature" in w.lower() for w in result.warnings)
    # A temperature mismatch alone is a warning, not a blocking error.
    assert result.compatible is True


def test_coating_mismatch_produces_warning():
    bolt = _get_bolt(standard="ISO 4017", nominal_diameter=10, designation="M10")
    nut = _get_nut(standard="ISO 4032", nominal_diameter=10)
    bolt = dict(bolt, coating_compatibility=["Xylan"])
    nut = dict(nut, coating_compatibility=["Dacromet"])
    result = check_bolt_nut_compatibility(bolt, nut)
    assert any("coating" in w.lower() for w in result.warnings)
    assert result.compatible is True


def test_lock_nut_reuse_warning():
    bolt = _get_bolt(standard="ISO 4017", nominal_diameter=10, designation="M10")
    lock_nut = _get_nut(standard="ISO 7042", nominal_diameter=10)
    result = check_bolt_nut_compatibility(bolt, lock_nut)
    assert any("not rated for reuse" in w.lower() for w in result.warnings)


def test_lubrication_mismatch_produces_warning():
    bolt = _get_bolt(standard="ISO 4017", nominal_diameter=10, designation="M10")
    nut = _get_nut(standard="ISO 4032", nominal_diameter=10)
    bolt = dict(bolt, lubrication_state="Waxed")
    nut = dict(nut, lubrication_state="As supplied (unlubricated)")
    result = check_bolt_nut_compatibility(bolt, nut)
    assert any("lubrication" in w.lower() for w in result.warnings)


def test_cross_standard_family_pairing_warning():
    bolt = _get_bolt(standard="DIN 933", nominal_diameter=10, designation="M10")
    nut = _get_nut(standard="ISO 4032", nominal_diameter=10)
    result = check_bolt_nut_compatibility(bolt, nut)
    assert any("cross-standard" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------
# 34-36: backward compatibility, legacy loading, migration
# ---------------------------------------------------------------------


def test_legacy_find_bolt_api_unchanged():
    results = population.find_bolt(diameter_mm=10, head_type="Hex")
    assert results
    assert all(r["diameter_mm"] == 10 and r["head_type"] == "Hex" for r in results)


def test_legacy_find_nut_api_unchanged():
    results = population.find_nut(diameter_mm=10, standard="ISO 4032")
    assert results
    assert results[0]["source_standard"] == "ISO 4032"


def test_legacy_bolt_records_present_and_enriched():
    bolts = population.load_population_records("bolt library")
    legacy = [r for r in bolts if r["id"] == "BOLT-M10-HEX"]
    assert len(legacy) == 1
    record = legacy[0]
    # Original Faz 2.4.1 fields untouched.
    assert record["source_standard"] == "ISO 4017"
    assert record["diameter_mm"] == 10
    # Faz 2.4.1B backfill fields present.
    assert record["bolt_family"] == "Hexagon head screw"
    assert record["nominal_diameter_mm"] == 10.0


def test_legacy_nut_records_present_and_enriched():
    nuts = population.load_population_records("nut library")
    legacy = [r for r in nuts if r["id"] == "NUT-ISO4032-M10"]
    assert len(legacy) == 1
    record = legacy[0]
    assert record["source_standard"] == "ISO 4032"
    assert record["nut_family"] == "Hexagon nut"


def test_migration_registry_record_count_matches_after_populate():
    lib = get_library("nut library")
    assert lib.records == []
    try:
        population.populate_library(lib)
        live_count = len(population.load_population_records("nut library"))
        assert lib.metadata.record_count == live_count
    finally:
        lib.replace_records([])
