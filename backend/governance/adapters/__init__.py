"""TorqPro Engineering Governance - compatibility adapters.

This package holds three *different* kinds of module, not one
uniform "read-only adapter" category -- each kind has its own write/
persistence contract, and none of them may be assumed to have another
kind's guarantees:

1. **Read-only source projection adapters** -- project an existing
   mechanism's own lifecycle data onto the canonical governance
   vocabulary (``docs/adr/ADR-0014-engineering-governance-architecture.md``).
   Never write to any existing ledger/table, never write to the
   governance event store, never expose a mutation/transition/
   persistence method.
   - :mod:`backend.governance.adapters.washer_resolution` (Faz 2.8.11
     Stage 5)
   - :mod:`backend.governance.adapters.joint_revision` (Faz 2.8.12
     Stage 4.2) -- projects ``joint_revisions.status`` only; not wired
     to any production API route or frontend page until Faz 2.8.13.

2. **Controlled governance-event synchronization adapters** -- read an
   existing mechanism's own already-authoritative decision record and
   write a *derived* governance event for it. Never write back to the
   source mechanism; the governance event store is the only thing
   they write to, and only for the one externally-owned
   ``aggregate_type`` each is scoped to
   (``docs/adr/ADR-0015-washer-resolution-governance-integration.md``).
   - :mod:`backend.governance.adapters.washer_resolution_sync` (Faz
     2.8.12 Stage 2/3) -- ``sync_washer_decision`` /
     ``sync_washer_decision_and_log``; the live write path wired into
     the washer decide endpoint.

3. **Reconciliation utilities** -- batch-replay every source decision
   through the same synchronization function kind 2 already uses (no
   second, independently written synchronization algorithm), for
   recovery/drift-correction. Read-only with respect to the source
   mechanism; writes only via the same governance-event path as
   kind 2.
   - :mod:`backend.governance.adapters.washer_resolution_reconciliation`
     (Faz 2.8.12 Stage 2) -- invoked only via
     ``tools/run_washer_governance_reconciliation.py`` (explicit CLI,
     dry-run default), never automatically.

See each module's own docstring for its exact scope and reasoning.
This package-level docstring intentionally does **not** claim "no
adapter here writes anywhere" -- that was true only through Faz
2.8.11 Stage 5 and is no longer accurate as of Faz 2.8.12 Stage 2.

Deliberately not implemented (see
``docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md`` Sec. 5 and
``docs/phases/PHASE_2.8.12_COMPLETION_REPORT.md`` Sec. 7 for the full
reasoning): Production Validation and the legacy calculation-revision
workflow (source-side architectural mismatch, NO-GO this phase in
both cases); ``joints.status`` -> ``PublicationStatus`` (the
``superseded`` transition has no live code path in the source
mechanism today).
"""

from __future__ import annotations

from .joint_revision import (
    JointRevisionProjection,
    ProjectionOutcome,
    project_joint_revision,
    project_joint_revisions_bulk,
)
from .washer_resolution import (
    AdapterSourceRecordNotFoundError,
    CompatibilityProjection,
    MappingQuality,
    project_washer_resolution,
)

__all__ = [
    "AdapterSourceRecordNotFoundError",
    "CompatibilityProjection",
    "JointRevisionProjection",
    "MappingQuality",
    "ProjectionOutcome",
    "project_joint_revision",
    "project_joint_revisions_bulk",
    "project_washer_resolution",
]
