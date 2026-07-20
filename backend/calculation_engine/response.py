"""TorqPro Calculation Engine - calculation response contract.

Prerequisite scaffolding. Defines the shared output contract every
calculation provider returns: an ordered list of individually
traceable ``CalculationResult`` entries, plus response-level formula
traces, warnings and a validation outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class CalculationResult:
    """A single traceable calculated quantity.

    Attributes:
        value: The computed numeric value, or ``None`` when the
            quantity could not be evaluated (e.g. result evaluation
            skipped because no limit was supplied).
        unit: Unit label for ``value`` (SI convention; see the wired
            calculation core's own unit module).
        formula_id: Identifier of the formula that produced
            ``value``, as defined by the wired calculation core.
        classification: Formula classification as defined by the
            wired calculation core (e.g. ``"QUICK"``,
            ``"CORE_ARCHITECTURE"``, ``"MANDATORY_CORRECTED_MODEL"``).
        validation_status: Formula validation lifecycle status as
            defined by the wired calculation core (e.g.
            ``"PROVISIONAL"``, ``"APPROVED"``).
    """

    value: Optional[float]
    unit: str
    formula_id: str
    classification: str
    validation_status: str


@dataclass(frozen=True)
class CalculationResponse:
    """Immutable output contract returned by any calculation
    provider.

    Attributes:
        standard: Identifier of the standard/provider that produced
            this response (matches the originating request).
        provider_version: Version string of the provider
            implementation that produced this response.
        inputs: The original request inputs, echoed back for
            traceability.
        results: Ordered list of ``CalculationResult`` entries.
        formula_traces: The full formula-trace records used to
            produce ``results`` (provider-specific type; for
            ``VDI2230Provider`` these are
            ``backend.vdi2230_core.FormulaTrace`` instances).
        warnings: Human-readable warnings surfaced from the
            calculation (e.g. provisional-formula notices, safety
            warn/fail outcomes). Empty when there is nothing to
            flag.
        validation: Structured outcome of the final result
            evaluation (status/message/utilization), or an empty
            mapping when no evaluation was requested or possible.
    """

    standard: str
    provider_version: str
    inputs: Mapping[str, Any]
    results: List[CalculationResult]
    formula_traces: Sequence[Any]
    warnings: List[str] = field(default_factory=list)
    validation: Mapping[str, Any] = field(default_factory=dict)


__all__ = ["CalculationResult", "CalculationResponse"]
