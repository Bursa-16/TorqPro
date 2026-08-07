"""Faz 2.9.5 -- Question Bank search, tagging, and difficulty
classification infrastructure.

Covers: category and difficulty filtering (Faz 2.9.2 regression --
unchanged, re-verified here rather than assumed), tag-based search
(``tags``/``tags_match``: "any" == OR, "all" == AND, case-insensitive
+ trimmed comparison), keyword search (whitespace-tokenized,
AND-across-tokens, case-insensitive, TR+EN combined), combination of
tag and keyword filters with each other and with every Faz 2.9.2/2.9.4
filter (category, difficulty, publishable_only, include_deleted,
include_archived), empty-tags/empty-keyword "no filtering" behaviour
(backward compatibility), ``select_questions`` passthrough, and the
HTTP API's new ``tags``/``tags_match``/``keyword`` query parameters.

Deliberately does NOT touch or expand the shipped 4-record demo
fixture (``backend/question_bank/data/question_bank.v1.json``) --
every test here uses its own isolated ``qb_store_path`` (same pattern
as ``tests/test_faz_2_9_2_question_bank_retrieval.py``).
"""

from __future__ import annotations

import pytest

from backend.app import conn
from backend.question_bank import retrieval, service, store
from backend.question_bank.errors import ContentNotFoundError
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
from backend.question_bank.transitions import ValidationStatus

# ---------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-SEARCH-00001",
        content_version=1,
        category=Category.TIGHTENING_TORQUE,
        subcategory=None,
        difficulty=Difficulty.BEGINNER,
        question_type=QuestionType.SINGLE_CHOICE,
        question_tr="Bu bir test sorusudur, en az on karakter.",
        question_en="This is a test question, at least ten characters.",
        options_tr=["A", "B", "C"],
        options_en=["A", "B", "C"],
        correct_answer=0,
        technical_explanation_tr="Bu açıklama en az yirmi karakter uzunluğundadır.",
        technical_explanation_en="This explanation must be at least twenty characters.",
        standard_reference=None,
        source_reference=SourceReference(
            source_type=SourceType.INTERNAL_ENGINE, description="test"
        ),
        source_locator=None,
        traceability_level=TraceabilityLevel.PROVISIONAL,
        tags=["test"],
        learning_objective="Test amaçlı öğrenme hedefi metni.",
        engineering_risk_level=EngineeringRiskLevel.LOW,
        is_active=True,
    )
    base.update(overrides)
    return QuestionRecord(**base)


def _allow_all(role: str, action: str) -> bool:
    return True


@pytest.fixture()
def qb_store_path(tmp_path, monkeypatch):
    path = tmp_path / "question_bank_search_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    with conn() as c:
        yield c


@pytest.fixture()
def unique_qid(request):
    import hashlib

    return "QB-SR-" + hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:14].upper()


def _register_with_status(c, path, record, status: ValidationStatus, actor="tester"):
    """Registers ``record``'s JSON content and drives its SQLite
    lifecycle row to ``status`` via legal transitions only. Identical
    helper to the one already established in
    ``tests/test_faz_2_9_2_question_bank_retrieval.py``."""
    store.save_question_content(record, path=path)
    service.register_question(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )
    if status == ValidationStatus.DRAFT:
        return
    service.submit_for_technical_review(
        c, question_id=record.question_id, content_version=record.content_version, actor=actor
    )
    if status == ValidationStatus.TECHNICAL_REVIEW:
        return
    if status == ValidationStatus.REJECTED:
        service.reject_question(
            c,
            question_id=record.question_id,
            content_version=record.content_version,
            actor=actor,
            actor_role="engineer",
            reason="Kaynak eksik, teknik olarak reddedildi.",
            authorize=_allow_all,
        )
        return
    service.validate_question(
        c,
        question_id=record.question_id,
        content_version=record.content_version,
        actor=actor,
        actor_role="engineer",
        reviewed_by="reviewer1",
        review_date="2026-08-07",
        authorize=_allow_all,
    )


def _register(c, path, record, actor="tester"):
    _register_with_status(c, path, record, ValidationStatus.VALIDATED, actor=actor)


# ---------------------------------------------------------------------
# 1. Category filtering (Faz 2.9.2 regression -- unchanged in Faz 2.9.5)
# ---------------------------------------------------------------------


def test_category_filter_still_works(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-CAT-00001", category=Category.TIGHTENING_TORQUE)
    r2 = _make_record(question_id="QB-SR-CAT-00002", category=Category.THREAD_GEOMETRY)
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.list_questions(db, category=Category.THREAD_GEOMETRY)
    ids = {r.question_id for r in results}
    assert "QB-SR-CAT-00002" in ids
    assert "QB-SR-CAT-00001" not in ids


def test_category_filter_combines_with_publishable_only(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-CAT-00003", category=Category.WASHERS)
    _register_with_status(db, qb_store_path, r1, ValidationStatus.DRAFT)

    results = retrieval.list_questions(db, category=Category.WASHERS, publishable_only=True)
    assert not any(r.question_id == "QB-SR-CAT-00003" for r in results)

    results_all = retrieval.list_questions(
        db, category=Category.WASHERS, publishable_only=False
    )
    assert any(r.question_id == "QB-SR-CAT-00003" for r in results_all)


# ---------------------------------------------------------------------
# 2. Difficulty filtering (Faz 2.9.2 regression -- unchanged in Faz 2.9.5)
# ---------------------------------------------------------------------


def test_difficulty_filter_still_works(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-DIF-00001", difficulty=Difficulty.BEGINNER)
    r2 = _make_record(question_id="QB-SR-DIF-00002", difficulty=Difficulty.EXPERT)
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.list_questions(db, difficulty=Difficulty.EXPERT)
    ids = {r.question_id for r in results}
    assert "QB-SR-DIF-00002" in ids
    assert "QB-SR-DIF-00001" not in ids


def test_category_and_difficulty_combine_with_and(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-CD-00001",
        category=Category.WASHERS,
        difficulty=Difficulty.EXPERT,
    )
    r2 = _make_record(
        question_id="QB-SR-CD-00002",
        category=Category.WASHERS,
        difficulty=Difficulty.BEGINNER,
    )
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.list_questions(
        db, category=Category.WASHERS, difficulty=Difficulty.EXPERT
    )
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-CD-00001"}


# ---------------------------------------------------------------------
# 3. Tag-based search: "any" (default, OR) semantics
# ---------------------------------------------------------------------


def test_tags_any_matches_at_least_one_shared_tag(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-TAG-00001", tags=["iso16047", "torque"])
    r2 = _make_record(question_id="QB-SR-TAG-00002", tags=["vdi2230"])
    r3 = _make_record(question_id="QB-SR-TAG-00003", tags=["friction"])
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)
    _register(db, qb_store_path, r3)

    results = retrieval.list_questions(db, tags=["torque", "vdi2230"])
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-TAG-00001", "QB-SR-TAG-00002"}


def test_tags_default_match_mode_is_any(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-TAG-00004", tags=["a", "b"])
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, tags=["b", "z"])
    assert any(r.question_id == "QB-SR-TAG-00004" for r in results)


# ---------------------------------------------------------------------
# 4. Tag-based search: "all" (AND) semantics
# ---------------------------------------------------------------------


def test_tags_all_requires_every_given_tag(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-TAG-00005", tags=["iso16047", "torque", "testing"])
    r2 = _make_record(question_id="QB-SR-TAG-00006", tags=["iso16047"])
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.list_questions(
        db, tags=["iso16047", "torque"], tags_match="all"
    )
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-TAG-00005"}


def test_tags_all_excludes_partial_match(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-TAG-00007", tags=["a"])
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, tags=["a", "b"], tags_match="all")
    assert not any(r.question_id == "QB-SR-TAG-00007" for r in results)


# ---------------------------------------------------------------------
# 5. Tag comparison: case-insensitive and trimmed
# ---------------------------------------------------------------------


def test_tag_comparison_is_case_insensitive(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-TAG-00008", tags=["ISO 16047"])
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, tags=["iso 16047"])
    assert any(r.question_id == "QB-SR-TAG-00008" for r in results)


def test_tag_comparison_is_trimmed(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-TAG-00009", tags=["  torque  "])
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, tags=["torque"])
    assert any(r.question_id == "QB-SR-TAG-00009" for r in results)

    results_all = retrieval.list_questions(db, tags=["  TORQUE  "], tags_match="all")
    assert any(r.question_id == "QB-SR-TAG-00009" for r in results_all)


# ---------------------------------------------------------------------
# 6. Tags filter: backward compatibility (None == no filtering)
# ---------------------------------------------------------------------


def test_tags_none_applies_no_filtering(db, qb_store_path, unique_qid):
    r1 = _make_record(question_id=unique_qid, tags=["whatever"])
    _register(db, qb_store_path, r1)

    with_tags_none = retrieval.list_questions(db, tags=None)
    assert any(r.question_id == unique_qid for r in with_tags_none)


def test_tags_empty_list_matches_nothing_extra_but_is_falsy_no_filter(db, qb_store_path):
    """An empty ``tags`` sequence is falsy, so ``_record_matches_tags``
    treats it identically to ``tags=None`` (no filtering) -- documented
    explicitly here since an empty list could otherwise be read either
    way ("no tags requested" vs "match nothing")."""
    r1 = _make_record(question_id="QB-SR-TAG-00010", tags=["x"])
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, tags=[])
    assert any(r.question_id == "QB-SR-TAG-00010" for r in results)


# ---------------------------------------------------------------------
# 7. Keyword search: single token, TR and EN
# ---------------------------------------------------------------------


def test_keyword_matches_turkish_question_text(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-KW-00001",
        question_tr="Sürtünme katsayısı nasıl hesaplanır, en az on karakter.",
    )
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, keyword="sürtünme")
    assert any(r.question_id == "QB-SR-KW-00001" for r in results)


def test_keyword_matches_english_question_text(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-KW-00002",
        question_en="How is the friction coefficient calculated in this case?",
    )
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, keyword="friction")
    assert any(r.question_id == "QB-SR-KW-00002" for r in results)


def test_keyword_search_reaches_both_languages_regardless_of_query_language(db, qb_store_path):
    """A question authored primarily in Turkish must still be
    reachable by an English-language keyword query, and vice versa --
    the required TR/EN compatibility guarantee."""
    r1 = _make_record(
        question_id="QB-SR-KW-00003",
        question_tr="Tork kontrolü ile sıkma işlemi nasıl yapılır?",
        question_en="How is tightening performed with torque control?",
    )
    _register(db, qb_store_path, r1)

    assert any(
        r.question_id == "QB-SR-KW-00003"
        for r in retrieval.list_questions(db, keyword="tork")
    )
    assert any(
        r.question_id == "QB-SR-KW-00003"
        for r in retrieval.list_questions(db, keyword="torque")
    )


def test_keyword_matches_tags_and_subcategory(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-KW-00004",
        subcategory="hidden-subcat-marker",
        tags=["distinctive-tag-marker"],
    )
    _register(db, qb_store_path, r1)

    assert any(
        r.question_id == "QB-SR-KW-00004"
        for r in retrieval.list_questions(db, keyword="hidden-subcat-marker")
    )
    assert any(
        r.question_id == "QB-SR-KW-00004"
        for r in retrieval.list_questions(db, keyword="distinctive-tag-marker")
    )


# ---------------------------------------------------------------------
# 8. Keyword search: case-insensitivity, including Turkish I/ı/İ/i
# ---------------------------------------------------------------------


def test_keyword_search_is_case_insensitive(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-KW-00005",
        question_en="This question discusses TORQUE control methods here.",
    )
    _register(db, qb_store_path, r1)

    for query in ("torque", "TORQUE", "Torque", "tOrQuE"):
        assert any(
            r.question_id == "QB-SR-KW-00005"
            for r in retrieval.list_questions(db, keyword=query)
        ), query


def test_keyword_search_turkish_dotted_i_case_folding(db, qb_store_path):
    """Python's locale-independent ``str.casefold()`` (not
    ``str.lower()``) is used specifically so this holds regardless of
    the host OS locale."""
    r1 = _make_record(
        question_id="QB-SR-KW-00006",
        question_tr="İşlem sırasında sıkma torku izlenmelidir, en az on karakter.",
    )
    _register(db, qb_store_path, r1)

    results_lower = retrieval.list_questions(db, keyword="işlem")
    results_upper = retrieval.list_questions(db, keyword="İŞLEM")
    assert any(r.question_id == "QB-SR-KW-00006" for r in results_lower)
    assert any(r.question_id == "QB-SR-KW-00006" for r in results_upper)


# ---------------------------------------------------------------------
# 9. Keyword search: multi-word AND-across-tokens
# ---------------------------------------------------------------------


def test_keyword_multi_word_requires_all_tokens(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-KW-00007",
        question_en="ISO 16047 defines a torque-preload-friction test method.",
    )
    r2 = _make_record(
        question_id="QB-SR-KW-00008",
        question_en="ISO 2320 covers prevailing torque nuts specifically.",
    )
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.list_questions(db, keyword="iso 16047")
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-KW-00007"}


def test_keyword_multi_word_no_match_when_one_token_missing(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-KW-00009",
        question_en="This text mentions torque but not the other word.",
    )
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, keyword="torque nonexistentword12345")
    assert not any(r.question_id == "QB-SR-KW-00009" for r in results)


# ---------------------------------------------------------------------
# 10. Keyword search: backward compatibility (None/empty == no filtering)
# ---------------------------------------------------------------------


def test_keyword_none_applies_no_filtering(db, qb_store_path, unique_qid):
    r1 = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, keyword=None)
    assert any(r.question_id == unique_qid for r in results)


def test_keyword_empty_string_applies_no_filtering(db, qb_store_path, unique_qid):
    r1 = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, r1)

    results = retrieval.list_questions(db, keyword="   ")
    assert any(r.question_id == unique_qid for r in results)


# ---------------------------------------------------------------------
# 11. Tags and keyword combine with each other and with existing filters
# ---------------------------------------------------------------------


def test_tags_and_keyword_combine_with_and(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-COMB-00001",
        tags=["iso16047"],
        question_en="This one mentions torque explicitly in its text.",
    )
    r2 = _make_record(
        question_id="QB-SR-COMB-00002",
        tags=["iso16047"],
        question_en="This one does not mention the target word at all.",
    )
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.list_questions(db, tags=["iso16047"], keyword="torque")
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-COMB-00001"}


def test_tags_keyword_category_difficulty_all_combine(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-COMB-00003",
        category=Category.WASHERS,
        difficulty=Difficulty.EXPERT,
        tags=["special"],
        question_en="A unique marker phrase appears in this question text.",
    )
    r2 = _make_record(
        question_id="QB-SR-COMB-00004",
        category=Category.WASHERS,
        difficulty=Difficulty.BEGINNER,
        tags=["special"],
        question_en="A unique marker phrase appears in this question text.",
    )
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.list_questions(
        db,
        category=Category.WASHERS,
        difficulty=Difficulty.EXPERT,
        tags=["special"],
        keyword="unique marker phrase",
    )
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-COMB-00003"}


def test_search_filters_respect_publishable_only_default(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-COMB-00005",
        tags=["draftonly"],
        question_en="This draft question mentions a searchable marker.",
    )
    _register_with_status(db, qb_store_path, r1, ValidationStatus.DRAFT)

    default_results = retrieval.list_questions(db, tags=["draftonly"])
    assert not any(r.question_id == "QB-SR-COMB-00005" for r in default_results)

    unrestricted_results = retrieval.list_questions(
        db, tags=["draftonly"], publishable_only=False
    )
    assert any(r.question_id == "QB-SR-COMB-00005" for r in unrestricted_results)


def test_search_filters_respect_include_deleted_default(db, qb_store_path, unique_qid):
    r1 = _make_record(
        question_id=unique_qid,
        tags=["deletedmarker"],
        question_en="This question will be soft-deleted after registration.",
    )
    _register(db, qb_store_path, r1)
    service.delete_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    default_results = retrieval.list_questions(
        db, tags=["deletedmarker"], publishable_only=False
    )
    assert not any(r.question_id == unique_qid for r in default_results)

    included_results = retrieval.list_questions(
        db, tags=["deletedmarker"], publishable_only=False, include_deleted=True
    )
    assert any(r.question_id == unique_qid for r in included_results)


def test_search_filters_respect_include_archived_default(db, qb_store_path, unique_qid):
    r1 = _make_record(
        question_id=unique_qid,
        question_en="This question will be archived after registration for search testing.",
    )
    _register(db, qb_store_path, r1)
    service.archive_question(
        db, question_id=unique_qid, actor="t", actor_role="admin", authorize=_allow_all
    )

    default_results = retrieval.list_questions(
        db, keyword="archived after registration", publishable_only=False
    )
    assert not any(r.question_id == unique_qid for r in default_results)

    included_results = retrieval.list_questions(
        db, keyword="archived after registration", publishable_only=False, include_archived=True
    )
    assert any(r.question_id == unique_qid for r in included_results)


# ---------------------------------------------------------------------
# 12. select_questions passthrough
# ---------------------------------------------------------------------


def test_select_questions_passes_through_tags(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-SEL-00001", tags=["selectme"])
    r2 = _make_record(question_id="QB-SR-SEL-00002", tags=["other"])
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.select_questions(db, count=10, seed=1, tags=["selectme"])
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-SEL-00001"}


def test_select_questions_passes_through_keyword(db, qb_store_path):
    r1 = _make_record(
        question_id="QB-SR-SEL-00003",
        question_en="This carries a very distinctive select-target phrase.",
    )
    r2 = _make_record(question_id="QB-SR-SEL-00004")
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.select_questions(db, count=10, seed=1, keyword="select-target")
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-SEL-00003"}


def test_select_questions_passes_through_tags_match_all(db, qb_store_path):
    r1 = _make_record(question_id="QB-SR-SEL-00005", tags=["p", "q"])
    r2 = _make_record(question_id="QB-SR-SEL-00006", tags=["p"])
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    results = retrieval.select_questions(
        db, count=10, seed=1, tags=["p", "q"], tags_match="all"
    )
    ids = {r.question_id for r in results}
    assert ids == {"QB-SR-SEL-00005"}


# ---------------------------------------------------------------------
# 13. get_question is unaffected (search params are list-only)
# ---------------------------------------------------------------------


def test_get_question_signature_unaffected(db, qb_store_path, unique_qid):
    r1 = _make_record(question_id=unique_qid)
    _register(db, qb_store_path, r1)

    record = retrieval.get_question(db, unique_qid)
    assert record.question_id == unique_qid


def test_get_question_still_raises_not_found_for_unknown_id(db):
    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, "QB-SR-DOES-NOT-EXIST")


# ---------------------------------------------------------------------
# 14. HTTP API
# ---------------------------------------------------------------------


def test_api_list_questions_filters_by_tags(client, auth_headers, db, qb_store_path):
    r1 = _make_record(question_id="QB-API-SR-TAG-00001", tags=["api-tag-marker"])
    r2 = _make_record(question_id="QB-API-SR-TAG-00002", tags=["other-tag"])
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    r = client.get(
        "/api/question-bank/questions",
        params={"tags": "api-tag-marker", "publishable_only": "false"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ids = {q["question_id"] for q in r.json()}
    assert "QB-API-SR-TAG-00001" in ids
    assert "QB-API-SR-TAG-00002" not in ids


def test_api_list_questions_tags_match_all(client, auth_headers, db, qb_store_path):
    r1 = _make_record(question_id="QB-API-SR-TAG-00003", tags=["alpha", "beta"])
    r2 = _make_record(question_id="QB-API-SR-TAG-00004", tags=["alpha"])
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    r = client.get(
        "/api/question-bank/questions",
        params=[
            ("tags", "alpha"),
            ("tags", "beta"),
            ("tags_match", "all"),
            ("publishable_only", "false"),
        ],
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ids = {q["question_id"] for q in r.json()}
    assert "QB-API-SR-TAG-00003" in ids
    assert "QB-API-SR-TAG-00004" not in ids


def test_api_list_questions_filters_by_keyword(client, auth_headers, db, qb_store_path):
    r1 = _make_record(
        question_id="QB-API-SR-KW-00001",
        question_en="This api-level test contains a very distinctive phrase.",
    )
    r2 = _make_record(question_id="QB-API-SR-KW-00002")
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    r = client.get(
        "/api/question-bank/questions",
        params={"keyword": "distinctive phrase", "publishable_only": "false"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ids = {q["question_id"] for q in r.json()}
    assert ids == {"QB-API-SR-KW-00001"}


def test_api_select_questions_filters_by_tags_and_keyword(
    client, auth_headers, db, qb_store_path
):
    r1 = _make_record(
        question_id="QB-API-SR-SEL-00001",
        tags=["select-api-marker"],
        question_en="This has the target select word present here.",
    )
    r2 = _make_record(question_id="QB-API-SR-SEL-00002", tags=["select-api-marker"])
    _register(db, qb_store_path, r1)
    _register(db, qb_store_path, r2)

    r = client.get(
        "/api/question-bank/questions/select",
        params={
            "count": 10,
            "seed": 1,
            "tags": "select-api-marker",
            "keyword": "target select word",
            "publishable_only": "false",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ids = {q["question_id"] for q in r.json()}
    assert ids == {"QB-API-SR-SEL-00001"}


def test_api_list_questions_no_search_params_unaffected(
    client, auth_headers, db, qb_store_path
):
    """Backward compatibility: a request with none of the new Faz
    2.9.5 parameters behaves exactly as it did before this phase."""
    r1 = _make_record(question_id="QB-API-SR-BC-00001")
    _register(db, qb_store_path, r1)

    r = client.get(
        "/api/question-bank/questions",
        params={"publishable_only": "false"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert any(q["question_id"] == "QB-API-SR-BC-00001" for q in r.json())


def test_api_list_questions_invalid_tags_match_is_422(client, auth_headers):
    r = client.get(
        "/api/question-bank/questions",
        params={"tags_match": "bogus"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_api_get_question_route_unaffected_by_search_additions(
    client, auth_headers, db, qb_store_path
):
    r1 = _make_record(question_id="QB-API-SR-GET-00001")
    _register(db, qb_store_path, r1)

    r = client.get(
        "/api/question-bank/questions/QB-API-SR-GET-00001",
        params={"publishable_only": "false"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["question_id"] == "QB-API-SR-GET-00001"
