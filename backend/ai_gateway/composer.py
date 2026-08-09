"""TorqPro AI Gateway - response composer.

Faz v3.0.0-alpha.1 (AI Architecture Foundation) + Faz v3.0.0-alpha.2
(AI Retrieval & Grounding) + Faz v3.0.0-alpha.3 (AI Safety, Validation
& Explainability), per ADR-0017 Karar 5 and Karar 9, ADR-0018 Karar
8/10, and ADR-0019 Karar 1/13/15/16/17.

The composer is the last stop before a :class:`ComposedAnswer` leaves
``backend.ai_gateway``. It enforces these rules structurally, not just
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
3. (ADR-0019) It labels every grounded answer with exactly one of the
   four :class:`ResultLabel` values, computed *structurally* from
   ``evidence_check.status``/``evidence_check.calculation_result`` --
   never guessed, never left to the model. ``CALCULATED`` is assigned
   whenever a ``calculation_result`` is present, unconditionally; no
   Question Bank evidence quality or conflict can ever downgrade it
   to ``RECOMMENDED``/``ESTIMATED`` (ADR-0019 Karar 1/2, this
   module's single most important invariant).

Citation model (ADR-0018 Karar 8, extended by ADR-0019 Karar 16/17):
:func:`build_citations` renders each grounding ``EvidenceSource`` into
a short, human-readable citation string built entirely from fields
already copied verbatim from the origin domain model
(``EvidenceSource.standard_name``/``standard_clause``/
``content_version``/``source_kind``/``traceability_level`` -- see
``backend.ai_gateway.retrieval.EvidenceSource``). No citation ever
contains a synthetic identifier invented by this module. A citation
for a source whose ``traceability_level`` is not ``"APPROVED"``, or
whose ``source_kind`` is inherently low-confidence
(``oem_estimation``/``educational_simplification``), always carries an
explicit, visible qualifier -- high-confidence citations stay
unadorned, low-confidence ones are never silently presented as
equally authoritative ("mark the exception, leave the normal case
quiet").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

from backend.ai_gateway.evidence_checker import EvidenceCheckResult, EvidenceStatus
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

#: ADR-0019 Karar 15: fixed, non-fabricated note appended (never
#: prepended, never merged into the model's own text) whenever
#: ``evidence_check.status == EvidenceStatus.WARN``. Contains no
#: certainty language -- deliberately hedged wording only (ADR-0019
#: Karar 13's phrasing policy).
VALIDATION_REQUIRED_NOTE_TR = (
    "Bu yanıt, doğrulanmamış veya kısmen doğrulanmış kaynaklara "
    "dayanmaktadır; mühendislik kararı almadan önce ek doğrulama "
    "yapılması önerilir."
)
VALIDATION_REQUIRED_NOTE_EN = (
    "This answer relies on unverified or partially verified sources; "
    "additional validation is recommended before making an engineering "
    "decision."
)

#: ADR-0019 Karar 16: human-readable TR/EN labels for each
#: ``backend.question_bank.schema.SourceType`` value, reused verbatim
#: as ``EvidenceSource.source_kind`` -- no new classification, only a
#: display-text mapping for an already-existing, closed vocabulary.
_SOURCE_KIND_LABELS_TR = {
    "standard_requirement": "standart gereksinimi",
    "engineering_interpretation": "mühendislik yorumu",
    "internal_engine": "TorqPro iç motoru",
    "oem_estimation": "OEM tahmini",
    "educational_simplification": "eğitim amaçlı basitleştirme",
}
_SOURCE_KIND_LABELS_EN = {
    "standard_requirement": "standard requirement",
    "engineering_interpretation": "engineering interpretation",
    "internal_engine": "internal engine",
    "oem_estimation": "OEM estimation",
    "educational_simplification": "educational simplification",
}

#: ADR-0019 Karar 6/16: source kinds that always carry a visible
#: low-confidence qualifier in their citation, regardless of
#: ``traceability_level`` -- this module's own copy, independent of
#: ``backend.ai_gateway.evidence_checker``'s confidence-eligibility
#: allow-list (that module fails closed via a whitelist of
#: *high*-confidence kinds; this module only needs the two kinds that
#: are always low-confidence, for display purposes, so the two lists
#: are not required to be structurally identical).
_LOW_CONFIDENCE_SOURCE_KINDS = frozenset({"oem_estimation", "educational_simplification"})

_HIGH_CONFIDENCE_TRACEABILITY_LEVEL = "APPROVED"


class ResultLabel:
    """Four-value answer classification (ADR-0019 Karar 1).

    Plain string constants, matching this module's and
    ``evidence_checker.EvidenceStatus``'s existing style.

    - ``CALCULATED``: the value came from the deterministic TorqPro
      calculation engine (``calculation_result is not None``).
      Unconditional -- no evidence quality signal can prevent or
      override this label (ADR-0019 Karar 1/2).
    - ``VALIDATED``: text grounded exclusively in high-confidence
      evidence (``EvidenceStatus.PASS`` with no calculation result).
    - ``ESTIMATED``: text grounded in evidence, but at least one
      contributing source is not high confidence
      (``EvidenceStatus.WARN``).
    - ``RECOMMENDED``: reserved for model-synthesised advisory text
      that goes beyond directly-cited evidence. Not mechanically
      reachable in this phase -- doing so would require claim-level
      NLP against real model output, which does not exist yet (no
      concrete ``AIModelClient`` beyond ``FakeModelClient``/
      ``RaisingModelClient``). Defined here for forward compatibility
      and so the vocabulary is complete and documented; a future,
      separately-approved phase with a real model integration is
      expected to be the first to actually produce it.
    """

    CALCULATED = "CALCULATED"
    VALIDATED = "VALIDATED"
    ESTIMATED = "ESTIMATED"
    RECOMMENDED = "RECOMMENDED"


def _resolve_result_label(evidence_check: EvidenceCheckResult) -> Optional[str]:
    """ADR-0019 Karar 1/2: compute the single ``ResultLabel`` for a
    sufficient-evidence answer. Returns ``None`` for
    ``EvidenceStatus.FAIL`` (an insufficient-evidence notice is not a
    claim, so it is not labelled at all).

    The calculation check is deliberately the *first* and
    unconditional branch -- nothing below it can ever run for a
    calculation-backed answer.
    """
    if evidence_check.calculation_result is not None:
        return ResultLabel.CALCULATED
    if evidence_check.status == EvidenceStatus.PASS:
        return ResultLabel.VALIDATED
    if evidence_check.status == EvidenceStatus.WARN:
        return ResultLabel.ESTIMATED
    return None


def build_citations(
    evidence: Sequence[EvidenceSource], *, language: str = "tr"
) -> Tuple[str, ...]:
    """Render each ``EvidenceSource`` in ``evidence`` into a short
    citation string (ADR-0018 Karar 8, extended by ADR-0019 Karar
    16/17).

    Every token in a citation is copied verbatim from the source's own
    fields -- this function performs no paraphrasing, summarisation or
    invention of identifiers. Returns one citation per source, in the
    same order as ``evidence``.

    A citation is left unadorned (no qualifier) when the source is
    high confidence (``traceability_level == "APPROVED"`` and
    ``source_kind`` not inherently low-confidence). Otherwise, a
    parenthetical, non-fabricated qualifier is always appended: the
    source kind's own low-confidence label
    (``oem_estimation``/``educational_simplification``) and/or the
    source's own ``traceability_level`` value verbatim, when not
    ``"APPROVED"``.
    """
    is_english = language.strip().casefold() == "en"
    kind_labels = _SOURCE_KIND_LABELS_EN if is_english else _SOURCE_KIND_LABELS_TR

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

        qualifiers = []
        if source.source_kind in _LOW_CONFIDENCE_SOURCE_KINDS:
            qualifiers.append(kind_labels.get(source.source_kind, source.source_kind))
        if (
            source.traceability_level is not None
            and source.traceability_level != _HIGH_CONFIDENCE_TRACEABILITY_LEVEL
        ):
            qualifiers.append(source.traceability_level)
        if qualifiers:
            citation += f" ({', '.join(qualifiers)})"

        citations.append(citation)
    return tuple(citations)


@dataclass(frozen=True)
class ComposedAnswer:
    """Final, gateway-boundary answer shape.

    Attributes:
        text: User-facing text. Either the underlying
            ``ModelResponse.text`` verbatim (when evidence was
            sufficient -- for both ``PASS`` and ``WARN``, unedited in
            either case; see ``validation_required``/``result_label``
            below for the structured WARN signal instead) or a fixed
            insufficient-evidence notice, optionally followed by a
            "sources queried" note (ADR-0018 Karar 10) -- never
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
        result_label: (ADR-0019 Karar 1, additive, optional) One of
            :class:`ResultLabel`'s four values, or ``None`` when
            ``insufficient_evidence`` is ``True``. Defaults to
            ``None`` for backward compatibility.
        validation_required: (ADR-0019 Karar 15, additive, optional)
            ``True`` iff ``result_label == ResultLabel.ESTIMATED``
            (i.e. ``evidence_check.status == EvidenceStatus.WARN``).
            Defaults to ``False`` for backward compatibility.
    """

    text: str
    evidence: Tuple[EvidenceSource, ...]
    calculation_result: Optional[CalculationResponse]
    insufficient_evidence: bool
    model_name: Optional[str]
    citations: Tuple[str, ...] = field(default_factory=tuple)
    result_label: Optional[str] = None
    validation_required: bool = False


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

    When ``evidence_check.status == EvidenceStatus.WARN`` (ADR-0019
    Karar 15), ``ComposedAnswer.validation_required`` is set to
    ``True`` and ``result_label`` is set to ``ResultLabel.ESTIMATED``
    -- exposed as structured fields for the caller/future UI layer to
    act on. ``text`` itself is left exactly as ``model_response.text``
    in every sufficient-evidence case (PASS or WARN alike): this
    module never mutates, appends to, or otherwise edits the model's
    own text for a grounded answer (mirrors this module's existing
    rule 2 above -- "never constructs, edits ... a numeric value" is
    extended here to "never edits the model's own prose either";
    :data:`VALIDATION_REQUIRED_NOTE_TR`/``_EN`` remain available as
    fixed, pre-approved wording for a caller that wants to surface
    them, but this function does not concatenate them into ``text``
    itself).
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
            result_label=None,
            validation_required=False,
        )

    result_label = _resolve_result_label(evidence_check)
    validation_required = evidence_check.status == EvidenceStatus.WARN

    return ComposedAnswer(
        text=model_response.text,
        evidence=evidence_check.verified_sources,
        calculation_result=evidence_check.calculation_result,
        insufficient_evidence=False,
        model_name=model_response.model_name,
        citations=build_citations(evidence_check.verified_sources, language=language),
        result_label=result_label,
        validation_required=validation_required,
    )


__all__ = [
    "ComposedAnswer",
    "ResultLabel",
    "compose",
    "build_citations",
    "INSUFFICIENT_EVIDENCE_TEXT_TR",
    "INSUFFICIENT_EVIDENCE_TEXT_EN",
    "VALIDATION_REQUIRED_NOTE_TR",
    "VALIDATION_REQUIRED_NOTE_EN",
]
