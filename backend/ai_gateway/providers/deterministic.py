"""TorqPro AI Gateway - deterministic/offline-safe provider.

Faz v3.0.0-alpha.5 (Provider Abstraction), per ADR-0020.

Distinct from ``backend.ai_gateway.llm_client.FakeModelClient``:
``FakeModelClient`` is a *test-only* double, constructed ad hoc by
individual tests and by ``tests/ai/test_http_route.py``'s FastAPI
``dependency_overrides`` fixture -- it is never registered anywhere.
``DeterministicModelClient`` is this phase's first concrete,
registry-eligible ``AIModelClient``: still makes no network call and
requires no credential or configuration (so it is always
``is_available() -> True``), but it is meant as a real, explicitly
selectable provider (e.g. for an offline/air-gapped deployment, or as
a safe, always-available registry entry alongside future networked
providers), not a throwaway test fixture. The two classes are
deliberately kept separate rather than merged or aliased, so a test
changing ``FakeModelClient``'s behaviour can never silently change
what ``ProviderRegistry`` exposes to production code, and vice versa.

No real OpenAI/Claude/Ollama integration is added in this phase
(ADR-0020 scope limit, mirrors ``backend.ai_gateway.llm_client``'s own
pre-existing deferral) -- this is the only concrete provider this
phase registers.
"""

from __future__ import annotations

from backend.ai_gateway.llm_client import AIModelClient, ModelResponse, PromptContext

#: Fixed, non-fabricated placeholder text (bilingual not required here:
#: this is a deliberately generic, low-stakes placeholder -- unlike
#: backend.ai_gateway.composer's user-facing notices, this text is
#: only ever seen when this provider is explicitly selected, which no
#: HTTP route does by default in this phase).
_DEFAULT_FIXED_TEXT = (
    "TorqPro AI (deterministic provider): bu yanit herhangi bir dis ag "
    "cagrisi yapilmadan uretilen sabit bir metindir."
)


class DeterministicModelClient(AIModelClient):
    """Concrete, registry-eligible, offline-safe ``AIModelClient``.

    Always available (:meth:`is_available` returns ``True``
    unconditionally) and always returns the same configured text
    regardless of ``prompt_context`` -- deterministic by construction,
    matching this class's name and ADR-0020's "provider selection must
    be explicit and deterministic" requirement.
    """

    name = "deterministic"

    def __init__(self, fixed_text: str = _DEFAULT_FIXED_TEXT) -> None:
        self._fixed_text = fixed_text
        self.calls: list[PromptContext] = []

    def is_available(self) -> bool:
        return True

    def complete(self, prompt_context: PromptContext) -> ModelResponse:
        self.calls.append(prompt_context)
        return ModelResponse(text=self._fixed_text, model_name=self.name)


__all__ = ["DeterministicModelClient"]
