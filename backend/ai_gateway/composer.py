"""TorqPro AI Gateway - response composer.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 5
and Karar 9.

The composer is the last stop before a :class:`ComposedAnswer` leaves
``backend.ai_gateway``. It enforces two rules structurally, not just
by convention:

1. It never returns a ``ModelResponse.text`` to the caller unless
   ``backend.ai_gateway.evidence_checker.check_evidence`` reported
   sufficient evidence -- an insufficient-evidence result always
   yields the same fixed, non-fabricated notice
   (:data:`INSUFFICIENT_EVIDENCE_TEXT_TR`/``_EN``), never the model's
   own text.
2. It never constructs, edits or rounds a numeric engineering value.
   ``ComposedAnswer.calculation_result`` is always either ``None`` or
   the exact, unmodified ``CalculationResponse`` that
   ``backend.ai_gateway.evidence_checker`` passed through from
   ``backend.ai_gateway.tools.calculation_tool``. The composer's
   ``text`` field may describe that result in prose (a later,
   real-model phase's job), but nothing in this module's own code
   touches ``CalculationResult.value``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from backend.ai_gateway.evidence_checker import EvidenceCheckResult
from backend.ai_gateway.llm_client import ModelResponse
from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse

#: Fixed, non-fabricated notices for the "insufficient evidence"
#: outcome (ADR-0017 Karar 9, case 2 / SDS §4). Bilingual, matching
#: TorqPro's existing TR/EN parity discipline. Never interpolated
#: with model output -- always used verbatim.
INSUFFICIENT_EVIDENCE_TEXT_TR = (
    "Bu soru için onaylı (validated) TorqPro kaynağı veya mühendislik "
    "hesaplama sonucu bulunamadı. Kanıtsız bir yanıt üretilmedi."
)
INSUFFICIENT_EVIDENCE_TEXT_EN = (
    "No approved (validated) TorqPro source or engineering calculation "
    "result was found for this question. No ungrounded answer was produced."
)


@dataclass(frozen=True)
class ComposedAnswer:
    """Final, gateway-boundary answer shape.

    Attributes:
        text: User-facing text. Either the underlying
            ``ModelResponse.text`` (when evidence was sufficient) or
            a fixed insufficient-evidence notice -- never anything
            else.
        evidence: The sources this answer is grounded in (empty when
            ``insufficient_evidence`` is ``True``).
        calculation_result: Unmodified deterministic-engine output,
            when one backs this answer; otherwise ``None``.
        insufficient_evidence: ``True`` iff this answer is the fixed
            insufficient-evidence notice rather than a grounded
            response.
        model_name: Which ``AIModelClient`` produced the underlying
            text (``None`` when ``insufficient_evidence`` is
            ``True``, since no model text was used).
    """

    text: str
    evidence: Tuple[EvidenceSource, ...]
    calculation_result: Optional[CalculationResponse]
    insufficient_evidence: bool
    model_name: Optional[str]


def compose(
    model_response: ModelResponse,
    evidence_check: EvidenceCheckResult,
    *,
    language: str = "tr",
) -> ComposedAnswer:
    """Produce the final :class:`ComposedAnswer` for one AI-gateway
    interaction.

    ``model_response`` is ignored entirely (not read, not referenced
    in the returned text) when ``evidence_check.has_sufficient_evidence``
    is ``False`` -- this is the structural enforcement of ADR-0017's
    "no ungrounded response" rule, not a formatting choice.
    """
    if not evidence_check.has_sufficient_evidence:
        notice = (
            INSUFFICIENT_EVIDENCE_TEXT_EN
            if language.strip().casefold() == "en"
            else INSUFFICIENT_EVIDENCE_TEXT_TR
        )
        return ComposedAnswer(
            text=notice,
            evidence=(),
            calculation_result=None,
            insufficient_evidence=True,
            model_name=None,
        )

    return ComposedAnswer(
        text=model_response.text,
        evidence=evidence_check.verified_sources,
        calculation_result=evidence_check.calculation_result,
        insufficient_evidence=False,
        model_name=model_response.model_name,
    )


__all__ = [
    "ComposedAnswer",
    "compose",
    "INSUFFICIENT_EVIDENCE_TEXT_TR",
    "INSUFFICIENT_EVIDENCE_TEXT_EN",
]
