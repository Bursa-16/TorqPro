"""TorqPro Torque Recommendation Engine - request/result models
(v3.0.0-beta.1).

``TorqueRecommendationRequest`` carries only parameters that already
exist as inputs to ``backend.calculation_engine.joint_analysis.
analyze_joint`` -- no field is invented and no engineering constant is
duplicated here. Field constraints (``gt=0``, ``ge=0``, ``le=1``, ...)
mirror ``backend.app.JointAnalysisRequest``'s own constraints exactly,
so a request that would be accepted/rejected by the existing
``/api/engineering/joint-analysis`` endpoint is accepted/rejected the
same way here -- this module does not invent a second, competing
validation policy for the same underlying inputs.

``TorqueRecommendationResult`` is this engine's own output contract.
It never carries a value invented by this module: every numeric field
originates from ``analyze_joint``'s ``JointAnalysisResult``; every
classification/explanation field is derived deterministically (see
``backend.torque_recommendation.validation`` /
``backend.torque_recommendation.explainability``) from that same
result, never from an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

#: Closed set of applicability statuses (deterministic, not
#: AI-assigned). "recommended" is the only status for which
#: ``recommended_torque`` is ever non-``None``.
APPLICABILITY_STATUSES = ("recommended", "not_applicable")

#: Closed set of confidence classifications (Faz beta.1 scope item 6).
#: Deliberately not a numeric/percentage scale -- derived only from
#: engineering completeness, validation status and assumptions.
CONFIDENCE_LEVELS = ("HIGH", "MEDIUM", "LOW", "NOT_APPLICABLE")


class StiffnessSegmentInput(BaseModel):
    """Mirrors ``backend.vdi2230_core.StiffnessSegment`` 1:1 -- no
    field invented, none omitted. Redefined locally (not imported)
    for the same reason ``backend.app.StiffnessSegmentInput`` and
    ``backend.vdi2230_core.stress_area`` redefine rather than import
    shared constants: this is a request-shape mirror, not a new or
    duplicated engineering constant.
    """

    length_mm: float = Field(gt=0)
    modulus_mpa: float = Field(gt=0)
    area_mm2: float = Field(gt=0)


class TorqueRecommendationRequest(BaseModel):
    """Typed input contract for ``POST /api/ai/torque-recommendation``.

    Every field is optional because ``analyze_joint`` itself requires
    none -- a missing input makes the corresponding output(s) "not
    evaluable" rather than raising, exactly mirroring
    ``backend.app.JointAnalysisRequest``'s own documented rationale.
    ``engineering_context`` is the one addition beyond
    ``JointAnalysisRequest``'s field set: optional, free-form,
    caller-supplied context (e.g. an internal joint/project label) is
    accepted for the caller's own traceability, is never interpreted
    or matched against any rule, and is never persisted verbatim to
    the audit trail (see ``backend.torque_recommendation.audit``) --
    only a length/type-checked, capped string is kept in-process.
    """

    diameter_mm: Optional[float] = Field(default=None, gt=0)
    pitch_mm: Optional[float] = Field(default=None, gt=0)
    rp02_mpa: Optional[float] = Field(default=None, gt=0)
    target_yield_ratio: Optional[float] = Field(default=None, gt=0, le=1)
    max_utilization_ratio: Optional[float] = Field(default=None, gt=0, le=1)
    mu_thread_nom: Optional[float] = Field(default=None, ge=0, le=1)
    mu_bearing_nom: Optional[float] = Field(default=None, ge=0, le=1)
    effective_bearing_diameter_mm: Optional[float] = Field(default=None, gt=0)
    bolt_segments: Optional[List[StiffnessSegmentInput]] = None
    joint_segments: Optional[List[StiffnessSegmentInput]] = None
    external_axial_load_n: Optional[float] = None
    minimum_required_clamp_load_n: Optional[float] = Field(default=None, ge=0)
    applied_torque_nm: Optional[float] = Field(default=None, gt=0)
    fail_threshold: Optional[float] = Field(default=None, gt=0)
    warn_threshold: Optional[float] = Field(default=None, gt=0)
    engineering_context: Optional[str] = Field(default=None, max_length=200)

    def to_analyze_joint_kwargs(self) -> Dict[str, Any]:
        """Every field ``analyze_joint`` accepts, excluding
        ``engineering_context`` (not one of its parameters)."""
        data = self.model_dump()
        data.pop("engineering_context", None)
        return data


@dataclass(frozen=True)
class TorqueRecommendationResult:
    """Output contract returned by
    :func:`backend.torque_recommendation.engine.recommend_torque`.

    Attributes:
        recommended_torque: The recommendation's headline torque
            value, or ``None`` when ``status == "not_applicable"``.
            Always sourced from ``analyze_joint``'s
            ``recommended_torque_nm`` -- never independently computed
            or adjusted by this module.
        unit: Fixed unit label for every torque-valued field here.
        calculated_torque: The raw ``analyze_joint`` value *before*
            any withholding rule is applied. Populated whenever
            ``analyze_joint`` could compute it, even when
            ``recommended_torque`` is withheld for safety (item 5,
            "fail closed") -- this preserves transparency: a caller
            can always see what was computed and why it was not
            surfaced as a recommendation.
        allowable_range: ``{"min_nm": ..., "max_nm": ...}`` from
            ``analyze_joint``'s ``torque_window``, or ``None``
            entries when not evaluable (mirrors
            ``torque_window["min_not_evaluable_reason"]`` /
            ``["max_not_evaluable_reason"]`` in ``explanation``).
        preload_n: Target preload (``target_preload_n``) backing the
            recommendation, when evaluable.
        status: One of :data:`APPLICABILITY_STATUSES`.
        confidence: One of :data:`CONFIDENCE_LEVELS`.
        warnings: Verbatim from ``analyze_joint`` (engine-level
            warnings), plus any withholding-rule notice this module
            adds itself (always appended, never replacing the
            original list).
        assumptions: Deterministic list of assumptions this
            recommendation relies on (e.g. "external axial load
            treated as 0 N").
        explanation: Structured, deterministic explanation (see
            ``backend.torque_recommendation.explainability``).
        calculation_source: Formula trace entries
            (``formula_id``/``classification``/``validation_status``)
            that produced the numeric results.
        trace_id: Audit-trail identifier for this recommendation, or
            ``None`` if audit recording was skipped/unavailable.
        readiness: Verbatim ``analyze_joint`` readiness value, kept
            for callers that already understand that vocabulary.
        coverage_percent: Verbatim ``analyze_joint`` coverage percent.
        critical_findings: Verbatim ``analyze_joint`` critical
            findings (non-empty only when ``status ==
            "not_applicable"`` due to a safety/consistency failure).
    """

    recommended_torque: Optional[float]
    unit: str
    calculated_torque: Optional[float]
    allowable_range: Dict[str, Optional[float]]
    preload_n: Optional[float]
    status: str
    confidence: str
    warnings: List[str]
    assumptions: List[str]
    explanation: Dict[str, Any]
    calculation_source: Sequence[Dict[str, str]]
    trace_id: Optional[str]
    readiness: str
    coverage_percent: float
    critical_findings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommended_torque": self.recommended_torque,
            "unit": self.unit,
            "calculated_torque": self.calculated_torque,
            "allowable_range": dict(self.allowable_range),
            "preload_n": self.preload_n,
            "status": self.status,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "assumptions": list(self.assumptions),
            "explanation": dict(self.explanation),
            "calculation_source": list(self.calculation_source),
            "trace_id": self.trace_id,
            "readiness": self.readiness,
            "coverage_percent": self.coverage_percent,
            "critical_findings": list(self.critical_findings),
        }


__all__ = [
    "APPLICABILITY_STATUSES",
    "CONFIDENCE_LEVELS",
    "StiffnessSegmentInput",
    "TorqueRecommendationRequest",
    "TorqueRecommendationResult",
]
