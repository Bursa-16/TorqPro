"""Faz v3.0.0-beta.1 (Torque Recommendation Engine) - engine-level
tests.

Pure-Python, no FastAPI/HTTP, no database -- exercises
``backend.torque_recommendation.engine.recommend_torque`` directly,
mirroring how ``tests/test_faz_2_8_7_joint_analysis.py`` exercises
``analyze_joint`` itself. HTTP/auth/audit coverage lives in
``tests/torque_recommendation/test_beta1_http_route.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.torque_recommendation.engine import recommend_torque
from backend.torque_recommendation.models import TorqueRecommendationRequest
from backend.vdi2230_core import CalculationDomainError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_SEGMENT = {"length_mm": 20, "modulus_mpa": 210000, "area_mm2": 200}


def _full_coverage_request(**overrides):
    base = dict(
        diameter_mm=10,
        pitch_mm=1.5,
        rp02_mpa=900,
        target_yield_ratio=0.5,
        max_utilization_ratio=0.9,
        mu_thread_nom=0.12,
        mu_bearing_nom=0.10,
        effective_bearing_diameter_mm=14,
        bolt_segments=[_SEGMENT],
        joint_segments=[_SEGMENT],
        minimum_required_clamp_load_n=1000,
        external_axial_load_n=500,
        fail_threshold=0.95,
        warn_threshold=0.80,
    )
    base.update(overrides)
    return TorqueRecommendationRequest(**base)


# ---------------------------------------------------------------------
# 1. Normal valid recommendation
# ---------------------------------------------------------------------


def test_normal_valid_recommendation_returns_recommended_status():
    result = recommend_torque(_full_coverage_request())
    assert result.status == "recommended"
    assert result.recommended_torque is not None
    assert result.recommended_torque > 0
    assert result.unit == "Nm"
    assert result.recommended_torque == result.calculated_torque


def test_normal_valid_recommendation_matches_analyze_joint_source_of_truth():
    """The recommendation value must be byte-identical to whatever
    analyze_joint itself computes -- never independently derived."""
    from backend.calculation_engine.joint_analysis import analyze_joint

    request = _full_coverage_request()
    result = recommend_torque(request)
    direct = analyze_joint(**request.to_analyze_joint_kwargs())
    assert result.recommended_torque == direct.calculated_values["recommended_torque_nm"]


# ---------------------------------------------------------------------
# 2. Missing inputs
# ---------------------------------------------------------------------


def test_missing_all_inputs_is_not_applicable_and_insufficient_data():
    result = recommend_torque(TorqueRecommendationRequest())
    assert result.status == "not_applicable"
    assert result.confidence == "NOT_APPLICABLE"
    assert result.recommended_torque is None
    assert result.readiness == "insufficient_data"


def test_missing_friction_inputs_only_lowers_readiness_not_an_error():
    request = _full_coverage_request(mu_thread_nom=None, mu_bearing_nom=None)
    result = recommend_torque(request)
    assert result.status == "not_applicable"
    assert result.recommended_torque is None
    assert "mu_thread_nom" not in result.explanation["input_drivers"]


# ---------------------------------------------------------------------
# 3. Invalid friction coefficient
# ---------------------------------------------------------------------


def test_invalid_friction_coefficient_rejected_by_pydantic_negative():
    with pytest.raises(Exception):
        _full_coverage_request(mu_thread_nom=-0.1)


def test_invalid_friction_coefficient_rejected_by_pydantic_above_one():
    with pytest.raises(Exception):
        _full_coverage_request(mu_bearing_nom=1.5)


# ---------------------------------------------------------------------
# 4. Unsupported input / domain
# ---------------------------------------------------------------------


def test_unsupported_thread_pitch_domain_raises_calculation_domain_error():
    # pitch_mm far too large relative to diameter_mm -> minor diameter
    # would be <= 0, exactly the domain rejection
    # vdi2230_core.tensile_stress_area_mm2 already documents.
    request = _full_coverage_request(diameter_mm=4, pitch_mm=5)
    with pytest.raises(CalculationDomainError):
        recommend_torque(request)


# ---------------------------------------------------------------------
# 5. Deterministic calculation failure
# ---------------------------------------------------------------------


def test_deterministic_calculation_failure_propagates_unchanged():
    """A domain failure from the wired core must propagate unchanged
    (never swallowed, never turned into a fabricated fallback
    recommendation)."""
    request = _full_coverage_request(diameter_mm=4, pitch_mm=5)
    with pytest.raises(CalculationDomainError) as excinfo:
        recommend_torque(request)
    assert "minor" in str(excinfo.value) or "diameter" in str(excinfo.value)


# ---------------------------------------------------------------------
# 6. Recommendation confidence classification
# ---------------------------------------------------------------------


def test_confidence_not_applicable_when_critical_findings_present():
    request = _full_coverage_request(external_axial_load_n=200000)
    result = recommend_torque(request)
    assert result.critical_findings
    assert result.status == "not_applicable"
    assert result.confidence == "NOT_APPLICABLE"
    assert result.recommended_torque is None
    # Transparency: the raw computed value is still exposed.
    assert result.calculated_torque is not None


def test_confidence_low_when_readiness_partial():
    request = _full_coverage_request(
        bolt_segments=None, joint_segments=None, minimum_required_clamp_load_n=None,
        max_utilization_ratio=None,
    )
    result = recommend_torque(request)
    assert result.readiness in ("partial", "torque_window_partial")
    assert result.status == "recommended"
    assert result.confidence == "LOW"


def test_confidence_medium_or_high_when_readiness_full():
    result = recommend_torque(_full_coverage_request())
    assert result.readiness == "full"
    assert result.status == "recommended"
    assert result.confidence in ("HIGH", "MEDIUM")


def test_confidence_is_only_ever_one_of_the_closed_vocabulary():
    from backend.torque_recommendation.models import CONFIDENCE_LEVELS

    for request in (
        TorqueRecommendationRequest(),
        _full_coverage_request(),
        _full_coverage_request(external_axial_load_n=200000),
    ):
        result = recommend_torque(request)
        assert result.confidence in CONFIDENCE_LEVELS


# ---------------------------------------------------------------------
# 7. Warnings / assumptions
# ---------------------------------------------------------------------


def test_assumptions_include_external_axial_load_default_when_omitted():
    request = _full_coverage_request(external_axial_load_n=None)
    result = recommend_torque(request)
    assert any("external_axial_load_n" in a for a in result.assumptions)


def test_assumptions_do_not_mention_default_when_axial_load_supplied():
    request = _full_coverage_request(external_axial_load_n=500)
    result = recommend_torque(request)
    assert not any("not supplied" in a for a in result.assumptions)


def test_warnings_and_assumptions_are_deterministic_across_repeated_calls():
    request = _full_coverage_request()
    first = recommend_torque(request)
    second = recommend_torque(request)
    assert first.warnings == second.warnings
    assert first.assumptions == second.assumptions
    assert first.explanation == second.explanation


# ---------------------------------------------------------------------
# 8. Deterministic output unchanged with AI enabled/disabled +
#    AI cannot override torque value + provider failure fallback
# ---------------------------------------------------------------------


def test_engine_module_never_imports_ai_gateway():
    """Static proof (mirrors tests/ai/test_dependency_direction.py's
    own AST-based technique): backend.torque_recommendation never
    imports backend.ai_gateway anywhere, so its output cannot depend
    on any AI provider's presence, availability, or behavior."""
    package_dir = REPO_ROOT / "backend" / "torque_recommendation"
    for py_file in sorted(package_dir.glob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("backend.ai_gateway"), py_file
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith("backend.ai_gateway"), py_file


def test_recommendation_output_identical_regardless_of_ai_gateway_state():
    """Deterministic operation must not depend on any AI provider --
    proven here simply by calling recommend_torque twice with no AI
    machinery touched at all in between, and getting identical
    results (a stronger, HTTP-independent version of the same
    guarantee tests/torque_recommendation/test_beta1_http_route.py
    checks at the API layer)."""
    request = _full_coverage_request()
    first = recommend_torque(request).to_dict()
    second = recommend_torque(request).to_dict()
    # trace_id is engine-level None either way (audit happens at the
    # HTTP layer, not here) -- excluded from comparison for clarity.
    first.pop("trace_id", None)
    second.pop("trace_id", None)
    assert first == second


def test_recommended_torque_identical_across_every_ai_gateway_provider_state():
    """Explicit, non-architectural proof (task requirement 9): the
    same deterministic inputs produce byte-identical
    ``recommended_torque`` regardless of whether an AI provider is
    enabled, unavailable, actively failing, or not configured at all.

    This is deliberately *not* a mock of ``recommend_torque`` itself
    -- it exercises the real ``backend.ai_gateway`` machinery (a
    package this test file, unlike ``backend.torque_recommendation``
    itself, is free to import) around an unmodified
    ``recommend_torque`` call, in four independent provider states:

    1. No provider touched at all ("not configured").
    2. A successful ``FakeModelClient.complete()`` call ("provider
       enabled").
    3. ``backend.api.routes.ai_gateway._UnavailableModelClient``
       (the real default runtime provider for POST /api/ai/query)
       raising its documented "unavailable" error ("provider
       unavailable").
    4. ``RaisingModelClient`` deliberately raising an arbitrary
       exception ("provider failure").

    Because ``backend.torque_recommendation`` never imports
    ``backend.ai_gateway`` at all (see
    test_engine_module_never_imports_ai_gateway above), this
    independence is architectural, not incidental -- there is no
    code path by which any of the four states below could reach
    ``recommend_torque``'s numeric output. This test proves that
    property empirically as well as statically.
    """
    from backend.ai_gateway.llm_client import (
        FakeModelClient,
        PromptContext,
        RaisingModelClient,
    )
    from backend.api.routes.ai_gateway import _UnavailableModelClient

    request = _full_coverage_request()
    prompt_context = PromptContext(query_text="torque recommendation context", language="en")

    def _current_recommendation():
        result = recommend_torque(request).to_dict()
        result.pop("trace_id", None)
        return result

    baseline = _current_recommendation()

    # 1. No provider configured at all -- the beta.1 default.
    assert _current_recommendation() == baseline

    # 2. Provider enabled and succeeding.
    fake_client = FakeModelClient(fixed_text="An AI explanation, never a torque value.")
    fake_client.complete(prompt_context)
    assert _current_recommendation() == baseline

    # 3. Provider unavailable (the real default runtime client).
    try:
        _UnavailableModelClient().complete(prompt_context)
    except Exception:
        pass
    assert _current_recommendation() == baseline

    # 4. Provider actively failing.
    raising_client = RaisingModelClient(RuntimeError("simulated provider failure"))
    try:
        raising_client.complete(prompt_context)
    except RuntimeError:
        pass
    assert _current_recommendation() == baseline


def test_provider_unavailable_never_prevents_deterministic_recommendation():
    """No provider is ever invoked by this engine in beta.1 -- a
    'provider failure' is therefore never even reachable, which is
    itself the fallback guarantee: recommend_torque succeeds using
    only backend.calculation_engine.joint_analysis.analyze_joint."""
    result = recommend_torque(_full_coverage_request())
    assert result.status == "recommended"
    assert result.recommended_torque is not None


# ---------------------------------------------------------------------
# Proprietary / OEM names not leaked
# ---------------------------------------------------------------------


def test_no_oem_standard_name_anywhere_in_a_recommendation_result():
    # Deliberately narrow to the repository's actual OEM-specific
    # standard modules (backend/standards/fiat.py,
    # backend/standards/oem.py) -- not the whole standards registry,
    # which also holds public, non-OEM standards (ISO/DIN/EN/
    # VDI 2230) already legitimately exposed via formula ids like
    # "VDI2230_AS" throughout this engine's own calculation_source.
    # Scope item 9 forbids OEM-specific names, not public standards.
    from backend.standards.fiat import FIAT_9_55823

    oem_terms = [FIAT_9_55823.name.lower(), FIAT_9_55823.key.lower()]
    result = recommend_torque(_full_coverage_request())
    haystack = str(result.to_dict()).lower()
    for term in oem_terms:
        assert term not in haystack, f"leaked OEM/standard term: {term}"


__all__: list = []
