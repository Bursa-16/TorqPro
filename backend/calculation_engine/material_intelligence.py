"""TorqPro Calculation Engine - Material Intelligence and readiness-gated
material Recommendation Engine (Faz 2.8.8).

Built entirely on the 8 existing, real ``MaterialRecord`` entries
already served by ``backend.library.population.find_material()`` (see
``backend/library/data/material_library.json``). No new material
family, grade or property value is introduced here -- see
``docs/adr/ADR-0012-material-intelligence-formula-validation.md``.

Three capabilities:

1. **Requirement matching** (``match_materials``): deterministic
   numeric filter of the 8 records against a stated
   ``MaterialRequirement`` (``min_rp02_mpa`` / ``min_rm_mpa`` /
   ``min_elastic_modulus_mpa`` / ``material_family``) -- only fields
   the record actually carries; nothing invented.
2. **Descriptive comparison** (``compare_materials``): pairwise,
   non-judgemental comparison of two records' numeric properties.
3. **Readiness-gated recommendation** (``recommend_materials``):
   follows the Faz 2.6.4 philosophy exactly (see
   ``friction_recommendations.py``) -- a
   ``MaterialRecommendationResult`` always states its
   ``readiness_level`` and, if capped, exactly why. Today, every live
   record is uniformly ``validation_status="reference_only"`` /
   ``approval_status="pending"``, so the ceiling is
   ``comparison_only``: candidates meeting the requirement are ranked
   by deterministic numeric margin, but the result always carries a
   mandatory "engineering sign-off required" disclaimer and never
   claims ``engineering_recommendation_ready`` or
   ``production_recommendation_ready``.

Every new message in this module is defined as a ``(code, tr, en)``
triple in ``_MESSAGES`` and selected by an explicit ``lang`` argument
("tr" default, "en" accepted) -- never inferred. This is the TR/EN
fix Faz 2.6.8 documented as out of scope for itself (see
``frontend/index.html`` comment above ``fcRenderWarnings``); applied
here for all new content from day one, per the Faz 2.8.8 mandate.

**Advisory-layer boundary (mandatory, product-owner directive
2026-07-28):** this module is a strictly separate advisory layer. It
imports only ``backend.library.population`` (read-only data access)
and never imports ``backend.engineering_core``,
``backend.vdi2230_core``'s calculation surface,
``backend.calculation_engine.joint_analysis`` or
``.assembly_intelligence``. It computes no preload, torque, clamp
force, stiffness, load factor or safety factor, and it cannot -- by
construction -- mutate any engineering calculation, coefficient or
formula. It only consumes already-existing, already-validated library
records and produces advisory ranking/readiness output. Engineering
calculations remain the single source of truth; this module never
feeds back into them. See ``test_faz_2_8_8_material_intelligence.py::
TestAdvisoryLayerBoundary`` for the import-boundary assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.library import population

# -- Readiness levels (ordered, lowest to highest) --------------------
LEVEL_DATA_INSUFFICIENT = "data_insufficient"
LEVEL_COMPARISON_ONLY = "comparison_only"
LEVEL_ENGINEERING_RECOMMENDATION_READY = "engineering_recommendation_ready"
LEVEL_PRODUCTION_RECOMMENDATION_READY = "production_recommendation_ready"

_LEVEL_ORDER = (
    LEVEL_DATA_INSUFFICIENT,
    LEVEL_COMPARISON_ONLY,
    LEVEL_ENGINEERING_RECOMMENDATION_READY,
    LEVEL_PRODUCTION_RECOMMENDATION_READY,
)

CAPABILITY_REQUIREMENT_FILTER = "requirement_filter"
CAPABILITY_DESCRIPTIVE_COMPARISON = "descriptive_comparison"
CAPABILITY_QUANTITATIVE_RANKING = "quantitative_ranking"
CAPABILITY_ENGINEERING_RECOMMENDATION = "engineering_recommendation"
CAPABILITY_PRODUCTION_APPROVAL = "production_approval"

_ALL_CAPABILITIES = (
    CAPABILITY_REQUIREMENT_FILTER,
    CAPABILITY_DESCRIPTIVE_COMPARISON,
    CAPABILITY_QUANTITATIVE_RANKING,
    CAPABILITY_ENGINEERING_RECOMMENDATION,
    CAPABILITY_PRODUCTION_APPROVAL,
)

#: What each level unlocks, in addition to every lower level's set.
_LEVEL_CAPABILITIES = {
    LEVEL_DATA_INSUFFICIENT: (),
    LEVEL_COMPARISON_ONLY: (
        CAPABILITY_REQUIREMENT_FILTER,
        CAPABILITY_DESCRIPTIVE_COMPARISON,
        CAPABILITY_QUANTITATIVE_RANKING,
    ),
    LEVEL_ENGINEERING_RECOMMENDATION_READY: (CAPABILITY_ENGINEERING_RECOMMENDATION,),
    LEVEL_PRODUCTION_RECOMMENDATION_READY: (CAPABILITY_PRODUCTION_APPROVAL,),
}

#: Data that would need to change, per live record, to unlock a higher
#: level than comparison_only -- listed once so no call site invents
#: its own vocabulary (mirrors friction_recommendations.py).
_ENGINEERING_LEVEL_REQUIREMENTS = ("approval_status=approved",)
_PRODUCTION_LEVEL_REQUIREMENTS = (
    "lot_specific_certified_test_data",
    "independent_engineering_review_sign_off",
)


# -- Bilingual message catalogue --------------------------------------
# (code, tr, en) triples. Selected explicitly by `lang`, never
# inferred. New for Faz 2.8.8 -- see module docstring.
_MESSAGES: Dict[str, Dict[str, str]] = {
    "reference_only": {
        "tr": "Malzeme verisi referans amaçlıdır; parti/sertifika bazlı doğrulanmış veri değildir.",
        "en": "The material data is reference-only; it is not lot/certificate-verified data.",
    },
    "approval_pending": {
        "tr": (
            "Kayıt onay durumu \u201cbeklemede\u201d; üretim onayı için mühendislik "
            "incelemesi gereklidir."
        ),
        "en": (
            "The record's approval status is \u201cpending\u201d; engineering review is "
            "required for production approval."
        ),
    },
    "not_certificate_substitute": {
        "tr": (
            "Bu değerler bir malzeme sertifikasının yerini tutmaz; tedarikçiye, "
            "döküme ve ısıl işleme göre değişebilir."
        ),
        "en": (
            "These values are not a substitute for a material certificate; they vary "
            "by supplier, heat and treatment condition."
        ),
    },
    "sign_off_required": {
        "tr": "Üretimde kullanılmadan önce mühendislik onayı zorunludur.",
        "en": "Engineering sign-off is required before production use.",
    },
    "no_candidates": {
        "tr": "Belirtilen gereksinimi karşılayan malzeme kaydı bulunamadı.",
        "en": "No material record meets the stated requirement.",
    },
    "requirement_empty": {
        "tr": "Hiçbir sayısal gereksinim belirtilmedi; tüm kayıtlar aday olarak değerlendirildi.",
        "en": "No numeric requirement was stated; every record was considered a candidate.",
    },
}


def _msg(code: str, lang: str) -> str:
    entry = _MESSAGES[code]
    return entry.get(lang, entry["tr"])


def _normalize_lang(lang: Optional[str]) -> str:
    return "en" if (lang or "tr").strip().lower().startswith("en") else "tr"


# -- Data access (thin wrapper over population.find_material) ---------
def _all_material_records() -> List[Dict[str, Any]]:
    return population.find_material()


def get_material_record(material_id: str) -> Optional[Dict[str, Any]]:
    """Return the raw material record dict for ``material_id``, or
    ``None`` if not found. Case-sensitive on the stored ``id`` field,
    matching every other library accessor's convention."""
    for record in _all_material_records():
        if record.get("id") == material_id:
            return record
    return None


def list_materials() -> List[Dict[str, Any]]:
    """Return all 8 live material records, unmodified."""
    return list(_all_material_records())


# -- Requirement matching ----------------------------------------------
@dataclass(frozen=True)
class MaterialRequirement:
    """A stated, numeric joint/material requirement. Every field is
    optional -- an unset field applies no filter on that property,
    matching the "missing input makes the corresponding check not
    evaluable, never invents a default" convention already used by
    ``joint_analysis.py`` and ``assembly_intelligence.py``."""

    min_rp02_mpa: Optional[float] = None
    min_rm_mpa: Optional[float] = None
    min_elastic_modulus_mpa: Optional[float] = None
    material_family: Optional[str] = None


def _record_matches(record: Dict[str, Any], requirement: MaterialRequirement) -> bool:
    if requirement.min_rp02_mpa is not None:
        rp02 = record.get("rp02_mpa")
        if rp02 is None or rp02 < requirement.min_rp02_mpa:
            return False
    if requirement.min_rm_mpa is not None:
        rm = record.get("rm_mpa")
        if rm is None or rm < requirement.min_rm_mpa:
            return False
    if requirement.min_elastic_modulus_mpa is not None:
        e = record.get("elastic_modulus_mpa")
        if e is None or e < requirement.min_elastic_modulus_mpa:
            return False
    if requirement.material_family:
        needle = requirement.material_family.strip().lower()
        if needle not in str(record.get("material", "")).lower():
            return False
    return True


def match_materials(requirement: MaterialRequirement) -> List[Dict[str, Any]]:
    """Return the subset of live material records that satisfy every
    stated field of ``requirement``. An all-``None``/empty requirement
    matches every record."""
    return [r for r in _all_material_records() if _record_matches(r, requirement)]


# -- Descriptive comparison ---------------------------------------------
@dataclass(frozen=True)
class MaterialComparisonResult:
    """Purely descriptive, numeric comparison of two material records.
    States which record has the higher value per property -- this is
    a factual statement about the numbers, not an engineering
    judgement of which material is "better" (that judgement requires
    the full joint context this module does not have)."""

    material_id_a: str
    material_id_b: str
    rp02_relation: str
    rm_relation: str
    elastic_modulus_relation: str
    validation_status_a: str
    validation_status_b: str
    descriptive_statements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "material_id_a": self.material_id_a,
            "material_id_b": self.material_id_b,
            "rp02_relation": self.rp02_relation,
            "rm_relation": self.rm_relation,
            "elastic_modulus_relation": self.elastic_modulus_relation,
            "validation_status_a": self.validation_status_a,
            "validation_status_b": self.validation_status_b,
            "descriptive_statements": list(self.descriptive_statements),
        }


def _relation(value_a: Optional[float], value_b: Optional[float]) -> str:
    if value_a is None or value_b is None:
        return "not_comparable"
    if value_a > value_b:
        return "a_higher"
    if value_a < value_b:
        return "b_higher"
    return "equal"


def compare_materials(
    material_id_a: str, material_id_b: str, lang: Optional[str] = None
) -> MaterialComparisonResult:
    """Compare two material records by id. Raises ``KeyError`` if
    either id is unknown."""
    lang = _normalize_lang(lang)
    record_a = get_material_record(material_id_a)
    record_b = get_material_record(material_id_b)
    if record_a is None:
        raise KeyError(material_id_a)
    if record_b is None:
        raise KeyError(material_id_b)

    rp02_relation = _relation(record_a.get("rp02_mpa"), record_b.get("rp02_mpa"))
    rm_relation = _relation(record_a.get("rm_mpa"), record_b.get("rm_mpa"))
    e_relation = _relation(
        record_a.get("elastic_modulus_mpa"), record_b.get("elastic_modulus_mpa")
    )

    statements = [_msg("reference_only", lang), _msg("not_certificate_substitute", lang)]

    return MaterialComparisonResult(
        material_id_a=material_id_a,
        material_id_b=material_id_b,
        rp02_relation=rp02_relation,
        rm_relation=rm_relation,
        elastic_modulus_relation=e_relation,
        validation_status_a=str(record_a.get("validation_status", "")),
        validation_status_b=str(record_b.get("validation_status", "")),
        descriptive_statements=statements,
    )


# -- Readiness-gated recommendation -------------------------------------
@dataclass(frozen=True)
class MaterialRecommendationCandidate:
    material_id: str
    material: str
    grade: str
    rp02_mpa: Optional[float]
    rm_mpa: Optional[float]
    elastic_modulus_mpa: Optional[float]
    #: Deterministic margin above the strictest stated requirement,
    #: normalized as a ratio (candidate / required). ``None`` when no
    #: numeric requirement was stated (nothing to rank against).
    requirement_margin_ratio: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "material_id": self.material_id,
            "material": self.material,
            "grade": self.grade,
            "rp02_mpa": self.rp02_mpa,
            "rm_mpa": self.rm_mpa,
            "elastic_modulus_mpa": self.elastic_modulus_mpa,
            "requirement_margin_ratio": self.requirement_margin_ratio,
        }


@dataclass(frozen=True)
class MaterialRecommendationResult:
    """Readiness-gated recommendation report. Mirrors the shape of
    ``FrictionRecommendationResult`` (Faz 2.6.4) exactly, generalized
    to material data -- see module docstring."""

    recommendation_available: bool
    readiness_level: str
    available_capabilities: List[str]
    blocked_capabilities: List[str]
    blocking_reasons: List[str]
    engineering_warnings: List[str]
    required_missing_data: List[str]
    candidates: List[MaterialRecommendationCandidate]
    sign_off_notice: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_available": self.recommendation_available,
            "readiness_level": self.readiness_level,
            "available_capabilities": list(self.available_capabilities),
            "blocked_capabilities": list(self.blocked_capabilities),
            "blocking_reasons": list(self.blocking_reasons),
            "engineering_warnings": list(self.engineering_warnings),
            "required_missing_data": list(self.required_missing_data),
            "candidates": [c.to_dict() for c in self.candidates],
            "sign_off_notice": self.sign_off_notice,
        }


def _margin_ratio(record: Dict[str, Any], requirement: MaterialRequirement) -> Optional[float]:
    """Deterministic ranking key: the smallest (tightest) margin ratio
    across every stated numeric requirement field. ``None`` if no
    numeric requirement was stated."""
    ratios = []
    if requirement.min_rp02_mpa:
        rp02 = record.get("rp02_mpa")
        if rp02 is not None:
            ratios.append(rp02 / requirement.min_rp02_mpa)
    if requirement.min_rm_mpa:
        rm = record.get("rm_mpa")
        if rm is not None:
            ratios.append(rm / requirement.min_rm_mpa)
    if requirement.min_elastic_modulus_mpa:
        e = record.get("elastic_modulus_mpa")
        if e is not None:
            ratios.append(e / requirement.min_elastic_modulus_mpa)
    if not ratios:
        return None
    return min(ratios)


def recommend_materials(
    requirement: Optional[MaterialRequirement] = None, lang: Optional[str] = None
) -> MaterialRecommendationResult:
    """Readiness-gated material recommendation. Never guesses: if the
    requirement is unmatched or data does not support a higher level,
    the result says exactly why instead of producing a ranking it
    cannot support.
    """
    lang = _normalize_lang(lang)
    requirement = requirement or MaterialRequirement()

    all_records = _all_material_records()
    candidates_raw = match_materials(requirement)

    # -- Determine readiness level from the data itself (never from
    # the request) -- every live record is uniformly reference_only /
    # pending, so the ceiling is comparison_only. See ADR-0012 §2.
    statuses = {r.get("validation_status") for r in all_records}
    approvals = {r.get("approval_status") for r in all_records}
    all_reference_only = statuses == {"reference_only"}
    all_pending = approvals == {"pending"}

    if not all_records:
        level = LEVEL_DATA_INSUFFICIENT
    elif all_reference_only and all_pending:
        level = LEVEL_COMPARISON_ONLY
    elif all_reference_only or all_pending:
        # Mixed state not seen in current data, but handled
        # conservatively: still capped below engineering-ready.
        level = LEVEL_COMPARISON_ONLY
    else:
        level = LEVEL_ENGINEERING_RECOMMENDATION_READY

    available = set(_LEVEL_CAPABILITIES[LEVEL_DATA_INSUFFICIENT])
    for lvl in _LEVEL_ORDER:
        available |= set(_LEVEL_CAPABILITIES[lvl])
        if lvl == level:
            break
    blocked = [c for c in _ALL_CAPABILITIES if c not in available]

    blocking_reasons: List[str] = []
    required_missing: List[str] = []
    if level == LEVEL_DATA_INSUFFICIENT:
        blocking_reasons.append(_msg("no_candidates", lang))
    if level in (LEVEL_DATA_INSUFFICIENT, LEVEL_COMPARISON_ONLY):
        blocking_reasons.append(_msg("approval_pending", lang))
        required_missing.extend(_ENGINEERING_LEVEL_REQUIREMENTS)
        required_missing.extend(_PRODUCTION_LEVEL_REQUIREMENTS)

    warnings = [_msg("reference_only", lang), _msg("not_certificate_substitute", lang)]
    if requirement == MaterialRequirement():
        warnings.append(_msg("requirement_empty", lang))

    candidates: List[MaterialRecommendationCandidate] = []
    if level != LEVEL_DATA_INSUFFICIENT and candidates_raw:
        scored = [
            (
                _margin_ratio(r, requirement),
                MaterialRecommendationCandidate(
                    material_id=str(r.get("id", "")),
                    material=str(r.get("material", "")),
                    grade=str(r.get("grade", "")),
                    rp02_mpa=r.get("rp02_mpa"),
                    rm_mpa=r.get("rm_mpa"),
                    elastic_modulus_mpa=r.get("elastic_modulus_mpa"),
                    requirement_margin_ratio=(
                        None if _margin_ratio(r, requirement) is None else round(
                            _margin_ratio(r, requirement), 6
                        )
                    ),
                ),
            )
            for r in candidates_raw
        ]
        # Deterministic order: highest margin first (best-satisfying
        # candidate first); ties broken by material_id for stability.
        # Candidates with no numeric margin (no requirement stated)
        # keep source order.
        if any(m is not None for m, _ in scored):
            scored.sort(
                key=lambda pair: (
                    -(pair[0] if pair[0] is not None else float("-inf")),
                    pair[1].material_id,
                )
            )
        candidates = [c for _, c in scored]

    if not candidates_raw and all_records:
        blocking_reasons.append(_msg("no_candidates", lang))

    return MaterialRecommendationResult(
        recommendation_available=bool(candidates),
        readiness_level=level,
        available_capabilities=sorted(available),
        blocked_capabilities=blocked,
        blocking_reasons=blocking_reasons,
        engineering_warnings=warnings,
        required_missing_data=required_missing,
        candidates=candidates,
        sign_off_notice=_msg("sign_off_required", lang),
    )


__all__ = [
    "LEVEL_DATA_INSUFFICIENT",
    "LEVEL_COMPARISON_ONLY",
    "LEVEL_ENGINEERING_RECOMMENDATION_READY",
    "LEVEL_PRODUCTION_RECOMMENDATION_READY",
    "MaterialRequirement",
    "MaterialComparisonResult",
    "MaterialRecommendationCandidate",
    "MaterialRecommendationResult",
    "get_material_record",
    "list_materials",
    "match_materials",
    "compare_materials",
    "recommend_materials",
]
