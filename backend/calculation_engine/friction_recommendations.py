"""TorqPro Calculation Engine - Friction Recommendation Readiness and
Warnings (Faz 2.6.4).

Two distinct output types, per the Faz 2.6.4 directive:

1. **Deterministic Engineering Warnings** (``generate_friction_warnings``):
   text derived only from fields already present on a
   ``FrictionConditionRecord`` (and, where relevant, the coating/
   lubricant record it references) -- never a judgement call, never a
   ranking, never a recommendation.
2. **Recommendation Readiness** (``assess_recommendation_readiness``):
   what capability level (if any) the record's data supports --
   ``warnings_only``, ``comparison_only``,
   ``engineering_recommendation_ready`` or
   ``production_recommendation_ready`` -- and, explicitly, what is
   still missing to reach a higher level.

This module builds NO recommendation engine. It never ranks, scores
or recommends a lubricant, coating, torque value, temperature
suitability, corrosion class or reuse decision. See
``docs/phases/PHASE_2.6.4_FRICTION_RECOMMENDATION_WARNING_FRAMEWORK.md``
for the full capability matrix and rationale.

Current data reality (2026-07-23, all 18 live records): only
``overall_friction_coefficient_min/max`` with
``friction_model = combined_or_unspecified`` exists. No
``mu_thread``/``mu_bearing``/``k_factor``/``scatter``, no verified
corrosion rating, reusability, max-temperature or
``recommended_standards`` value exists anywhere. Consequently, **no
live record reaches ``engineering_recommendation_ready`` or
``production_recommendation_ready`` today** -- this is asserted by a
dedicated test, not just documented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.library import population

from .friction_readiness import (
    _check_reference_integrity,
    _check_source_traceability,
    _resolve_raw_record,
    assess_friction_readiness,
)

# -- Recommendation readiness levels (ordered, lowest to highest) -----
LEVEL_WARNINGS_ONLY = "warnings_only"
LEVEL_COMPARISON_ONLY = "comparison_only"
LEVEL_ENGINEERING_RECOMMENDATION_READY = "engineering_recommendation_ready"
LEVEL_PRODUCTION_RECOMMENDATION_READY = "production_recommendation_ready"

_LEVEL_ORDER = (
    LEVEL_WARNINGS_ONLY,
    LEVEL_COMPARISON_ONLY,
    LEVEL_ENGINEERING_RECOMMENDATION_READY,
    LEVEL_PRODUCTION_RECOMMENDATION_READY,
)

#: intended_use -> minimum recommendation level it implies. Used only
#: to annotate the response with a gap warning when the requested use
#: exceeds what the data supports -- never to unlock a capability the
#: data does not have.
INTENDED_USE_MINIMUM_LEVEL = {
    "reference_comparison": LEVEL_COMPARISON_ONLY,
    "engineering_calculation": LEVEL_ENGINEERING_RECOMMENDATION_READY,
    "production_release": LEVEL_PRODUCTION_RECOMMENDATION_READY,
}

# -- Capability identifiers (see capability matrix in the phase doc) --
CAPABILITY_REFERENCE_COMPARISON = "reference_comparison"
CAPABILITY_TORQUE_SENSITIVITY = "torque_sensitivity"
CAPABILITY_TORQUE_RECOMMENDATION = "torque_recommendation"
CAPABILITY_LUBRICANT_RECOMMENDATION = "lubricant_recommendation"
CAPABILITY_COATING_RECOMMENDATION = "coating_recommendation"
CAPABILITY_PRODUCTION_APPROVAL = "production_approval"

_ALL_CAPABILITIES = (
    CAPABILITY_REFERENCE_COMPARISON,
    CAPABILITY_TORQUE_SENSITIVITY,
    CAPABILITY_TORQUE_RECOMMENDATION,
    CAPABILITY_LUBRICANT_RECOMMENDATION,
    CAPABILITY_COATING_RECOMMENDATION,
    CAPABILITY_PRODUCTION_APPROVAL,
)

# -- Deterministic warning text (verbatim, per directive) -------------
COMBINED_FRICTION_WARNINGS = (
    "Thread and bearing friction are not separately verified.",
    "Torque decomposition is unavailable.",
    "This condition may only be used as a reference friction range.",
)
REFERENCE_ONLY_WARNINGS = (
    "The friction data is reference-only and is not a certified ISO 16047 test result.",
    "Production approval requires verified application-specific data.",
)
RESTRICTED_LEGACY_WARNINGS = (
    "This condition is marked as restricted/legacy.",
    "Regulatory and customer-specific requirements must be verified before use.",
)
TORQUE_CALCULATION_WARNINGS = (
    "No torque recommendation can be generated from combined friction data.",
    "Verified nut factor or separated thread/bearing friction data is required.",
)

#: Data items that, once verified and sourced, would unlock higher
#: capability levels -- listed here so ``required_missing_data`` never
#: has to invent its own vocabulary per call site.
_ENGINEERING_LEVEL_REQUIREMENTS = (
    "verified_mu_thread", "verified_mu_bearing", "verified_k_factor", "scatter",
)
_PRODUCTION_LEVEL_REQUIREMENTS = (
    "application_specific_verified_test_data",
)
_RECOMMENDATION_ENGINE_REQUIREMENTS = (
    "verified_max_temperature", "verified_corrosion_rating", "verified_reusability",
    "recommended_standards", "supplier_product_identity",
)


@dataclass(frozen=True)
class FrictionRecommendationResult:
    """Recommendation-readiness report for one ``friction_condition_id``.
    Carries no recommendation itself -- only what level of downstream
    use the data supports, and what would need to change for a higher
    level."""

    recommendation_available: bool
    recommendation_level: str
    friction_condition_id: str
    available_capabilities: List[str]
    blocked_capabilities: List[str]
    blocking_reasons: List[str]
    engineering_warnings: List[str]
    source_reference: str
    verification_status: str
    required_missing_data: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_available": self.recommendation_available,
            "recommendation_level": self.recommendation_level,
            "friction_condition_id": self.friction_condition_id,
            "available_capabilities": list(self.available_capabilities),
            "blocked_capabilities": list(self.blocked_capabilities),
            "blocking_reasons": list(self.blocking_reasons),
            "engineering_warnings": list(self.engineering_warnings),
            "source_reference": self.source_reference,
            "verification_status": self.verification_status,
            "required_missing_data": list(self.required_missing_data),
        }


@dataclass(frozen=True)
class FrictionConditionComparisonResult:
    """Purely descriptive comparison between two friction conditions.
    Never states which is "better", "safer", or produces any torque/
    temperature/corrosion judgement -- see module docstring."""

    friction_condition_id_a: str
    friction_condition_id_b: str
    range_relation: str
    width_relation: str
    source_classification_a: str
    source_classification_b: str
    verification_status_a: str
    verification_status_b: str
    source_status_relation: str
    descriptive_statements: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "friction_condition_id_a": self.friction_condition_id_a,
            "friction_condition_id_b": self.friction_condition_id_b,
            "range_relation": self.range_relation,
            "width_relation": self.width_relation,
            "source_classification_a": self.source_classification_a,
            "source_classification_b": self.source_classification_b,
            "verification_status_a": self.verification_status_a,
            "verification_status_b": self.verification_status_b,
            "source_status_relation": self.source_status_relation,
            "descriptive_statements": list(self.descriptive_statements),
        }


def _referenced_status_and_warning(raw: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """Return (status, regulatory_warning) of the coating or lubricant
    record ``raw`` references (whichever id is set), or (None, "") if
    neither resolves to a record carrying those fields. Never raises
    -- reference existence is already checked separately."""
    coating_id = raw.get("coating_id") or ""
    lubricant_id = raw.get("lubricant_id") or ""
    if coating_id:
        for r in population.load_population_records("coating library"):
            if r.get("id") == coating_id:
                return r.get("status"), r.get("regulatory_warning") or ""
    if lubricant_id:
        for r in population.load_population_records("lubrication library"):
            if r.get("id") == lubricant_id:
                return r.get("status"), r.get("regulatory_warning") or ""
    return None, ""


def _source_classification(raw: Dict[str, Any]) -> str:
    """Descriptive-only classification of which domain a friction
    condition's identity comes from -- not a quality judgement."""
    coating_id = raw.get("coating_id") or ""
    lubricant_id = raw.get("lubricant_id") or ""
    if coating_id and lubricant_id:
        return "coating_and_lubricant_based"
    if coating_id:
        return "coating_based"
    if lubricant_id:
        return "lubricant_based"
    return "unclassified"


def generate_friction_warnings(
    friction_condition_id: str,
) -> List[str]:
    """Return the deterministic engineering warnings for
    ``friction_condition_id``, in a fixed, deterministic order:
    combined-friction, reference-only, restricted-legacy, torque-
    calculation. Raises ``CalculationInputError`` for the same
    controlled failures as ``assess_friction_readiness`` (unknown id,
    broken reference, missing source traceability) -- warnings are
    never generated for unresolvable data."""
    raw = _resolve_raw_record(friction_condition_id)
    _check_reference_integrity(raw)
    _check_source_traceability(raw)

    warnings: List[str] = []

    if raw.get("friction_model") == "combined_or_unspecified":
        warnings.extend(COMBINED_FRICTION_WARNINGS)

    if raw.get("verification_status") == "reference_only":
        warnings.extend(REFERENCE_ONLY_WARNINGS)

    ref_status, ref_warning = _referenced_status_and_warning(raw)
    if ref_status == "restricted_legacy":
        warnings.extend(RESTRICTED_LEGACY_WARNINGS)
        if ref_warning:
            warnings.append(ref_warning)

    readiness = assess_friction_readiness(friction_condition_id)
    if readiness.blocking_reasons and not readiness.decomposition_available:
        warnings.extend(TORQUE_CALCULATION_WARNINGS)

    return warnings


def assess_recommendation_readiness(
    friction_condition_id: str,
    *,
    intended_use: Optional[str] = None,
) -> FrictionRecommendationResult:
    """Resolve ``friction_condition_id`` and report what
    recommendation-readiness level (if any) its data supports.

    ``intended_use`` (one of ``INTENDED_USE_MINIMUM_LEVEL``'s keys, if
    given) never raises the achieved level -- it only annotates
    ``engineering_warnings`` when the requested use exceeds what the
    data supports.

    Raises ``CalculationInputError`` for unknown id / broken reference
    / missing source traceability (same controlled failures as
    ``assess_friction_readiness``). Does NOT raise for "both
    coating_id and lubricant_id are empty" -- that is reported as an
    incomplete-condition blocking reason instead, with
    ``recommendation_available = False``.
    """
    raw = _resolve_raw_record(friction_condition_id)
    _check_reference_integrity(raw)
    _check_source_traceability(raw)

    coating_id = raw.get("coating_id") or ""
    lubricant_id = raw.get("lubricant_id") or ""
    has_overall = (
        raw.get("overall_friction_coefficient_min") is not None
        and raw.get("overall_friction_coefficient_max") is not None
    )
    incomplete = not coating_id and not lubricant_id

    blocking_reasons: List[str] = []
    warnings = generate_friction_warnings(friction_condition_id)

    if incomplete:
        blocking_reasons.append(
            "incomplete_condition: both coating_id and lubricant_id are empty"
        )

    available: List[str] = []
    blocked: List[str] = []
    if has_overall and not incomplete:
        available.append(CAPABILITY_REFERENCE_COMPARISON)
    else:
        blocked.append(CAPABILITY_REFERENCE_COMPARISON)

    # None of the 18 live records has independent mu_thread/mu_bearing,
    # a K factor, verified temperature/corrosion/reusability data, or
    # application-specific test data -- every remaining capability is
    # blocked for all of them today, by construction (no such field is
    # ever populated without a cited source, per Faz 2.6.2 rules).
    has_split = (
        raw.get("mu_thread_min") is not None and raw.get("mu_thread_max") is not None
        and raw.get("mu_bearing_min") is not None and raw.get("mu_bearing_max") is not None
    )
    has_k_factor = raw.get("k_factor_min") is not None and raw.get("k_factor_max") is not None
    if has_split or has_k_factor:
        # Infrastructure only -- no live record reaches this branch.
        # Still does not itself constitute a torque recommendation.
        available.append(CAPABILITY_TORQUE_SENSITIVITY)
    else:
        blocked.append(CAPABILITY_TORQUE_SENSITIVITY)
    blocked.append(CAPABILITY_TORQUE_RECOMMENDATION)
    blocked.append(CAPABILITY_LUBRICANT_RECOMMENDATION)
    blocked.append(CAPABILITY_COATING_RECOMMENDATION)
    blocked.append(CAPABILITY_PRODUCTION_APPROVAL)

    if incomplete:
        level = LEVEL_WARNINGS_ONLY
    elif CAPABILITY_REFERENCE_COMPARISON in available:
        level = LEVEL_COMPARISON_ONLY
    else:
        level = LEVEL_WARNINGS_ONLY

    required_missing: List[str] = []
    if level != LEVEL_PRODUCTION_RECOMMENDATION_READY:
        required_missing.extend(_ENGINEERING_LEVEL_REQUIREMENTS)
        required_missing.extend(_RECOMMENDATION_ENGINE_REQUIREMENTS)
        required_missing.extend(_PRODUCTION_LEVEL_REQUIREMENTS)

    if intended_use:
        required_level = INTENDED_USE_MINIMUM_LEVEL.get(intended_use)
        current_index = _LEVEL_ORDER.index(level)
        required_index = _LEVEL_ORDER.index(required_level) if required_level else -1
        if required_level is not None and current_index < required_index:
            warnings.append(
                f"intended_use={intended_use!r} requested, but the current "
                f"data only supports recommendation_level={level!r}; "
                f"{required_level!r} is not reached."
            )

    return FrictionRecommendationResult(
        recommendation_available=not incomplete,
        recommendation_level=level,
        friction_condition_id=friction_condition_id,
        available_capabilities=available,
        blocked_capabilities=blocked,
        blocking_reasons=blocking_reasons,
        engineering_warnings=warnings,
        source_reference=raw.get("source_reference", ""),
        verification_status=raw.get("verification_status", ""),
        required_missing_data=required_missing,
    )


def compare_friction_conditions(
    friction_condition_id_a: str,
    friction_condition_id_b: str,
) -> FrictionConditionComparisonResult:
    """Purely descriptive comparison of two friction conditions'
    reference ranges, source classification and verification status.
    Never states which is "better" or produces any torque/
    temperature/corrosion judgement (see module docstring and
    ``docs/phases/PHASE_2.6.4_FRICTION_RECOMMENDATION_WARNING_FRAMEWORK.md``
    "Comparison capability").

    Raises ``CalculationInputError`` if either id is unresolvable
    (same controlled failures as ``assess_friction_readiness``).
    """
    raw_a = _resolve_raw_record(friction_condition_id_a)
    _check_reference_integrity(raw_a)
    _check_source_traceability(raw_a)
    raw_b = _resolve_raw_record(friction_condition_id_b)
    _check_reference_integrity(raw_b)
    _check_source_traceability(raw_b)

    a_min = raw_a.get("overall_friction_coefficient_min")
    a_max = raw_a.get("overall_friction_coefficient_max")
    b_min = raw_b.get("overall_friction_coefficient_min")
    b_max = raw_b.get("overall_friction_coefficient_max")

    statements: List[str] = []

    if a_min is None or a_max is None or b_min is None or b_max is None:
        range_relation = "not_comparable"
        width_relation = "not_comparable"
        statements.append(
            "One or both conditions have no overall friction coefficient range; "
            "no range comparison can be made."
        )
    elif a_min == b_min and a_max == b_max:
        range_relation = "identical"
        width_relation = "equal_width"
        statements.append(
            "Condition A and Condition B have identical reference friction ranges."
        )
    elif a_max < b_min:
        range_relation = "a_lower"
        width_relation = _width_relation(a_min, a_max, b_min, b_max)
        statements.append(
            "Condition A has a lower reference combined-friction range than Condition B."
        )
    elif b_max < a_min:
        range_relation = "b_lower"
        width_relation = _width_relation(a_min, a_max, b_min, b_max)
        statements.append(
            "Condition B has a lower reference combined-friction range than Condition A."
        )
    else:
        range_relation = "overlapping"
        width_relation = _width_relation(a_min, a_max, b_min, b_max)
        statements.append(
            "The reference combined-friction ranges of Condition A and Condition B overlap."
        )

    verification_status_a = raw_a.get("verification_status", "")
    verification_status_b = raw_b.get("verification_status", "")
    source_status_relation = (
        "same" if verification_status_a == verification_status_b else "different"
    )
    statements.append(
        "Both conditions share the same verification_status."
        if source_status_relation == "same"
        else "Condition A and Condition B have different verification_status values."
    )

    statements.append(
        "Neither condition has separated mu_thread/mu_bearing verification."
        if not (_has_split(raw_a) or _has_split(raw_b))
        else "At least one condition has separated mu_thread/mu_bearing data, "
             "but this comparison does not evaluate it."
    )
    statements.append("No tightening recommendation can be derived from this comparison.")

    return FrictionConditionComparisonResult(
        friction_condition_id_a=friction_condition_id_a,
        friction_condition_id_b=friction_condition_id_b,
        range_relation=range_relation,
        width_relation=width_relation,
        source_classification_a=_source_classification(raw_a),
        source_classification_b=_source_classification(raw_b),
        verification_status_a=verification_status_a,
        verification_status_b=verification_status_b,
        source_status_relation=source_status_relation,
        descriptive_statements=statements,
    )


def _has_split(raw: Dict[str, Any]) -> bool:
    return (
        raw.get("mu_thread_min") is not None and raw.get("mu_thread_max") is not None
        and raw.get("mu_bearing_min") is not None and raw.get("mu_bearing_max") is not None
    )


def _width_relation(a_min: float, a_max: float, b_min: float, b_max: float) -> str:
    width_a = a_max - a_min
    width_b = b_max - b_min
    if abs(width_a - width_b) < 1e-12:
        return "equal_width"
    return "a_narrower" if width_a < width_b else "b_narrower"


__all__ = [
    "LEVEL_WARNINGS_ONLY",
    "LEVEL_COMPARISON_ONLY",
    "LEVEL_ENGINEERING_RECOMMENDATION_READY",
    "LEVEL_PRODUCTION_RECOMMENDATION_READY",
    "INTENDED_USE_MINIMUM_LEVEL",
    "CAPABILITY_REFERENCE_COMPARISON",
    "CAPABILITY_TORQUE_SENSITIVITY",
    "CAPABILITY_TORQUE_RECOMMENDATION",
    "CAPABILITY_LUBRICANT_RECOMMENDATION",
    "CAPABILITY_COATING_RECOMMENDATION",
    "CAPABILITY_PRODUCTION_APPROVAL",
    "COMBINED_FRICTION_WARNINGS",
    "REFERENCE_ONLY_WARNINGS",
    "RESTRICTED_LEGACY_WARNINGS",
    "TORQUE_CALCULATION_WARNINGS",
    "FrictionRecommendationResult",
    "FrictionConditionComparisonResult",
    "generate_friction_warnings",
    "assess_recommendation_readiness",
    "compare_friction_conditions",
]
