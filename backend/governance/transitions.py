"""TorqPro Engineering Governance - Faz 2.8.11 Stage 2 generic
transition-table plumbing.

The three lifecycle groups (review, publication, resolution) each
have their own status enum and their own closed transition table
(``backend.governance.enums``) -- ADR-0014 is explicit that these
must never be merged into one status field. This module's two
functions are pure, generic mechanics for *checking membership in
whichever table is passed in*; they carry no lifecycle-specific
semantics themselves; nothing here couples the three lifecycle
groups together (each caller passes its own table).
"""

from __future__ import annotations

from typing import Dict, FrozenSet, TypeVar

from .exceptions import InvalidTransitionError

StatusT = TypeVar("StatusT")


def is_transition_allowed(
    transitions: Dict[StatusT, FrozenSet[StatusT]],
    previous_status: StatusT,
    new_status: StatusT,
) -> bool:
    """Pure predicate: does ``transitions`` permit this exact
    ``previous_status -> new_status`` move? Does not raise. A status
    absent as a key (i.e. terminal) yields an empty transition set,
    so this returns ``False`` rather than raising ``KeyError``."""
    return new_status in transitions.get(previous_status, frozenset())


def validate_transition(
    transitions: Dict[StatusT, FrozenSet[StatusT]],
    previous_status: StatusT,
    new_status: StatusT,
    *,
    lifecycle_name: str,
) -> None:
    """Raise :class:`InvalidTransitionError` if this transition is
    not legal under ``transitions``; return ``None`` (no exception)
    if it is. ``lifecycle_name`` (``"review"`` / ``"publication"`` /
    ``"resolution"``) is only used to make the raised error's message
    identify which lifecycle group rejected the transition."""
    if not is_transition_allowed(transitions, previous_status, new_status):
        raise InvalidTransitionError(lifecycle_name, previous_status, new_status)


__all__ = ["is_transition_allowed", "validate_transition"]
