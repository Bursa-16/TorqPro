"""Domain errors for the Question Bank module.

Kept as this module's own closed error vocabulary rather than reusing
``backend.governance``'s or ``backend.library.washer_resolution_decisions``'s
exception types -- each governed module in TorqPro keeps its own error
types (ADR-0014, "Compatibility strategy"); only the *generic,
side-effect-free* transition-table predicate from
``backend.governance.transitions`` is reused directly (see
``backend/question_bank/transitions.py``), never its exception classes.
"""

from __future__ import annotations


class QuestionBankError(Exception):
    """Base class for every domain error this module raises."""


class DuplicateQuestionIdError(QuestionBankError):
    """A JSON content fixture contains the same ``question_id`` twice."""


class DuplicateContentVersionError(QuestionBankError):
    """The same ``(question_id, content_version)`` pair already exists.

    Raised by both the JSON content store (silent-overwrite guard) and
    the SQLite records store (unique-constraint backstop) -- see
    :func:`backend.question_bank.store.save_question_content` and
    :func:`backend.question_bank.store.register_record`.
    """


class ContentNotFoundError(QuestionBankError):
    """No JSON content exists for the requested ``(question_id,
    content_version)`` -- raised before any SQLite write is attempted,
    so a lifecycle record can never point at content that does not
    exist (JSON/SQLite ``question_id``/``content_version`` mismatch
    rejection)."""


class InvalidTransitionError(QuestionBankError):
    """The requested ``previous_status -> new_status`` transition is
    not in :data:`backend.question_bank.transitions.
    QUESTION_VALIDATION_TRANSITIONS`. Fail-closed: anything not
    explicitly listed is rejected."""

    def __init__(self, previous_status: str, new_status: str) -> None:
        self.previous_status = previous_status
        self.new_status = new_status
        super().__init__(
            f"Transition '{previous_status}' -> '{new_status}' is not permitted."
        )


class MissingRevisionReasonError(QuestionBankError):
    """``technical_review -> draft`` (or ``rejected -> draft``)
    attempted without a ``revision_reason`` of at least 20 characters
    after trimming."""


class ContentVersionUnchangedError(QuestionBankError):
    """A draft-return transition supplied a ``content_version_after``
    equal to ``content_version_before`` -- returning to draft must
    always target a new content version, never re-open the exact same
    one silently."""


class UnauthorizedTransitionError(QuestionBankError):
    """The supplied authorization callback denied this actor/action
    combination."""


class QuestionAlreadyDeletedError(QuestionBankError):
    """Faz 2.9.4: a soft-delete was requested for a ``question_id``
    whose SQLite records are already ``is_deleted=1``. Fail-closed,
    matching this module's existing "explicit error rather than a
    silent no-op" convention (e.g. :class:`DuplicateContentVersionError`
    for a silent-overwrite attempt)."""


class QuestionNotDeletedError(QuestionBankError):
    """Faz 2.9.4: a restore was requested for a ``question_id`` whose
    SQLite records are not currently ``is_deleted=1``."""


class QuestionAlreadyArchivedError(QuestionBankError):
    """Faz 2.9.4: an archive was requested for a ``question_id`` whose
    SQLite records already carry a non-null ``archived_at``. There is
    no "unarchive" action in this phase (deliberately out of scope), so
    an already-archived question can never legally be archived again."""


class QuestionBankValidationError(QuestionBankError):
    """One or more structural/content validation checks failed. Carries
    the full list of human-readable failure reasons."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = list(reasons)
        super().__init__("; ".join(reasons) if reasons else "validation failed")


class EmptyPatchError(QuestionBankValidationError):
    """Faz 2.9.3: a PATCH payload with zero fields set (``exclude_unset``
    is empty). Subclasses :class:`QuestionBankValidationError` on purpose
    -- an empty patch is a validation failure like any other, so it maps
    to the same 422 response without a second HTTP-mapping branch in the
    router."""

    def __init__(self) -> None:
        super().__init__(["PATCH body en az bir alan içermeli (empty patch)"])


class SnapshotDataError(QuestionBankError):
    """Faz 2.9.12: a stored ``question_bank_stats_snapshots`` row could
    not be decoded back into a statistics payload -- either its
    ``stats_json`` column is not valid JSON, or it decoded to
    something other than the ``compute_stats()``-shaped ``dict`` every
    snapshot is written as (see
    ``backend.question_bank.stats_history.create_snapshot``). Raised by
    :func:`backend.question_bank.stats_history.list_snapshots` so a
    single corrupted row fails loudly rather than being silently
    skipped or returned as-is to a caller expecting the normal shape.
    """


class PartialUpdateFailureError(QuestionBankError):
    """Faz 2.9.3: the paired SQLite lifecycle registration (draft record
    + status-history entry) for a new content_version failed inside its
    own transaction and was rolled back, *after* the new content
    snapshot had already been appended to the JSON store.

    JSON and SQLite are two separate storage backends with no shared
    transaction, so true cross-store atomicity is not technically
    achievable here. ``update_question`` always attempts a best-effort
    compensating delete of its own just-written JSON record before
    raising this error (see
    ``backend.question_bank.store._delete_question_content_version``).
    In the common case that compensation succeeds, no orphan is left
    behind and the net effect is as if the update had never been
    attempted. In the rare case that the compensating delete *also*
    fails, an orphaned ``content_version`` (a JSON record with no
    matching SQLite row) may remain; that residual case is called out
    explicitly in this error's message rather than hidden, and stays
    harmless to normal use because every publishable-only read path in
    this module already excludes any content_version with no matching
    SQLite row. See ``backend.question_bank.service.update_question``'s
    docstring for the full write-ordering rationale.
    """
