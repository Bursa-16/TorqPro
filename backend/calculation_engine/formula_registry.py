"""TorqPro Calculation Engine - formula registry.

Prerequisite scaffolding. Defines the generic, engine-level record
shape for a traceable formula -- matching the fields already
independently duplicated by
``backend.vdi2230_core.trace.FormulaTrace`` (see that module's
docstring). This module intentionally starts **empty**: registering
any concrete formula here is engineering-formula work and is out of
scope for this prerequisite layer. A provider may register its own
formulas here, or keep its own independent trace catalog (as
``backend.vdi2230_core`` does, by design, to preserve its
zero-dependency isolation) -- ``VDI2230Provider`` takes the latter
approach and registers nothing here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .exceptions import CalculationInputError


@dataclass(frozen=True)
class FormulaRegistryEntry:
    """Immutable, engine-level traceability record for a single
    formula, shared across providers."""

    formula_id: str
    symbol: str
    unit: str
    source: str
    classification: str
    validation_status: str


_REGISTRY: Dict[str, FormulaRegistryEntry] = {}


def register_formula(entry: FormulaRegistryEntry) -> None:
    """Register ``entry`` under its ``formula_id``.

    Raises ``CalculationInputError`` if ``formula_id`` is already
    registered, to keep registration accidental-overwrite-free.
    """
    if entry.formula_id in _REGISTRY:
        raise CalculationInputError(
            f"formula_id already registered: {entry.formula_id!r}"
        )
    _REGISTRY[entry.formula_id] = entry


def get_formula(formula_id: str) -> FormulaRegistryEntry:
    """Return the registered entry for ``formula_id``.

    Raises ``KeyError`` if nothing is registered under that id.
    """
    return _REGISTRY[formula_id]


def all_formulas() -> Dict[str, FormulaRegistryEntry]:
    """Return a shallow copy of the full registry."""
    return dict(_REGISTRY)


__all__ = [
    "FormulaRegistryEntry",
    "register_formula",
    "get_formula",
    "all_formulas",
]
