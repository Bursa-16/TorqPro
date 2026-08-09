"""TorqPro AI Gateway - evidence checker.

Faz v3.0.0-alpha.1 (AI Architecture Foundation) + Faz v3.0.0-alpha.2
(AI Retrieval & Grounding) + Faz v3.0.0-alpha.3 (AI Safety, Validation
& Explainability), per ADR-0017 Karar 1 (evidence-checker as a
mandatory gate in the orchestration pipeline), ADR-0018 Karar 9/11,
ADR-0019 Karar 5/6/7/19, and the SDS §4 principle this module
operationalizes: "Insufficient evidence response when sources are
unavailable."

Scope (deliberately limited -- claim-level NLP evidence-checking
remains out of scope for as long as there is no real
``AIModelClient``, per ADR-0017 Karar 4/12): this module does not
perform natural-language claim extraction against
``ModelResponse.text``. What it *does* guarantee, and what
``backend.ai_gateway.composer`` depends on absolutely, is the
structural precondition every later, richer evidence-checking design
must also satisfy: an answer is never presented as grounded unless at
least one retrieved ``EvidenceSource`` or a real
``CalculationResponse`` backs it. Zero of either is not an error --
it is the designed "insufficient evidence" outcome (ADR-0017 Karar 9,
case 2).

Conflicting-evidence handling (ADR-0018 Karar 11 / ADR-0019 Karar 8):
this module makes no attempt to detect, resolve or silently prefer
one ``EvidenceSource`` over another -- every source passed in is
retained in ``verified_sources`` unchanged and unfiltered, and a
``calculation_result``, when present, is always retained alongside
them, never displacing them. ADR-0018 Karar 11's rule that "the
deterministic calculation result is always authoritative for numeric
claims" is enforced downstream, at the composer boundary (numeric
values are only ever read from ``calculation_result``, never from an
``EvidenceSource``'s text) -- this module's only conflict-relevant
job is to never drop a source, so no information is silently lost
before it reaches the composer. Transparency (every contributing
source visible in the audit trail), not automatic resolution, is the
chosen safeguard against conflicting evidence.

ADR-0019 safety/validation layer (this phase's addition): in addition
to the binary ``has_sufficient_evidence`` question, this module now
also classifies *how well-grounded* a sufficient answer is, into a
three-value :class:`EvidenceStatus` (``PASS``/``WARN``/``FAIL``). This
classification reuses TorqPro's own existing five-value confidence
vocabulary (``backend.engineering_core.trace``'s
APPROVED/PROVISIONAL/EXPERIMENTAL/DEPRECATED/UNVERIFIED, surfaced on
every ``EvidenceSource.traceability_level`` since ADR-0018) and the
existing ``EvidenceSource.source_kind`` (``backend.question_bank.
schema.SourceType``) -- no new confidence vocabulary, no numeric
score, is invented here (ADR-0019 Karar 5).

Fail-closed by design (ADR-0019 Karar 19): a ``calculation_result`` is
*unconditionally* ``PASS`` -- no amount of Question Bank evidence,
regardless of quality or quantity, can downgrade a calculation-backed
answer, and no amount of Question Bank evidence, regardless of
quality, can substitute for one. When there is no calculation result,
a source only counts as "high confidence" when its
``traceability_level`` is exactly ``"APPROVED"`` *and* its
``source_kind`` is not one of TorqPro's own inherently-non-authoritative
kinds (``oem_estimation``, ``educational_simplification`` -- see
``backend.question_bank.schema.SourceType``'s own docstring: an
OEM-estimation source is, by that schema's own definition, mutually
exclusive with a populated standard reference). Any source with an
unrecognised/``None`` ``traceability_level`` or ``source_kind`` is
treated as **not** high confidence -- ambiguity never rounds up to
"safe".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Sequence, Tuple

from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse

#: Fixed source-type label for a deterministic calculation result,
#: used only inside ``contributing_source_types`` -- never written
#: into an actual ``EvidenceSource`` (ADR-0018 Karar 17 / ADR-0019
#: Karar 12: a ``CalculationResponse`` is never converted into an
#: ``EvidenceSource``).
_CALCULATION_SOURCE_TYPE_LABEL = "calculation_engine"

#: The one ``traceability_level`` value that counts as high confidence
#: (ADR-0019 Karar 6). Reuses ``backend.engineering_core.trace``'s own
#: vocabulary verbatim -- not redefined here.
_HIGH_CONFIDENCE_TRACEABILITY_LEVEL = "APPROVED"

#: The only ``source_kind`` values that *can* count as high confidence
#: (ADR-0019 Karar 6, fail-closed per Karar 5/19): a closed allow-list,
#: not "everything except the low-confidence set" -- an unrecognised
#: or future/unknown ``source_kind`` value must never silently pass as
#: high confidence just because it also isn't in
#: ``_LOW_CONFIDENCE_SOURCE_KINDS``. Values are
#: ``backend.question_bank.schema.SourceType`` members, reused
#: verbatim, not redefined here.
_HIGH_CONFIDENCE_ELIGIBLE_SOURCE_KINDS = frozenset(
    {"standard_requirement", "engineering_interpretation", "internal_engine"}
)


class EvidenceStatus:
    """Three-value safety/validation outcome of :func:`check_evidence`
    (ADR-0019 Karar 7).

    Plain string constants (matching this module's existing style,
    e.g. ``_CALCULATION_SOURCE_TYPE_LABEL`` above) rather than an
    ``enum.Enum`` -- kept comparable-by-value and trivially
    serialisable for the audit trail (``backend.ai_gateway.audit``)
    without an extra (de)serialisation step.

    - ``PASS``: the answer is backed by a ``calculation_result``
      (unconditionally, regardless of any Question Bank evidence
      quality) or by evidence sources that are *all* high confidence.
    - ``WARN``: the answer is backed by at least one evidence source,
      but not all contributing sources are high confidence.
    - ``FAIL``: no evidence source and no calculation result at all
      (ADR-0017 Karar 9 case 2's "insufficient evidence" outcome).
    """

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


def _is_high_confidence(source: EvidenceSource) -> bool:
    """ADR-0019 Karar 6: a source counts as high confidence iff its
    ``traceability_level`` is exactly ``"APPROVED"`` *and* its
    ``source_kind`` is one of the closed set of eligible kinds
    (``_HIGH_CONFIDENCE_ELIGIBLE_SOURCE_KINDS``). Any other value --
    including ``None``, ``"PROVISIONAL"``, ``"EXPERIMENTAL"``,
    ``"DEPRECATED"``, ``"UNVERIFIED"``, an unrecognised
    ``traceability_level`` string, or an unrecognised/``None``
    ``source_kind`` -- fails closed to ``False`` (ADR-0019 Karar
    5/19). Note this is a whitelist on ``source_kind``, not merely
    "not in the low-confidence set": an unrecognised future
    ``source_kind`` value must never silently pass just because it
    also isn't ``oem_estimation``/``educational_simplification``."""
    if source.traceability_level != _HIGH_CONFIDENCE_TRACEABILITY_LEVEL:
        return False
    return source.source_kind in _HIGH_CONFIDENCE_ELIGIBLE_SOURCE_KINDS


@dataclass(frozen=True)
class EvidenceCheckResult:
    """Outcome of checking whether a response has grounding.

    Attributes:
        has_sufficient_evidence: ``True`` iff at least one
            ``EvidenceSource`` was retrieved or a ``calculation_result``
            is present. Kept for backward compatibility with
            v3.0.0-alpha.1/alpha.2 callers; always equals
            ``status != EvidenceStatus.FAIL``.
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
        status: (ADR-0019 Karar 7, additive) One of
            :class:`EvidenceStatus`'s three values. See that class's
            docstring for the exact PASS/WARN/FAIL rule.
    """

    has_sufficient_evidence: bool
    verified_sources: Tuple[EvidenceSource, ...]
    calculation_result: Optional[CalculationResponse]
    notes: Tuple[str, ...] = field(default_factory=tuple)
    contributing_source_types: FrozenSet[str] = field(default_factory=frozenset)
    status: str = EvidenceStatus.FAIL


def check_evidence(
    sources: Sequence[EvidenceSource],
    calculation_result: Optional[CalculationResponse],
) -> EvidenceCheckResult:
    """Evaluate whether ``sources``/``calculation_result`` are
    sufficient grounding for a composed answer, and how well-grounded
    (PASS/WARN/FAIL) that grounding is (ADR-0019 Karar 7).

    This function never raises for the "no evidence" case -- an
    unsuccessful check is a normal return value
    (``has_sufficient_evidence=False``, ``status=EvidenceStatus.FAIL``),
    consistent with ADR-0017 Karar 9's rule that "insufficient
    evidence" is an expected outcome, not an error condition.

    Every element of ``sources`` is retained in the result unfiltered
    when evidence is sufficient -- this function performs no
    deduplication, ranking or conflict resolution among sources
    (ADR-0018 Karar 11 / ADR-0019 Karar 8; conflict *resolution*
    remains explicitly out of scope for this phase -- only conflict
    *visibility* is guaranteed, by never dropping a source).

    A ``calculation_result`` unconditionally yields
    ``EvidenceStatus.PASS`` -- no Question Bank evidence, of any
    quality or in any quantity, can downgrade it (ADR-0019 Karar 1/2,
    the single most important invariant this module enforces).
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
            status=EvidenceStatus.FAIL,
        )

    contributing_source_types = {source.source_type for source in sources}
    if calculation_result is not None:
        contributing_source_types.add(_CALCULATION_SOURCE_TYPE_LABEL)

    if calculation_result is not None:
        # ADR-0019 Karar 1/2: unconditional PASS. Evidence quality is
        # irrelevant here -- deliberately evaluated *before*, and
        # independently of, the per-source confidence check below.
        status = EvidenceStatus.PASS
    elif sources and all(_is_high_confidence(source) for source in sources):
        status = EvidenceStatus.PASS
    else:
        status = EvidenceStatus.WARN

    return EvidenceCheckResult(
        has_sufficient_evidence=True,
        verified_sources=tuple(sources),
        calculation_result=calculation_result,
        notes=notes,
        contributing_source_types=frozenset(contributing_source_types),
        status=status,
    )


__all__ = ["EvidenceCheckResult", "EvidenceStatus", "check_evidence"]
