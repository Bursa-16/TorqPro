"""Question Bank Retrieval, Filtering & Read API (Faz 2.9.2).

Thin, read-only FastAPI routes over
``backend.question_bank.retrieval``. No business logic, no SQL, and no
publishability rule lives in this module -- filtering, single-question
lookup, and deterministic selection all live in
``backend.question_bank.retrieval`` (which itself reuses
``backend.question_bank.validator.validate_publishable``, the exact
same function Faz 2.9.1's own
``backend.question_bank.service.get_publishable_questions`` uses --
never a second definition of "publishable"). This module only does
request-parameter parsing, the DB connection, the retrieval call
itself, response serialization, and domain-exception -> HTTPException
mapping.

Follows ``backend/api/routes/joints.py``'s / ``production_validation.
py``'s established pattern (``APIRouter``, ``Depends(user)``, a single
central ``_handle()`` exception-mapping helper) without introducing a
new convention.

``publishable_only`` defaults to ``True`` on every route here -- Faz
2.9.2's required "safe default" for general retrieval. A deprecated,
inactive, or unvalidated question never appears in a default response;
callers who genuinely need to see non-publishable content (e.g. a
review workspace) must explicitly pass ``publishable_only=false``.

Route registration order matters: ``/api/question-bank/questions/select``
is declared *before* ``/api/question-bank/questions/{question_id}`` so
FastAPI's exact-match route is tried first and the literal path segment
``select`` is never swallowed by the ``{question_id}`` path parameter.

Faz 2.9.3 adds the one write route this module has (``PATCH
.../questions/{question_id}``). It is still thin: all merge, no-op,
versioning and JSON/SQLite write-ordering logic lives in
``backend.question_bank.service.update_question``; this module only
does request-body parsing (via ``backend.question_bank.patch.
QuestionPatch``), the DB connection, the service call, response
serialization, and the extra domain-exception -> HTTPException mappings
that writing (as opposed to Faz 2.9.2's pure reads) newly requires.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(tags=["question_bank"])

# `router` is assigned before these imports for the same reason
# backend/api/routes/joints.py and backend/api/routes/production_validation.py
# already document on their own equivalent import blocks: if backend.app
# ends up re-entering this module while it is still mid-import, the
# partially-initialized module already exposes a usable `router`
# attribute, which breaks a circular-import failure instead of
# propagating it.
from backend.api.dependencies import user  # noqa: E402
from backend.app import conn  # noqa: E402
from backend.question_bank import retrieval  # noqa: E402
from backend.question_bank import service as qb_service  # noqa: E402
from backend.question_bank.errors import (  # noqa: E402
    ContentNotFoundError,
    DuplicateContentVersionError,
    PartialUpdateFailureError,
    QuestionBankValidationError,
)
from backend.question_bank.patch import QuestionPatch  # noqa: E402
from backend.question_bank.schema import (  # noqa: E402
    Category,
    Difficulty,
    QuestionType,
    TraceabilityLevel,
)
from backend.question_bank.transitions import ValidationStatus  # noqa: E402


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ContentNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except DuplicateContentVersionError as exc:
        raise HTTPException(409, str(exc))
    except QuestionBankValidationError as exc:
        raise HTTPException(422, {"message": str(exc), "reasons": exc.reasons})
    except PartialUpdateFailureError as exc:
        raise HTTPException(500, str(exc))


@router.get("/api/question-bank/questions/select")
def select_questions(
    count: int,
    seed: int,
    category: Optional[Category] = None,
    difficulty: Optional[Difficulty] = None,
    question_type: Optional[QuestionType] = None,
    traceability_level: Optional[TraceabilityLevel] = None,
    is_active: Optional[bool] = None,
    validation_status: Optional[ValidationStatus] = None,
    publishable_only: bool = True,
    u=Depends(user),
):
    if count < 0:
        raise HTTPException(422, "count must be >= 0")
    with conn() as c:
        records = retrieval.select_questions(
            c,
            count=count,
            seed=seed,
            category=category,
            difficulty=difficulty,
            question_type=question_type,
            traceability_level=traceability_level,
            is_active=is_active,
            validation_status=validation_status,
            publishable_only=publishable_only,
        )
    return [r.model_dump(mode="json") for r in records]


@router.get("/api/question-bank/questions/{question_id}")
def get_question(
    question_id: str,
    content_version: Optional[int] = None,
    publishable_only: bool = True,
    u=Depends(user),
):
    with conn() as c:
        record = _handle(
            retrieval.get_question,
            c,
            question_id,
            content_version,
            publishable_only=publishable_only,
        )
    return record.model_dump(mode="json")


@router.get("/api/question-bank/questions")
def list_questions(
    category: Optional[Category] = None,
    difficulty: Optional[Difficulty] = None,
    question_type: Optional[QuestionType] = None,
    traceability_level: Optional[TraceabilityLevel] = None,
    is_active: Optional[bool] = None,
    validation_status: Optional[ValidationStatus] = None,
    publishable_only: bool = True,
    u=Depends(user),
):
    with conn() as c:
        records = retrieval.list_questions(
            c,
            category=category,
            difficulty=difficulty,
            question_type=question_type,
            traceability_level=traceability_level,
            is_active=is_active,
            validation_status=validation_status,
            publishable_only=publishable_only,
        )
    return [r.model_dump(mode="json") for r in records]


@router.patch("/api/question-bank/questions/{question_id}")
def patch_question(question_id: str, patch: QuestionPatch, u=Depends(user)):
    """Faz 2.9.3. Partial content update: only fields present in the
    request body are changed; ``question_id`` and lifecycle fields
    (``validation_status`` etc.) cannot be set through this body at all.
    Internally this always creates a new, immutable ``content_version``
    rather than mutating an existing one -- see
    ``backend.question_bank.service.update_question``'s docstring for
    the full versioning and JSON/SQLite write-ordering behaviour. A
    no-op patch (every provided field already matches the current
    value) returns the unchanged current record with no new version
    created. The response uses the same canonical
    :class:`backend.question_bank.schema.QuestionRecord` shape as every
    Faz 2.9.2 retrieval route."""
    with conn() as c:
        record = _handle(
            qb_service.update_question,
            c,
            question_id=question_id,
            patch=patch,
            actor=u["username"],
        )
    return record.model_dump(mode="json")
