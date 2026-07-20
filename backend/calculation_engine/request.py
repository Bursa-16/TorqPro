"""TorqPro Calculation Engine - calculation request contract.

Prerequisite scaffolding. ``CalculationRequest`` is the single input
contract every calculation provider accepts. It carries no
engineering semantics of its own: ``inputs`` is an opaque mapping
whose expected keys are defined by each individual provider (see
``backend.calculation_engine.providers.vdi2230_provider`` for the
first concrete example).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class CalculationRequest:
    """Immutable input contract for any calculation provider.

    Attributes:
        standard: Identifier of the target standard/provider (e.g.
            ``"VDI2230"``).
        inputs: Provider-specific input values. Structure and
            required keys are defined by the provider, not here.
        limit_mpa: Optional engineering limit for a final result
            evaluation. Providers must treat this as optional: when
            absent, result evaluation is skipped (not treated as an
            error).
        fail_threshold: Optional utilization threshold above which a
            result evaluation is a ``fail``. Only meaningful when
            ``limit_mpa`` is also supplied.
        warn_threshold: Optional utilization threshold above which a
            result evaluation is a ``warn``.
        metadata: Optional free-form caller metadata (request id,
            trace id, etc.), not interpreted by the engine itself.
    """

    standard: str
    inputs: Mapping[str, Any]
    limit_mpa: Optional[float] = None
    fail_threshold: Optional[float] = None
    warn_threshold: Optional[float] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = ["CalculationRequest"]
