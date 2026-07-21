"""Faz 2.4.0 tests: backend/library/models.py typed schema layer.

Covers only the new typed-validation surface. Does not touch, load or
migrate any real record set (out of scope for Faz 2.4.0).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.library.models import (
    ConfidenceLevel,
    LIBRARY_RECORD_MODELS,
    LibraryRecordBase,
    BoltRecord,
    CompatibilityRecord,
    OEMRecord,
    ThreadRecord,
    find_schema_violations,
    get_record_model,
    parse_typed_records,
)


def test_confidence_level_matches_existing_json_int_convention():
    # data/Civata_Somun_Uyumluluk.json and
    # data/Teknik_Kaynak_Kayitlari.json both use "confidence": 2.
    assert ConfidenceLevel(2) is ConfidenceLevel.G2
    record = LibraryRecordBase.model_validate({"id": "x", "confidence": 2})
    assert record.confidence is ConfidenceLevel.G2


def test_library_record_base_defaults():
    record = LibraryRecordBase()
    assert record.id == ""
    assert record.confidence is ConfidenceLevel.G4
    assert record.notes == ""


def test_library_record_base_allows_extra_fields():
    # Existing JSON files may carry descriptive keys no schema models
    # explicitly yet; extra fields must not be rejected in this phase.
    record = LibraryRecordBase.model_validate({"id": "x", "unmodelled_key": "value"})
    assert record.id == "x"


def test_all_nine_shells_plus_oem_are_mapped():
    # Faz 2.4.1C adds a tenth domain (joint hardware library, shell
    # only -- see backend/library/joint_hardware_library.py); the
    # original nine domain shells plus OEM are unchanged.
    expected_keys = {
        "bolt library",
        "nut library",
        "washer library",
        "thread library",
        "material library",
        "coating library",
        "lubrication library",
        "strength class library",
        "compatibility library",
        "oem library",
        "joint hardware library",
    }
    assert set(LIBRARY_RECORD_MODELS.keys()) == expected_keys


def test_get_record_model_unknown_key_returns_base():
    assert get_record_model("unregistered library") is LibraryRecordBase


def test_bolt_record_parses_valid_dict():
    raw = {
        "id": "BOLT-M8x1.25-8.8",
        "designation": "M8x1.25",
        "thread": "M8",
        "property_class": "8.8",
        "material": "8.8",
        "confidence": 1,
    }
    record = BoltRecord.model_validate(raw)
    assert isinstance(record, BoltRecord)
    assert record.confidence is ConfidenceLevel.G1


def test_thread_record_requires_designation():
    with pytest.raises(ValidationError):
        ThreadRecord.model_validate({"id": "x"})


def test_compatibility_record_field_names_match_validator():
    # Must line up with
    # backend.library.validator.find_broken_compatibility defaults.
    record = CompatibilityRecord.model_validate(
        {"bolt_class": "8.8", "minimum_nut_class": "8", "confidence": 2}
    )
    assert record.bolt_class == "8.8"
    assert record.minimum_nut_class == "8"


def test_oem_record_requires_standard_reference_and_carries_no_data():
    record = OEMRecord.model_validate(
        {"oem_name": "Example OEM", "standard_reference": "FIAT-01391"}
    )
    assert record.standard_reference == "FIAT-01391"
    # No engineering value/unit fields exist on OEMRecord -- it only
    # references a backend.standards entry by name.
    assert not hasattr(record, "value")


def test_parse_typed_records_raises_on_first_invalid_record():
    with pytest.raises(ValidationError):
        parse_typed_records("thread library", [{"designation": "M8"}, {"id": "bad"}])


def test_find_schema_violations_reports_without_raising():
    violations = find_schema_violations(
        "thread library", [{"designation": "M8"}, {"id": "bad-no-designation"}]
    )
    assert violations == [] or len(violations) == 1
    # The second record is missing the required "designation" field.
    assert any("designation" in v for v in violations)


def test_find_schema_violations_empty_for_all_valid_records():
    violations = find_schema_violations(
        "compatibility library",
        [{"bolt_class": "8.8", "minimum_nut_class": "8"}],
    )
    assert violations == []
