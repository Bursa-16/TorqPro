"""ADR-0017 Karar 1, 5, 9 -- end-to-end pipeline boundary tests for
backend.ai_gateway.orchestrator.handle_query.

Covers:
    - Permission is checked before anything else (an inactive user
      never reaches retrieval or the model client).
    - No evidence + no calculation -> insufficient-evidence answer,
      even though the pipeline still calls the model client (the
      *composer*, not the model call, is what withholds the text).
    - Evidence present -> the model's text is returned, evidence is
      attached.
    - A deterministic calculation result is forwarded completely
      unmodified into the final answer (ADR-0017 Karar 5's core
      guarantee).
    - A CalculationInputError from the deterministic engine
      propagates out of handle_query unchanged, and the model client
      is never called in that case (ADR-0017 Karar 9, case 3).
    - A model-client failure is normalized into ModelUnavailableError
      (ADR-0017 Karar 9, case 1).
"""

from __future__ import annotations

import pytest

from backend.ai_gateway.audit import InMemoryAuditSink
from backend.ai_gateway.exceptions import ModelUnavailableError, PermissionDeniedError
from backend.ai_gateway.llm_client import FakeModelClient, RaisingModelClient
from backend.ai_gateway.orchestrator import handle_query
from backend.ai_gateway.permission import UserContext
from backend.app import conn
from backend.calculation_engine.exceptions import CalculationInputError
from backend.calculation_engine.provider import Provider
from backend.calculation_engine.request import CalculationRequest
from backend.calculation_engine.response import CalculationResponse, CalculationResult
from backend.question_bank import service, store
from backend.question_bank.schema import (
    Category,
    Difficulty,
    EngineeringRiskLevel,
    QuestionRecord,
    QuestionType,
    SourceReference,
    SourceType,
    TraceabilityLevel,
)


class _FixedResultProvider(Provider):
    standard = "TEST-STANDARD"
    version = "0.0.1-test"

    def calculate(self, request: CalculationRequest) -> CalculationResponse:
        return CalculationResponse(
            standard=self.standard,
            provider_version=self.version,
            inputs=request.inputs,
            results=[
                CalculationResult(
                    value=987.65,
                    unit="Nm",
                    formula_id="TEST-FORMULA-ORCH-001",
                    classification="QUICK",
                    validation_status="APPROVED",
                )
            ],
            formula_traces=[],
            warnings=[],
            validation={},
        )


class _RaisingProvider(Provider):
    standard = "TEST-STANDARD-RAISING"
    version = "0.0.1-test"

    def calculate(self, request: CalculationRequest) -> CalculationResponse:
        raise CalculationInputError("missing required input: torque_target_nm")


def _allow_all(role: str, action: str) -> bool:
    return True


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-AI-ORCH-00001",
        content_version=1,
        category=Category.TIGHTENING_TORQUE,
        subcategory=None,
        difficulty=Difficulty.BEGINNER,
        question_type=QuestionType.SINGLE_CHOICE,
        question_tr="Orkestrasyon testi için soru metni, en az on karakter.",
        question_en="Orchestrator test question text, at least ten characters.",
        options_tr=["A", "B", "C"],
        options_en=["A", "B", "C"],
        correct_answer=0,
        technical_explanation_tr="Bu açıklama en az yirmi karakter uzunluğunda olmalıdır.",
        technical_explanation_en="This explanation must be at least twenty characters long.",
        standard_reference=None,
        source_reference=SourceReference(
            source_type=SourceType.INTERNAL_ENGINE, description="ai-gateway-orchestrator-test"
        ),
        source_locator=None,
        traceability_level=TraceabilityLevel.PROVISIONAL,
        tags=["ai-gateway-orchestrator-test"],
        learning_objective="Orkestrasyon testi için öğrenme hedefi metni.",
        engineering_risk_level=EngineeringRiskLevel.LOW,
        is_active=True,
    )
    base.update(overrides)
    return QuestionRecord(**base)


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_ai_orchestrator_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    with conn() as c:
        yield c


def _active_user(user_id: int = 1) -> UserContext:
    return UserContext(user_id=user_id, role="engineer", is_active=True)


def test_inactive_user_is_denied_before_any_retrieval_or_model_call(db):
    model = FakeModelClient()
    sink = InMemoryAuditSink()
    inactive_user = UserContext(user_id=99, role="engineer", is_active=False)

    with pytest.raises(PermissionDeniedError):
        handle_query(
            user=inactive_user,
            query_text="preload nedir?",
            conn=db,
            model_client=model,
            audit_sink=sink,
            query_text_hash="hash-1",
            created_at="2026-08-09T00:00:00+00:00",
        )

    assert model.calls == []
    assert sink.all_entries() == ()


def test_no_evidence_no_calculation_yields_insufficient_evidence(db):
    model = FakeModelClient(fixed_text="This text must never reach the user.")
    sink = InMemoryAuditSink()

    answer = handle_query(
        user=_active_user(),
        query_text="tamamen ilgisiz bir sorgu metni xyz123",
        conn=db,
        model_client=model,
        audit_sink=sink,
        query_text_hash="hash-2",
        created_at="2026-08-09T00:00:00+00:00",
    )

    assert answer.insufficient_evidence is True
    assert answer.text != "This text must never reach the user."
    assert answer.evidence == ()
    assert answer.calculation_result is None
    # The model *is* still called (pipeline order: retrieval -> tools ->
    # llm_client -> evidence_checker -> composer) -- it is the composer,
    # not the model call itself, that withholds the model's text.
    assert len(model.calls) == 1
    entries = sink.all_entries()
    assert len(entries) == 1
    assert entries[0].had_sufficient_evidence is False


def test_evidence_present_yields_model_text_and_attached_evidence(db, qb_store_path):
    record = _make_record()
    store.save_question_content(record, path=qb_store_path)
    service.register_question(
        db, question_id=record.question_id, content_version=record.content_version, actor="t"
    )
    service.submit_for_technical_review(
        db, question_id=record.question_id, content_version=record.content_version, actor="t"
    )
    service.validate_question(
        db,
        question_id=record.question_id,
        content_version=record.content_version,
        actor="t",
        actor_role="admin",
        reviewed_by="t",
        review_date="2026-08-09",
        authorize=_allow_all,
    )

    model = FakeModelClient(fixed_text="Grounded answer text.")
    sink = InMemoryAuditSink()

    answer = handle_query(
        user=_active_user(),
        query_text="orkestrasyon",
        conn=db,
        model_client=model,
        audit_sink=sink,
        query_text_hash="hash-3",
        created_at="2026-08-09T00:00:00+00:00",
    )

    assert answer.insufficient_evidence is False
    assert answer.text == "Grounded answer text."
    assert any(source.source_id == "QB-AI-ORCH-00001" for source in answer.evidence)


def test_calculation_result_is_forwarded_completely_unmodified(db):
    model = FakeModelClient(fixed_text="Explains the calculation.")
    sink = InMemoryAuditSink()
    provider = _FixedResultProvider()
    request = CalculationRequest(standard="TEST-STANDARD", inputs={"thread": "M10"})

    answer = handle_query(
        user=_active_user(),
        query_text="preload hesapla",
        conn=db,
        model_client=model,
        audit_sink=sink,
        query_text_hash="hash-4",
        created_at="2026-08-09T00:00:00+00:00",
        calculation_provider=provider,
        calculation_request=request,
    )

    assert answer.insufficient_evidence is False
    assert answer.calculation_result is not None
    assert answer.calculation_result.results[0].value == 987.65
    assert answer.calculation_result.results[0].formula_id == "TEST-FORMULA-ORCH-001"
    # The composer's text is the model's own text -- the numeric result
    # is carried alongside it, never re-derived from it.
    assert answer.text == "Explains the calculation."
    entries = sink.all_entries()
    assert entries[0].calculation_formula_ids == ("TEST-FORMULA-ORCH-001",)


def test_calculation_input_error_propagates_and_model_is_never_called(db):
    model = FakeModelClient()
    sink = InMemoryAuditSink()
    provider = _RaisingProvider()
    request = CalculationRequest(standard="TEST-STANDARD-RAISING", inputs={})

    with pytest.raises(CalculationInputError, match="torque_target_nm"):
        handle_query(
            user=_active_user(),
            query_text="preload hesapla",
            conn=db,
            model_client=model,
            audit_sink=sink,
            query_text_hash="hash-5",
            created_at="2026-08-09T00:00:00+00:00",
            calculation_provider=provider,
            calculation_request=request,
        )

    assert model.calls == []
    assert sink.all_entries() == ()


def test_model_failure_is_normalized_to_model_unavailable_error(db):
    original_error = RuntimeError("simulated network timeout")
    model = RaisingModelClient(original_error)
    sink = InMemoryAuditSink()

    with pytest.raises(ModelUnavailableError) as exc_info:
        handle_query(
            user=_active_user(),
            query_text="preload nedir?",
            conn=db,
            model_client=model,
            audit_sink=sink,
            query_text_hash="hash-6",
            created_at="2026-08-09T00:00:00+00:00",
        )

    assert exc_info.value.__cause__ is original_error
    assert sink.all_entries() == ()
