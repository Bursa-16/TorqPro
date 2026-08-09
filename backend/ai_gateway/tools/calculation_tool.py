"""TorqPro AI Gateway - deterministic calculation tool adaptor.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 5
("Deterministic calculation engine ile AI arasindaki sinir") and the
prompt's explicit architectural rule: **AI never produces an
authoritative torque/preload numeric result; the existing
deterministic TorqPro calculation engine always does.**

This module contains exactly one function, and that function contains
no engineering logic whatsoever: it forwards a ``CalculationRequest``
to an existing ``backend.calculation_engine.provider.Provider`` and
returns whatever ``CalculationResponse`` that provider computes,
unmodified. It never inspects, rounds, recomputes or overrides a
``CalculationResult.value``.

Exception policy (ADR-0017 Karar 9, case 3): any exception the
provider raises -- ``CalculationInputError``,
``CalculationNotImplementedError``, or a wired core's own domain
exception (e.g. ``VdiCalculationDomainError``) -- propagates
unchanged. This function contains no ``try``/``except`` of its own.
An AI-generated answer is never produced to paper over a calculation
failure; the failure is surfaced as-is to
``backend.ai_gateway.orchestrator``, exactly as
``backend.calculation_engine.providers.vdi2230_provider`` itself never
catches and re-wraps its wired core's exceptions.
"""

from __future__ import annotations

from backend.calculation_engine.provider import Provider
from backend.calculation_engine.request import CalculationRequest
from backend.calculation_engine.response import CalculationResponse


def run_calculation(provider: Provider, request: CalculationRequest) -> CalculationResponse:
    """Call ``provider.calculate(request)`` and return its result
    unmodified.

    This is the *only* path by which any numeric engineering value
    can enter the AI layer's data flow. Nothing else in
    ``backend.ai_gateway`` is permitted to construct a
    ``CalculationResponse``/``CalculationResult`` itself.
    """
    return provider.calculate(request)


__all__ = ["run_calculation"]
