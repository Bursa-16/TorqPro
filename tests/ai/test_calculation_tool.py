"""ADR-0017 Karar 5 -- backend.ai_gateway.tools.calculation_tool must
be a pure, salt-calling forwarder around
backend.calculation_engine.provider.Provider.calculate: it returns the
provider's CalculationResponse completely unmodified, and it never
catches/re-wraps any exception the provider raises.
"""

from __future__ import annotations

import pytest

from backend.ai_gateway.tools.calculation_tool import run_calculation
from backend.calculation_engine.exceptions import CalculationInputError
from backend.calculation_engine.provider import Provider
from backend.calculation_engine.request import CalculationRequest
from backend.calculation_engine.response import CalculationResponse, CalculationResult


class _FixedResultProvider(Provider):
    """Test-only Provider returning a fixed, easily-identified
    CalculationResponse -- stands in for VDI2230Provider without
    depending on real engineering formulas."""

    standard = "TEST-STANDARD"
    version = "0.0.1-test"

    def calculate(self, request: CalculationRequest) -> CalculationResponse:
        return CalculationResponse(
            standard=self.standard,
            provider_version=self.version,
            inputs=request.inputs,
            results=[
                CalculationResult(
                    value=123.456,
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


class _RaisingProvider(Provider):
    """Test-only Provider that always raises CalculationInputError,
    to prove calculation_tool does not swallow it."""

    standard = "TEST-STANDARD-RAISING"
    version = "0.0.1-test"

    def calculate(self, request: CalculationRequest) -> CalculationResponse:
        raise CalculationInputError("missing required input: preload_target_n")


def test_run_calculation_forwards_response_unmodified():
    provider = _FixedResultProvider()
    request = CalculationRequest(standard="TEST-STANDARD", inputs={"thread": "M10"})

    response = run_calculation(provider, request)

    assert response.standard == "TEST-STANDARD"
    assert response.provider_version == "0.0.1-test"
    assert len(response.results) == 1
    result = response.results[0]
    assert result.value == 123.456
    assert result.unit == "Nm"
    assert result.formula_id == "TEST-FORMULA-001"
    assert result.classification == "QUICK"
    assert result.validation_status == "APPROVED"


def test_run_calculation_does_not_mutate_inputs_echo():
    provider = _FixedResultProvider()
    inputs = {"thread": "M12", "property_class": "8.8"}
    request = CalculationRequest(standard="TEST-STANDARD", inputs=inputs)

    response = run_calculation(provider, request)

    assert response.inputs == inputs


def test_run_calculation_propagates_calculation_input_error_unchanged():
    provider = _RaisingProvider()
    request = CalculationRequest(standard="TEST-STANDARD-RAISING", inputs={})

    with pytest.raises(CalculationInputError, match="preload_target_n"):
        run_calculation(provider, request)
