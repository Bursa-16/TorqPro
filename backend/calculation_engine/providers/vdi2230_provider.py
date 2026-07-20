"""TorqPro Calculation Engine - VDI 2230 provider wiring (Faz 2.3).

Orchestration only. Maps a ``CalculationRequest`` onto the Phase 2.2
``backend.vdi2230_core`` calculation slice, in the fixed order:

    1. Stress area (A_s)
    2. Preload (F_M)
    3. Bolt stiffness (c_b)
    4. Joint stiffness (c_c)
    5. Phi
    6. Service load (F_S)
    7. Result evaluation (only when a limit is supplied)

and maps the results back onto a ``CalculationResponse``.

No engineering formula is implemented or re-implemented here. Every
numeric value in ``CalculationResponse.results`` comes directly from
a ``backend.vdi2230_core`` function call; every ``unit``,
``formula_id``, ``classification`` and ``validation_status`` comes
directly from that same package's own ``FormulaTrace`` catalog
(``backend.vdi2230_core.get_trace``), never duplicated or guessed
here.

One derived value is computed at the provider boundary rather than
inside any core function, flagged here explicitly for reviewer
visibility: the service *stress* (``F_S / A_s``, MPa) fed into
``evaluate_safety``. ``vdi2230_core.load_factor.service_bolt_force_n``
returns a *force* (N); ``vdi2230_core.result.evaluate_safety``
compares a *stress* (MPa) against ``limit_mpa``. Dividing a force the
core already computed by an area the core already computed, purely
so the two can be wired together, is unit-conversion glue -- not a
new engineering formula. It introduces no coefficient, assumption or
model choice of its own.

Exception policy:
    - A required ``CalculationRequest.inputs`` key is absent ->
      ``backend.calculation_engine.CalculationInputError`` (this
      module's own, raised before any core call).
    - The request asks for a bolt/joint stiffness method other than
      the only one this core slice implements (``"segments"``) ->
      ``backend.calculation_engine.CalculationNotImplementedError``.
    - Any value the core itself rejects (NaN, infinite, negative,
      empty segment list, a domain violation such as
      ``c_b + c_c == 0``, ...) -> the core's own
      ``backend.vdi2230_core`` exception, propagated unchanged. This
      provider never catches and re-wraps a core exception.
    - No ``limit_mpa`` in the request -> result evaluation is
      skipped entirely (not an error); the final result carries
      ``STATUS_NOT_EVALUABLE`` (from ``backend.vdi2230_core.result``)
      in ``CalculationResponse.validation``.
"""

from __future__ import annotations

from typing import Any, List, Mapping

from backend.vdi2230_core import (
    STATUS_NOT_EVALUABLE,
    FormulaId,
    FormulaTrace,
    StiffnessSegment,
    evaluate_safety,
    get_trace,
    load_factor_phi,
    series_compliance_stiffness_n_per_mm,
    service_bolt_force_n,
    target_preload_n,
    tensile_stress_area_mm2,
)

from ..exceptions import (
    CalculationInputError,
    CalculationNotImplementedError,
)
from ..provider import Provider
from ..request import CalculationRequest
from ..response import CalculationResponse, CalculationResult

#: Provider implementation version (independent of the VDI 2230 core
#: package version; bump when this wiring's own behaviour changes).
PROVIDER_VERSION = "2.3.0"

#: The only bolt/joint stiffness method implemented by
#: backend.vdi2230_core in this phase: generic series-compliance
#: over caller-supplied segments. Substitution-length and
#: pressure-cone geometry methods are explicitly out of scope (see
#: backend/vdi2230_core/__init__.py) and are not implemented.
_IMPLEMENTED_STIFFNESS_METHOD = "segments"

_REQUIRED_INPUT_KEYS = (
    "diameter_mm",
    "pitch_mm",
    "rp02_mpa",
    "utilization_ratio",
    "bolt_segments",
    "joint_segments",
    "external_axial_load_n",
)


def _require_inputs(inputs: Mapping[str, Any]) -> None:
    """Raise CalculationInputError if any required key is absent
    from ``inputs``. Does not validate values -- malformed *values*
    (NaN, negative, empty segment list, ...) are the wired core's
    responsibility and surface as the core's own exceptions."""
    missing = [key for key in _REQUIRED_INPUT_KEYS if key not in inputs]
    if missing:
        raise CalculationInputError(
            "Missing required CalculationRequest.inputs key(s): "
            + ", ".join(missing)
        )


def _require_implemented_method(
    inputs: Mapping[str, Any], key: str
) -> None:
    """Raise CalculationNotImplementedError if ``inputs[key]`` names
    a stiffness method other than the one implemented core slice
    supports. Defaults to the implemented method when absent, so
    existing callers that never set this key are unaffected."""
    method = inputs.get(key, _IMPLEMENTED_STIFFNESS_METHOD)
    if method != _IMPLEMENTED_STIFFNESS_METHOD:
        raise CalculationNotImplementedError(
            f"{key}={method!r} is not implemented by "
            "backend.vdi2230_core; only "
            f"{_IMPLEMENTED_STIFFNESS_METHOD!r} (generic series "
            "compliance) is available in this calculation core "
            "slice."
        )


def _segments_from_inputs(
    raw_segments: Any, name: str
) -> List[StiffnessSegment]:
    """Map a request's raw segment list onto
    ``vdi2230_core.StiffnessSegment`` instances. An empty list is
    passed through unchanged -- the core itself rejects it with
    ``CalculationDomainError``, which this function does not
    pre-empt."""
    if not isinstance(raw_segments, (list, tuple)):
        raise CalculationInputError(
            f"{name} must be a list of segment mappings, got "
            f"{type(raw_segments).__name__}"
        )
    segments: List[StiffnessSegment] = []
    for index, raw in enumerate(raw_segments):
        try:
            segments.append(
                StiffnessSegment(
                    length_mm=raw["length_mm"],
                    modulus_mpa=raw["modulus_mpa"],
                    area_mm2=raw["area_mm2"],
                )
            )
        except (KeyError, TypeError) as exc:
            raise CalculationInputError(
                f"{name}[{index}] must supply length_mm, "
                f"modulus_mpa and area_mm2: {exc}"
            ) from exc
    return segments


def _result_from_trace(
    value: Any, trace: FormulaTrace
) -> CalculationResult:
    """Build a CalculationResult purely from a computed value plus
    an already-authoritative FormulaTrace -- unit, formula_id,
    classification and validation_status are read from the trace,
    never re-specified here."""
    return CalculationResult(
        value=value,
        unit=trace.unit,
        formula_id=trace.formula_id.value,
        classification=trace.classification,
        validation_status=trace.validation_status,
    )


class VDI2230Provider(Provider):
    """Wires ``backend.vdi2230_core`` into the
    ``backend.calculation_engine`` ``Provider`` contract.

    Orchestration only -- see module docstring for the exact
    calculation order and exception policy.
    """

    standard = "VDI2230"
    version = PROVIDER_VERSION

    def calculate(
        self, request: CalculationRequest
    ) -> CalculationResponse:
        inputs = request.inputs
        _require_inputs(inputs)
        _require_implemented_method(inputs, "bolt_stiffness_method")
        _require_implemented_method(inputs, "joint_stiffness_method")

        results: List[CalculationResult] = []
        traces: List[FormulaTrace] = []
        warnings: List[str] = []

        # 1. Stress area (A_s)
        as_trace = get_trace(FormulaId.VDI2230_AS)
        stress_area_mm2 = tensile_stress_area_mm2(
            inputs["diameter_mm"], inputs["pitch_mm"]
        )
        results.append(_result_from_trace(stress_area_mm2, as_trace))
        traces.append(as_trace)

        # 2. Preload (F_M)
        preload_trace = get_trace(FormulaId.VDI2230_PRELOAD)
        preload_n = target_preload_n(
            inputs["rp02_mpa"],
            stress_area_mm2,
            inputs["utilization_ratio"],
        )
        results.append(_result_from_trace(preload_n, preload_trace))
        traces.append(preload_trace)

        # 3. Bolt stiffness (c_b)
        cb_trace = get_trace(FormulaId.VDI2230_CB)
        bolt_segments = _segments_from_inputs(
            inputs["bolt_segments"], "bolt_segments"
        )
        bolt_stiffness = series_compliance_stiffness_n_per_mm(
            bolt_segments
        )
        results.append(_result_from_trace(bolt_stiffness, cb_trace))
        traces.append(cb_trace)

        # 4. Joint stiffness (c_c)
        cc_trace = get_trace(FormulaId.VDI2230_CC)
        joint_segments = _segments_from_inputs(
            inputs["joint_segments"], "joint_segments"
        )
        joint_stiffness = series_compliance_stiffness_n_per_mm(
            joint_segments
        )
        results.append(_result_from_trace(joint_stiffness, cc_trace))
        traces.append(cc_trace)

        # 5. Phi
        phi_trace = get_trace(FormulaId.VDI2230_PHI)
        phi = load_factor_phi(bolt_stiffness, joint_stiffness)
        results.append(_result_from_trace(phi, phi_trace))
        traces.append(phi_trace)

        # 6. Service load (F_S)
        fs_trace = get_trace(FormulaId.VDI2230_FS)
        service_load_n = service_bolt_force_n(
            preload_n, phi, inputs["external_axial_load_n"]
        )
        results.append(_result_from_trace(service_load_n, fs_trace))
        traces.append(fs_trace)

        # 7. Result evaluation (only when a limit was supplied)
        result_trace = get_trace(FormulaId.VDI2230_RESULT)
        traces.append(result_trace)
        if request.limit_mpa is None:
            results.append(
                CalculationResult(
                    value=None,
                    unit=result_trace.unit,
                    formula_id=result_trace.formula_id.value,
                    classification=result_trace.classification,
                    validation_status=result_trace.validation_status,
                )
            )
            validation: Mapping[str, Any] = {
                "status": STATUS_NOT_EVALUABLE,
                "message": (
                    "No limit_mpa supplied; result evaluation "
                    "skipped."
                ),
                "utilization": None,
            }
        else:
            # Provider-boundary unit conversion, see module
            # docstring: F_S [N] / A_s [mm^2] -> stress [MPa].
            service_stress_mpa = service_load_n / stress_area_mm2
            safety = evaluate_safety(
                stress_mpa=service_stress_mpa,
                limit_mpa=request.limit_mpa,
                fail_threshold=request.fail_threshold,
                warn_threshold=request.warn_threshold,
            )
            results.append(
                CalculationResult(
                    value=safety.utilization,
                    unit=result_trace.unit,
                    formula_id=result_trace.formula_id.value,
                    classification=result_trace.classification,
                    validation_status=result_trace.validation_status,
                )
            )
            validation = {
                "status": safety.status,
                "message": safety.message,
                "utilization": safety.utilization,
            }
            if safety.status in ("warn", "fail"):
                warnings.append(
                    f"Result evaluation status={safety.status}: "
                    f"{safety.message}"
                )

        for trace in traces:
            if trace.validation_status == "PROVISIONAL":
                warnings.append(
                    f"{trace.formula_id.value} ({trace.symbol}) is "
                    "PROVISIONAL: independent validation not yet "
                    "complete."
                )

        return CalculationResponse(
            standard=self.standard,
            provider_version=self.version,
            inputs=dict(inputs),
            results=results,
            formula_traces=traces,
            warnings=warnings,
            validation=validation,
        )


__all__ = ["VDI2230Provider", "PROVIDER_VERSION"]
