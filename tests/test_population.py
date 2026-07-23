"""Faz 2.4.1 tests: backend/library/population.py population engine.

Covers the explicit, opt-in population pipeline (data file -> typed
records -> registry) and the "OEM Library stays adapter-only" rule.
Tests that mutate a *shared, registered* library always restore its
original empty state in a ``finally`` block, mirroring the existing
convention in ``tests/test_library_migration.py``, so this file's own
tests -- and every other test that assumes a fresh registry -- stay
green regardless of collection order.
"""

from __future__ import annotations

from backend.library import population
from backend.library.oem_library import OEM_LIBRARY
from backend.library.registry import BaseLibrary, LibraryMetadata, get_library


def test_population_sources_cover_nine_domains():
    # Faz 2.4.1C adds "joint hardware library" as a tenth mapped
    # source (currently empty -- shell only, see
    # backend/library/joint_hardware_library.py). Faz 2.6.2A adds
    # "friction condition library" as an eleventh (also currently
    # empty -- shell only, see
    # backend/library/friction_condition_library.py). The original
    # nine domains are unchanged.
    expected = {
        "bolt library",
        "nut library",
        "washer library",
        "thread library",
        "material library",
        "coating library",
        "lubrication library",
        "strength class library",
        "compatibility library",
        "joint hardware library",
        "friction condition library",
    }
    assert set(population.POPULATION_SOURCES.keys()) == expected
    # OEM stays adapter-only: never gets a population source mapping.
    assert "oem library" not in population.POPULATION_SOURCES


def test_total_population_record_count_exceeds_500():
    assert population.total_population_record_count() > 500


def test_record_distribution_covers_every_domain_with_real_records():
    # "joint hardware library" and "friction condition library" are
    # intentional exceptions (Faz 2.4.1C / Faz 2.6.2A shells, no
    # verified data yet -- see backend/library/joint_hardware_library.py
    # and backend/library/friction_condition_library.py).
    empty_by_design = {"joint hardware library", "friction condition library"}
    for key in population.POPULATION_SOURCES:
        records = population.load_population_records(key)
        if key in empty_by_design:
            assert records == []
            continue
        assert len(records) > 0, f"{key} has no records"
    assert len(population.oem_catalog()) > 0


def test_populate_library_applies_records_and_restores_state():
    lib = get_library("Bolt Library")
    assert lib.records == []
    try:
        count = population.populate_library(lib)
        assert count > 0
        assert len(lib.records) == count
        assert lib.metadata.record_count == count
    finally:
        lib.replace_records([])
    assert lib.records == []
    assert lib.metadata.record_count == 0


def test_populate_all_populates_every_mapped_library_and_restores_state():
    touched = [get_library(key) for key in population.POPULATION_SOURCES]
    for lib in touched:
        assert lib.records == []
    try:
        results = population.populate_all()
        assert set(results.keys()) == {lib.metadata.name for lib in touched}
        assert sum(results.values()) > 500
        for lib in touched:
            assert lib.metadata.record_count == len(lib.records)
            if lib.metadata.key in ("joint hardware library", "friction condition library"):
                assert lib.records == []
            else:
                assert lib.records != []
    finally:
        for lib in touched:
            lib.replace_records([])
    for lib in touched:
        assert lib.records == []


def test_populate_all_with_explicit_isolated_libraries_does_not_touch_registry():
    fresh = [
        BaseLibrary(metadata=LibraryMetadata(name=name, organization="TorqPro"))
        for name in [
            "Bolt Library", "Nut Library", "Washer Library", "Thread Library",
            "Material Library", "Coating Library", "Lubrication Library",
            "Strength Class Library", "Compatibility Library",
        ]
    ]
    results = population.populate_all(libraries=fresh)
    assert sum(results.values()) > 500
    for lib in fresh:
        assert lib.records != []
    # The real, registered libraries were never touched.
    for lib in fresh:
        registered = get_library(lib.metadata.name)
        assert registered is not lib
        assert registered.records == []


def test_populate_library_raises_for_oem_library():
    import pytest

    with pytest.raises(KeyError):
        population.populate_library(OEM_LIBRARY)


def test_oem_library_never_receives_population_records():
    # OEM_LIBRARY must remain adapter-only even after populate_all()
    # runs for every other library.
    touched = [get_library(key) for key in population.POPULATION_SOURCES]
    try:
        population.populate_all()
        assert OEM_LIBRARY.records == []
        assert OEM_LIBRARY.metadata.record_count == 0
    finally:
        for lib in touched:
            lib.replace_records([])
