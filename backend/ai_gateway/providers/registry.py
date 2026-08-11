"""TorqPro AI Gateway - provider registry.

Faz v3.0.0-alpha.5 (Provider Abstraction), per ADR-0020.

A ``ProviderRegistry`` is a simple, explicit name -> ``AIModelClient``
lookup. Selection is always by an exact, caller-supplied name string
(never inferred, never a fallback chain) -- ADR-0020's "provider
seçimi açık ve deterministic olsun" requirement. Looking up a name
that was never registered raises
``backend.ai_gateway.exceptions.ProviderNotFoundError`` -- it is never
silently substituted with a different provider or a fabricated
response.

This module never imports ``fastapi`` or ``backend.app``, matching
every other ``backend.ai_gateway`` module's framework-agnostic
discipline (see e.g. ``backend.ai_gateway.orchestrator``'s own module
docstring).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from backend.ai_gateway.exceptions import ProviderNotFoundError
from backend.ai_gateway.llm_client import AIModelClient
from backend.ai_gateway.providers.deterministic import DeterministicModelClient


@dataclass(frozen=True)
class ProviderInfo:
    """Read-only, HTTP/serialization-friendly summary of one
    registered provider (ADR-0020, HTTP exposure section).

    Deliberately holds only display/selection metadata -- never a
    reference to the live ``AIModelClient`` instance itself, so a
    caller cannot reach into the registry and start calling
    ``complete()`` through this object.
    """

    name: str
    model_identifier: str
    available: bool


class ProviderRegistry:
    """Explicit name -> ``AIModelClient`` registry.

    Not framework-agnostic-adjacent magic: :meth:`register` and
    :meth:`get` are the only two ways to add or retrieve a provider,
    and both operate on ``AIModelClient`` instances only -- no other
    provider abstraction is introduced (see package docstring).
    """

    def __init__(self) -> None:
        self._providers: Dict[str, AIModelClient] = {}

    def register(self, client: AIModelClient) -> None:
        """Register ``client`` under its own ``client.name``.

        Registering a second client under an already-used name
        replaces the first -- deliberately simple (last registration
        wins), matching this phase's single-caller, single-process
        usage (``build_default_registry`` below is the only caller in
        this phase); no concurrent-registration scenario exists yet
        for this to need to guard against.
        """
        self._providers[client.name] = client

    def get(self, name: str) -> AIModelClient:
        """Return the registered ``AIModelClient`` for ``name``.

        Raises :class:`~backend.ai_gateway.exceptions.
        ProviderNotFoundError` -- never ``KeyError``, never a silently
        substituted default -- when ``name`` was never registered
        (ADR-0020's "bilinmeyen provider güvenli şekilde hata versin"
        requirement).
        """
        try:
            return self._providers[name]
        except KeyError:
            raise ProviderNotFoundError(f"unknown AI provider '{name}'") from None

    def list_providers(self) -> Tuple[ProviderInfo, ...]:
        """Read-only snapshot of every registered provider's metadata,
        sorted by name for deterministic ordering (matters for the
        ``GET /api/ai/providers`` HTTP response, which must not vary
        run-to-run for the same registered set)."""
        return tuple(
            ProviderInfo(
                name=client.name,
                model_identifier=client.model_identifier,
                available=client.is_available(),
            )
            for client in sorted(self._providers.values(), key=lambda c: c.name)
        )


def build_default_registry() -> ProviderRegistry:
    """Construct the registry TorqPro registers by default in this
    phase: only :class:`~backend.ai_gateway.providers.deterministic.
    DeterministicModelClient`.

    No networked provider (OpenAI/Claude/Ollama) is registered here --
    ADR-0020 explicitly defers those to a later, separately-approved
    phase; this function exists precisely so that later phase only has
    to add one more ``.register(...)`` call here, not change any
    caller of this function.
    """
    registry = ProviderRegistry()
    registry.register(DeterministicModelClient())
    return registry


__all__ = ["ProviderInfo", "ProviderRegistry", "build_default_registry"]
