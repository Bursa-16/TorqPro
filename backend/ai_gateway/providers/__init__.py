"""TorqPro AI Gateway - provider abstraction package (Faz v3.0.0-alpha.5).

Per ADR-0020 ("Provider abstraction, persistent audit ve
explainability -- v3.0.0-alpha.5 kapsami"), this package holds
*selectable, registry-eligible* ``backend.ai_gateway.llm_client.
AIModelClient`` implementations and the registry that looks them up by
name.

Deliberately not a new, competing abstraction: every provider here
still implements ``AIModelClient`` (``backend.ai_gateway.llm_client``)
verbatim -- this package adds *selection* (a name -> instance registry)
and two small, additive capability hooks already defined directly on
``AIModelClient`` itself (``is_available()``, ``model_identifier``),
not a second interface. This mirrors the same naming discipline
``llm_client.py``'s own module docstring already establishes:
``AIModelClient`` is never aliased to, or merged with,
``backend.calculation_engine.provider.Provider`` -- nothing in this
package introduces a "Provider" class either.

No concrete, network-calling client (OpenAI/Claude/Ollama) is defined
in this phase -- ADR-0020 keeps that explicitly deferred, same as
``llm_client.py``'s own pre-existing deferral. ``deterministic.py``'s
``DeterministicModelClient`` is the only concrete provider registered
by :func:`registry.build_default_registry` in this phase.
"""

from __future__ import annotations

from backend.ai_gateway.providers.deterministic import DeterministicModelClient
from backend.ai_gateway.providers.registry import (
    ProviderInfo,
    ProviderRegistry,
    build_default_registry,
)

__all__ = [
    "DeterministicModelClient",
    "ProviderInfo",
    "ProviderRegistry",
    "build_default_registry",
]
