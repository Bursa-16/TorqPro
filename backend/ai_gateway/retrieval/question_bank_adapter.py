"""TorqPro AI Gateway - Question Bank retrieval adaptor.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 3
and ADR-0020 (Question Bank / AI integration, not yet written beyond
this foundation).

Hard rule (ADR-0017 Karar 3, restated here for reviewer visibility):
this module calls **only** ``backend.question_bank.service`` public
functions. It never imports ``backend.question_bank.store`` (the raw
SQLite access layer) and never writes a ``SELECT``/filter of its own
against the ``question_bank_records`` table. The "only validated
content is visible to AI" rule is therefore enforced by the exact
same, already-tested code path the rest of TorqPro uses for
publishable-question visibility
(``service.get_publishable_questions`` -- see that function's own
docstring: "SQLite status is always authoritative for visibility").
This adaptor does not re-implement or duplicate that check.

This module also never calls any Question Bank *write* function
(``register_question``, ``update_question``, ``validate_question``,
``reject_question``, ``delete_question``, bulk operations, import/
export, etc.) -- the AI layer has no write path into Question Bank,
per ADR-0017 Karar 1 and Karar 3.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from backend.ai_gateway.retrieval import EvidenceSource
from backend.question_bank.service import get_publishable_questions

_SOURCE_TYPE = "question_bank"


def _matches_keyword(question_tr: str, question_en: str, keyword: Optional[str]) -> bool:
    """Casefolded substring match across both language fields.

    Deliberately simple (ADR-0018's eventual retrieval-strategy ADR
    owns any future refinement): this foundation phase only needs to
    prove the adaptor boundary (Karar 3), not deliver a tuned search
    ranking.
    """
    if not keyword or not keyword.strip():
        return True
    needle = keyword.casefold()
    return needle in question_tr.casefold() or needle in question_en.casefold()


def get_validated_question_evidence(
    conn: sqlite3.Connection, *, keyword: Optional[str] = None
) -> List[EvidenceSource]:
    """Return :class:`EvidenceSource` entries for every currently
    publishable (``validated`` status, active content -- see
    ``get_publishable_questions`` docstring) Question Bank record,
    optionally narrowed by a TR/EN keyword match.

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
        evidence.append(
            EvidenceSource(
                source_type=_SOURCE_TYPE,
                source_id=record.question_id,
                content_version=record.content_version,
                title_tr=record.question_tr,
                title_en=record.question_en,
                body_tr=record.technical_explanation_tr,
                body_en=record.technical_explanation_en,
            )
        )
    return evidence


__all__ = ["get_validated_question_evidence"]
