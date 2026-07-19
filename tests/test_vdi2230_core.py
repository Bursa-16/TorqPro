"""Phase 2.2 VDI 2230 Core unit tests.

Covers the first VDI 2230 calculation slice only: tensile stress area
(A_s), quick target preload (F_M), generic series-compliance
stiffness (c_b/c_c), the mandatory load-factor/service-force model
(Phi/F_S) and the safety/result evaluation structure. No detailed
substitution-length, pressure-cone, torque-decomposition or scatter
model is exercised here -- those are explicitly out of scope for this
phase (see backend/vdi2230_core/__init__.py).
"""

import math

import pytest

try:
    from backend.vdi2230_core import (
        CalculationDomainError,
        CalculationInputError,
        FormulaId,
        FormulaTrace,
        MissingFormulaError,
        SafetyResult,
        StiffnessSegment,
        ValidationError,
        Vdi2230CoreError,
        all_traces,
        evaluate_safety,
        get_trace,
        load_factor_phi,
        series_compliance_stiffness_n_per_mm,
        service_bolt_force_n,
        target_preload_n,
        tensile_stress_area_mm2,
    )
    from backend import vdi2230_core
    from backend import calculation_engine
    from backend import engineering_core
    from backend import library
except ImportError:
    from vdi2230_core import (
        CalculationDomainError,
        CalculationInputError,
        FormulaId,
        FormulaTrace,
        MissingFormulaError,
        SafetyResult,
        StiffnessSegment,
        ValidationError,
        Vdi2230CoreError,
        all_traces,
        evaluate_safety,
        get_trace,
        load_factor_phi,
        series_compliance_stiffness_n_per_mm,
        service_bolt_force_n,
        target_preload_n,
        tensile_stress_area_mm2,
    )
    import vdi2230_core
    import calculation_engine
    import engineering_core
    import library


# ---------------------------------------------------------------------------
# Package isolation
# ---------------------------------------------------------------------------


def test_package_imports_without_side_effects():
    assert hasattr(vdi2230_core, "FormulaId")
    assert hasattr(vdi2230_core, "evaluate_safety")


def test_vdi2230_core_has_no_sibling_package_imports():
    import ast
    import pathlib

    forbidden = {"engineering_core", "standards", "library", "calculation_engine", "app"}
    pkg_dir = pathlib.Path(vdi2230_core.__file__).resolve().parent
    for path in pkg_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        collision = imported & forbidden
        assert not collision, f"{path} imports forbidden package(s): {collision}"


def test_vdi2230_core_does_not_mutate_sibling_packages():
    core_before = set(engineering_core.__all__)
    library_before = set(library.__all__)
    calc_engine_before = set(calculation_engine.__all__)
    tensile_stress_area_mm2(10.0, 1.5)
    assert set(engineering_core.__all__) == core_before
    assert set(library.__all__) == library_before
    assert set(calculation_engine.__all__) == calc_engine_before


# ---------------------------------------------------------------------------
# Formula IDs
# ---------------------------------------------------------------------------


def test_formula_id_members_match_required_set():
    expected = {
        "VDI2230_AS",
        "VDI2230_PRELOAD",
        "VDI2230_CB",
        "VDI2230_CC",
        "VDI2230_PHI",
        "VDI2230_FS",
        "VDI2230_RESULT",
    }
    assert {member.name for member in FormulaId} == expected
    assert {member.value for member in FormulaId} == expected


def test_formula_id_is_a_string_enum():
    assert FormulaId.VDI2230_AS == "VDI2230_AS"
    assert isinstance(FormulaId.VDI2230_AS, str)


# ---------------------------------------------------------------------------
# Trace metadata
# ---------------------------------------------------------------------------


def test_every_formula_id_has_a_complete_trace():
    traces = all_traces()
    assert set(traces.keys()) == set(FormulaId)
    for formula_id, trace in traces.items():
        assert isinstance(trace, FormulaTrace)
        assert trace.formula_id == formula_id
        assert trace.symbol
        assert trace.unit is not None  # may be "" for dimensionless
        assert trace.source
        assert trace.classification
        assert trace.validation_status == "PROVISIONAL"


def test_get_trace_returns_matching_entry():
    trace = get_trace(FormulaId.VDI2230_PHI)
    assert trace.symbol == "Phi"
    assert trace.formula_id == FormulaId.VDI2230_PHI


def test_get_trace_raises_missing_formula_error_for_unknown_id():
    with pytest.raises(MissingFormulaError):
        get_trace("NOT-A-REAL-ID")  # type: ignore[arg-type]


def test_all_traces_is_a_copy_not_the_live_catalog():
    traces = all_traces()
    traces.clear()
    assert len(all_traces()) == len(FormulaId)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_exception_hierarchy():
    assert issubclass(CalculationInputError, Vdi2230CoreError)
    assert issubclass(CalculationDomainError, Vdi2230CoreError)
    assert issubclass(MissingFormulaError, Vdi2230CoreError)
    assert issubclass(ValidationError, Vdi2230CoreError)


# ---------------------------------------------------------------------------
# A_s - tensile stress area
# ---------------------------------------------------------------------------


def test_tensile_stress_area_reference_value_m10():
    # M10 x 1.5: d2 = 10 - 0.6495*1.5 = 9.02575, d3 = 10 - 1.2269*1.5 = 8.15965
    # A_s = pi/4 * ((9.02575+8.15965)/2)^2
    expected = math.pi / 4 * ((9.02575 + 8.15965) / 2) ** 2
    assert tensile_stress_area_mm2(10.0, 1.5) == pytest.approx(expected, rel=1e-9)
    assert tensile_stress_area_mm2(10.0, 1.5) == pytest.approx(58.0, abs=0.5)


@pytest.mark.parametrize(
    "diameter_mm", [0.0, -10.0, math.nan, math.inf, -math.inf, None]
)
def test_tensile_stress_area_rejects_invalid_diameter(diameter_mm):
    with pytest.raises(CalculationInputError):
        tensile_stress_area_mm2(diameter_mm, 1.5)


@pytest.mark.parametrize("pitch_mm", [0.0, -1.5, math.nan, math.inf, -math.inf])
def test_tensile_stress_area_rejects_invalid_pitch(pitch_mm):
    with pytest.raises(CalculationInputError):
        tensile_stress_area_mm2(10.0, pitch_mm)


def test_tensile_stress_area_rejects_pitch_too_large_for_diameter():
    # pitch large enough that d3 <= 0 -> domain error, not input error.
    with pytest.raises(CalculationDomainError):
        tensile_stress_area_mm2(2.0, 5.0)


# ---------------------------------------------------------------------------
# F_M - quick target preload
# ---------------------------------------------------------------------------


def test_target_preload_reference_value():
    # F_M = 640 * 58.0 * 0.9
    assert target_preload_n(640.0, 58.0, 0.9) == pytest.approx(640.0 * 58.0 * 0.9)


@pytest.mark.parametrize("rp02_mpa", [0.0, -1.0, math.nan, math.inf])
def test_target_preload_rejects_invalid_rp02(rp02_mpa):
    with pytest.raises(CalculationInputError):
        target_preload_n(rp02_mpa, 58.0, 0.9)


@pytest.mark.parametrize("stress_area_mm2", [0.0, -58.0, math.nan, math.inf])
def test_target_preload_rejects_invalid_stress_area(stress_area_mm2):
    with pytest.raises(CalculationInputError):
        target_preload_n(640.0, stress_area_mm2, 0.9)


@pytest.mark.parametrize("ratio", [0.0, -0.5, math.nan, math.inf, 1.5])
def test_target_preload_rejects_invalid_utilization_ratio(ratio):
    with pytest.raises(CalculationInputError):
        target_preload_n(640.0, 58.0, ratio)


def test_target_preload_accepts_ratio_of_exactly_one():
    assert target_preload_n(640.0, 58.0, 1.0) == pytest.approx(640.0 * 58.0)


# ---------------------------------------------------------------------------
# c_b / c_c - generic series-compliance stiffness
# ---------------------------------------------------------------------------


def test_series_compliance_single_segment_matches_ea_over_l():
    # A single segment reduces to the textbook EA/L quick approximation.
    segment = StiffnessSegment(length_mm=20.0, modulus_mpa=210000.0, area_mm2=78.5)
    expected = (210000.0 * 78.5) / 20.0
    assert series_compliance_stiffness_n_per_mm([segment]) == pytest.approx(expected)


def test_series_compliance_two_segments_reference_value():
    segments = [
        StiffnessSegment(10.0, 210000.0, 78.5),
        StiffnessSegment(10.0, 210000.0, 50.0),
    ]
    expected_compliance = 10.0 / (210000.0 * 78.5) + 10.0 / (210000.0 * 50.0)
    assert series_compliance_stiffness_n_per_mm(segments) == pytest.approx(
        1.0 / expected_compliance
    )


def test_series_compliance_rejects_empty_segment_list():
    with pytest.raises(CalculationDomainError):
        series_compliance_stiffness_n_per_mm([])


@pytest.mark.parametrize(
    "length_mm,modulus_mpa,area_mm2",
    [
        (0.0, 210000.0, 78.5),
        (-10.0, 210000.0, 78.5),
        (10.0, 0.0, 78.5),
        (10.0, -210000.0, 78.5),
        (10.0, 210000.0, 0.0),
        (10.0, 210000.0, -78.5),
        (math.nan, 210000.0, 78.5),
        (10.0, math.inf, 78.5),
    ],
)
def test_series_compliance_rejects_invalid_segment(length_mm, modulus_mpa, area_mm2):
    with pytest.raises(CalculationInputError):
        series_compliance_stiffness_n_per_mm(
            [StiffnessSegment(length_mm, modulus_mpa, area_mm2)]
        )


def test_stiffness_segment_is_immutable():
    segment = StiffnessSegment(10.0, 210000.0, 78.5)
    with pytest.raises(Exception):
        segment.length_mm = 20.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Phi - load factor
# ---------------------------------------------------------------------------


def test_load_factor_phi_reference_value():
    # c_b = 824250, c_c = 3150000 -> Phi = c_b / (c_b + c_c)
    c_b, c_c = 824250.0, 3150000.0
    assert load_factor_phi(c_b, c_c) == pytest.approx(c_b / (c_b + c_c))


def test_load_factor_phi_bounds_are_zero_and_one():
    assert load_factor_phi(0.0, 100.0) == pytest.approx(0.0)
    assert load_factor_phi(100.0, 0.0) == pytest.approx(1.0)


def test_load_factor_phi_is_always_within_unit_interval():
    for c_b in (1.0, 500.0, 1e6):
        for c_c in (1.0, 500.0, 1e6):
            phi = load_factor_phi(c_b, c_c)
            assert 0.0 <= phi <= 1.0


@pytest.mark.parametrize("c_b,c_c", [(-1.0, 100.0), (100.0, -1.0)])
def test_load_factor_phi_rejects_negative_stiffness(c_b, c_c):
    with pytest.raises(CalculationInputError):
        load_factor_phi(c_b, c_c)


@pytest.mark.parametrize("c_b,c_c", [(math.nan, 100.0), (100.0, math.inf)])
def test_load_factor_phi_rejects_non_finite_stiffness(c_b, c_c):
    with pytest.raises(CalculationInputError):
        load_factor_phi(c_b, c_c)


def test_load_factor_phi_rejects_zero_sum():
    with pytest.raises(CalculationDomainError):
        load_factor_phi(0.0, 0.0)


# ---------------------------------------------------------------------------
# F_S - service bolt force (correct model + regression against the
# rejected minus-sign expression)
# ---------------------------------------------------------------------------


def test_service_bolt_force_correct_formula():
    f_m, phi, f_a = 30000.0, 0.25, 8000.0
    assert service_bolt_force_n(f_m, phi, f_a) == pytest.approx(f_m + phi * f_a)


def test_service_bolt_force_regression_against_rejected_minus_sign_formula():
    """docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §3: the expression
    ``F_M - Phi*F_A`` for the service bolt force is explicitly
    rejected. This test proves the implementation does not match that
    rejected formula whenever F_A != 0, and does match the correct
    ``F_M + Phi*F_A`` formula.
    """
    f_m, phi, f_a = 30000.0, 0.25, 8000.0
    correct = f_m + phi * f_a
    rejected = f_m - phi * f_a  # the superseded, incorrect expression

    actual = service_bolt_force_n(f_m, phi, f_a)

    assert actual == pytest.approx(correct)
    assert actual != pytest.approx(rejected)


def test_service_bolt_force_zero_external_load_equals_preload():
    assert service_bolt_force_n(30000.0, 0.4, 0.0) == pytest.approx(30000.0)


def test_service_bolt_force_allows_negative_external_load():
    # A negative F_A (load reversal / compressive convention) must
    # still use addition, not be rejected outright.
    assert service_bolt_force_n(30000.0, 0.4, -1000.0) == pytest.approx(30000.0 - 400.0)


@pytest.mark.parametrize("preload_n", [-1.0, math.nan, math.inf])
def test_service_bolt_force_rejects_invalid_preload(preload_n):
    with pytest.raises(CalculationInputError):
        service_bolt_force_n(preload_n, 0.5, 1000.0)


@pytest.mark.parametrize("phi", [-0.1, 1.1, math.nan, math.inf])
def test_service_bolt_force_rejects_out_of_range_phi(phi):
    with pytest.raises(CalculationInputError):
        service_bolt_force_n(30000.0, phi, 1000.0)


@pytest.mark.parametrize("external_axial_load_n", [math.nan, math.inf, -math.inf])
def test_service_bolt_force_rejects_non_finite_external_load(external_axial_load_n):
    with pytest.raises(CalculationInputError):
        service_bolt_force_n(30000.0, 0.5, external_axial_load_n)


def test_service_bolt_force_uses_full_load_factor_pipeline():
    c_b, c_c = 824250.0, 3150000.0
    phi = load_factor_phi(c_b, c_c)
    f_s = service_bolt_force_n(30000.0, phi, 8000.0)
    assert f_s == pytest.approx(30000.0 + phi * 8000.0)


# ---------------------------------------------------------------------------
# Safety / result evaluation
# ---------------------------------------------------------------------------


def test_evaluate_safety_pass():
    result = evaluate_safety(
        stress_mpa=400.0, limit_mpa=640.0, fail_threshold=1.0, warn_threshold=0.9
    )
    assert result.status == "pass"
    assert result.utilization == pytest.approx(400.0 / 640.0)
    assert isinstance(result, SafetyResult)


def test_evaluate_safety_warn():
    result = evaluate_safety(
        stress_mpa=600.0, limit_mpa=640.0, fail_threshold=1.0, warn_threshold=0.9
    )
    assert result.status == "warn"
    assert result.utilization == pytest.approx(600.0 / 640.0)


def test_evaluate_safety_fail():
    result = evaluate_safety(
        stress_mpa=700.0, limit_mpa=640.0, fail_threshold=1.0, warn_threshold=0.9
    )
    assert result.status == "fail"


def test_evaluate_safety_pass_without_warn_threshold():
    result = evaluate_safety(stress_mpa=400.0, limit_mpa=640.0, fail_threshold=1.0)
    assert result.status == "pass"


def test_evaluate_safety_fail_without_warn_threshold():
    result = evaluate_safety(stress_mpa=700.0, limit_mpa=640.0, fail_threshold=1.0)
    assert result.status == "fail"


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(stress_mpa=None, limit_mpa=640.0, fail_threshold=1.0),
        dict(stress_mpa=400.0, limit_mpa=None, fail_threshold=1.0),
        dict(stress_mpa=400.0, limit_mpa=640.0, fail_threshold=None),
    ],
)
def test_evaluate_safety_missing_input(kwargs):
    result = evaluate_safety(**kwargs)
    assert result.status == "missing_input"
    assert result.utilization is None


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(stress_mpa=-1.0, limit_mpa=640.0, fail_threshold=1.0),
        dict(stress_mpa=math.nan, limit_mpa=640.0, fail_threshold=1.0),
        dict(stress_mpa=400.0, limit_mpa=0.0, fail_threshold=1.0),
        dict(stress_mpa=400.0, limit_mpa=-640.0, fail_threshold=1.0),
        dict(stress_mpa=400.0, limit_mpa=640.0, fail_threshold=0.0),
        dict(stress_mpa=400.0, limit_mpa=640.0, fail_threshold=math.inf),
        dict(
            stress_mpa=400.0,
            limit_mpa=640.0,
            fail_threshold=1.0,
            warn_threshold=-0.1,
        ),
        dict(
            stress_mpa=400.0,
            limit_mpa=640.0,
            fail_threshold=0.8,
            warn_threshold=0.9,
        ),  # warn_threshold >= fail_threshold
    ],
)
def test_evaluate_safety_invalid_input(kwargs):
    result = evaluate_safety(**kwargs)
    assert result.status == "invalid_input"
    assert result.utilization is None


def test_evaluate_safety_not_evaluable_when_evidence_incomplete():
    result = evaluate_safety(
        stress_mpa=400.0,
        limit_mpa=640.0,
        fail_threshold=1.0,
        evidence_complete=False,
    )
    assert result.status == "not_evaluable"
    assert result.utilization is None


def test_evaluate_safety_result_carries_result_trace():
    result = evaluate_safety(stress_mpa=400.0, limit_mpa=640.0, fail_threshold=1.0)
    assert result.trace.formula_id == FormulaId.VDI2230_RESULT
    assert result.trace.validation_status == "PROVISIONAL"


def test_evaluate_safety_never_raises_on_bad_input():
    # A safety-critical evaluation function must never crash the
    # caller; every bad input path returns a structured status.
    for kwargs in (
        dict(stress_mpa="not-a-number", limit_mpa=640.0, fail_threshold=1.0),
        dict(stress_mpa=None, limit_mpa=None, fail_threshold=None),
    ):
        result = evaluate_safety(**kwargs)
        assert result.status in {"missing_input", "invalid_input"}
