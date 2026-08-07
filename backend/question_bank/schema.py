"""Question Bank canonical content schema (Pydantic).

Structural shape only -- cross-field and cross-record business rules
(duplicate detection, TR/EN parity, correct-answer consistency,
publishable-state checks, etc.) live in
:mod:`backend.question_bank.validator`, not here, matching the
project's existing split between ``schemas.py`` (shape) and
``validation.py``/``*_validator.py`` (rules) used throughout
``backend/production_validation`` and ``backend/library``.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# Faz 2.9.0's traceability-level design decision was to align with,
# not duplicate, the five-value confidence vocabulary already proven
# out in backend.engineering_core.trace (itself reusing APPROVED /
# PROVISIONAL from backend.vdi2230_core.trace). We import the actual
# values rather than re-declaring the strings.
from backend.engineering_core.trace import VALID_STATUSES as _ENGINEERING_CORE_TRACE_STATUSES


class TraceabilityLevel(str, Enum):
    """Reuses backend.engineering_core.trace's five-value vocabulary
    verbatim (APPROVED/PROVISIONAL/EXPERIMENTAL/DEPRECATED/UNVERIFIED).
    Not a re-definition: values are asserted equal to the source of
    truth at import time (see the assertion below), so a future change
    to engineering_core.trace's vocabulary cannot silently diverge
    from this enum without breaking an import-time check."""

    APPROVED = "APPROVED"
    PROVISIONAL = "PROVISIONAL"
    EXPERIMENTAL = "EXPERIMENTAL"
    DEPRECATED = "DEPRECATED"
    UNVERIFIED = "UNVERIFIED"


assert {m.value for m in TraceabilityLevel} == set(_ENGINEERING_CORE_TRACE_STATUSES), (
    "TraceabilityLevel has drifted from backend.engineering_core.trace.VALID_STATUSES "
    "-- update this enum to match, do not fork the vocabulary."
)


class Category(str, Enum):
    """Faz 2.9.0 Sec. 3's 30-category scope. Closed set -- an unlisted
    category is a structural validation failure, not a free-text
    value (ADR-0014 "closed vocabulary" principle applied here)."""

    FASTENER_FUNDAMENTALS = "fastener_fundamentals"
    BOLT_NUT_IDENTIFICATION = "bolt_and_nut_identification"
    STRENGTH_CLASSES = "strength_classes"
    PRELOAD_CLAMP_FORCE = "preload_and_clamp_force"
    TIGHTENING_TORQUE = "tightening_torque"
    FRICTION_LUBRICATION = "friction_and_lubrication"
    TORQUE_TENSION_RELATIONSHIP = "torque_tension_relationship"
    VDI_2230_FUNDAMENTALS = "vdi_2230_fundamentals"
    ISO_16047_TESTING = "iso_16047_testing"
    ISO_2320_PREVAILING_TORQUE_NUTS = "iso_2320_prevailing_torque_nuts"
    THREAD_GEOMETRY = "thread_geometry"
    THREAD_STRIPPING_SHEAR_AREA = "thread_stripping_and_shear_area"
    JOINT_STIFFNESS = "joint_stiffness"
    LOAD_DISTRIBUTION = "load_distribution"
    EMBEDDING_SETTLEMENT = "embedding_and_settlement"
    SELF_LOOSENING = "self_loosening"
    FATIGUE_DYNAMIC_LOADING = "fatigue_and_dynamic_loading"
    WASHERS = "washers"
    LOCKING_METHODS = "locking_methods"
    SURFACE_COATINGS = "surface_coatings"
    TIGHTENING_TOOLS = "tightening_tools"
    TORQUE_CONTROL = "torque_control"
    ANGLE_CONTROLLED_TIGHTENING = "angle_controlled_tightening"
    YIELD_CONTROLLED_TIGHTENING = "yield_controlled_tightening"
    PROCESS_CAPABILITY = "process_capability"
    PP_PPK_CP_CPK = "pp_ppk_cp_cpk"
    MEASUREMENT_CALIBRATION = "measurement_and_calibration"
    FAILURE_ANALYSIS = "failure_analysis"
    PRACTICAL_ASSEMBLY_CASES = "practical_assembly_cases"
    OEM_GENERAL_ESTIMATION_METHODS = "oem_general_estimation_methods"


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class QuestionType(str, Enum):
    """Faz 2.9.1 foundation supports the v1-core subset from Faz
    2.9.0 Sec. 5. Scenario-based, error-analysis, standard-interpretation
    and visual/diagram types remain deferred (Faz 2.9.0 Sec. 5) and are
    intentionally not enum members yet -- adding them later is
    additive, not a breaking schema change."""

    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    NUMERICAL = "numerical"
    UNIT_CONVERSION = "unit_conversion"
    FORMULA_SELECTION = "formula_selection"


class SourceType(str, Enum):
    """Faz 2.9.0 Sec. 6's five-way source-of-truth split. Mutually
    exclusive with a populated ``standard_reference`` when
    ``OEM_ESTIMATION`` (enforced in validator.py, not here)."""

    STANDARD_REQUIREMENT = "standard_requirement"
    ENGINEERING_INTERPRETATION = "engineering_interpretation"
    INTERNAL_ENGINE = "internal_engine"
    OEM_ESTIMATION = "oem_estimation"
    EDUCATIONAL_SIMPLIFICATION = "educational_simplification"


class EngineeringRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StandardReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    edition_or_year: Optional[str] = None
    clause_or_table: Optional[str] = None


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    description: str = Field(min_length=1)


class QuestionRecord(BaseModel):
    """One canonical content snapshot for one ``(question_id,
    content_version)`` pair. Immutable once written -- a content
    change always means a *new* ``content_version``, never an edit in
    place (append-only, matches the JSON store's silent-overwrite
    guard in ``store.py``)."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    content_version: int = Field(ge=1)
    category: Category
    subcategory: Optional[str] = None
    difficulty: Difficulty
    question_type: QuestionType

    question_tr: str = Field(min_length=10)
    question_en: str = Field(min_length=10)

    options_tr: Optional[List[str]] = None
    options_en: Optional[List[str]] = None
    correct_answer: Union[int, List[int], bool, float]
    tolerance: Optional[float] = None

    technical_explanation_tr: str = Field(min_length=20)
    technical_explanation_en: str = Field(min_length=20)

    standard_reference: Optional[StandardReference] = None
    source_reference: Optional[SourceReference] = None
    source_locator: Optional[str] = None
    traceability_level: TraceabilityLevel

    tags: List[str] = Field(default_factory=list)
    learning_objective: str = Field(min_length=10)
    engineering_risk_level: EngineeringRiskLevel

    # Content-side activation flag as requested by the Faz 2.9.1 field
    # list. NOTE (deliberately not enforced here): the *publishable*
    # decision is always is_active AND validation_status == "validated"
    # -- validation_status lives in SQLite, not in this model, so that
    # combined check is a validator.py / service.py responsibility
    # (see validator.validate_publishable), never a schema-level one.
    is_active: bool = False
