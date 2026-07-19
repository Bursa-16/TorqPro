"""TorqPro Calculation Engine - concrete provider implementations.

Faz 2.3: ``VDI2230Provider`` is the first concrete provider, wiring
``backend.vdi2230_core`` (Phase 2.2) into the
``backend.calculation_engine`` contract layer (prerequisite,
established in the immediately preceding commit).

No FIAT or ISO calculation provider is implemented or registered
here -- see the package-level docstring in
``backend.calculation_engine`` for the technical-debt note.
"""

from __future__ import annotations

from .vdi2230_provider import PROVIDER_VERSION, VDI2230Provider

__all__ = ["VDI2230Provider", "PROVIDER_VERSION"]
