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


class QuestionBankValidationError(QuestionBankError):
    """One or more structural/content validation checks failed. Carries
    the full list of human-readable failure reasons."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = list(reasons)
        super().__init__("; ".join(reasons) if reasons else "validation failed")
