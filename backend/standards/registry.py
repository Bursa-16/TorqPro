"""TorqPro Standards Engine - standard registry.

Central lookup for standard metadata. Infrastructure only:
no formulas, no calculation logic, no API coupling.
"""

from typing import Dict, List

from .base_standard import BaseStandard

_REGISTRY: Dict[str, BaseStandard] = {}


def register(standard: BaseStandard) -> BaseStandard:
    """Register a standard. Re-registering the same key overwrites it."""
    if not isinstance(standard, BaseStandard):
        raise TypeError("register() expects a BaseStandard instance")
    _REGISTRY[standard.key] = standard
    return standard


def get_standard(name: str) -> BaseStandard:
    """Return a registered standard by name (case-insensitive)."""
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise KeyError(f"Standard not registered: {name}")
    return _REGISTRY[key]


def list_standards() -> List[BaseStandard]:
    """Return all registered standards, sorted by name."""
    return sorted(_REGISTRY.values(), key=lambda s: s.key)


def supported_methods(name: str) -> List[str]:
    """Return the calculation methods a registered standard supports."""
    return list(get_standard(name).supported_calculations)
