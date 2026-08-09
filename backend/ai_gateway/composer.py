"""TorqPro AI Gateway - response composer.

Faz v3.0.0-alpha.1 (AI Architecture Foundation) + Faz v3.0.0-alpha.2
(AI Retrieval & Grounding), per ADR-0017 Karar 5 and Karar 9, and
ADR-0018 Karar 8/10.

The composer is the last stop before a :class:`ComposedAnswer` leaves
``backend.ai_gateway``. It enforces two rules structurally, not just
by convention:

1. It never returns a ``ModelResponse.text`` to the caller unless
   ``backend.ai_gateway.evidence_checker.check_evidence`` reported
   sufficient evidence -- an insufficient-evidence result always
   yields the same fixed, non-fabricated notice
   (:data:`INSUFFICIENT_EVIDENCE_TEXT_TR`/``_EN``), never the model's
   own text. ADR-0018 Karar 10 permits appending a short, separate
   "which sources were queried" note after that fixed notice -- the
   fixed notice's own wording never changes.
2. It never constructs, edits or rounds a numeric engineering value.
   ``ComposedAnswer.calculation_result`` is always either ``None`` or
   the exact, unmodified ``CalculationResponse`` that
   ``backend.ai_gateway.evidence_checker`` passed through from
   ``backend.ai_gateway.tools.calculation_tool``. The composer's
   ``text`` field may describe that result in prose (a later,
   real-model phase's job), but nothing in this module's own code
   touches ``CalculationResult.value``.

Citation model (ADR-0018 Karar 8): :func:`build_citations` renders
each grounding ``EvidenceSource`` into a short, human-readable
citation string built entirely from fields already copied verbatim
from the origin domain model (``EvidenceSource.standard_name``/
``standard_clause``/``content_version`` etc. -- see
``backend.ai_gateway.retrieval.EvidenceSource``). No citation ever
contains a synthetic identifier invented by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

from backend.ai_gateway.evidence_checker import EvidenceCheckResult
from backend.ai_gateway.llm_client import ModelResponse
from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse

#: Fixed, non-fabricated notices for the "insufficient evidence"
#: outcome (ADR-0017 Karar 9, case 2 / SDS §4). Bilingual, matching
#: TorqPro's existing TR/EN parity discipline. Never interpolated
#: with model output -- always used verbatim. ADR-0018 Karar 10: this
#: exact wording never changes; any additional "sources queried" note
#: is appended after it, never merged into it.
INSUFFICIENT_EVIDENCE_TEXT_TR = (
    "Bu soru için onaylı (validated) TorqPro kaynağı veya mühendislik "
    "hesaplama sonucu bulunamadı. Kanıtsız bir yanıt üretilmedi."
)
INSUFFICIENT_EVIDENCE_TEXT_EN = (
    "No approved (validated) TorqPro source or engineering calculation "
    "result was found for this question. No ungrounded answer was produced."
)

#: Templates for the ADR-0018 Karar 10 "which sources were queried"
#: note appended after the fixed insufficient-evidence notice. Never
#: used alone -- always appended, never replaces the fixed text above.
_ATTEMPTED_SOURCES_NOTE_TR = "Aranan kaynak türleri: {sources}."
_ATTEMPTED_SOURCES_NOTE_EN = "Source types searched: {sources}."


def build_citations(evidence: Sequence[EvidenceSource]) -> Tuple[str, ...]:
    """Render each ``EvidenceSource`` in ``evidence`` into a short
    citation string (ADR-0018 Karar 8).

    Every token in a citation is copied verbatim from the source's own
    fields -- this function performs no paraphrasing, summarisation or
    invention of identifiers. Returns one citation per source, in the
    same order as ``evidence``.
    """
    citations = []
    for source in evidence:
        parts = [f"[{source.source_type} #{source.source_id}"]
        if source.content_version is not None:
            parts.append(f" v{source.content_version}")
        parts.append("]")
        citation = "".join(parts)
        if source.standard_name:
            citation += f" {source.standard_name}"
            if source.standard_clause:
                citation += f" {source.standard_clause}"
        citations.append(citation)
    return tuple(citations)


@dataclass(frozen=True)
class ComposedAnswer:
    """Final, gateway-boundary answer shape.

    Attributes:
        text: User-facing text. Either the underlying
            ``ModelResponse.text`` (when evidence was sufficient) or
            a fixed insufficient-evidence notice, optionally followed
            by a "sources queried" note (ADR-0018 Karar 10) -- never
            anything else.
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
        citations: (ADR-0018 Karar 8, additive, optional) One citation
            string per entry in ``evidence``, same order, built by
            :func:`build_citations`. Empty when ``insufficient_evidence``
            is ``True``. Defaults to an empty tuple for backward
            compatibility with any v3.0.0-alpha.1-style construction.
    """

    text: str
    evidence: Tuple[EvidenceSource, ...]
    calculation_result: Optional[CalculationResponse]
    insufficient_evidence: bool
    model_name: Optional[str]
    citations: Tuple[str, ...] = field(default_factory=tuple)


def compose(
    model_response: ModelResponse,
    evidence_check: EvidenceCheckResult,
    *,
    language: str = "tr",
    attempted_source_types: Sequence[str] = (),
) -> ComposedAnswer:
    """Produce the final :class:`ComposedAnswer` for one AI-gateway
    interaction.

    ``model_response`` is ignored entirely (not read, not referenced
    in the returned text) when ``evidence_check.has_sufficient_evidence``
    is ``False`` -- this is the structural enforcement of ADR-0017's
    "no ungrounded response" rule, not a formatting choice.

    ``attempted_source_types`` (ADR-0018 Karar 10, optional, default
    empty) names which retrieval adaptors were actually queried for
    this interaction. When supplied and evidence is insufficient, a
    short note listing those source types is appended after the fixed
    insufficient-evidence notice; the fixed notice's own wording is
    never altered. Ignored when evidence is sufficient (no note is
    needed when an answer is already grounded).
    """
    if not evidence_check.has_sufficient_evidence:
        is_english = language.strip().casefold() == "en"
        notice = INSUFFICIENT_EVIDENCE_TEXT_EN if is_english else INSUFFICIENT_EVIDENCE_TEXT_TR
        if attempted_source_types:
            note_template = _ATTEMPTED_SOURCES_NOTE_EN if is_english else _ATTEMPTED_SOURCES_NOTE_TR
            note = note_template.format(sources=", ".join(attempted_source_types))
            notice = f"{notice} {note}"
        return ComposedAnswer(
            text=notice,
            evidence=(),
            calculation_result=None,
            insufficient_evidence=True,
            model_name=None,
            citations=(),
        )

    return ComposedAnswer(
        text=model_response.text,
        evidence=evidence_check.verified_sources,
        calculation_result=evidence_check.calculation_result,
        insufficient_evidence=False,
        model_name=model_response.model_name,
        citations=build_citations(evidence_check.verified_sources),
    )


__all__ = [
    "ComposedAnswer",
    "compose",
    "build_citations",
    "INSUFFICIENT_EVIDENCE_TEXT_TR",
    "INSUFFICIENT_EVIDENCE_TEXT_EN",
]
