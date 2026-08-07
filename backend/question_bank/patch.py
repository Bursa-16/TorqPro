"""Faz 2.9.3: PATCH payload model for Question Bank content updates.

Kept as its own small module (not added to ``schema.py``) so the
Faz 2.9.1/2.9.2 canonical-content schema file stays untouched by this
phase -- this model is purely an API/service-layer input shape, never
persisted as-is and never a second definition of the content schema
itself (every field's type is reused directly from ``schema.py``).
"""

from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict

from .schema import (
    Category,
    Difficulty,
    EngineeringRiskLevel,
    QuestionType,
    SourceReference,
    StandardReference,
    TraceabilityLevel,
)


class QuestionPatch(BaseModel):
    """Partial-update payload for
    ``PATCH /api/question-bank/questions/{question_id}``.

    Deliberately excludes ``question_id`` and ``content_version``
    (identity, immutable -- see ``schema.QuestionRecord``'s own
    immutability docstring) and carries no lifecycle field either
    (``validation_status`` and friends live only in SQLite, never on
    :class:`backend.question_bank.schema.QuestionRecord`) -- so neither
    can be set through this payload even by an over-permissive client,
    they simply have no field to write to here.

    Every field is ``Optional`` with a plain ``None`` default and no
    sentinel trickery: :func:`backend.question_bank.service.update_question`
    reads this model exclusively via ``model_dump(exclude_unset=True)``,
    which uses Pydantic's own ``fields_set`` bookkeeping to distinguish
    "field omitted from the request body" (never touched) from
    "field explicitly provided as ``null``" (present in ``fields_set``
    with value ``None``) -- the latter is a legal way to clear an
    already-nullable content field (e.g. ``subcategory``), while the
    former means "leave this field's current value untouched".
    """

    model_config = ConfigDict(extra="forbid")

    category: Optional[Category] = None
    subcategory: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    question_type: Optional[QuestionType] = None

    question_tr: Optional[str] = None
    question_en: Optional[str] = None

    options_tr: Optional[List[str]] = None
    options_en: Optional[List[str]] = None
    correct_answer: Optional[Union[int, List[int], bool, float]] = None
    tolerance: Optional[float] = None

    technical_explanation_tr: Optional[str] = None
    technical_explanation_en: Optional[str] = None

    standard_reference: Optional[StandardReference] = None
    source_reference: Optional[SourceReference] = None
    source_locator: Optional[str] = None
    traceability_level: Optional[TraceabilityLevel] = None

    tags: Optional[List[str]] = None
    learning_objective: Optional[str] = None
    engineering_risk_level: Optional[EngineeringRiskLevel] = None

    is_active: Optional[bool] = None


#: Documents the editable/immutable split for callers and tests, kept
#: next to the model itself as the single source of truth (the router's
#: docstring and the final delivery report both reference this constant
#: rather than re-enumerating the field list by hand).
EDITABLE_FIELDS = frozenset(QuestionPatch.model_fields.keys())
IMMUTABLE_FIELDS = frozenset({"question_id", "content_version"})

__all__ = ["QuestionPatch", "EDITABLE_FIELDS", "IMMUTABLE_FIELDS"]
