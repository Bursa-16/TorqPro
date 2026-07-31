"""TorqPro Engineering Governance - Faz 2.8.12 Stage 2 washer
resolution reconciliation.

Scans every recorded washer resolution decision
(``backend.library.washer_resolution_decisions_store.list_decisions``)
and, for each one, calls
``backend.governance.adapters.washer_resolution_sync.sync_washer_decision``
-- the exact same function a future Stage 3 washer API handler will
call inline. This module never re-implements classification,
mapping, or idempotency logic; it only orchestrates one call per
decision and aggregates the results deterministically (ADR-0015,
"Do not implement two separate synchronization algorithms").

Read-only over washer data: this module calls
``washer_resolution_decisions_store.list_decisions()`` (a pure
accessor) and nothing else in ``backend.library`` -- it never calls
``append_decision``/``record_decision``, never touches
``washer_resolution_ledger.json``, and never mutates any washer
population data. Safe to run any number of times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.library.washer_resolution_decisions import WasherResolutionDecision
from backend.library.washer_resolution_decisions_store import list_decisions

from ..store import GovernanceEventStore
from .washer_resolution_sync import SyncOutcome, SyncResult, sync_washer_decision

#: Every counter this module guarantees to populate, always present
#: (zero-initialized) even when a category has no members -- mirrors
#: ``washer_resolution.count_by_status``'s "every member present"
#: convention.
_COUNTER_NAMES = (
    "scanned",
    "eligible",
    "synchronized",
    "already_synchronized",
    "would_synchronize",
    "not_representable",
    "skipped_open",
    "failed",
    "governance_store_unconfigured",
)

#: Outcomes that count as "eligible" -- i.e. passed the
#: open/under_review filter and were actually evaluated against the
#: governance store (or would have been, absent dry_run/unconfigured
#: store). Documented, informational, deliberately overlapping with
#: the mutually-exclusive terminal-outcome counters below (ADR-0015,
#: "Reconciliation Counters"): every scanned record has exactly one
#: terminal outcome among {synchronized, already_synchronized,
#: would_synchronize, not_representable, skipped_open, failed,
#: governance_store_unconfigured}; ``eligible`` is the sum of every
#: terminal outcome *except* ``not_representable``/``skipped_open``.
_ELIGIBLE_OUTCOMES = frozenset(
    {
        SyncOutcome.SYNCHRONIZED,
        SyncOutcome.ALREADY_SYNCHRONIZED,
        SyncOutcome.WOULD_SYNCHRONIZE,
        SyncOutcome.FAILED,
        SyncOutcome.GOVERNANCE_STORE_UNCONFIGURED,
    }
)

_OUTCOME_TO_COUNTER = {
    SyncOutcome.SYNCHRONIZED: "synchronized",
    SyncOutcome.ALREADY_SYNCHRONIZED: "already_synchronized",
    SyncOutcome.WOULD_SYNCHRONIZE: "would_synchronize",
    SyncOutcome.NOT_REPRESENTABLE: "not_representable",
    SyncOutcome.SKIPPED_OPEN: "skipped_open",
    SyncOutcome.FAILED: "failed",
    SyncOutcome.GOVERNANCE_STORE_UNCONFIGURED: "governance_store_unconfigured",
}


@dataclass(frozen=True)
class ReconciliationReport:
    """Deterministic result of one reconciliation run.

    Counter invariant (ADR-0015, tested explicitly):
    ``scanned == synchronized + already_synchronized +
    would_synchronize + not_representable + skipped_open + failed +
    governance_store_unconfigured``. ``eligible`` is documented,
    informational, and intentionally *not* part of that sum (see
    :data:`_ELIGIBLE_OUTCOMES`).
    """

    counters: Dict[str, int]
    records: List[SyncResult] = field(default_factory=list)
    dry_run: bool = True

    def terminal_outcome_sum(self) -> int:
        """The sum the ``scanned`` invariant must equal -- exposed as
        a method (not re-derived ad hoc by callers/tests) so the
        invariant has exactly one implementation."""
        return (
            self.counters["synchronized"]
            + self.counters["already_synchronized"]
            + self.counters["would_synchronize"]
            + self.counters["not_representable"]
            + self.counters["skipped_open"]
            + self.counters["failed"]
            + self.counters["governance_store_unconfigured"]
        )


def reconcile(
    store: Optional[GovernanceEventStore],
    *,
    decisions: Optional[List[WasherResolutionDecision]] = None,
    dry_run: bool = True,
) -> ReconciliationReport:
    """Run one reconciliation pass.

    ``store=None`` means "governance not configured" -- every
    eligible decision is classified
    :data:`~backend.governance.adapters.washer_resolution_sync.
    SyncOutcome.GOVERNANCE_STORE_UNCONFIGURED`, never as a failure,
    and ``not_representable``/``skipped_open`` classification for
    non-eligible decisions is still reported accurately (ADR-0015,
    "Store-Unconfigured Behaviour") -- this function never skips
    reading/classifying washer decisions just because the store is
    unconfigured.

    ``decisions`` is normally left as ``None`` (the real,
    read-only ``list_decisions()`` accessor is used); tests may pass
    a fixed list for determinism. Never mutated.

    ``dry_run=True`` (the safe default) never calls a governance
    write command -- see
    ``washer_resolution_sync.sync_washer_decision``'s own
    ``dry_run`` contract. The governance event store and the washer
    decision store are never written to in dry-run mode.
    """
    counters: Dict[str, int] = {name: 0 for name in _COUNTER_NAMES}
    records: List[SyncResult] = []

    source_decisions = list_decisions() if decisions is None else decisions

    for decision in source_decisions:
        counters["scanned"] += 1
        result = sync_washer_decision(decision, store, dry_run=dry_run)
        records.append(result)

        counter_name = _OUTCOME_TO_COUNTER[result.outcome]
        counters[counter_name] += 1
        if result.outcome in _ELIGIBLE_OUTCOMES:
            counters["eligible"] += 1

    return ReconciliationReport(counters=counters, records=records, dry_run=dry_run)


__all__ = ["ReconciliationReport", "reconcile"]
