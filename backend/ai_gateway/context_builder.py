"""TorqPro AI Gateway - context builder.

Faz v3.0.0-alpha.1 (AI Architecture Foundation), per ADR-0017 Karar 7
("Prompt / context olusturma katmaninin yeri").

Framework-agnostic and side-effect-free: this module only assembles a
:class:`~backend.ai_gateway.llm_client.PromptContext` from already-
retrieved data. It never calls a retrieval adaptor itself (that is
``backend.ai_gateway.orchestrator``'s job) and never calls a
``backend.ai_gateway.tools`` adaptor -- per ADR-0017 Karar 7:
"context_builder.py, tools/ adaptörlerini çağırmaz -- yalnızca bağlam
toplar. Hesaplama tetikleme kararı composer/orchestrator seviyesinde
verilir."
"""

from __future__ import annotations

from typing import Optional, Sequence

from backend.ai_gateway.llm_client import PromptContext
from backend.ai_gateway.permission import UserContext
from backend.ai_gateway.retrieval import EvidenceSource
from backend.calculation_engine.response import CalculationResponse


def build_context(
    *,
    query_text: str,
    user: UserContext,
    evidence: Sequence[EvidenceSource],
    calculation_result: Optional[CalculationResponse] = None,
) -> PromptContext:
    """Assemble a :class:`PromptContext` from already-collected
    inputs.

    ``evidence`` and ``calculation_result`` are passed through
    unmodified -- this function performs no filtering, ranking or
    truncation of its own (any such policy belongs to the retrieval
    adaptor that produced ``evidence``, or to a later, separately-
    approved phase). ``calculation_result``, when present, is never
    inspected or altered here -- it is carried into ``PromptContext``
    exactly as received, matching ADR-0017 Karar 5.
    """
    return PromptContext(
        query_text=query_text,
        language=user.language,
        evidence=tuple(evidence),
        calculation_result=calculation_result,
        metadata={"user_id": user.user_id, "user_role": user.role},
    )


__all__ = ["build_context"]
