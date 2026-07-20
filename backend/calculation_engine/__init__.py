"""TorqPro Calculation Engine (prerequisite scaffolding).

Minimal, provider-agnostic contract layer: ``CalculationRequest``,
``CalculationResponse`` / ``CalculationResult``, the abstract
``Provider`` base class, the shared exception hierarchy, and an
empty ``formula_registry``. No engineering formula or calculation
logic lives in this package -- see each concrete provider module
(e.g. ``backend.calculation_engine.providers.vdi2230_provider``) for
that.

Built as an explicit, separately-committed prerequisite immediately
ahead of Phase 2.3 (VDI 2230 provider wiring): earlier phase
docstrings and ``tests/test_vdi2230_core.py`` already referenced
this package by name, but it did not previously exist anywhere in
this repository's history.

Technical debt: FIAT and ISO calculation providers are **not**
implemented here, or anywhere else in this codebase. Only their
standard *metadata* exists (``backend/standards/fiat.py``,
``backend/standards/iso.py``, Phase 1.2, metadata-only). No
``providers.fiat_provider`` / ``providers.iso_provider`` module is
registered in ``backend.calculation_engine.providers``.
"""

from __future__ import annotations

from .exceptions import (
    CalculationEngineError,
    CalculationInputError,
    CalculationNotImplementedError,
    ProviderNotFoundError,
)
from .formula_registry import (
    FormulaRegistryEntry,
    all_formulas,
    get_formula,
    register_formula,
)
from .provider import Provider
from .request import CalculationRequest
from .response import CalculationResponse, CalculationResult

__all__ = [
    "CalculationEngineError",
    "CalculationInputError",
    "CalculationNotImplementedError",
    "ProviderNotFoundError",
    "CalculationRequest",
    "CalculationResult",
    "CalculationResponse",
    "Provider",
    "FormulaRegistryEntry",
    "register_formula",
    "get_formula",
    "all_formulas",
]
