"""TorqPro Engineering Governance - Faz 2.8.12 Stage 2 aggregate
ownership registry.

Purely additive, closed, string-only registry: which
``aggregate_type`` values are "externally owned" by another existing
mechanism's own decision workflow, and therefore must not be written
through the generic governance HTTP write endpoints
(``backend.governance.api``'s nine ``POST`` routes).

This module deliberately never imports ``backend.library`` or any
other existing mechanism -- it only holds string constants and a pure
predicate over them, matching ``backend.governance.enums``'s existing
"closed vocabulary" pattern. This keeps the governance package's
Stage 4/2.8.11 compatibility contract intact (no governance module
imports an existing mechanism except the two Stage 5/2.8.12-approved
adapter files -- see ``backend/governance/adapters/__init__.py``).

Scope (Faz 2.8.12 Stage 2, ADR-0015): only ``"washer_resolution"`` is
registered today, matching
``backend.governance.adapters.washer_resolution.SOURCE_SYSTEM`` and
the new ``backend.governance.adapters.washer_resolution_sync`` write
path. Adding a future mechanism (e.g. Production Validation) to this
registry is an explicit, separate decision for its own phase -- not
implied by this module's structure.

This registry affects **only** the generic governance HTTP write
endpoints (enforced centrally in
``backend.governance.api._run_command``). It never affects:

  - governance read endpoints (history/status) -- an externally-owned
    aggregate's governance events remain fully visible;
  - internal, in-process calls into
    ``backend.governance.service`` (e.g. from
    ``backend.governance.adapters.washer_resolution_sync``) -- those
    are the legitimate, approved way an externally-owned aggregate's
    events are written.

No existing ``aggregate_type`` used by any current test or caller is
affected: ``"washer_resolution"`` was not previously used as a
governance ``aggregate_type`` value anywhere in the test suite or any
shipped caller (verified by repository search before this module was
written).
"""

from __future__ import annotations

#: Closed set of aggregate_type values owned by an existing
#: mechanism's own decision workflow. Values here may only receive
#: governance events via that mechanism's own synchronization
#: adapter, never via the generic governance HTTP write endpoints.
RESTRICTED_AGGREGATE_TYPES = frozenset({"washer_resolution"})


def is_externally_owned(aggregate_type: str) -> bool:
    """``True`` if ``aggregate_type`` is registered in
    :data:`RESTRICTED_AGGREGATE_TYPES` -- i.e. governance events for
    it may only be written by that mechanism's own synchronization
    adapter, never through the generic governance HTTP write
    endpoints. Any other value (including one this module does not
    recognize) is ``False`` -- this predicate is additive-only and
    never restricts an aggregate_type it does not explicitly list."""
    return aggregate_type in RESTRICTED_AGGREGATE_TYPES


__all__ = ["RESTRICTED_AGGREGATE_TYPES", "is_externally_owned"]
