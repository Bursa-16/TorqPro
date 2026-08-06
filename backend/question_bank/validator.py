"""Question Bank validation rules (Faz 2.9.1 foundation scope).

Structural shape lives in ``schema.py`` (Pydantic); this module holds
cross-field, cross-record and workflow rules that Pydantic alone
cannot express, following the existing project split between shape
and validation modules.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence

from .errors import QuestionBankValidationError
from .schema import QuestionRecord, SourceType
from .transitions import QUESTION_VALIDATION_TRANSITIONS, ValidationStatus, is_valid_transition

#: A standard whose real scope is a torque-preload-friction test
#: method (ISO 16047), not a thread-stripping/shear-area calculation
#: method. Faz 2.9.0's own constraint, made a concrete, checkable rule
#: here rather than left as prose. Kept as a small, explicit mapping
#: (not a general NLP/keyword classifier) so it stays auditable.
_ISO_16047_MISUSE_CATEGORIES = frozenset({"thread_stripping_and_shear_area"})
_ISO_16047_NAME_MARKERS = ("iso 16047", "iso16047")


def _is_iso_16047_reference(standard_name: str | None) -> bool:
    if not standard_name:
        return False
    lowered = standard_name.strip().lower()
    return any(marker in lowered for marker in _ISO_16047_NAME_MARKERS)


def validate_record_structure(record: QuestionRecord) -> List[str]:
    """Structural + content checks for a single content record.
    Returns a list of human-readable failure reasons (empty list ==
    valid). Never raises -- callers decide whether to raise
    :class:`QuestionBankValidationError`."""
    reasons: List[str] = []

    # Missing TR/EN question text or technical explanation is already
    # enforced by schema.py's min_length constraints at construction
    # time; re-checked here defensively in case a record was built
    # with model_construct() or loaded from a partially-trusted source.
    if not record.question_tr.strip():
        reasons.append("question_tr boş olamaz")
    if not record.question_en.strip():
        reasons.append("question_en boş olamaz")
    if not record.technical_explanation_tr.strip():
        reasons.append("technical_explanation_tr boş olamaz")
    if not record.technical_explanation_en.strip():
        reasons.append("technical_explanation_en boş olamaz")

    # TR/EN option-count parity.
    if (record.options_tr is None) != (record.options_en is None):
        reasons.append("options_tr ve options_en ikisi de dolu ya da ikisi de boş olmalı")
    elif record.options_tr is not None and record.options_en is not None:
        if len(record.options_tr) != len(record.options_en):
            reasons.append("options_tr ve options_en uzunlukları eşleşmiyor")
        # Empty option.
        for opt in (*record.options_tr, *record.options_en):
            if not opt.strip():
                reasons.append("boş seçenek tespit edildi")
                break
        # Duplicate option within the same language.
        if len(set(record.options_tr)) != len(record.options_tr):
            reasons.append("options_tr içinde tekrarlanan seçenek var")
        if len(set(record.options_en)) != len(record.options_en):
            reasons.append("options_en içinde tekrarlanan seçenek var")

    reasons.extend(_validate_correct_answer(record))

    # engineering_risk_level == high requires a source.
    if record.engineering_risk_level.value == "high":
        if record.standard_reference is None and record.source_reference is None:
            reasons.append(
                "engineering_risk_level='high' iken standard_reference veya "
                "source_reference dolu olmalı (kaynaksız teknik iddia)"
            )

    # oem_estimation source_type must not carry a standard_reference.
    if (
        record.source_reference is not None
        and record.source_reference.source_type == SourceType.OEM_ESTIMATION
        and record.standard_reference is not None
    ):
        reasons.append(
            "source_type='oem_estimation' iken standard_reference boş olmalı "
            "(OEM tahmini ile standart gerekliliğinin karıştırılması)"
        )

    # ISO 16047 scope-misuse guard.
    std_name = record.standard_reference.name if record.standard_reference else None
    if _is_iso_16047_reference(std_name) and record.category.value in _ISO_16047_MISUSE_CATEGORIES:
        reasons.append(
            "ISO 16047, tork-önyük-sürtünme test metodudur; "
            f"'{record.category.value}' kapsamında (diş sıyırma) referans olarak kullanılamaz"
        )

    if record.question_type.value == "numerical" and (
        record.tolerance is None or record.tolerance <= 0
    ):
        reasons.append("question_type='numerical' iken tolerance zorunlu ve > 0 olmalı")

    return reasons


def _validate_correct_answer(record: QuestionRecord) -> List[str]:
    reasons: List[str] = []
    qtype = record.question_type.value
    ca = record.correct_answer

    if qtype in ("single_choice", "formula_selection"):
        if not isinstance(ca, int) or isinstance(ca, bool):
            reasons.append(f"question_type='{qtype}' için correct_answer bir int (indeks) olmalı")
        elif record.options_tr is not None and not (0 <= ca < len(record.options_tr)):
            reasons.append("correct_answer indeksi options listesi sınırları dışında")
    elif qtype == "multiple_choice":
        if not isinstance(ca, list) or not all(isinstance(i, int) for i in ca):
            reasons.append("question_type='multiple_choice' için correct_answer bir int listesi olmalı")
        elif record.options_tr is not None:
            if any(not (0 <= i < len(record.options_tr)) for i in ca):
                reasons.append("correct_answer indekslerinden biri options listesi sınırları dışında")
            if len(set(ca)) != len(ca):
                reasons.append("correct_answer listesinde tekrarlanan indeks var")
    elif qtype == "true_false":
        if not isinstance(ca, bool):
            reasons.append("question_type='true_false' için correct_answer bool olmalı")
    elif qtype in ("numerical", "unit_conversion"):
        if isinstance(ca, bool) or not isinstance(ca, (int, float)):
            reasons.append(f"question_type='{qtype}' için correct_answer sayısal olmalı")

    return reasons


def find_duplicate_question_ids(records: Iterable[QuestionRecord]) -> List[str]:
    """Faz 2.9.0 Risk: aynı sorunun farklı kimliklerle değil, aynı
    kimlikle *birden fazla farklı content_version dışı* tekrar
    eklenmesi -- yani aynı ``question_id`` birden fazla kez, farklı
    ``content_version`` OLMADAN (ör. iki kez version=1) görülüyorsa bu
    bir hata. content_version farklıysa bu meşru bir revizyon
    zinciridir, çakışma değildir."""
    seen: dict[tuple[str, int], int] = {}
    duplicates: List[str] = []
    for r in records:
        key = (r.question_id, r.content_version)
        seen[key] = seen.get(key, 0) + 1
    for (qid, version), count in seen.items():
        if count > 1:
            duplicates.append(f"{qid}@v{version}")
    return duplicates


def validate_category(value: str) -> bool:
    from .schema import Category

    return value in {c.value for c in Category}


def validate_difficulty(value: str) -> bool:
    from .schema import Difficulty

    return value in {d.value for d in Difficulty}


def validate_question_type(value: str) -> bool:
    from .schema import QuestionType

    return value in {q.value for q in QuestionType}


def validate_traceability_level(value: str) -> bool:
    from .schema import TraceabilityLevel

    return value in {t.value for t in TraceabilityLevel}


def validate_revision_reason(revision_reason: str | None) -> List[str]:
    reasons: List[str] = []
    if revision_reason is None or len(revision_reason.strip()) < 20:
        reasons.append("revision_reason zorunlu ve trim sonrası en az 20 karakter olmalı")
    return reasons


def validate_transition_request(previous: str, new: str) -> List[str]:
    reasons: List[str] = []
    try:
        prev_status = ValidationStatus(previous)
        new_status = ValidationStatus(new)
    except ValueError:
        reasons.append(f"geçersiz durum: '{previous}' veya '{new}'")
        return reasons
    if not is_valid_transition(prev_status, new_status):
        reasons.append(f"geçersiz durum geçişi: '{previous}' -> '{new}'")
    return reasons


def validate_publishable(record: QuestionRecord, validation_status: str) -> bool:
    """A question is publishable (may appear in
    :func:`backend.question_bank.service.get_publishable_questions`'s
    result) if and only if its content marks it active *and* its
    SQLite-side lifecycle status is exactly ``validated``. A
    ``deprecated`` record is never publishable even if ``is_active``
    is still (stale) ``True`` in its JSON content -- the SQLite status
    is always authoritative for visibility, never the JSON content
    alone (Faz 2.9.0 Risk: "kullanıcıya doğrulanmamış soruların
    gösterilmesi")."""
    return bool(record.is_active) and validation_status == ValidationStatus.VALIDATED.value


def require_valid(record: QuestionRecord) -> None:
    reasons = validate_record_structure(record)
    if reasons:
        raise QuestionBankValidationError(reasons)
