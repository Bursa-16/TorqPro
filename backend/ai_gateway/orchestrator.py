"""TorqPro AI Gateway - orchestrator (single entry point).

Faz v3.0.0-alpha.1 (AI Architecture Foundation) + Faz v3.0.0-alpha.2
(AI Retrieval & Grounding) + Faz v3.0.0-alpha.3 (AI Safety, Validation
& Explainability), per ADR-0017 Karar 1 ("ai_gateway paketinin kesin
sorumlulukları") and Karar 11 (module tree: "orchestrator.py # tek
giriş noktası"), ADR-0018 Karar 6/13/15, and ADR-0019 Karar 18.

``handle_query`` is the *only* function outside functions in this
package that a future HTTP route layer (``backend.api.ai.routes``,
not created in this phase -- ADR-0017 Karar 12/13) is expected to
call. It wires, in fixed order:

    permission -> context_builder -> retrieval -> (optional) tools ->
    llm_client -> evidence_checker -> composer -> audit

exactly matching SDS §5 / ADR-0017 Karar 1's pipeline description.
No step is skipped and no step's output is mutated by a later step
beyond what each module's own contract already allows (composer may
select *between* the model's text and the fixed insufficient-evidence
notice; it may not edit either).

Framework-agnostic: no ``fastapi`` import, no ``backend.app`` import.
Callers supply an already-open ``sqlite3.Connection`` (matching every
existing ``backend.question_bank.service`` function's own calling
convention) and an ``AIModelClient`` instance; this module manages no
connection lifecycle and no model-client configuration of its own.

Error handling (ADR-0017 Karar 9):
    1. Model-provider failure -> caught here and re-raised as
       ``backend.ai_gateway.exceptions.ModelUnavailableError`` (never
       swallowed, never papered over with a fabricated answer).
    2. Insufficient evidence -> not an error; flows through
       ``evidence_checker``/``composer`` as a normal
       ``ComposedAnswer`` with ``insufficient_evidence=True``.
    3. Deterministic calculation failure
       (``CalculationInputError`` and siblings) -> deliberately
       **not** caught here. It propagates unchanged out of
       ``handle_query`` to the caller, exactly as it propagates
       unchanged out of ``backend.ai_gateway.tools.calculation_tool``.
"""

from __future__ import annotations

import sqlite3
from typing import Optional, Sequence

from backend.ai_gateway import composer as composer_module
from backend.ai_gateway.audit import AIInteractionRecord, AuditSink
from backend.ai_gateway.context_builder import build_context
from backend.ai_gateway.evidence_checker import check_evidence
from backend.ai_gateway.exceptions import ModelUnavailableError
from backend.ai_gateway.llm_client import AIModelClient
from backend.ai_gateway.permission import UserContext, ensure_active_user
from backend.ai_gateway.retrieval.question_bank_adapter import (
    get_filtered_question_evidence,
    get_validated_question_evidence,
)
from backend.ai_gateway.tools.calculation_tool import run_calculation
from backend.calculation_engine.provider import Provider
from backend.calculation_engine.request import CalculationRequest
from backend.calculation_engine.response import CalculationResponse

#: Fixed label used in AIInteractionRecord.retrieval_source_types_queried
#: for the Question Bank adaptor -- mirrors the adaptor's own
#: EvidenceSource.source_type constant (ADR-0018 Karar 15).
_QUESTION_BANK_SOURCE_TYPE = "question_bank"


def handle_query(
    *,
    user: UserContext,
    query_text: str,
    conn: sqlite3.Connection,
    model_client: AIModelClient,
    audit_sink: AuditSink,
    query_text_hash: str,
    created_at: str,
    calculation_provider: Optional[Provider] = None,
    calculation_request: Optional[CalculationRequest] = None,
    category_hint: Optional[str] = None,
    difficulty_hint: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
) -> composer_module.ComposedAnswer:
    """Run one full AI-gateway interaction and return a
    :class:`~backend.ai_gateway.composer.ComposedAnswer`.

    ``calculation_provider``/``calculation_request``, when both
    supplied, name a deterministic ``Provider``/``CalculationRequest``
    pair to invoke via ``backend.ai_gateway.tools.calculation_tool``
    (ADR-0017 Karar 5) -- this is the *only* way a
    ``CalculationResponse`` can enter this pipeline. If
    ``provider.calculate(request)`` raises, that exception propagates
    unchanged out of this function (see module docstring, error
    handling case 3); no partial audit record is written for a failed
    calculation. Supplying only one of the two parameters is treated
    as "no calculation requested" (both are required together).

    ``category_hint``/``difficulty_hint``/``tags`` (ADR-0018 Karar 6/7,
    all optional, default ``None``) narrow Question Bank retrieval via
    ``backend.ai_gateway.retrieval.question_bank_adapter.
    get_filtered_question_evidence``. When none of the three are
    supplied, retrieval behaves exactly as in v3.0.0-alpha.1
    (``get_validated_question_evidence`` with only a keyword match) --
    this keeps every existing alpha.1 caller's behaviour byte-for-byte
    unchanged.
    """
    ensure_active_user(user)

    if category_hint is not None or difficulty_hint is not None or tags is not None:
        evidence = get_filtered_question_evidence(
            conn,
            keyword=query_text,
            category_hint=category_hint,
            difficulty_hint=difficulty_hint,
            tags=tags,
        )
    else:
        evidence = get_validated_question_evidence(conn, keyword=query_text)

    calculation_result: Optional[CalculationResponse] = None
    if calculation_provider is not None and calculation_request is not None:
        # Deliberately no try/except here -- CalculationInputError and
        # siblings must propagate unchanged (ADR-0017 Karar 9, case 3).
        calculation_result = run_calculation(calculation_provider, calculation_request)

    prompt_context = build_context(
        query_text=query_text,
        user=user,
        evidence=evidence,
        calculation_result=calculation_result,
    )

    try:
        model_response = model_client.complete(prompt_context)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any
        # AIModelClient failure mode (network error, timeout, malformed
        # provider payload) is normalized into ModelUnavailableError so
        # it is never silently swallowed (ADR-0017 Karar 9, case 1).
        raise ModelUnavailableError(
            f"AIModelClient '{model_client.name}' failed to produce a completion"
        ) from exc

    evidence_check = check_evidence(evidence, calculation_result)
    answer = composer_module.compose(
        model_response,
        evidence_check,
        language=user.language,
        attempted_source_types=(_QUESTION_BANK_SOURCE_TYPE,),
    )

    evidence_counts: dict[str, int] = {}
    for source in answer.evidence:
        evidence_counts[source.source_type] = evidence_counts.get(source.source_type, 0) + 1

    audit_sink.record(
        AIInteractionRecord(
            user_id=user.user_id,
            query_text_hash=query_text_hash,
            evidence_source_ids=tuple(
                (source.source_type, source.source_id) for source in answer.evidence
            ),
            calculation_formula_ids=(
                tuple(result.formula_id for result in calculation_result.results)
                if calculation_result is not None
                else ()
            ),
            model_name=answer.model_name,
            had_sufficient_evidence=not answer.insufficient_evidence,
            created_at=created_at,
            # ADR-0018 Karar 15: only adaptors actually invoked this call are
            # listed. This phase only ever queries Question Bank.
            retrieval_source_types_queried=(_QUESTION_BANK_SOURCE_TYPE,),
            evidence_count_by_source_type=tuple(sorted(evidence_counts.items())),
            # ADR-0019 Karar 18: mirror the safety/validation outcome verbatim.
            evidence_status=evidence_check.status,
            result_label=answer.result_label,
        )
    )

    return answer


__all__ = ["handle_query"]
