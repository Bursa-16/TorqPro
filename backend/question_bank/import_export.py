"""Question Bank JSON import/export (Faz 2.9.9).

Deliberately *not* a new persistence mechanism, a new content schema,
or a second validation system: export is a thin, read-only wrapper
over :func:`backend.question_bank.retrieval.list_questions` (the exact
same filter/search/tag/lifecycle machinery the Faz 2.9.2/2.9.4/2.9.5
list route already exposes), and import is a thin sequencing wrapper
over the exact same two-call registration path
(:func:`backend.question_bank.service.register_question_content` then
:func:`backend.question_bank.service.register_question`) the Faz 2.9.6
``POST /api/question-bank/questions`` route already uses for a single
question -- applied to many records in one request, one record at a
time, following the same "no item's failure aborts the rest of the
batch" philosophy :mod:`backend.question_bank.bulk` (Faz 2.9.8)
already established.

Export
------

:func:`export_questions` returns the exact same
:class:`~backend.question_bank.schema.QuestionRecord` list
``retrieval.list_questions`` would return for the given filters,
already sorted deterministically by ``(question_id, content_version)``
(that ordering guarantee lives in ``retrieval.list_questions`` itself,
not duplicated here). Two calls against an unchanged dataset with the
same filters therefore always produce byte-identical serialized
output -- this function never adds a wall-clock timestamp or any other
non-deterministic field to the payload, specifically so that
determinism holds at the HTTP response level too (see
``backend/api/routes/question_bank.py``'s ``export_questions_route``).
This function never writes anything -- existing records (JSON or
SQLite) are never touched.

Import
------

:func:`import_questions` classifies every item of ``records`` into
exactly one of three buckets, matching the Faz 2.9.9 instruction to
report "created / skipped / rejected" counts:

  - **created** -- structurally and semantically valid, a genuinely
    new ``(question_id, content_version)`` pair. Registered via the
    same ``register_question_content`` + ``register_question`` two-step
    sequence the single-item create route uses.
  - **skipped** -- structurally valid but ``(question_id,
    content_version)`` already exists (a duplicate/conflict with
    existing data, or with an earlier item of the same import batch --
    both are caught identically, since
    :func:`backend.question_bank.store.save_question_content`'s
    append-only guard checks the JSON store's *current* on-disk state
    at the moment each item is processed, which already includes every
    item this same import call has itself just written). Never treated
    as an error: the existing record is left completely untouched,
    exactly as the Faz 2.9.9 "mevcut kayıtları değiştirme" constraint
    requires.
  - **rejected** -- missing required fields, wrong field types, or any
    other structural/content validation failure (schema validation via
    Pydantic, then :func:`backend.question_bank.validator.
    validate_record_structure` -- the exact same two-stage validation
    :func:`backend.question_bank.service.register_question_content`
    already performs for a single question).

Transaction-safety / partial-failure behaviour, per item (mirrors
:func:`backend.question_bank.service.update_question`'s own documented
write-ordering and compensating-delete pattern -- see that function's
docstring for the detailed rationale, not repeated here): the JSON
content append happens first; if the paired SQLite registration then
fails (e.g. a same-batch race, or a pre-existing orphaned SQLite row),
this function immediately performs the same best-effort compensating
delete of that item's own just-written JSON record
(:func:`backend.question_bank.store._delete_question_content_version`)
and reports the item as **rejected** rather than leaving an orphan
content_version with no matching SQLite row behind. One item's
JSON-write-then-SQLite-registration is therefore atomic in practice
(either both succeed, or neither remains); the import call as a whole
is *not* wrapped in one shared all-or-nothing transaction, by design --
exactly like ``bulk.bulk_transition``/``bulk.bulk_update_tags``, a
batch import is expected to legitimately produce a mix of
created/skipped/rejected outcomes in one call (Faz 2.9.9 explicitly
requires this three-way report, not an all-or-nothing accept/reject of
the whole file), and an already-created earlier item in the same batch
is never rolled back because a later item in that same batch turns out
to be invalid. Across the whole call, no pre-existing record (JSON or
SQLite) is ever mutated or removed -- only brand-new content_versions
are ever written (and, on failure, compensated away).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import sqlite3

from pydantic import ValidationError

from . import retrieval
from .errors import DuplicateContentVersionError, QuestionBankError, QuestionBankValidationError
from .schema import (
    Category,
    Difficulty,
    QuestionRecord,
    QuestionType,
    TraceabilityLevel,
)
from .service import register_question, register_question_content
from .store import _delete_question_content_version
from .transitions import ValidationStatus


def _pydantic_reasons(exc: ValidationError) -> List[str]:
    """Same field-path + message formatting as
    ``backend.question_bank.service._pydantic_reasons`` -- duplicated
    (not imported) only because that name is underscore-prefixed
    module-private to ``service.py`` and this module deliberately does
    not reach into another module's private helpers; the formatting
    itself is intentionally identical so a rejection reason looks the
    same here as it does from a single-item create/update 422.
    """
    reasons = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        reasons.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return reasons


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------


def export_questions(
    c: sqlite3.Connection,
    *,
    category: Optional[Category] = None,
    difficulty: Optional[Difficulty] = None,
    question_type: Optional[QuestionType] = None,
    traceability_level: Optional[TraceabilityLevel] = None,
    is_active: Optional[bool] = None,
    validation_status: Optional[ValidationStatus] = None,
    publishable_only: bool = True,
    include_deleted: bool = False,
    include_archived: bool = False,
    tags: Optional[Sequence[str]] = None,
    tags_match: str = "any",
    keyword: Optional[str] = None,
) -> List[QuestionRecord]:
    """Read-only. Every keyword argument is forwarded verbatim to
    :func:`backend.question_bank.retrieval.list_questions` -- no
    filter logic is re-implemented here. See that function's own
    docstring for the exact semantics of each parameter (AND
    combination, publishable_only's interaction with
    validation_status, tags_match, keyword tokenization, etc.)."""
    return retrieval.list_questions(
        c,
        category=category,
        difficulty=difficulty,
        question_type=question_type,
        traceability_level=traceability_level,
        is_active=is_active,
        validation_status=validation_status,
        publishable_only=publishable_only,
        include_deleted=include_deleted,
        include_archived=include_archived,
        tags=tags,
        tags_match=tags_match,
        keyword=keyword,
    )


# ---------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------


@dataclass
class ImportItemOutcome:
    """One record's classification result within an
    :class:`ImportResult`. ``question_id``/``content_version`` are
    extracted defensively (``dict.get``) even when the record failed
    Pydantic validation, so a rejected item can still usually be
    identified in the report; both may be ``None`` if the raw item did
    not even carry those keys."""

    question_id: Optional[str]
    content_version: Optional[int]
    reasons: List[str] = field(default_factory=list)


@dataclass
class ImportResult:
    created: List[ImportItemOutcome] = field(default_factory=list)
    skipped: List[ImportItemOutcome] = field(default_factory=list)
    rejected: List[ImportItemOutcome] = field(default_factory=list)


def _extract_identity(item: Any) -> tuple[Optional[str], Optional[int]]:
    if not isinstance(item, dict):
        return None, None
    qid = item.get("question_id")
    ver = item.get("content_version")
    return (qid if isinstance(qid, str) else None), (ver if isinstance(ver, int) else None)


def import_questions(
    c: sqlite3.Connection,
    *,
    records: Sequence[Dict[str, Any]],
    actor: str,
) -> ImportResult:
    """Classifies and (for valid, non-duplicate items) registers every
    item of ``records`` -- see this module's own docstring for the
    full created/skipped/rejected contract and the per-item
    transaction-safety guarantee. Never raises for an individual
    record's own validation/duplicate/registration failure -- every
    such outcome is captured in the returned :class:`ImportResult`
    instead, exactly like :mod:`backend.question_bank.bulk`'s
    ``succeeded``/``failed`` split for bulk transitions."""
    result = ImportResult()

    for raw_item in records:
        qid_hint, ver_hint = _extract_identity(raw_item)

        if not isinstance(raw_item, dict):
            result.rejected.append(
                ImportItemOutcome(None, None, ["kayıt bir JSON nesnesi (object) olmalı"])
            )
            continue

        try:
            record = QuestionRecord.model_validate(raw_item)
        except ValidationError as exc:
            result.rejected.append(
                ImportItemOutcome(qid_hint, ver_hint, _pydantic_reasons(exc))
            )
            continue

        # Stage 1: JSON content append. register_question_content()
        # itself runs backend.question_bank.validator.require_valid()
        # before writing (the exact same structural/content validation
        # the single-item create route already performs) and raises
        # DuplicateContentVersionError via store.save_question_content's
        # own append-only guard if this (question_id, content_version)
        # already exists -- whether from data written before this
        # import call, or from an earlier item of this same batch.
        try:
            register_question_content(record)
        except DuplicateContentVersionError:
            result.skipped.append(
                ImportItemOutcome(
                    record.question_id,
                    record.content_version,
                    [f"{record.question_id}@v{record.content_version} zaten mevcut (duplicate)"],
                )
            )
            continue
        except QuestionBankValidationError as exc:
            result.rejected.append(
                ImportItemOutcome(record.question_id, record.content_version, list(exc.reasons))
            )
            continue

        # Stage 2: SQLite lifecycle registration. On any failure here,
        # the JSON append from Stage 1 is compensated away (best
        # effort) so this record never ends up as a JSON-only orphan --
        # see this module's docstring for the full rationale, mirrored
        # from service.update_question's own compensating-delete path.
        try:
            register_question(
                c,
                question_id=record.question_id,
                content_version=record.content_version,
                actor=actor,
            )
        except QuestionBankError as exc:
            try:
                _delete_question_content_version(record.question_id, record.content_version)
            except Exception:
                pass
            result.rejected.append(
                ImportItemOutcome(
                    record.question_id,
                    record.content_version,
                    [
                        f"{record.question_id}@v{record.content_version} SQLite lifecycle "
                        f"kaydı başarısız oldu, işlem geri alındı: {exc}"
                    ],
                )
            )
            continue

        result.created.append(ImportItemOutcome(record.question_id, record.content_version, []))

    return result


__all__ = [
    "ImportItemOutcome",
    "ImportResult",
    "export_questions",
    "import_questions",
]
