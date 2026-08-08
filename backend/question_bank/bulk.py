"""Question Bank bulk lifecycle-transition and tag operations (Faz 2.9.8).

Deliberately *not* a new persistence mechanism, a new transition rule,
or a second authorization system: every action this module performs is
a sequenced set of calls into the exact same single-item service
functions Faz 2.9.4/2.9.6 already established
(``submit_for_technical_review``, ``validate_question``,
``reject_question``, ``deprecate_question``, ``archive_question``) and
the exact same content-update path Faz 2.9.3 already established
(``update_question``). This module's only job is *sequencing* those
calls over many items in one request and reporting a per-item
succeeded/failed result -- no item's failure aborts the rest of the
batch, and (for the four ``ValidationStatus``-gated actions plus
``archive``) authorization is checked exactly once, up front, so an
unauthorized request touches zero items rather than partially applying
before failing partway through.

Each single-item service call keeps its own independent SQLite
transaction (``BEGIN``/``commit``/``rollback``) exactly as it already
does when invoked individually elsewhere in the codebase -- this
module does not wrap the whole batch in one shared transaction. A
later item's failure must never roll back an earlier item's
already-committed success, and true batch atomicity was never a
requirement here (partial success is the explicit, documented
contract of both functions below).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .errors import QuestionBankError, UnauthorizedTransitionError
from .patch import QuestionPatch
from .retrieval import normalize_tag
from .service import (
    AuthorizationCallback,
    archive_question,
    deprecate_question,
    load_question_content_validated,
    reject_question,
    submit_for_technical_review,
    update_question,
    validate_question,
)
from .transitions import AUTHORIZATION_REQUIRED_TRANSITIONS

#: Faz 2.9.8. No prior art in this module for a request-size cap, so
#: the closest existing precedent in the codebase
#: (``backend.governance.joint_revision_query.MAX_PAGE_SIZE``, 200) is
#: reused rather than inventing a new number.
MAX_BULK_ITEMS = 200

#: Wire action name -> the internal action string the reused
#: single-item functions/AUTHORIZATION_REQUIRED_TRANSITIONS already
#: use. "archive" acts on the whole question_id (every content_version
#: at once, per Faz 2.9.4 -- see ``service.archive_question``), never
#: on a single content_version, unlike the other four actions here.
_ACTION_TO_INTERNAL: Dict[str, str] = {
    "submit-for-review": "submit_for_technical_review",
    "validate": "validate_question",
    "reject": "reject_question",
    "deprecate": "deprecate_question",
    "archive": "archive",
}

#: Actions that operate on a single ``content_version`` (as opposed to
#: "archive", which always acts on every content_version of a
#: question_id at once).
CONTENT_VERSION_ACTIONS = frozenset({"submit-for-review", "validate", "reject", "deprecate"})


@dataclass
class BulkItemOutcome:
    """One item's result within a :class:`BulkResult`. ``extra`` carries
    action-specific additive detail (e.g. the resulting ``tags`` list
    for a bulk tag update) -- never a second definition of a field
    already present elsewhere on this dataclass."""

    question_id: str
    content_version: Optional[int]
    ok: bool
    error: Optional[str] = None
    extra: Optional[dict] = None


@dataclass
class BulkResult:
    succeeded: List[BulkItemOutcome] = field(default_factory=list)
    failed: List[BulkItemOutcome] = field(default_factory=list)


def bulk_transition(
    c: sqlite3.Connection,
    *,
    action: str,
    items: Sequence[Tuple[str, Optional[int]]],
    actor: str,
    actor_role: str,
    authorize: AuthorizationCallback,
    reviewed_by: Optional[str] = None,
    review_date: Optional[str] = None,
    reason: Optional[str] = None,
) -> BulkResult:
    """Applies one lifecycle action to many ``(question_id,
    content_version)`` items (``content_version`` is ignored for
    ``"archive"``, which always acts on the whole question -- see
    :data:`CONTENT_VERSION_ACTIONS`).

    Raises :class:`backend.question_bank.errors.UnauthorizedTransitionError`
    immediately, before touching any item, if ``action`` is
    authorization-gated (validate/reject/deprecate/archive -- exactly
    :data:`backend.question_bank.transitions.AUTHORIZATION_REQUIRED_TRANSITIONS`'s
    existing set) and ``authorize(actor_role, internal_action)`` denies
    it. ``submit-for-review`` remains ungated, matching the single-item
    route's own behaviour.

    Every other failure (``ContentNotFoundError``,
    ``InvalidTransitionError``, an already-archived question, ...) is
    caught per item and recorded in the returned
    :class:`BulkResult`'s ``failed`` list; it never aborts the
    remaining items in ``items``.
    """
    if action not in _ACTION_TO_INTERNAL:
        raise ValueError(f"unknown bulk transition action: {action!r}")

    internal_action = _ACTION_TO_INTERNAL[action]
    if internal_action in AUTHORIZATION_REQUIRED_TRANSITIONS and not authorize(
        actor_role, internal_action
    ):
        raise UnauthorizedTransitionError(
            f"actor role '{actor_role}' is not authorized to perform bulk '{action}'"
        )

    result = BulkResult()
    for question_id, content_version in items:
        try:
            if action == "submit-for-review":
                submit_for_technical_review(
                    c, question_id=question_id, content_version=content_version, actor=actor
                )
            elif action == "validate":
                validate_question(
                    c,
                    question_id=question_id,
                    content_version=content_version,
                    actor=actor,
                    actor_role=actor_role,
                    reviewed_by=reviewed_by,
                    review_date=review_date,
                    authorize=authorize,
                )
            elif action == "reject":
                reject_question(
                    c,
                    question_id=question_id,
                    content_version=content_version,
                    actor=actor,
                    actor_role=actor_role,
                    reason=reason,
                    authorize=authorize,
                )
            elif action == "deprecate":
                deprecate_question(
                    c,
                    question_id=question_id,
                    content_version=content_version,
                    actor=actor,
                    actor_role=actor_role,
                    authorize=authorize,
                )
            else:  # action == "archive"
                archive_question(
                    c,
                    question_id=question_id,
                    actor=actor,
                    actor_role=actor_role,
                    authorize=authorize,
                )
            result.succeeded.append(BulkItemOutcome(question_id, content_version, True))
        except QuestionBankError as exc:
            result.failed.append(BulkItemOutcome(question_id, content_version, False, str(exc)))
    return result


def bulk_update_tags(
    c: sqlite3.Connection,
    *,
    question_ids: Sequence[str],
    add: Sequence[str],
    remove: Sequence[str],
    actor: str,
) -> BulkResult:
    """Applies the same add/remove tag set to each ``question_id``'s
    current (latest) content_version, one
    :func:`backend.question_bank.service.update_question` PATCH call
    per question -- the exact same function, and exact same
    versioning/no-op/validation semantics, the single-item PATCH route
    already uses (see that function's own docstring). A question whose
    resulting tag set is unchanged (e.g. every ``add`` tag was already
    present and no ``remove`` tag was present) is a no-op there:
    ``update_question`` returns the unchanged current record, no new
    content_version, no SQLite write.

    Tag comparison reuses
    :func:`backend.question_bank.retrieval.normalize_tag`, the
    module's single existing case-insensitive/trimmed tag-comparison
    definition, so ``'ISO 16047'`` and ``'iso 16047'`` are treated as
    the same tag here exactly as they already are by search/filtering
    (Faz 2.9.5). Stored casing of a newly-added tag is whatever the
    caller supplied; an existing tag's stored casing is never altered
    by a ``remove`` that doesn't match it.

    Every failure (``ContentNotFoundError``, a structural validation
    failure on the merged record, ...) is caught per item and recorded
    in the returned :class:`BulkResult`'s ``failed`` list; it never
    aborts the remaining ``question_ids``.
    """
    add_clean = [t.strip() for t in add if t and t.strip()]
    remove_normalized = {normalize_tag(t) for t in remove if t and t.strip()}

    result = BulkResult()
    for question_id in question_ids:
        try:
            current = load_question_content_validated(question_id)
            new_tags = [t for t in current.tags if normalize_tag(t) not in remove_normalized]
            present_normalized = {normalize_tag(t) for t in new_tags}
            for t in add_clean:
                norm = normalize_tag(t)
                if norm not in present_normalized:
                    new_tags.append(t)
                    present_normalized.add(norm)

            record = update_question(
                c, question_id=question_id, patch=QuestionPatch(tags=new_tags), actor=actor
            )
            result.succeeded.append(
                BulkItemOutcome(
                    question_id, record.content_version, True, extra={"tags": record.tags}
                )
            )
        except QuestionBankError as exc:
            result.failed.append(BulkItemOutcome(question_id, None, False, str(exc)))
    return result


__all__ = [
    "MAX_BULK_ITEMS",
    "CONTENT_VERSION_ACTIONS",
    "BulkItemOutcome",
    "BulkResult",
    "bulk_transition",
    "bulk_update_tags",
]
