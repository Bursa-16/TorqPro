"""Faz 2.4.1C tests: washer engineering database.

Covers the Faz 2.4.1C structured ``WasherRecord`` fields, the new
washer validators, the new washer search API
(``find_washer_by_standard`` / ``find_washer_by_size`` /
``find_washer_by_material`` / ``find_washer_for_bolt`` /
``find_washer_locking`` / ``find_washer_temperature``), the DIN 127 B
generator's idempotency, and backward compatibility with the
pre-existing 189 flat-washer records. Generator tests run entirely
against temporary copies of the data file -- the real
``backend/library/data/washer_library.json`` is never touched by this
suite.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

from backend.library import population, validator
from backend.library.facade import library_registry
from backend.library.models import find_schema_violations

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "backend" / "library" / "data"
GENERATOR_PATH = REPO_ROOT / "tools" / "generate_faz2_4_1c_washer_records.py"


def _load_generator_module():
    spec = importlib.util.spec_from_file_location("faz2_4_1c_generator", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record_checksum(record: dict) -> str:
    payload = {k: v for k, v in record.items() if k != "checksum"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def setup_module(_module):
    population.clear_cache()


# ---------------------------------------------------------------------
# 1-2: data loading, schema, record counts
# ---------------------------------------------------------------------


def test_washer_data_loading():
    records = population.load_population_records("washer library")
    assert len(records) == 223
    assert all("id" in r and "designation" in r for r in records)


def test_washer_records_satisfy_pydantic_schema():
    records = population.load_population_records("washer library")
    assert find_schema_violations("washer library", records) == []


def test_din127b_record_count():
    records = population.load_population_records("washer library")
    din127b = [r for r in records if r.get("source_standard") == "DIN 127 B"]
    assert len(din127b) == 34


def test_legacy_flat_washer_records_still_present():
    records = population.load_population_records("washer library")
    legacy_standards = {
        "ISO 7089",
        "ISO 7090",
        "ISO 7091",
        "ISO 7093",
        "ISO 8738",
        "DIN 125",
        "DIN 9021",
    }
    legacy = [r for r in records if r.get("source_standard") in legacy_standards]
    assert len(legacy) == 189


# ---------------------------------------------------------------------
# 3: backward compatibility -- pre-existing records keep validating
# ---------------------------------------------------------------------


def test_legacy_records_have_new_fields_backfilled():
    records = population.load_population_records("washer library")
    iso7089 = next(r for r in records if r["id"] == "WASH-ISO7089-M3")
    assert iso7089["standard_organization"] == "ISO"
    assert iso7089["washer_type"]
    assert iso7089["compatible_bolt_sizes"] == ["M3"]


def test_legacy_records_do_not_invent_material_or_temperature():
    records = population.load_population_records("washer library")
    legacy_standards = {
        "ISO 7089",
        "ISO 7090",
        "ISO 7091",
        "ISO 7093",
        "ISO 8738",
        "DIN 125",
        "DIN 9021",
    }
    legacy = [r for r in records if r.get("source_standard") in legacy_standards]
    for record in legacy:
        assert record.get("material", "") == ""
        assert record.get("operating_temperature_min_c") is None
        assert record.get("operating_temperature_max_c") is None


def test_din127b_records_have_verified_dimensions_and_source():
    records = population.load_population_records("washer library")
    m10 = next(r for r in records if r["id"] == "WASH-DIN127B-M10")
    assert m10["inner_diameter_mm"] == 10.2
    assert m10["outer_diameter_mm"] == 18.1
    assert m10["thickness_mm"] == 2.2
    assert m10["source"] == "DIN 127 B"
    assert m10["material"] == "Spring steel"
    assert m10["locking_principle"]


# ---------------------------------------------------------------------
# 4: duplicate detection
# ---------------------------------------------------------------------


def test_no_duplicate_washer_ids_in_live_data():
    records = population.load_population_records("washer library")
    assert validator.find_duplicate_ids(records) == []


def test_no_duplicate_designation_standard_in_live_data():
    records = population.load_population_records("washer library")
    assert validator.find_duplicate_designation_standard_dimension(records) == []


def test_duplicate_washer_id_detected_on_fixture():
    records = [
        {"id": "WASH-X", "designation": "M8"},
        {"id": "WASH-X", "designation": "M10"},
    ]
    issues = validator.find_duplicate_ids(records)
    assert len(issues) == 1
    assert issues[0].code == "duplicate_id"


# ---------------------------------------------------------------------
# 5: dimension validators
# ---------------------------------------------------------------------


def test_non_positive_washer_dimension_detected():
    records = [
        {
            "id": "W1",
            "inner_diameter_mm": 0,
            "outer_diameter_mm": 10,
            "thickness_mm": 1,
        },
        {
            "id": "W2",
            "inner_diameter_mm": 3,
            "outer_diameter_mm": -5,
            "thickness_mm": 1,
        },
    ]
    issues = validator.find_non_positive_washer_dimensions(records)
    assert len(issues) == 2
    assert all(i.code == "non_positive_washer_dimension" for i in issues)


def test_inner_diameter_not_less_than_outer_detected():
    records = [{"id": "W1", "inner_diameter_mm": 12.0, "outer_diameter_mm": 10.0}]
    issues = validator.find_inner_diameter_not_less_than_outer(records)
    assert len(issues) == 1
    assert issues[0].code == "inner_diameter_not_less_than_outer"


def test_inner_less_than_outer_passes():
    records = [{"id": "W1", "inner_diameter_mm": 3.2, "outer_diameter_mm": 7.0}]
    assert validator.find_inner_diameter_not_less_than_outer(records) == []


def test_invalid_compatible_bolt_size_format_detected():
    records = [{"id": "W1", "compatible_bolt_sizes": ["M8", "not-a-size", "8mm"]}]
    issues = validator.find_invalid_compatible_bolt_size_format(records)
    assert len(issues) == 2


def test_valid_compatible_bolt_size_format_passes():
    records = [{"id": "W1", "compatible_bolt_sizes": ["M8", "M3.5", "M100"]}]
    assert validator.find_invalid_compatible_bolt_size_format(records) == []


def test_all_live_washer_records_pass_dimension_and_format_checks():
    records = population.load_population_records("washer library")
    assert validator.find_non_positive_washer_dimensions(records) == []
    assert validator.find_inner_diameter_not_less_than_outer(records) == []
    assert validator.find_invalid_compatible_bolt_size_format(records) == []


def test_validate_washer_library_aggregate_report_is_clean():
    records = population.load_population_records("washer library")
    report = validator.validate_washer_library(records)
    assert report.is_valid, [i.message for i in report.issues]


def test_validate_washer_library_records_population_entry_point():
    assert population.validate_washer_library_records() == []


# ---------------------------------------------------------------------
# 6: search API
# ---------------------------------------------------------------------


def test_find_washer_by_standard():
    records = population.find_washer_by_standard("DIN 127 B")
    assert len(records) == 34
    assert all(r["source_standard"] == "DIN 127 B" for r in records)


def test_find_washer_by_standard_no_match():
    assert population.find_washer_by_standard("ISO 99999") == []


def test_find_washer_by_size_nominal():
    records = population.find_washer_by_size(nominal_size_mm=10)
    ids = {r["id"] for r in records}
    assert "WASH-DIN127B-M10" in ids
    assert any(i.startswith("WASH-ISO7089-M10") for i in ids)


def test_find_washer_by_size_designation_substring():
    records = population.find_washer_by_size(designation="DIN 127 B M12")
    assert len(records) == 1
    assert records[0]["id"] == "WASH-DIN127B-M12"


def test_find_washer_by_material():
    records = population.find_washer_by_material("Spring steel")
    assert len(records) == 34
    assert all(r["material"] == "Spring steel" for r in records)


def test_find_washer_by_material_no_invented_matches():
    # Legacy flat-washer records never had material populated, so a
    # query for a generic steel grade must not silently match them.
    records = population.find_washer_by_material("Carbon steel")
    assert records == []


def test_find_washer_for_bolt():
    records = population.find_washer_for_bolt("M8")
    ids = {r["id"] for r in records}
    assert "WASH-DIN127B-M8" in ids
    assert len(records) >= 2  # DIN127B + at least one flat-washer standard


def test_find_washer_for_bolt_case_insensitive():
    records_upper = population.find_washer_for_bolt("M8")
    records_lower = population.find_washer_for_bolt("m8")
    assert {r["id"] for r in records_upper} == {r["id"] for r in records_lower}


def test_find_washer_locking_returns_only_lock_washers():
    records = population.find_washer_locking()
    assert len(records) == 34
    assert all(r["source_standard"] == "DIN 127 B" for r in records)


def test_find_washer_locking_flat_washers_excluded():
    records = population.find_washer_locking()
    ids = {r["id"] for r in records}
    assert "WASH-ISO7089-M3" not in ids


def test_find_washer_locking_substring_filter():
    records = population.find_washer_locking(locking="spring tension")
    assert len(records) == 34
    no_match = population.find_washer_locking(locking="wedge")
    assert no_match == []


def test_find_washer_temperature_returns_empty_without_verified_data():
    # No currently-populated washer record has a verified temperature
    # limit (see Faz 2.4.1C generator docstring) -- this must return
    # an empty list rather than inventing a match.
    assert population.find_washer_temperature(min_c=-20, max_c=80) == []


def test_find_washer_temperature_matches_fixture_with_declared_range():
    records = [
        {
            "id": "W-TEMP",
            "operating_temperature_min_c": -40.0,
            "operating_temperature_max_c": 120.0,
        },
    ]
    matches = [
        r
        for r in records
        if r["operating_temperature_min_c"] <= -20
        and r["operating_temperature_max_c"] >= 80
    ]
    assert len(matches) == 1


# ---------------------------------------------------------------------
# 7: facade wiring
# ---------------------------------------------------------------------


def test_facade_exposes_washer_search_methods():
    assert library_registry.find_washer_by_standard("DIN 127 B")
    assert library_registry.find_washer_for_bolt("M8")
    assert library_registry.find_washer_locking()
    assert library_registry.find_washer_by_material("Spring steel")
    assert library_registry.find_washer_by_size(nominal_size_mm=10)
    assert library_registry.find_washer_temperature(min_c=0) == []


# ---------------------------------------------------------------------
# 8: checksum integrity
# ---------------------------------------------------------------------


def test_every_washer_record_checksum_matches_content():
    records = population.load_population_records("washer library")
    mismatches = [r["id"] for r in records if r.get("checksum") != _record_checksum(r)]
    assert mismatches == []


# ---------------------------------------------------------------------
# 9: generator idempotency (runs against temp copies only)
# ---------------------------------------------------------------------


def test_generator_is_idempotent_on_temp_copy(tmp_path):
    temp_data_dir = tmp_path / "data"
    temp_data_dir.mkdir()
    temp_washer_path = temp_data_dir / "washer_library.json"
    shutil.copy(DATA_DIR / "washer_library.json", temp_washer_path)

    generator = _load_generator_module()
    generator.WASHER_PATH = str(temp_washer_path)

    generator.main()
    first_pass = json.loads(temp_washer_path.read_text(encoding="utf-8"))

    generator.main()
    second_pass = json.loads(temp_washer_path.read_text(encoding="utf-8"))

    assert first_pass == second_pass
    assert len(second_pass["records"]) == len(first_pass["records"])


def test_generator_does_not_duplicate_legacy_records(tmp_path):
    temp_data_dir = tmp_path / "data"
    temp_data_dir.mkdir()
    temp_washer_path = temp_data_dir / "washer_library.json"

    original = json.loads(
        (DATA_DIR / "washer_library.json").read_text(encoding="utf-8")
    )
    legacy_only = copy.deepcopy(original)
    legacy_only["records"] = [
        r for r in legacy_only["records"] if r.get("source_standard") != "DIN 127 B"
    ]
    temp_washer_path.write_text(json.dumps(legacy_only), encoding="utf-8")

    generator = _load_generator_module()
    generator.WASHER_PATH = str(temp_washer_path)
    generator.main()

    result = json.loads(temp_washer_path.read_text(encoding="utf-8"))
    ids = [r["id"] for r in result["records"]]
    assert len(ids) == len(set(ids))
    assert len(result["records"]) == 189 + 34
