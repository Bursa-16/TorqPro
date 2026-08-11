"""TorqPro Torque Recommendation Engine - deterministic validation and
confidence/applicability classification (v3.0.0-beta.1, scope items 5
and 6).

Pure functions over an already-computed
``backend.calculation_engine.joint_analysis.JointAnalysisResult`` --
this module runs no calculation of its own and never touches
``backend.vdi2230_core``/``backend.engineering_core`` directly. It
only decides, from the wired core's own output, whether a
recommendation may be surfaced (``status``) and how much engineering
confidence backs it (``confidence``) -- both deterministic, closed
vocabularies (see ``backend.torque_recommendation.models``). No
arbitrary AI confidence percentage is used anywhere in this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from .models import CONFIDENCE_LEVELS

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from backend.calculation_engine.joint_analysis import JointAnalysisResult

_READY_FULL = "full"
_READY_PARTIAL_STATES = ("partial", "torque_window_partial")
_SAFETY_PASS = "pass"


def classify(result: "JointAnalysisResult") -> Tuple[str, str]:
    """Return ``(status, confidence)`` for ``result``.

    Fail-closed rules (scope item 5), applied in order:

    1. Any ``critical_findings`` (e.g. a negative residual clamp
       load, an inverted torque window, a yield-utilization failure)
       -> ``("not_applicable", "NOT_APPLICABLE")``, regardless of how
       complete the rest of the calculation is.
    2. No computable ``recommended_torque_nm`` at all -> the same
       ``("not_applicable", "NOT_APPLICABLE")`` -- there is nothing to
       recommend.
    3. Otherwise, confidence derives only from ``readiness``, the
       safety evaluation status, presence of engine warnings, and
       whether any formula backing the result is still
       ``PROVISIONAL`` (scope item 6: "engineering completeness,
       validation status, supported data and assumptions"):

       - ``readiness == "full"`` and safety ``status == "pass"`` and
         no warnings and no ``PROVISIONAL`` formula in the trace ->
         ``HIGH``.
       - ``readiness == "full"`` otherwise (e.g. a warning, a
         provisional formula, or a non-"pass" safety status that is
         not itself a critical finding) -> ``MEDIUM``.
       - ``readiness`` in ``{"partial", "torque_window_partial"}``
         (torque is computable but the full window/safety picture is
         not) -> ``LOW``.
       - Any other state (only ``"insufficient_data"`` remains, and
         is already excluded by rule 2 whenever it also means no
         torque value) -> ``NOT_APPLICABLE``.
    """
    if result.critical_findings:
        return "not_applicable", "NOT_APPLICABLE"

    recommended_torque_nm = result.calculated_values.get("recommended_torque_nm")
    if recommended_torque_nm is None:
        return "not_applicable", "NOT_APPLICABLE"

    if result.readiness == _READY_FULL:
        has_provisional = any(
            trace.get("validation_status") == "PROVISIONAL" for trace in result.formula_trace
        )
        safety_status = result.safety.get("status")
        if safety_status == _SAFETY_PASS and not result.warnings and not has_provisional:
            return "recommended", "HIGH"
        return "recommended", "MEDIUM"

    if result.readiness in _READY_PARTIAL_STATES:
        return "recommended", "LOW"

    return "not_applicable", "NOT_APPLICABLE"


assert set(CONFIDENCE_LEVELS) == {"HIGH", "MEDIUM", "LOW", "NOT_APPLICABLE"}

__all__ = ["classify"]
