"""TorqPro AI Gateway Reasoning - deterministic reasoning engine
(v3.0.0-beta.2).

``run_reasoning`` is this module's single entry point, mirroring
``backend.ai_gateway.orchestrator.handle_query``'s own "single entry
point" convention. It never imports
``backend.ai_gateway.llm_client.AIModelClient`` or any concrete
provider, and never calls ``.complete()`` -- this is the structural
enforcement of the Stage 0-approved "Engineering Reasoning must be
clearly separated from AI-generated explanation" invariant. The
optional AI-wording step lives exclusively in ``wording.py`` and is
layered on *after* this function returns, by the caller (see
``backend/api/routes/ai_gateway.py``'s new
``engineering_reasoning_endpoint``), never inside this module.

**Safety invariants enforced structurally here (not just by
convention):**

1. Every field under ``ReasoningResult.engineering_conclusion`` is
   copied verbatim from the stored Beta.1 payload
   (``record["result_json"]``) -- this module contains no arithmetic
   on any of those values (no ``+``/``-``/``*``//``, no ``round()``),
   and re-runs no engineering formula (imports neither
   ``backend.torque_recommendation.engine`` nor
   ``backend.calculation_engine``/``backend.vdi2230_core``/
   ``backend.engineering_core`` directly).
2. ``record`` (the caller-supplied, already-fetched
   ``get_recommendation_audit`` result) is never mutated -- this
   module only reads from it via ``dict.get``.
3. Fail-closed: any ``record`` this module cannot structurally
   validate (``_is_well_formed`` returns ``False``) or that carries no
   calculation evidence (``evidence_adapter.to_calculation_response``
   returns ``None``) yields
   ``ReasoningState.INSUFFICIENT_EVIDENCE`` with an empty
   ``engineering_conclusion`` -- never a guessed or partially-filled
   conclusion.
4. No engineering input is ever invented: this module takes no
   engineering parameter (diameter/pitch/load/...) as an argument at
   all -- its only per-call inputs are ``trace_id`` and the
   already-persisted ``record``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

from backend.ai_gateway.composer import compose
from backend.ai_gateway.evidence_checker import EvidenceStatus, check_evidence
from backend.ai_gateway.llm_client import ModelResponse
from backend.ai_gateway.permission import UserContext, ensure_active_user, ensure_read_only_action

from .evidence_adapter import to_calculation_response
from .models import ReasoningResult, ReasoningState

#: Fixed, always-read action name passed to ``ensure_read_only_action``
#: (mirrors ``backend/api/routes/ai_gateway.py``'s own
#: ``_QUERY_ACTION`` convention for ``POST /api/ai/query``) -- never
#: derived from request input, so the existing write/approval-action
#: guard is genuinely exercised on every reasoning request.
REASONING_ACTION = "reason"

#: Fields copied verbatim from the stored Beta.1 payload into
#: ``ReasoningResult.engineering_conclusion``. A fixed, closed list --
#: this module never invents an additional field, and never omits one
#: of these when present in the stored payload.
_CONCLUSION_FIELDS = (
    "recommended_torque",
    "unit",
    "calculated_torque",
    "preload_n",
    "allowable_range",
    "status",
    "confidence",
    "readiness",
    "coverage_percent",
    "critical_findings",
)

#: ``model_name`` used for the internal, discarded ``ModelResponse``
#: passed to ``compose()`` purely to reuse its ``ResultLabel``
#: resolution (see ``_resolve_result_label`` below) -- never surfaced
#: to a caller as if it were a real AI provider, and never equal to
#: any real ``AIModelClient.name`` value registered in
#: ``backend.ai_gateway.providers.registry``.
_INTERNAL_LABEL_RESOLUTION_MODEL_NAME = "reasoning-internal-label-resolution"


def _is_well_formed(record: Optional[Dict[str, Any]]) -> bool:
    """Structural validation only -- never a value/range check (that
    remains Beta.1's own, already-tested responsibility). Returns
    ``False`` for anything this module cannot safely read a
    conclusion from: a missing record, a non-dict ``result_json``, or
    a missing ``status`` key (the one field every downstream branch in
    this module depends on)."""
    if not isinstance(record, dict):
        return False
    result_json = record.get("result_json")
    if not isinstance(result_json, dict):
        return False
    if "status" not in result_json:
        return False
    return True


def _build_engineering_conclusion(result_json: Dict[str, Any]) -> Dict[str, Any]:
    """Verbatim copy of the fixed field set (see ``_CONCLUSION_FIELDS``)
    -- a field absent from ``result_json`` is simply absent from the
    returned dict, never filled with a guessed default."""
    return {
        field_name: result_json[field_name]
        for field_name in _CONCLUSION_FIELDS
        if field_name in result_json
    }


def _resolve_result_label(
    evidence_status: str, calculation_response: Optional[Any]
) -> Optional[str]:
    """Resolve ``ResultLabel`` by reusing
    ``backend.ai_gateway.composer.compose`` itself -- not by
    reimplementing its label rule a second time.

    An internal, never-surfaced placeholder ``ModelResponse`` is
    passed in; only ``ComposedAnswer.result_label`` is read back from
    the result -- ``ComposedAnswer.text`` is deliberately discarded
    (see module docstring: AI-generated wording never originates from
    this function). This is legitimate reuse of ``compose()`` as
    designed, not a misuse of its "final answer text" role, because
    the text half of its output is simply never looked at here.
    ``calculation_response`` is passed through exactly as produced by
    ``evidence_adapter.to_calculation_response`` -- never a synthetic
    stand-in object -- so this stays a genuine
    ``Optional[CalculationResponse]`` all the way into ``compose()``.
    """
    from backend.ai_gateway.evidence_checker import EvidenceCheckResult

    # Reconstructing the minimal EvidenceCheckResult compose() needs:
    # only .has_sufficient_evidence/.calculation_result/.status are
    # read by compose()'s label-resolution branch (see that module's
    # _resolve_result_label). verified_sources/notes/
    # contributing_source_types are irrelevant to label resolution and
    # are left at their dataclass defaults.
    evidence_check = EvidenceCheckResult(
        has_sufficient_evidence=evidence_status != EvidenceStatus.FAIL,
        verified_sources=(),
        calculation_result=calculation_response,
        status=evidence_status,
    )
    dummy_response = ModelResponse(text="", model_name=_INTERNAL_LABEL_RESOLUTION_MODEL_NAME)
    composed = compose(dummy_response, evidence_check)
    return composed.result_label


def _build_reasoning_steps(
    *,
    reasoning_state: str,
    trace_id: int,
    result_json: Dict[str, Any],
) -> Tuple[str, ...]:
    """Deterministic, template-built sentences -- no LLM, no free-text
    generation, mirrors
    ``backend.torque_recommendation.explainability.build_explanation``'s
    own "plain string formatting" discipline. Every interpolated value
    is read from ``result_json`` verbatim; nothing here is computed."""
    if reasoning_state == ReasoningState.INSUFFICIENT_EVIDENCE:
        return (
            f"trace_id={trace_id} için yeterli mühendislik kanıtı bulunamadı; "
            "reasoning üretilmedi (fail-closed).",
        )

    status = result_json.get("status")
    confidence = result_json.get("confidence")
    readiness = result_json.get("readiness")
    steps = [
        f"trace_id={trace_id}: Beta.1 Torque Recommendation Engine status={status!r}, "
        f"confidence={confidence!r}, readiness={readiness!r}.",
    ]

    if reasoning_state == ReasoningState.SUPPORTED:
        recommended_torque = result_json.get("recommended_torque")
        unit = result_json.get("unit")
        steps.append(
            f"Önerilen tork değeri {recommended_torque} {unit} olarak deterministik "
            "hesaplama motorundan alındı; bu değer reasoning katmanı tarafından "
            "yeniden hesaplanmadı veya değiştirilmedi."
        )
        if result_json.get("warnings"):
            steps.append(
                "Hesaplama motoru tarafından üretilen uyarılar mevcut; "
                "bkz. warnings alanı."
            )
    elif reasoning_state == ReasoningState.UNSUPPORTED:
        critical_findings = result_json.get("critical_findings") or []
        if critical_findings:
            steps.append(
                "Öneri, deterministik motor tarafından kritik bulgular nedeniyle "
                "geri tutuldu (fail-closed withholding); bkz. critical_findings alanı."
            )
        else:
            steps.append(
                "Öneri, deterministik motor tarafından hesaplanabilir bir tork "
                "değeri bulunamadığı için geri tutuldu."
            )

    return tuple(steps)


def run_reasoning(
    trace_id: int,
    record: Optional[Dict[str, Any]],
    *,
    user: UserContext,
) -> ReasoningResult:
    """Deterministic, AI-free reasoning over an already-fetched Beta.1
    audit ``record`` (the dict returned by
    ``backend.torque_recommendation.audit.get_recommendation_audit``,
    or ``None``/malformed when the caller could not read a well-formed
    row -- see that function's own "corrupt row" handling note in
    ``backend/api/routes/ai_gateway.py``).

    This function performs **no I/O of its own** (no DB connection, no
    network call) -- exactly like
    ``backend.torque_recommendation.engine.recommend_torque``'s own
    "takes no sqlite3.Connection" design and
    ``backend.ai_gateway.orchestrator.handle_query``'s "caller supplies
    an already-open connection" convention, kept here even though this
    function needs no connection at all: trivially testable, no
    lifecycle to manage.

    Raises ``backend.ai_gateway.exceptions.PermissionDeniedError``
    (never caught here -- propagates to the caller, mirroring
    ``handle_query``'s own permission-step behaviour) if ``user`` is
    not active. Ownership/cross-user authorization for ``trace_id`` is
    the caller's (HTTP route's) responsibility -- this function has no
    HTTP/request concept and is never given another user's data
    without the caller already having authorized that access.
    """
    ensure_active_user(user)
    ensure_read_only_action(REASONING_ACTION)

    if not _is_well_formed(record):
        return ReasoningResult(
            trace_id=trace_id,
            reasoning_state=ReasoningState.INSUFFICIENT_EVIDENCE,
            engineering_conclusion={},
            reasoning_steps=_build_reasoning_steps(
                reasoning_state=ReasoningState.INSUFFICIENT_EVIDENCE,
                trace_id=trace_id,
                result_json={},
            ),
            applied_rules=(),
            assumptions=(),
            warnings=(),
            limitations=(),
            evidence_status=EvidenceStatus.FAIL,
            result_label=None,
        )

    result_json = record["result_json"]
    calculation_response = to_calculation_response(record)
    evidence_check = check_evidence((), calculation_response)

    beta1_status = result_json.get("status")
    if evidence_check.status == EvidenceStatus.FAIL:
        reasoning_state = ReasoningState.INSUFFICIENT_EVIDENCE
    elif beta1_status == "recommended":
        reasoning_state = ReasoningState.SUPPORTED
    elif beta1_status == "not_applicable":
        reasoning_state = ReasoningState.UNSUPPORTED
    else:
        # Unrecognised/unexpected status string: fail closed rather
        # than guess which of SUPPORTED/UNSUPPORTED it might mean.
        reasoning_state = ReasoningState.INSUFFICIENT_EVIDENCE

    if reasoning_state == ReasoningState.INSUFFICIENT_EVIDENCE:
        engineering_conclusion: Dict[str, Any] = {}
        applied_rules: Tuple[Dict[str, str], ...] = ()
        assumptions: Tuple[str, ...] = ()
        warnings: Tuple[str, ...] = ()
        limitations: Tuple[str, ...] = ()
    else:
        engineering_conclusion = _build_engineering_conclusion(result_json)
        applied_rules = tuple(
            {
                "formula_id": str(trace.get("formula_id", "")),
                "classification": str(trace.get("classification", "")),
                "validation_status": str(trace.get("validation_status", "")),
            }
            for trace in (result_json.get("calculation_source") or [])
        )
        assumptions = tuple(result_json.get("assumptions") or ())
        warnings = tuple(result_json.get("warnings") or ())
        explanation = result_json.get("explanation") or {}
        limitations = tuple(explanation.get("limitations") or ())

    result_label = _resolve_result_label(evidence_check.status, calculation_response)

    return ReasoningResult(
        trace_id=trace_id,
        reasoning_state=reasoning_state,
        engineering_conclusion=engineering_conclusion,
        reasoning_steps=_build_reasoning_steps(
            reasoning_state=reasoning_state,
            trace_id=trace_id,
            result_json=result_json,
        ),
        applied_rules=applied_rules,
        assumptions=assumptions,
        warnings=warnings,
        limitations=limitations,
        evidence_status=evidence_check.status,
        result_label=result_label,
    )


def with_ai_explanation(
    reasoning_result: ReasoningResult,
    *,
    ai_explanation: Optional[str],
    ai_explanation_provider: Optional[str],
) -> ReasoningResult:
    """Return a new ``ReasoningResult`` with only the two AI-wording
    fields replaced -- every deterministic field
    (``engineering_conclusion``/``reasoning_steps``/``applied_rules``/
    ``evidence_status``/``result_label``/...) is carried over
    unchanged via ``dataclasses.replace``. The only function in this
    module that ever sets ``ai_explanation``; ``run_reasoning`` itself
    always leaves it ``None``, structurally guaranteeing the
    deterministic path never depends on this function having been
    called."""
    return replace(
        reasoning_result,
        ai_explanation=ai_explanation,
        ai_explanation_provider=ai_explanation_provider,
    )


__all__ = ["REASONING_ACTION", "run_reasoning", "with_ai_explanation"]
