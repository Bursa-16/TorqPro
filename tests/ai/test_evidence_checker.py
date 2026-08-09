"""ADR-0017 Karar 9 (case 2) -- insufficient evidence is a normal,
non-error outcome; sufficient evidence requires at least one
EvidenceSource or a CalculationResponse.
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
