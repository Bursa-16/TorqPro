"""TorqPro Calculation Engine - Friction Readiness (Faz 2.6.3).

Resolves a ``friction_condition_id`` against the Friction Condition
Library (``backend.library``, ADR-0009/ADR-0010) and reports what --
if anything -- can be safely calculated with the data that record
actually carries. This module computes NO tightening torque value in
this phase. See ``docs/phases/PHASE_2.6.3_FRICTION_AWARE_TORQUE_MODEL.md``
for the full investigation and rationale.

Investigation summary (2026-07-23): every one of the 18 live
``FrictionConditionRecord``s carries only
``overall_friction_coefficient_min/max`` with
``friction_model = combined_or_unspecified`` -- no
``mu_thread``/``mu_bearing`` split, no ``k_factor``. The only two
torque formulas that exist anywhere in this codebase
(``backend.engineering_core.torque.tightening_torque_nm``, which
needs independent ``mu_thread``/``mu_bearing``; and formula-spec
Section 4's ``M_A = K*d*F_M`` quick estimate, which needs ``K``)
cannot consume a single combined coefficient without one of two
prohibited operations: copying the combined value into both
``mu_thread`` and ``mu_bearing`` (a physically unjustified assumption
this phase explicitly forbids), or deriving ``K`` from ``mu`` (also
forbidden -- ``K`` is an independently measured empirical value, not
computable from friction angle alone without its own approved
formula and source). Therefore: **Mode A (combined estimate) does not
produce a torque number in this phase.** It reports readiness state,
a min/nominal/max *friction-coefficient* sensitivity range (not
torque), and clear engineering warnings. Mode B (separated model)
has zero records with the data it would need, so it is always
``blocked`` today; this module's job is to make the codebase *ready*
to activate it once such data exists, without inventing it now.

Two things this module never does, by design (Faz 2.6.3 safety
rules):

    - Assign an overall/combined friction value to ``mu_thread`` or
      ``mu_bearing``.
    - Derive a nut factor ``K`` from any friction value.

No formula from ``backend.engineering_core`` is called by this
module. It is pure resolution, validation and status reporting over
already-approved data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.library import population
from backend.library.models import FrictionConditionRecord
from backend.library.validator import (
    find_dangling_coating_references,
    find_dangling_lubricant_references,
)

from .exceptions import CalculationInputError

# -- Status/reason codes (directive's example vocabulary, used verbatim,
# plus a few precise additions for resolution-time failures) ----------
STATUS_COMBINED_ESTIMATE_AVAILABLE = "combined_estimate_available"
STATUS_SEPARATED_MODEL_AVAILABLE = "separated_model_available"
STATUS_INSUFFICIENT_FRICTION_DATA = "insufficient_friction_data"
STATUS_MISSING_JOINT_GEOMETRY = "missing_joint_geometry"
STATUS_REFERENCE_ONLY_SOURCE = "reference_only_source"
STATUS_UNSUPPORTED_FRICTION_MODEL = "unsupported_friction_model"
STATUS_UNKNOWN_FRICTION_CONDITION_ID = "unknown_friction_condition_id"
STATUS_BROKEN_REFERENCE = "broken_reference"
STATUS_MISSING_SOURCE_TRACEABILITY = "missing_source_traceability"

CALCULATION_MODE_COMBINED = "mode_a_combined_estimate"
CALCULATION_MODE_SEPARATED = "mode_b_separated_model"
CALCULATION_MODE_BLOCKED = "blocked"

#: The only nominal-value policy this module ever uses for a combined
#: friction range: the plain arithmetic midpoint of the already-
#: approved min/max. Never a measured or test-derived value -- always
#: labelled as such wherever it appears.
MIDPOINT_POLICY_ARITHMETIC = "arithmetic_midpoint_of_reference_range"

_MODE_A_WARNINGS = (
    "Combined friction data does not support thread/bearing torque decomposition.",
    "Result is a sensitivity estimate based on a reference friction range.",
    "This result must not be interpreted as ISO 16047 test certification.",
    "Verified mu_thread and mu_bearing data are required for separated decomposition.",
)


@dataclass(frozen=True)
class FrictionReadinessResult:
    """Decomposition-readiness report for one ``friction_condition_id``.

    Every torque-decomposition field below is populated only in
    ``CALCULATION_MODE_SEPARATED`` -- which no live record currently
    reaches, so they are always ``None`` today. This is a status/
    readiness object, not a calculation result: it carries no
    invented number.
    """

    calculation_mode: str
    friction_condition_id: str
    friction_model: str
    data_completeness: Dict[str, bool]
    decomposition_available: bool
    blocking_reasons: List[str]
    source_reference: str
    verification_status: str
    engineering_warnings: List[str]
    combined_friction_scenarios: Optional[Dict[str, Any]] = None

    # Mode B only -- always None while no record has a verified
    # mu_thread/mu_bearing split (see module docstring).
    thread_raising_torque: Optional[float] = None
    thread_friction_torque: Optional[float] = None
    bearing_friction_torque: Optional[float] = None
    total_torque: Optional[float] = None
    preload_contribution_percent: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calculation_mode": self.calculation_mode,
            "friction_condition_id": self.friction_condition_id,
            "friction_model": self.friction_model,
            "data_completeness": dict(self.data_completeness),
            "decomposition_available": self.decomposition_available,
            "blocking_reasons": list(self.blocking_reasons),
            "source_reference": self.source_reference,
            "verification_status": self.verification_status,
            "engineering_warnings": list(self.engineering_warnings),
            "combined_friction_scenarios": self.combined_friction_scenarios,
            "thread_raising_torque": self.thread_raising_torque,
            "thread_friction_torque": self.thread_friction_torque,
            "bearing_friction_torque": self.bearing_friction_torque,
            "total_torque": self.total_torque,
            "preload_contribution_percent": self.preload_contribution_percent,
        }


def _resolve_raw_record(friction_condition_id: str) -> Dict[str, Any]:
    """Return the raw dict for ``friction_condition_id``, or raise
    ``CalculationInputError`` (controlled validation error) if it does
    not exist -- never a silent ``None``/KeyError."""
    records = population.load_population_records("friction condition library")
    for record in records:
        if record.get("id") == friction_condition_id:
            return record
    raise CalculationInputError(
        f"{STATUS_UNKNOWN_FRICTION_CONDITION_ID}: "
        f"{friction_condition_id!r} not found in friction condition library"
    )


def _check_reference_integrity(raw: Dict[str, Any]) -> None:
    """Raise ``CalculationInputError`` if ``raw``'s coating_id/
    lubricant_id reference is broken (dangling)."""
    coating_ids = {r["id"] for r in population.load_population_records("coating library")}
    lubricant_ids = {r["id"] for r in population.load_population_records("lubrication library")}
    issues = find_dangling_coating_references([raw], coating_ids)
    issues += find_dangling_lubricant_references([raw], lubricant_ids)
    if issues:
        messages = "; ".join(issue.message for issue in issues)
        raise CalculationInputError(f"{STATUS_BROKEN_REFERENCE}: {messages}")


def _check_source_traceability(raw: Dict[str, Any]) -> None:
    """Raise ``CalculationInputError`` if ``raw`` has no
    ``source_reference`` at all -- a calculation must never be
    attempted against completely unsourced data."""
    if not raw.get("source_reference"):
        raise CalculationInputError(
            f"{STATUS_MISSING_SOURCE_TRACEABILITY}: "
            f"{raw.get('id')!r} has no source_reference"
        )


def combined_friction_scenarios(
    overall_min: float, overall_max: float,
) -> Dict[str, Any]:
    """Return the min/nominal/max friction-*coefficient* scenario
    values for a combined range -- NOT a torque calculation. The
    nominal value is always the plain arithmetic midpoint, explicitly
    labelled as such (never presented as a measured value)."""
    nominal = (overall_min + overall_max) / 2
    return {
        "minimum": overall_min,
        "nominal_estimate": nominal,
        "nominal_estimate_policy": MIDPOINT_POLICY_ARITHMETIC,
        "maximum": overall_max,
        "unit": "dimensionless",
    }


def assess_friction_readiness(
    friction_condition_id: str,
    *,
    has_joint_geometry: bool = False,
    has_preload: bool = False,
) -> FrictionReadinessResult:
    """Resolve ``friction_condition_id`` and report what calculation
    mode (if any) its data supports.

    Raises ``CalculationInputError`` (controlled validation error, per
    the Faz 2.6.3 directive) if:
        - the id does not exist;
        - its coating_id/lubricant_id reference is broken;
        - it has no source_reference at all.

    Never raises for "not enough data to calculate" -- that is a
    normal, expected outcome reported via ``calculation_mode``/
    ``blocking_reasons``, not an error.
    """
    raw = _resolve_raw_record(friction_condition_id)
    _check_reference_integrity(raw)
    _check_source_traceability(raw)

    record = FrictionConditionRecord.model_validate(raw)

    has_overall = (
        record.overall_friction_coefficient_min is not None
        and record.overall_friction_coefficient_max is not None
    )
    has_mu_thread = record.mu_thread_min is not None and record.mu_thread_max is not None
    has_mu_bearing = record.mu_bearing_min is not None and record.mu_bearing_max is not None
    has_k_factor = record.k_factor_min is not None and record.k_factor_max is not None

    data_completeness = {
        "has_overall_coefficient": has_overall,
        "has_mu_thread": has_mu_thread,
        "has_mu_bearing": has_mu_bearing,
        "has_k_factor": has_k_factor,
        "has_joint_geometry": has_joint_geometry,
        "has_preload": has_preload,
    }

    blocking_reasons: List[str] = []
    warnings: List[str] = []
    scenarios: Optional[Dict[str, Any]] = None
    decomposition_available = False

    separated_ready = (
        has_mu_thread and has_mu_bearing and has_joint_geometry and has_preload
    )

    if separated_ready:
        # No live record reaches this branch today (see module
        # docstring) -- infrastructure only. Still computes no torque
        # value here: that is Faz 2.6.4+ scope once real data exists,
        # and even then must go through an approved, cited formula.
        calculation_mode = CALCULATION_MODE_SEPARATED
        decomposition_available = True
    elif has_overall:
        calculation_mode = CALCULATION_MODE_COMBINED
        blocking_reasons.append(
            f"{STATUS_UNSUPPORTED_FRICTION_MODEL}: a combined/unspecified "
            "friction coefficient cannot be converted into a thread/bearing "
            "torque split or a nut factor K without either copying it into "
            "mu_thread/mu_bearing or deriving K from mu -- both explicitly "
            "forbidden by Faz 2.6.3 safety rules. No approved formula in "
            "this codebase accepts a single combined coefficient as input."
        )
        if not (has_mu_thread and has_mu_bearing):
            blocking_reasons.append(
                f"{STATUS_INSUFFICIENT_FRICTION_DATA}: no independent "
                "mu_thread/mu_bearing values are recorded"
            )
        if not has_joint_geometry:
            blocking_reasons.append(f"{STATUS_MISSING_JOINT_GEOMETRY}: not supplied")
        scenarios = combined_friction_scenarios(
            record.overall_friction_coefficient_min,
            record.overall_friction_coefficient_max,
        )
        warnings.extend(_MODE_A_WARNINGS)
    else:
        calculation_mode = CALCULATION_MODE_BLOCKED
        blocking_reasons.append(
            f"{STATUS_INSUFFICIENT_FRICTION_DATA}: no overall or split "
            "friction coefficient is recorded on this record"
        )

    if record.verification_status == "reference_only":
        warnings.append(
            f"{STATUS_REFERENCE_ONLY_SOURCE}: source is reference_only, "
            "not a production-approved test report -- result (if any) "
            "must be labelled accordingly and not used as production-approved."
        )

    return FrictionReadinessResult(
        calculation_mode=calculation_mode,
        friction_condition_id=friction_condition_id,
        friction_model=record.friction_model.value,
        data_completeness=data_completeness,
        decomposition_available=decomposition_available,
        blocking_reasons=blocking_reasons,
        source_reference=record.source_reference,
        verification_status=record.verification_status,
        engineering_warnings=warnings,
        combined_friction_scenarios=scenarios,
    )


__all__ = [
    "STATUS_COMBINED_ESTIMATE_AVAILABLE",
    "STATUS_SEPARATED_MODEL_AVAILABLE",
    "STATUS_INSUFFICIENT_FRICTION_DATA",
    "STATUS_MISSING_JOINT_GEOMETRY",
    "STATUS_REFERENCE_ONLY_SOURCE",
    "STATUS_UNSUPPORTED_FRICTION_MODEL",
    "STATUS_UNKNOWN_FRICTION_CONDITION_ID",
    "STATUS_BROKEN_REFERENCE",
    "STATUS_MISSING_SOURCE_TRACEABILITY",
    "CALCULATION_MODE_COMBINED",
    "CALCULATION_MODE_SEPARATED",
    "CALCULATION_MODE_BLOCKED",
    "MIDPOINT_POLICY_ARITHMETIC",
    "FrictionReadinessResult",
    "combined_friction_scenarios",
    "assess_friction_readiness",
]
