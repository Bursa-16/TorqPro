"""TorqPro AI Gateway - exception hierarchy.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 9
("hata/fallback davranışı"). This module defines only the exception
types the AI layer raises for failures detected *inside* ai_gateway
itself (permission denial, model-provider unavailability, gateway
misconfiguration).

Deliberately distinct from ``backend.calculation_engine.exceptions``
(``CalculationInputError`` and siblings): ADR-0017 Karar 5 and Karar 9
require that a deterministic-engine failure is *never* caught and
re-wrapped here. Any ``CalculationInputError``/``VdiCalculationDomainError``
raised while a ``backend.ai_gateway.tools`` adaptor calls into
``backend.calculation_engine``/``backend.engineering_core``/
``backend.vdi2230_core`` must propagate unchanged, exactly as it does
between ``calculation_engine`` providers and their wired cores. This
module's hierarchy therefore has no relationship to, and never
subclasses, the calculation-engine exception hierarchy.
"""

from __future__ import annotations


class AIGatewayError(Exception):
    """Base class for all backend.ai_gateway errors.

    Never raised directly -- always one of the subclasses below, or a
    deterministic-engine exception propagated unchanged (see module
    docstring).
    """


class PermissionDeniedError(AIGatewayError):
    """The requesting user context is not permitted to use the AI
    gateway for the attempted action (e.g. inactive user, or an
    attempted write/approval action -- ADR-0017 Karar 1 & Karar 9:
    the AI layer never performs write or approval actions, so any
    caller attempting to route one through the gateway is a
    permission failure, not a supported operation)."""


class ModelUnavailableError(AIGatewayError):
    """The configured ``AIModelClient`` raised an exception or timed
    out while producing a completion (ADR-0017 Karar 9, case 1: model
    provider failure). This is always surfaced explicitly to the
    caller -- it is never swallowed and never substituted with a
    guessed or fabricated answer."""


class AIGatewayConfigurationError(AIGatewayError):
    """The gateway was invoked without a required collaborator (e.g.
    no ``AIModelClient`` configured). Distinct from
    ``ModelUnavailableError``: this is a caller/wiring mistake, not a
    runtime failure of an otherwise-correctly-configured model
    client."""


class ProviderNotFoundError(AIGatewayConfigurationError):
    """Faz v3.0.0-alpha.5 (Provider Abstraction, ADR-0020): a caller
    named an AI provider that is not registered in the active
    ``backend.ai_gateway.providers.registry.ProviderRegistry``.

    Deliberately a subclass of ``AIGatewayConfigurationError`` rather
    than a new, unrelated exception type: an unknown provider name is
    the same *kind* of failure as any other AI-gateway wiring mistake
    (caller/config error, not a runtime provider failure), so it
    reuses that branch of the existing hierarchy instead of growing a
    parallel one. Never raised for a provider that exists but failed
    at runtime -- that remains ``ModelUnavailableError``'s job,
    unchanged.
    """


__all__ = [
    "AIGatewayError",
    "PermissionDeniedError",
    "ModelUnavailableError",
    "AIGatewayConfigurationError",
    "ProviderNotFoundError",
]
