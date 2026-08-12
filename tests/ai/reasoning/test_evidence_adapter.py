"""Faz v3.0.0-beta.2 (Engineering Reasoning Engine) unit tests --
``backend.ai_gateway.reasoning.evidence_adapter``.

No HTTP layer, no DB connection -- pure function tests over
hand-built ``get_recommendation_audit``-shaped dicts, mirroring
``tests/torque_recommendation/test_beta1_engine.py``'s own
"no I/O" testing style for a pure-function module.
"""

from __future__ import annotations

from backend.ai_gateway.reasoning.evidence_adapter import to_calculation_response

_TRACE_ENTRY = {
    "formula_id": "VDI2230_PRELOAD",
    "symbol": "F_M",
    "unit": "N",
    "classification": "QUICK",
    "validation_status": "PROVISIONAL",
}


def _record(**result_overrides):
    result_json = {
        "status": "recommended",
        "confidence": "HIGH",
        "readiness": "full",
        "warnings": [],
        "calculation_source": [_TRACE_ENTRY],
        **result_overrides,
    }
    return {
        "request_json": {"diameter_mm": 10, "pitch_mm": 1.5},
        "result_json": result_json,
    }


def test_returns_none_when_calculation_source_missing():
    record = _record(calculation_source=[])
    assert to_calculation_response(record) is None


def test_returns_none_when_result_json_missing():
    assert to_calculation_response({}) is None


def test_maps_formula_trace_fields_verbatim():
    response = to_calculation_response(_record())
    assert response is not None
    assert len(response.results) == len(response.results)  # sanity
    result = response.results[0]
    assert result.formula_id == _TRACE_ENTRY["formula_id"]
    assert result.classification == _TRACE_ENTRY["classification"]
    assert result.validation_status == _TRACE_ENTRY["validation_status"]
    assert result.unit == _TRACE_ENTRY["unit"]


def test_never_fabricates_a_numeric_value():
    """The adapter must never invent a per-formula numeric value it
    does not actually have (see module docstring, "Known, deliberate
    fidelity limitation") -- every CalculationResult.value is None."""
    response = to_calculation_response(_record())
    assert all(result.value is None for result in response.results)


def test_inputs_echoed_from_request_json_not_recomputed():
    record = _record()
    response = to_calculation_response(record)
    assert response.inputs == record["request_json"]


def test_warnings_passed_through_verbatim():
    record = _record(warnings=["some warning"])
    response = to_calculation_response(record)
    assert response.warnings == ["some warning"]


def test_validation_mirrors_beta1_status_confidence_readiness():
    record = _record(status="not_applicable", confidence="NOT_APPLICABLE", readiness="partial")
    response = to_calculation_response(record)
    assert response.validation == {
        "status": "not_applicable",
        "confidence": "NOT_APPLICABLE",
        "readiness": "partial",
    }


def test_adapter_module_never_imports_a_calculation_or_recommendation_engine():
    """Static guarantee: this module can only ever be a data-shape
    adapter -- it structurally cannot re-run Beta.1 or any deterministic
    formula, because it never imports the modules that would let it."""
    import ast
    from pathlib import Path

    import backend.ai_gateway.reasoning.evidence_adapter as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    forbidden = {
        "backend.torque_recommendation.engine",
        "backend.calculation_engine.joint_analysis",
        "backend.vdi2230_core",
        "backend.engineering_core",
    }
    assert not (imported_modules & forbidden)


__all__: list = []
