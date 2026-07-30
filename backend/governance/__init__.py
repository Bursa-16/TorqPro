"""TorqPro Engineering Governance - Faz 2.8.11 Stage 2.

Shared governance contracts and typed domain models implementing
``docs/adr/ADR-0014-engineering-governance-architecture.md``'s
canonical model: three independent lifecycle groups (review,
publication/revision, resolution), each with its own status
vocabulary, closed transition table, and typed decision model.

Compatibility strategy (ADR-0014, "Compatibility strategy" and Stage
2 scope, restated here as this package's own contract):

  - This package is purely additive. No existing table, JSON ledger,
    API endpoint, enum, or transition graph belonging to any of the
    four pre-existing mechanisms is imported, modified, renamed, or
    depended upon:
      * ``backend.production_validation`` (Production Validation
        workflow, Faz 2.5A)
      * ``backend.app`` (legacy ``calculation_revisions`` review/
        approve/reject workflow)
      * ``backend.joints`` (joint revision lifecycle, ADR-0003)
      * ``backend.library.washer_resolution`` /
        ``backend.library.washer_resolution_decisions`` (Faz 2.8.9
        washer resolution decision workflow, ADR-0013)
  - Symmetrically, none of those four mechanisms imports or depends
    on this package. No existing runtime behavior changes as a
    result of this package's addition -- it is inert until a future
    stage explicitly wires something to it.
  - This package has no persistence layer (no JSON ledger, no SQLite
    table) and defines no service function or API route. It is
    contracts and models only. Stage 3 (append-only governance event
    store and service layer) is where a decision produced by these
    models would actually be written down and retrieved; Stage 4
    would add additive API routes; neither exists yet.

Submodules:

  - :mod:`backend.governance.enums` -- the three canonical status
    enums and their closed transition tables.
  - :mod:`backend.governance.exceptions` -- domain errors
    (:class:`~backend.governance.exceptions.InvalidTransitionError`,
    :class:`~backend.governance.exceptions.MissingRequiredFieldError`).
  - :mod:`backend.governance.transitions` -- generic, table-agnostic
    transition-checking mechanics shared by all three lifecycle
    groups.
  - :mod:`backend.governance.models` -- the ``*Decision`` Pydantic
    models (one per lifecycle group), the canonical required-field
    tables, and the ``validate_*_decision`` entry points that tie a
    lifecycle's transition table and required-field table together.
"""

from __future__ import annotations

from .enums import (
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
from .exceptions import (
    GovernanceError,
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

__all__ = [
    # enums
    "ReviewStatus",
    "PublicationStatus",
    "ResolutionStatus",
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
    # models
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
]
