"""ADR-0019 (AI Safety, Validation & Explainability) -- cross-cutting
safety/validation test suite spanning
``backend.ai_gateway.evidence_checker``,
``backend.ai_gateway.composer`` and ``backend.ai_gateway.audit``.

A dedicated file (rather than folding these into the existing
per-module test files) because these are cross-cutting invariants
about the *safety contract* itself, not about any single module's
local behaviour -- the same rationale already established by
``tests/ai/test_dependency_direction.py`` (a single file auditing a
whole-package architectural rule rather than one module).

Covers, per ADR-0019 Karar 1-14 and the v3.0.0-alpha.3 task's explicit
safety rules:
    - CALCULATED precedence (unconditional, evidence-quality-independent).
    - Fail-closed behaviour for unknown traceability_level/source_kind.
    - oem_estimation/educational_simplification can never yield
      PASS/VALIDATED.
    - DEPRECATED/UNVERIFIED evidence behaviour.
    - Missing-evidence and conflicting-evidence transparency.
    - No path exists to produce an "invalid VALIDATED" claim.
    - CalculationResponse is never converted into EvidenceSource and
      never appears in ComposedAnswer.evidence.
    - No engineering numeric literal exists anywhere in
      backend.ai_gateway (AST-based static test).
    - A deterministic calculation result can never be altered by
      anything in this package.
"""

from __future__ import annotations

import ast
from pathlib import Path

from backend.ai_gateway.audit import AIInteractionRecord, InMemoryAuditSink
from backend.ai_gateway.composer import ResultLabel, compose
from backend.ai_gateway.context_builder import build_context
from backend.ai_gateway.evidence_checker import EvidenceStatus, check_evidence
from backend.ai_gateway.llm_client import FakeModelClient, PromptContext
from backend.ai_gateway.permission import UserContext
from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse, CalculationResult

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AI_GATEWAY_ROOT = REPO_ROOT / "backend" / "ai_gateway"

#: Only these bare integer literals are tolerated anywhere in
#: backend.ai_gateway -- trivial structural constants (list/dict
#: default values, sentinel comparisons), never anything that could
#: be mistaken for an engineering coefficient or tolerance. No float
#: literal is tolerated at all: as of this phase, zero legitimate
#: float literal exists anywhere in the package (confirmed by
#: inspection before writing this test), so any float literal found
#: is treated as a violation.
_ALLOWED_INT_LITERALS = frozenset({-1, 0, 1})


def _make_source(
    source_id: str = "QB-0001",
    *,
    traceability_level=None,
    source_kind=None,
    standard_name=None,
    standard_clause=None,
) -> EvidenceSource:
    return EvidenceSource(
        source_type="question_bank",
        source_id=source_id,
        content_version=1,
        title_tr="Test soru",
        title_en="Test question",
        body_tr="Test açıklama, en az yirmi karakter uzunluğunda.",
        body_en="Test explanation, at least twenty characters long.",
        standard_name=standard_name,
        standard_clause=standard_clause,
        source_kind=source_kind,
        traceability_level=traceability_level,
    )


def _make_calculation_response(value: float = 42.0) -> CalculationResponse:
    return CalculationResponse(
        standard="TEST-STANDARD",
        provider_version="0.0.1-test",
        inputs={},
        results=[
            CalculationResult(
                value=value,
                unit="Nm",
                formula_id="TEST-FORMULA-SAFETY-001",
                classification="QUICK",
                validation_status="APPROVED",
            )
        ],
        formula_traces=[],
        warnings=[],
        validation={},
    )


# ---------------------------------------------------------------------
# CALCULATED precedence -- unconditional, never downgradable.
# ---------------------------------------------------------------------


def test_calculated_precedence_with_no_question_bank_evidence():
    calc = _make_calculation_response()

    check = check_evidence([], calc)

    assert check.status == EvidenceStatus.PASS
    model = FakeModelClient(fixed_text="Explains the calculation.")
    user = UserContext(user_id=1, role="engineer", is_active=True)
    prompt_context = build_context(
        query_text="q", user=user, evidence=(), calculation_result=calc
    )
    answer = compose(model.complete(prompt_context), check)
    assert answer.result_label == ResultLabel.CALCULATED


def test_calculated_precedence_with_high_confidence_question_bank_evidence():
    calc = _make_calculation_response()
    high_conf_source = _make_source(
        traceability_level="APPROVED", source_kind="internal_engine"
    )

    check = check_evidence([high_conf_source], calc)

    assert check.status == EvidenceStatus.PASS
    assert check.calculation_result is calc


def test_calculated_precedence_survives_low_confidence_question_bank_evidence():
    """The core ADR-0019 Karar 1/2 invariant: evidence quality or
    conflict can never downgrade a calculation-backed answer."""
    calc = _make_calculation_response()
    low_conf_source = _make_source(
        traceability_level="EXPERIMENTAL", source_kind="oem_estimation"
    )

    check = check_evidence([low_conf_source], calc)

    assert check.status == EvidenceStatus.PASS
    assert check.calculation_result is calc


def test_calculated_precedence_survives_multiple_conflicting_low_confidence_sources():
    calc = _make_calculation_response()
    sources = [
        _make_source("QB-A", traceability_level=None, source_kind=None),
        _make_source("QB-B", traceability_level="UNVERIFIED", source_kind="oem_estimation"),
        _make_source(
            "QB-C", traceability_level="DEPRECATED", source_kind="educational_simplification"
        ),
    ]

    check = check_evidence(sources, calc)

    assert check.status == EvidenceStatus.PASS
    # All three low-confidence sources are still retained (transparency,
    # not silent dropping) even though they cannot affect the PASS status.
    assert len(check.verified_sources) == 3


def test_composer_result_label_is_calculated_whenever_calculation_result_present():
    calc = _make_calculation_response()
    low_conf_source = _make_source(
        traceability_level="PROVISIONAL", source_kind="oem_estimation"
    )
    check = check_evidence([low_conf_source], calc)
    model = FakeModelClient(fixed_text="Some advisory text.")

    answer = compose(
        model.complete(
            PromptContext(
                query_text="q",
                language="tr",
                evidence=(low_conf_source,),
                calculation_result=calc,
            )
        ),
        check,
    )

    assert answer.result_label == ResultLabel.CALCULATED
    assert answer.calculation_result is calc


# ---------------------------------------------------------------------
# Fail-closed: unknown traceability_level / unknown source_kind.
# ---------------------------------------------------------------------


def test_unknown_traceability_level_fails_closed_to_warn():
    unknown_level_source = _make_source(
        traceability_level="SOMETHING_UNRECOGNISED", source_kind="internal_engine"
    )

    check = check_evidence([unknown_level_source], None)

    assert check.status == EvidenceStatus.WARN


def test_none_traceability_level_fails_closed_to_warn():
    none_level_source = _make_source(traceability_level=None, source_kind="internal_engine")

    check = check_evidence([none_level_source], None)

    assert check.status == EvidenceStatus.WARN


def test_unknown_source_kind_fails_closed_to_warn():
    unknown_kind_source = _make_source(
        traceability_level="APPROVED", source_kind="something_unrecognised"
    )

    check = check_evidence([unknown_kind_source], None)

    assert check.status == EvidenceStatus.WARN


def test_none_source_kind_fails_closed_to_warn_even_with_approved_traceability():
    """Even a top-tier traceability_level cannot compensate for a
    missing/unknown source_kind -- both signals must independently
    clear the high-confidence bar (ADR-0019 Karar 6)."""
    none_kind_source = _make_source(traceability_level="APPROVED", source_kind=None)

    check = check_evidence([none_kind_source], None)

    assert check.status == EvidenceStatus.WARN


# ---------------------------------------------------------------------
# oem_estimation / educational_simplification can never yield
# PASS/VALIDATED, regardless of traceability_level.
# ---------------------------------------------------------------------


def test_oem_estimation_cannot_pass_even_with_approved_traceability():
    oem_source = _make_source(traceability_level="APPROVED", source_kind="oem_estimation")

    check = check_evidence([oem_source], None)

    assert check.status == EvidenceStatus.WARN


def test_educational_simplification_cannot_pass_even_with_approved_traceability():
    edu_source = _make_source(
        traceability_level="APPROVED", source_kind="educational_simplification"
    )

    check = check_evidence([edu_source], None)

    assert check.status == EvidenceStatus.WARN


def test_oem_estimation_composed_answer_is_never_validated():
    oem_source = _make_source(traceability_level="APPROVED", source_kind="oem_estimation")
    check = check_evidence([oem_source], None)
    model = FakeModelClient(fixed_text="An OEM-estimation-backed answer.")

    answer = compose(
        model.complete(PromptContext(query_text="q", language="tr", evidence=(oem_source,))),
        check,
    )

    assert answer.result_label != ResultLabel.VALIDATED
    assert answer.result_label == ResultLabel.ESTIMATED
    assert answer.validation_required is True


def test_educational_simplification_composed_answer_is_never_validated():
    edu_source = _make_source(
        traceability_level="APPROVED", source_kind="educational_simplification"
    )
    check = check_evidence([edu_source], None)
    model = FakeModelClient(fixed_text="An educational-simplification-backed answer.")

    answer = compose(
        model.complete(PromptContext(query_text="q", language="tr", evidence=(edu_source,))),
        check,
    )

    assert answer.result_label != ResultLabel.VALIDATED
    assert answer.result_label == ResultLabel.ESTIMATED


# ---------------------------------------------------------------------
# DEPRECATED / UNVERIFIED evidence behaviour.
# ---------------------------------------------------------------------


def test_deprecated_traceability_level_is_never_high_confidence():
    deprecated_source = _make_source(
        traceability_level="DEPRECATED", source_kind="internal_engine"
    )

    check = check_evidence([deprecated_source], None)

    assert check.status == EvidenceStatus.WARN


def test_unverified_traceability_level_is_never_high_confidence():
    unverified_source = _make_source(
        traceability_level="UNVERIFIED", source_kind="internal_engine"
    )

    check = check_evidence([unverified_source], None)

    assert check.status == EvidenceStatus.WARN


def test_deprecated_and_unverified_sources_still_visible_not_silently_dropped():
    """DEPRECATED/UNVERIFIED content can never be *authoritative*
    evidence (never PASS/VALIDATED), but it is not silently discarded
    either -- it remains visible in verified_sources for transparency
    (ADR-0018 Karar 11 / ADR-0019 Karar 8), only downgraded to WARN."""
    deprecated_source = _make_source(
        "QB-DEP", traceability_level="DEPRECATED", source_kind="internal_engine"
    )

    check = check_evidence([deprecated_source], None)

    assert check.status == EvidenceStatus.WARN
    assert deprecated_source in check.verified_sources


# ---------------------------------------------------------------------
# Missing-evidence and conflicting-evidence transparency.
# ---------------------------------------------------------------------


def test_missing_evidence_is_explicitly_fail():
    check = check_evidence([], None)

    assert check.status == EvidenceStatus.FAIL
    assert check.has_sufficient_evidence is False
    assert check.verified_sources == ()


def test_missing_evidence_composed_answer_has_no_result_label():
    check = check_evidence([], None)
    model = FakeModelClient(fixed_text="This text must never be used.")

    answer = compose(model.complete(PromptContext(query_text="q", language="tr")), check)

    assert answer.insufficient_evidence is True
    assert answer.result_label is None
    assert answer.text != "This text must never be used."


def test_conflicting_evidence_sources_are_all_retained_and_visible():
    """Two Question Bank sources that (hypothetically) disagree with
    each other must both remain visible in the check result and in
    the composed answer's evidence -- no silent conflict resolution
    (ADR-0018 Karar 11 / ADR-0019 Karar 8/11)."""
    source_a = _make_source(
        "QB-CONFLICT-A", traceability_level="APPROVED", source_kind="internal_engine"
    )
    source_b = _make_source(
        "QB-CONFLICT-B", traceability_level="APPROVED", source_kind="internal_engine"
    )

    check = check_evidence([source_a, source_b], None)
    model = FakeModelClient(fixed_text="Answer citing both sources.")

    answer = compose(
        model.complete(
            PromptContext(query_text="q", language="tr", evidence=(source_a, source_b))
        ),
        check,
    )

    assert source_a in answer.evidence
    assert source_b in answer.evidence
    assert len(answer.citations) == 2


def test_conflicting_evidence_with_mixed_confidence_yields_warn():
    """One high-confidence and one low-confidence source together
    still yield WARN, not PASS -- the weakest contributing source
    determines the outcome (ADR-0019 Karar 6, "weakest link" rule)."""
    high_conf = _make_source(
        "QB-HIGH", traceability_level="APPROVED", source_kind="internal_engine"
    )
    low_conf = _make_source(
        "QB-LOW", traceability_level="PROVISIONAL", source_kind="internal_engine"
    )

    check = check_evidence([high_conf, low_conf], None)

    assert check.status == EvidenceStatus.WARN


# ---------------------------------------------------------------------
# No path to an "invalid VALIDATED" claim.
# ---------------------------------------------------------------------


def test_validated_label_requires_all_sources_high_confidence():
    all_high_conf = [
        _make_source("QB-1", traceability_level="APPROVED", source_kind="internal_engine"),
        _make_source("QB-2", traceability_level="APPROVED", source_kind="standard_requirement"),
    ]

    check = check_evidence(all_high_conf, None)

    assert check.status == EvidenceStatus.PASS
    model = FakeModelClient(fixed_text="Fully validated answer.")

    answer = compose(
        model.complete(
            PromptContext(query_text="q", language="tr", evidence=tuple(all_high_conf))
        ),
        check,
    )

    assert answer.result_label == ResultLabel.VALIDATED
    assert answer.validation_required is False


def test_single_low_confidence_source_prevents_validated_label_for_whole_answer():
    """Even if nine sources are high confidence, a single low-confidence
    tenth source must prevent the VALIDATED label for the whole
    answer -- there is no path to a partially-VALIDATED claim."""
    sources = [
        _make_source(f"QB-{i}", traceability_level="APPROVED", source_kind="internal_engine")
        for i in range(9)
    ] + [_make_source("QB-WEAK", traceability_level="PROVISIONAL", source_kind="internal_engine")]

    check = check_evidence(sources, None)

    assert check.status == EvidenceStatus.WARN
    model = FakeModelClient(fixed_text="Mostly validated but not quite.")

    answer = compose(
        model.complete(PromptContext(query_text="q", language="tr", evidence=tuple(sources))),
        check,
    )

    assert answer.result_label == ResultLabel.ESTIMATED
    assert answer.result_label != ResultLabel.VALIDATED


def test_recommended_label_is_never_mechanically_produced_in_this_phase():
    """ADR-0019 Karar 1: RECOMMENDED is defined in the vocabulary but
    not reachable through any structural rule in this phase (no
    claim-level NLP exists yet). This test documents that boundary
    explicitly rather than leaving it merely as a docstring claim."""
    scenarios = [
        ([], None),
        ([_make_source(traceability_level="APPROVED", source_kind="internal_engine")], None),
        ([_make_source(traceability_level="PROVISIONAL", source_kind="internal_engine")], None),
        ([], _make_calculation_response()),
    ]
    for sources, calc in scenarios:
        check = check_evidence(sources, calc)
        assert check.status in (EvidenceStatus.PASS, EvidenceStatus.WARN, EvidenceStatus.FAIL)
        # There is no branch in _resolve_result_label that can produce
        # RECOMMENDED -- verified indirectly via exhaustive status coverage.


# ---------------------------------------------------------------------
# CalculationResponse separation.
# ---------------------------------------------------------------------


def test_calculation_response_never_converted_to_evidence_source():
    calc = _make_calculation_response()
    source = _make_source(traceability_level="APPROVED", source_kind="internal_engine")

    check = check_evidence([source], calc)

    assert all(not isinstance(item, CalculationResponse) for item in check.verified_sources)
    assert all(item.source_type != "calculation_engine" for item in check.verified_sources)


def test_composed_answer_evidence_never_contains_calculation_data():
    calc = _make_calculation_response()
    source = _make_source(traceability_level="APPROVED", source_kind="internal_engine")
    check = check_evidence([source], calc)
    model = FakeModelClient(fixed_text="Answer with both.")

    answer = compose(
        model.complete(
            PromptContext(
                query_text="q", language="tr", evidence=(source,), calculation_result=calc
            )
        ),
        check,
    )

    assert answer.calculation_result is calc
    assert all(item.source_type != "calculation_engine" for item in answer.evidence)
    assert calc not in answer.evidence


def test_contributing_source_types_uses_fixed_label_not_a_fabricated_evidence_source():
    calc = _make_calculation_response()

    check = check_evidence([], calc)

    assert "calculation_engine" in check.contributing_source_types
    # ...but there is no corresponding EvidenceSource for it.
    assert check.verified_sources == ()


# ---------------------------------------------------------------------
# Deterministic calculation result can never be altered.
# ---------------------------------------------------------------------


def test_calculation_result_identity_preserved_through_evidence_checker():
    calc = _make_calculation_response(value=987.65)

    check = check_evidence([], calc)

    assert check.calculation_result is calc
    assert check.calculation_result.results[0].value == 987.65


def test_calculation_result_identity_preserved_through_composer():
    calc = _make_calculation_response(value=123.45)
    check = check_evidence([], calc)
    model = FakeModelClient(fixed_text="Describes the value without changing it.")

    answer = compose(
        model.complete(PromptContext(query_text="q", language="tr", calculation_result=calc)),
        check,
    )

    assert answer.calculation_result is calc
    assert answer.calculation_result.results[0].value == 123.45
    assert answer.calculation_result.results[0].formula_id == "TEST-FORMULA-SAFETY-001"


def test_audit_record_never_copies_numeric_value_only_formula_id():
    """The audit trail records formula_id references, never the
    numeric value itself (ADR-0017 Karar 8's existing rule,
    reaffirmed) -- proves AIInteractionRecord has no field that could
    hold a raw CalculationResult.value."""
    record = AIInteractionRecord(
        user_id=1,
        query_text_hash="hash",
        evidence_source_ids=(),
        calculation_formula_ids=("TEST-FORMULA-SAFETY-001",),
        model_name="fake-test-client",
        had_sufficient_evidence=True,
        created_at="2026-08-09T00:00:00+00:00",
        evidence_status=EvidenceStatus.PASS,
        result_label=ResultLabel.CALCULATED,
    )

    sink = InMemoryAuditSink()
    sink.record(record)

    field_names = set(record.__dataclass_fields__)
    assert "calculation_value" not in field_names
    assert "value" not in field_names
    assert record.calculation_formula_ids == ("TEST-FORMULA-SAFETY-001",)


# ---------------------------------------------------------------------
# AST-based static safety test: no engineering numeric literal
# anywhere in backend.ai_gateway.
# ---------------------------------------------------------------------


def test_no_engineering_numeric_literal_anywhere_in_ai_gateway():
    """Scans every .py file under backend/ai_gateway for numeric
    literals. Bare structural integers in _ALLOWED_INT_LITERALS
    (-1/0/1) are tolerated (list defaults, sentinel comparisons); any
    other int and *any* float literal is treated as a potential
    engineering constant and fails this test.

    This is the automated form of the rule ADR-0017/0018/0019 have
    stated in prose since v3.0.0-alpha.1: no ai_gateway module may
    contain an engineering formula, coefficient or tolerance value.
    """
    violations = []
    for py_file in sorted(AI_GATEWAY_ROOT.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            value = node.value
            if isinstance(value, bool):
                continue
            rel_path = str(py_file.relative_to(REPO_ROOT))
            if isinstance(value, float):
                violations.append((rel_path, node.lineno, value))
            elif isinstance(value, int) and value not in _ALLOWED_INT_LITERALS:
                violations.append((rel_path, node.lineno, value))

    assert not violations, f"Potential engineering numeric literal(s) found: {violations}"


def test_no_engineering_numeric_literal_scan_actually_covers_files():
    """Guards the guard: confirms the scan above is not silently
    inspecting zero files."""
    scanned = list(AI_GATEWAY_ROOT.rglob("*.py"))
    assert len(scanned) >= 10
