"""Faz 2.4.1 tests: population.py's find_bolt/find_nut/find_material/
find_thread/find_coating/find_lubrication/list_strength_classes/
list_oems search API.

These read the population data files directly and never touch the
registry, so no setup/teardown of registered library state is needed.
"""

from __future__ import annotations

from backend.library import population


def test_find_thread_by_designation():
    results = population.find_thread(designation="M8")
    assert results
    assert all(r["designation"] == "M8" for r in results)


def test_find_thread_by_series():
    results = population.find_thread(series="Coarse")
    assert results
    assert all(r["series"] == "Coarse" for r in results)
    # M8 coarse should be exactly one record.
    m8 = [r for r in results if r["designation"] == "M8"]
    assert len(m8) == 1


def test_find_bolt_filters_by_diameter_and_head_type():
    results = population.find_bolt(diameter_mm=10, head_type="Hex")
    assert len(results) == 1
    assert results[0]["diameter_mm"] == 10
    assert results[0]["head_type"] == "Hex"


def test_find_bolt_no_filters_returns_everything():
    assert len(population.find_bolt()) == len(population.load_population_records("bolt library"))


def test_find_nut_filters_by_standard():
    results = population.find_nut(standard="ISO 4032")
    assert results
    assert all(r["source_standard"] == "ISO 4032" for r in results)


def test_find_nut_filters_by_diameter():
    results = population.find_nut(diameter_mm=12)
    assert results
    assert all(r["thread"].split("x")[0] == "M12" for r in results)


def test_find_material_case_insensitive_substring():
    results = population.find_material("STAINLESS")
    names = {r["material"] for r in results}
    assert "Stainless A2" in names
    assert "Stainless A4" in names


def test_find_coating_substring_match():
    results = population.find_coating("zn")
    names = {r["designation"] for r in results}
    assert "Zn" in names
    assert "ZnNi" in names


def test_find_lubrication_substring_match():
    results = population.find_lubrication("anti")
    names = {r["designation"] for r in results}
    assert "Anti Seize" in names


def test_list_strength_classes_category_filter():
    bolts = population.list_strength_classes("Bolt")
    nuts = population.list_strength_classes("Nut")
    assert {r["designation"] for r in bolts} == {
        "4.6", "4.8", "5.6", "5.8", "6.8", "8.8", "9.8", "10.9", "12.9",
    }
    assert {r["designation"] for r in nuts} == {"04", "05", "6", "8", "10", "12"}


def test_list_strength_classes_no_filter_returns_all():
    assert len(population.list_strength_classes()) == 15


def test_list_oems_returns_full_catalog():
    oems = population.list_oems()
    assert len(oems) == 18
    for name in ("FIAT", "VW", "BMW", "Toyota", "Tesla", "Cummins"):
        assert name in oems
