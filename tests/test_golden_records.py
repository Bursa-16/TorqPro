"""Faz 2.4.1 golden-record tests.

Cross-checks a curated set of records against known, independently
verifiable engineering reference values (not just "does a record
exist" -- the actual numbers). Every assertion here is a value the
author is confident is correct from standard fastener-engineering
references (ISO 724 formula results are textbook-reproducible; the
ISO 4032/ISO 7089/ISO 898-1 values are common, widely-published
standard-table entries). Nothing here is guessed or extrapolated --
see docs/phase-2.4.1-engineering-database-population.md for the data
gaps that are intentionally left ``provisional``/``reference_only``
instead of being asserted here.
"""

from __future__ import annotations

from backend.library import population


def test_golden_m6_coarse_thread():
    rec = population.find_thread(designation="M6", series="Coarse")[0]
    assert rec["pitch_mm"] == 1.0
    # ISO 724 base-profile formulas on d=6, P=1.0.
    assert rec["pitch_diameter_mm"] == 5.3505
    assert rec["minor_diameter_mm"] == 4.9175
    # Widely-published ISO 898-1 tensile stress area for M6 is 20.1 mm^2.
    assert round(rec["stress_area_mm2"], 1) == 20.1
    assert rec["validation_status"] == "validated"
    assert rec["approval_status"] == "approved"
    assert rec["source_standard"] == "ISO 724 / ISO 261"


def test_golden_m10_coarse_thread():
    rec = population.find_thread(designation="M10", series="Coarse")[0]
    assert rec["pitch_mm"] == 1.5
    assert rec["pitch_diameter_mm"] == 9.0258
    assert rec["minor_diameter_mm"] == 8.3763
    # Widely-published ISO 898-1 tensile stress area for M10 is 58.0 mm^2.
    assert round(rec["stress_area_mm2"], 1) == 58.0
    assert rec["validation_status"] == "validated"
    assert rec["approval_status"] == "approved"


def test_golden_m10_fine_thread_pitch_and_geometry():
    rec = population.find_thread(designation="M10x1.25", series="Fine")[0]
    assert rec["pitch_mm"] == 1.25
    # Widely-published stress area for M10x1.25 fine thread is
    # ~61.2 mm^2 -- geometry itself (ISO 724 formula) is sound, but
    # the *pitch selection* is programmatic, not looked up from the
    # ISO 261/262 fine-pitch table, so this record stays provisional.
    assert round(rec["stress_area_mm2"], 1) == 61.2
    assert rec["validation_status"] == "provisional"
    assert rec["approval_status"] == "pending"


def test_golden_iso4032_m10_nut():
    rec = population.find_nut(diameter_mm=10, standard="ISO 4032")[0]
    # Standard ISO 4032 style-1 hex nut, M10: width across flats 16 mm,
    # height 8.4 mm (independently verifiable standard-table values).
    assert rec["width_across_flats_mm"] == 16
    assert rec["height_mm"] == 8.4
    assert rec["validation_status"] == "validated"
    assert rec["approval_status"] == "approved"


def test_golden_iso7089_m10_washer():
    records = population.load_population_records("washer library")
    rec = next(r for r in records if r["id"] == "WASH-ISO7089-M10")
    # Standard ISO 7089 plain washer, M10: ID 10.5 mm, OD 20 mm,
    # thickness 2.0 mm.
    assert rec["inner_diameter_mm"] == 10.5
    assert rec["outer_diameter_mm"] == 20.0
    assert rec["thickness_mm"] == 2.0
    assert rec["validation_status"] == "validated"
    assert rec["approval_status"] == "approved"


def test_golden_strength_classes_8_8_10_9_12_9():
    by_class = {r["designation"]: r for r in population.list_strength_classes("Bolt")}
    assert by_class["8.8"]["rp02_mpa"] == 660
    assert by_class["8.8"]["rm_mpa"] == 830
    assert by_class["10.9"]["rp02_mpa"] == 940
    assert by_class["10.9"]["rm_mpa"] == 1040
    assert by_class["12.9"]["rp02_mpa"] == 1100
    assert by_class["12.9"]["rm_mpa"] == 1220
    for cls in ("8.8", "10.9", "12.9"):
        assert by_class[cls]["validation_status"] == "validated"
        assert by_class[cls]["approval_status"] == "approved"


def test_bolt_head_geometry_is_honestly_graded_not_validated():
    # Bolt records mix a verified field (width across flats) with
    # ratio-estimated ones (head height, hole sizes, weight, ...).
    # The record-level status must reflect the weakest field: never
    # "validated"/"approved" for the whole record, and the exact
    # verified/estimated split must be documented in metadata.
    rec = population.find_bolt(diameter_mm=10, head_type="Hex")[0]
    assert rec["validation_status"] == "reference_only"
    assert rec["approval_status"] == "pending"
    assert "head_across_flats_mm" in rec["metadata"]["verified_fields"]
    assert "head_height_mm" in rec["metadata"]["estimated_fields"]
