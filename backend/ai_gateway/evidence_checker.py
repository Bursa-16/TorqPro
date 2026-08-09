"""TorqPro AI Gateway - evidence checker.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 1
(evidence-checker as a mandatory gate in the orchestration pipeline)
and the SDS §4 principle it operationalizes: "Insufficient evidence
response when sources are unavailable."

Foundation-phase scope (deliberately limited -- ADR-0019 owns the
full claim-level evidence-checking design in a later phase): this
module does not perform natural-language claim extraction against
``ModelResponse.text`` (there is no real ``AIModelClient`` integrated
yet, per ADR-0017 Karar 4/12). What it *does* guarantee, and what
``backend.ai_gateway.composer`` depends on absolutely, is the
structural precondition every later, richer evidence-checking design
must also satisfy: an answer is never presented as grounded unless at
least one retrieved ``EvidenceSource`` or a real
``CalculationResponse`` backs it. Zero of either is not an error --
it is the designed "insufficient evidence" outcome (ADR-0017 Karar 9,
case 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse


@dataclass(frozen=True)
class EvidenceCheckResult:
    """Outcome of checking whether a response has grounding.

    Attributes:
        has_sufficient_evidence: ``True`` iff at least one
            ``EvidenceSource`` was retrieved or a ``calculation_result``
            is present.
        verified_sources: The evidence sources considered as
            grounding for this response (empty when
            ``has_sufficient_evidence`` is ``False``).
        calculation_result: Passed through unmodified from the input
            -- never inspected for numeric correctness here (that is
            the deterministic engine's own responsibility; this
            checker only confirms *presence*, per ADR-0017 Karar 5).
        notes: Machine-readable reason codes, not user-facing text
            (``backend.ai_gateway.composer`` owns user-facing
            wording).
    """

    has_sufficient_evidence: bool
    verified_sources: Tuple[EvidenceSource, ...]
    calculation_result: Optional[CalculationResponse]
    notes: Tuple[str, ...] = field(default_factory=tuple)


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
    """
    has_evidence = bool(sources) or calculation_result is not None
    notes: Tuple[str, ...] = () if has_evidence else ("no_retrieval_sources_or_calculation_result",)
    return EvidenceCheckResult(
        has_sufficient_evidence=has_evidence,
        verified_sources=tuple(sources) if has_evidence else (),
        calculation_result=calculation_result if has_evidence else None,
        notes=notes,
    )


__all__ = ["EvidenceCheckResult", "check_evidence"]
