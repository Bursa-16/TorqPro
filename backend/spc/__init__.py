"""TorqPro Statistical Process Control engine (Faz 2.5B).

Faz 2.5B delivers the first real SPC computation: a pure, deterministic
Individuals / Moving Range (I-MR) control chart engine.

This package has no dependency on ``backend.production_validation`` (or
any other domain/persistence module). It consumes plain numeric
sequences and returns immutable, in-memory result objects. Ordering,
persistence, and integration with production-validation data are
deliberately out of scope for this phase and belong to a future
adapter/integration phase.

Explicitly NOT implemented in Faz 2.5B (see docs/phases for the
approved scope):

- production-validation adapter / sequence-number ordering
- persistence of SPC results
- public API exposure
- frontend visualization
- Xbar-R, Xbar-S control charts
- Cp / Cpk / Pp / Ppk / Cmk capability indices
- Nelson rules / Western Electric rules / zone analysis / pattern
  events (including Rule 4 - alternating up/down)
- EWMA, CUSUM
- AI interpretation of SPC results
- configurable moving-range span
- a general-purpose SPC constants registry/framework
"""
from __future__ import annotations
