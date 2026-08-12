"""TorqPro AI Gateway - Engineering Reasoning Engine.

Faz v3.0.0-beta.2 (Engineering Reasoning Engine).

This subpackage lives *inside* ``backend.ai_gateway`` -- not as a new
top-level package, and not inside ``backend.torque_recommendation`` --
deliberately, for two reasons proven out during Stage 0 discovery:

1. ``backend.ai_gateway`` is already the one package in this
   repository permitted to import the deterministic engineering
   packages (``backend.torque_recommendation``,
   ``backend.calculation_engine``, ...) -- see this package's own
   ``__init__.py`` docstring. Placing reasoning here means it can
   consume ``backend.torque_recommendation``'s Beta.1 output without
   requiring any change to ``tests/ai/test_dependency_direction.py``'s
   ``GUARDED_DIRS``/``SANCTIONED_ENTRY_POINTS`` lists: the guard only
   restricts *guarded* packages from importing ``backend.ai_gateway``,
   and ``backend.torque_recommendation`` is not, and remains not, one
   of those guarded packages.
2. ``backend/api/routes/ai_gateway.py`` is already the sole sanctioned
   HTTP entry point permitted to import ``backend.ai_gateway``. A new
   ``POST /api/ai/engineering-reasoning`` endpoint added to that same
   file therefore does not introduce a second consumer either -- no
   guard-test edit, no new sanctioned entry point, no parallel route
   module.

Engineering Reasoning is structurally separate from AI-generated
explanation throughout this subpackage (see ``engine.py`` and
``wording.py`` module docstrings): ``engine.py`` never imports an
``AIModelClient`` implementation and never calls ``.complete()``;
``wording.py`` is the only module in this subpackage that does, and it
never constructs, edits, or rounds a numeric engineering value --
mirroring ``backend.ai_gateway.composer``'s own rule 2 verbatim.

This subpackage never re-runs
``backend.torque_recommendation.engine.recommend_torque`` -- it only
reads an already-persisted Beta.1 result via
``backend.torque_recommendation.audit.get_recommendation_audit``.
"""

from __future__ import annotations

__all__: list = []
