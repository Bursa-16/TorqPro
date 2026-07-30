"""TorqPro Engineering Governance - Faz 2.8.11 Stage 5 compatibility
adapters.

Read-only, additive projections from an existing mechanism's own
lifecycle data onto the canonical governance vocabulary
(``docs/adr/ADR-0014-engineering-governance-architecture.md``). No
adapter here writes to any existing ledger/table, writes to the
governance event store, or exposes a mutation/transition/persistence
method -- see each adapter module's own docstring for its specific
scope and the reasoning behind which mechanisms are covered in this
stage.

Currently implemented:
  - :mod:`backend.governance.adapters.washer_resolution`

Deliberately not implemented in Stage 5 (see
``docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md`` Sec. 5 for the
full reasoning): Production Validation, the legacy calculation-
revision workflow, and the joint revision lifecycle all require a
live database connection to read anything, which this stage's
"read-only, additive, no new dependency cycle" adapter contract does
not yet have a settled pattern for.
"""

from __future__ import annotations

from .washer_resolution import (
    AdapterSourceRecordNotFoundError,
    CompatibilityProjection,
    MappingQuality,
    project_washer_resolution,
)

__all__ = [
    "AdapterSourceRecordNotFoundError",
    "CompatibilityProjection",
    "MappingQuality",
    "project_washer_resolution",
]
