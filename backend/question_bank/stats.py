"""Question Bank aggregate statistics / coverage (Faz 2.9.10).

Single responsibility: produce read-only aggregate counts over the
Question Bank's existing records. This module introduces no new
persistence, no new schema, and no new lifecycle/business rule -- it
is a pure counting layer on top of functions Faz 2.9.1/2.9.2/2.9.7
already built:

- :func:`backend.question_bank.retrieval.list_questions` (Faz 2.9.2)
  is reused verbatim as the single source of "which records exist"
  -- exactly the same canonical read path
  ``GET /api/question-bank/questions`` already uses, so this module
  never re-implements JSON-content loading, SQLite-lifecycle
  joining, or deleted/archived filtering a second time.
- :func:`backend.question_bank.retrieval.get_validation_status_map`
  (Faz 2.9.7's public wrapper) is reused verbatim for the
  ``(question_id, content_version) -> validation_status`` lookup --
  the exact same lookup the admin UI's ``include_status`` already
  uses.

Deliberately excluded from this phase (per the Faz 2.9.10 scope
lock): no "publishable" count. Every other Question Bank read route
defaults ``publishable_only=True`` because it exists to decide what a
*consumer* may see; a statistics/coverage view exists for an *admin*
to see the whole bank's shape, so this module always calls
``list_questions`` with ``publishable_only=False`` and never invokes
:func:`backend.question_bank.validator.validate_publishable` (directly
or indirectly) -- that lifecycle/business rule is not duplicated,
extended, or reinterpreted here.

Deleted/archived semantics: this module uses the exact same safe
default every other Question Bank read route already uses --
``include_deleted=False``, ``include_archived=False``. Soft-deleted
and archived records are excluded from every count here, matching
what an admin's own default question list already shows (Faz 2.9.4's
existing convention, not a new one). This is fixed by test, not left
implicit -- see ``tests/test_faz_2_9_10_question_bank_stats.py``.

Missing/blank breakdown values (in practice: a JSON content record
whose ``validation_status`` has no matching SQLite row -- see
``retrieval._status_map``'s own docstring, "no entry == unknown, not
an error") are grouped under a single deterministic
:data:`UNKNOWN_BUCKET` key rather than being silently dropped or
raising. ``category``/``difficulty``/``question_type`` are required,
closed-vocabulary enum fields on
:class:`backend.question_bank.schema.QuestionRecord` (schema-enforced
at write time), so in practice only ``by_validation_status`` can ever
populate this bucket -- the same handling is applied uniformly to all
four breakdowns anyway, so the contract holds even if a future schema
change ever makes one of the other fields optional.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, Optional

from . import retrieval

#: Deterministic bucket name for a missing/blank breakdown value.
#: Never collides with a real enum value -- every closed vocabulary
#: this module reads from (Category/Difficulty/QuestionType/
#: ValidationStatus) uses lowercase snake_case members, none of which
#: is the literal string "unknown" prefixed/suffixed like this.
UNKNOWN_BUCKET = "unknown"


def _bucket_label(value: object) -> str:
    """Normalizes one breakdown value to its final string bucket key.

    ``value`` may be a ``str``-backed :class:`enum.Enum` member (e.g.
    ``Category.WASHERS``), a plain ``str``, or ``None``/empty-string
    (the "missing" case). Enum members are reduced to their ``.value``
    so the response contains plain JSON strings, never enum reprs.
    """
    if value is None:
        return UNKNOWN_BUCKET
    label = value.value if hasattr(value, "value") else value
    if not isinstance(label, str) or label.strip() == "":
        return UNKNOWN_BUCKET
    return label


def _bump(counter: Dict[str, int], value: object) -> None:
    label = _bucket_label(value)
    counter[label] = counter.get(label, 0) + 1


def compute_stats(c: sqlite3.Connection) -> dict:
    """Returns a plain ``dict`` with ``total`` and four breakdowns:
    ``by_validation_status``, ``by_category``, ``by_difficulty``,
    ``by_question_type``.

    Every breakdown dict is key-sorted (``sorted(...)`` over
    ``dict.items()``) so the response is byte-for-byte deterministic
    across calls and across Python versions/dict-ordering
    implementations -- callers (including tests) never need to sort
    the response themselves to compare it reliably.
    """
    records = retrieval.list_questions(
        c,
        publishable_only=False,
        include_deleted=False,
        include_archived=False,
    )
    status_by_key: Dict[tuple, Optional[str]] = retrieval.get_validation_status_map(c)

    by_validation_status: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    by_difficulty: Dict[str, int] = {}
    by_question_type: Dict[str, int] = {}

    for record in records:
        key = (record.question_id, record.content_version)
        _bump(by_validation_status, status_by_key.get(key))
        _bump(by_category, record.category)
        _bump(by_difficulty, record.difficulty)
        _bump(by_question_type, record.question_type)

    return {
        "total": len(records),
        "by_validation_status": dict(sorted(by_validation_status.items())),
        "by_category": dict(sorted(by_category.items())),
        "by_difficulty": dict(sorted(by_difficulty.items())),
        "by_question_type": dict(sorted(by_question_type.items())),
    }


__all__ = ["compute_stats", "UNKNOWN_BUCKET"]
