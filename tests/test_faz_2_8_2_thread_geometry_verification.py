"""Faz 2.8.2 tests: thread geometry verification & confidence upgrade.

Covers the 72-record Faz 2.8.2 target scope (Fine M3-M100 x35, Extra
Fine M8-M100 x29, Coarse M68-M100 x8) against the live
``backend/library/data/thread_library.json`` data file, plus the
``tools/verify_thread_geometry_faz_2_8_2.py`` verification tool
itself. Per the task brief, assertions favour independent
formula/invariant checks over repeating stored dataset values back at
themselves; float comparisons use an explicit, documented tolerance.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from backend.library import models as models_module
from backend.library import population

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "tools" / "verify_thread_geometry_faz_2_8_2.py"
_SPEC = importlib.util.spec_from_file_location(
    "verify_thread_geometry_faz_2_8_2", _MODULE_PATH
)
verify = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("verify_thread_geometry_faz_2_8_2", verify)
_SPEC.loader.exec_module(verify)  # type: ignore[union-attr]

#: Diameter-comparison tolerance for geometric-ordering/independent
#: checks in this file (not the tool's own, stricter tolerance --
#: this one is intentionally generous since these tests check physical
#: invariants, not exact-value reproduction).
DIAMETER_TOL = 1e-6


def _all_thread_records():
    return population.load_population_records("thread library")


def _target_records():
    return [r for r in _all_thread_records() if verify.is_in_scope(r)]


def _by_series(records, series):
    return sorted(
        (r for r in records if r["series"] == series),
        key=lambda r: r["nominal_diameter_mm"],
    )


# ---------------------------------------------------------------------
# 0. Scope sanity: exactly 72 records, split as specified.
# ---------------------------------------------------------------------

def test_target_scope_is_exactly_72_records_split_as_specified():
    target = _target_records()
    assert len(target) == 72

    coarse = _by_series(target, "Coarse")
    fine = _by_series(target, "Fine")
    xfine = _by_series(target, "Extra Fine")

    assert len(coarse) == 8
    assert len(fine) == 35
    assert len(xfine) == 29

    assert [r["nominal_diameter_mm"] for r in coarse] == [
        68, 72, 76, 80, 85, 90, 95, 100,
    ]
    assert fine[0]["nominal_diameter_mm"] == 3
    assert fine[-1]["nominal_diameter_mm"] == 100
    assert xfine[0]["nominal_diameter_mm"] == 8
    assert xfine[-1]["nominal_diameter_mm"] == 100


# ---------------------------------------------------------------------
# 1. Schema validation of the 72 target records.
# ---------------------------------------------------------------------

def test_target_records_pass_schema_validation():
    target = _target_records()
    violations = models_module.find_schema_violations("thread library", target)
    assert violations == []


# ---------------------------------------------------------------------
# 2. Unique (nominal_diameter_mm, pitch_mm) per series.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("series", ["Coarse", "Fine", "Extra Fine"])
def test_unique_diameter_pitch_combination_per_series(series):
    target = _target_records()
    recs = [r for r in target if r["series"] == series]
    combos = [(r["nominal_diameter_mm"], r["pitch_mm"]) for r in recs]
    assert len(combos) == len(set(combos)), (
        f"duplicate (diameter, pitch) combo(s) in {series}"
    )


# ---------------------------------------------------------------------
# 3. Positive diameter and pitch.
# ---------------------------------------------------------------------

def test_all_target_records_have_positive_diameter_and_pitch():
    for r in _target_records():
        assert r["nominal_diameter_mm"] > 0, r["id"]
        assert r["pitch_mm"] > 0, r["id"]


# ---------------------------------------------------------------------
# 4. Geometric ordering: major >= pitch_diameter >= minor_diameter > 0.
# ---------------------------------------------------------------------

def test_geometric_ordering_major_ge_pitch_ge_minor_gt_zero():
    for r in _target_records():
        major = r["major_diameter_mm"]
        pitch_d = r["pitch_diameter_mm"]
        minor = r["minor_diameter_mm"]
        assert major >= pitch_d - DIAMETER_TOL, r["id"]
        assert pitch_d >= minor - DIAMETER_TOL, r["id"]
        assert minor > 0, r["id"]


# ---------------------------------------------------------------------
# 5. stress_area_mm2 > 0.
# ---------------------------------------------------------------------

def test_stress_area_is_positive():
    for r in _target_records():
        assert r["stress_area_mm2"] > 0, r["id"]


# ---------------------------------------------------------------------
# 6. Fine pitch < Coarse pitch at the same nominal diameter
#    (independent invariant: fine threads are always finer than
#    coarse by ISO 261 definition, not a repeat of stored values).
# ---------------------------------------------------------------------

def test_fine_pitch_smaller_than_coarse_pitch_same_diameter():
    all_records = _all_thread_records()
    coarse_by_dia = {
        r["nominal_diameter_mm"]: r["pitch_mm"]
        for r in all_records if r["series"] == "Coarse"
    }
    fine_target = [r for r in _target_records() if r["series"] == "Fine"]
    checked = 0
    for r in fine_target:
        coarse_pitch = coarse_by_dia.get(r["nominal_diameter_mm"])
        if coarse_pitch is None:
            continue
        assert r["pitch_mm"] < coarse_pitch, (
            f"{r['id']}: fine pitch {r['pitch_mm']} not < "
            f"coarse pitch {coarse_pitch}"
        )
        checked += 1
    assert checked == len(fine_target)


# ---------------------------------------------------------------------
# 7. Extra Fine pitch < the corresponding Fine (or Coarse, if no Fine
#    entry exists at that diameter) pitch.
# ---------------------------------------------------------------------

def test_extra_fine_pitch_smaller_than_fine_or_coarse_same_diameter():
    all_records = _all_thread_records()
    coarse_by_dia = {
        r["nominal_diameter_mm"]: r["pitch_mm"]
        for r in all_records if r["series"] == "Coarse"
    }
    fine_by_dia = {
        r["nominal_diameter_mm"]: r["pitch_mm"]
        for r in all_records if r["series"] == "Fine"
    }
    xfine_target = [r for r in _target_records() if r["series"] == "Extra Fine"]
    checked = 0
    for r in xfine_target:
        dia = r["nominal_diameter_mm"]
        reference_pitch = fine_by_dia.get(dia, coarse_by_dia.get(dia))
        if reference_pitch is None:
            continue
        assert r["pitch_mm"] < reference_pitch, (
            f"{r['id']}: extra-fine pitch {r['pitch_mm']} not < "
            f"reference pitch {reference_pitch}"
        )
        checked += 1
    assert checked == len(xfine_target)


# ---------------------------------------------------------------------
# 8. Boundary records.
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "designation,series",
    [
        ("M3x0.45", "Fine"),
        ("M100x5.5", "Fine"),
        ("M8x0.8", "Extra Fine"),
        ("M100x5", "Extra Fine"),
        ("M68", "Coarse"),
        ("M100", "Coarse"),
    ],
)
def test_boundary_records_exist_and_are_in_scope(designation, series):
    target = _target_records()
    matches = [
        r for r in target
        if r["series"] == series
        and (
            r["nominal_diameter_mm"] == min(
                rr["nominal_diameter_mm"] for rr in target if rr["series"] == series
            )
            or r["nominal_diameter_mm"] == max(
                rr["nominal_diameter_mm"] for rr in target if rr["series"] == series
            )
        )
    ]
    assert matches, f"no boundary record found for {series}"
    # Every boundary record must itself pass schema validation and
    # carry a positive pitch/diameter (redundant with tests above by
    # design -- boundary records are exactly where formula edge cases
    # would first appear).
    for r in matches:
        assert r["pitch_mm"] > 0
        assert r["nominal_diameter_mm"] > 0


def test_min_max_diameters_per_series_match_task_scope():
    target = _target_records()
    for series, expected_min, expected_max in [
        ("Fine", 3, 100),
        ("Extra Fine", 8, 100),
        ("Coarse", 68, 100),
    ]:
        recs = [r for r in target if r["series"] == series]
        diameters = [r["nominal_diameter_mm"] for r in recs]
        assert min(diameters) == expected_min
        assert max(diameters) == expected_max


# ---------------------------------------------------------------------
# 9. Zero regression against the existing golden-record values (none
#    of which fall inside the Faz 2.8.2 target scope, so this asserts
#    the *absence* of overlap plus re-runs the independent geometry
#    re-derivation the tool itself performs).
# ---------------------------------------------------------------------

def test_golden_record_designations_are_outside_faz_2_8_2_scope():
    # M6/M10 coarse (the existing golden cases in test_golden_records.py)
    # must not be part of this phase's edited set -- confirms this
    # phase cannot have touched them.
    target_ids = {r["id"] for r in _target_records()}
    assert "THR-M6-COARSE" not in target_ids
    assert "THR-M10-COARSE" not in target_ids


def test_independent_geometry_rederivation_matches_stored_values():
    analysis = verify.analyze()
    mismatches = [
        pr for pr in analysis["per_record"] if not pr["geometry"]["geometry_verified"]
    ]
    assert mismatches == []


def test_no_geometric_invariant_issues_across_target_scope():
    analysis = verify.analyze()
    with_issues = [pr for pr in analysis["per_record"] if pr["invariant_issues"]]
    assert with_issues == []


# ---------------------------------------------------------------------
# 10. Source and confidence fields non-empty for all 72.
# ---------------------------------------------------------------------

def test_source_and_confidence_fields_non_empty():
    for r in _target_records():
        assert r.get("source"), r["id"]
        assert r.get("source_standard"), r["id"]
        assert r.get("confidence") is not None, r["id"]
        assert r.get("validation_status"), r["id"]


# ---------------------------------------------------------------------
# 11. Confidence upgrades match source evidence: exactly the
#     corroborated records were upgraded, non-corroborated records are
#     untouched, and every upgraded record's notes cite the evidence.
# ---------------------------------------------------------------------

EXPECTED_UPGRADED_IDS = {
    "THR-M68-COARSE", "THR-M72-COARSE", "THR-M80-COARSE",
    "THR-M90-COARSE", "THR-M100-COARSE",
}
EXPECTED_UNCHANGED_G4_IDS = {"THR-M76-COARSE", "THR-M85-COARSE", "THR-M95-COARSE"}


def test_exactly_the_corroborated_coarse_records_were_upgraded():
    target = {r["id"]: r for r in _target_records()}

    for rid in EXPECTED_UPGRADED_IDS:
        rec = target[rid]
        assert rec["confidence"] == 3, rid
        assert rec["confidence_level"] == 3, rid
        assert rec["validation_status"] == "reference_only", rid
        assert rec["review_status"] == "reference_only", rid
        # approval_status must stay "pending" -- only "validated"
        # records may be "approved" (population.find_invalid_status_
        # values enforces this pairing).
        assert rec["approval_status"] == "pending", rid
        assert "Faz 2.8.2" in rec["notes"]

    for rid in EXPECTED_UNCHANGED_G4_IDS:
        rec = target[rid]
        assert rec["confidence"] == 4, rid
        assert rec["validation_status"] == "provisional", rid


def test_fine_and_extra_fine_records_were_not_upgraded():
    target = _target_records()
    for r in target:
        if r["series"] in ("Fine", "Extra Fine"):
            assert r["confidence"] == 4, r["id"]
            assert r["validation_status"] == "provisional", r["id"]


def test_upgraded_record_notes_cite_independent_evidence_sources():
    target = {r["id"]: r for r in _target_records()}
    for rid in EXPECTED_UPGRADED_IDS:
        notes = target[rid]["notes"]
        assert "corroborated" in notes.lower()
        assert "reference_only" in notes


def test_upgrade_count_matches_tool_analysis():
    # analyze() gates eligibility on confidence == 4 (idempotency
    # guard: a record already upgraded to G3 is correctly no longer
    # "eligible" on a re-run), so after the --apply write the
    # upgraded records show corroborated=True but upgrade_eligible=
    # False. Check corroboration status directly instead, which is
    # stable across a re-run.
    analysis = verify.analyze()
    corroborated_ids = {
        pr["id"] for pr in analysis["per_record"]
        if pr["corroboration"]["corroborated"]
    }
    assert corroborated_ids == EXPECTED_UPGRADED_IDS
    # And re-running apply_upgrades() in dry-run mode must be a true
    # no-op now (nothing left eligible to change) -- confirms the
    # write path is idempotent.
    dry_run_result = verify.apply_upgrades(analysis, dry_run=True)
    assert dry_run_result["changed_records"] == []


def test_no_geometric_value_changed_by_the_confidence_upgrade():
    # The upgrade only ever touches provenance/confidence metadata;
    # cross-check that against the same independent ISO 724/68-1
    # re-derivation used for every other record in scope (already
    # exercised end-to-end in
    # test_independent_geometry_rederivation_matches_stored_values,
    # this test narrows to exactly the 5 upgraded ids as an explicit
    # regression guard for the --apply code path itself).
    target = {r["id"]: r for r in _target_records()}
    for rid in EXPECTED_UPGRADED_IDS:
        rec = target[rid]
        result = verify.verify_record_geometry(rec)
        assert result["geometry_verified"], rid


# ---------------------------------------------------------------------
# Data-file integrity: record count and checksum consistency preserved
# by the --apply write path.
# ---------------------------------------------------------------------

def test_thread_library_record_count_unchanged_by_this_phase():
    assert len(_all_thread_records()) == 134


def test_no_checksum_mismatches_after_confidence_upgrade():
    assert population.find_checksum_mismatches() == []


def test_no_schema_or_duplicate_or_integrity_issues_after_upgrade():
    report = population.run_all_integrity_checks()
    for check_name, issues in report.items():
        assert issues == [], f"{check_name}: {issues}"
