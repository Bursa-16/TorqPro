"""TorqPro AI Gateway - Question Bank retrieval adaptor.

Faz v3.0.0-alpha.1 (AI Architecture Foundation) + Faz v3.0.0-alpha.2
(AI Retrieval & Grounding), per ADR-0017 Karar 3 and ADR-0018.

Hard rule (ADR-0017 Karar 3 / ADR-0018 Karar 2, restated here for
reviewer visibility): this module calls **only**
``backend.question_bank.service``/``backend.question_bank.retrieval``
public functions. It never imports ``backend.question_bank.store``
(the raw SQLite access layer) and never writes a ``SELECT``/filter of
its own against the ``question_bank_records`` table. The "only
validated content is visible to AI" rule is therefore enforced by the
exact same, already-tested code path the rest of TorqPro uses for
publishable-question visibility -- ``validator.validate_publishable``,
reached here only indirectly through
``service.get_publishable_questions`` and
``retrieval.list_questions(..., publishable_only=True)``, never
reimplemented.

ADR-0018 Karar 2's exact usage boundary (statically enforced by
``tests/ai/test_question_bank_adapter.py``):

    - ``list_questions`` is **always** called with
      ``publishable_only=True``. This module never passes
      ``publishable_only=False``.
    - ``validation_status=`` is **never** passed to ``list_questions``
      (that parameter is only meaningful when
      ``publishable_only=False``, which this module never uses -- see
      above).
    - ``include_deleted``/``include_archived`` are never set to
      ``True``.

Because ``publishable_only=True`` funnels every result through
``validate_publishable()`` -- which returns ``False`` for ``draft``,
``technical_review``, ``rejected`` *and* ``deprecated`` records
regardless of their JSON ``is_active`` flag (see that function's own
docstring) -- this adaptor never sees, and therefore can never
surface, any of those four lifecycle states as AI evidence. This
module does not implement that exclusion itself; it inherits it
entirely from the existing, already-tested Question Bank lifecycle
guarantee.

This module also never calls any Question Bank *write* function
(``register_question``, ``update_question``, ``validate_question``,
``reject_question``, ``delete_question``, bulk operations, import/
export, etc.) -- the AI layer has no write path into Question Bank,
per ADR-0017 Karar 1 and Karar 3.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional, Sequence

from backend.ai_gateway.retrieval import EvidenceSource
from backend.question_bank.retrieval import list_questions
from backend.question_bank.schema import Category, Difficulty
from backend.question_bank.service import get_publishable_questions

_SOURCE_TYPE = "question_bank"


def _matches_keyword(question_tr: str, question_en: str, keyword: Optional[str]) -> bool:
    """Casefolded substring match across both language fields.

    Used only by :func:`get_validated_question_evidence` (the
    unfiltered, alpha.1-compatible entry point) -- the filtered entry
    point, :func:`get_filtered_question_evidence`, delegates its own
    keyword matching entirely to
    ``backend.question_bank.retrieval.list_questions``'s own
    ``keyword`` parameter instead of this helper, per ADR-0018 Karar 2
    ("hiçbir yeni filtre mantığı yazmadan mevcut fonksiyonu
    çağırmak").
    """
    if not keyword or not keyword.strip():
        return True
    needle = keyword.casefold()
    return needle in question_tr.casefold() or needle in question_en.casefold()


def _category_from_hint(category_hint: Optional[str]) -> Optional[Category]:
    """Best-effort, non-raising conversion of a free-form category
    hint string (ADR-0018 Karar 6's rule-based intent extraction) into
    the Question Bank's own closed ``Category`` vocabulary.

    An unrecognised hint is treated as "no category filter" (returns
    ``None``) rather than raising -- ADR-0018 Karar 6: "eşleşme
    başarısızlığı bir hata değildir". This function does not define a
    new vocabulary; it only attempts to resolve the hint against the
    vocabulary ``Category`` already defines.
    """
    if not category_hint:
        return None
    try:
        return Category(category_hint)
    except ValueError:
        return None


def _difficulty_from_hint(difficulty_hint: Optional[str]) -> Optional[Difficulty]:
    """Same non-raising resolution rule as :func:`_category_from_hint`,
    against the existing ``Difficulty`` vocabulary."""
    if not difficulty_hint:
        return None
    try:
        return Difficulty(difficulty_hint)
    except ValueError:
        return None


def _record_to_evidence(record) -> EvidenceSource:
    """Map one ``QuestionRecord`` onto an :class:`EvidenceSource`,
    copying every ADR-0018 Karar 5/16 metadata field verbatim from the
    existing domain model -- no new classification is computed or
    invented here."""
    standard_reference = record.standard_reference
    source_reference = record.source_reference
    return EvidenceSource(
        source_type=_SOURCE_TYPE,
        source_id=record.question_id,
        content_version=record.content_version,
        title_tr=record.question_tr,
        title_en=record.question_en,
        body_tr=record.technical_explanation_tr,
        body_en=record.technical_explanation_en,
        standard_name=standard_reference.name if standard_reference else None,
        standard_clause=standard_reference.clause_or_table if standard_reference else None,
        source_kind=source_reference.source_type.value if source_reference else None,
        category=record.category.value if record.category else None,
        difficulty=record.difficulty.value if record.difficulty else None,
        tags=tuple(record.tags),
        traceability_level=(
            record.traceability_level.value if record.traceability_level else None
        ),
    )


def get_validated_question_evidence(
    conn: sqlite3.Connection, *, keyword: Optional[str] = None
) -> List[EvidenceSource]:
    """Return :class:`EvidenceSource` entries for every currently
    publishable (``validated`` status, active content -- see
    ``get_publishable_questions`` docstring) Question Bank record,
    optionally narrowed by a TR/EN keyword match.

    Unchanged from v3.0.0-alpha.1: this is the unfiltered, "give me
    everything publishable" entry point (ADR-0018 Karar 2's first
    bullet -- appropriate for aggregate/unfiltered scenarios). For
    category/difficulty/tag-narrowed retrieval, use
    :func:`get_filtered_question_evidence` instead.

    ``conn`` is supplied by the caller (the orchestrator), matching
    the existing project convention (``backend.question_bank.service``
    functions all take an injected ``sqlite3.Connection`` rather than
    opening their own) -- this adaptor manages no connection
    lifecycle of its own.

    Never returns ``draft``/``technical_review``/``rejected``/
    ``deprecated`` content: that filtering happens entirely inside
    ``get_publishable_questions`` before this function ever sees a
    record.
    """
    records = get_publishable_questions(conn)
    evidence: List[EvidenceSource] = []
    for record in records:
        if not _matches_keyword(record.question_tr, record.question_en, keyword):
            continue
        evidence.append(_record_to_evidence(record))
    return evidence


def get_filtered_question_evidence(
    conn: sqlite3.Connection,
    *,
    keyword: Optional[str] = None,
    category_hint: Optional[str] = None,
    difficulty_hint: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
) -> List[EvidenceSource]:
    """Return :class:`EvidenceSource` entries for currently publishable
    Question Bank records, narrowed by optional category/difficulty/
    tag/keyword hints (ADR-0018 Karar 6/7).

    Delegates all filtering to
    ``backend.question_bank.retrieval.list_questions`` -- this
    function writes no filter predicate of its own. Always calls
    ``list_questions`` with ``publishable_only=True`` and never passes
    ``validation_status=``, ``include_deleted=True`` or
    ``include_archived=True`` (ADR-0018 Karar 2's exact usage
    boundary -- see module docstring).

    ``category_hint``/``difficulty_hint`` are free-form strings (e.g.
    extracted by a rule-based intent step upstream, ADR-0018 Karar 6);
    an unrecognised hint silently degrades to "no filter on that
    axis" rather than raising or excluding all results -- see
    :func:`_category_from_hint`/:func:`_difficulty_from_hint`.
    ``tags`` is passed through to ``list_questions`` unchanged, using
    its default ``tags_match="any"`` (ADR-0018 Karar 7: the more
    restrictive ``"all"`` mode is out of scope for this phase).
    """
    records = list_questions(
        conn,
        category=_category_from_hint(category_hint),
        difficulty=_difficulty_from_hint(difficulty_hint),
        tags=tags,
        keyword=keyword,
        publishable_only=True,
    )
    return [_record_to_evidence(record) for record in records]


__all__ = ["get_validated_question_evidence", "get_filtered_question_evidence"]
