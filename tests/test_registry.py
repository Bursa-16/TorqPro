"""Faz 2.4.1 tests: registry effects of population.populate_library /
populate_all -- record_count sync, isolation between fresh instances
and the real registry, and typed-schema conformance once populated.

Uses fresh, unregistered BaseLibrary instances wherever possible so
these tests never depend on -- or leak into -- the shared global
registry; the two tests that do touch the real registry restore it in
a ``finally`` block (see tests/test_population.py for the established
convention).
"""

from __future__ import annotations

from backend.library import population
from backend.library.registry import BaseLibrary, LibraryMetadata, get_library


def _fresh(name: str) -> BaseLibrary:
    return BaseLibrary(metadata=LibraryMetadata(name=name, organization="TorqPro"))


def test_populate_library_keeps_record_count_in_sync_on_fresh_instance():
    lib = _fresh("Thread Library")
    assert lib.metadata.record_count == 0
    count = population.populate_library(lib)
    assert lib.metadata.record_count == count == len(lib.records)


def test_populated_fresh_library_typed_records_parse_cleanly():
    lib = _fresh("Bolt Library")
    population.populate_library(lib)
    typed = lib.typed_records()
    assert len(typed) == len(lib.records)
    assert lib.find_schema_violations() == []


def test_populated_fresh_library_is_isolated_from_registry():
    registered = get_library("Bolt Library")
    assert registered.records == []
    lib = _fresh("Bolt Library")
    population.populate_library(lib)
    assert lib.records != []
    assert registered.records == []


def test_registry_libraries_remain_empty_before_any_explicit_population():
    # Mirrors test_library_migration.test_migration_never_runs_automatically:
    # merely importing backend.library.population must not populate
    # anything.
    for key in population.POPULATION_SOURCES:
        lib = get_library(key)
        assert lib.records == []
        assert lib.metadata.record_count == 0


def test_populate_all_on_real_registry_round_trips_cleanly():
    touched = [get_library(key) for key in population.POPULATION_SOURCES]
    try:
        results = population.populate_all()
        for lib in touched:
            assert lib.metadata.record_count == results[lib.metadata.name]
    finally:
        for lib in touched:
            lib.replace_records([])
    for lib in touched:
        assert lib.metadata.record_count == 0
