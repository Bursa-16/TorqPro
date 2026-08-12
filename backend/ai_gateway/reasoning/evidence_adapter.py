"""TorqPro AI Gateway Reasoning - Beta.1 evidence adapter (v3.0.0-beta.2).

Maps an already-persisted
``backend.torque_recommendation.audit.get_recommendation_audit`` record
onto a ``backend.calculation_engine.response.CalculationResponse`` --
purely a data-shape adapter, so that
``backend.ai_gateway.evidence_checker.check_evidence`` (and, through
it, ``backend.ai_gateway.composer.ResultLabel``) can be reused
byte-for-byte unchanged, rather than reimplementing their
PASS/WARN/FAIL and CALCULATED/VALIDATED/ESTIMATED grounding logic a
second time for reasoning.

**This module runs no calculation whatsoever.** It never imports
``backend.torque_recommendation.engine``,
``backend.calculation_engine.joint_analysis``, or any
``backend.vdi2230_core``/``backend.engineering_core`` function --
every value returned here is copied from the already-computed,
already-persisted Stage 0-approved Beta.1 payload.

**Known, deliberate fidelity limitation** (documented rather than
worked around by recomputation, per the Stage 0-approved "no
rerun" rule): Beta.1's persisted ``calculation_source`` only retains
``formula_id``/``symbol``/``unit``/``classification``/
``validation_status`` per formula-trace entry, not each formula's
individual numeric value (only the *aggregate* outputs --
``recommended_torque``/``preload_n``/``calculated_torque`` -- are
retained, as top-level ``TorqueRecommendationResult`` fields, not
mapped back to one specific formula each). Every
``CalculationResult.value`` this adapter produces is therefore
``None`` -- this module never fabricates a per-formula numeric value
it does not actually have. This is sufficient for
``evidence_checker``/``composer``: both only depend on *presence* of a
``CalculationResponse`` (and its ``formula_id``s, for audit purposes)
-- never on ``CalculationResult.value`` -- to assign
``EvidenceStatus.PASS``/``ResultLabel.CALCULATED`` (see those modules'
own docstrings: "this checker only confirms presence, per ADR-0017
Karar 5" / "no Question Bank evidence ... can downgrade it").
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.calculation_engine.response import CalculationResponse, CalculationResult

#: Fixed ``CalculationResponse.standard`` label for every response
#: this adapter builds -- distinguishes a Beta.1-sourced, adapted
#: response from a live ``VDI2230Provider`` response in any log/audit
#: reader that inspects this field. Not one of
#: ``backend.standards``' registered standard names -- deliberately a
#: reasoning-layer-only label.
_STANDARD_LABEL = "torque_recommendation_beta1"

#: Fixed ``CalculationResponse.provider_version`` label -- this is an
#: adapter, not a provider; the value names the Beta.1 phase whose
#: output it adapts, not a calculation-provider version number.
_PROVIDER_VERSION_LABEL = "beta.1"


def to_calculation_response(record: Dict[str, Any]) -> Optional[CalculationResponse]:
    """Build a structural ``CalculationResponse`` from ``record``
    (the dict returned by
    ``backend.torque_recommendation.audit.get_recommendation_audit``).

    Returns ``None`` -- not a response with empty ``results`` -- when
    ``record`` carries no ``calculation_source`` entries at all, so
    that a caller passing this straight into
    ``evidence_checker.check_evidence`` gets the correct
    ``EvidenceStatus.FAIL`` outcome for "no calculation evidence"
    rather than a false ``PASS`` from an empty-but-non-``None``
    response object.

    Raises nothing for a malformed ``record``: a missing key is
    treated the same as an empty value throughout (``.get(...)`` with
    safe defaults) -- callers that need to distinguish "well-formed
    but empty" from "structurally corrupt" should validate ``record``
    themselves before calling this function (see
    ``engine.py``'s own ``_is_well_formed`` check, which does exactly
    that upstream of this adapter).
    """
    result_json = record.get("result_json") or {}
    calculation_source = result_json.get("calculation_source") or []
    if not calculation_source:
        return None

    results: List[CalculationResult] = [
        CalculationResult(
            value=None,
            unit=str(trace.get("unit", "")),
            formula_id=str(trace.get("formula_id", "")),
            classification=str(trace.get("classification", "")),
            validation_status=str(trace.get("validation_status", "")),
        )
        for trace in calculation_source
    ]

    return CalculationResponse(
        standard=_STANDARD_LABEL,
        provider_version=_PROVIDER_VERSION_LABEL,
        inputs=dict(record.get("request_json") or {}),
        results=results,
        formula_traces=tuple(calculation_source),
        warnings=list(result_json.get("warnings") or []),
        validation={
            "status": result_json.get("status"),
            "confidence": result_json.get("confidence"),
            "readiness": result_json.get("readiness"),
        },
    )


__all__ = ["to_calculation_response"]
