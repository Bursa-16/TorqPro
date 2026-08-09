"""ADR-0017 Karar 9 (case 2) -- insufficient evidence is a normal,
non-error outcome; sufficient evidence requires at least one
EvidenceSource or a CalculationResponse.

Also covers ADR-0018 Karar 9 (contributing_source_types) and Karar 11
(conflicting evidence is never silently dropped or preferred -- every
source passed in is retained unfiltered).
"""

from __future__ import annotations

from backend.ai_gateway.evidence_checker import check_evidence
from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse, CalculationResult


def _make_source(source_id: str = "QB-0001") -> EvidenceSource:
    return EvidenceSource(
        source_type="question_bank",
        source_id=source_id,
        content_version=1,
        title_tr="Test soru",
        title_en="Test question",
        body_tr="Test açıklama, en az yirmi karakter.",
        body_en="Test explanation, at least twenty characters.",
    )


def _make_calculation_response() -> CalculationResponse:
    return CalculationResponse(
        standard="TEST-STANDARD",
        provider_version="0.0.1-test",
        inputs={},
        results=[
            CalculationResult(
                value=42.0,
                unit="Nm",
                formula_id="TEST-FORMULA-001",
                classification="QUICK",
                validation_status="APPROVED",
            )
        ],
        formula_traces=[],
        warnings=[],
        validation={},
    )


def test_no_sources_and_no_calculation_is_insufficient():
    result = check_evidence([], None)

    assert result.has_sufficient_evidence is False
    assert result.verified_sources == ()
    assert result.calculation_result is None
    assert "no_retrieval_sources_or_calculation_result" in result.notes


def test_sources_only_is_sufficient():
    sources = [_make_source()]

    result = check_evidence(sources, None)

    assert result.has_sufficient_evidence is True
    assert result.verified_sources == tuple(sources)
    assert result.calculation_result is None
    assert result.notes == ()


def test_calculation_only_is_sufficient():
    calc = _make_calculation_response()

    result = check_evidence([], calc)

    assert result.has_sufficient_evidence is True
    assert result.verified_sources == ()
    assert result.calculation_result is calc
    assert result.notes == ()


def test_sources_and_calculation_are_both_carried_through_unmodified():
    sources = [_make_source("QB-0001"), _make_source("QB-0002")]
    calc = _make_calculation_response()

    result = check_evidence(sources, calc)

    assert result.has_sufficient_evidence is True
    assert result.verified_sources == tuple(sources)
    assert result.calculation_result is calc
    # Numeric value is untouched -- evidence_checker never inspects it.
    assert result.calculation_result.results[0].value == 42.0


# ---------------------------------------------------------------------
# ADR-0018 Karar 9 -- contributing_source_types.
# ---------------------------------------------------------------------


def test_contributing_source_types_empty_when_insufficient():
    result = check_evidence([], None)

    assert result.contributing_source_types == frozenset()


def test_contributing_source_types_includes_question_bank_only():
    result = check_evidence([_make_source()], None)

    assert result.contributing_source_types == frozenset({"question_bank"})


def test_contributing_source_types_includes_calculation_engine_only():
    result = check_evidence([], _make_calculation_response())

    assert result.contributing_source_types == frozenset({"calculation_engine"})


def test_contributing_source_types_includes_both_when_both_present():
    result = check_evidence([_make_source()], _make_calculation_response())

    assert result.contributing_source_types == frozenset({"question_bank", "calculation_engine"})


def test_contributing_source_types_deduplicates_same_source_type():
    sources = [_make_source("QB-0001"), _make_source("QB-0002"), _make_source("QB-0003")]

    result = check_evidence(sources, None)

    assert result.contributing_source_types == frozenset({"question_bank"})
    # All three sources are still individually retained -- dedup only
    # applies to the *type* summary, never to verified_sources itself.
    assert len(result.verified_sources) == 3


# ---------------------------------------------------------------------
# ADR-0018 Karar 11 -- conflicting evidence is never silently dropped
# or preferred; every source passed in survives unfiltered.
# ---------------------------------------------------------------------


def _make_conflicting_source(source_id: str, body_en: str) -> EvidenceSource:
    return EvidenceSource(
        source_type="question_bank",
        source_id=source_id,
        content_version=1,
        title_tr="Çelişen kaynak testi",
        title_en="Conflicting source test",
        body_tr="Çelişen içerikli açıklama metni burada, yirmi karakterden uzun.",
        body_en=body_en,
    )


def test_conflicting_sources_are_all_retained_not_deduplicated_or_chosen_between():
    """Two Question Bank sources that (hypothetically) disagree with
    each other must both survive check_evidence unfiltered -- this
    module never picks a 'winner' among conflicting sources (ADR-0018
    Karar 11)."""
    source_a = _make_conflicting_source(
        "QB-CONFLICT-A", "Explanation stating the torque value is 45 Nm."
    )
    source_b = _make_conflicting_source(
        "QB-CONFLICT-B", "Explanation stating the torque value is 50 Nm."
    )

    result = check_evidence([source_a, source_b], None)

    assert result.has_sufficient_evidence is True
    assert source_a in result.verified_sources
    assert source_b in result.verified_sources
    assert len(result.verified_sources) == 2


def test_calculation_result_survives_alongside_conflicting_question_bank_sources():
    """Per ADR-0018 Karar 11, the deterministic calculation result is
    never displaced by Question Bank sources, even when several are
    present at once -- it is always retained alongside them."""
    source_a = _make_conflicting_source("QB-CONFLICT-C", "One version of the explanation.")
    source_b = _make_conflicting_source("QB-CONFLICT-D", "A different version of it.")
    calc = _make_calculation_response()

    result = check_evidence([source_a, source_b], calc)

    assert result.calculation_result is calc
    assert len(result.verified_sources) == 2
