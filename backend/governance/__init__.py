"""TorqPro Engineering Governance - Faz 2.8.11 Stage 2 + Stage 3.

Shared governance contracts, typed domain models, an append-only
event store, and a service layer implementing
``docs/adr/ADR-0014-engineering-governance-architecture.md``'s
canonical model: three independent lifecycle groups (review,
publication/revision, resolution), each with its own status
vocabulary, closed transition table, typed decision model, and
event-sourced service commands.

Compatibility strategy (ADR-0014, "Compatibility strategy" and Stage
2/3 scope, restated here as this package's own contract):

  - This package is purely additive. No existing table, JSON ledger,
    API endpoint, enum, or transition graph belonging to any of the
    four pre-existing mechanisms is imported, modified, renamed, or
    depended upon:
      * ``backend.production_validation`` (Production Validation
        workflow, Faz 2.5A)
      * ``backend.app`` (legacy ``calculation_revisions`` review/
        approve/reject workflow, and the generic ``audit_log`` table)
      * ``backend.joints`` (joint revision lifecycle, ADR-0003)
      * ``backend.library.washer_resolution`` /
        ``backend.library.washer_resolution_decisions`` /
        ``backend.library.washer_resolution_decisions_store`` (Faz
        2.8.9 washer resolution decision workflow, ADR-0013)
  - Symmetrically, none of those four mechanisms imports or depends
    on this package. No existing runtime behavior changes as a
    result of this package's addition -- it is inert until a future
    stage explicitly wires something to it. This is mechanically
    enforced by ``tests/governance/test_compatibility.py``.
  - This package's event store (Stage 3) is a standalone, additive
    persistence layer with a fully caller-controlled storage path --
    there is no default production data file, no wiring into
    ``backend/app.py``, and no API route. It never reads or writes
    ``backend/library/data/washer_resolution_ledger.json`` or
    ``washer_resolution_decisions.json``. Stage 4 (additive API and
    TR/EN governance workspace) is where a route would first be
    added; it does not exist yet.

Submodules:

  - :mod:`backend.governance.enums` -- the three canonical status
    enums, :class:`~backend.governance.enums.LifecycleGroup`, and
    their closed transition tables (Stage 2).
  - :mod:`backend.governance.exceptions` -- domain errors for both
    Stage 2 (transition/field validation) and Stage 3 (store,
    idempotency, aggregate lookup).
  - :mod:`backend.governance.transitions` -- generic, table-agnostic
    transition-checking mechanics shared by all three lifecycle
    groups (Stage 2).
  - :mod:`backend.governance.models` -- the ``*Decision`` Pydantic
    models (one per lifecycle group), the canonical required-field
    tables, and the ``validate_*_decision`` entry points (Stage 2).
  - :mod:`backend.governance.events` -- :class:`~backend.governance.
    events.GovernanceEvent`, the append-only, lifecycle-group-tagged
    event shape persisted by the Stage 3 store (Stage 3).
  - :mod:`backend.governance.store` -- the abstract
    :class:`~backend.governance.store.GovernanceEventStore` contract
    and the deterministic, atomic, file-backed
    :class:`~backend.governance.store.FileGovernanceEventStore`
    implementation (Stage 3).
  - :mod:`backend.governance.service` -- idempotency-first command
    functions (submit/approve/reject review, activate/supersede/
    archive publication, resolve/reject/waive resolution) and read
    accessors (event history, effective status, latest event),
    reusing the Stage 2 validators without duplicating any lifecycle
    rule (Stage 3).
"""

from __future__ import annotations

from .enums import (
    LifecycleGroup,
    PUBLICATION_TERMINAL_STATUSES,
    PUBLICATION_TRANSITIONS,
    PublicationStatus,
    RESOLUTION_TERMINAL_STATUSES,
    RESOLUTION_TRANSITIONS,
    REVIEW_TERMINAL_STATUSES,
    REVIEW_TRANSITIONS,
    ResolutionStatus,
    ReviewStatus,
)
from .events import GovernanceEvent
from .exceptions import (
    GovernanceAggregateNotFoundError,
    GovernanceCorruptionError,
    GovernanceDuplicateDecisionError,
    GovernanceError,
    GovernanceIdempotencyConflictError,
    GovernanceStoreError,
    InvalidTransitionError,
    MissingRequiredFieldError,
)
from .models import (
    PUBLICATION_REQUIRED_FIELDS,
    PublicationDecision,
    RESOLUTION_REQUIRED_FIELDS,
    REVIEW_REQUIRED_FIELDS,
    ResolutionDecision,
    ReviewDecision,
    validate_publication_decision,
    validate_required_fields,
    validate_resolution_decision,
    validate_review_decision,
)
from .service import (
    activate_publication,
    approve_review,
    archive_publication,
    effective_status,
    event_history,
    latest_event,
    reject_resolution,
    reject_review,
    resolve_resolution,
    submit_review,
    supersede_publication,
    waive_resolution,
)
from .store import FileGovernanceEventStore, GovernanceEventStore

__all__ = [
    # enums
    "ReviewStatus",
    "PublicationStatus",
    "ResolutionStatus",
    "LifecycleGroup",
    "REVIEW_TRANSITIONS",
    "REVIEW_TERMINAL_STATUSES",
    "PUBLICATION_TRANSITIONS",
    "PUBLICATION_TERMINAL_STATUSES",
    "RESOLUTION_TRANSITIONS",
    "RESOLUTION_TERMINAL_STATUSES",
    # exceptions
    "GovernanceError",
    "InvalidTransitionError",
    "MissingRequiredFieldError",
    "GovernanceStoreError",
    "GovernanceCorruptionError",
    "GovernanceIdempotencyConflictError",
    "GovernanceDuplicateDecisionError",
    "GovernanceAggregateNotFoundError",
    # models (Stage 2)
    "ReviewDecision",
    "REVIEW_REQUIRED_FIELDS",
    "validate_review_decision",
    "PublicationDecision",
    "PUBLICATION_REQUIRED_FIELDS",
    "validate_publication_decision",
    "ResolutionDecision",
    "RESOLUTION_REQUIRED_FIELDS",
    "validate_resolution_decision",
    "validate_required_fields",
    # events + store (Stage 3)
    "GovernanceEvent",
    "GovernanceEventStore",
    "FileGovernanceEventStore",
    # service (Stage 3)
    "event_history",
    "latest_event",
    "effective_status",
    "submit_review",
    "approve_review",
    "reject_review",
    "activate_publication",
    "supersede_publication",
    "archive_publication",
    "resolve_resolution",
    "reject_resolution",
    "waive_resolution",
]
