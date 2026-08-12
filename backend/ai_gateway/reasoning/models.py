"""TorqPro AI Gateway Reasoning - output contract (v3.0.0-beta.2).

Defines the closed reasoning-state vocabulary and the immutable
``ReasoningResult`` this subpackage's ``engine.run_reasoning`` returns.
Mirrors the discipline already established by
``backend.torque_recommendation.models``
(``APPLICABILITY_STATUSES``/``CONFIDENCE_LEVELS`` as plain closed
tuples, a frozen ``@dataclass`` result with a ``to_dict()`` method) and
``backend.ai_gateway.evidence_checker.EvidenceStatus`` /
``backend.ai_gateway.composer.ResultLabel`` (plain string constants,
not an ``enum.Enum``, for trivial JSON serialization).

No numeric confidence score is introduced anywhere in this module --
per the approved Stage 0 design, reasoning outcomes are one of exactly
three closed states (:class:`ReasoningState`), not a percentage or
score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

#: Closed, three-value reasoning outcome vocabulary (approved Stage 0
#: design). Deliberately distinct from
#: ``backend.ai_gateway.evidence_checker.EvidenceStatus``
#: (PASS/WARN/FAIL, an *evidence-grounding* judgement) and from
#: ``backend.torque_recommendation.models.APPLICABILITY_STATUSES``
#: (recommended/not_applicable, a *Beta.1 engineering* judgement) --
#: ``ReasoningState`` is the Engineering Reasoning Engine's own,
#: additional judgement about whether it could reason at all over a
#: given Beta.1 trace, layered on top of both of those, never
#: replacing either.
REASONING_STATES = ("SUPPORTED", "INSUFFICIENT_EVIDENCE", "UNSUPPORTED")


class ReasoningState:
    """Plain string constants -- see :data:`REASONING_STATES`.

    - ``SUPPORTED``: the referenced Beta.1 trace has sufficient
      deterministic evidence (``EvidenceStatus`` PASS/WARN via a
      non-``None`` ``calculation_result``) *and* Beta.1's own
      ``status`` is ``"recommended"`` -- a torque recommendation
      exists and this engine can explain it.
    - ``UNSUPPORTED``: sufficient deterministic evidence exists, but
      Beta.1's own ``status`` is ``"not_applicable"`` (e.g. a critical
      finding withheld the recommendation) -- the reasoning engine can
      still explain *why*, but there is no recommendation to support.
    - ``INSUFFICIENT_EVIDENCE``: the referenced audit row could not be
      read as a well-formed Beta.1 result (missing, corrupt, or
      structurally incomplete stored payload), or carries zero
      calculation evidence at all. Fail-closed: this engine never
      guesses a conclusion in this state.
    """

    SUPPORTED = "SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class ReasoningResult:
    """Immutable output of one ``engine.run_reasoning`` call.

    Attributes:
        trace_id: The Beta.1 ``audit_log.id`` this reasoning result is
            about. Never invented -- always the caller-supplied
            ``trace_id`` that was looked up.
        reasoning_state: One of :data:`REASONING_STATES`.
        engineering_conclusion: A read-only snapshot of Beta.1's own
            authoritative fields
            (``recommended_torque``/``unit``/``calculated_torque``/
            ``preload_n``/``allowable_range``/``status``/
            ``confidence``/``readiness``/``coverage_percent``/
            ``critical_findings``), copied verbatim from the stored
            ``TorqueRecommendationResult.to_dict()`` payload. Empty
            when ``reasoning_state == INSUFFICIENT_EVIDENCE`` and the
            stored payload could not be read at all. Never
            recomputed, rounded, or altered by this module -- see
            ``engine.py`` module docstring, invariant 1.
        reasoning_steps: Deterministic, template-built explanation
            sentences (no LLM) -- mirrors
            ``backend.torque_recommendation.explainability``'s own
            "plain string formatting, no free-text generation"
            discipline. Empty only when ``reasoning_state ==
            INSUFFICIENT_EVIDENCE``.
        applied_rules: ``(formula_id, classification,
            validation_status)`` dicts taken verbatim from Beta.1's
            own ``calculation_source`` (formula trace) -- never
            re-derived or re-validated here.
        assumptions: Verbatim from the stored Beta.1 result.
        warnings: Verbatim from the stored Beta.1 result.
        limitations: Verbatim from the stored Beta.1 result's
            ``explanation.limitations``.
        evidence_status: Mirrors
            ``backend.ai_gateway.evidence_checker.EvidenceCheckResult.
            status`` verbatim (``PASS``/``WARN``/``FAIL``).
        result_label: Mirrors
            ``backend.ai_gateway.composer.ResultLabel`` verbatim, or
            ``None`` for ``EvidenceStatus.FAIL``.
        ai_explanation: Optional AI-generated prose, or ``None`` when
            not requested, not attempted (``INSUFFICIENT_EVIDENCE``),
            or the provider failed/was unavailable/was unknown. A
            ``None`` value here never means the deterministic fields
            above are missing or invalid -- they are always fully
            populated whenever ``reasoning_state`` is ``SUPPORTED`` or
            ``UNSUPPORTED``, independent of this field.
        ai_explanation_provider: Which registered provider produced
            ``ai_explanation``, or ``None`` when ``ai_explanation`` is
            ``None``.
        reasoning_trace_id: Audit-trail identifier for *this*
            reasoning interaction (an ``ai_audit_records.id``), or
            ``None`` if audit recording was skipped/unavailable.
    """

    trace_id: int
    reasoning_state: str
    engineering_conclusion: Dict[str, Any]
    reasoning_steps: Tuple[str, ...]
    applied_rules: Tuple[Dict[str, str], ...]
    assumptions: Tuple[str, ...]
    warnings: Tuple[str, ...]
    limitations: Tuple[str, ...]
    evidence_status: str
    result_label: Optional[str]
    ai_explanation: Optional[str] = None
    ai_explanation_provider: Optional[str] = None
    reasoning_trace_id: Optional[int] = field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "reasoning_state": self.reasoning_state,
            "engineering_conclusion": dict(self.engineering_conclusion),
            "reasoning_steps": list(self.reasoning_steps),
            "applied_rules": list(self.applied_rules),
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "evidence_status": self.evidence_status,
            "result_label": self.result_label,
            "ai_explanation": self.ai_explanation,
            "ai_explanation_provider": self.ai_explanation_provider,
            "reasoning_trace_id": self.reasoning_trace_id,
        }


__all__ = ["REASONING_STATES", "ReasoningState", "ReasoningResult"]
