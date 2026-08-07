"""Question Bank lifecycle status vocabulary and closed transition
table.

Mirrors ``backend/governance/enums.py``'s design (ADR-0014): a closed,
explicit transition table plus an import-time exhaustiveness
assertion, so a future new status can never be silently unaccounted
for. The *generic* transition-legality predicate
(``is_transition_allowed``) is reused directly from
``backend.governance.transitions`` -- it is pure, type-parametric, and
carries no lifecycle-specific semantics of its own, so importing it
here duplicates nothing. This module's own
:class:`backend.question_bank.errors.InvalidTransitionError` is raised
by the service layer, not by the reused predicate itself (the
predicate only returns ``bool``).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet

from backend.governance.transitions import is_transition_allowed


class ValidationStatus(str, Enum):
    DRAFT = "draft"
    TECHNICAL_REVIEW = "technical_review"
    VALIDATED = "validated"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


#: Closed transition table. Faz 2.9.1's required minimum set, taken
#: verbatim from the implementation instruction:
#:   draft -> technical_review
#:   technical_review -> validated
#:   technical_review -> rejected
#:   technical_review -> draft
#:   rejected -> draft
#:   validated -> deprecated
QUESTION_VALIDATION_TRANSITIONS: Dict[ValidationStatus, FrozenSet[ValidationStatus]] = {
    ValidationStatus.DRAFT: frozenset({ValidationStatus.TECHNICAL_REVIEW}),
    ValidationStatus.TECHNICAL_REVIEW: frozenset(
        {ValidationStatus.VALIDATED, ValidationStatus.REJECTED, ValidationStatus.DRAFT}
    ),
    ValidationStatus.REJECTED: frozenset({ValidationStatus.DRAFT}),
    ValidationStatus.VALIDATED: frozenset({ValidationStatus.DEPRECATED}),
}

#: Terminal: no outgoing transition in this base model.
QUESTION_VALIDATION_TERMINAL: FrozenSet[ValidationStatus] = frozenset(
    {ValidationStatus.DEPRECATED}
)


def _assert_exhaustive() -> None:
    unaccounted = [
        s
        for s in ValidationStatus
        if s not in QUESTION_VALIDATION_TRANSITIONS and s not in QUESTION_VALIDATION_TERMINAL
    ]
    assert not unaccounted, (
        f"ValidationStatus member(s) {[s.value for s in unaccounted]} have no "
        "transition table entry and are not marked terminal."
    )


_assert_exhaustive()


def is_valid_transition(previous: ValidationStatus, new: ValidationStatus) -> bool:
    """Thin, question-bank-typed wrapper around the reused generic
    predicate -- kept here so callers never import
    ``backend.governance.transitions`` directly."""
    return is_transition_allowed(QUESTION_VALIDATION_TRANSITIONS, previous, new)


#: Actions requiring authorization -- every non-DRAFT-originating
#: transition, plus the DRAFT->TECHNICAL_REVIEW submission itself, per
#: the Faz 2.9.1 instruction ("technical_review -> validated ve
#: validated -> deprecated geçişleri de authorization gerektirmeli",
#: and technical_review -> draft explicitly requires it). Submission
#: (draft -> technical_review) is intentionally left to the caller's
#: own judgement on whether authorization applies to authorship --
#: this module only enumerates the transitions that unambiguously
#: require it per the instruction text.
#: Faz 2.9.4 additions: soft-delete/restore/archive are not
#: ``ValidationStatus`` transitions at all (they never touch
#: ``validation_status`` -- see ``service.delete_question`` /
#: ``restore_question`` / ``archive_question``), but they are exactly
#: the kind of state-mutating, authorization-gated action this same
#: callback/policy mechanism already exists for. Reusing
#: ``AUTHORIZATION_REQUIRED_TRANSITIONS`` + the existing
#: ``AuthorizationCallback`` here means Faz 2.9.4 introduces no second,
#: parallel authorization mechanism.
AUTHORIZATION_REQUIRED_TRANSITIONS: FrozenSet[str] = frozenset(
    {
        "return_to_draft",
        "validate_question",
        "reject_question",
        "deprecate_question",
        "soft_delete",
        "restore",
        "archive",
    }
)

__all__ = [
    "ValidationStatus",
    "QUESTION_VALIDATION_TRANSITIONS",
    "QUESTION_VALIDATION_TERMINAL",
    "is_valid_transition",
    "AUTHORIZATION_REQUIRED_TRANSITIONS",
]
