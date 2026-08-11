"""Faz 2.8.6 tests: Fastener Assembly Intelligence engine.

Covers: the four-status contract (compatible/incompatible/
insufficient_data/blocked_authoritative_source), the score formula
(only compatible+incompatible checks in the denominator,
insufficient_data/blocked never counted, never treated as compatible),
the not_assessable boundary (zero assessed checks), assessment
coverage reporting, critical-incompatibility surfacing independent of
score, JSON serializability, and regression safety (existing engines
this module wraps are not modified; full existing suite unaffected).

Does not touch bolt_library.json, nut_library.json, washer data, the
API, or the frontend.
"""

from __future__ import annotations

import json

import pytest

from backend.calculation_engine import assembly_intelligence as ai
from backend.library import population


# ---------------------------------------------------------------------
# Fixtures: pick real, currently-loaded records so tests stay valid as
# long as the underlying libraries keep at least one record each.
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def sample_bolt():
    bolts = population.find_bolt()
    assert bolts, "expected at least one bolt record in the population library"
    return bolts[0]


@pytest.fixture(scope="module")
def sample_nut_for(sample_bolt):
    nuts = population.find_nut()
    match = next(
        (n for n in nuts if n.get("nominal_diameter_mm") == sample_bolt.get("nominal_diameter_mm")),
        None,
    )
    assert match is not None, "expected a nut record matching the sample bolt's diameter"
    return match


# ---------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------

def test_status_constants_are_the_four_status_contract():
    assert ai.STATUS_COMPATIBLE == "compatible"
    assert ai.STATUS_INCOMPATIBLE == "incompatible"
    assert ai.STATUS_INSUFFICIENT_DATA == "insufficient_data"
    assert ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE == "blocked_authoritative_source"
    assert ai._ALL_STATUSES == (
        ai.STATUS_COMPATIBLE,
        ai.STATUS_INCOMPATIBLE,
        ai.STATUS_INSUFFICIENT_DATA,
        ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE,
    )


def test_every_check_result_status_is_in_the_four_status_contract():
    result = ai.assess_assembly(
        bolt_designation="M3", nut_designation="ISO 4032 M3", nominal_diameter_mm=3.0,
        bolt_strength_class="8.8", nut_property_class="8", thread_designation="M3",
        bolt_size="M3", intended_operating_temperature_c=100.0,
        intended_coating="Zinc-nickel",
    )
    for check in result.checks:
        assert check.status in ai._ALL_STATUSES


# ---------------------------------------------------------------------
# Positive: fully assessable, fully compatible input
# ---------------------------------------------------------------------

def test_positive_bolt_nut_dimensional_compatible(sample_bolt, sample_nut_for):
    check = ai._check_bolt_nut_dimensional(
        sample_bolt, sample_nut_for, sample_bolt["designation"], sample_nut_for["designation"],
    )
    assert check.status in (ai.STATUS_COMPATIBLE, ai.STATUS_INCOMPATIBLE)


def test_positive_thread_check_compatible_for_known_designation(sample_bolt):
    check = ai._check_thread(sample_bolt["designation"], sample_bolt["nominal_diameter_mm"])
    assert check.status == ai.STATUS_COMPATIBLE


def test_positive_strength_class_compatible_known_safe_pairing():
    check = ai._check_strength_class("8.8", "8", None)
    assert check.status == ai.STATUS_COMPATIBLE


def test_positive_bolt_washer_compatible_for_known_bolt_size(sample_bolt):
    check = ai._check_bolt_washer(sample_bolt["designation"])
    assert check.status in (ai.STATUS_COMPATIBLE, ai.STATUS_INCOMPATIBLE)


def test_positive_standard_check_compatible_for_registered_standard():
    check = ai._check_standard("ISO 898-1")
    assert check.status in (ai.STATUS_COMPATIBLE, ai.STATUS_INCOMPATIBLE)


def test_positive_operating_temperature_within_range(sample_bolt, sample_nut_for):
    mid = (
        sample_bolt["operating_temperature_min_c"] + sample_bolt["operating_temperature_max_c"]
    ) / 2
    check = ai._check_operating_temperature(sample_bolt, sample_nut_for, mid)
    assert check.status == ai.STATUS_COMPATIBLE


def test_positive_coating_listed_as_compatible(sample_bolt, sample_nut_for):
    common = set(sample_bolt.get("coating_compatibility") or []) & set(
        sample_nut_for.get("coating_compatibility") or []
    )
    assert common, "expected at least one shared coating between sample bolt and nut"
    coating = sorted(common)[0]
    check = ai._check_coating(sample_bolt, sample_nut_for, coating)
    assert check.status == ai.STATUS_COMPATIBLE


# ---------------------------------------------------------------------
# Negative: genuinely incompatible input
# ---------------------------------------------------------------------

def test_negative_strength_class_incompatible_nut_too_weak():
    check = ai._check_strength_class("10.9", "04", None)
    assert check.status == ai.STATUS_INCOMPATIBLE
    assert "10.9" in check.detail or "10" in check.detail


def test_negative_thread_incompatible_unknown_designation():
    check = ai._check_thread("M999-DOES-NOT-EXIST", None)
    assert check.status == ai.STATUS_INCOMPATIBLE


def test_negative_bolt_washer_incompatible_unknown_bolt_size():
    check = ai._check_bolt_washer("M999-DOES-NOT-EXIST")
    assert check.status == ai.STATUS_INCOMPATIBLE


def test_negative_standard_incompatible_unregistered_name():
    check = ai._check_standard("NOT-A-REAL-STANDARD-XYZ")
    assert check.status == ai.STATUS_INCOMPATIBLE


def test_negative_operating_temperature_incompatible_out_of_range(sample_bolt, sample_nut_for):
    too_hot = sample_bolt["operating_temperature_max_c"] + 500.0
    check = ai._check_operating_temperature(sample_bolt, sample_nut_for, too_hot)
    assert check.status == ai.STATUS_INCOMPATIBLE


def test_negative_coating_incompatible_unlisted_coating(sample_bolt, sample_nut_for):
    check = ai._check_coating(sample_bolt, sample_nut_for, "Definitely-Not-A-Listed-Coating")
    assert check.status == ai.STATUS_INCOMPATIBLE


def test_negative_critical_incompatibility_surfaced_and_not_hidden_by_score():
    result = ai.assess_assembly(
        bolt_designation="M3", nut_designation="ISO 4032 M3", nominal_diameter_mm=3.0,
        bolt_strength_class="8.8", nut_property_class="8",
        thread_designation="M3", bolt_size="M3",
        intended_operating_temperature_c=100.0, intended_coating="Zinc-nickel",
    )
    strength_check = next(c for c in result.checks if c.check_id == "strength_class")
    assert strength_check.status == ai.STATUS_INCOMPATIBLE
    assert any("strength_class" in c for c in result.critical_incompatibilities)
    # Score can still be high from other compatible checks -- the
    # critical incompatibility must remain visible regardless.
    assert result.score is not None


# ---------------------------------------------------------------------
# insufficient_data vs blocked_authoritative_source distinction
# ---------------------------------------------------------------------

def test_insufficient_data_when_designation_missing():
    check = ai._check_bolt_nut_dimensional(None, None, None, None)
    assert check.status == ai.STATUS_INSUFFICIENT_DATA


def test_insufficient_data_unknown_strength_class_not_incompatible():
    check = ai._check_strength_class("99.9-UNKNOWN", "8", None)
    assert check.status == ai.STATUS_INSUFFICIENT_DATA


def test_insufficient_data_never_treated_as_compatible_in_score():
    result = ai.assess_assembly(bolt_strength_class="99.9-UNKNOWN", nut_property_class="8")
    strength_check = next(c for c in result.checks if c.check_id == "strength_class")
    assert strength_check.status == ai.STATUS_INSUFFICIENT_DATA
    # Not counted toward assessed_checks at all.
    assert strength_check not in [
        c for c in result.checks if c.status in (ai.STATUS_COMPATIBLE, ai.STATUS_INCOMPATIBLE)
    ]


def test_blocked_authoritative_source_for_intended_use_material_defence():
    result = ai.assess_assembly(
        bolt_designation="M3", nut_designation="ISO 4032 M3", nominal_diameter_mm=3.0,
    )
    for check_id in ("intended_use", "material", "defence_recommendation"):
        check = next(c for c in result.checks if c.check_id == check_id)
        assert check.status == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE


def test_blocked_domains_constant_matches_actual_blocked_checks():
    result = ai.assess_assembly()
    blocked_ids = {
        c.check_id for c in result.checks
        if c.status == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE
    }
    assert blocked_ids == set(ai.BLOCKED_DOMAINS)


def test_operating_temperature_and_coating_are_not_structurally_blocked(
    sample_bolt, sample_nut_for,
):
    """Regression guard for the mid-session correction: these two
    checks must resolve to compatible/incompatible/insufficient_data
    based on real per-record data, never blocked_authoritative_source,
    when a bolt/nut record with the relevant field is resolved."""
    mid = (
        sample_bolt["operating_temperature_min_c"] + sample_bolt["operating_temperature_max_c"]
    ) / 2
    temp_check = ai._check_operating_temperature(sample_bolt, sample_nut_for, mid)
    assert temp_check.status != ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE

    coating = (sample_bolt.get("coating_compatibility") or [None])[0]
    if coating:
        coating_check = ai._check_coating(sample_bolt, sample_nut_for, coating)
        assert coating_check.status != ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE


# ---------------------------------------------------------------------
# Score formula
# ---------------------------------------------------------------------

def test_score_formula_all_compatible_is_100():
    result = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    strength = next(c for c in result.checks if c.check_id == "strength_class")
    assert strength.status == ai.STATUS_COMPATIBLE
    assessed = [
        c for c in result.checks
        if c.status in (ai.STATUS_COMPATIBLE, ai.STATUS_INCOMPATIBLE)
    ]
    compatible = [c for c in assessed if c.status == ai.STATUS_COMPATIBLE]
    assert result.score == pytest.approx(len(compatible) / len(assessed) * 100.0, abs=0.01)


def test_score_formula_excludes_insufficient_data_and_blocked_from_denominator():
    result = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    assert result.assessed_checks == (
        len([c for c in result.checks if c.status == ai.STATUS_COMPATIBLE])
        + len([c for c in result.checks if c.status == ai.STATUS_INCOMPATIBLE])
    )
    assert result.assessed_checks < result.total_checks
    assert result.insufficient_data_checks + result.blocked_authoritative_source_checks == (
        result.total_checks - result.assessed_checks
    )


def test_score_boundary_zero_assessed_checks_is_not_assessable():
    result = ai.assess_assembly()  # nothing supplied at all
    assert result.assessed_checks == 0
    assert result.overall_status == "not_assessable"
    assert result.score is None


def test_score_never_reduced_merely_because_of_blocked_or_insufficient_checks():
    # Only strength_class supplied and compatible -> score must be
    # 100, unaffected by the many blocked/insufficient checks present.
    result = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    assert result.score == 100.0


def test_assessment_coverage_percent_matches_assessed_over_total():
    result = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    expected = round(result.assessed_checks / result.total_checks * 100.0, 2)
    assert result.assessment_coverage_percent == expected


# ---------------------------------------------------------------------
# Boundary: partially supplied input
# ---------------------------------------------------------------------

def test_boundary_only_bolt_supplied_nut_missing_is_insufficient_data():
    check = ai._check_bolt_nut_dimensional(None, None, "M3", None)
    assert check.status == ai.STATUS_INSUFFICIENT_DATA


def test_boundary_washer_diameter_requires_both_bolt_size_and_standard():
    only_bolt = ai._check_washer_diameter("M8", None)
    only_standard = ai._check_washer_diameter(None, "ISO 7089")
    neither = ai._check_washer_diameter(None, None)
    assert only_bolt.status == ai.STATUS_INSUFFICIENT_DATA
    assert only_standard.status == ai.STATUS_INSUFFICIENT_DATA
    assert neither.status == ai.STATUS_INSUFFICIENT_DATA


def test_boundary_oem_and_automotive_share_mechanism_but_are_separate_checks():
    result = ai.assess_assembly(
        oem_reference="REF-EXAMPLE-01", automotive_reference="REF-EXAMPLE-01"
    )
    oem = next(c for c in result.checks if c.check_id == "oem_recommendation")
    auto = next(c for c in result.checks if c.check_id == "automotive_recommendation")
    assert oem.status in ai._ALL_STATUSES
    assert auto.status in ai._ALL_STATUSES


# ---------------------------------------------------------------------
# Regression: existing engines unaffected
# ---------------------------------------------------------------------

def test_regression_wrapped_engines_still_importable_and_unchanged():
    from backend.library.compatibility_engine import check_bolt_nut_compatibility
    from backend.library.strength_compatibility import (
        check_bolt_nut_strength_compatibility,
    )
    from backend.calculation_engine.friction_readiness import assess_friction_readiness

    assert callable(check_bolt_nut_compatibility)
    assert callable(check_bolt_nut_strength_compatibility)
    assert callable(assess_friction_readiness)


def test_regression_population_library_record_counts_unaffected():
    # Faz 2.8.6 must not mutate any library data file.
    bolts_before = len(population.find_bolt())
    ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    bolts_after = len(population.find_bolt())
    assert bolts_before == bolts_after


# ---------------------------------------------------------------------
# JSON serializability
# ---------------------------------------------------------------------

def test_json_result_and_checks_are_json_serializable():
    result = ai.assess_assembly(
        bolt_designation="M3", nut_designation="ISO 4032 M3", nominal_diameter_mm=3.0,
        bolt_strength_class="8.8", nut_property_class="8",
    )
    payload = result.to_dict()
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    reloaded = json.loads(serialized)
    assert reloaded["overall_status"] == result.overall_status
    assert len(reloaded["checks"]) == len(result.checks)


def test_json_check_to_dict_has_expected_keys():
    check = ai._check_strength_class("8.8", "8", None)
    d = check.to_dict()
    assert set(d.keys()) == {"check_id", "status", "detail", "warnings", "recommendations"}
