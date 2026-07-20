"""Faz 2.4.0 tests: registry.py typed-record wiring.

Covers only the additive typed surface (LibraryMetadata as a frozen
Pydantic model, BaseLibrary.typed_records/find_schema_violations).
Does not migrate or load any real record set.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.library.models import BoltRecord, ConfidenceLevel
from backend.library.registry import BaseLibrary, LibraryMetadata


def _bolt_metadata(**overrides):
    defaults = dict(
        name="Bolt Library",
        organization="TorqPro",
        status="draft",
        supported_units=("mm", "N", "MPa"),
    )
    defaults.update(overrides)
    return LibraryMetadata(**defaults)


def test_library_metadata_is_frozen_pydantic_model():
    meta = _bolt_metadata()
    assert isinstance(meta, LibraryMetadata)
    with pytest.raises(ValidationError):
        meta.name = "Changed"  # type: ignore[misc]


def test_library_metadata_key_property_unchanged():
    meta = _bolt_metadata(name="  Bolt Library  ")
    assert meta.key == "bolt library"


def test_replace_records_keeps_record_count_in_sync():
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records([{"id": "a"}, {"id": "b"}])
    assert lib.metadata.record_count == 2
    assert isinstance(lib.metadata, LibraryMetadata)


def test_typed_records_parses_against_mapped_schema():
    lib = BaseLibrary(metadata=_bolt_metadata())
    lib.replace_records(
        [{"id": "BOLT-1", "designation": "M8", "confidence": 1}]
    )
    typed = lib.typed_records()
    assert len(typed) == 1
    assert isinstance(typed[0], BoltRecord)
    assert typed[0].confidence is ConfidenceLevel.G1


def test_typed_records_raises_on_invalid_record():
    lib = BaseLibrary(
        metadata=LibraryMetadata(name="Thread Library", organization="TorqPro")
    )
    lib.replace_records([{"id": "no-designation"}])
    with pytest.raises(ValidationError):
        lib.typed_records()


def test_find_schema_violations_reports_without_raising():
    lib = BaseLibrary(
        metadata=LibraryMetadata(name="Thread Library", organization="TorqPro")
    )
    lib.replace_records([{"id": "no-designation"}])
    violations = lib.find_schema_violations()
    assert len(violations) == 1
    assert "designation" in violations[0]


def test_find_schema_violations_empty_for_unregistered_library_key():
    # No domain schema is mapped for this key -> falls back to the
    # permissive LibraryRecordBase, which has no required fields.
    lib = BaseLibrary(metadata=_bolt_metadata(name="Unmapped Library"))
    lib.replace_records([{"id": "anything"}])
    assert lib.find_schema_violations() == []
