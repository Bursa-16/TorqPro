"""TorqPro Engineering Library - Faz 2.8.3 bolt/nut strength class
typed layer.

Additive, read-only typed models and loader over a new data file
(``backend/library/data/bolt_nut_strength_classes.json``), distinct
from and never touching the Phase 1.3/2.4.1 generic
``StrengthClassRecord`` / ``strength_class_library.json`` (see
``models.py`` / ``strength_class_library.py``), which keeps working
unmodified. Bolt and nut classes are modelled as two separate Pydantic
types (``BoltStrengthClassRecord`` / ``NutPropertyClassRecord``) --
they are not the same shape and are not compared as if they were.

Nothing here is registered with ``backend.library.registry`` /
``backend.library.population`` (that 12-key architecture is unchanged
this phase); this module is deliberately self-contained.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

DATA_PATH = Path(__file__).resolve().parent / "data" / "bolt_nut_strength_classes.json"


class StrengthClassMaterialFamily(str, Enum):
    """Material family a strength/property class belongs to. Carbon/
    alloy steel (ISO 898-1/-2) and the two common stainless alloy
    families (ISO 3506-1) are kept distinct -- a 10.9 carbon-steel
    bolt and an A4-80 stainless bolt are never treated as
    interchangeable data just because both happen to produce a
    "high strength" number."""

    CARBON_ALLOY_STEEL = "carbon_alloy_steel"
    STAINLESS_A2 = "stainless_a2"
    STAINLESS_A4 = "stainless_a4"


class StrengthClassVerificationStatus(str, Enum):
    """How strongly a strength-class record's data is sourced.
    Mirrors the ``validation_status`` vocabulary already used
    elsewhere in ``backend.library`` (validated / reference_only /
    provisional) so the same mental model applies here."""

    VALIDATED = "validated"
    REFERENCE_ONLY = "reference_only"
    PROVISIONAL = "provisional"


class StrengthValueSource(str, Enum):
    """Where a resolved mechanical-property value came from, per
    field -- used by :func:`resolve_strength_properties` so a caller
    can always tell whether a number is a stored library value, a
    derived-from-designation estimate, a manual override, or a value
    read from the older Faz 2.4.1 ``StrengthClassRecord`` legacy
    path."""

    DERIVED_FROM_STRENGTH_CLASS = "derived_from_strength_class"
    MANUAL_OVERRIDE = "manual_override"
    LIBRARY_RECORD = "library_record"
    LEGACY_CALCULATION = "legacy_calculation"


class BoltStrengthClassRecord(BaseModel):
    """ISO 898-1 (carbon/alloy steel) or ISO 3506-1 (stainless) bolt
    strength/property class record."""

    id: str
    designation: str
    standard: str
    material_family: StrengthClassMaterialFamily
    nominal_tensile_strength_mpa: Optional[float] = None
    min_tensile_strength_mpa: Optional[float] = None
    yield_ratio: Optional[float] = None
    min_yield_strength_mpa: Optional[float] = None
    proof_stress_mpa: Optional[float] = None
    hardness_min: Optional[float] = None
    hardness_max: Optional[float] = None
    hardness_scale: str = ""
    diameter_min_mm: Optional[float] = None
    diameter_max_mm: Optional[float] = None
    heat_treatment: str = ""
    elongation_percent: Optional[float] = None
    notes_tr: str = ""
    notes_en: str = ""
    source: str = ""
    verification_status: StrengthClassVerificationStatus
    engineering_warning: Optional[str] = None
    revision: str = ""

    model_config = {"extra": "forbid"}


class NutPropertyClassRecord(BaseModel):
    """ISO 898-2 nut property class record. Deliberately NOT the same
    shape as :class:`BoltStrengthClassRecord` -- nuts are specified by
    proof load stress, not a tensile/yield pair, and pairing rules
    live in ``compatible_bolt_classes`` here rather than being
    inferred mathematically from the designation."""

    id: str
    designation: str  # e.g. "04" -- always a string, never coerced to int
    standard: str
    material_family: StrengthClassMaterialFamily
    proof_load_stress_mpa: Optional[float] = None
    compatible_bolt_classes: Tuple[str, ...] = ()
    diameter_min_mm: Optional[float] = None
    diameter_max_mm: Optional[float] = None
    nut_style: str = ""
    hardness_min: Optional[float] = None
    hardness_max: Optional[float] = None
    hardness_scale: str = ""
    heat_treatment: str = ""
    notes_tr: str = ""
    notes_en: str = ""
    source: str = ""
    verification_status: StrengthClassVerificationStatus
    revision: str = ""

    model_config = {"extra": "forbid"}


class BoltNutCompatibilityResult(BaseModel):
    """Structured strength-class compatibility outcome. See
    ``backend.library.strength_compatibility`` for the engine that
    produces this."""

    status: str  # "compatible" | "conditionally_compatible" | "not_compatible" | "unknown"
    compatible: bool
    bolt_strength_class: Optional[str] = None
    nut_property_class: Optional[str] = None
    recommended_minimum_nut_class: Optional[str] = None
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    warning_codes: List[str] = Field(default_factory=list)
    checks: Dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------
# Loading (read-only; cached at module scope like the rest of
# backend.library, invalidated by an explicit reload() call only --
# no file-watching).
# ---------------------------------------------------------------------

_CACHE: Optional[Dict[str, Any]] = None


def _raw_data() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE


def reload() -> None:
    """Clear the in-memory cache so the next read re-parses the JSON
    file from disk. Exposed for tests; not used by any request path."""
    global _CACHE
    _CACHE = None


def _bolt_records_raw() -> List[Dict[str, Any]]:
    return list(_raw_data().get("bolt_records", []))


def _nut_records_raw() -> List[Dict[str, Any]]:
    return list(_raw_data().get("nut_records", []))


def _matches_diameter(record: Dict[str, Any], diameter_mm: Optional[float]) -> bool:
    if diameter_mm is None:
        return True
    dmin = record.get("diameter_min_mm")
    dmax = record.get("diameter_max_mm")
    if dmin is not None and diameter_mm < dmin:
        return False
    if dmax is not None and diameter_mm > dmax:
        return False
    return True


def list_bolt_strength_classes(
    standard: Optional[str] = None,
    material_family: Optional[str] = None,
    designation: Optional[str] = None,
    diameter_mm: Optional[float] = None,
    verification_status: Optional[str] = None,
) -> List[BoltStrengthClassRecord]:
    """List bolt strength-class records, optionally filtered.

    Every filter is "no constraint" only when the argument is
    ``None`` -- an empty string ``""`` is treated as a literal
    (non-matching) filter value, never silently treated the same as
    "no filter", per the Faz 2.8.3 brief ("Boş string ile None filtre
    davranışını karıştırmayın").
    """
    results = []
    for raw in _bolt_records_raw():
        if standard is not None and raw.get("standard") != standard:
            continue
        if material_family is not None and raw.get("material_family") != material_family:
            continue
        if designation is not None and raw.get("designation") != designation:
            continue
        if (
            verification_status is not None
            and raw.get("verification_status") != verification_status
        ):
            continue
        if not _matches_diameter(raw, diameter_mm):
            continue
        results.append(BoltStrengthClassRecord.model_validate(raw))
    return results


def get_bolt_strength_class(designation: str) -> Optional[BoltStrengthClassRecord]:
    for raw in _bolt_records_raw():
        if raw.get("designation") == designation:
            return BoltStrengthClassRecord.model_validate(raw)
    return None


def list_nut_property_classes(
    standard: Optional[str] = None,
    material_family: Optional[str] = None,
    designation: Optional[str] = None,
    diameter_mm: Optional[float] = None,
    verification_status: Optional[str] = None,
) -> List[NutPropertyClassRecord]:
    results = []
    for raw in _nut_records_raw():
        if standard is not None and raw.get("standard") != standard:
            continue
        if material_family is not None and raw.get("material_family") != material_family:
            continue
        if designation is not None and raw.get("designation") != designation:
            continue
        if (
            verification_status is not None
            and raw.get("verification_status") != verification_status
        ):
            continue
        if not _matches_diameter(raw, diameter_mm):
            continue
        results.append(NutPropertyClassRecord.model_validate(raw))
    return results


def get_nut_property_class(designation: str) -> Optional[NutPropertyClassRecord]:
    for raw in _nut_records_raw():
        if raw.get("designation") == designation:
            return NutPropertyClassRecord.model_validate(raw)
    return None


# ---------------------------------------------------------------------
# ISO 898 decimal designation parser
# ---------------------------------------------------------------------

class Iso898DesignationError(ValueError):
    """Raised by :func:`parse_iso898_bolt_designation` for a
    malformed or out-of-range ISO 898-1 decimal designation."""


def parse_iso898_bolt_designation(designation: str) -> Dict[str, float]:
    """Parse an ISO 898-1 decimal bolt designation (e.g. ``"8.8"``)
    into its NOMINAL mechanical properties, per the designation
    system's own definition:

    - nominal tensile strength (Rm) = first digit(s) * 100 MPa
    - yield ratio = second digit / 10
    - nominal yield strength (Rp0.2) = Rm * ratio

    These are *nominal* values implied by the designation itself, not
    a substitute for the real per-class minimum values in
    ``BoltStrengthClassRecord`` (``min_tensile_strength_mpa`` /
    ``min_yield_strength_mpa`` / ``proof_stress_mpa``), which come
    from the standard's table and can differ from this simple
    formula (e.g. 8.8's real Rm minimum is 830 MPa, not the nominal
    800 MPa this formula gives). Callers needing the real,
    standard-table minimum values must use
    :func:`get_bolt_strength_class` / :func:`resolve_strength_properties`,
    not this parser alone.

    Raises :class:`Iso898DesignationError` for anything that isn't a
    two-part ``X.Y`` decimal designation with positive integer parts.
    """
    if not isinstance(designation, str) or "." not in designation:
        raise Iso898DesignationError(
            f"Not a valid ISO 898-1 decimal designation: {designation!r}"
        )
    parts = designation.split(".")
    if len(parts) != 2:
        raise Iso898DesignationError(
            f"Not a valid ISO 898-1 decimal designation: {designation!r}"
        )
    first, second = parts
    if not (first.isdigit() and second.isdigit()):
        raise Iso898DesignationError(
            f"Not a valid ISO 898-1 decimal designation: {designation!r}"
        )
    first_i, second_i = int(first), int(second)
    if first_i <= 0 or second_i <= 0:
        raise Iso898DesignationError(
            f"ISO 898-1 designation parts must be positive: {designation!r}"
        )
    if first_i > 20 or second_i > 9:
        # ISO 898-1 classes run up to 12.9; anything wildly outside
        # that range is almost certainly not a real designation
        # rather than a legitimate new class this parser should
        # silently accept.
        raise Iso898DesignationError(
            f"Designation out of plausible ISO 898-1 range: {designation!r}"
        )
    nominal_tensile = float(first_i * 100)
    yield_ratio = second_i / 10.0
    nominal_yield = nominal_tensile * yield_ratio
    return {
        "nominal_tensile_strength_mpa": nominal_tensile,
        "yield_ratio": yield_ratio,
        "nominal_yield_strength_mpa": nominal_yield,
    }


# ---------------------------------------------------------------------
# Manual-override-aware property resolution
# ---------------------------------------------------------------------

#: Fields resolve_strength_properties will report a per-field source
#: for. Kept to the fields that actually vary by resolution path
#: (id/designation/standard are never "resolved", they identify the
#: record).
_RESOLVABLE_FIELDS = (
    "nominal_tensile_strength_mpa",
    "min_tensile_strength_mpa",
    "yield_ratio",
    "min_yield_strength_mpa",
    "proof_stress_mpa",
)


def resolve_strength_properties(
    designation: str,
    manual_values: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Pure function: resolve mechanical properties for ``designation``
    by combining (in order of precedence)

    1. an explicit per-field ``manual_values`` override (never
       silently overwritten by a library or derived value), then
    2. the stored :class:`BoltStrengthClassRecord` (``library_record``),
       falling back to
    3. the nominal, designation-derived formula
       (``derived_from_strength_class``) when no library record exists
       for this designation.

    Every resolved field gets an explicit :class:`StrengthValueSource`
    tag in the returned ``sources`` map -- callers can always tell
    whether a number came from a manual override, a stored library
    record, or a plain designation-based derivation. Nothing here
    reads or writes any file; this is a pure, side-effect-free
    function (no state persists between calls).
    """
    manual_values = manual_values or {}
    result: Dict[str, Any] = {"designation": designation, "sources": {}}

    record = get_bolt_strength_class(designation)
    derived: Optional[Dict[str, float]] = None
    try:
        derived = parse_iso898_bolt_designation(designation)
    except Iso898DesignationError:
        derived = None

    for field_name in _RESOLVABLE_FIELDS:
        if field_name in manual_values:
            result[field_name] = manual_values[field_name]
            result["sources"][field_name] = StrengthValueSource.MANUAL_OVERRIDE.value
            continue
        if record is not None and getattr(record, field_name, None) is not None:
            result[field_name] = getattr(record, field_name)
            result["sources"][field_name] = StrengthValueSource.LIBRARY_RECORD.value
            continue
        if derived is not None:
            # derived only has 3 of the 5 resolvable fields (no
            # separate min_tensile/proof_stress concept) -- map what
            # it has, leave the rest unresolved rather than guessing.
            mapped = {
                "nominal_tensile_strength_mpa": derived["nominal_tensile_strength_mpa"],
                "yield_ratio": derived["yield_ratio"],
            }
            if field_name in mapped:
                result[field_name] = mapped[field_name]
                result["sources"][field_name] = (
                    StrengthValueSource.DERIVED_FROM_STRENGTH_CLASS.value
                )
                continue
        result[field_name] = None
        result["sources"][field_name] = None

    result["has_library_record"] = record is not None
    return result


__all__ = [
    "StrengthClassMaterialFamily",
    "StrengthClassVerificationStatus",
    "StrengthValueSource",
    "BoltStrengthClassRecord",
    "NutPropertyClassRecord",
    "BoltNutCompatibilityResult",
    "Iso898DesignationError",
    "list_bolt_strength_classes",
    "get_bolt_strength_class",
    "list_nut_property_classes",
    "get_nut_property_class",
    "parse_iso898_bolt_designation",
    "resolve_strength_properties",
    "reload",
]
