"""Faz 2.3 VDI2230Provider tests.

Covers only orchestration/wiring behaviour: request mapping, core
call sequencing, response mapping and exception routing. No
engineering-formula correctness is asserted here beyond consistency
with directly-called backend.vdi2230_core functions -- this provider
implements no formula of its own (see module docstring in
backend/calculation_engine/providers/vdi2230_provider.py), and this
package's formulas are themselves PROVISIONAL except Phi/F_S.
"""

from __future__ import annotations

import ast
import math
import pathlib

import pytest

from backend import vdi2230_core
from backend.calculation_engine import (
    CalculationInputError,
    CalculationNotImplementedError,
    CalculationRequest,
)
from backend.calculation_engine.providers.vdi2230_provider import (
    PROVIDER_VERSION,
    VDI2230Provider,
)
from backend.vdi2230_core import (
    STATUS_NOT_EVALUABLE,
    CalculationDomainError,
    FormulaId,
    StiffnessSegment,
    get_trace,
    load_factor_phi,
    series_compliance_stiffness_n_per_mm,
    service_bolt_force_n,
    target_preload_n,
    tensile_stress_area_mm2,
)
from backend.vdi2230_core.exceptions import (
    CalculationInputError as CoreCalculationInputError,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_BOLT_SEGMENTS = [
    {"length_mm": 20.0, "modulus_mpa": 210000.0, "area_mm2": 78.5},
    {"length_mm": 10.0, "modulus_mpa": 210000.0, "area_mm2": 58.0},
]
_JOINT_SEGMENTS = [
    {"length_mm": 15.0, "modulus_mpa": 210000.0, "area_mm2": 200.0},
]

_EXPECTED_RESULT_ORDER = [
    FormulaId.VDI2230_AS,
    FormulaId.VDI2230_PRELOAD,
    FormulaId.VDI2230_CB,
    FormulaId.VDI2230_CC,
    FormulaId.VDI2230_PHI,
    FormulaId.VDI2230_FS,
    FormulaId.VDI2230_RESULT,
]


def _base_inputs(**overrides):
    inputs = {
        "diameter_mm": 10.0,
        "pitch_mm": 1.5,
        "rp02_mpa": 640.0,
        "utilization_ratio": 0.9,
        "bolt_segments": [dict(s) for s in _BOLT_SEGMENTS],
        "joint_segments": [dict(s) for s in _JOINT_SEGMENTS],
        "external_axial_load_n": 5000.0,
    }
    inputs.update(overrides)
    return inputs


def _request(
    limit_mpa=None, fail_threshold=None, warn_threshold=None, **overrides
):
    return CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(**overrides),
        limit_mpa=limit_mpa,
        fail_threshold=fail_threshold,
        warn_threshold=warn_threshold,
    )


@pytest.fixture
def provider():
    return VDI2230Provider()


# ---------------------------------------------------------------------------
# End-to-end success
# ---------------------------------------------------------------------------


def test_end_to_end_calculation_without_limit(provider):
    response = provider.calculate(_request())

    assert response.standard == "VDI2230"
    assert response.provider_version == PROVIDER_VERSION
    assert len(response.results) == 7

    # Cross-check every value against directly-called core functions
    # (the provider must not recompute or alter the formulas).
    expected_as = tensile_stress_area_mm2(10.0, 1.5)
    expected_fm = target_preload_n(640.0, expected_as, 0.9)
    bolt_segs = [StiffnessSegment(**s) for s in _BOLT_SEGMENTS]
    joint_segs = [StiffnessSegment(**s) for s in _JOINT_SEGMENTS]
    expected_cb = series_compliance_stiffness_n_per_mm(bolt_segs)
    expected_cc = series_compliance_stiffness_n_per_mm(joint_segs)
    expected_phi = load_factor_phi(expected_cb, expected_cc)
    expected_fs = service_bolt_force_n(expected_fm, expected_phi, 5000.0)

    values = [r.value for r in response.results]
    assert values[0] == pytest.approx(expected_as)
    assert values[1] == pytest.approx(expected_fm)
    assert values[2] == pytest.approx(expected_cb)
    assert values[3] == pytest.approx(expected_cc)
    assert values[4] == pytest.approx(expected_phi)
    assert values[5] == pytest.approx(expected_fs)
    assert values[6] is None  # no limit -> not evaluated


def test_results_are_in_the_mandated_calculation_order(provider):
    response = provider.calculate(_request())
    actual_ids = [r.formula_id for r in response.results]
    expected_ids = [fid.value for fid in _EXPECTED_RESULT_ORDER]
    assert actual_ids == expected_ids


def test_response_echoes_inputs(provider):
    response = provider.calculate(_request())
    assert response.inputs["diameter_mm"] == 10.0
    assert response.inputs["pitch_mm"] == 1.5


# ---------------------------------------------------------------------------
# Missing / malformed input
# ---------------------------------------------------------------------------


def test_missing_required_input_raises_engine_input_error(provider):
    inputs = _base_inputs()
    del inputs["diameter_mm"]
    request = CalculationRequest(standard="VDI2230", inputs=inputs)
    with pytest.raises(CalculationInputError) as excinfo:
        provider.calculate(request)
    assert "diameter_mm" in str(excinfo.value)


def test_missing_required_input_is_not_the_core_exception(provider):
    # The two CalculationInputError classes (engine-level vs.
    # core-level) must not be confused with each other.
    inputs = _base_inputs()
    del inputs["external_axial_load_n"]
    request = CalculationRequest(standard="VDI2230", inputs=inputs)
    with pytest.raises(CalculationInputError) as excinfo:
        provider.calculate(request)
    assert not isinstance(excinfo.value, CoreCalculationInputError)


def test_malformed_segment_list_raises_engine_input_error(provider):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(bolt_segments="not-a-list"),
    )
    with pytest.raises(CalculationInputError):
        provider.calculate(request)


def test_segment_missing_field_raises_engine_input_error(provider):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(
            bolt_segments=[{"length_mm": 20.0, "modulus_mpa": 210000.0}]
        ),
    )
    with pytest.raises(CalculationInputError):
        provider.calculate(request)


# ---------------------------------------------------------------------------
# With / without limit
# ---------------------------------------------------------------------------


def test_calculation_with_limit_populates_validation(provider):
    response = provider.calculate(
        _request(limit_mpa=640.0, fail_threshold=1.0, warn_threshold=0.9)
    )
    assert response.results[-1].value is not None
    assert response.validation["status"] in ("pass", "warn", "fail")
    assert response.validation["utilization"] is not None


def test_calculation_without_limit_is_not_evaluable(provider):
    response = provider.calculate(_request())
    assert response.results[-1].value is None
    assert response.validation["status"] == STATUS_NOT_EVALUABLE
    assert response.validation["utilization"] is None


def test_limit_without_fail_threshold_is_core_missing_input(provider):
    # limit_mpa supplied without fail_threshold is a genuine gap
    # forwarded to evaluate_safety(), which reports its own
    # missing_input status -- distinct from the "no limit at all"
    # not_evaluable business rule.
    response = provider.calculate(_request(limit_mpa=640.0))
    assert response.validation["status"] == "missing_input"


def test_high_utilization_produces_warning(provider):
    response = provider.calculate(
        _request(
            limit_mpa=100.0,
            fail_threshold=1.0,
            warn_threshold=0.01,
            external_axial_load_n=50000.0,
        )
    )
    assert response.validation["status"] in ("warn", "fail")
    assert any(
        "Result evaluation status=" in w for w in response.warnings
    )


# ---------------------------------------------------------------------------
# Core exception propagation: NaN / infinite / negative / empty segment
# ---------------------------------------------------------------------------


def test_nan_input_raises_core_exception_unchanged(provider):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(diameter_mm=float("nan")),
    )
    with pytest.raises(CoreCalculationInputError):
        provider.calculate(request)


def test_infinite_input_raises_core_exception_unchanged(provider):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(external_axial_load_n=float("inf")),
    )
    with pytest.raises(CoreCalculationInputError):
        provider.calculate(request)


def test_negative_input_raises_core_exception_unchanged(provider):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(rp02_mpa=-640.0),
    )
    with pytest.raises(CoreCalculationInputError):
        provider.calculate(request)


def test_empty_segment_list_raises_core_domain_error(provider):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(bolt_segments=[]),
    )
    with pytest.raises(CalculationDomainError):
        provider.calculate(request)


def test_empty_joint_segment_list_raises_core_domain_error(provider):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(joint_segments=[]),
    )
    with pytest.raises(CalculationDomainError):
        provider.calculate(request)


# ---------------------------------------------------------------------------
# Unimplemented VDI geometry
# ---------------------------------------------------------------------------


def test_unimplemented_bolt_stiffness_method_raises_not_implemented(
    provider,
):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(bolt_stiffness_method="substitution_length"),
    )
    with pytest.raises(CalculationNotImplementedError):
        provider.calculate(request)


def test_unimplemented_joint_stiffness_method_raises_not_implemented(
    provider,
):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(joint_stiffness_method="pressure_cone"),
    )
    with pytest.raises(CalculationNotImplementedError):
        provider.calculate(request)


# ---------------------------------------------------------------------------
# FormulaTrace validation
# ---------------------------------------------------------------------------


def test_formula_traces_match_core_catalog_in_order(provider):
    response = provider.calculate(_request())
    assert len(response.formula_traces) == 7
    for trace, expected_id in zip(
        response.formula_traces, _EXPECTED_RESULT_ORDER
    ):
        assert trace == get_trace(expected_id)


def test_each_result_formula_id_matches_its_trace(provider):
    response = provider.calculate(_request())
    for result, trace in zip(response.results, response.formula_traces):
        assert result.formula_id == trace.formula_id.value
        assert result.unit == trace.unit
        assert result.classification == trace.classification
        assert result.validation_status == trace.validation_status


# ---------------------------------------------------------------------------
# APPROVED vs. PROVISIONAL metadata
# ---------------------------------------------------------------------------


def test_phi_and_fs_are_approved(provider):
    response = provider.calculate(_request())
    by_id = {r.formula_id: r for r in response.results}
    assert by_id[FormulaId.VDI2230_PHI.value].validation_status == "APPROVED"
    assert by_id[FormulaId.VDI2230_FS.value].validation_status == "APPROVED"


def test_all_other_results_are_provisional(provider):
    response = provider.calculate(_request())
    provisional_ids = {
        FormulaId.VDI2230_AS.value,
        FormulaId.VDI2230_PRELOAD.value,
        FormulaId.VDI2230_CB.value,
        FormulaId.VDI2230_CC.value,
        FormulaId.VDI2230_RESULT.value,
    }
    for result in response.results:
        if result.formula_id in provisional_ids:
            assert result.validation_status == "PROVISIONAL"


def test_provisional_results_are_warned_about(provider):
    response = provider.calculate(_request())
    provisional_warnings = [
        w for w in response.warnings if "PROVISIONAL" in w
    ]
    # 5 of 7 formulas are PROVISIONAL (see backend/vdi2230_core/trace.py).
    assert len(provisional_warnings) == 5


# ---------------------------------------------------------------------------
# FIAT / ISO: no calculation provider exists (technical debt)
# ---------------------------------------------------------------------------


def test_fiat_iso_metadata_untouched_by_this_change():
    """Not a FIAT/ISO *calculation provider* regression test -- no
    such provider exists anywhere in this codebase (technical debt,
    see backend/calculation_engine/__init__.py docstring). This is
    the closest honest substitute: confirming the Phase 1.2
    metadata-only standard descriptors this change was scoped to
    leave untouched still import and register correctly.
    """
    from backend.standards import fiat, iso
    from backend.standards.registry import get_standard

    assert fiat.FIAT_9_55823.name == "FIAT 9.55823"
    assert fiat.FIAT_9_55823.organization == "FIAT"
    assert iso.ISO_898_1.name == "ISO 898-1"
    assert iso.ISO_965_1.name == "ISO 965-1"
    assert get_standard("FIAT 9.55823") is fiat.FIAT_9_55823
    assert get_standard("ISO 898-1") is iso.ISO_898_1


def test_no_fiat_or_iso_calculation_provider_is_registered():
    from backend.calculation_engine import providers

    assert providers.__all__ == ["VDI2230Provider", "PROVIDER_VERSION"]
    assert not hasattr(providers, "fiat_provider")
    assert not hasattr(providers, "iso_provider")


# ---------------------------------------------------------------------------
# Dependency direction: vdi2230_core must never import calculation_engine
# ---------------------------------------------------------------------------


def test_vdi2230_core_still_does_not_import_calculation_engine():
    forbidden = {
        "engineering_core",
        "standards",
        "library",
        "calculation_engine",
        "app",
    }
    pkg_dir = pathlib.Path(vdi2230_core.__file__).resolve().parent
    for path in pkg_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        collision = imported & forbidden
        assert not collision, (
            f"{path} imports forbidden package(s): {collision}"
        )


def test_calculation_engine_provider_does_import_vdi2230_core():
    # The dependency direction is one-way: calculation_engine may
    # depend on vdi2230_core, never the reverse (checked above).
    import backend.calculation_engine.providers.vdi2230_provider as mod

    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "vdi2230_core" in source


def test_math_isnan_sanity_for_nan_fixture():
    # Guards the NaN test fixture itself against accidental typos.
    assert math.isnan(float("nan"))
