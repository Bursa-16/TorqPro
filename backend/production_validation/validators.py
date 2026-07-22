"""Stateless data-integrity validators (section 5 of the Faz 2.5A spec).

Uniqueness checks (study_code, dataset_code, sequence_number) require a
database round-trip and live in repository.py / service.py instead.
"""
from __future__ import annotations

import math

from backend.production_validation.exceptions import ValidationDataError


def validate_spec_limits(
    lower_spec_limit: float, upper_spec_limit: float, target_value: float | None = None
) -> None:
    if lower_spec_limit is None or upper_spec_limit is None:
        raise ValidationDataError("lower_spec_limit and upper_spec_limit are required")
    if not (lower_spec_limit < upper_spec_limit):
        raise ValidationDataError("lower_spec_limit must be smaller than upper_spec_limit")
    if target_value is not None and not (lower_spec_limit <= target_value <= upper_spec_limit):
        raise ValidationDataError(
            "target_value must fall within [lower_spec_limit, upper_spec_limit]"
        )


def validate_subgroup_size(subgroup_size: int | None) -> None:
    if subgroup_size is not None and subgroup_size <= 0:
        raise ValidationDataError("subgroup_size must be a positive integer")


def validate_measured_value(value: float) -> None:
    if value is None:
        raise ValidationDataError("measured_value is required")
    try:
        fv = float(value)
    except (TypeError, ValueError):
        raise ValidationDataError("measured_value must be numeric")
    if math.isnan(fv) or math.isinf(fv):
        raise ValidationDataError("measured_value must be a finite number (NaN/Infinity rejected)")


def validate_unit_present(unit: str | None) -> None:
    if not unit or not str(unit).strip():
        raise ValidationDataError("dataset unit must not be empty")


def validate_invalid_reason(is_valid: bool, invalid_reason: str | None) -> None:
    if not is_valid and not (invalid_reason and invalid_reason.strip()):
        raise ValidationDataError("invalid_reason is required when is_valid is False")


def validate_study_type(study_type: str) -> None:
    from backend.production_validation.enums import STUDY_TYPES
    if study_type not in STUDY_TYPES:
        raise ValidationDataError(f"unknown study_type '{study_type}'")


def validate_characteristic_type(characteristic_type: str) -> None:
    from backend.production_validation.enums import CHARACTERISTIC_TYPES
    if characteristic_type not in CHARACTERISTIC_TYPES:
        raise ValidationDataError(f"unknown characteristic_type '{characteristic_type}'")
