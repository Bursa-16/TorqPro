"""TorqPro AI Gateway Reasoning - optional AI-generated wording layer
(v3.0.0-beta.2).

This is the **only** module in ``backend.ai_gateway.reasoning`` that
ever imports an ``AIModelClient`` or calls ``.complete()`` --
structurally separating "Engineering Reasoning" (``engine.py``, fully
deterministic) from "AI-generated explanation" (here), per the
approved Stage 0 design.

Reuses ``backend.ai_gateway.context_builder.build_context`` unchanged
(the same ``PromptContext`` assembly every other AI-gateway pipeline
step uses) rather than building a second, competing context shape.

**Never affects the deterministic reasoning result.** Every function
here returns ``(text, provider_name)`` or ``(None, None)`` -- it never
raises to its caller (``backend/api/routes/ai_gateway.py``'s
``engineering_reasoning_endpoint``) for a provider failure/timeout/
unknown-provider-name; those are all normalized to ``(None, None)``
here, mirroring ``backend.ai_gateway.orchestrator.handle_query``'s own
``ModelUnavailableError`` normalization pattern but *contained*
locally rather than propagated, because a reasoning caller must
receive HTTP 200 with the full deterministic ``ReasoningResult`` even
when AI wording fails (Stage 0 invariant: "AI provider unavailable
must not affect the deterministic result").

Never constructs, edits, or rounds a numeric engineering value -- the
``calculation_result`` passed into the prompt context is the same,
unmodified ``CalculationResponse``
``backend.ai_gateway.reasoning.evidence_adapter`` produced; this
module only reads ``model_client.complete(...).text`` back out and
returns it verbatim, mirroring
``backend.ai_gateway.composer``'s own rule 2.
"""

from __future__ import annotations

from typing import Optional, Tuple

from backend.ai_gateway.context_builder import build_context
from backend.ai_gateway.llm_client import AIModelClient
from backend.ai_gateway.permission import UserContext
from backend.calculation_engine.response import CalculationResponse

from .models import ReasoningResult, ReasoningState


def _build_reasoning_query_text(reasoning_result: ReasoningResult) -> str:
    """Fixed-template prompt text -- built entirely from already-
    computed, already-verbatim ``ReasoningResult`` fields (never a
    caller-supplied free string), so this module invents no new
    engineering claim for the model to react to."""
    return (
        f"trace_id={reasoning_result.trace_id} için mühendislik "
        f"reasoning sonucu: state={reasoning_result.reasoning_state}, "
        f"conclusion={reasoning_result.engineering_conclusion}. "
        "Bu deterministik sonucu, mühendislik kararını değiştirmeden, "
        "sade ve anlaşılır bir dille açıkla."
    )


def attempt_ai_explanation(
    reasoning_result: ReasoningResult,
    *,
    calculation_response: Optional[CalculationResponse],
    model_client: Optional[AIModelClient],
    user: UserContext,
    language: str = "tr",
) -> Tuple[Optional[str], Optional[str]]:
    """Try to produce AI-generated wording for an already-computed
    ``reasoning_result``. Returns ``(text, provider_name)`` on success,
    ``(None, None)`` on any failure or when no attempt was made.

    Deliberately does not attempt this for
    ``ReasoningState.INSUFFICIENT_EVIDENCE`` results (nothing evidenced
    exists to word) -- callers are expected to only call this for
    ``SUPPORTED``/``UNSUPPORTED`` results, but this function itself
    also never raises even if called for an insufficient-evidence
    result; it simply has nothing useful to prompt with and will
    return whatever the model produces for an empty conclusion (a
    caller-level gate, not a hard requirement of this function, keeps
    ``run_reasoning``'s own contract the sole source of truth for
    reasoning-state semantics).
    """
    if model_client is None:
        return None, None

    if reasoning_result.reasoning_state == ReasoningState.INSUFFICIENT_EVIDENCE:
        return None, None

    try:
        prompt_context = build_context(
            query_text=_build_reasoning_query_text(reasoning_result),
            user=user,
            evidence=(),
            calculation_result=calculation_response,
        )
        response = model_client.complete(prompt_context)
    except Exception:  # noqa: BLE001 - deliberately broad, see module
        # docstring: any AIModelClient failure mode (network error,
        # timeout, unknown-provider wiring mistake surfaced as an
        # exception by the caller before this function, malformed
        # provider payload) is normalized to (None, None) here rather
        # than propagated, so the deterministic reasoning result this
        # function's caller already has is never affected.
        return None, None

    return response.text, model_client.name


__all__ = ["attempt_ai_explanation"]
