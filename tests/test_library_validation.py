"""Faz 2.4.1 tests: data-quality and typed-schema validation over the
population data files (structural checks via validator.py, schema
checks via models.py -- neither mutates a registered library).

Named ``test_library_validation.py`` (not ``test_validation.py``,
which already exists in this repo for the API validation endpoints)
to avoid a module-name collision under pytest's default rootdir
import mode.
"""

from __future__ import annotations

import pytest

from backend.library import population, validator
from backend.library.models import find_schema_violations


def test_validate_all_population_sources_reports_no_violations():
    report = population.validate_all_population_sources()
    for key, issues in report.items():
        assert issues == [], f"{key}: {issues}"


def test_validate_population_source_unknown_key_raises():
    with pytest.raises(KeyError):
        population.validate_population_source("gizmo library")


def test_no_duplicate_ids_within_any_domain():
    for key in population.POPULATION_SOURCES:
        records = population.load_population_records(key)
        assert validator.find_duplicate_ids(records) == [], key
    assert validator.find_duplicate_ids(population.oem_catalog()) == []


def test_every_domain_satisfies_its_typed_schema():
    for key in population.POPULATION_SOURCES:
        records = population.load_population_records(key)
        assert find_schema_violations(key, records) == [], key


def test_compatibility_records_reference_only_known_classes():
    rules = population.load_population_records("compatibility library")
    assert validator.find_broken_compatibility(rules) == []


def test_thread_designations_in_bolt_library_are_valid():
    bolts = population.load_population_records("bolt library")
    issues = validator.find_invalid_threads(bolts, thread_field="thread")
    assert issues == []
