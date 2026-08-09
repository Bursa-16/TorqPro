"""ADR-0017 Karar 3 / ADR-0018 Karar 2/3/6/7/12 --
backend.ai_gateway.retrieval.question_bank_adapter must (a) return
only currently-publishable (``validated`` status, active content)
Question Bank records, (b) never import backend.question_bank.store,
(c) call no Question Bank *write* function, (d) never pass
``publishable_only=False``/``validation_status=`` to
``list_questions``, and (e) support category/difficulty/tag/keyword
narrowing entirely through the existing
``backend.question_bank.retrieval.list_questions`` filters.

Reuses the same lifecycle-building pattern as
tests/test_faz_2_9_1_question_bank_foundation.py (register -> submit
for technical review -> validate / reject / deprecate), since this
adapter's only job is to sit correctly on top of that already-tested
lifecycle.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.ai_gateway.retrieval.question_bank_adapter import (
    get_filtered_question_evidence,
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
    StandardReference,
    TraceabilityLevel,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ADAPTER_PATH = REPO_ROOT / "backend" / "ai_gateway" / "retrieval" / "question_bank_adapter.py"


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


def _promote_to_deprecated(c, record, actor="ai-gateway-tester"):
    """validated -> deprecated (a legal transition per
    backend.question_bank.transitions). Used to prove ADR-0018 Karar
    12: a deprecated record is never AI evidence, even though it was
    validated at some point and even if its JSON is_active is still
    True (validate_publishable's own docstring)."""
    _promote_to_validated(c, record, actor=actor)
    service.deprecate_question(
        c,
        question_id=record.question_id,
        content_version=record.content_version,
        actor=actor,
        actor_role="admin",
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


# ---------------------------------------------------------------------
# ADR-0018 Karar 2 -- static usage-boundary tests for list_questions().
# ---------------------------------------------------------------------


def test_adapter_never_passes_publishable_only_false_or_validation_status():
    """Static proof of ADR-0018 Karar 2's exact usage boundary: no
    call in this module may pass ``publishable_only=False`` or
    ``validation_status=`` to ``list_questions`` (the latter is only
    meaningful when the former is False, which never happens here).

    AST-based (keyword names on Call nodes), not a substring search --
    same rationale as
    test_adapter_module_calls_no_question_bank_write_function above:
    this module's own docstring discusses both parameters in prose to
    document what must never happen, so a substring search would
    false-positive on that documentation.
    """
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"), filename=str(ADAPTER_PATH))

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "validation_status":
                violations.append("validation_status= passed to a call")
            if kw.arg == "publishable_only" and isinstance(kw.value, ast.Constant):
                if kw.value.value is False:
                    violations.append("publishable_only=False passed to a call")

    assert not violations, f"ADR-0018 Karar 2 usage-boundary violation(s): {violations}"


def test_adapter_never_sets_include_deleted_or_include_archived_true():
    """Static proof that this module never passes
    ``include_deleted=True`` or ``include_archived=True`` to
    ``list_questions`` (ADR-0018 Karar 2)."""
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"), filename=str(ADAPTER_PATH))

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in ("include_deleted", "include_archived") and isinstance(
                kw.value, ast.Constant
            ):
                if kw.value.value is True:
                    violations.append(f"{kw.arg}=True passed to a call")

    assert not violations, f"ADR-0018 Karar 2 usage-boundary violation(s): {violations}"


# ---------------------------------------------------------------------
# ADR-0018 Karar 3/12 -- deprecated/rejected/technical_review content
# is never AI evidence.
# ---------------------------------------------------------------------


def test_deprecated_content_is_never_evidence(db, qb_store_path):
    """A record that was once validated, then deprecated, must never
    appear as evidence -- even though it passed through 'validated'
    and even if its JSON is_active is still True (ADR-0018 Karar 12 /
    validate_publishable's own authoritative-SQLite-status rule)."""
    deprecated = _make_record(
        question_id="QB-AI-DEPRECATED-001",
        question_tr="Kullanımdan kaldırılan soru, en az on karakter.",
        question_en="A deprecated-status question, at least ten characters.",
    )
    _register(db, qb_store_path, deprecated)
    _promote_to_deprecated(db, deprecated)

    evidence = get_validated_question_evidence(db)
    filtered_evidence = get_filtered_question_evidence(db)

    assert not any(s.source_id == "QB-AI-DEPRECATED-001" for s in evidence)
    assert not any(s.source_id == "QB-AI-DEPRECATED-001" for s in filtered_evidence)


def test_technical_review_content_is_never_evidence(db, qb_store_path):
    """A record sitting in technical_review (never yet validated) must
    never appear as evidence (ADR-0018 Karar 3)."""
    in_review = _make_record(
        question_id="QB-AI-TECHREVIEW-001",
        question_tr="İnceleme aşamasındaki soru, en az on karakter.",
        question_en="A technical-review-status question, at least ten characters.",
    )
    _register(db, qb_store_path, in_review)
    service.submit_for_technical_review(
        db,
        question_id=in_review.question_id,
        content_version=in_review.content_version,
        actor="ai-gateway-tester",
    )

    evidence = get_validated_question_evidence(db)
    filtered_evidence = get_filtered_question_evidence(db)

    assert not any(s.source_id == "QB-AI-TECHREVIEW-001" for s in evidence)
    assert not any(s.source_id == "QB-AI-TECHREVIEW-001" for s in filtered_evidence)


# ---------------------------------------------------------------------
# ADR-0018 Karar 6/7 -- category/difficulty/tag/keyword narrowing via
# the existing list_questions() filters.
# ---------------------------------------------------------------------


def test_filtered_evidence_narrows_by_category(db, qb_store_path):
    torque_question = _make_record(
        question_id="QB-AI-CAT-TORQUE-001",
        category=Category.TIGHTENING_TORQUE,
    )
    preload_question = _make_record(
        question_id="QB-AI-CAT-PRELOAD-001",
        category=Category.PRELOAD_CLAMP_FORCE,
        question_tr="Ön yük hakkında farklı bir soru metni.",
        question_en="A different question text about preload.",
    )
    for record in (torque_question, preload_question):
        _register(db, qb_store_path, record)
        _promote_to_validated(db, record)

    torque_only = get_filtered_question_evidence(
        db, category_hint=Category.TIGHTENING_TORQUE.value
    )
    returned_ids = {s.source_id for s in torque_only}

    assert "QB-AI-CAT-TORQUE-001" in returned_ids
    assert "QB-AI-CAT-PRELOAD-001" not in returned_ids


def test_filtered_evidence_narrows_by_difficulty(db, qb_store_path):
    beginner = _make_record(
        question_id="QB-AI-DIFF-BEGINNER-001", difficulty=Difficulty.BEGINNER
    )
    advanced = _make_record(
        question_id="QB-AI-DIFF-ADVANCED-001",
        difficulty=Difficulty.ADVANCED,
        question_tr="İleri seviye için farklı bir soru metni.",
        question_en="A different advanced-level question text.",
    )
    for record in (beginner, advanced):
        _register(db, qb_store_path, record)
        _promote_to_validated(db, record)

    beginner_only = get_filtered_question_evidence(
        db, difficulty_hint=Difficulty.BEGINNER.value
    )
    returned_ids = {s.source_id for s in beginner_only}

    assert "QB-AI-DIFF-BEGINNER-001" in returned_ids
    assert "QB-AI-DIFF-ADVANCED-001" not in returned_ids


def test_filtered_evidence_narrows_by_tags(db, qb_store_path):
    tagged = _make_record(question_id="QB-AI-TAG-001", tags=["torque-wrench-calibration"])
    untagged = _make_record(
        question_id="QB-AI-TAG-002",
        tags=["unrelated-tag"],
        question_tr="Etiketsiz farklı bir soru metni burada.",
        question_en="A differently-tagged question text here.",
    )
    for record in (tagged, untagged):
        _register(db, qb_store_path, record)
        _promote_to_validated(db, record)

    tag_match = get_filtered_question_evidence(db, tags=["torque-wrench-calibration"])
    returned_ids = {s.source_id for s in tag_match}

    assert "QB-AI-TAG-001" in returned_ids
    assert "QB-AI-TAG-002" not in returned_ids


def test_filtered_evidence_unknown_category_hint_degrades_gracefully(db, qb_store_path):
    """An unrecognised category hint must not raise and must not
    exclude every result -- it degrades to 'no category filter'
    (ADR-0018 Karar 6)."""
    validated = _make_record(question_id="QB-AI-UNKNOWN-HINT-001")
    _register(db, qb_store_path, validated)
    _promote_to_validated(db, validated)

    evidence = get_filtered_question_evidence(
        db, category_hint="not-a-real-category-xyz"
    )

    assert any(s.source_id == "QB-AI-UNKNOWN-HINT-001" for s in evidence)


def test_filtered_evidence_still_excludes_non_publishable_content(db, qb_store_path):
    """The filtered entry point must apply the exact same
    publishable-only guarantee as the unfiltered one (ADR-0018 Karar
    2's single-source-of-truth rule)."""
    draft = _make_record(
        question_id="QB-AI-FILTERED-DRAFT-001",
        category=Category.TIGHTENING_TORQUE,
    )
    _register(db, qb_store_path, draft)
    # left in draft -- no transition applied.

    evidence = get_filtered_question_evidence(
        db, category_hint=Category.TIGHTENING_TORQUE.value
    )

    assert not any(s.source_id == "QB-AI-FILTERED-DRAFT-001" for s in evidence)


# ---------------------------------------------------------------------
# ADR-0018 Karar 5/8/16 -- EvidenceSource metadata fields and backward
# compatibility.
# ---------------------------------------------------------------------


def test_evidence_source_metadata_populated_from_domain_model(db, qb_store_path):
    record = _make_record(
        question_id="QB-AI-METADATA-001",
        standard_reference=StandardReference(
            name="VDI 2230", edition_or_year="2015", clause_or_table="Table 5.4/1"
        ),
    )
    _register(db, qb_store_path, record)
    _promote_to_validated(db, record)

    evidence = get_validated_question_evidence(db)
    match = [s for s in evidence if s.source_id == "QB-AI-METADATA-001"][0]

    assert match.standard_name == "VDI 2230"
    assert match.standard_clause == "Table 5.4/1"
    assert match.source_kind == SourceType.INTERNAL_ENGINE.value
    assert match.category == Category.TIGHTENING_TORQUE.value
    assert match.difficulty == Difficulty.BEGINNER.value
    assert "ai-gateway-test" in match.tags
    assert match.traceability_level == TraceabilityLevel.PROVISIONAL.value


def test_evidence_source_metadata_defaults_to_none_when_no_standard_reference(db, qb_store_path):
    record = _make_record(question_id="QB-AI-NO-STANDARD-001", standard_reference=None)
    _register(db, qb_store_path, record)
    _promote_to_validated(db, record)

    evidence = get_validated_question_evidence(db)
    match = [s for s in evidence if s.source_id == "QB-AI-NO-STANDARD-001"][0]

    assert match.standard_name is None
    assert match.standard_clause is None


def test_evidence_source_original_seven_field_construction_still_works():
    """Backward-compatibility proof (ADR-0018 Karar 5/9 in the GO
    criteria): constructing an EvidenceSource the way
    v3.0.0-alpha.1 code did -- with only the original seven fields --
    must still work unchanged, with every new field defaulting."""
    from backend.ai_gateway.retrieval import EvidenceSource

    source = EvidenceSource(
        source_type="question_bank",
        source_id="QB-LEGACY-001",
        content_version=1,
        title_tr="Eski stil çağrı",
        title_en="Legacy-style call",
        body_tr="Açıklama metni burada, en az yirmi karakter uzunlukta.",
        body_en="Explanation text here, at least twenty characters long.",
    )

    assert source.standard_name is None
    assert source.standard_clause is None
    assert source.source_kind is None
    assert source.category is None
    assert source.difficulty is None
    assert source.tags == ()
    assert source.traceability_level is None
