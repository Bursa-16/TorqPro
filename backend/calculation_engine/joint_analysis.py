"""TorqPro Calculation Engine - Joint Analysis & Torque Optimization
(Faz 2.8.7).

Orchestrates existing, already-tested calculation building blocks --
``backend.vdi2230_core`` (tensile stress area A_s, quick target
preload F_M, generic series-compliance stiffness c_b/c_c, the
mandatory corrected load-sharing model Phi/F_S, and the safety/result
evaluation structure) and ``backend.engineering_core`` (tightening
torque, thread/friction geometry) -- into one deterministic per-joint
torque-optimization assessment.

Builds NO new physical model. Two narrow, explicitly-documented
algebraic derivations of already-approved/already-specified formulas
are added locally in this module (never in the closed
``backend.vdi2230_core`` package, which stays import-isolated by
design -- see that package's own ``__init__.py``):

- ``_residual_clamp_load_n``: ``F_K,res = F_M - (1 - Phi) * F_A``,
  the residual-clamp-force half of the same "mandatory corrected
  model" already implemented for ``F_S`` (see
  ``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §3 and
  ``backend/vdi2230_core/load_factor.py``). Not independently
  golden-case validated in this phase, so this module marks it
  PROVISIONAL rather than reusing the APPROVED status ``vdi2230_core``
  gives Phi/F_S -- see ``_LOCAL_TRACES`` below.
- ``_preload_from_torque_n``: the algebraic inverse of
  ``backend.engineering_core.torque.tightening_torque_nm`` (that
  function is linear in preload; this module never recomputes its
  torque coefficient independently -- see the function's own
  docstring and the round-trip regression test in
  ``tests/test_faz_2_8_7_joint_analysis.py``).

No coefficient, threshold or default engineering limit is invented
anywhere in this module. ``fail_threshold``, ``warn_threshold`` and
``max_utilization_ratio`` must always be supplied by the caller from a
validated source; when absent, the corresponding output is ``None``
with an explicit reason in ``warnings``/``coverage`` -- never a
silently assumed default. The one exception, clearly noted in the
response rather than hidden, is ``external_axial_load_n``: when the
caller omits it, it is treated as ``0`` (no external axial load
specified), which is a physically meaningful state, not a fabricated
value.

Explicitly out of scope for this phase (see
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §6, §10-§17 and the
Faz 2.8.7 brief) -- ``UNSUPPORTED_EFFECTS`` below lists these and
every response echoes the list back verbatim: settlement/embedment,
thermal preload change, relaxation/creep, torque-angle tightening,
multi-step tightening, sequence optimization, a full VDI 2230
compliance claim, FEA and AI/ML torque prediction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from backend.engineering_core import friction as eg_friction
from backend.engineering_core import geometry as eg_geometry
from backend.engineering_core import torque as eg_torque
from backend.vdi2230_core import (
    CalculationDomainError,
    CalculationInputError,
    FormulaId,
    StiffnessSegment,
    evaluate_safety,
    get_trace,
    load_factor_phi,
    series_compliance_stiffness_n_per_mm,
    service_bolt_force_n,
    target_preload_n,
    tensile_stress_area_mm2,
)

#: Fixed, non-exhaustive-labelled list of effects this phase does not
#: model. Identifiers only -- TR/EN display text lives in the
#: frontend's ``ja.*`` i18n namespace, never hard-coded here.
UNSUPPORTED_EFFECTS = (
    "settlement_embedment",
    "thermal_preload_change",
    "relaxation_creep",
    "torque_angle_tightening",
    "multi_step_tightening",
    "sequence_optimization",
    "full_vdi2230_compliance",
    "fea",
    "ai_ml_torque_prediction",
)

_PROVISIONAL = "PROVISIONAL"


@dataclass(frozen=True)
class LocalFormulaTrace:
    """Traceability record for a formula computed in this module
    rather than read from ``backend.vdi2230_core.get_trace`` -- same
    shape as ``backend.vdi2230_core.FormulaTrace`` so both can be
    serialized identically in ``formula_trace``."""

    formula_id: str
    symbol: str
    unit: str
    source: str
    classification: str
    validation_status: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "formula_id": self.formula_id,
            "symbol": self.symbol,
            "unit": self.unit,
            "source": self.source,
            "classification": self.classification,
            "validation_status": self.validation_status,
        }


_LOCAL_TRACES: Dict[str, LocalFormulaTrace] = {
    "RESIDUAL_CLAMP_LOAD": LocalFormulaTrace(
        formula_id="JOINT_ANALYSIS_FK_RES",
        symbol="F_K,res",
        unit="N",
        source=(
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §3 "
            "(F_K,res = F_M - (1-Phi)*F_A, same mandatory corrected "
            "model section as the already-APPROVED Phi/F_S in "
            "backend/vdi2230_core/load_factor.py); not independently "
            "golden-case validated in this phase"
        ),
        classification="MANDATORY_CORRECTED_MODEL",
        validation_status=_PROVISIONAL,
    ),
    "PRELOAD_FROM_TORQUE": LocalFormulaTrace(
        formula_id="JOINT_ANALYSIS_PRELOAD_FROM_TORQUE",
        symbol="F_M(M_A)",
        unit="N",
        source=(
            "Algebraic inverse of "
            "backend/engineering_core/torque.py:tightening_torque_nm "
            "(that formula is linear in preload; solved here for F "
            "given M_A instead of M_A given F -- see "
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §5)"
        ),
        classification="DETAILED",
        validation_status=_PROVISIONAL,
    ),
    "SAFETY_FACTOR": LocalFormulaTrace(
        formula_id="JOINT_ANALYSIS_SAFETY_FACTOR",
        symbol="S_F",
        unit="",
        source=(
            "S_F = 1 / utilization, the reciprocal of the utilization "
            "ratio already computed by "
            "backend/vdi2230_core/result.py:evaluate_safety "
            "(docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §9)"
        ),
        classification="QUICK",
        validation_status=_PROVISIONAL,
    ),
}


def _residual_clamp_load_n(preload_n: float, phi: float, external_axial_load_n: float) -> float:
    """Residual clamp force F_K,res = F_M - (1 - Phi) * F_A.

    See ``_LOCAL_TRACES["RESIDUAL_CLAMP_LOAD"]`` for sourcing. Raises
    nothing of its own -- ``preload_n``, ``phi`` and
    ``external_axial_load_n`` are already validated by the callers
    that produced them (``target_preload_n`` / ``load_factor_phi`` /
    plain finite-float coercion respectively).
    """
    return preload_n - (1.0 - phi) * external_axial_load_n


def _preload_from_torque_n(
    applied_torque_nm: float,
    pitch_diameter_mm: float,
    pitch_mm: float,
    mu_thread: float,
    mu_bearing: float,
    effective_bearing_diameter_mm: float,
) -> float:
    """Preload F_M implied by an already-applied tightening torque.

    Algebraic inverse of
    ``backend.engineering_core.torque.tightening_torque_nm``, which
    computes::

        M_A [Nm] = F * ((d2/2)*tan(helix+rho) + mu_bearing*(D_Km/2)) / 1000

    -- linear in F for fixed geometry/friction, so::

        F = M_A * 1000 / ((d2/2)*tan(helix+rho) + mu_bearing*(D_Km/2))

    Built from the exact same primitives
    (``engineering_core.geometry.helix_angle_rad``,
    ``engineering_core.friction.thread_friction_angle_rad``) as the
    forward formula, so the two can never silently drift apart --
    guarded by a round-trip regression test.

    Raises ``CalculationInputError`` if the torque coefficient
    (denominator) is not strictly positive (degenerate geometry).
    """
    helix = eg_geometry.helix_angle_rad(pitch_mm, pitch_diameter_mm)
    rho = eg_friction.thread_friction_angle_rad(mu_thread)
    coefficient_mm = (pitch_diameter_mm / 2) * math.tan(helix + rho) + mu_bearing * (
        effective_bearing_diameter_mm / 2
    )
    if coefficient_mm <= 0:
        raise CalculationInputError(
            "Torque coefficient must be > 0 to invert torque into preload, "
            f"got {coefficient_mm} mm (check geometry/friction inputs)"
        )
    return applied_torque_nm * 1000.0 / coefficient_mm


def _segments_from_raw(raw_segments: Any, name: str) -> Optional[List[StiffnessSegment]]:
    """Best-effort mapping of a raw segment list into
    ``StiffnessSegment`` instances. Returns ``None`` (not evaluable,
    never a fabricated default) when ``raw_segments`` is missing or
    not a usable list. Malformed present segments (wrong keys/types)
    propagate ``CalculationInputError`` -- a present-but-broken value
    is a real input error, not missing data.
    """
    if raw_segments is None:
        return None
    if not isinstance(raw_segments, (list, tuple)) or len(raw_segments) == 0:
        return None
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
                f"{name}[{index}] must supply length_mm, modulus_mpa and "
                f"area_mm2: {exc}"
            ) from exc
    return segments


@dataclass(frozen=True)
class JointAnalysisResult:
    """Full Faz 2.8.7 Joint Analysis & Torque Optimization assessment
    for one joint input set."""

    calculated_values: Dict[str, Optional[float]]
    torque_window: Dict[str, Any]
    safety: Dict[str, Any]
    coverage: Dict[str, Any]
    readiness: str
    warnings: List[str]
    critical_findings: List[str]
    formula_trace: List[Dict[str, str]]
    unsupported_effects: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calculated_values": dict(self.calculated_values),
            "torque_window": dict(self.torque_window),
            "safety": dict(self.safety),
            "coverage": dict(self.coverage),
            "readiness": self.readiness,
            "warnings": list(self.warnings),
            "critical_findings": list(self.critical_findings),
            "formula_trace": list(self.formula_trace),
            "unsupported_effects": list(self.unsupported_effects),
        }


# Quantities tracked for coverage/readiness -- each becomes True/False
# in ``coverage.evaluated`` depending on whether it was computable
# from the supplied inputs. Fixed, closed set (do not add a quantity
# here without also producing/explaining it below).
_TRACKED_QUANTITIES = (
    "stress_area_mm2",
    "target_preload_n",
    "bolt_stiffness_n_per_mm",
    "joint_stiffness_n_per_mm",
    "phi",
    "bolt_load_increase_n",
    "residual_clamp_load_n",
    "recommended_torque_nm",
    "preload_from_applied_torque_n",
    "torque_window_min_nm",
    "torque_window_max_nm",
    "yield_utilization",
    "safety_factor",
)


def analyze_joint(
    *,
    diameter_mm: Optional[float] = None,
    pitch_mm: Optional[float] = None,
    rp02_mpa: Optional[float] = None,
    target_yield_ratio: Optional[float] = None,
    max_utilization_ratio: Optional[float] = None,
    mu_thread_nom: Optional[float] = None,
    mu_bearing_nom: Optional[float] = None,
    effective_bearing_diameter_mm: Optional[float] = None,
    bolt_segments: Optional[Sequence[Dict[str, float]]] = None,
    joint_segments: Optional[Sequence[Dict[str, float]]] = None,
    external_axial_load_n: Optional[float] = None,
    minimum_required_clamp_load_n: Optional[float] = None,
    applied_torque_nm: Optional[float] = None,
    fail_threshold: Optional[float] = None,
    warn_threshold: Optional[float] = None,
) -> JointAnalysisResult:
    """Assess a joint's torque/preload/stiffness/safety picture from
    whichever of the above inputs are supplied.

    Never raises for a *missing* optional input -- the corresponding
    output is ``None`` and ``coverage``/``warnings`` explain why. Does
    raise ``backend.vdi2230_core.CalculationInputError`` /
    ``CalculationDomainError`` when a *supplied* value is malformed
    (not a finite number, non-positive where positive is required, an
    empty/broken segment list, ...) -- those exceptions propagate
    unchanged from the wired core, exactly as
    ``backend.calculation_engine.providers.vdi2230_provider`` already
    does for the same underlying functions.
    """
    values: Dict[str, Optional[float]] = {name: None for name in _TRACKED_QUANTITIES}
    warnings: List[str] = []
    critical: List[str] = []
    traces: List[Dict[str, str]] = []
    missing_for: Dict[str, List[str]] = {}

    def _trace_from_core(formula_id: FormulaId) -> None:
        core_trace = get_trace(formula_id)
        traces.append(
            {
                "formula_id": core_trace.formula_id.value,
                "symbol": core_trace.symbol,
                "unit": core_trace.unit,
                "source": core_trace.source,
                "classification": core_trace.classification,
                "validation_status": core_trace.validation_status,
            }
        )
        if core_trace.validation_status == _PROVISIONAL:
            warnings.append(
                f"{core_trace.formula_id.value} ({core_trace.symbol}) is "
                "PROVISIONAL: independent validation not yet complete."
            )

    def _trace_local(key: str) -> None:
        local_trace = _LOCAL_TRACES[key]
        traces.append(local_trace.to_dict())
        warnings.append(
            f"{local_trace.formula_id} ({local_trace.symbol}) is "
            "PROVISIONAL: independent validation not yet complete."
        )

    # 1. Stress area (A_s)
    stress_area_mm2: Optional[float] = None
    if diameter_mm is not None and pitch_mm is not None:
        stress_area_mm2 = tensile_stress_area_mm2(diameter_mm, pitch_mm)
        values["stress_area_mm2"] = stress_area_mm2
        _trace_from_core(FormulaId.VDI2230_AS)
    else:
        missing_for["stress_area_mm2"] = [
            name
            for name, value in (("diameter_mm", diameter_mm), ("pitch_mm", pitch_mm))
            if value is None
        ]

    # 2. Target preload (F_M)
    preload_n: Optional[float] = None
    if stress_area_mm2 is not None and rp02_mpa is not None and target_yield_ratio is not None:
        preload_n = target_preload_n(rp02_mpa, stress_area_mm2, target_yield_ratio)
        values["target_preload_n"] = preload_n
        _trace_from_core(FormulaId.VDI2230_PRELOAD)
    else:
        needed = []
        if stress_area_mm2 is None:
            needed.append("diameter_mm/pitch_mm")
        if rp02_mpa is None:
            needed.append("rp02_mpa")
        if target_yield_ratio is None:
            needed.append("target_yield_ratio")
        missing_for["target_preload_n"] = needed

    # 3/4. Bolt & joint stiffness (c_b, c_c)
    bolt_stiffness: Optional[float] = None
    joint_stiffness: Optional[float] = None
    bolt_seg_list = _segments_from_raw(bolt_segments, "bolt_segments")
    joint_seg_list = _segments_from_raw(joint_segments, "joint_segments")
    if bolt_seg_list:
        bolt_stiffness = series_compliance_stiffness_n_per_mm(bolt_seg_list)
        values["bolt_stiffness_n_per_mm"] = bolt_stiffness
        _trace_from_core(FormulaId.VDI2230_CB)
    else:
        missing_for["bolt_stiffness_n_per_mm"] = ["bolt_segments"]
    if joint_seg_list:
        joint_stiffness = series_compliance_stiffness_n_per_mm(joint_seg_list)
        values["joint_stiffness_n_per_mm"] = joint_stiffness
        _trace_from_core(FormulaId.VDI2230_CC)
    else:
        missing_for["joint_stiffness_n_per_mm"] = ["joint_segments"]

    # 5. Phi
    phi: Optional[float] = None
    if bolt_stiffness is not None and joint_stiffness is not None:
        try:
            phi = load_factor_phi(bolt_stiffness, joint_stiffness)
            values["phi"] = phi
            _trace_from_core(FormulaId.VDI2230_PHI)
        except CalculationDomainError as exc:
            warnings.append(f"Phi not evaluable: {exc}")
            missing_for["phi"] = ["bolt_segments/joint_segments (degenerate: c_b+c_c=0)"]
    else:
        missing_for["phi"] = ["bolt_segments", "joint_segments"]

    # External axial load: absence is a meaningful zero, not a
    # fabricated value -- noted, not warned.
    axial_load_supplied = external_axial_load_n is not None
    axial_load_n = float(external_axial_load_n) if axial_load_supplied else 0.0
    if not axial_load_supplied:
        warnings.append(
            "external_axial_load_n not supplied; treated as 0 N "
            "(no external axial load)."
        )

    # 6. Bolt load increase under external axial load (Phi * F_A) and
    #    residual clamp load F_K,res -- both need Phi and a preload.
    if phi is not None and preload_n is not None:
        service_load_n = service_bolt_force_n(preload_n, phi, axial_load_n)
        values["bolt_load_increase_n"] = service_load_n - preload_n
        if not any(t["formula_id"] == FormulaId.VDI2230_FS.value for t in traces):
            _trace_from_core(FormulaId.VDI2230_FS)

        residual = _residual_clamp_load_n(preload_n, phi, axial_load_n)
        values["residual_clamp_load_n"] = residual
        _trace_local("RESIDUAL_CLAMP_LOAD")
        if residual < 0:
            critical.append(
                "residual_clamp_load_negative: computed residual clamp "
                f"load is {residual:.1f} N (< 0) -- the joint is "
                "predicted to separate under the supplied external "
                "axial load."
            )
    else:
        missing_for["bolt_load_increase_n"] = ["phi", "target_preload_n"]
        missing_for["residual_clamp_load_n"] = ["phi", "target_preload_n"]

    # Geometry/friction needed for any torque<->preload conversion.
    torque_geometry_ready = (
        diameter_mm is not None
        and pitch_mm is not None
        and mu_thread_nom is not None
        and mu_bearing_nom is not None
        and effective_bearing_diameter_mm is not None
    )
    pitch_diameter_mm_value = (
        eg_geometry.pitch_diameter_mm(diameter_mm, pitch_mm) if torque_geometry_ready else None
    )

    # 7. Recommended torque for the target preload (reuses the exact
    #    engineering_core.torque.tightening_torque_nm formula already
    #    used by /api/engineering/check for torque_nom_nm).
    if torque_geometry_ready and preload_n is not None:
        recommended_torque_nm = eg_torque.tightening_torque_nm(
            preload_n,
            pitch_diameter_mm_value,
            pitch_mm,
            mu_thread_nom,
            mu_bearing_nom,
            effective_bearing_diameter_mm,
        )
        values["recommended_torque_nm"] = recommended_torque_nm
    else:
        missing_for["recommended_torque_nm"] = [
            n
            for n, v in (
                ("diameter_mm", diameter_mm),
                ("pitch_mm", pitch_mm),
                ("mu_thread_nom", mu_thread_nom),
                ("mu_bearing_nom", mu_bearing_nom),
                ("effective_bearing_diameter_mm", effective_bearing_diameter_mm),
                ("target_preload_n (rp02_mpa/target_yield_ratio)", preload_n),
            )
            if v is None
        ]

    # 8. Preload implied by an already-applied torque (inverse formula).
    if torque_geometry_ready and applied_torque_nm is not None:
        preload_from_torque = _preload_from_torque_n(
            applied_torque_nm,
            pitch_diameter_mm_value,
            pitch_mm,
            mu_thread_nom,
            mu_bearing_nom,
            effective_bearing_diameter_mm,
        )
        values["preload_from_applied_torque_n"] = preload_from_torque
        _trace_local("PRELOAD_FROM_TORQUE")
    else:
        missing_for["preload_from_applied_torque_n"] = (
            ["applied_torque_nm"] if applied_torque_nm is None else []
        ) + (
            []
            if torque_geometry_ready
            else ["diameter_mm/pitch_mm/mu_thread_nom/mu_bearing_nom/"
                  "effective_bearing_diameter_mm"]
        )

    # 9. Torque window: lower bound from minimum required clamp load,
    #    upper bound from the proof/yield limit + safety evaluation.
    torque_window: Dict[str, Any] = {
        "min_nm": None,
        "max_nm": None,
        "recommended_nm": values["recommended_torque_nm"],
        "min_not_evaluable_reason": None,
        "max_not_evaluable_reason": None,
    }

    if torque_geometry_ready and minimum_required_clamp_load_n is not None:
        if phi is not None:
            required_preload_for_min_clamp = minimum_required_clamp_load_n + (
                1.0 - phi
            ) * axial_load_n
        else:
            required_preload_for_min_clamp = minimum_required_clamp_load_n
            warnings.append(
                "torque_window.min_nm computed without Phi (bolt_segments/"
                "joint_segments not supplied); external axial load is not "
                "compensated for in this lower bound."
            )
        torque_window["min_nm"] = eg_torque.tightening_torque_nm(
            required_preload_for_min_clamp,
            pitch_diameter_mm_value,
            pitch_mm,
            mu_thread_nom,
            mu_bearing_nom,
            effective_bearing_diameter_mm,
        )
        values["torque_window_min_nm"] = torque_window["min_nm"]
    else:
        reason = "minimum_required_clamp_load_n not supplied" if (
            minimum_required_clamp_load_n is None
        ) else "torque geometry inputs incomplete"
        torque_window["min_not_evaluable_reason"] = reason
        missing_for["torque_window_min_nm"] = (
            ["minimum_required_clamp_load_n"]
            if minimum_required_clamp_load_n is None
            else ["diameter_mm/pitch_mm/mu_thread_nom/mu_bearing_nom/"
                  "effective_bearing_diameter_mm"]
        )

    max_bound_ready = (
        torque_geometry_ready
        and stress_area_mm2 is not None
        and rp02_mpa is not None
        and max_utilization_ratio is not None
    )
    if max_bound_ready:
        preload_at_max_utilization = target_preload_n(
            rp02_mpa, stress_area_mm2, max_utilization_ratio
        )
        torque_window["max_nm"] = eg_torque.tightening_torque_nm(
            preload_at_max_utilization,
            pitch_diameter_mm_value,
            pitch_mm,
            mu_thread_nom,
            mu_bearing_nom,
            effective_bearing_diameter_mm,
        )
        values["torque_window_max_nm"] = torque_window["max_nm"]
    else:
        reason = "max_utilization_ratio not supplied" if max_utilization_ratio is None else (
            "torque geometry or rp02_mpa/stress_area inputs incomplete"
        )
        torque_window["max_not_evaluable_reason"] = reason
        missing_for["torque_window_max_nm"] = (
            ["max_utilization_ratio"] if max_utilization_ratio is None else
            ["diameter_mm/pitch_mm/mu_thread_nom/mu_bearing_nom/"
             "effective_bearing_diameter_mm/rp02_mpa"]
        )

    if torque_window["min_nm"] is not None and torque_window["max_nm"] is not None:
        if torque_window["min_nm"] > torque_window["max_nm"]:
            critical.append(
                "torque_window_inverted: computed lower bound "
                f"({torque_window['min_nm']:.1f} Nm) exceeds the computed "
                f"upper bound ({torque_window['max_nm']:.1f} Nm) -- the "
                "minimum clamp-load requirement cannot be met without "
                "exceeding the proof/yield limit with the supplied inputs."
            )

    # 10. Safety: yield utilization + safety factor. Uses service load
    #     F_S when Phi/external load are available, else the plain
    #     target preload -- fail_threshold must be caller-supplied.
    stress_for_safety_mpa = None
    if stress_area_mm2 is not None:
        if phi is not None and preload_n is not None:
            stress_for_safety_mpa = (
                service_bolt_force_n(preload_n, phi, axial_load_n) / stress_area_mm2
            )
        elif preload_n is not None:
            stress_for_safety_mpa = preload_n / stress_area_mm2

    safety_result = evaluate_safety(
        stress_mpa=stress_for_safety_mpa,
        limit_mpa=rp02_mpa,
        fail_threshold=fail_threshold,
        warn_threshold=warn_threshold,
    )
    values["yield_utilization"] = safety_result.utilization
    safety: Dict[str, Any] = {
        "status": safety_result.status,
        "message": safety_result.message,
        "utilization": safety_result.utilization,
        "safety_factor": None,
    }
    if safety_result.utilization is not None and safety_result.utilization > 0:
        safety_factor = 1.0 / safety_result.utilization
        safety["safety_factor"] = safety_factor
        values["safety_factor"] = safety_factor
        _trace_local("SAFETY_FACTOR")
    if not any(t["formula_id"] == FormulaId.VDI2230_RESULT.value for t in traces):
        _trace_from_core(FormulaId.VDI2230_RESULT)
    if safety_result.status == "fail":
        critical.append(
            f"yield_utilization_fail: {safety_result.message} "
            f"(utilization={safety_result.utilization})"
        )
    elif safety_result.status == "warn":
        warnings.append(f"yield_utilization_warn: {safety_result.message}")

    # Coverage / readiness.
    evaluated = {name: values[name] is not None for name in _TRACKED_QUANTITIES}
    evaluated_count = sum(1 for v in evaluated.values() if v)
    total_count = len(_TRACKED_QUANTITIES)
    coverage = {
        "evaluated": evaluated,
        "evaluated_count": evaluated_count,
        "total_count": total_count,
        "coverage_percent": round(100.0 * evaluated_count / total_count, 1),
        "missing_inputs_for": missing_for,
    }

    window_complete = torque_window["min_nm"] is not None and torque_window["max_nm"] is not None
    if evaluated_count == 0:
        readiness = "insufficient_data"
    elif window_complete and safety_result.utilization is not None:
        readiness = "full"
    elif torque_window["min_nm"] is not None or torque_window["max_nm"] is not None:
        readiness = "torque_window_partial"
    else:
        readiness = "partial"

    return JointAnalysisResult(
        calculated_values=values,
        torque_window=torque_window,
        safety=safety,
        coverage=coverage,
        readiness=readiness,
        warnings=warnings,
        critical_findings=critical,
        formula_trace=traces,
        unsupported_effects=list(UNSUPPORTED_EFFECTS),
    )


__all__ = ["analyze_joint", "JointAnalysisResult", "UNSUPPORTED_EFFECTS"]
