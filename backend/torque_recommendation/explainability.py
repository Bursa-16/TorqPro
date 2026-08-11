"""TorqPro Torque Recommendation Engine - deterministic explainability
(v3.0.0-beta.1, scope item 7).

Every field this module produces is derived directly from an
``analyze_joint`` result (and the request that produced it) with
plain string formatting -- no LLM call, no free-text generation, no
model-invented wording. This is what makes every successful
recommendation "explainable without requiring an LLM": deleting
``backend.ai_gateway`` entirely (or it being offline/unavailable)
changes nothing here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from backend.calculation_engine.joint_analysis import JointAnalysisResult

    from .models import TorqueRecommendationRequest


def build_explanation(
    result: "JointAnalysisResult",
    request: "TorqueRecommendationRequest",
) -> Dict[str, Any]:
    """Build the deterministic ``explanation`` payload.

    Fields:
        input_drivers: Which supplied inputs actually fed the
            recommendation (fixed field-name list, no free text).
        calculation_source: Formula IDs (verbatim ``formula_trace``
            entries) that produced the numeric results -- the single
            source of truth for "what calculation source was used".
        assumptions: Deterministic list built from
            :func:`_build_assumptions`.
        limitations: ``analyze_joint``'s own ``unsupported_effects``
            list, verbatim -- this module never edits or reinterprets
            it.
        warning_reasons: ``analyze_joint``'s own ``warnings``,
            verbatim -- "why warnings were generated" *is* that list;
            this module does not re-derive or summarize it.
    """
    return {
        "input_drivers": _input_drivers(request),
        "calculation_source": list(result.formula_trace),
        "assumptions": _build_assumptions(result, request),
        "limitations": list(result.unsupported_effects),
        "warning_reasons": list(result.warnings),
    }


def _input_drivers(request: "TorqueRecommendationRequest") -> List[str]:
    """Names of every request field the caller actually supplied
    (``None`` fields excluded) -- a fixed, closed field-name
    vocabulary, not free text."""
    data = request.model_dump(exclude={"engineering_context"})
    return sorted(name for name, value in data.items() if value is not None)


def _build_assumptions(
    result: "JointAnalysisResult",
    request: "TorqueRecommendationRequest",
) -> List[str]:
    """Deterministic assumption notices.

    Two fixed, always-checked sources -- never an LLM-generated
    assumption:

    1. The one assumption ``analyze_joint`` itself always documents
       when triggered: ``external_axial_load_n`` not supplied ->
       treated as 0 N (already present verbatim in ``result.warnings``,
       repeated here under the dedicated ``assumptions`` field so a
       caller does not have to string-match the warnings list to find
       it).
    2. Any formula still ``PROVISIONAL`` in ``result.formula_trace``
       is an assumption about validation status, listed by formula id.
    """
    assumptions: List[str] = []
    if request.external_axial_load_n is None:
        assumptions.append(
            "external_axial_load_n not supplied; treated as 0 N (no external axial load)."
        )
    for trace in result.formula_trace:
        if trace.get("validation_status") == "PROVISIONAL":
            assumptions.append(
                f"{trace.get('formula_id')} ({trace.get('symbol')}) is PROVISIONAL: "
                "independent validation not yet complete."
            )
    return assumptions


__all__ = ["build_explanation"]
