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

from .errors import (
    ContentVersionUnchangedError,
    UnauthorizedTransitionError,
)
from .schema import QuestionRecord
from .store import (
    append_status_history,
    fetch_publishable_candidates,
    fetch_record,
    fetch_status_history,
    load_question_content,
    register_record,
    save_question_content,
    update_record_status,
)
from .transitions import AUTHORIZATION_REQUIRED_TRANSITIONS, ValidationStatus
from .validator import require_valid, validate_publishable, validate_revision_reason, validate_transition_request

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
