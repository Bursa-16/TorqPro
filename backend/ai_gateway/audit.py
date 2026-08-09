"""TorqPro AI Gateway - audit recording.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 8
("Audit ve trace kayıtlarının hangi katmanda tutulacağı").

Scope of this phase (deliberately limited, per ADR-0017 Karar 12/13):
this module defines the audit *record shape* and an append-only sink
*interface*, plus an in-memory implementation for use by the
orchestrator and by tests. It does **not** create or migrate any
SQLite table (``ai_interactions``/``ai_evidence_links``/
``ai_feedback``) -- that is explicitly deferred to a later,
separately-approved phase once this in-process pipeline is proven.
``backend/app.py`` is not touched by this phase and its
``SCHEMA_VERSION`` is not bumped.

Append-only by construction: :class:`AuditSink` declares exactly one
mutating method, ``record``, and no ``update``/``delete``/``clear``
method exists on the interface or on :class:`InMemoryAuditSink`. A
previously recorded :class:`AIInteractionRecord` can therefore never
be altered or removed through this module's API -- mirroring
``backend.app``'s own ``audit_log`` table (``INSERT``-only) and
``backend.question_bank``'s ``question_bank_status_history``
(append-only audit trail).

Privacy note (ADR-0017 Karar 8, forward reference to ADR-0019): raw
query text is intentionally not part of :class:`AIInteractionRecord`
-- only a caller-supplied ``query_text_hash`` is recorded. Computing
that hash is the orchestrator's responsibility, not this module's;
``audit.py`` never sees or stores the raw query text.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class AIInteractionRecord:
    """One immutable audit entry for a single AI-gateway interaction.

    Attributes:
        user_id: Who made the request.
        query_text_hash: Caller-supplied hash/digest of the original
            query text -- never the raw text itself (see module
            docstring).
        evidence_source_ids: ``(source_type, source_id)`` pairs for
            every ``EvidenceSource`` that grounded the answer. Empty
            when the answer was an insufficient-evidence notice.
        calculation_formula_ids: Formula IDs from
            ``CalculationResponse.results`` when a deterministic
            calculation backed the answer; empty otherwise. Recorded
            by reference (the ID string only) -- this module never
            copies a ``CalculationResult.value`` into the audit
            trail.
        model_name: Which ``AIModelClient`` produced the answer, or
            ``None`` for an insufficient-evidence outcome.
        had_sufficient_evidence: Mirrors
            ``EvidenceCheckResult.has_sufficient_evidence``.
        created_at: ISO-8601 timestamp, supplied by the caller (this
            module does not read the system clock, keeping it
            trivially testable -- mirrors
            ``backend.question_bank.service``'s own
            caller-supplied-timestamp discipline where relevant).
    """

    user_id: int
    query_text_hash: str
    evidence_source_ids: Tuple[Tuple[str, str], ...]
    calculation_formula_ids: Tuple[str, ...]
    model_name: str | None
    had_sufficient_evidence: bool
    created_at: str


class AuditSink(abc.ABC):
    """Append-only audit destination.

    Exactly one mutating method (``record``) is declared. No
    ``update``/``delete``/``clear`` method exists on this interface --
    see module docstring.
    """

    @abc.abstractmethod
    def record(self, entry: AIInteractionRecord) -> None:
        """Append ``entry``. Implementations must not mutate or
        remove any previously recorded entry."""
        raise NotImplementedError


class InMemoryAuditSink(AuditSink):
    """Development/test append-only sink.

    Holds recorded entries in an internal list for the lifetime of
    the sink instance. Real SQLite persistence
    (``ai_interactions``/``ai_evidence_links`` tables) is a later,
    separately-approved phase (ADR-0017 Karar 8/12) -- this class is
    the only ``AuditSink`` implementation in v3.0.0-alpha.1.
    """

    def __init__(self) -> None:
        self._entries: List[AIInteractionRecord] = []

    def record(self, entry: AIInteractionRecord) -> None:
        self._entries.append(entry)

    def all_entries(self) -> Sequence[AIInteractionRecord]:
        """Read-only snapshot of every entry recorded so far, in
        insertion order. Returns a new tuple each call so the caller
        cannot mutate this sink's internal state through the returned
        value."""
        return tuple(self._entries)


__all__ = ["AIInteractionRecord", "AuditSink", "InMemoryAuditSink"]
