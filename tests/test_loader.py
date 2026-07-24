"""Faz 2.4.1 tests: population.py's lazy JSON reading over
backend/library/data/*.json.

Distinct from tests/test_library_loader_typed.py (Faz 2.4.0, generic
LibraryLoader.load_typed on a temp file): this file covers the
Faz 2.4.1-specific reading of the real, shipped engineering database
files.
"""

from __future__ import annotations

import os

import pytest

from backend.library import population


def setup_function(_fn):
    population.clear_cache()


def test_load_population_records_unknown_key_raises_key_error():
    with pytest.raises(KeyError):
        population.load_population_records("gizmo library")


def test_all_nine_data_files_load_without_error():
    # Faz 2.4.1C adds "joint hardware library" as a tenth, currently
    # empty data source (shell only -- see
    # backend/library/joint_hardware_library.py). Faz 2.6.2A added
    # "friction condition library" as an eleventh, empty at the time;
    # Faz 2.6.2B populated it with 18 deterministically-sourced
    # records (see
    # backend/library/friction_condition_library.py,
    # tools/generate_faz_2_6_2b_friction_condition_records.py) -- it
    # is no longer in the empty-by-design set.
    empty_by_design = {"joint hardware library"}
    for key in population.POPULATION_SOURCES:
        records = population.load_population_records(key)
        assert isinstance(records, list)
        if key in empty_by_design:
            assert records == []
        else:
            assert records


def test_oem_catalog_loads_without_error():
    records = population.oem_catalog()
    assert isinstance(records, list)
    assert records


def test_load_population_records_is_cached_and_returns_copies():
    first = population.load_population_records("bolt library")
    first.append({"injected": True})
    second = population.load_population_records("bolt library")
    assert {"injected": True} not in second


def test_clear_cache_forces_a_fresh_read():
    population.load_population_records("nut library")
    assert "nut library" in population._FILE_CACHE
    population.clear_cache()
    assert "nut library" not in population._FILE_CACHE
    # A subsequent call re-populates the cache from disk.
    population.load_population_records("nut library")
    assert "nut library" in population._FILE_CACHE


def test_data_files_exist_under_backend_library_data():
    for filename in population.POPULATION_SOURCES.values():
        path = os.path.join(population.DATA_DIR, filename)
        assert os.path.isfile(path), f"missing data file: {path}"
    assert os.path.isfile(os.path.join(population.DATA_DIR, population.OEM_SOURCE))


def test_data_files_are_never_written_by_population_reads():
    paths = [
        os.path.join(population.DATA_DIR, filename)
        for filename in population.POPULATION_SOURCES.values()
    ]
    before = {path: os.path.getmtime(path) for path in paths}

    population.clear_cache()
    for key in population.POPULATION_SOURCES:
        population.load_population_records(key)
    population.total_population_record_count()

    after = {path: os.path.getmtime(path) for path in paths}
    assert before == after
