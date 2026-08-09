"""TorqPro AI Gateway - permission / user-context module.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 1
("permission/context builder"), Karar 5 and Karar 9 (write/approval
actions are always a permission failure, never a supported path).

Deliberately framework-agnostic: this module never imports
``fastapi``, ``backend.app`` or ``backend.api.dependencies``. The
(not-yet-built, later-phase) HTTP route layer is responsible for
turning the existing ``backend.api.dependencies.user`` Depends result
(a ``dict`` with ``id``/``username``/``display_name``/``is_active``/
``role`` keys -- see that module) into a :class:`UserContext` before
calling into ``backend.ai_gateway``. This mirrors
``backend.question_bank.service``'s own framework-agnostic design
(see that module's docstring: "keeps the service functions themselves
framework-agnostic ... so they stay trivially testable").

No new role vocabulary is introduced in this phase. ``UserContext.role``
reuses TorqPro's existing role strings (``admin``/``engineer``/
``viewer``) verbatim -- this module does not define an ``ai_reviewer``
role or any other new RBAC scope; that is explicitly out of scope for
v3.0.0-alpha.1 (ADR-0019 concern, not yet written).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.ai_gateway.exceptions import PermissionDeniedError

#: Frozenset, not a list -- membership-checked only, never iterated in
#: a way that would assume ordering.
_WRITE_ACTIONS = frozenset(
    {
        "create",
        "update",
        "delete",
        "approve",
        "reject",
        "validate",
        "activate",
        "deprecate",
        "restore",
        "archive",
    }
)


@dataclass(frozen=True)
class UserContext:
    """Minimal, framework-agnostic snapshot of the authenticated user
    making an AI request.

    Attributes:
        user_id: TorqPro user id (matches ``users.id``).
        role: Existing TorqPro role string (``admin``/``engineer``/
            ``viewer``). Not validated against a closed set here --
            that remains ``backend.app``'s responsibility; this
            module only reads the value.
        is_active: Mirrors ``users.is_active``. An inactive user is
            always denied (see :func:`ensure_active_user`).
        language: Active UI language ("tr" or "en"), used by
            ``context_builder`` to select which of a bilingual
            ``EvidenceSource`` field pair to prioritize. Defaults to
            ``"tr"`` to match TorqPro's default UI language.
    """

    user_id: int
    role: str
    is_active: bool
    language: str = "tr"


def ensure_active_user(user: UserContext) -> None:
    """Raise :class:`PermissionDeniedError` unless ``user`` is an
    active account. Mirrors the existing ``backend.api.dependencies.
    user()`` check ("Kullanıcı aktif değil") at the AI-gateway
    boundary, without importing that module."""
    if not user.is_active:
        raise PermissionDeniedError(f"user_id={user.user_id} is not active")


def ensure_read_only_action(action: str) -> None:
    """Raise :class:`PermissionDeniedError` if ``action`` names a
    write/approval-style operation.

    This is the concrete enforcement point for ADR-0017 Karar 1 and
    Karar 9: the AI gateway has no write path into any TorqPro
    domain. Any caller that constructs a request naming one of
    ``_WRITE_ACTIONS`` is rejected here, before any retrieval, tool
    call or model invocation happens.
    """
    if action.strip().casefold() in _WRITE_ACTIONS:
        raise PermissionDeniedError(
            f"action '{action}' is a write/approval action; "
            "the AI gateway is read-only/advisory-only (ADR-0017 Karar 1/9)"
        )


__all__ = ["UserContext", "ensure_active_user", "ensure_read_only_action"]
