"""TorqPro AI Gateway - tools package.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 5
("Deterministic calculation engine ile AI arasindaki sinir").

Every module under ``backend.ai_gateway.tools`` is a thin, purely
call-forwarding adaptor around an existing deterministic engineering
entry point (``backend.calculation_engine.provider.Provider`` and,
transitively, ``backend.engineering_core``/``backend.vdi2230_core``).
No module in this package contains, computes or approximates any
engineering formula, coefficient or tolerance value -- see
``calculation_tool.py``'s module docstring for the exact contract.
"""

from __future__ import annotations

__all__: list[str] = []
