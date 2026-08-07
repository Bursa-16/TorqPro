"""Question Bank service layer.

Every lifecycle-changing operation performs its SQLite record update
and its append-only audit-history insert inside the *same*
transaction, and rolls back entirely on any failure -- mirroring the
"status change + audit record together, or neither" principle already
implicit in ``backend.governance``'s append-only event store design.

Authorization is a small, explicit, injectable callback -- deliberately
*not* a hardcoded role check and *not* a new fake user/role system.
TorqPro already has a real, usable authorization substrate
(``backend/api/dependencies.py``'s JWT-based ``user``/``admin``
FastAPI dependencies, and the ``admin``/``engineer``/``viewer`` role
vocabulary used throughout ``backend/app.py``). This module reuses
that *vocabulary* via :func:`default_role_authorization` below, but
keeps the service functions themselves framework-agnostic (no FastAPI
import here) so they stay trivially testable with allow/deny stubs, as
the Faz 2.9.1 instruction requires.
"""

from __future__ import annotations

import sqlite3
from typing import Callable, List, Optional

from pydantic import ValidationError

from .errors import (
    ContentVersionUnchangedError,
    EmptyPatchError,
    PartialUpdateFailureError,
    QuestionAlreadyArchivedError,
    QuestionAlreadyDeletedError,
    QuestionBankValidationError,
    QuestionNotDeletedError,
    UnauthorizedTransitionError,
)
from .patch import QuestionPatch
from .schema import QuestionRecord
from .store import (
    _delete_question_content_version,
    append_lifecycle_audit,
    append_status_history,
    fetch_lifecycle_audit,
    fetch_publishable_candidates,
    fetch_record,
    fetch_records_by_question_id,
    fetch_status_history,
    load_question_content,
    register_record,
    save_question_content,
    set_records_archived,
    set_records_deleted_flag,
    update_record_status,
)
from .transitions import AUTHORIZATION_REQUIRED_TRANSITIONS, ValidationStatus
from .validator import (
    require_valid,
    validate_publishable,
    validate_record_structure,
    validate_revision_reason,
    validate_transition_request,
)

#: (actor_role: str, action: str) -> bool. No FastAPI/JWT dependency
#: here -- the API layer (out of Faz 2.9.1's file scope) is expected to
#: wire a real callback that resolves the authenticated user's role
#: (via backend.api.dependencies.user) and calls this module's
#: functions with it. Tests use trivial allow-all/deny-all stubs.
AuthorizationCallback = Callable[[str, str], bool]


def default_role_authorization(role: str, action: str) -> bool:
    """Reference implementation reusing TorqPro's existing role
    vocabulary verbatim (admin/engineer/viewer), mirroring the exact
    ``if u["role"]=="viewer": raise HTTPException(403, ...)`` pattern
    used throughout ``backend/app.py``. Not a new role system -- if
    the project's role vocabulary ever changes, this one function is
    the only place that needs updating."""
    del action  # every gated action currently uses the same rule
    return role in ("admin", "engineer")


def _require_authorized(
    authorize: AuthorizationCallback, actor_role: str, action: str
) -> None:
    if action in AUTHORIZATION_REQUIRED_TRANSITIONS and not authorize(actor_role, action):
        raise UnauthorizedTransitionError(
            f"actor role '{actor_role}' is not authorized to perform '{action}'"
        )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------
# Content loading (read-through to the JSON store, validated)
# ---------------------------------------------------------------------


def load_question_content_validated(
    question_id: str, content_version: Optional[int] = None
) -> QuestionRecord:
    record = load_question_content(question_id, content_version)
    require_valid(record)
    return record


# ---------------------------------------------------------------------
# Registration (JSON content must already exist -- no orphan SQLite rows)
# ---------------------------------------------------------------------


def register_question(
    c: sqlite3.Connection, *, question_id: str, content_version: int, actor: str
) -> None:
    """Creates the initial ``draft`` SQLite record for an existing
    JSON content snapshot. Raises :class:`backend.question_bank.errors.
    ContentNotFoundError` if the JSON content does not exist -- the
    JSON/SQLite ``question_id``/``content_version`` mismatch rejection
    required by Faz 2.9.1. This function does not create JSON content
    itself; use :func:`register_question_content` for that."""
    # Raises ContentNotFoundError if absent -- deliberately not caught here.
    record = load_question_content_validated(question_id, content_version)

    now = _now_iso()
    try:
        c.execute("BEGIN")
        register_record(
            c,
            question_id=record.question_id,
            content_version=record.content_version,
            now_iso=now,
            validation_status=ValidationStatus.DRAFT.value,
        )
        append_status_history(
            c,
            question_id=record.question_id,
            from_status=None,
            to_status=ValidationStatus.DRAFT.value,
            actor=actor,
            now_iso=now,
            content_version_before=None,
            content_version_after=record.content_version,
        )
        c.commit()
    except Exception:
        c.rollback()
        raise


def register_question_content(record: QuestionRecord) -> None:
    """Validates and appends a brand-new content snapshot to the JSON
    store. Does not touch SQLite -- call :func:`register_question`
    afterwards to create the corresponding lifecycle record."""
    require_valid(record)
    save_question_content(record)


# ---------------------------------------------------------------------
# Faz 2.9.3: content update (implemented as an append-only revision)
# ---------------------------------------------------------------------


def _pydantic_reasons(exc: ValidationError) -> List[str]:
    reasons = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        reasons.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return reasons


def update_question(
    c: sqlite3.Connection, *, question_id: str, patch: QuestionPatch, actor: str
) -> QuestionRecord:
    """Faz 2.9.3: partial ("PATCH") update of a question's content.

    Deliberately **not** an in-place mutation of an existing
    ``(question_id, content_version)`` record -- that would break both
    :class:`backend.question_bank.schema.QuestionRecord`'s own
    immutability contract ("a content change always means a new
    content_version, never an edit in place") and
    :func:`backend.question_bank.store.save_question_content`'s
    silent-overwrite guard. Instead this function computes the merged
    result, and -- only if that merge is an actual change -- appends it
    as a brand-new ``content_version = current_version + 1`` and
    registers that new version in SQLite exactly the way
    :func:`register_question` registers any other brand-new version
    (``draft``, ``from_status=None``). Every previously existing
    ``(question_id, content_version)`` row, in JSON and in SQLite alike,
    is left completely untouched.

    Only fields present in ``patch`` (``model_dump(exclude_unset=True)``)
    are applied; every omitted field keeps the current version's value.
    ``question_id`` and ``content_version`` are not patchable at all --
    :class:`backend.question_bank.patch.QuestionPatch` has no fields for
    them -- and no lifecycle field (``validation_status`` etc.) can be
    set through this path either, since those live only in SQLite and
    are never part of :class:`QuestionRecord`.

    Write ordering and partial-failure behaviour (JSON + SQLite are two
    separate storage backends with no shared/distributed transaction --
    true cross-store atomicity is not technically achievable here):

    1. The new content snapshot is appended to the JSON store first.
       This mirrors the existing two-step ``register_question_content()``
       then ``register_question()`` pattern -- SQLite registration
       already requires the JSON content to exist first
       (``register_question``'s own docstring), so this ordering is
       forced, not a new choice made here.
    2. The SQLite draft record + status-history entry are then written
       inside one transaction, committed together or rolled back
       together.
    3. If step 2 fails, this function immediately performs a *best-
       effort compensating delete* of the exact JSON record step 1 just
       wrote (:func:`backend.question_bank.store._delete_question_content_version`,
       a narrowly-scoped helper used from nowhere else -- see its own
       docstring for why this does not weaken the append-only contract:
       it only ever undoes this same call's own half-finished write,
       never a content_version that ever had a completed, observable
       SQLite registration).
       - If the compensating delete succeeds, the net effect is exactly
         as if the update had never been attempted at all: no new
         content_version in JSON, no new SQLite row, the previous
         latest version completely unchanged.
       - If the compensating delete *also* fails (a genuine double
         failure -- e.g. the filesystem itself is unavailable), true
         atomicity is not achievable and this is not hidden: the raised
         error explicitly says so, and an orphaned ``content_version``
         may remain in JSON with no matching SQLite row. Even in that
         residual case the orphan cannot leak into normal use --
         *every* publishable-only read path in this module (the default
         everywhere) already treats a JSON record with no matching
         SQLite row as "not publishable"
         (``retrieval._status_map``'s own docstring), and
         :func:`load_question_content_validated` always resolves
         "current" to the JSON store's *latest* version regardless of
         SQLite state, so a future ``update_question`` call would
         simply treat that orphan as its own new base content rather
         than silently losing data. Detection is a plain audit
         (any JSON ``content_version`` with no matching
         ``question_bank_records`` row is, by definition, an orphan);
         manual completion via :func:`register_question` remains
         available.
       In both cases :class:`backend.question_bank.errors.
       PartialUpdateFailureError` is raised so the caller is always told
       about the failure explicitly rather than seeing it swallowed.

    Raises:
        EmptyPatchError: ``patch`` has no fields set at all.
        ContentNotFoundError: ``question_id`` has no existing content.
        QuestionBankValidationError: the merged content fails schema or
            structural validation.
        DuplicateContentVersionError: a concurrent update already
            claimed ``current_version + 1`` (race condition) -- the
            append-only guard in :func:`save_question_content` catches
            this; the caller should reload and retry.
        PartialUpdateFailureError: see (3) above.
    """
    provided = patch.model_dump(exclude_unset=True)
    if not provided:
        raise EmptyPatchError()

    current = load_question_content_validated(question_id)

    merged_fields = current.model_dump()
    merged_fields.update(provided)

    try:
        merged_at_current_version = QuestionRecord.model_validate(merged_fields)
    except ValidationError as exc:
        raise QuestionBankValidationError(_pydantic_reasons(exc)) from exc

    if merged_at_current_version.model_dump(
        exclude={"content_version"}
    ) == current.model_dump(exclude={"content_version"}):
        # No-op: every provided field's value equals the current
        # version's value. No new content_version, no SQLite write, no
        # status-history entry -- explicit and deterministic per the
        # Faz 2.9.3 instruction.
        return current

    structure_reasons = validate_record_structure(merged_at_current_version)
    if structure_reasons:
        raise QuestionBankValidationError(structure_reasons)

    target_version = current.content_version + 1
    new_record = merged_at_current_version.model_copy(
        update={"content_version": target_version}
    )

    # Step 1: JSON append (append-only; raises DuplicateContentVersionError
    # on a concurrent racing writer -- propagated as-is).
    save_question_content(new_record)

    # Step 2: SQLite draft registration + status history, one transaction.
    now = _now_iso()
    try:
        c.execute("BEGIN")
        register_record(
            c,
            question_id=new_record.question_id,
            content_version=target_version,
            now_iso=now,
            validation_status=ValidationStatus.DRAFT.value,
        )
        append_status_history(
            c,
            question_id=new_record.question_id,
            from_status=None,
            to_status=ValidationStatus.DRAFT.value,
            actor=actor,
            now_iso=now,
            revision_reason="content updated via PATCH",
            content_version_before=current.content_version,
            content_version_after=target_version,
        )
        c.commit()
    except Exception as exc:
        c.rollback()
        try:
            compensated = _delete_question_content_version(
                new_record.question_id, target_version
            )
        except Exception:
            compensated = False

        if compensated:
            raise PartialUpdateFailureError(
                f"{question_id}@v{target_version} için SQLite lifecycle kaydı başarısız "
                "oldu; işlem geri alındı (JSON içeriği otomatik olarak temizlendi, "
                "orphan content_version bırakılmadı). Değişiklik hiç uygulanmamış "
                "gibi davranın ve isterseniz tekrar deneyin."
            ) from exc

        raise PartialUpdateFailureError(
            f"{question_id}@v{target_version} için SQLite lifecycle kaydı başarısız oldu "
            "VE JSON telafi (compensation) silme işlemi de başarısız oldu -- gerçek "
            "atomicity bu iki ayrı depolama katmanı arasında teknik olarak garanti "
            "edilemez. content_version orphan olarak JSON'da kalmış olabilir. Bu "
            "orphan varsayılan publishable_only=True okuma yolunda görünmez (SQLite "
            "kaydı yok), ama kalıcı temizlik için manuel doğrulama gerekir: JSON'daki "
            "her content_version'ın question_bank_records tablosunda bir karşılığı "
            "olup olmadığını denetleyin; eksikse register_question() ile tamamlayın "
            "ya da içeriği manuel temizleyin."
        ) from exc

    return new_record


# ---------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------


def submit_for_technical_review(
    c: sqlite3.Connection, *, question_id: str, content_version: int, actor: str
) -> None:
    _transition(
        c,
        question_id=question_id,
        content_version=content_version,
        new_status=ValidationStatus.TECHNICAL_REVIEW.value,
        actor=actor,
    )


def return_to_draft(
    c: sqlite3.Connection,
    *,
    question_id: str,
    content_version_before: int,
    content_version_after: int,
    actor: str,
    actor_role: str,
    revision_reason: str,
    authorize: AuthorizationCallback,
) -> None:
    """Handles both ``technical_review -> draft`` and
    ``rejected -> draft`` (both are legal per the transition table).
    Requires: revision_reason (>=20 chars trimmed), authorization,
    and a strictly different ``content_version_after``."""
    reasons = validate_revision_reason(revision_reason)
    if reasons:
        from .errors import MissingRevisionReasonError

        raise MissingRevisionReasonError("; ".join(reasons))

    if content_version_after == content_version_before:
        raise ContentVersionUnchangedError(
            "return_to_draft requires content_version_after != content_version_before"
        )

    _require_authorized(authorize, actor_role, "return_to_draft")

    current = fetch_record(c, question_id, content_version_before)
    previous_status = current["validation_status"] if current else None

    _transition(
        c,
        question_id=question_id,
        content_version=content_version_before,
        new_status=ValidationStatus.DRAFT.value,
        actor=actor,
        revision_reason=revision_reason.strip(),
        content_version_after=content_version_after,
        _previous_status_override=previous_status,
    )


def validate_question(
    c: sqlite3.Connection,
    *,
    question_id: str,
    content_version: int,
    actor: str,
    actor_role: str,
    reviewed_by: str,
    review_date: str,
    authorize: AuthorizationCallback,
) -> None:
    _require_authorized(authorize, actor_role, "validate_question")
    _transition(
        c,
        question_id=question_id,
        content_version=content_version,
        new_status=ValidationStatus.VALIDATED.value,
        actor=actor,
        reviewed_by=reviewed_by,
        review_date=review_date,
    )


def reject_question(
    c: sqlite3.Connection,
    *,
    question_id: str,
    content_version: int,
    actor: str,
    actor_role: str,
    reason: str,
    authorize: AuthorizationCallback,
) -> None:
    _require_authorized(authorize, actor_role, "reject_question")
    _transition(
        c,
        question_id=question_id,
        content_version=content_version,
        new_status=ValidationStatus.REJECTED.value,
        actor=actor,
        revision_reason=reason,
    )


def deprecate_question(
    c: sqlite3.Connection,
    *,
    question_id: str,
    content_version: int,
    actor: str,
    actor_role: str,
    authorize: AuthorizationCallback,
) -> None:
    _require_authorized(authorize, actor_role, "deprecate_question")
    _transition(
        c,
        question_id=question_id,
        content_version=content_version,
        new_status=ValidationStatus.DEPRECATED.value,
        actor=actor,
    )


def _transition(
    c: sqlite3.Connection,
    *,
    question_id: str,
    content_version: int,
    new_status: str,
    actor: str,
    revision_reason: Optional[str] = None,
    reviewed_by: Optional[str] = None,
    review_date: Optional[str] = None,
    content_version_after: Optional[int] = None,
    _previous_status_override: Optional[str] = None,
) -> None:
    current = fetch_record(c, question_id, content_version)
    if current is None:
        from .errors import ContentNotFoundError

        raise ContentNotFoundError(
            f"{question_id}@v{content_version} SQLite lifecycle kaydı bulunamadı"
        )
    previous_status = _previous_status_override or current["validation_status"]

    reasons = validate_transition_request(previous_status, new_status)
    if reasons:
        from .errors import InvalidTransitionError

        raise InvalidTransitionError(previous_status, new_status)

    now = _now_iso()
    try:
        c.execute("BEGIN")
        target_version = content_version_after if content_version_after is not None else content_version
        if content_version_after is not None:
            # return_to_draft: the audit row targets the *old* version's
            # question_id (there is no new SQLite record row created
            # here -- the new content_version's own draft record is
            # expected to be created via register_question() once its
            # JSON content is authored).
            append_status_history(
                c,
                question_id=question_id,
                from_status=previous_status,
                to_status=new_status,
                actor=actor,
                now_iso=now,
                revision_reason=revision_reason,
                content_version_before=content_version,
                content_version_after=content_version_after,
            )
        else:
            update_record_status(
                c,
                question_id=question_id,
                content_version=content_version,
                new_status=new_status,
                now_iso=now,
                reviewed_by=reviewed_by,
                review_date=review_date,
            )
            append_status_history(
                c,
                question_id=question_id,
                from_status=previous_status,
                to_status=new_status,
                actor=actor,
                now_iso=now,
                revision_reason=revision_reason,
                content_version_before=content_version,
                content_version_after=target_version,
            )
        c.commit()
    except Exception:
        c.rollback()
        raise


# ---------------------------------------------------------------------
# Faz 2.9.4: soft-delete / restore / archive lifecycle management
#
# All three functions below act on *every* ``content_version`` row of
# a ``question_id`` at once, inside a single SQLite transaction
# (commit or rollback together) -- per the Faz 2.9.4 instruction that
# these operations must never partially apply across a question's
# versions. None of the three ever touches ``validation_status`` (that
# remains Faz 2.9.1/2.9.3's exclusive concern) and none of them uses
# ``question_bank_status_history`` -- see ``store.DDL``'s
# ``question_bank_lifecycle_audit`` table docstring for why that table
# is a deliberately separate, additive audit trail rather than a reuse
# of the validation-status one.
# ---------------------------------------------------------------------


def _lifecycle_rows_or_not_found(c: sqlite3.Connection, question_id: str) -> list:
    from .errors import ContentNotFoundError

    rows = fetch_records_by_question_id(c, question_id)
    if not rows:
        raise ContentNotFoundError(
            f"question_id '{question_id}' için SQLite lifecycle kaydı bulunamadı"
        )
    return rows


def delete_question(
    c: sqlite3.Connection,
    *,
    question_id: str,
    actor: str,
    actor_role: str,
    authorize: AuthorizationCallback,
) -> List[int]:
    """Soft-deletes (``is_deleted=1``) every ``content_version`` row of
    ``question_id``. Never a hard delete -- no row is ever removed from
    ``question_bank_records`` or the JSON content store by this
    function. Raises :class:`backend.question_bank.errors.
    QuestionAlreadyDeletedError` if every existing row is already
    ``is_deleted=1`` (nothing to do). Returns the list of
    ``content_version`` values affected."""
    _require_authorized(authorize, actor_role, "soft_delete")
    rows = _lifecycle_rows_or_not_found(c, question_id)
    if all(bool(row["is_deleted"]) for row in rows):
        raise QuestionAlreadyDeletedError(
            f"question_id '{question_id}' zaten silinmiş durumda (is_deleted=1)"
        )

    now = _now_iso()
    try:
        c.execute("BEGIN")
        set_records_deleted_flag(
            c, question_id=question_id, is_deleted=True, now_iso=now, actor=actor
        )
        for row in rows:
            append_lifecycle_audit(
                c,
                question_id=question_id,
                content_version=row["content_version"],
                action="soft_delete",
                actor=actor,
                actor_role=actor_role,
                previous_is_deleted=bool(row["is_deleted"]),
                new_is_deleted=True,
                previous_archived_at=row["archived_at"],
                new_archived_at=row["archived_at"],
                now_iso=now,
            )
        c.commit()
    except Exception:
        c.rollback()
        raise

    return [row["content_version"] for row in rows]


def restore_question(
    c: sqlite3.Connection,
    *,
    question_id: str,
    actor: str,
    actor_role: str,
    authorize: AuthorizationCallback,
) -> List[int]:
    """Restores (``is_deleted=0``) every ``content_version`` row of
    ``question_id``. Deliberately clears **only** ``is_deleted`` --
    ``archived_at``/``archived_by`` are left completely untouched (Faz
    2.9.4 instruction: restore must not clear archive state; a
    restored-but-still-archived question stays hidden from default
    retrieval until a future, out-of-scope "unarchive" action exists).
    Raises :class:`backend.question_bank.errors.QuestionNotDeletedError`
    if no existing row is currently ``is_deleted=1``."""
    _require_authorized(authorize, actor_role, "restore")
    rows = _lifecycle_rows_or_not_found(c, question_id)
    if all(not bool(row["is_deleted"]) for row in rows):
        raise QuestionNotDeletedError(
            f"question_id '{question_id}' silinmiş durumda değil (is_deleted=0)"
        )

    now = _now_iso()
    try:
        c.execute("BEGIN")
        set_records_deleted_flag(
            c, question_id=question_id, is_deleted=False, now_iso=now, actor=actor
        )
        for row in rows:
            append_lifecycle_audit(
                c,
                question_id=question_id,
                content_version=row["content_version"],
                action="restore",
                actor=actor,
                actor_role=actor_role,
                previous_is_deleted=bool(row["is_deleted"]),
                new_is_deleted=False,
                previous_archived_at=row["archived_at"],
                new_archived_at=row["archived_at"],
                now_iso=now,
            )
        c.commit()
    except Exception:
        c.rollback()
        raise

    return [row["content_version"] for row in rows]


def archive_question(
    c: sqlite3.Connection,
    *,
    question_id: str,
    actor: str,
    actor_role: str,
    authorize: AuthorizationCallback,
) -> List[int]:
    """Sets ``archived_at``/``archived_by`` (and ``modified_at``/
    ``modified_by``) on every ``content_version`` row of
    ``question_id``. Never touches ``is_deleted`` or
    ``validation_status``. There is no "unarchive" counterpart in Faz
    2.9.4 -- deliberately out of this phase's scope. Raises
    :class:`backend.question_bank.errors.QuestionAlreadyArchivedError`
    if every existing row already has a non-null ``archived_at``."""
    _require_authorized(authorize, actor_role, "archive")
    rows = _lifecycle_rows_or_not_found(c, question_id)
    if all(row["archived_at"] is not None for row in rows):
        raise QuestionAlreadyArchivedError(
            f"question_id '{question_id}' zaten arşivlenmiş durumda"
        )

    now = _now_iso()
    try:
        c.execute("BEGIN")
        set_records_archived(c, question_id=question_id, now_iso=now, actor=actor)
        for row in rows:
            append_lifecycle_audit(
                c,
                question_id=question_id,
                content_version=row["content_version"],
                action="archive",
                actor=actor,
                actor_role=actor_role,
                previous_is_deleted=bool(row["is_deleted"]),
                new_is_deleted=bool(row["is_deleted"]),
                previous_archived_at=row["archived_at"],
                new_archived_at=now,
                now_iso=now,
            )
        c.commit()
    except Exception:
        c.rollback()
        raise

    return [row["content_version"] for row in rows]


def get_lifecycle_audit(c: sqlite3.Connection, question_id: str) -> list:
    return fetch_lifecycle_audit(c, question_id)


# ---------------------------------------------------------------------
# Read paths
# ---------------------------------------------------------------------


def get_publishable_questions(c: sqlite3.Connection) -> List[QuestionRecord]:
    """Cross-references SQLite's authoritative ``validated`` status
    against JSON content's ``is_active`` flag -- see
    ``validator.validate_publishable``'s docstring for why SQLite
    status is always authoritative for visibility."""
    rows = fetch_publishable_candidates(c)
    results: List[QuestionRecord] = []
    for row in rows:
        try:
            record = load_question_content(row["question_id"], row["content_version"])
        except Exception:
            continue
        if validate_publishable(record, row["validation_status"]):
            results.append(record)
    return results


def get_status_history(c: sqlite3.Connection, question_id: str) -> list:
    return fetch_status_history(c, question_id)
