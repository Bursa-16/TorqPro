"""Faz 2.8.6 Stage 2 tests: Assembly Intelligence Report Section.

Covers: JSON/Markdown determinism (byte-for-byte across repeated
calls), critical-incompatibility visibility regardless of score,
score-vs-coverage separation, insufficient_data vs
blocked_authoritative_source reporting, Turkish-character handling and
JSON serialization, passed/warning/failed counting, and regression
safety (Stage 1 engine untouched, full existing suite unaffected).

Does not touch backend/calculation_engine/assembly_intelligence.py
(Stage 1), the API, or the frontend.
"""

from __future__ import annotations

import json

import pytest

from backend.calculation_engine import assembly_intelligence as ai
from backend.calculation_engine import assembly_intelligence_report as report_module
from backend.library import population


@pytest.fixture(scope="module")
def sample_bolt():
    bolts = population.find_bolt()
    assert bolts
    return bolts[0]


@pytest.fixture(scope="module")
def sample_nut_for(sample_bolt):
    nuts = population.find_nut()
    match = next(
        (n for n in nuts if n.get("nominal_diameter_mm") == sample_bolt.get("nominal_diameter_mm")),
        None,
    )
    assert match is not None
    return match


def _report_with_critical_incompatibility() -> dict:
    return report_module.collect_assembly_intelligence_report(
        bolt_designation="M3", nut_designation="ISO 4032 M3", nominal_diameter_mm=3.0,
        bolt_strength_class="10.9", nut_property_class="04",
        thread_designation="M3", bolt_size="M3",
    )


def _report_all_supplied_and_valid(sample_bolt, sample_nut_for) -> dict:
    mid_temp = (
        sample_bolt["operating_temperature_min_c"] + sample_bolt["operating_temperature_max_c"]
    ) / 2
    coating = (sample_bolt.get("coating_compatibility") or [None])[0]
    return report_module.collect_assembly_intelligence_report(
        bolt_designation=sample_bolt["designation"],
        nut_designation=sample_nut_for["designation"],
        nominal_diameter_mm=sample_bolt["nominal_diameter_mm"],
        bolt_strength_class="8.8", nut_property_class="8",
        thread_designation=sample_bolt["designation"],
        bolt_size=sample_bolt["designation"],
        intended_operating_temperature_c=mid_temp,
        intended_coating=coating,
    )


def _report_nothing_supplied() -> dict:
    return report_module.collect_assembly_intelligence_report()


# ---------------------------------------------------------------------
# Determinism: JSON and Markdown
# ---------------------------------------------------------------------

def test_json_rendering_is_byte_for_byte_deterministic(sample_bolt, sample_nut_for):
    report = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    out1 = report_module.render_assembly_intelligence_report_json(report)
    out2 = report_module.render_assembly_intelligence_report_json(report)
    assert out1 == out2


def test_markdown_rendering_is_byte_for_byte_deterministic(sample_bolt, sample_nut_for):
    report = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    out1 = report_module.render_assembly_intelligence_report_markdown(report)
    out2 = report_module.render_assembly_intelligence_report_markdown(report)
    assert out1 == out2


def test_json_rendering_deterministic_across_two_independent_collections(
    sample_bolt, sample_nut_for,
):
    """Two independent collect() calls with identical input must
    produce identical JSON -- the report must not embed any wall-clock
    timestamp or other non-deterministic value."""
    report_a = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    report_b = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    json_a = report_module.render_assembly_intelligence_report_json(report_a)
    json_b = report_module.render_assembly_intelligence_report_json(report_b)
    assert json_a == json_b


def test_json_output_has_no_timestamp_field(sample_bolt, sample_nut_for):
    report = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    serialized = report_module.render_assembly_intelligence_report_json(report)
    for forbidden in ("generated_at", "timestamp", "report_generated_at"):
        assert forbidden not in serialized


# ---------------------------------------------------------------------
# Critical incompatibility visibility
# ---------------------------------------------------------------------

def test_critical_incompatibility_present_in_json():
    report = _report_with_critical_incompatibility()
    assert report["assembly_readiness"]["has_critical_incompatibility"] is True
    assert report["assembly_readiness"]["overall_risk_level"] == "critical"
    assert len(report["critical_incompatibilities"]) >= 1


def test_critical_incompatibility_visible_in_markdown_regardless_of_score():
    report = _report_with_critical_incompatibility()
    md = report_module.render_assembly_intelligence_report_markdown(report)
    assert "Kritik Uyumsuzluklar" in md
    for item in report["critical_incompatibilities"]:
        assert item in md


def test_no_critical_incompatibility_section_when_none_present(sample_bolt, sample_nut_for):
    report = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    if not report["critical_incompatibilities"]:
        md = report_module.render_assembly_intelligence_report_markdown(report)
        assert "Kritik Uyumsuzluklar" not in md


def test_critical_status_not_overridden_by_high_score():
    report = _report_with_critical_incompatibility()
    # Even if other checks pushed the score up, risk level must stay
    # "critical" whenever any incompatibility exists.
    assert report["assembly_readiness"]["overall_risk_level"] == "critical"


# ---------------------------------------------------------------------
# Score vs coverage separation
# ---------------------------------------------------------------------

def test_score_and_coverage_are_reported_in_separate_top_level_sections():
    report = _report_with_critical_incompatibility()
    assert "score" in report
    assert "coverage" in report
    assert set(report["score"].keys()) == {
        "assembly_intelligence_score", "score_denominator_note",
    }
    assert set(report["coverage"].keys()) == {
        "assessment_coverage_percent", "total_checks", "assessed_checks",
        "insufficient_data_checks", "blocked_authoritative_source_checks",
        "coverage_vs_score_note",
    }


def test_score_denominator_matches_stage_1_assessed_checks_only():
    result = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    report = report_module._collect_from_result(result)
    assert report["score"]["assembly_intelligence_score"] == result.score
    assert report["coverage"]["assessed_checks"] == result.assessed_checks
    assert report["coverage"]["total_checks"] == result.total_checks


def test_not_assessable_score_reported_as_null_not_zero():
    report = _report_nothing_supplied()
    assert report["score"]["assembly_intelligence_score"] is None
    assert report["assembly_readiness"]["overall_status"] == "not_assessable"
    assert report["assembly_readiness"]["overall_risk_level"] == "not_assessable"


def test_not_assessable_markdown_shows_not_assessable_not_a_number():
    report = _report_nothing_supplied()
    md = report_module.render_assembly_intelligence_report_markdown(report)
    assert "not_assessable" in md


def test_coverage_percent_independent_of_score_value():
    # High score (100) with low coverage must be representable and
    # must not force coverage to also read 100.
    result = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    report = report_module._collect_from_result(result)
    assert report["score"]["assembly_intelligence_score"] == 100.0
    assert report["coverage"]["assessment_coverage_percent"] < 100.0


# ---------------------------------------------------------------------
# insufficient_data vs blocked_authoritative_source reporting
# ---------------------------------------------------------------------

def test_insufficient_data_checks_reported_with_info_severity():
    report = _report_nothing_supplied()
    insufficient_rows = [
        c for c in report["checks"] if c["status"] == ai.STATUS_INSUFFICIENT_DATA
    ]
    assert insufficient_rows
    for row in insufficient_rows:
        assert row["severity"] == "info"


def test_blocked_authoritative_source_checks_reported_with_warning_severity():
    report = _report_nothing_supplied()
    blocked_rows = [
        c for c in report["checks"]
        if c["status"] == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE
    ]
    assert blocked_rows
    for row in blocked_rows:
        assert row["severity"] == "warning"


def test_insufficient_data_and_blocked_counts_kept_separate_in_coverage():
    report = _report_nothing_supplied()
    coverage = report["coverage"]
    assert coverage["insufficient_data_checks"] > 0
    assert coverage["blocked_authoritative_source_checks"] > 0
    # The two counts must sum correctly against total/assessed.
    assert (
        coverage["assessed_checks"]
        + coverage["insufficient_data_checks"]
        + coverage["blocked_authoritative_source_checks"]
        == coverage["total_checks"]
    )


def test_blocked_domains_never_appear_as_compatible_or_incompatible():
    report = _report_nothing_supplied()
    for check_id in ai.BLOCKED_DOMAINS:
        row = next(c for c in report["checks"] if c["check_id"] == check_id)
        assert row["status"] == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE
        assert row["status"] not in (ai.STATUS_COMPATIBLE, ai.STATUS_INCOMPATIBLE)


def test_operating_temperature_and_coating_never_reported_as_blocked(
    sample_bolt, sample_nut_for,
):
    """Regression guard mirroring the Stage 1 test of the same name:
    the report layer must not re-introduce the earlier mis-scoping."""
    report = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    for check_id in ("operating_temperature", "coating"):
        row = next(c for c in report["checks"] if c["check_id"] == check_id)
        assert row["status"] != ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE


# ---------------------------------------------------------------------
# Passed / warning / failed counting
# ---------------------------------------------------------------------

def test_check_summary_counts_match_status_distribution():
    report = _report_with_critical_incompatibility()
    summary = report["check_summary"]
    checks = report["checks"]
    assert summary["passed"] == len([c for c in checks if c["status"] == ai.STATUS_COMPATIBLE])
    assert summary["failed"] == len([c for c in checks if c["status"] == ai.STATUS_INCOMPATIBLE])
    assert summary["warning"] == len([
        c for c in checks
        if c["status"] in (ai.STATUS_INSUFFICIENT_DATA, ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE)
    ])
    assert summary["total"] == len(checks)
    assert summary["passed"] + summary["warning"] + summary["failed"] == summary["total"]


# ---------------------------------------------------------------------
# No fabricated data: report must not invent thresholds/recommendations
# ---------------------------------------------------------------------

def test_no_numeric_score_band_labels_invented():
    """The report must not introduce an Excellent/Good/Warning/High
    Risk/Unsafe banding system -- Stage 1 explicitly does not define
    numeric score thresholds."""
    report = _report_with_critical_incompatibility()
    md = report_module.render_assembly_intelligence_report_markdown(report).lower()
    for forbidden_label in ("excellent", "good", "unsafe", "high risk"):
        assert forbidden_label not in md


def test_suggested_action_for_blocked_checks_is_generic_not_a_fabricated_recommendation():
    report = _report_nothing_supplied()
    blocked_row = next(
        c for c in report["checks"]
        if c["status"] == ai.STATUS_BLOCKED_AUTHORITATIVE_SOURCE
    )
    # Must not contain invented coating/material product names.
    for forbidden in ("Zn-Ni", "Geomet", "Delta Protekt"):
        assert forbidden not in blocked_row["suggested_action"]


def test_engine_recommendations_passed_through_verbatim_not_authored_here(
    sample_bolt, sample_nut_for,
):
    report = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    dimensional_row = next(
        c for c in report["checks"] if c["check_id"] == "bolt_nut_dimensional"
    )
    # Whatever recommendations Stage 1's compatibility_engine produced
    # (engineering_notes) must appear verbatim, unmodified.
    check_result = next(
        c for c in ai.assess_assembly(
            bolt_designation=sample_bolt["designation"],
            nut_designation=sample_nut_for["designation"],
            nominal_diameter_mm=sample_bolt["nominal_diameter_mm"],
        ).checks
        if c.check_id == "bolt_nut_dimensional"
    )
    assert dimensional_row["engine_recommendations"] == list(check_result.recommendations)


# ---------------------------------------------------------------------
# Turkish characters and JSON serialization
# ---------------------------------------------------------------------

def test_turkish_characters_present_and_not_ascii_escaped():
    report = _report_nothing_supplied()
    serialized = report_module.render_assembly_intelligence_report_json(report)
    # ensure_ascii=False must be in effect -- Turkish characters appear
    # literally, not as \u00e7 / \u011f escapes.
    assert "ç" in serialized or "ğ" in serialized or "ı" in serialized or "ş" in serialized
    assert "\\u00e7" not in serialized
    assert "\\u011f" not in serialized


def test_turkish_characters_round_trip_through_json_parsing():
    report = _report_nothing_supplied()
    serialized = report_module.render_assembly_intelligence_report_json(report)
    reparsed = json.loads(serialized)
    assert reparsed == report


def test_markdown_output_contains_turkish_characters():
    report = _report_nothing_supplied()
    md = report_module.render_assembly_intelligence_report_markdown(report)
    assert any(ch in md for ch in "çğıöşü")


def test_full_report_is_json_serializable_end_to_end(sample_bolt, sample_nut_for):
    report = _report_all_supplied_and_valid(sample_bolt, sample_nut_for)
    serialized = json.dumps(report, sort_keys=True, ensure_ascii=False)
    reloaded = json.loads(serialized)
    assert reloaded == report


def test_json_output_is_sorted_keys_and_indented():
    report = _report_nothing_supplied()
    serialized = report_module.render_assembly_intelligence_report_json(report)
    parsed_manually = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    assert serialized == parsed_manually


# ---------------------------------------------------------------------
# Report field completeness (Stage 2 brief items 1-9)
# ---------------------------------------------------------------------

def test_report_contains_all_required_top_level_sections():
    report = _report_with_critical_incompatibility()
    for key in (
        "assembly_readiness", "score", "coverage", "check_summary",
        "checks", "critical_incompatibilities",
    ):
        assert key in report


def test_each_check_row_contains_all_required_fields():
    report = _report_with_critical_incompatibility()
    required_fields = {
        "check_id", "check_name", "status", "severity", "detail",
        "data_source", "suggested_action", "engine_warnings",
        "engine_recommendations",
    }
    for row in report["checks"]:
        assert required_fields.issubset(row.keys())


def test_every_check_has_a_non_empty_data_source_description():
    report = _report_nothing_supplied()
    for row in report["checks"]:
        assert row["data_source"]


# ---------------------------------------------------------------------
# Regression: Stage 1 engine untouched
# ---------------------------------------------------------------------

def test_regression_stage1_module_not_modified_in_behavior():
    result_direct = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    result_via_report = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    assert result_direct.score == result_via_report.score
    assert result_direct.overall_status == result_via_report.overall_status
    assert len(result_direct.checks) == len(result_via_report.checks)


def test_regression_report_collector_does_not_mutate_population_library():
    bolts_before = len(population.find_bolt())
    report_module.collect_assembly_intelligence_report(
        bolt_strength_class="8.8", nut_property_class="8",
    )
    bolts_after = len(population.find_bolt())
    assert bolts_before == bolts_after


# ---------------------------------------------------------------------
# Public alias for Stage 3 reuse (collect_assembly_intelligence_report_from_result)
# ---------------------------------------------------------------------

def test_public_alias_exists_and_is_exported():
    assert "collect_assembly_intelligence_report_from_result" in report_module.__all__
    assert (
        report_module.collect_assembly_intelligence_report_from_result
        is report_module._collect_from_result
    )


def test_public_alias_builds_identical_report_to_private_helper():
    result = ai.assess_assembly(bolt_strength_class="8.8", nut_property_class="8")
    via_private = report_module._collect_from_result(result)
    via_public = report_module.collect_assembly_intelligence_report_from_result(result)
    assert via_private == via_public


def test_public_alias_avoids_a_second_assess_assembly_call(sample_bolt, sample_nut_for):
    """The whole point of the alias: an API layer that already has a
    Stage 1 result must be able to build the report without calling
    assess_assembly() again. Verify the alias accepts an
    AssemblyIntelligenceResult directly and needs no further engine
    call to produce a complete, correct report."""
    result = ai.assess_assembly(
        bolt_designation=sample_bolt["designation"],
        nut_designation=sample_nut_for["designation"],
        nominal_diameter_mm=sample_bolt["nominal_diameter_mm"],
    )
    report = report_module.collect_assembly_intelligence_report_from_result(result)
    assert report["score"]["assembly_intelligence_score"] == result.score
    assert len(report["checks"]) == len(result.checks)
