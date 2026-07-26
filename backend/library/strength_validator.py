"""TorqPro Engineering Library - Faz 2.8.3 bolt/nut strength class
validation.

Reuses the existing ``ValidationIssue`` dataclass from
``backend.library.validator`` (same shape, same conventions) rather
than inventing a new finding type. Validates the raw JSON records in
``bolt_nut_strength_classes.json`` -- schema/type correctness itself
is already enforced by Pydantic (see ``strength_classes.py``, both
models use ``extra="forbid"``); the checks here are the
cross-field/business-rule checks Pydantic alone can't express.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .strength_classes import (
    BoltStrengthClassRecord,
    NutPropertyClassRecord,
    Iso898DesignationError,
    parse_iso898_bolt_designation,
)
from .validator import ValidationIssue


def _issue(code: str, message: str, index: int, field: str = "") -> ValidationIssue:
    return ValidationIssue(code=code, message=message, record_index=index, field=field or None)


def find_negative_or_invalid_values(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """No mechanical-property, hardness or diameter field may be
    negative (zero is invalid too for anything that must be a real
    physical dimension/strength)."""
    issues: List[ValidationIssue] = []
    numeric_fields = (
        "nominal_tensile_strength_mpa", "min_tensile_strength_mpa",
        "min_yield_strength_mpa", "proof_stress_mpa", "hardness_min",
        "hardness_max", "diameter_min_mm", "diameter_max_mm",
        "elongation_percent", "proof_load_stress_mpa",
    )
    for i, r in enumerate(records):
        for field in numeric_fields:
            value = r.get(field)
            if value is not None and value <= 0:
                issues.append(_issue(
                    "non_positive_value",
                    f"{field}={value!r} must be positive",
                    i, field,
                ))
    return issues


def find_empty_designations(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for i, r in enumerate(records):
        designation = r.get("designation")
        if designation is None or not str(designation).strip():
            issues.append(_issue(
                "empty_designation", "designation must not be empty", i, "designation",
            ))
        elif not isinstance(designation, str):
            issues.append(_issue(
                "designation_not_string",
                f"designation must be a string, got {type(designation).__name__}",
                i, "designation",
            ))
    return issues


def find_diameter_range_violations(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for i, r in enumerate(records):
        dmin, dmax = r.get("diameter_min_mm"), r.get("diameter_max_mm")
        if dmin is not None and dmax is not None and dmin > dmax:
            issues.append(_issue(
                "diameter_range_inverted",
                f"diameter_min_mm ({dmin}) > diameter_max_mm ({dmax})",
                i, "diameter_min_mm",
            ))
    return issues


def find_hardness_range_violations(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for i, r in enumerate(records):
        hmin, hmax = r.get("hardness_min"), r.get("hardness_max")
        if hmin is not None and hmax is not None and hmin > hmax:
            issues.append(_issue(
                "hardness_range_inverted",
                f"hardness_min ({hmin}) > hardness_max ({hmax})",
                i, "hardness_min",
            ))
    return issues


def find_yield_tensile_violations(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """min_yield_strength_mpa must never exceed min_tensile_strength_mpa
    (yield cannot physically exceed ultimate tensile strength)."""
    issues: List[ValidationIssue] = []
    for i, r in enumerate(records):
        yield_v, tensile_v = r.get("min_yield_strength_mpa"), r.get("min_tensile_strength_mpa")
        if yield_v is not None and tensile_v is not None and yield_v > tensile_v:
            issues.append(_issue(
                "yield_exceeds_tensile",
                f"min_yield_strength_mpa ({yield_v}) > min_tensile_strength_mpa ({tensile_v})",
                i, "min_yield_strength_mpa",
            ))
    return issues


def find_yield_ratio_violations(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """yield_ratio must fall in the physically plausible (0, 1] range
    -- ISO 898-1 classes in practice run 0.6-0.9."""
    issues: List[ValidationIssue] = []
    for i, r in enumerate(records):
        ratio = r.get("yield_ratio")
        if ratio is not None and not (0.0 < ratio <= 1.0):
            issues.append(_issue(
                "yield_ratio_out_of_range",
                f"yield_ratio ({ratio}) is outside the plausible (0, 1] range",
                i, "yield_ratio",
            ))
    return issues


def find_invalid_verification_status(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    valid = {"validated", "reference_only", "provisional"}
    issues: List[ValidationIssue] = []
    for i, r in enumerate(records):
        status = r.get("verification_status")
        if status not in valid:
            issues.append(_issue(
                "invalid_verification_status",
                f"verification_status={status!r} is not one of {sorted(valid)}",
                i, "verification_status",
            ))
    return issues


def find_duplicate_standard_designation_diameter(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Reject duplicate (standard, designation) pairs whose diameter
    ranges overlap -- two records for the same designation are only
    legitimate if they cover genuinely disjoint diameter ranges (this
    Faz 2.8.3 dataset has none, but this guards future additions)."""
    issues: List[ValidationIssue] = []
    seen: List[Dict[str, Any]] = []
    for i, r in enumerate(records):
        std, desig = r.get("standard"), r.get("designation")
        dmin = r.get("diameter_min_mm", float("-inf"))
        dmax = r.get("diameter_max_mm", float("inf"))
        for prior_i, prior in seen:
            if prior.get("standard") != std or prior.get("designation") != desig:
                continue
            p_dmin = prior.get("diameter_min_mm", float("-inf"))
            p_dmax = prior.get("diameter_max_mm", float("inf"))
            if dmin <= p_dmax and p_dmin <= dmax:
                issues.append(_issue(
                    "duplicate_overlapping_range",
                    f"duplicate (standard={std!r}, designation={desig!r}) "
                    f"with overlapping diameter range (record #{prior_i} "
                    f"and #{i})",
                    i,
                ))
        seen.append((i, r))
    return issues


def find_iso898_designation_mismatches(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """For carbon/alloy-steel bolt records only: the stored
    ``nominal_tensile_strength_mpa`` / ``yield_ratio`` must agree with
    what :func:`parse_iso898_bolt_designation` derives from the
    designation itself (catches a typo'd designation or a stale
    nominal value after an edit)."""
    issues: List[ValidationIssue] = []
    for i, r in enumerate(records):
        if r.get("standard") != "ISO 898-1":
            continue
        designation = r.get("designation", "")
        try:
            derived = parse_iso898_bolt_designation(designation)
        except Iso898DesignationError:
            issues.append(_issue(
                "unparseable_iso898_designation",
                f"designation {designation!r} is not a valid ISO 898-1 "
                "decimal designation",
                i, "designation",
            ))
            continue
        stored_nominal = r.get("nominal_tensile_strength_mpa")
        if stored_nominal is not None and stored_nominal != derived["nominal_tensile_strength_mpa"]:
            issues.append(_issue(
                "nominal_tensile_mismatch",
                f"stored nominal_tensile_strength_mpa ({stored_nominal}) != "
                f"designation-derived value ({derived['nominal_tensile_strength_mpa']})",
                i, "nominal_tensile_strength_mpa",
            ))
        stored_ratio = r.get("yield_ratio")
        if stored_ratio is not None and stored_ratio != derived["yield_ratio"]:
            issues.append(_issue(
                "yield_ratio_mismatch",
                f"stored yield_ratio ({stored_ratio}) != designation-derived "
                f"value ({derived['yield_ratio']})",
                i, "yield_ratio",
            ))
    return issues


def validate_bolt_strength_class_records(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Run every applicable check against bolt strength-class records
    and return the combined, deterministically-ordered issue list."""
    issues: List[ValidationIssue] = []
    issues += find_negative_or_invalid_values(records)
    issues += find_empty_designations(records)
    issues += find_diameter_range_violations(records)
    issues += find_hardness_range_violations(records)
    issues += find_yield_tensile_violations(records)
    issues += find_yield_ratio_violations(records)
    issues += find_invalid_verification_status(records)
    issues += find_duplicate_standard_designation_diameter(records)
    issues += find_iso898_designation_mismatches(records)
    return issues


def validate_nut_property_class_records(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    issues += find_negative_or_invalid_values(records)
    issues += find_empty_designations(records)
    issues += find_diameter_range_violations(records)
    issues += find_hardness_range_violations(records)
    issues += find_invalid_verification_status(records)
    issues += find_duplicate_standard_designation_diameter(records)
    return issues


def bolt_record_cannot_parse_as_nut(raw: Dict[str, Any]) -> bool:
    """True if ``raw`` (a bolt-shaped dict) is rejected by the nut
    model -- guards against a bolt record silently being accepted as
    a nut record (or vice versa) if the two shapes ever partially
    overlap. Both models use ``extra="forbid"``, so a bolt record
    (which has ``min_tensile_strength_mpa`` etc., fields the nut model
    doesn't declare) is rejected by ``NutPropertyClassRecord`` and a
    nut record (which has ``proof_load_stress_mpa`` /
    ``compatible_bolt_classes``, fields the bolt model doesn't
    declare) is rejected by ``BoltStrengthClassRecord``."""
    try:
        NutPropertyClassRecord.model_validate(raw)
    except Exception:
        return True
    return False


def nut_record_cannot_parse_as_bolt(raw: Dict[str, Any]) -> bool:
    try:
        BoltStrengthClassRecord.model_validate(raw)
    except Exception:
        return True
    return False


__all__ = [
    "find_negative_or_invalid_values",
    "find_empty_designations",
    "find_diameter_range_violations",
    "find_hardness_range_violations",
    "find_yield_tensile_violations",
    "find_yield_ratio_violations",
    "find_invalid_verification_status",
    "find_duplicate_standard_designation_diameter",
    "find_iso898_designation_mismatches",
    "validate_bolt_strength_class_records",
    "validate_nut_property_class_records",
    "bolt_record_cannot_parse_as_nut",
    "nut_record_cannot_parse_as_bolt",
]
