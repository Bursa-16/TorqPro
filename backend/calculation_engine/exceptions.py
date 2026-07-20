"""TorqPro Calculation Engine - shared exception hierarchy.

Prerequisite scaffolding, established immediately ahead of Phase 2.3
(VDI 2230 provider wiring). Earlier phase docstrings and
``tests/test_vdi2230_core.py`` already referenced
``backend.calculation_engine`` as if it existed; it did not, on any
branch, anywhere in this repository's history. This module defines
only the exception types a calculation provider raises for its own
request-validation and orchestration failures. It contains no
engineering formulas or calculation logic.

Distinct from a wired calculation core's own exceptions (e.g.
``backend.vdi2230_core.exceptions``): a provider re-raises its
core's exceptions unchanged for domain/numeric failures detected
*inside* the core (NaN, infinite, negative, empty segment list,
etc.). It raises the exceptions defined here only for failures
detected at the provider/orchestration boundary itself -- a required
request field is absent, or the request asks for a feature the wired
core does not implement.
"""

from __future__ import annotations


class CalculationEngineError(Exception):
    """Base class for all backend.calculation_engine errors."""


class CalculationInputError(CalculationEngineError):
    """A required field is missing from a ``CalculationRequest``, or
    the request is malformed in a way detected before any
    calculation core is invoked."""


class CalculationNotImplementedError(CalculationEngineError):
    """The request asks for a calculation method, geometry or
    feature that the wired calculation core does not (yet)
    implement."""


class ProviderNotFoundError(CalculationEngineError):
    """No provider is registered for the requested standard."""


__all__ = [
    "CalculationEngineError",
    "CalculationInputError",
    "CalculationNotImplementedError",
    "ProviderNotFoundError",
]
