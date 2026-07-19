"""Prerequisite-layer sanity tests for backend.calculation_engine.

Covers only the scaffolding contract itself (request/response
dataclasses, base Provider, exception hierarchy, empty formula
registry). No engineering formula or calculation-provider behaviour
is exercised here -- see tests/test_vdi2230_provider.py for that.
"""

from __future__ import annotations

import pytest

from backend import calculation_engine
from backend.calculation_engine import (
    CalculationEngineError,
    CalculationInputError,
    CalculationNotImplementedError,
    CalculationRequest,
    CalculationResponse,
    CalculationResult,
    FormulaRegistryEntry,
    Provider,
    ProviderNotFoundError,
    all_formulas,
    get_formula,
    register_formula,
)


def test_package_exports_expected_public_api():
    expected = {
        "CalculationEngineError",
        "CalculationInputError",
        "CalculationNotImplementedError",
        "ProviderNotFoundError",
        "CalculationRequest",
        "CalculationResult",
        "CalculationResponse",
        "Provider",
        "FormulaRegistryEntry",
        "register_formula",
        "get_formula",
        "all_formulas",
    }
    assert set(calculation_engine.__all__) == expected


def test_providers_subpackage_is_empty_by_design():
    from backend.calculation_engine import providers

    assert providers.__all__ == []


def test_calculation_request_defaults():
    request = CalculationRequest(standard="VDI2230", inputs={"a": 1})
    assert request.limit_mpa is None
    assert request.fail_threshold is None
    assert request.warn_threshold is None
    assert request.metadata == {}


def test_calculation_response_construction():
    response = CalculationResponse(
        standard="VDI2230",
        provider_version="0.0.0",
        inputs={},
        results=[
            CalculationResult(
                value=1.0,
                unit="mm^2",
                formula_id="X",
                classification="QUICK",
                validation_status="PROVISIONAL",
            )
        ],
        formula_traces=[],
    )
    assert response.warnings == []
    assert response.validation == {}
    assert response.results[0].value == 1.0


def test_provider_is_abstract():
    with pytest.raises(TypeError):
        Provider()  # type: ignore[abstract]


def test_exception_hierarchy():
    assert issubclass(CalculationInputError, CalculationEngineError)
    assert issubclass(
        CalculationNotImplementedError, CalculationEngineError
    )
    assert issubclass(ProviderNotFoundError, CalculationEngineError)


def test_formula_registry_starts_empty():
    assert all_formulas() == {}


def test_formula_registry_register_and_get():
    entry = FormulaRegistryEntry(
        formula_id="TEST_ID",
        symbol="x",
        unit="mm",
        source="test",
        classification="QUICK",
        validation_status="PROVISIONAL",
    )
    register_formula(entry)
    try:
        assert get_formula("TEST_ID") == entry
        assert all_formulas() == {"TEST_ID": entry}
    finally:
        # Keep the module-level registry clean for other tests.
        calculation_engine.formula_registry._REGISTRY = {}


def test_formula_registry_duplicate_registration_rejected():
    entry = FormulaRegistryEntry(
        formula_id="DUP_ID",
        symbol="x",
        unit="mm",
        source="test",
        classification="QUICK",
        validation_status="PROVISIONAL",
    )
    register_formula(entry)
    try:
        with pytest.raises(CalculationInputError):
            register_formula(entry)
    finally:
        calculation_engine.formula_registry._REGISTRY = {}


def test_formula_registry_missing_key_raises_keyerror():
    with pytest.raises(KeyError):
        get_formula("NOT_REGISTERED")
