"""TorqPro AI Gateway.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), implementing ADR-0017
("TorqPro AI Layer Architecture", Status: Accepted).

**Architectural rule (ADR-0017, restated here for every reader of this
package):** AI never produces an authoritative torque/preload or any
other numeric engineering result. Every numeric engineering result
this package's data ever carries is produced exclusively by the
existing deterministic TorqPro calculation engine
(``backend.calculation_engine`` / ``backend.engineering_core`` /
``backend.vdi2230_core``) and is only ever forwarded, never computed
or altered, by ``backend.ai_gateway.tools.calculation_tool``. This
package is the interpretation / retrieval / explanation /
recommendation / orchestration layer only.

**Dependency direction (ADR-0017 Karar 2):** this package, and only
this package, is permitted to import
``backend.engineering_core``/``backend.vdi2230_core``/
``backend.calculation_engine``/``backend.question_bank`` (read-only,
via their existing public service functions). None of those packages
-- nor ``backend.governance``, ``backend.production_validation``,
``backend.joints``, ``backend.library``, ``backend.standards``, nor
``backend.app`` itself -- may import anything from
``backend.ai_gateway``. This direction is enforced by
``tests/ai/test_dependency_direction.py``. If this package were
deleted entirely, every other TorqPro module and every existing
``/api/*`` endpoint would continue to function exactly as before,
because nothing outside this package depends on it (see
ADR-0017 Karar 10).

**Scope of this phase (v3.0.0-alpha.1):** this package has no HTTP
route yet (``backend/api/ai/routes`` is a later, separately-approved
phase per ADR-0017 Karar 12/13), no real ``AIModelClient``
implementation (only the abstract interface plus in-process test
doubles), and no SQLite persistence for its own audit tables (only an
in-memory ``AuditSink``). ``backend/app.py`` is not modified by this
phase.

No public re-exports are declared at package level: import from the
specific submodule you need (``backend.ai_gateway.orchestrator``,
``backend.ai_gateway.permission``, etc.) -- this keeps each
submodule's own docstring the authoritative description of its
contract, rather than duplicating it here.
"""

from __future__ import annotations

__all__: list[str] = []
