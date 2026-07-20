"""Faz 2.4.0 tests: validator.validate_schema() bridge."""

from __future__ import annotations

from backend.library.registry import BaseLibrary, LibraryMetadata
from backend.library.validator import validate_schema


def _thread_library() -> BaseLibrary:
    return BaseLibrary(
        metadata=LibraryMetadata(name="Thread Library", organization="TorqPro")
    )


def test_validate_schema_reports_schema_violation_code():
    lib = _thread_library()
    lib.replace_records([{"id": "no-designation"}])

    report = validate_schema(lib)

    assert not report.is_valid
    assert report.count_by_code() == {"schema_violation": 1}


def test_validate_schema_valid_for_conforming_records():
    lib = _thread_library()
    lib.replace_records([{"id": "T1", "designation": "M8"}])

    report = validate_schema(lib)

    assert report.is_valid
    assert report.issues == []


def test_validate_schema_is_independent_from_validate_library():
    # A record can pass the Phase 1.4 structural checks
    # (validate_library) while still failing the Faz 2.4.0 typed
    # schema, and vice versa -- the two are separate, non-overlapping
    # checks over the same raw records.
    lib = _thread_library()
    lib.replace_records([{"id": "no-designation"}])

    schema_report = validate_schema(lib)
    assert not schema_report.is_valid
