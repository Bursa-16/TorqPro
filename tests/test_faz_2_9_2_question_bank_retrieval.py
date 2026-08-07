"""Faz 2.9.2 -- Question Bank retrieval, filtering, deterministic
selection, and the read-only HTTP API.

Covers: single-field filters (category/difficulty/question_type/
traceability_level/is_active/validation_status), combined filters,
publishable-only default and its reuse of the single authoritative
``validate_publishable`` rule (never a second definition), exclusion of
inactive/deprecated/unvalidated/unregistered questions from the
publishable set, empty results, deterministic same-seed selection,
different-seed variability, ``count`` edge cases (zero, larger than
result set), single-question retrieval (including 404 for both a truly
unknown ``question_id`` and a non-publishable one under the default),
and the HTTP routes' auth enforcement + response shape.

Deliberately does NOT touch or expand the shipped 4-record demo fixture
(``backend/question_bank/data/question_bank.v1.json``) -- every test
here uses its own isolated ``qb_store_path`` (same pattern as
``tests/test_faz_2_9_1_question_bank_foundation.py``).
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
# Fixtures
# ---------------------------------------------------------------------


def _make_record(**overrides) -> QuestionRecord:
    base = dict(
        question_id="QB-RETR-00001",
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
    """Isolated JSON content file per test -- never touches the real
    demo fixture shipped with the repo."""
    path = tmp_path / "question_bank_retrieval_test.json"
    monkeypatch.setattr(store, "DATA_PATH", path)
    return path


@pytest.fixture()
def db():
    with conn() as c:
        yield c


def _register_with_status(c, path, record, status: ValidationStatus, actor="tester"):
    """Registers ``record``'s JSON content and drives its SQLite
    lifecycle row to ``status`` via legal transitions only (never by
    writing SQLite state directly) -- draft -> technical_review ->
    validated -> deprecated, or draft -> technical_review -> rejected."""
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
    if status == ValidationStatus.VALIDATED:
        return
    if status == ValidationStatus.DEPRECATED:
        service.deprecate_question(
            c,
            question_id=record.question_id,
            content_version=record.content_version,
            actor=actor,
            actor_role="engineer",
            authorize=_allow_all,
        )
        return
    raise AssertionError(f"unsupported status in test helper: {status}")


@pytest.fixture()
def seeded_dataset(db, qb_store_path, request):
    """A deliberately varied, isolated dataset -- 9 records spanning
    every filter dimension and every lifecycle status, including one
    JSON-only record that is never registered in SQLite at all (no
    lifecycle row/status whatsoever).

    ``question_id``s are namespaced with a per-test-unique prefix
    (derived from the pytest node id) because the underlying SQLite
    database (``question_bank_records``) is the shared, session-scoped
    test DB from ``tests/conftest.py`` -- it is never reset between
    tests, so two tests reusing the exact same literal ``question_id``
    would collide against the store's own silent-overwrite/unique-
    constraint guard (a correctness guarantee this suite must not work
    around). Each test gets its own fully isolated ``(question_id,
    content_version)`` namespace instead, returned here keyed by a
    stable logical name so tests never need to know the generated
    prefix.
    """
    import hashlib

    # A short, collision-resistant hash of the full node id (not a
    # truncated slice of the test name) -- two test names that happen
    # to share a long common prefix must never collapse onto the same
    # SQLite (question_id, content_version) namespace.
    prefix = hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()[:12].upper()

    def qid(suffix: str) -> str:
        return f"QB-{prefix}-{suffix}"

    records = {}

    # Three VALIDATED + is_active=True TIGHTENING_TORQUE/BEGINNER/
    # SINGLE_CHOICE/APPROVED records -- the core publishable set used
    # for combined-filter and selection tests.
    for i in range(1, 4):
        r = _make_record(
            question_id=qid(f"PUB{i}"),
            content_version=1,
            category=Category.TIGHTENING_TORQUE,
            difficulty=Difficulty.BEGINNER,
            question_type=QuestionType.SINGLE_CHOICE,
            traceability_level=TraceabilityLevel.APPROVED,
            is_active=True,
        )
        _register_with_status(db, qb_store_path, r, ValidationStatus.VALIDATED)
        records[f"pub{i}"] = r

    # Same category, different difficulty, still publishable -- lets a
    # category-only filter and a difficulty-only filter disagree.
    r_intermediate = _make_record(
        question_id=qid("PUBINTERMEDIATE"),
        content_version=1,
        category=Category.TIGHTENING_TORQUE,
        difficulty=Difficulty.INTERMEDIATE,
        question_type=QuestionType.TRUE_FALSE,
        correct_answer=True,
        options_tr=None,
        options_en=None,
        traceability_level=TraceabilityLevel.PROVISIONAL,
        is_active=True,
    )
    _register_with_status(db, qb_store_path, r_intermediate, ValidationStatus.VALIDATED)
    records["pub_intermediate"] = r_intermediate

    # Different category, numerical type, EXPERIMENTAL traceability,
    # validated + active -- publishable, distinguishes question_type
    # and traceability_level filters from the core set above.
    r_numerical = _make_record(
        question_id=qid("PUBNUMERICAL"),
        content_version=1,
        category=Category.WASHERS,
        difficulty=Difficulty.ADVANCED,
        question_type=QuestionType.NUMERICAL,
        correct_answer=12.5,
        tolerance=0.5,
        options_tr=None,
        options_en=None,
        traceability_level=TraceabilityLevel.EXPERIMENTAL,
        is_active=True,
    )
    _register_with_status(db, qb_store_path, r_numerical, ValidationStatus.VALIDATED)
    records["pub_numerical"] = r_numerical

    # DRAFT status -- exists, but never publishable.
    r_draft = _make_record(
        question_id=qid("DRAFT"),
        content_version=1,
        category=Category.WASHERS,
        difficulty=Difficulty.BEGINNER,
        traceability_level=TraceabilityLevel.APPROVED,
        is_active=True,
    )
    _register_with_status(db, qb_store_path, r_draft, ValidationStatus.DRAFT)
    records["draft"] = r_draft

    # VALIDATED but is_active=False -- must be excluded from
    # publishable results despite a "validated" SQLite status.
    r_inactive = _make_record(
        question_id=qid("INACTIVE"),
        content_version=1,
        category=Category.VDI_2230_FUNDAMENTALS,
        difficulty=Difficulty.EXPERT,
        traceability_level=TraceabilityLevel.APPROVED,
        is_active=False,
    )
    _register_with_status(db, qb_store_path, r_inactive, ValidationStatus.VALIDATED)
    records["inactive"] = r_inactive

    # DEPRECATED, with is_active still (stale) True -- must be excluded
    # from publishable results; SQLite status is authoritative, not the
    # JSON content's is_active flag.
    r_deprecated = _make_record(
        question_id=qid("DEPRECATED"),
        content_version=1,
        category=Category.VDI_2230_FUNDAMENTALS,
        difficulty=Difficulty.EXPERT,
        traceability_level=TraceabilityLevel.APPROVED,
        is_active=True,
    )
    _register_with_status(db, qb_store_path, r_deprecated, ValidationStatus.DEPRECATED)
    records["deprecated"] = r_deprecated

    # REJECTED -- must be excluded from publishable results.
    r_rejected = _make_record(
        question_id=qid("REJECTED"),
        content_version=1,
        category=Category.THREAD_GEOMETRY,
        difficulty=Difficulty.INTERMEDIATE,
        question_type=QuestionType.MULTIPLE_CHOICE,
        correct_answer=[0, 2],
        traceability_level=TraceabilityLevel.PROVISIONAL,
        is_active=True,
    )
    _register_with_status(db, qb_store_path, r_rejected, ValidationStatus.REJECTED)
    records["rejected"] = r_rejected

    # JSON content exists but was never registered in SQLite at all --
    # no lifecycle row, no validation_status whatsoever.
    r_unregistered = _make_record(
        question_id=qid("UNREGISTERED"),
        content_version=1,
        category=Category.ISO_16047_TESTING,
        difficulty=Difficulty.INTERMEDIATE,
        traceability_level=TraceabilityLevel.APPROVED,
        is_active=True,
    )
    store.save_question_content(r_unregistered, path=qb_store_path)
    records["unregistered"] = r_unregistered

    return records


# ---------------------------------------------------------------------
# 1. Individual filters
# ---------------------------------------------------------------------


def test_filter_by_category(db, seeded_dataset):
    results = retrieval.list_questions(
        db, category=Category.WASHERS, publishable_only=False
    )
    ids = {r.question_id for r in results}
    assert ids == {
        seeded_dataset["pub_numerical"].question_id,
        seeded_dataset["draft"].question_id,
    }


def test_filter_by_difficulty(db, seeded_dataset):
    results = retrieval.list_questions(
        db, difficulty=Difficulty.EXPERT, publishable_only=False
    )
    ids = {r.question_id for r in results}
    assert ids == {
        seeded_dataset["inactive"].question_id,
        seeded_dataset["deprecated"].question_id,
    }


def test_filter_by_question_type(db, seeded_dataset):
    results = retrieval.list_questions(
        db, question_type=QuestionType.NUMERICAL, publishable_only=False
    )
    ids = {r.question_id for r in results}
    assert ids == {seeded_dataset["pub_numerical"].question_id}


def test_filter_by_traceability_level(db, seeded_dataset):
    results = retrieval.list_questions(
        db, traceability_level=TraceabilityLevel.EXPERIMENTAL, publishable_only=False
    )
    ids = {r.question_id for r in results}
    assert ids == {seeded_dataset["pub_numerical"].question_id}


def test_filter_by_is_active(db, seeded_dataset):
    results = retrieval.list_questions(db, is_active=False, publishable_only=False)
    ids = {r.question_id for r in results}
    assert ids == {seeded_dataset["inactive"].question_id}


def test_filter_by_validation_status(db, seeded_dataset):
    results = retrieval.list_questions(
        db, validation_status=ValidationStatus.REJECTED, publishable_only=False
    )
    ids = {r.question_id for r in results}
    assert ids == {seeded_dataset["rejected"].question_id}


def test_validation_status_filter_excludes_unregistered(db, seeded_dataset):
    # An unregistered record has no status at all, so it can never
    # match any explicit validation_status filter value.
    unregistered_id = seeded_dataset["unregistered"].question_id
    for status in ValidationStatus:
        results = retrieval.list_questions(
            db, validation_status=status, publishable_only=False
        )
        assert all(r.question_id != unregistered_id for r in results)


# ---------------------------------------------------------------------
# 2. Combined filters
# ---------------------------------------------------------------------


def test_combined_filters_narrow_correctly(db, seeded_dataset):
    results = retrieval.list_questions(
        db,
        category=Category.TIGHTENING_TORQUE,
        difficulty=Difficulty.BEGINNER,
        publishable_only=True,
    )
    ids = {r.question_id for r in results}
    assert ids == {
        seeded_dataset["pub1"].question_id,
        seeded_dataset["pub2"].question_id,
        seeded_dataset["pub3"].question_id,
    }


def test_combined_filters_category_and_difficulty_disagree(db, seeded_dataset):
    # Same category as the core set, different difficulty -- combined
    # filter must require BOTH to match, not either.
    results = retrieval.list_questions(
        db,
        category=Category.TIGHTENING_TORQUE,
        difficulty=Difficulty.ADVANCED,
        publishable_only=False,
    )
    assert results == []


def test_combined_filters_five_dimensions(db, seeded_dataset):
    results = retrieval.list_questions(
        db,
        category=Category.WASHERS,
        difficulty=Difficulty.ADVANCED,
        question_type=QuestionType.NUMERICAL,
        traceability_level=TraceabilityLevel.EXPERIMENTAL,
        is_active=True,
        publishable_only=True,
    )
    ids = {r.question_id for r in results}
    assert ids == {seeded_dataset["pub_numerical"].question_id}


# ---------------------------------------------------------------------
# 3. Publishable-only default and exclusions (reuses validate_publishable)
# ---------------------------------------------------------------------


def test_publishable_only_is_the_default(db, seeded_dataset):
    default_results = retrieval.list_questions(db)
    explicit_results = retrieval.list_questions(db, publishable_only=True)
    assert {r.question_id for r in default_results} == {
        r.question_id for r in explicit_results
    }


def test_publishable_only_reuses_the_single_authoritative_rule(db, seeded_dataset):
    """No second definition of 'publishable' -- every record returned
    by list_questions(publishable_only=True) must independently satisfy
    backend.question_bank.validator.validate_publishable, and every
    record NOT returned must fail it."""
    from backend.question_bank.validator import validate_publishable

    status_map = retrieval._status_map(db)
    all_records = store.load_all_question_content()
    returned_ids = {
        r.question_id for r in retrieval.list_questions(db, publishable_only=True)
    }
    for record in all_records:
        status = status_map.get((record.question_id, record.content_version)) or ""
        expected = validate_publishable(record, status)
        assert (record.question_id in returned_ids) == expected


def test_draft_excluded_from_publishable(db, seeded_dataset):
    results = retrieval.list_questions(db, publishable_only=True)
    assert all(r.question_id != seeded_dataset["draft"].question_id for r in results)


def test_inactive_excluded_from_publishable_even_if_validated(db, seeded_dataset):
    results = retrieval.list_questions(db, publishable_only=True)
    assert all(r.question_id != seeded_dataset["inactive"].question_id for r in results)


def test_deprecated_excluded_from_publishable_even_if_stale_active(db, seeded_dataset):
    results = retrieval.list_questions(db, publishable_only=True)
    assert all(r.question_id != seeded_dataset["deprecated"].question_id for r in results)


def test_rejected_excluded_from_publishable(db, seeded_dataset):
    results = retrieval.list_questions(db, publishable_only=True)
    assert all(r.question_id != seeded_dataset["rejected"].question_id for r in results)


def test_unregistered_excluded_from_publishable(db, seeded_dataset):
    results = retrieval.list_questions(db, publishable_only=True)
    assert all(r.question_id != seeded_dataset["unregistered"].question_id for r in results)


# ---------------------------------------------------------------------
# 4. Empty results
# ---------------------------------------------------------------------


def test_no_match_returns_empty_list(db, seeded_dataset):
    results = retrieval.list_questions(
        db, category=Category.SELF_LOOSENING, publishable_only=False
    )
    assert results == []


def test_empty_store_returns_empty_list(db, qb_store_path):
    # No seeded_dataset here -- a genuinely empty JSON content store.
    assert retrieval.list_questions(db, publishable_only=False) == []
    assert retrieval.list_questions(db, publishable_only=True) == []


# ---------------------------------------------------------------------
# 5. Deterministic selection
# ---------------------------------------------------------------------


def test_same_seed_same_ordered_result(db, seeded_dataset):
    first = retrieval.select_questions(
        db, count=3, seed=42, category=Category.TIGHTENING_TORQUE, publishable_only=True
    )
    second = retrieval.select_questions(
        db, count=3, seed=42, category=Category.TIGHTENING_TORQUE, publishable_only=True
    )
    assert [r.question_id for r in first] == [r.question_id for r in second]


def test_different_seed_is_valid_and_may_differ(db, seeded_dataset):
    candidates = retrieval.list_questions(
        db, category=Category.TIGHTENING_TORQUE, publishable_only=True
    )
    candidate_ids = {r.question_id for r in candidates}

    a = retrieval.select_questions(
        db, count=len(candidates), seed=1, category=Category.TIGHTENING_TORQUE,
        publishable_only=True,
    )
    b = retrieval.select_questions(
        db, count=len(candidates), seed=2, category=Category.TIGHTENING_TORQUE,
        publishable_only=True,
    )
    # Both are valid (well-formed) selections over the same candidate pool.
    assert {r.question_id for r in a} == candidate_ids
    assert {r.question_id for r in b} == candidate_ids
    # The two seeds are not required to differ in order, but with >=4
    # candidates and two distinct seeds this dataset's actual orderings
    # do differ -- asserted directly rather than assumed.
    assert [r.question_id for r in a] != [r.question_id for r in b]


def test_selection_seed_is_required_keyword(db, seeded_dataset):
    with pytest.raises(TypeError):
        retrieval.select_questions(db, count=2)  # no seed supplied


def test_selection_only_returns_publishable_candidates_by_default(db, seeded_dataset):
    results = retrieval.select_questions(db, count=50, seed=7)
    ids = {r.question_id for r in results}
    for key in ("draft", "inactive", "deprecated", "rejected", "unregistered"):
        assert seeded_dataset[key].question_id not in ids


# ---------------------------------------------------------------------
# 6. count edge cases
# ---------------------------------------------------------------------


def test_count_zero_returns_empty_list(db, seeded_dataset):
    results = retrieval.select_questions(
        db, count=0, seed=1, category=Category.TIGHTENING_TORQUE, publishable_only=True
    )
    assert results == []


def test_count_larger_than_result_set_returns_all_without_error(db, seeded_dataset):
    candidates = retrieval.list_questions(
        db, category=Category.TIGHTENING_TORQUE, publishable_only=True
    )
    results = retrieval.select_questions(
        db,
        count=len(candidates) + 100,
        seed=1,
        category=Category.TIGHTENING_TORQUE,
        publishable_only=True,
    )
    assert len(results) == len(candidates)
    assert {r.question_id for r in results} == {r.question_id for r in candidates}


def test_negative_count_raises(db, seeded_dataset):
    with pytest.raises(ValueError):
        retrieval.select_questions(db, count=-1, seed=1)


# ---------------------------------------------------------------------
# 7. Single-question retrieval
# ---------------------------------------------------------------------


def test_get_publishable_question_by_id(db, seeded_dataset):
    pub1_id = seeded_dataset["pub1"].question_id
    record = retrieval.get_question(db, pub1_id)
    assert record.question_id == pub1_id


def test_get_question_unknown_id_raises_not_found(db, seeded_dataset):
    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, "QB-DOES-NOT-EXIST-AT-ALL")


def test_get_question_non_publishable_raises_not_found_by_default(db, seeded_dataset):
    # Exists (it's a real DRAFT record) but is not publishable -- the
    # default (publishable_only=True) must raise the SAME error type as
    # a genuinely unknown question_id, never leak its existence.
    draft_id = seeded_dataset["draft"].question_id
    with pytest.raises(ContentNotFoundError):
        retrieval.get_question(db, draft_id)


def test_get_question_non_publishable_visible_when_explicitly_requested(db, seeded_dataset):
    draft_id = seeded_dataset["draft"].question_id
    record = retrieval.get_question(db, draft_id, publishable_only=False)
    assert record.question_id == draft_id


# ---------------------------------------------------------------------
# 8. HTTP API -- auth, response shape, routing
# ---------------------------------------------------------------------


def test_api_requires_authentication(client):
    r = client.get("/api/question-bank/questions")
    assert r.status_code == 401


def test_api_list_questions_response_shape(client, auth_headers, seeded_dataset):
    pub1_id = seeded_dataset["pub1"].question_id
    draft_id = seeded_dataset["draft"].question_id
    r = client.get("/api/question-bank/questions", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    ids = {item["question_id"] for item in body}
    assert pub1_id in ids
    assert draft_id not in ids
    sample = next(item for item in body if item["question_id"] == pub1_id)
    assert sample["category"] == "tightening_torque"
    assert sample["difficulty"] == "beginner"
    assert sample["is_active"] is True


def test_api_list_questions_with_filters(client, auth_headers, seeded_dataset):
    r = client.get(
        "/api/question-bank/questions",
        params={"category": "washers", "publishable_only": "false"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    ids = {item["question_id"] for item in r.json()}
    assert ids == {
        seeded_dataset["pub_numerical"].question_id,
        seeded_dataset["draft"].question_id,
    }


def test_api_get_question_by_id(client, auth_headers, seeded_dataset):
    pub1_id = seeded_dataset["pub1"].question_id
    r = client.get(
        f"/api/question-bank/questions/{pub1_id}", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["question_id"] == pub1_id


def test_api_get_question_unknown_id_is_404(client, auth_headers, seeded_dataset):
    r = client.get(
        "/api/question-bank/questions/QB-DOES-NOT-EXIST-AT-ALL", headers=auth_headers
    )
    assert r.status_code == 404


def test_api_get_question_non_publishable_is_404_by_default(client, auth_headers, seeded_dataset):
    draft_id = seeded_dataset["draft"].question_id
    r = client.get(
        f"/api/question-bank/questions/{draft_id}", headers=auth_headers
    )
    assert r.status_code == 404


def test_api_select_route_is_not_shadowed_by_question_id_route(
    client, auth_headers, seeded_dataset
):
    # If routing order were wrong, "select" would be captured as a
    # question_id path parameter and this would 404 instead of 200.
    r = client.get(
        "/api/question-bank/questions/select",
        params={"count": 2, "seed": 5, "category": "tightening_torque"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2


def test_api_select_same_seed_same_order(client, auth_headers, seeded_dataset):
    params = {"count": 3, "seed": 99, "category": "tightening_torque"}
    r1 = client.get("/api/question-bank/questions/select", params=params, headers=auth_headers)
    r2 = client.get("/api/question-bank/questions/select", params=params, headers=auth_headers)
    assert r1.status_code == r2.status_code == 200
    ids1 = [item["question_id"] for item in r1.json()]
    ids2 = [item["question_id"] for item in r2.json()]
    assert ids1 == ids2


def test_api_select_missing_seed_is_422(client, auth_headers, seeded_dataset):
    r = client.get(
        "/api/question-bank/questions/select",
        params={"count": 2},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_api_select_negative_count_is_422(client, auth_headers, seeded_dataset):
    r = client.get(
        "/api/question-bank/questions/select",
        params={"count": -1, "seed": 1},
        headers=auth_headers,
    )
    assert r.status_code == 422
