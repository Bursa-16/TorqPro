"""Faz v3.0.0-beta.2 (Engineering Reasoning Engine) unit tests --
``backend.ai_gateway.reasoning.wording`` (the optional, AI-generated
explanation layer -- structurally separate from ``engine.py``).
"""

from __future__ import annotations

from backend.ai_gateway.llm_client import FakeModelClient, RaisingModelClient
from backend.ai_gateway.permission import UserContext
from backend.ai_gateway.reasoning import engine, wording
from backend.ai_gateway.reasoning.evidence_adapter import to_calculation_response

_TRACE_ENTRY = {
    "formula_id": "VDI2230_PRELOAD",
    "symbol": "F_M",
    "unit": "N",
    "classification": "QUICK",
    "validation_status": "PROVISIONAL",
}

_USER = UserContext(user_id=1, role="engineer", is_active=True)


def _supported_record():
    return {
        "request_json": {"diameter_mm": 10},
        "result_json": {
            "status": "recommended",
            "confidence": "HIGH",
            "readiness": "full",
            "recommended_torque": 12.5,
            "unit": "Nm",
            "calculated_torque": 12.5,
            "preload_n": 5000,
            "allowable_range": {"min_nm": 10.0, "max_nm": 15.0},
            "coverage_percent": 100.0,
            "critical_findings": [],
            "warnings": [],
            "assumptions": [],
            "calculation_source": [_TRACE_ENTRY],
            "explanation": {"limitations": []},
        },
    }


def _supported_reasoning_result():
    return engine.run_reasoning(1, _supported_record(), user=_USER)


def test_no_attempt_when_model_client_is_none():
    result = _supported_reasoning_result()
    text, provider = wording.attempt_ai_explanation(
        result, calculation_response=None, model_client=None, user=_USER
    )
    assert text is None
    assert provider is None


def test_no_attempt_for_insufficient_evidence_state():
    insufficient = engine.run_reasoning(1, None, user=_USER)
    fake = FakeModelClient()
    text, provider = wording.attempt_ai_explanation(
        insufficient, calculation_response=None, model_client=fake, user=_USER
    )
    assert text is None
    assert provider is None
    assert fake.calls == []  # never invoked


def test_successful_wording_returns_text_and_provider_name():
    result = _supported_reasoning_result()
    calc_response = to_calculation_response(_supported_record())
    fake = FakeModelClient(fixed_text="Reasoning explained in plain language.")

    text, provider = wording.attempt_ai_explanation(
        result, calculation_response=calc_response, model_client=fake, user=_USER
    )

    assert text == "Reasoning explained in plain language."
    assert provider == fake.name
    assert len(fake.calls) == 1


def test_provider_failure_returns_none_none_never_raises():
    """Provider independence / provider-failure requirement: a raising
    AIModelClient must never propagate an exception out of this
    function."""
    result = _supported_reasoning_result()
    calc_response = to_calculation_response(_supported_record())
    raising = RaisingModelClient(RuntimeError("simulated provider outage"))

    text, provider = wording.attempt_ai_explanation(
        result, calculation_response=calc_response, model_client=raising, user=_USER
    )

    assert text is None
    assert provider is None


def test_wording_never_alters_calculation_response_object():
    result = _supported_reasoning_result()
    calc_response = to_calculation_response(_supported_record())
    before = calc_response.results[0]
    fake = FakeModelClient()

    wording.attempt_ai_explanation(
        result, calculation_response=calc_response, model_client=fake, user=_USER
    )

    after = calc_response.results[0]
    assert before == after  # unchanged (frozen dataclass, but assert anyway)


__all__: list = []
