"""ADR-0017 Karar 3 -- backend.ai_gateway.retrieval.question_bank_adapter
must (a) return only currently-publishable (``validated`` status,
active content) Question Bank records, (b) never import
backend.question_bank.store, and (c) call no Question Bank *write*
function.

Reuses the same lifecycle-building pattern as
tests/test_faz_2_9_1_question_bank_foundation.py (register -> submit
for technical review -> validate / reject), since this adapter's only
job is to sit correctly on top of that already-tested lifecycle.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.ai_gateway.retrieval.question_bank_adapter import (
    get_validated_question_evidence,
)
from backend.app import conn
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

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _allow_all(role: str, action: str) -> bool:
    return True


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-AI-TEST-00001",
        content_version=1,
        category=Category.TIGHTENING_TORQUE,
        subcategory=None,
        difficulty=Difficulty.BEGINNER,
        question_type=QuestionType.SINGLE_CHOICE,
        question_tr="AI erişim testi için soru metni, en az on karakter.",
        question_en="AI access test question text, at least ten characters.",
        options_tr=["A", "B", "C"],
        options_en=["A", "B", "C"],
        correct_answer=0,
        technical_explanation_tr="Bu açıklama en az yirmi karakter uzunluğunda olmalıdır.",
        technical_explanation_en="This explanation must be at least twenty characters long.",
        standard_reference=None,
        source_reference=SourceReference(
            source_type=SourceType.INTERNAL_ENGINE, description="ai-gateway-test"
        ),
        source_locator=None,
        traceability_level=TraceabilityLevel.PROVISIONAL,
        tags=["ai-gateway-test"],
        learning_objective="AI erişim testi için öğrenme hedefi metni.",
        engineering_risk_level=EngineeringRiskLevel.LOW,
        is_active=True,
    )
    base.update(overrides)
    return QuestionRecord(**base)


def _register(c, path, record, actor="ai-gateway-tester"):
    store.save_question_content(record, path=path)
    service.register_question(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )


def _promote_to_validated(c, record, actor="ai-gateway-tester"):
    service.submit_for_technical_review(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )
    service.validate_question(
        c,
        question_id=record.question_id,
        content_version=record.content_version,
        actor=actor,
        actor_role="admin",
        reviewed_by=actor,
        review_date="2026-08-09",
        authorize=_allow_all,
    )


def _promote_to_rejected(c, record, actor="ai-gateway-tester"):
    service.submit_for_technical_review(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )
    service.reject_question(
        c,
        question_id=record.question_id,
        content_version=record.content_version,
        actor=actor,
        actor_role="admin",
        reason="ai-gateway-test-rejection",
        authorize=_allow_all,
    )


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    """Isolated JSON content file per test -- never touches the real
    demo fixture shipped with the repo (same isolation pattern as
    tests/test_faz_2_9_1_question_bank_foundation.py)."""
    path = tmp_path / "question_bank_ai_gateway_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    with conn() as c:
        yield c


def test_adapter_returns_only_validated_question(db, qb_store_path):
    validated = _make_record(question_id="QB-AI-VALIDATED-001")
    draft = _make_record(
        question_id="QB-AI-DRAFT-001",
        question_tr="Taslak durumdaki soru, en az on karakter.",
        question_en="A draft-status question, at least ten characters.",
    )
    rejected = _make_record(
        question_id="QB-AI-REJECTED-001",
        question_tr="Reddedilen durumdaki soru, en az on karakter.",
        question_en="A rejected-status question, at least ten characters.",
    )

    for record in (validated, draft, rejected):
        _register(db, qb_store_path, record)
    _promote_to_validated(db, validated)
    _promote_to_rejected(db, rejected)
    # draft stays in draft status (no transition applied).

    evidence = get_validated_question_evidence(db)
    returned_ids = {source.source_id for source in evidence}

    assert "QB-AI-VALIDATED-001" in returned_ids
    assert "QB-AI-DRAFT-001" not in returned_ids
    assert "QB-AI-REJECTED-001" not in returned_ids


def test_adapter_evidence_carries_question_bank_version_pair(db, qb_store_path):
    validated = _make_record(question_id="QB-AI-VALIDATED-002", content_version=1)
    _register(db, qb_store_path, validated)
    _promote_to_validated(db, validated)

    evidence = get_validated_question_evidence(db)
    match = [source for source in evidence if source.source_id == "QB-AI-VALIDATED-002"]

    assert len(match) == 1
    assert match[0].source_type == "question_bank"
    assert match[0].content_version == 1
    assert match[0].title_tr == validated.question_tr
    assert match[0].title_en == validated.question_en


def test_adapter_keyword_filter_matches_either_language(db, qb_store_path):
    validated = _make_record(
        question_id="QB-AI-VALIDATED-003",
        question_tr="Ön yük hesaplaması hakkında bir soru.",
        question_en="A question about preload calculation.",
    )
    _register(db, qb_store_path, validated)
    _promote_to_validated(db, validated)

    tr_match = get_validated_question_evidence(db, keyword="ön yük")
    en_match = get_validated_question_evidence(db, keyword="preload")
    no_match = get_validated_question_evidence(db, keyword="nonexistent-keyword-xyz")

    assert any(s.source_id == "QB-AI-VALIDATED-003" for s in tr_match)
    assert any(s.source_id == "QB-AI-VALIDATED-003" for s in en_match)
    assert not any(s.source_id == "QB-AI-VALIDATED-003" for s in no_match)


def test_adapter_module_does_not_import_question_bank_store():
    """Static proof of ADR-0017 Karar 3: the adapter must call only
    backend.question_bank.service, never backend.question_bank.store
    directly."""
    adapter_path = (
        REPO_ROOT / "backend" / "ai_gateway" / "retrieval" / "question_bank_adapter.py"
    )
    tree = ast.parse(adapter_path.read_text(encoding="utf-8"), filename=str(adapter_path))

    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)

    assert not any(mod.endswith(".store") or mod == "backend.question_bank.store"
                   for mod in imported_modules), (
        f"question_bank_adapter.py must not import backend.question_bank.store; "
        f"found imports: {imported_modules}"
    )
    assert any("question_bank.service" in mod for mod in imported_modules)


def test_adapter_module_calls_no_question_bank_write_function():
    """Static proof that the adapter never *references as code* a
    Question Bank write-side function name (register_question,
    update_question, validate_question, reject_question,
    delete_question, and the bulk/import-export families).

    Deliberately AST-based (Name/Attribute/import identifiers only),
    not a raw substring search: this module's own docstring names
    several of these functions in prose (to document what the adapter
    must *not* do), and a substring search over the raw source text
    would false-positive on that documentation. Real code usage
    (a call, an import, an attribute access) is what actually matters
    here, and only that is what this test inspects.
    """
    adapter_path = (
        REPO_ROOT / "backend" / "ai_gateway" / "retrieval" / "question_bank_adapter.py"
    )
    tree = ast.parse(adapter_path.read_text(encoding="utf-8"), filename=str(adapter_path))

    referenced_identifiers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced_identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced_identifiers.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            referenced_identifiers.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            referenced_identifiers.update(alias.name for alias in node.names)

    forbidden_names = {
        "register_question",
        "register_question_content",
        "update_question",
        "submit_for_technical_review",
        "return_to_draft",
        "validate_question",
        "reject_question",
        "deprecate_question",
        "delete_question",
        "restore_question",
        "archive_question",
    }
    offenders = referenced_identifiers & forbidden_names
    assert not offenders, f"Adapter references write-side function(s) as code: {offenders}"
