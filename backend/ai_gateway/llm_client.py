"""TorqPro AI Gateway - AI model client abstraction.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 4
("AI provider abstraction yapisi").

Naming note (deliberate, per ADR-0017 Karar 4): this module's
abstraction is named ``AIModelClient``, never ``Provider``.
``backend.calculation_engine.provider.Provider`` is the existing,
unrelated abstraction for deterministic engineering-calculation
providers (e.g. ``VDI2230Provider``). The two concepts must never be
merged, aliased or made to share a base class -- doing so would blur
exactly the deterministic/AI boundary ADR-0017 exists to keep sharp.

``PromptContext`` and ``ModelResponse`` follow the same immutable-
dataclass design philosophy as
``backend.calculation_engine.request.CalculationRequest``/
``response.CalculationResponse``, but are entirely separate types
with no import relationship to those modules -- one pair is a
deterministic engineering calculation contract, the other is a model-
completion contract, and they are never interchanged.

No concrete, network-calling ``AIModelClient`` subclass is defined in
this phase (ADR-0017 Karar 4 / Karar 12: "ilk implementasyon fazında
oluşturulmayan dosyalar" explicitly excludes ``backend/ai_gateway/
providers/*``). ``FakeModelClient`` below is a deterministic,
in-process test double only -- it makes no network call, requires no
API key and is not a "real" AI provider.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse


@dataclass(frozen=True)
class PromptContext:
    """Structured (never free-text-concatenated) input to an
    ``AIModelClient``.

    Attributes:
        query_text: The user's original question, verbatim.
        language: Active UI language ("tr" or "en") -- see
            ``backend.ai_gateway.permission.UserContext.language``.
        evidence: Retrieved, approved-only sources (ADR-0017 Karar 3;
            ADR-0018 owns retrieval strategy). May be empty -- an
            empty sequence is a normal, expected value, not an error.
        calculation_result: The deterministic engine's own output for
            this query, when a calculation was requested and
            succeeded (ADR-0017 Karar 5). ``None`` when no
            calculation was requested. Never constructed or
            approximated by anything in ``backend.ai_gateway`` --
            always the unmodified return value of a
            ``backend.calculation_engine.provider.Provider.calculate``
            call, forwarded via ``backend.ai_gateway.tools.
            calculation_tool``.
        metadata: Optional free-form caller metadata (request id,
            trace id), never interpreted by an ``AIModelClient``
            implementation -- mirrors
            ``CalculationRequest.metadata``'s same role.
    """

    query_text: str
    language: str
    evidence: Sequence[EvidenceSource] = field(default_factory=tuple)
    calculation_result: Optional[CalculationResponse] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelResponse:
    """Immutable output contract returned by any ``AIModelClient``.

    Attributes:
        text: The model's natural-language completion. This is
            advisory/interpretive text only -- per ADR-0017 Karar 5,
            nothing in ``text`` is treated as an authoritative
            numeric engineering result by any downstream consumer
            (``evidence_checker``/``composer``); the authoritative
            numeric source, when one exists, is always
            ``PromptContext.calculation_result``, carried through
            unchanged.
        model_name: Identifier of the concrete ``AIModelClient`` that
            produced this response (mirrors
            ``CalculationResponse.provider_version``'s traceability
            role for the deterministic side).
    """

    text: str
    model_name: str


class AIModelClient(abc.ABC):
    """Abstract base every concrete AI model provider implements.

    Concrete subclasses declare ``name`` as a class attribute and
    implement ``complete``. Mirrors
    ``backend.calculation_engine.provider.Provider``'s shape
    deliberately (same abstraction *style*), while remaining a fully
    separate type (see module docstring's naming note).
    """

    name: str

    @abc.abstractmethod
    def complete(self, prompt_context: PromptContext) -> ModelResponse:
        """Produce a completion for ``prompt_context``.

        Implementations may raise any exception on failure (network
        error, timeout, malformed provider response); callers
        (``backend.ai_gateway.orchestrator``) are responsible for
        catching and re-raising as
        ``backend.ai_gateway.exceptions.ModelUnavailableError``
        (ADR-0017 Karar 9, case 1) -- this method itself does not
        need to normalize its own failure modes.
        """
        raise NotImplementedError

    @property
    def model_identifier(self) -> str:
        """Faz v3.0.0-alpha.5 (Provider Abstraction, ADR-0020): the
        concrete model/build identifier this client reports, distinct
        in principle from ``name`` (a networked provider may expose
        several models under one provider ``name``, e.g.
        ``name="openai"`` with several selectable ``model_identifier``
        values). Defaults to ``name`` verbatim -- every client defined
        in this phase (``DeterministicModelClient``, ``FakeModelClient``,
        ``RaisingModelClient``) has exactly one model, so the default
        is correct as-is and none of them need to override it. A
        future networked provider (out of scope here) would override
        this property, not ``name``.
        """
        return self.name

    def is_available(self) -> bool:
        """Faz v3.0.0-alpha.5 (Provider Abstraction, ADR-0020): cheap,
        side-effect-free configuration/availability check -- never
        calls ``complete`` and never performs network I/O. Defaults to
        ``True`` (every client already defined in
        ``backend.ai_gateway`` is unconditionally usable). A future
        networked provider would override this to report, for
        example, "no API key configured" without attempting a real
        request -- this is a static readiness signal, not a liveness
        probe.
        """
        return True


class FakeModelClient(AIModelClient):
    """Deterministic, in-process test double.

    Not a real AI provider: makes no network call, has no external
    dependency, and always returns the same configured text
    regardless of ``prompt_context`` content. Exists solely so
    ``backend.ai_gateway.orchestrator`` and its tests can exercise the
    full permission -> context -> retrieval -> tools -> llm_client ->
    evidence_checker -> composer -> audit pipeline without a real
    model integration, which ADR-0017 Karar 4/12 explicitly defers to
    a later, separately-approved phase.
    """

    name = "fake-test-client"

    def __init__(self, fixed_text: str = "TorqPro AI test response.") -> None:
        self._fixed_text = fixed_text
        self.calls: list[PromptContext] = []

    def complete(self, prompt_context: PromptContext) -> ModelResponse:
        self.calls.append(prompt_context)
        return ModelResponse(text=self._fixed_text, model_name=self.name)


class RaisingModelClient(AIModelClient):
    """Deterministic test double that always fails.

    Used by tests to exercise ADR-0017 Karar 9 case 1 (model provider
    failure -> explicit, non-swallowed error) without depending on a
    real network failure being reproducible in CI.
    """

    name = "raising-test-client"

    def __init__(self, error: Exception) -> None:
        self._error = error

    def complete(self, prompt_context: PromptContext) -> ModelResponse:
        raise self._error


__all__ = [
    "PromptContext",
    "ModelResponse",
    "AIModelClient",
    "FakeModelClient",
    "RaisingModelClient",
]
