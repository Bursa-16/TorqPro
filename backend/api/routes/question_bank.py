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

Faz 2.9.3 adds the one write route this module has at that point
(``PATCH .../questions/{question_id}``). It is still thin: all merge,
no-op, versioning and JSON/SQLite write-ordering logic lives in
``backend.question_bank.service.update_question``; this module only
does request-body parsing (via ``backend.question_bank.patch.
QuestionPatch``), the DB connection, the service call, response
serialization, and the extra domain-exception -> HTTPException mappings
that writing (as opposed to Faz 2.9.2's pure reads) newly requires.

Faz 2.9.4 adds three more thin write routes -- ``POST
.../{question_id}/archive``, ``POST .../{question_id}/restore``, and
``DELETE .../{question_id}`` -- for soft-delete/restore/archive
lifecycle management. Same division of responsibility: all
transaction, all-content-version, and authorization logic lives in
``backend.question_bank.service``; every Faz 2.9.2 read route also
gains ``include_deleted``/``include_archived`` query parameters
(each defaulting to ``False``, matching ``publishable_only``'s
existing safe-default convention) so an admin view can opt back into
seeing soft-deleted or archived content.

Faz 2.9.5 adds tag-based and keyword search on the two Faz 2.9.2 list
routes (``GET .../questions`` and ``GET .../questions/select``):
``tags`` (repeatable query parameter, e.g. ``?tags=iso&tags=torque``),
``tags_match`` (``"any"``/``"all"``, default ``"any"``), and
``keyword`` (free-text, whitespace-tokenized). All three default to
"no filtering" (``None``/``"any"``), so every existing caller's request
is completely unaffected. No route path, method, or existing parameter
changes -- this is purely additive. All matching logic lives in
``backend.question_bank.retrieval``; this module only parses the query
parameters and passes them through.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

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
    QuestionAlreadyArchivedError,
    QuestionAlreadyDeletedError,
    QuestionBankValidationError,
    QuestionNotDeletedError,
    UnauthorizedTransitionError,
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
    except UnauthorizedTransitionError as exc:
        raise HTTPException(403, str(exc))
    except (
        QuestionAlreadyDeletedError,
        QuestionNotDeletedError,
        QuestionAlreadyArchivedError,
    ) as exc:
        raise HTTPException(409, str(exc))


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
    include_deleted: bool = False,
    include_archived: bool = False,
    tags: Optional[List[str]] = Query(None),
    tags_match: Literal["any", "all"] = "any",
    keyword: Optional[str] = None,
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
            include_deleted=include_deleted,
            include_archived=include_archived,
            tags=tags,
            tags_match=tags_match,
            keyword=keyword,
        )
    return [r.model_dump(mode="json") for r in records]


@router.get("/api/question-bank/questions/{question_id}")
def get_question(
    question_id: str,
    content_version: Optional[int] = None,
    publishable_only: bool = True,
    include_deleted: bool = False,
    include_archived: bool = False,
    u=Depends(user),
):
    with conn() as c:
        record = _handle(
            retrieval.get_question,
            c,
            question_id,
            content_version,
            publishable_only=publishable_only,
            include_deleted=include_deleted,
            include_archived=include_archived,
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
    include_deleted: bool = False,
    include_archived: bool = False,
    tags: Optional[List[str]] = Query(None),
    tags_match: Literal["any", "all"] = "any",
    keyword: Optional[str] = None,
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
            include_deleted=include_deleted,
            include_archived=include_archived,
            tags=tags,
            tags_match=tags_match,
            keyword=keyword,
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


# ---------------------------------------------------------------------
# Faz 2.9.4: soft-delete / restore / archive lifecycle management.
#
# All three routes below are thin wrappers exactly like the PATCH route
# above: request parsing, the DB connection, the service call, response
# serialization, and the shared ``_handle`` exception mapping. All
# merge/versioning/authorization/audit logic lives in
# ``backend.question_bank.service`` -- see that module's
# ``delete_question``/``restore_question``/``archive_question``
# docstrings. Every one of these three actions acts on *all*
# ``content_version`` rows of ``question_id`` at once and never
# performs a hard delete (``DELETE`` here means soft-delete, never a
# SQL ``DELETE`` / JSON removal).
# ---------------------------------------------------------------------


def _lifecycle_response(question_id: str, content_versions: list) -> dict:
    return {"question_id": question_id, "content_versions": content_versions}


@router.post("/api/question-bank/{question_id}/archive")
def archive_question(question_id: str, u=Depends(user)):
    """Sets ``archived_at``/``archived_by`` on every content_version of
    ``question_id``. Requires admin/engineer authorization (see
    ``backend.question_bank.service.default_role_authorization``).
    409 if already archived; 404 if the question_id has no lifecycle
    record at all. There is no unarchive route in this phase."""
    with conn() as c:
        versions = _handle(
            qb_service.archive_question,
            c,
            question_id=question_id,
            actor=u["username"],
            actor_role=u["role"],
            authorize=qb_service.default_role_authorization,
        )
    return _lifecycle_response(question_id, versions)


@router.post("/api/question-bank/{question_id}/restore")
def restore_question(question_id: str, u=Depends(user)):
    """Clears ``is_deleted`` on every content_version of ``question_id``.
    Does not clear ``archived_at``/``archived_by`` -- a restored but
    still-archived question stays hidden from default retrieval until
    explicitly un-archived (out of this phase's scope). 409 if not
    currently deleted; 404 if the question_id has no lifecycle record."""
    with conn() as c:
        versions = _handle(
            qb_service.restore_question,
            c,
            question_id=question_id,
            actor=u["username"],
            actor_role=u["role"],
            authorize=qb_service.default_role_authorization,
        )
    return _lifecycle_response(question_id, versions)


@router.delete("/api/question-bank/{question_id}")
def delete_question(question_id: str, u=Depends(user)):
    """Soft-deletes (``is_deleted=1``) every content_version of
    ``question_id``. Never a hard delete: no row is ever removed from
    SQLite or the JSON content store. 409 if already deleted; 404 if
    the question_id has no lifecycle record at all."""
    with conn() as c:
        versions = _handle(
            qb_service.delete_question,
            c,
            question_id=question_id,
            actor=u["username"],
            actor_role=u["role"],
            authorize=qb_service.default_role_authorization,
        )
    return _lifecycle_response(question_id, versions)
