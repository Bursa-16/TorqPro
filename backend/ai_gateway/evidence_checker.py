"""TorqPro AI Gateway - evidence checker.

Faz v3.0.0-alpha.1 (AI Architecture Foundation) + Faz v3.0.0-alpha.2
(AI Retrieval & Grounding), per ADR-0017 Karar 1 (evidence-checker as
a mandatory gate in the orchestration pipeline), ADR-0018 Karar 9/11,
and the SDS §4 principle this module operationalizes: "Insufficient
evidence response when sources are unavailable."

Scope (deliberately limited -- ADR-0019 owns the full claim-level
evidence-checking design in a later phase): this module does not
perform natural-language claim extraction against
``ModelResponse.text`` (there is no real ``AIModelClient`` integrated
yet, per ADR-0017 Karar 4/12). What it *does* guarantee, and what
``backend.ai_gateway.composer`` depends on absolutely, is the
structural precondition every later, richer evidence-checking design
must also satisfy: an answer is never presented as grounded unless at
least one retrieved ``EvidenceSource`` or a real
``CalculationResponse`` backs it. Zero of either is not an error --
it is the designed "insufficient evidence" outcome (ADR-0017 Karar 9,
case 2).

Conflicting-evidence handling (ADR-0018 Karar 11): this module makes
no attempt to detect, resolve or silently prefer one
``EvidenceSource`` over another -- every source passed in is retained
in ``verified_sources`` unchanged and unfiltered, and a
``calculation_result``, when present, is always retained alongside
them, never displacing them. ADR-0018 Karar 11's rule that "the
deterministic calculation result is always authoritative for numeric
claims" is enforced downstream, at the composer boundary (numeric
values are only ever read from ``calculation_result``, never from an
``EvidenceSource``'s text) -- this module's only conflict-relevant
job is to never drop a source, so no information is silently lost
before it reaches the composer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Sequence, Tuple

from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse

#: Fixed source-type label for a deterministic calculation result,
#: used only inside ``contributing_source_types`` -- never written
#: into an actual ``EvidenceSource`` (ADR-0018 Karar 17: a
#: ``CalculationResponse`` is never converted into an
#: ``EvidenceSource``).
_CALCULATION_SOURCE_TYPE_LABEL = "calculation_engine"


@dataclass(frozen=True)
class EvidenceCheckResult:
    """Outcome of checking whether a response has grounding.

    Attributes:
        has_sufficient_evidence: ``True`` iff at least one
            ``EvidenceSource`` was retrieved or a ``calculation_result``
            is present.
        verified_sources: The evidence sources considered as
            grounding for this response (empty when
            ``has_sufficient_evidence`` is ``False``). Every source
            passed to :func:`check_evidence` is retained here
            unfiltered -- this module never drops or prefers one
            source over another (ADR-0018 Karar 11).
        calculation_result: Passed through unmodified from the input
            -- never inspected for numeric correctness here (that is
            the deterministic engine's own responsibility; this
            checker only confirms *presence*, per ADR-0017 Karar 5).
        notes: Machine-readable reason codes, not user-facing text
            (``backend.ai_gateway.composer`` owns user-facing
            wording).
        contributing_source_types: (ADR-0018 Karar 9, additive) The
            distinct ``EvidenceSource.source_type`` values present in
            ``verified_sources``, plus
            ``"calculation_engine"`` when ``calculation_result`` is
            present. Empty when ``has_sufficient_evidence`` is
            ``False``. Lets ``composer``/``audit`` know *which kinds*
            of grounding backed an answer without re-deriving it from
            ``verified_sources`` each time.
    """

    has_sufficient_evidence: bool
    verified_sources: Tuple[EvidenceSource, ...]
    calculation_result: Optional[CalculationResponse]
    notes: Tuple[str, ...] = field(default_factory=tuple)
    contributing_source_types: FrozenSet[str] = field(default_factory=frozenset)


def check_evidence(
    sources: Sequence[EvidenceSource],
    calculation_result: Optional[CalculationResponse],
) -> EvidenceCheckResult:
    """Evaluate whether ``sources``/``calculation_result`` are
    sufficient grounding for a composed answer.

    This function never raises for the "no evidence" case -- an
    unsuccessful check is a normal return value
    (``has_sufficient_evidence=False``), consistent with ADR-0017
    Karar 9's rule that "insufficient evidence" is an expected
    outcome, not an error condition.

    Every element of ``sources`` is retained in the result unfiltered
    when evidence is sufficient -- this function performs no
    deduplication, ranking or conflict resolution among sources
    (ADR-0018 Karar 11; that remains explicitly out of scope for this
    phase).
    """
    has_evidence = bool(sources) or calculation_result is not None
    notes: Tuple[str, ...] = () if has_evidence else ("no_retrieval_sources_or_calculation_result",)

    if not has_evidence:
        return EvidenceCheckResult(
            has_sufficient_evidence=False,
            verified_sources=(),
            calculation_result=None,
            notes=notes,
            contributing_source_types=frozenset(),
        )

    contributing_source_types = {source.source_type for source in sources}
    if calculation_result is not None:
        contributing_source_types.add(_CALCULATION_SOURCE_TYPE_LABEL)

    return EvidenceCheckResult(
        has_sufficient_evidence=True,
        verified_sources=tuple(sources),
        calculation_result=calculation_result,
        notes=notes,
        contributing_source_types=frozenset(contributing_source_types),
    )


__all__ = ["EvidenceCheckResult", "check_evidence"]
