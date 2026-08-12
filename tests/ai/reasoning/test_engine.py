"""Faz v3.0.0-beta.2 (Engineering Reasoning Engine) unit tests --
``backend.ai_gateway.reasoning.engine``.

Pure function/module tests (no HTTP layer, no DB connection) -- see
``test_evidence_adapter.py``'s own module docstring for the same
"no I/O" rationale, extended here to the deterministic reasoning
engine itself.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from backend.ai_gateway.evidence_checker import EvidenceStatus
from backend.ai_gateway.exceptions import PermissionDeniedError
from backend.ai_gateway.permission import UserContext
from backend.ai_gateway.reasoning import engine
from backend.ai_gateway.reasoning.models import ReasoningState

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
        "request_json": {"diameter_mm": 10, "pitch_mm": 1.5},
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
            "assumptions": ["external_axial_load_n not supplied; treated as 0 N."],
            "calculation_source": [_TRACE_ENTRY],
            "explanation": {"limitations": ["fea"]},
        },
    }


def _unsupported_record():
    record = _supported_record()
    record["result_json"] = dict(
        record["result_json"],
        status="not_applicable",
        confidence="NOT_APPLICABLE",
        recommended_torque=None,
        critical_findings=["yield_utilization_fail: utilization=1.2"],
    )
    return record


# ---------------------------------------------------------------------
# Deterministic-authority preservation / no recomputation / no mutation
# ---------------------------------------------------------------------


def test_engineering_conclusion_copies_beta1_values_verbatim():
    record = _supported_record()
    result = engine.run_reasoning(1, record, user=_USER)
    assert result.engineering_conclusion["recommended_torque"] == 12.5
    assert result.engineering_conclusion["preload_n"] == 5000
    assert result.engineering_conclusion["allowable_range"] == {"min_nm": 10.0, "max_nm": 15.0}


def test_run_reasoning_never_mutates_the_supplied_record():
    record = _supported_record()
    snapshot = copy.deepcopy(record)
    engine.run_reasoning(1, record, user=_USER)
    assert record == snapshot


def test_repeated_calls_are_idempotent():
    record = _supported_record()
    r1 = engine.run_reasoning(1, record, user=_USER)
    r2 = engine.run_reasoning(1, record, user=_USER)
    assert r1.to_dict() == r2.to_dict()


def test_engine_module_never_imports_torque_recommendation_engine_or_calc_core():
    """Structural, AST-based proof that this module cannot re-run
    Beta.1 or any deterministic formula -- it never imports the
    modules that would let it."""
    source = Path(engine.__file__).read_text(encoding="utf-8")
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


def test_engine_module_never_imports_an_ai_model_client():
    """Structural separation of Engineering Reasoning from AI-generated
    explanation: this module must never *import* an AIModelClient or a
    concrete provider module -- that lives exclusively in wording.py.
    (The docstring mentions ``AIModelClient`` in prose, by design, to
    document the invariant -- so this check is AST-based over actual
    import statements only, not a raw substring search over the whole
    file.)"""
    source = Path(engine.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = set()
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    assert "AIModelClient" not in imported_names
    assert not any(
        m.startswith("backend.ai_gateway.providers") for m in imported_modules
    )


# ---------------------------------------------------------------------
# Reasoning states
# ---------------------------------------------------------------------


def test_supported_state_when_beta1_status_recommended():
    result = engine.run_reasoning(1, _supported_record(), user=_USER)
    assert result.reasoning_state == ReasoningState.SUPPORTED
    assert result.evidence_status in (EvidenceStatus.PASS, EvidenceStatus.WARN)
    assert result.reasoning_steps  # non-empty


def test_unsupported_state_when_beta1_status_not_applicable():
    result = engine.run_reasoning(1, _unsupported_record(), user=_USER)
    assert result.reasoning_state == ReasoningState.UNSUPPORTED
    assert result.engineering_conclusion["critical_findings"]
    assert result.reasoning_steps


@pytest.mark.parametrize("record", [None, {}, {"result_json": "not-a-dict"}])
def test_insufficient_evidence_for_malformed_record(record):
    result = engine.run_reasoning(1, record, user=_USER)
    assert result.reasoning_state == ReasoningState.INSUFFICIENT_EVIDENCE
    assert result.engineering_conclusion == {}
    assert result.applied_rules == ()
    assert result.evidence_status == EvidenceStatus.FAIL
    assert result.result_label is None


def test_insufficient_evidence_when_no_calculation_source():
    record = _supported_record()
    record["result_json"]["calculation_source"] = []
    result = engine.run_reasoning(1, record, user=_USER)
    assert result.reasoning_state == ReasoningState.INSUFFICIENT_EVIDENCE


def test_insufficient_evidence_for_unrecognised_status_fails_closed():
    record = _supported_record()
    record["result_json"]["status"] = "some-future-status-value"
    result = engine.run_reasoning(1, record, user=_USER)
    assert result.reasoning_state == ReasoningState.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------
# applied_rules / assumptions / warnings / limitations reuse
# ---------------------------------------------------------------------


def test_applied_rules_taken_verbatim_from_calculation_source():
    result = engine.run_reasoning(1, _supported_record(), user=_USER)
    assert result.applied_rules == (
        {
            "formula_id": "VDI2230_PRELOAD",
            "classification": "QUICK",
            "validation_status": "PROVISIONAL",
        },
    )


def test_assumptions_and_limitations_reused_verbatim():
    result = engine.run_reasoning(1, _supported_record(), user=_USER)
    assert result.assumptions == (
        "external_axial_load_n not supplied; treated as 0 N.",
    )
    assert result.limitations == ("fea",)


# ---------------------------------------------------------------------
# result_label reuse (composer.ResultLabel via compose())
# ---------------------------------------------------------------------


def test_result_label_is_calculated_when_evidence_present():
    result = engine.run_reasoning(1, _supported_record(), user=_USER)
    assert result.result_label == "CALCULATED"


# ---------------------------------------------------------------------
# Permission enforcement (reused ai_gateway.permission)
# ---------------------------------------------------------------------


def test_inactive_user_raises_permission_denied_error():
    inactive = UserContext(user_id=1, role="engineer", is_active=False)
    with pytest.raises(PermissionDeniedError):
        engine.run_reasoning(1, _supported_record(), user=inactive)


# ---------------------------------------------------------------------
# with_ai_explanation helper
# ---------------------------------------------------------------------


def test_with_ai_explanation_only_replaces_ai_fields():
    result = engine.run_reasoning(1, _supported_record(), user=_USER)
    updated = engine.with_ai_explanation(
        result, ai_explanation="prose", ai_explanation_provider="deterministic"
    )
    assert updated.ai_explanation == "prose"
    assert updated.ai_explanation_provider == "deterministic"
    assert updated.engineering_conclusion == result.engineering_conclusion
    assert updated.reasoning_steps == result.reasoning_steps
    assert updated.reasoning_state == result.reasoning_state


__all__: list = []
