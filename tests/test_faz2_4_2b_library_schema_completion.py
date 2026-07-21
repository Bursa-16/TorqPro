"""Faz 2.4.2B tests: library schema completion.

Covers everything Faz 2.4.2B added to ``backend/library/models.py``:

- the eleven new enums (``Status``, ``UnitSystem``, ``ThreadDirection``,
  ``ThreadSeries``, ``StandardType``, ``MaterialType``, ``CoatingType``,
  ``LubricationType``, ``HeadType``, ``DriveType``, ``LockingType``);
- the common metadata block added to ``LibraryRecordBase``;
- the 28 previously-unmodelled engineering fields identified by the
  Faz 2.4.2A inventory (``docs/phase_2_4_2_schema_inventory.md``),
  now declared on ``BoltRecord`` / ``NutRecord`` / ``MaterialRecord``
  / ``CoatingRecord`` / ``LubricationRecord``;
- ``to_dict()`` / ``from_dict()`` / ``serialize()`` / ``deserialize()``;
- physical-validity numeric constraints (``gt=0`` etc.) on the new
  fields;
- backward compatibility with every pre-Faz-2.4.2B record and test.

Does not touch, load or migrate any real record set beyond read-only
validation against the live ``data/*.json`` files (no data file is
ever written by this suite).
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.library import models
from backend.library.models import (
    BoltRecord,
    CoatingRecord,
    CoatingType,
    ConfidenceLevel,
    DriveType,
    HeadType,
    JointHardwareRecord,
    KNOWN_THREAD_SERIES,
    LibraryRecordBase,
    LockingType,
    LubricationRecord,
    LubricationType,
    MaterialRecord,
    MaterialType,
    NutRecord,
    Status,
    StandardType,
    ThreadDirection,
    ThreadRecord,
    ThreadSeries,
    UnitSystem,
    WasherRecord,
    find_schema_violations,
)

# ---------------------------------------------------------------------------
# Common metadata block (LibraryRecordBase)
# ---------------------------------------------------------------------------


def test_library_record_base_new_metadata_defaults():
    record = LibraryRecordBase()
    assert record.name == ""
    assert record.standard == ""
    assert record.description == ""
    assert record.aliases == []
    assert record.created_at is None
    assert record.updated_at is None
    assert record.record_version == "1.0"
    assert record.status is Status.DRAFT
    assert record.unit_system is UnitSystem.METRIC
    assert record.country == ""
    assert record.manufacturer == ""
    assert record.tags == []


def test_library_record_base_new_metadata_accepts_values():
    record = LibraryRecordBase.model_validate(
        {
            "id": "x",
            "name": "Test Record",
            "standard": "ISO 4762",
            "description": "A test record.",
            "aliases": ["alt-name"],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-06-01T00:00:00",
            "record_version": "1.1",
            "status": "verified",
            "unit_system": "metric",
            "country": "TR",
            "manufacturer": "TorqPro",
            "tags": ["fastener", "iso"],
        }
    )
    assert record.name == "Test Record"
    assert record.standard == "ISO 4762"
    assert record.aliases == ["alt-name"]
    assert record.record_version == "1.1"
    assert record.status is Status.VERIFIED
    assert record.unit_system is UnitSystem.METRIC
    assert record.country == "TR"
    assert record.manufacturer == "TorqPro"
    assert record.tags == ["fastener", "iso"]
    assert record.created_at is not None
    assert record.updated_at is not None


def test_status_and_unit_system_reject_unknown_values():
    with pytest.raises(ValidationError):
        LibraryRecordBase.model_validate({"id": "x", "status": "not-a-status"})
    with pytest.raises(ValidationError):
        LibraryRecordBase.model_validate({"id": "x", "unit_system": "furlongs"})


# ---------------------------------------------------------------------------
# Serialization: to_dict / from_dict / serialize / deserialize
# ---------------------------------------------------------------------------


def test_to_dict_returns_json_safe_plain_dict():
    record = BoltRecord(id="B1", head_type=HeadType.HEX, diameter_mm=8.0)
    data = record.to_dict()
    assert isinstance(data, dict)
    assert data["head_type"] == "Hex"  # plain string value, not "HeadType.HEX"
    assert data["diameter_mm"] == 8.0
    # Must be JSON-round-trippable without a custom encoder.
    json.dumps(data)


def test_from_dict_round_trips_with_to_dict():
    original = BoltRecord(
        id="B2",
        head_type=HeadType.SOCKET,
        drive_type=DriveType.HEX_SOCKET_INTERNAL,
        diameter_mm=10.0,
        coating_compatibility=["Plain", "Zinc flake"],
    )
    rebuilt = BoltRecord.from_dict(original.to_dict())
    assert rebuilt == original


def test_from_dict_accepts_enum_instance_or_raw_string():
    from_string = BoltRecord.from_dict({"id": "a", "head_type": "Flange"})
    from_enum = BoltRecord.from_dict({"id": "b", "head_type": HeadType.FLANGE})
    assert from_string.head_type is HeadType.FLANGE
    assert from_enum.head_type is HeadType.FLANGE


def test_serialize_produces_enum_value_not_enum_name():
    record = CoatingRecord(id="C1", coating_type=CoatingType.ZINC_NICKEL)
    payload = record.serialize()
    assert isinstance(payload, str)
    assert "Zinc-nickel, ISO 4042" in payload
    assert "CoatingType.ZINC_NICKEL" not in payload
    assert "ZINC_NICKEL" not in payload


def test_deserialize_round_trips_with_serialize():
    original = LubricationRecord(
        id="L1",
        lubricant_type=LubricationType.PTFE_DRY_FILM,
        oem_compatibility=["FIAT", "VW"],
    )
    rebuilt = LubricationRecord.deserialize(original.serialize())
    assert rebuilt == original
    assert rebuilt.oem_compatibility == ["FIAT", "VW"]


def test_deserialize_invalid_json_raises_clear_error():
    with pytest.raises(ValidationError) as excinfo:
        BoltRecord.deserialize("{this is not valid json")
    assert "json" in str(excinfo.value).lower()


def test_deserialize_valid_json_but_wrong_shape_raises():
    # Valid JSON, but not an object -- must still fail clearly rather
    # than silently constructing a bogus record.
    with pytest.raises(ValidationError):
        ThreadRecord.deserialize("[1, 2, 3]")


def test_to_dict_handles_optional_list_and_dict_fields():
    record = NutRecord(
        id="N1",
        locking_type=None,
        strength_compatibility=["4.6", "4.8"],
        metadata={"batch": 42},
        aliases=["din-985-equivalent"],
    )
    data = record.to_dict()
    assert data["locking_type"] is None
    assert data["strength_compatibility"] == ["4.6", "4.8"]
    assert data["metadata"] == {"batch": 42}
    assert data["aliases"] == ["din-985-equivalent"]
    # Round-trips cleanly through JSON with no custom encoder needed.
    reloaded = NutRecord.from_dict(json.loads(json.dumps(data)))
    assert reloaded == record


def test_unknown_field_behaviour_matches_existing_project_approach():
    # extra="allow" everywhere except ThreadRecord (unchanged Faz
    # 2.4.1A decision) -- Faz 2.4.2B does not alter this.
    allowed = BoltRecord.model_validate({"id": "x", "totally_unmodelled_key": "v"})
    assert getattr(allowed, "totally_unmodelled_key") == "v"
    with pytest.raises(ValidationError):
        ThreadRecord.model_validate(
            {"designation": "M8", "totally_unmodelled_key": "v"}
        )


# ---------------------------------------------------------------------------
# BoltRecord: 17-field gap + thread_direction + enum retyping
# ---------------------------------------------------------------------------


def test_bolt_record_accepts_all_faz_2_4_2b_fields():
    raw = {
        "id": "BOLT-M8x1.25-8.8",
        "designation": "M8x1.25",
        "head_type": "Hex",
        "drive_type": "Hex (external)",
        "standard_organization": "ISO",
        "diameter_mm": 8.0,
        "pitch_coarse_mm": 1.25,
        "pitch_fine_mm": 1.0,
        "stress_area_mm2": 36.6,
        "minor_diameter_mm": 6.466,
        "pitch_diameter_mm": 7.188,
        "head_across_flats_mm": 13.0,
        "head_across_corners_mm": 14.38,
        "head_height_mm": 5.3,
        "socket_size_mm": None,
        "washer_face_diameter_mm": 12.4,
        "bearing_diameter_mm": 13.0,
        "recommended_hole_mm": 9.0,
        "clearance_hole_medium_mm": 9.0,
        "tap_drill_mm": 6.8,
        "thread_engagement_mm": 8.0,
        "weight_kg_per_100": 3.11,
    }
    record = BoltRecord.model_validate(raw)
    assert record.head_type is HeadType.HEX
    assert record.drive_type is DriveType.HEX_EXTERNAL
    assert record.standard_organization is StandardType.ISO
    assert record.diameter_mm == 8.0
    assert record.socket_size_mm is None
    assert record.thread_direction is ThreadDirection.RIGHT  # default


def test_bolt_record_defaults_keep_predating_records_valid():
    # Minimal dict, exactly as used since Faz 2.4.0 -- none of the
    # Faz 2.4.2B fields are set. Must still validate.
    record = BoltRecord.model_validate({"id": "BOLT-OLD", "designation": "M8"})
    assert record.diameter_mm is None
    assert record.head_type is HeadType.UNSPECIFIED
    assert record.drive_type is DriveType.UNSPECIFIED
    assert record.standard_organization is StandardType.UNSPECIFIED
    assert record.thread_direction is ThreadDirection.RIGHT


def test_bolt_record_rejects_unknown_head_type():
    with pytest.raises(ValidationError):
        BoltRecord.model_validate({"id": "x", "head_type": "Torx"})


def test_bolt_record_rejects_negative_or_zero_physical_dimensions():
    for field in (
        "diameter_mm",
        "pitch_coarse_mm",
        "pitch_fine_mm",
        "stress_area_mm2",
        "minor_diameter_mm",
        "pitch_diameter_mm",
        "recommended_hole_mm",
        "clearance_hole_medium_mm",
        "tap_drill_mm",
        "thread_engagement_mm",
        "weight_kg_per_100",
    ):
        with pytest.raises(ValidationError):
            BoltRecord.model_validate({"id": "x", field: 0})
        with pytest.raises(ValidationError):
            BoltRecord.model_validate({"id": "x", field: -1.0})


def test_bolt_record_nullable_geometry_fields_reject_negative_when_set():
    with pytest.raises(ValidationError):
        BoltRecord.model_validate({"id": "x", "head_across_flats_mm": -13.0})
    # But still permit None (unset).
    record = BoltRecord.model_validate({"id": "x", "head_across_flats_mm": None})
    assert record.head_across_flats_mm is None


def test_bolt_library_json_records_all_parse_with_faz_2_4_2b_fields_populated():
    with open("backend/library/data/bolt_library.json") as f:
        records = json.load(f)["records"]
    assert len(records) == 176
    typed = [BoltRecord.model_validate(r) for r in records]
    assert all(t.diameter_mm is not None for t in typed)
    assert all(t.weight_kg_per_100 is not None for t in typed)
    assert all(isinstance(t.head_type, HeadType) for t in typed)
    assert all(isinstance(t.standard_organization, StandardType) for t in typed)


# ---------------------------------------------------------------------------
# NutRecord: 5-field gap + thread_direction + LockingType + StandardType
# ---------------------------------------------------------------------------


def test_nut_record_accepts_all_faz_2_4_2b_fields():
    raw = {
        "id": "NUT-M8-8",
        "designation": "M8",
        "bearing_face": "Flat, chamfered",
        "flange": False,
        "width_across_flats_mm": 13.0,
        "locking_type": "None",
        "strength_compatibility": ["4.6", "4.8", "8.8"],
        "standard_organization": "DIN",
    }
    record = NutRecord.model_validate(raw)
    assert record.bearing_face == "Flat, chamfered"
    assert record.flange is False
    assert record.width_across_flats_mm == 13.0
    assert record.locking_type is LockingType.NONE
    assert record.strength_compatibility == ["4.6", "4.8", "8.8"]
    assert record.standard_organization is StandardType.DIN


def test_nut_record_locking_type_string_none_is_not_python_none():
    # Inventory §2: the JSON value "None" is a literal string, distinct
    # from JSON null / Python None. Both must be representable and
    # distinguishable.
    literal_none = NutRecord.model_validate({"id": "x", "locking_type": "None"})
    unset = NutRecord.model_validate({"id": "y"})
    assert literal_none.locking_type is LockingType.NONE
    assert literal_none.locking_type is not None
    assert unset.locking_type is None


def test_nut_record_defaults_keep_predating_records_valid():
    record = NutRecord.model_validate({"id": "NUT-OLD", "designation": "M8"})
    assert record.bearing_face == ""
    assert record.flange is None
    assert record.width_across_flats_mm is None
    assert record.locking_type is None
    assert record.strength_compatibility == []
    assert record.thread_direction is ThreadDirection.RIGHT


def test_nut_record_rejects_unknown_locking_type():
    with pytest.raises(ValidationError):
        NutRecord.model_validate({"id": "x", "locking_type": "Cotter pin"})


def test_nut_record_rejects_negative_width_across_flats():
    with pytest.raises(ValidationError):
        NutRecord.model_validate({"id": "x", "width_across_flats_mm": -13.0})


def test_nut_library_json_records_all_parse_with_faz_2_4_2b_fields_populated():
    with open("backend/library/data/nut_library.json") as f:
        records = json.load(f)["records"]
    assert len(records) == 211
    typed = [NutRecord.model_validate(r) for r in records]
    assert all(t.width_across_flats_mm is not None for t in typed)
    assert all(t.strength_compatibility for t in typed)
    assert sum(1 for t in typed if t.locking_type is LockingType.NONE) == 140
    assert sum(1 for t in typed if t.locking_type is LockingType.NYLON_INSERT) == 54
    assert (
        sum(1 for t in typed if t.locking_type is LockingType.ALL_METAL_DEFORMED) == 17
    )


# ---------------------------------------------------------------------------
# WasherRecord / JointHardwareRecord: StandardType retyping only
# ---------------------------------------------------------------------------


def test_washer_record_standard_organization_is_enum():
    record = WasherRecord.model_validate({"id": "x", "standard_organization": "ISO"})
    assert record.standard_organization is StandardType.ISO
    with pytest.raises(ValidationError):
        WasherRecord.model_validate({"id": "x", "standard_organization": "JIS"})


def test_washer_record_default_standard_organization_unspecified():
    record = WasherRecord.model_validate({"id": "x"})
    assert record.standard_organization is StandardType.UNSPECIFIED


def test_washer_library_json_records_all_parse():
    with open("backend/library/data/washer_library.json") as f:
        records = json.load(f)["records"]
    assert len(records) == 223
    typed = [WasherRecord.model_validate(r) for r in records]
    assert all(isinstance(t.standard_organization, StandardType) for t in typed)


def test_joint_hardware_record_standard_organization_is_enum():
    record = JointHardwareRecord.model_validate(
        {"id": "JH-1", "designation": "Test", "standard_organization": "DIN"}
    )
    assert record.standard_organization is StandardType.DIN


# ---------------------------------------------------------------------------
# MaterialRecord: 3 new fields + legacy duplicate pass-through + MaterialType
# ---------------------------------------------------------------------------


def test_material_record_requires_material_and_accepts_new_fields():
    raw = {
        "id": "MAT-STEEL",
        "material": "Steel",
        "grade": "8.8",
        "rm_mpa": 800.0,
        "rp02_mpa": 640.0,
        "density_kg_mm3": 7.85e-06,
        "poisson_ratio": 0.3,
        "thermal_expansion_per_k": 1.2e-05,
        "ultimate_mpa": 800.0,
        "yield_mpa": 640.0,
    }
    record = MaterialRecord.model_validate(raw)
    assert record.material is MaterialType.STEEL
    assert record.density_kg_mm3 == pytest.approx(7.85e-06)
    assert record.poisson_ratio == 0.3
    assert record.thermal_expansion_per_k == pytest.approx(1.2e-05)
    assert record.ultimate_mpa == record.rm_mpa == 800.0
    assert record.yield_mpa == record.rp02_mpa == 640.0


def test_material_record_material_is_required():
    with pytest.raises(ValidationError):
        MaterialRecord.model_validate({"id": "x"})


def test_material_record_rejects_unknown_material_type():
    with pytest.raises(ValidationError):
        MaterialRecord.model_validate({"id": "x", "material": "Unobtainium"})


def test_material_record_new_fields_are_optional_for_predating_records():
    record = MaterialRecord.model_validate({"id": "x", "material": "Titanium"})
    assert record.density_kg_mm3 is None
    assert record.poisson_ratio is None
    assert record.thermal_expansion_per_k is None
    assert record.ultimate_mpa is None
    assert record.yield_mpa is None


def test_material_record_rejects_non_physical_poisson_ratio():
    with pytest.raises(ValidationError):
        MaterialRecord.model_validate(
            {"id": "x", "material": "Steel", "poisson_ratio": 0.6}
        )
    with pytest.raises(ValidationError):
        MaterialRecord.model_validate(
            {"id": "x", "material": "Steel", "poisson_ratio": -0.1}
        )


def test_material_record_rejects_negative_density():
    with pytest.raises(ValidationError):
        MaterialRecord.model_validate(
            {"id": "x", "material": "Steel", "density_kg_mm3": -1.0}
        )


def test_material_library_json_records_all_parse_and_legacy_fields_match():
    with open("backend/library/data/material_library.json") as f:
        records = json.load(f)["records"]
    assert len(records) == 8
    typed = [MaterialRecord.model_validate(r) for r in records]
    assert all(isinstance(t.material, MaterialType) for t in typed)
    assert all(t.density_kg_mm3 is not None for t in typed)
    # Inventory-documented duplicate relationship, still holds.
    for t in typed:
        assert t.ultimate_mpa == t.rm_mpa
        assert t.yield_mpa == t.rp02_mpa


# ---------------------------------------------------------------------------
# CoatingRecord: 3 new fields + CoatingType
# ---------------------------------------------------------------------------


def test_coating_record_accepts_all_faz_2_4_2b_fields():
    raw = {
        "id": "COAT-ZN-NI",
        "coating_type": "Zinc-nickel, ISO 4042",
        "corrosion_class": "High (720h+ salt spray typ.)",
        "remark": "Preferred for high-corrosion environments.",
        "temperature_range_c": "-40..300",
    }
    record = CoatingRecord.model_validate(raw)
    assert record.coating_type is CoatingType.ZINC_NICKEL
    assert record.corrosion_class == "High (720h+ salt spray typ.)"
    assert record.remark == "Preferred for high-corrosion environments."
    assert record.temperature_range_c == "-40..300"


def test_coating_record_temperature_range_stays_string_not_numeric():
    record = CoatingRecord.model_validate(
        {"id": "x", "temperature_range_c": "-40..300"}
    )
    assert isinstance(record.temperature_range_c, str)


def test_coating_record_rejects_unknown_coating_type():
    with pytest.raises(ValidationError):
        CoatingRecord.model_validate({"id": "x", "coating_type": "Chrome plating"})


def test_coating_record_defaults_keep_predating_records_valid():
    record = CoatingRecord.model_validate({"id": "COAT-OLD"})
    assert record.coating_type is CoatingType.UNSPECIFIED
    assert record.corrosion_class == ""
    assert record.remark is None
    assert record.temperature_range_c == ""


def test_coating_library_json_records_all_parse():
    with open("backend/library/data/coating_library.json") as f:
        records = json.load(f)["records"]
    assert len(records) == 10
    typed = [CoatingRecord.model_validate(r) for r in records]
    assert all(isinstance(t.coating_type, CoatingType) for t in typed)
    assert all(t.corrosion_class for t in typed)
    assert all(".." in t.temperature_range_c for t in typed)


# ---------------------------------------------------------------------------
# LubricationRecord: 1 new field + LubricationType
# ---------------------------------------------------------------------------


def test_lubrication_record_accepts_oem_compatibility_and_enum():
    raw = {
        "id": "LUBE-PTFE",
        "lubricant_type": "PTFE (Teflon) dry-film lubricant",
        "oem_compatibility": ["FIAT", "VW", "Ford", "GM", "Toyota"],
    }
    record = LubricationRecord.model_validate(raw)
    assert record.lubricant_type is LubricationType.PTFE_DRY_FILM
    assert record.oem_compatibility == ["FIAT", "VW", "Ford", "GM", "Toyota"]


def test_lubrication_record_rejects_unknown_lubricant_type():
    with pytest.raises(ValidationError):
        LubricationRecord.model_validate({"id": "x", "lubricant_type": "Snake oil"})


def test_lubrication_record_defaults_keep_predating_records_valid():
    record = LubricationRecord.model_validate({"id": "LUBE-OLD"})
    assert record.lubricant_type is LubricationType.UNSPECIFIED
    assert record.oem_compatibility == []


def test_lubrication_library_json_records_all_parse():
    with open("backend/library/data/lubrication_library.json") as f:
        records = json.load(f)["records"]
    assert len(records) == 8
    typed = [LubricationRecord.model_validate(r) for r in records]
    assert all(isinstance(t.lubricant_type, LubricationType) for t in typed)
    assert all(t.oem_compatibility for t in typed)


# ---------------------------------------------------------------------------
# ThreadRecord: KNOWN_THREAD_SERIES <-> ThreadSeries (item 5)
# ---------------------------------------------------------------------------


def test_known_thread_series_derived_from_thread_series_enum():
    assert KNOWN_THREAD_SERIES == tuple(member.value for member in ThreadSeries)
    assert set(KNOWN_THREAD_SERIES) == {
        "ISO_METRIC",
        "UNC",
        "UNF",
        "UNEF",
        "BSP",
        "NPT",
        "TRAPEZOIDAL",
    }


def test_thread_record_thread_series_field_still_accepts_free_text():
    # thread_series stays untyped str (Faz 2.4.1A design, unchanged):
    # must keep accepting values outside the known enum, not reject
    # them at the schema layer.
    record = ThreadRecord.model_validate(
        {"designation": "M8", "thread_series": "SOME_FUTURE_SERIES"}
    )
    assert record.thread_series == "SOME_FUTURE_SERIES"

    known = ThreadRecord.model_validate(
        {"designation": "M8", "thread_series": "ISO_METRIC"}
    )
    assert known.thread_series == "ISO_METRIC"
    assert known.thread_series in KNOWN_THREAD_SERIES


def test_thread_record_extra_forbid_unchanged_by_faz_2_4_2b():
    # ThreadRecord keeps extra="forbid" (Faz 2.4.1A); Faz 2.4.2B's new
    # LibraryRecordBase metadata fields are declared, so they're
    # accepted with defaults -- they do not trip extra="forbid".
    record = ThreadRecord.model_validate({"designation": "M8", "name": "Metric M8"})
    assert record.name == "Metric M8"
    with pytest.raises(ValidationError):
        ThreadRecord.model_validate({"designation": "M8", "not_a_real_field": 1})


def test_thread_library_json_records_all_parse_with_new_base_metadata():
    with open("backend/library/data/thread_library.json") as f:
        records = json.load(f)["records"]
    assert len(records) == 134
    typed = [ThreadRecord.model_validate(r) for r in records]
    assert all(t.status is Status.DRAFT for t in typed)
    assert all(t.unit_system is UnitSystem.METRIC for t in typed)


# ---------------------------------------------------------------------------
# Enum <-> string parsing (generic, across enums)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "enum_cls,value,expected_member",
    [
        (Status, "approved", Status.APPROVED),
        (UnitSystem, "imperial", UnitSystem.IMPERIAL),
        (ThreadDirection, "left", ThreadDirection.LEFT),
        (ThreadSeries, "UNC", ThreadSeries.UNC),
        (StandardType, "FIAT", StandardType.FIAT),
        (MaterialType, "Brass", MaterialType.BRASS),
        (CoatingType, "Black oxide (gun bluing) + oil", CoatingType.BLACK_OXIDE_OIL),
        (LubricationType, "Graphite-based paste", LubricationType.GRAPHITE_PASTE),
        (HeadType, "Headless", HeadType.HEADLESS),
        (DriveType, "Hex socket (internal)", DriveType.HEX_SOCKET_INTERNAL),
        (LockingType, "Nylon insert", LockingType.NYLON_INSERT),
    ],
)
def test_enum_parses_from_string_value(enum_cls, value, expected_member):
    assert enum_cls(value) is expected_member


def test_all_faz_2_4_2b_enums_are_str_subclasses_for_transparent_json_output():
    for enum_cls in (
        Status,
        UnitSystem,
        ThreadDirection,
        ThreadSeries,
        StandardType,
        MaterialType,
        CoatingType,
        LubricationType,
        HeadType,
        DriveType,
        LockingType,
    ):
        assert issubclass(enum_cls, str)


# ---------------------------------------------------------------------------
# Cross-domain: zero schema violations against every live data file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "library_key,path,expected_count",
    [
        ("bolt library", "backend/library/data/bolt_library.json", 176),
        ("nut library", "backend/library/data/nut_library.json", 211),
        ("washer library", "backend/library/data/washer_library.json", 223),
        ("thread library", "backend/library/data/thread_library.json", 134),
        ("material library", "backend/library/data/material_library.json", 8),
        ("coating library", "backend/library/data/coating_library.json", 10),
        ("lubrication library", "backend/library/data/lubrication_library.json", 8),
        (
            "strength class library",
            "backend/library/data/strength_class_library.json",
            15,
        ),
        ("oem library", "backend/library/data/oem_library.json", 18),
    ],
)
def test_no_schema_violations_against_live_data(library_key, path, expected_count):
    with open(path) as f:
        records = json.load(f)["records"]
    assert len(records) == expected_count
    assert find_schema_violations(library_key, records) == []


# ---------------------------------------------------------------------------
# Backward compatibility: confidence/notes/id defaults untouched
# ---------------------------------------------------------------------------


def test_confidence_level_unaffected_by_faz_2_4_2b():
    assert ConfidenceLevel(2) is ConfidenceLevel.G2
    record = LibraryRecordBase.model_validate({"id": "x", "confidence": 2})
    assert record.confidence is ConfidenceLevel.G2


def test_library_record_base_still_allows_extra_fields():
    record = LibraryRecordBase.model_validate({"id": "x", "unmodelled_key": "value"})
    assert record.id == "x"


def test_models_module_exports_new_enums():
    for name in (
        "Status",
        "UnitSystem",
        "ThreadDirection",
        "ThreadSeries",
        "StandardType",
        "MaterialType",
        "CoatingType",
        "LubricationType",
        "HeadType",
        "DriveType",
        "LockingType",
    ):
        assert hasattr(models, name)
        assert name in models.__all__
