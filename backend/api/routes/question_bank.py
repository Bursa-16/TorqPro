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

Faz 2.9.6 exposes the create workflow and the lifecycle-transition /
audit / status-history read paths that Faz 2.9.1's service layer has
carried since its own foundation but that, until now, had no HTTP
route at all (``register_question``/``register_question_content``,
``submit_for_technical_review``, ``validate_question``,
``reject_question``, ``deprecate_question``, ``get_lifecycle_audit``,
``get_status_history``). No new persistence, no new schema, no new
service-layer business rule is introduced here -- every new route is
a thin wrapper in the exact same style as the Faz 2.9.3/2.9.4 write
routes above: request-body parsing (via two small, local, purpose-
built Pydantic bodies), the DB connection, the service call, response
serialization, and the shared ``_handle`` exception mapping (extended
with one new entry, ``InvalidTransitionError`` -> 409, the one domain
error no prior route's service call could raise).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
from backend.question_bank import bulk as qb_bulk  # noqa: E402
from backend.question_bank import retrieval  # noqa: E402
from backend.question_bank import service as qb_service  # noqa: E402
from backend.question_bank.errors import (  # noqa: E402
    ContentNotFoundError,
    DuplicateContentVersionError,
    InvalidTransitionError,
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
    QuestionRecord,
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
        InvalidTransitionError,
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
    include_status: bool = False,
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
        payload = record.model_dump(mode="json")
        # Faz 2.9.7, additive/opt-in only (default False -- every existing
        # caller's response shape is completely unaffected): the Question
        # Bank admin UI needs validation_status displayed alongside the
        # content record, which QuestionRecord itself never carries (see
        # retrieval.get_validation_status_map's docstring). One extra
        # read-only lookup, no new persistence, no change to any
        # existing field.
        if include_status:
            status_map = retrieval.get_validation_status_map(c)
            payload["validation_status"] = status_map.get(
                (record.question_id, record.content_version)
            )
    return payload


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
    include_status: bool = False,
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
        payloads = [r.model_dump(mode="json") for r in records]
        # Faz 2.9.7: same additive/opt-in include_status behavior as
        # get_question above -- one extra read-only status-map lookup,
        # never per-row, merged in only when the caller explicitly asks.
        if include_status:
            status_map = retrieval.get_validation_status_map(c)
            for record, payload in zip(records, payloads):
                payload["validation_status"] = status_map.get(
                    (record.question_id, record.content_version)
                )
    return payloads


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


# ---------------------------------------------------------------------
# Faz 2.9.6: create workflow + lifecycle-transition routes + audit /
# status-history read routes.
#
# Same division of responsibility as every write route above: all
# merge/versioning/transition-legality/authorization logic lives in
# ``backend.question_bank.service``; this module only parses the
# request, opens the DB connection, calls the service function, and
# serializes the response. Every body model below is deliberately
# minimal (``extra="forbid"``, matching ``QuestionPatch``'s own
# convention) -- no field this phase does not need.
# ---------------------------------------------------------------------


class ContentVersionBody(BaseModel):
    """Request body for the two transition routes that need nothing
    beyond the target ``content_version`` (submit-for-review,
    deprecate) -- and the base that ``validate``/``reject`` extend
    with their own additional required fields."""

    model_config = ConfigDict(extra="forbid")

    content_version: int = Field(ge=1)


class ValidateQuestionBody(ContentVersionBody):
    reviewed_by: str = Field(min_length=1)
    review_date: str = Field(min_length=1)


class RejectQuestionBody(ContentVersionBody):
    reason: str = Field(min_length=1)


def _transition_response(question_id: str, content_version: int, validation_status: str) -> dict:
    return {
        "question_id": question_id,
        "content_version": content_version,
        "validation_status": validation_status,
    }


@router.post("/api/question-bank/questions", status_code=201)
def create_question(payload: QuestionRecord, u=Depends(user)):
    """Creates a brand-new question: appends the content snapshot to
    the JSON store, then registers the initial ``draft`` SQLite
    lifecycle record for it -- the same two-call sequence
    (``register_question_content`` then ``register_question``) Faz
    2.9.1's own tests already use, now reachable over HTTP for the
    first time. ``question_id`` and ``content_version`` come from the
    request body itself; posting a ``(question_id, content_version)``
    pair that already exists in either store is a 409, never a silent
    overwrite (matches every other append-only write path in this
    module). Structural/content validation failures (e.g. a too-short
    ``technical_explanation_tr``) are a 422 with the full reason list,
    exactly like the PATCH route above."""
    _handle(qb_service.register_question_content, payload)
    with conn() as c:
        _handle(
            qb_service.register_question,
            c,
            question_id=payload.question_id,
            content_version=payload.content_version,
            actor=u["username"],
        )
    return payload.model_dump(mode="json")


@router.post("/api/question-bank/questions/{question_id}/submit-for-review")
def submit_question_for_review(question_id: str, body: ContentVersionBody, u=Depends(user)):
    """``draft -> technical_review``. Matches
    ``backend.question_bank.service.submit_for_technical_review``'s own
    signature exactly: no ``authorize`` callback, because submission is
    not in ``AUTHORIZATION_REQUIRED_TRANSITIONS`` (see
    ``backend/question_bank/transitions.py``'s docstring -- authorship
    submission is deliberately left ungated; this route does not add a
    gate the service layer itself does not have). Any authenticated
    user may call this route. 409 if the current status is not
    ``draft``; 404 if the ``(question_id, content_version)`` pair has
    no SQLite lifecycle record at all."""
    with conn() as c:
        _handle(
            qb_service.submit_for_technical_review,
            c,
            question_id=question_id,
            content_version=body.content_version,
            actor=u["username"],
        )
    return _transition_response(question_id, body.content_version, "technical_review")


@router.post("/api/question-bank/questions/{question_id}/validate")
def validate_question_route(question_id: str, body: ValidateQuestionBody, u=Depends(user)):
    """``technical_review -> validated``. Requires admin/engineer
    authorization (``backend.question_bank.service.
    default_role_authorization`` -- the same reference implementation
    the Faz 2.9.4 archive/restore/delete routes already reuse); a
    ``viewer`` gets 403. 409 if the current status is not
    ``technical_review``; 404 if unregistered."""
    with conn() as c:
        _handle(
            qb_service.validate_question,
            c,
            question_id=question_id,
            content_version=body.content_version,
            actor=u["username"],
            actor_role=u["role"],
            reviewed_by=body.reviewed_by,
            review_date=body.review_date,
            authorize=qb_service.default_role_authorization,
        )
    return _transition_response(question_id, body.content_version, "validated")


@router.post("/api/question-bank/questions/{question_id}/reject")
def reject_question_route(question_id: str, body: RejectQuestionBody, u=Depends(user)):
    """``technical_review -> rejected``. Requires admin/engineer
    authorization, same as ``validate`` above. 409 if the current
    status is not ``technical_review``; 404 if unregistered."""
    with conn() as c:
        _handle(
            qb_service.reject_question,
            c,
            question_id=question_id,
            content_version=body.content_version,
            actor=u["username"],
            actor_role=u["role"],
            reason=body.reason,
            authorize=qb_service.default_role_authorization,
        )
    return _transition_response(question_id, body.content_version, "rejected")


@router.post("/api/question-bank/questions/{question_id}/deprecate")
def deprecate_question_route(question_id: str, body: ContentVersionBody, u=Depends(user)):
    """``validated -> deprecated``. Requires admin/engineer
    authorization, same as ``validate``/``reject`` above. 409 if the
    current status is not ``validated``; 404 if unregistered. Terminal
    -- there is no route back out of ``deprecated`` in this phase."""
    with conn() as c:
        _handle(
            qb_service.deprecate_question,
            c,
            question_id=question_id,
            content_version=body.content_version,
            actor=u["username"],
            actor_role=u["role"],
            authorize=qb_service.default_role_authorization,
        )
    return _transition_response(question_id, body.content_version, "deprecated")


def _require_question_exists(c, question_id: str) -> None:
    """Existence check shared by the two read-only routes below. Reuses
    an invariant ``register_question`` already establishes: every
    legitimately-registered ``question_id`` has at least one
    ``question_bank_status_history`` row from the moment it is created
    (``register_question`` always appends a ``None -> draft`` row), so
    an empty status-history result is equivalent to "no such
    question_id" -- mapped to the same 404 shape every other lifecycle
    route already uses for an unknown ``question_id``."""
    if not qb_service.get_status_history(c, question_id):
        raise HTTPException(404, f"question_id '{question_id}' bulunamadı")


@router.get("/api/question-bank/questions/{question_id}/audit")
def get_question_audit(question_id: str, u=Depends(user)):
    """Read-only wrapper over
    ``backend.question_bank.service.get_lifecycle_audit`` (the Faz
    2.9.4 soft-delete/restore/archive audit trail). A question that
    exists but was never deleted/restored/archived legitimately
    returns an empty list with 200 -- only a wholly unknown
    ``question_id`` is a 404 (see ``_require_question_exists``)."""
    with conn() as c:
        _require_question_exists(c, question_id)
        rows = qb_service.get_lifecycle_audit(c, question_id)
    return [dict(row) for row in rows]


@router.get("/api/question-bank/questions/{question_id}/status-history")
def get_question_status_history(question_id: str, u=Depends(user)):
    """Read-only wrapper over
    ``backend.question_bank.service.get_status_history`` (the Faz
    2.9.1 validation-status transition trail). Every registered
    question always has at least one row here, so an empty result is
    itself the 404 signal -- see ``_require_question_exists``."""
    with conn() as c:
        _require_question_exists(c, question_id)
        rows = qb_service.get_status_history(c, question_id)
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------
# Faz 2.9.8: bulk lifecycle transition + bulk tag add/remove.
#
# Same division of responsibility as every write route above: all
# sequencing, per-item partial-success handling, and the one-time
# up-front authorization check for gated actions live in
# ``backend.question_bank.bulk``; this module only parses the request
# body (with the small amount of cross-field validation these two
# bodies need -- action-specific required fields, at-least-one-of
# add/remove), opens the DB connection, calls the bulk service
# function, and serializes the result. No new persistence, no new
# transition rule, no new authorization mechanism: both bulk functions
# are thin sequencing wrappers over the exact same single-item service
# functions the routes above already call.
# ---------------------------------------------------------------------


class BulkTransitionItem(BaseModel):
    """One item of a bulk transition request. ``content_version`` is
    required for every action except ``"archive"`` (which always acts
    on the whole question_id, every content_version at once, per Faz
    2.9.4 -- see ``backend.question_bank.bulk.CONTENT_VERSION_ACTIONS``);
    that per-action requirement is enforced by
    ``BulkTransitionBody._check_action_specific_fields`` below rather
    than by this item model itself, since the requirement depends on
    the sibling ``action`` field."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    content_version: Optional[int] = Field(default=None, ge=1)


class BulkTransitionBody(BaseModel):
    """Request body for ``POST /api/question-bank/questions/bulk/transition``.

    ``reviewed_by``/``review_date``/``reason`` are batch-level (one
    value applied to every item), not per-item -- matching the
    realistic bulk-review scenario (one reviewer processing a batch at
    once) and keeping this body no more complex than it needs to be
    for a bounded first bulk-operations phase."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["submit-for-review", "validate", "reject", "deprecate", "archive"]
    items: List[BulkTransitionItem] = Field(min_length=1, max_length=qb_bulk.MAX_BULK_ITEMS)
    reviewed_by: Optional[str] = None
    review_date: Optional[str] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _check_action_specific_fields(self) -> "BulkTransitionBody":
        if self.action == "validate" and not (self.reviewed_by and self.review_date):
            raise ValueError(
                "'validate' eylemi için istek gövdesinde 'reviewed_by' ve 'review_date' zorunludur"
            )
        if self.action == "reject" and not self.reason:
            raise ValueError("'reject' eylemi için istek gövdesinde 'reason' zorunludur")
        if self.action in qb_bulk.CONTENT_VERSION_ACTIONS:
            missing = [item.question_id for item in self.items if item.content_version is None]
            if missing:
                raise ValueError(
                    f"'{self.action}' eylemi her item için content_version zorunlu kılar; "
                    f"eksik olan question_id(ler): {missing}"
                )
        return self


class BulkTagsBody(BaseModel):
    """Request body for ``POST /api/question-bank/questions/bulk/tags``.
    At least one of ``add``/``remove`` must be non-empty -- an empty
    body would be a no-op bulk call, rejected the same way
    ``EmptyPatchError`` rejects an empty single-item PATCH."""

    model_config = ConfigDict(extra="forbid")

    question_ids: List[str] = Field(min_length=1, max_length=qb_bulk.MAX_BULK_ITEMS)
    add: List[str] = Field(default_factory=list)
    remove: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_add_or_remove(self) -> "BulkTagsBody":
        if not any(t.strip() for t in self.add) and not any(t.strip() for t in self.remove):
            raise ValueError(
                "bulk etiket güncellemesi için 'add' veya 'remove' listelerinden en az biri "
                "dolu olmalı"
            )
        return self


def _bulk_outcome_dict(outcome) -> dict:
    d: dict = {"question_id": outcome.question_id, "content_version": outcome.content_version}
    if outcome.error is not None:
        d["error"] = outcome.error
    if outcome.extra:
        d.update(outcome.extra)
    return d


def _bulk_result_response(result) -> dict:
    return {
        "succeeded": [_bulk_outcome_dict(o) for o in result.succeeded],
        "failed": [_bulk_outcome_dict(o) for o in result.failed],
        "total": len(result.succeeded) + len(result.failed),
        "succeeded_count": len(result.succeeded),
        "failed_count": len(result.failed),
    }


@router.post("/api/question-bank/questions/bulk/transition")
def bulk_transition_questions(body: BulkTransitionBody, u=Depends(user)):
    """Faz 2.9.8. Applies one lifecycle action
    (submit-for-review/validate/reject/deprecate/archive) to every item
    in ``body.items`` in one request, reusing the exact same
    single-item service functions the routes above already call (see
    ``backend.question_bank.bulk.bulk_transition``'s docstring).
    Authorization for gated actions (validate/reject/deprecate/archive)
    is checked once, before any item is touched: an unauthorized actor
    gets a 403 with zero items processed, never a partial application.
    Every other per-item failure (404 not found, 409 illegal
    transition, ...) is captured in the response body's ``failed``
    list rather than raised as an HTTP error, since a batch request is
    expected to legitimately have mixed per-item outcomes; only the
    up-front authorization failure is raised as an HTTP 403 for the
    whole request."""
    with conn() as c:
        result = _handle(
            qb_bulk.bulk_transition,
            c,
            action=body.action,
            items=[(item.question_id, item.content_version) for item in body.items],
            actor=u["username"],
            actor_role=u["role"],
            authorize=qb_service.default_role_authorization,
            reviewed_by=body.reviewed_by,
            review_date=body.review_date,
            reason=body.reason,
        )
    return _bulk_result_response(result)


@router.post("/api/question-bank/questions/bulk/tags")
def bulk_update_question_tags(body: BulkTagsBody, u=Depends(user)):
    """Faz 2.9.8. Applies the same add/remove tag set to every
    question_id in ``body.question_ids``, one
    ``backend.question_bank.service.update_question`` PATCH call per
    question (see ``backend.question_bank.bulk.bulk_update_tags``'s
    docstring) -- identical versioning/no-op/validation semantics to a
    manual single-item PATCH, applied to many questions at once. Any
    authenticated user may call this route: it reuses the exact same
    content-update path the single-item PATCH route already exposes
    with no additional authorization gate of its own (matching that
    route's own behaviour -- content editing has never been
    role-gated in this module; only lifecycle *transitions* are).
    Every per-item failure is captured in the response body's
    ``failed`` list rather than raised as an HTTP error."""
    with conn() as c:
        result = _handle(
            qb_bulk.bulk_update_tags,
            c,
            question_ids=body.question_ids,
            add=body.add,
            remove=body.remove,
            actor=u["username"],
        )
    return _bulk_result_response(result)
