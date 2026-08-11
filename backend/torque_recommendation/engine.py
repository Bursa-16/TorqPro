"""TorqPro Torque Recommendation Engine - orchestration
(v3.0.0-beta.1).

``recommend_torque`` is the single entry point this package exposes
to the HTTP layer (``backend.api.routes.torque_recommendation``). It
wires, in fixed order, exactly the flow the beta.1 brief specifies::

    engineering inputs
    -> deterministic TorqPro calculation (analyze_joint)
    -> engineering constraint validation (analyze_joint's own domain
       checks + this module's fail-closed withholding rule)
    -> recommendation candidate
    -> confidence / applicability assessment (validation.classify)
    -> explainable recommendation (explainability.build_explanation)

Traceability/audit recording is deliberately a separate, explicit
step (see ``backend.torque_recommendation.audit``) rather than
something this function does itself: ``recommend_torque`` takes no
``sqlite3.Connection`` and performs no I/O, which keeps it trivially
testable and keeps "deterministic recommendation" and "record it"
as two independently verifiable responsibilities -- mirroring
``backend.calculation_engine.joint_analysis.analyze_joint``'s own
framework-agnostic, I/O-free design.

No LLM/AI provider is invoked anywhere in this module (see
``docs/phases/PHASE_v3.0.0-beta.1_TORQUE_RECOMMENDATION_ENGINE.md``,
architecture note on the ``backend.ai_gateway`` one-way dependency
guard): every field of the returned
``TorqueRecommendationResult`` is fully determined the moment
``analyze_joint`` returns, so recommendation output is provably
identical whether or not any AI provider is installed, configured, or
available -- scope item 10's "offline/deterministic operation must
remain possible" holds trivially, not by a runtime feature flag.
"""

from __future__ import annotations

from backend.calculation_engine.joint_analysis import analyze_joint

from .explainability import build_explanation
from .models import TorqueRecommendationRequest, TorqueRecommendationResult
from .validation import classify

#: Fixed unit label for every torque-valued field this engine returns.
#: ``analyze_joint``/``engineering_core.torque`` always compute in
#: N*m; this module invents no alternate unit or conversion.
TORQUE_UNIT = "Nm"


def recommend_torque(request: TorqueRecommendationRequest) -> TorqueRecommendationResult:
    """Run one full deterministic torque-recommendation pass.

    Raises ``backend.vdi2230_core.CalculationInputError`` /
    ``CalculationDomainError`` unchanged when a *supplied* input is
    malformed or combines into a mathematically undefined/unsupported
    thread-fastener domain (e.g. pitch too large for the given
    diameter) -- propagated exactly as ``analyze_joint`` itself raises
    them, for the HTTP route layer to map to ``422`` (mirroring
    ``/api/engineering/joint-analysis``'s existing, already-tested
    error-mapping convention). A *missing* optional input never
    raises here either -- it simply lowers coverage/readiness/
    confidence, exactly as ``analyze_joint`` already documents.
    """
    result = analyze_joint(**request.to_analyze_joint_kwargs())

    status, confidence = classify(result)

    calculated_torque = result.calculated_values.get("recommended_torque_nm")
    # Fail-closed withholding (scope item 5): a "not_applicable"
    # classification never surfaces a headline recommended_torque,
    # even when analyze_joint did compute one -- calculated_torque
    # still exposes the raw value for transparency (see
    # TorqueRecommendationResult.calculated_torque docstring).
    recommended_torque = calculated_torque if status == "recommended" else None

    warnings = list(result.warnings)
    if status == "not_applicable" and calculated_torque is not None:
        warnings.append(
            "recommended_torque withheld: engineering validation classified this "
            "result as not_applicable (see critical_findings/readiness) even "
            "though a preliminary torque value was computable."
        )

    explanation = build_explanation(result, request)

    return TorqueRecommendationResult(
        recommended_torque=recommended_torque,
        unit=TORQUE_UNIT,
        calculated_torque=calculated_torque,
        allowable_range={
            "min_nm": result.torque_window.get("min_nm"),
            "max_nm": result.torque_window.get("max_nm"),
        },
        preload_n=result.calculated_values.get("target_preload_n"),
        status=status,
        confidence=confidence,
        warnings=warnings,
        assumptions=explanation["assumptions"],
        explanation=explanation,
        calculation_source=result.formula_trace,
        trace_id=None,
        readiness=result.readiness,
        coverage_percent=result.coverage.get("coverage_percent", 0.0),
        critical_findings=list(result.critical_findings),
    )


__all__ = ["recommend_torque", "TORQUE_UNIT"]
