"""Question Bank retrieval, filtering, and deterministic selection
(Faz 2.9.2).

This module adds the read paths Faz 2.9.1 explicitly deferred: filtered
listing, single-question lookup, and deterministic (seeded) selection.
It introduces no new persistence, no new schema, and no new lifecycle
rule -- it only *reads* the JSON content store (``store.py``) and the
SQLite lifecycle table (``store.py``'s ``question_bank_records``) that
Faz 2.9.1 already built.

Publishability is intentionally not redefined here. Every publishable-
only code path in this module calls
:func:`backend.question_bank.validator.validate_publishable` directly
-- the exact same function Faz 2.9.1's
``backend.question_bank.service.get_publishable_questions`` already
uses -- so there is exactly one publishable-state rule in the codebase,
never two. As that function's own docstring establishes: SQLite's
``validation_status`` is always authoritative for visibility, never
the JSON content's ``is_active`` flag alone; a ``deprecated`` question
is never publishable even if ``is_active`` is stale-``True`` in its
JSON content.
"""

from __future__ import annotations

import random
import sqlite3
from typing import Dict, List, Optional, Tuple

from .errors import ContentNotFoundError
from .schema import Category, Difficulty, QuestionRecord, QuestionType, TraceabilityLevel
from .store import fetch_all_records, load_all_question_content, load_question_content
from .transitions import ValidationStatus
from .validator import validate_publishable


def _status_map(c: sqlite3.Connection) -> Dict[Tuple[str, int], str]:
    """``(question_id, content_version) -> validation_status`` lookup
    built from every SQLite lifecycle row. A JSON content record with
    no matching SQLite row (never registered via
    ``service.register_question``) simply has no entry here -- callers
    treat that as "no known validation_status", not as an error."""
    rows = fetch_all_records(c)
    return {(r["question_id"], r["content_version"]): r["validation_status"] for r in rows}


def list_questions(
    c: sqlite3.Connection,
    *,
    category: Optional[Category] = None,
    difficulty: Optional[Difficulty] = None,
    question_type: Optional[QuestionType] = None,
    traceability_level: Optional[TraceabilityLevel] = None,
    is_active: Optional[bool] = None,
    validation_status: Optional[ValidationStatus] = None,
    publishable_only: bool = True,
) -> List[QuestionRecord]:
    """Filtered listing over every JSON content record.

    All filters combine with logical AND. ``publishable_only=True``
    (the default) applies
    :func:`backend.question_bank.validator.validate_publishable` per
    record and ignores ``validation_status`` (publishable already
    implies ``validation_status == 'validated'`` -- accepting a
    conflicting explicit ``validation_status`` filter alongside
    ``publishable_only=True`` would either be redundant or produce a
    silently-empty result; this function does not guess which one the
    caller meant, so ``validation_status`` is only consulted when
    ``publishable_only=False``).

    Results are sorted deterministically by ``(question_id,
    content_version)`` so repeated calls against an unchanged dataset
    always return the same order -- callers needing a shuffled subset
    should use :func:`select_questions` instead of relying on this
    function's order.
    """
    status_by_key = _status_map(c)
    records = load_all_question_content()

    results: List[QuestionRecord] = []
    for record in records:
        key = (record.question_id, record.content_version)
        record_status = status_by_key.get(key)

        if publishable_only:
            if not validate_publishable(record, record_status or ""):
                continue
        elif validation_status is not None:
            if record_status != validation_status.value:
                continue

        if category is not None and record.category != category:
            continue
        if difficulty is not None and record.difficulty != difficulty:
            continue
        if question_type is not None and record.question_type != question_type:
            continue
        if traceability_level is not None and record.traceability_level != traceability_level:
            continue
        if is_active is not None and record.is_active != is_active:
            continue

        results.append(record)

    results.sort(key=lambda r: (r.question_id, r.content_version))
    return results


def get_question(
    c: sqlite3.Connection,
    question_id: str,
    content_version: Optional[int] = None,
    *,
    publishable_only: bool = True,
) -> QuestionRecord:
    """Single-question lookup. ``content_version=None`` resolves to
    the highest existing ``content_version`` for ``question_id``
    (matching :func:`backend.question_bank.store.load_question_content`'s
    own default).

    When ``publishable_only=True`` (the default -- Faz 2.9.2's required
    safe default for general retrieval) and the resolved record is not
    publishable, this raises the same
    :class:`backend.question_bank.errors.ContentNotFoundError` as a
    genuinely non-existent ``question_id`` -- deliberately not a
    different error/status, so a caller cannot distinguish "does not
    exist" from "exists but is hidden" and non-publishable content
    never leaks its existence through this path either."""
    record = load_question_content(question_id, content_version)

    if publishable_only:
        status_map = _status_map(c)
        status = status_map.get((record.question_id, record.content_version))
        if not validate_publishable(record, status or ""):
            raise ContentNotFoundError(
                f"question_id '{question_id}' publishable sonuçlarda bulunamadı"
            )

    return record


def select_questions(
    c: sqlite3.Connection,
    *,
    count: int,
    seed: int,
    category: Optional[Category] = None,
    difficulty: Optional[Difficulty] = None,
    question_type: Optional[QuestionType] = None,
    traceability_level: Optional[TraceabilityLevel] = None,
    is_active: Optional[bool] = None,
    validation_status: Optional[ValidationStatus] = None,
    publishable_only: bool = True,
) -> List[QuestionRecord]:
    """Deterministic (seeded) selection over the same filter set as
    :func:`list_questions`.

    ``seed`` is a required keyword argument with no default -- Faz
    2.9.2's explicit requirement that no hidden/non-deterministic
    randomness exist in this path. The candidate set is always built
    via :func:`list_questions` first (so it is already sorted
    deterministically by ``(question_id, content_version)``), then
    shuffled with a ``random.Random(seed)`` instance private to this
    call -- never the shared/global ``random`` module -- so the same
    dataset + same filters + same seed always produces the same
    ordered result, and different calls (even concurrent ones) never
    perturb each other's randomness state.

    ``count`` larger than the candidate set is handled by plain slice
    truncation: the full (shuffled) candidate set is returned, safely
    and predictably, never an error and never a padded/duplicated
    result. ``count`` must be ``>= 0``.
    """
    if count < 0:
        raise ValueError("count must be >= 0")

    candidates = list_questions(
        c,
        category=category,
        difficulty=difficulty,
        question_type=question_type,
        traceability_level=traceability_level,
        is_active=is_active,
        validation_status=validation_status,
        publishable_only=publishable_only,
    )

    rng = random.Random(seed)
    shuffled = candidates.copy()
    rng.shuffle(shuffled)
    return shuffled[:count]


__all__ = ["list_questions", "get_question", "select_questions"]
