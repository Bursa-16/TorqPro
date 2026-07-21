"""TorqPro Engineering Library - validation engine (Phase 1.4 infrastructure).

Data-quality checks over library records: duplicate identifiers,
missing required fields, unit mismatches against a library's declared
supported units, malformed thread designations, unrecognised material
designations and broken bolt/nut compatibility references.

These are structural/data-quality checks, not engineering
calculations: nothing here computes a physical result, invents a
coefficient, or is wired into ``backend.engineering_core`` or
``backend.standards``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .registry import BaseLibrary
from .models import KNOWN_THREAD_SERIES, THREAD_SCHEMA_VERSION, ThreadRecord
from .thread_geometry import (
    basic_minor_diameter_external_mm,
    basic_minor_diameter_internal_mm,
)

# Reference designation sets used only to flag records the validator
# does not recognise. These are data-quality allow-lists for this
# infrastructure layer, not calculation inputs, and are independent of
# engineering_core/standards.
KNOWN_BOLT_CLASSES = frozenset(
    {"3.6", "4.6", "4.8", "5.6", "5.8", "6.8", "6.9", "8.8", "9.8", "10.9", "12.9"}
)
KNOWN_NUT_CLASSES = frozenset({"04", "05", "4", "5", "6", "8", "9", "10", "12"})
KNOWN_MATERIAL_GRADES = frozenset(
    {
        "4.6", "4.8", "5.6", "5.8", "8.8", "10.9", "12.9",
        "A2-50", "A2-70", "A2-80", "A4-50", "A4-70", "A4-80",
        "C1022", "35CrMo4", "42CrMo4", "41Cr4",
    }
)

# Metric thread designations such as "M8" or "M10x1.5".
_THREAD_PATTERN = re.compile(r"^M\d{1,3}(\.\d{1,2})?([xX]\d{1,2}(\.\d{1,2})?)?$")


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding."""

    code: str
    message: str
    record_index: Optional[int] = None
    field: Optional[str] = None


@dataclass
class ValidationReport:
    """Aggregated validation result for one library (or raw record set)."""

    subject: str
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when no issues were found."""
        return not self.issues

    def count_by_code(self) -> Dict[str, int]:
        """Number of issues found per issue code."""
        counts: Dict[str, int] = {}
        for issue in self.issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        return counts


def find_duplicate_ids(
    records: Sequence[Dict[str, Any]], id_field: str = "id"
) -> List[ValidationIssue]:
    """Flag records that reuse an identifier already seen earlier in
    the list. Records without ``id_field`` are skipped (not flagged
    here; use ``find_missing_fields`` for that)."""
    seen: Dict[Any, int] = {}
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if id_field not in record:
            continue
        value = record[id_field]
        if value in seen:
            issues.append(
                ValidationIssue(
                    code="duplicate_id",
                    message=(
                        f"Duplicate {id_field!r} value {value!r} "
                        f"(first seen at index {seen[value]})"
                    ),
                    record_index=index,
                    field=id_field,
                )
            )
        else:
            seen[value] = index
    return issues


def find_missing_fields(
    records: Sequence[Dict[str, Any]], required_fields: Iterable[str]
) -> List[ValidationIssue]:
    """Flag records missing any of ``required_fields`` (absent or
    holding an empty value)."""
    fields = list(required_fields)
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        for name in fields:
            if record.get(name) in (None, ""):
                issues.append(
                    ValidationIssue(
                        code="missing_field",
                        message=f"Missing required field {name!r}",
                        record_index=index,
                        field=name,
                    )
                )
    return issues


def find_unit_mismatches(
    records: Sequence[Dict[str, Any]],
    unit_field: str,
    supported_units: Sequence[str],
) -> List[ValidationIssue]:
    """Flag records whose ``unit_field`` value is not one of
    ``supported_units``. Records without ``unit_field`` are skipped."""
    if not supported_units:
        return []
    allowed = set(supported_units)
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if unit_field not in record:
            continue
        value = record[unit_field]
        if value not in allowed:
            issues.append(
                ValidationIssue(
                    code="unit_mismatch",
                    message=f"Unit {value!r} not in supported units {sorted(allowed)}",
                    record_index=index,
                    field=unit_field,
                )
            )
    return issues


def is_valid_thread_designation(value: str) -> bool:
    """Return True if ``value`` looks like a metric thread designation
    (e.g. 'M8', 'M10x1.5')."""
    return bool(value) and bool(_THREAD_PATTERN.match(value.strip()))


def find_invalid_threads(
    records: Sequence[Dict[str, Any]], thread_field: str = "thread"
) -> List[ValidationIssue]:
    """Flag records whose ``thread_field`` is not a recognised metric
    thread designation. Records without ``thread_field`` are skipped."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if thread_field not in record:
            continue
        value = record[thread_field]
        if not isinstance(value, str) or not is_valid_thread_designation(value):
            issues.append(
                ValidationIssue(
                    code="invalid_thread",
                    message=f"Not a recognised thread designation: {value!r}",
                    record_index=index,
                    field=thread_field,
                )
            )
    return issues


def is_known_material_grade(value: str) -> bool:
    """Return True if ``value`` is one of the recognised reference
    material/property-class designations."""
    return value in KNOWN_MATERIAL_GRADES


def find_invalid_materials(
    records: Sequence[Dict[str, Any]], material_field: str = "material"
) -> List[ValidationIssue]:
    """Flag records whose ``material_field`` is not a recognised
    material grade. Records without ``material_field`` are skipped."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if material_field not in record:
            continue
        value = record[material_field]
        if not isinstance(value, str) or not is_known_material_grade(value):
            issues.append(
                ValidationIssue(
                    code="invalid_material",
                    message=f"Unrecognised material grade: {value!r}",
                    record_index=index,
                    field=material_field,
                )
            )
    return issues


def find_broken_compatibility(
    rules: Sequence[Dict[str, Any]],
    bolt_field: str = "bolt_class",
    nut_field: str = "minimum_nut_class",
) -> List[ValidationIssue]:
    """Flag compatibility rules referencing an unrecognised bolt or
    nut property class."""
    issues: List[ValidationIssue] = []
    for index, rule in enumerate(rules):
        bolt_class = rule.get(bolt_field)
        nut_class = rule.get(nut_field)
        if bolt_class not in KNOWN_BOLT_CLASSES:
            issues.append(
                ValidationIssue(
                    code="broken_compatibility",
                    message=f"Unrecognised bolt class in compatibility rule: {bolt_class!r}",
                    record_index=index,
                    field=bolt_field,
                )
            )
        if nut_class not in KNOWN_NUT_CLASSES:
            issues.append(
                ValidationIssue(
                    code="broken_compatibility",
                    message=f"Unrecognised nut class in compatibility rule: {nut_class!r}",
                    record_index=index,
                    field=nut_field,
                )
            )
    return issues


# Per-library-key hints so ``validate_library`` knows which optional,
# shape-specific checks make sense for that library's records.
_LIBRARY_FIELD_HINTS: Dict[str, Dict[str, Any]] = {
    "thread library": {"thread_field": "designation"},
    "material library": {"material_field": "material"},
    "compatibility library": {"is_compatibility": True},
}


def validate_records(
    records: Sequence[Dict[str, Any]],
    *,
    id_field: str = "id",
    required_fields: Iterable[str] = (),
    unit_field: Optional[str] = None,
    supported_units: Sequence[str] = (),
    thread_field: Optional[str] = None,
    material_field: Optional[str] = None,
    is_compatibility: bool = False,
    subject: str = "records",
) -> ValidationReport:
    """Run the requested checks over a raw record list. Each check is
    opt-in: only checks whose parameters were supplied are run."""
    issues: List[ValidationIssue] = []
    issues.extend(find_duplicate_ids(records, id_field))
    if required_fields:
        issues.extend(find_missing_fields(records, required_fields))
    if unit_field and supported_units:
        issues.extend(find_unit_mismatches(records, unit_field, supported_units))
    if thread_field:
        issues.extend(find_invalid_threads(records, thread_field))
    if material_field:
        issues.extend(find_invalid_materials(records, material_field))
    if is_compatibility:
        issues.extend(find_broken_compatibility(records))
    return ValidationReport(subject=subject, issues=issues)


def validate_library(library: BaseLibrary, id_field: str = "id") -> ValidationReport:
    """Validate a registered library's current in-memory records,
    automatically choosing the checks relevant to that library."""
    hints = _LIBRARY_FIELD_HINTS.get(library.metadata.key, {})
    return validate_records(
        library.records,
        id_field=id_field,
        unit_field="unit",
        supported_units=library.metadata.supported_units,
        thread_field=hints.get("thread_field"),
        material_field=hints.get("material_field"),
        is_compatibility=hints.get("is_compatibility", False),
        subject=library.metadata.name,
    )


def validate_schema(library: BaseLibrary) -> ValidationReport:
    """Validate a library's current in-memory records against its
    Faz 2.4.0 typed schema (see ``backend.library.models``).

    Distinct from ``validate_library`` above: that function runs the
    Phase 1.4 structural/data-quality checks (duplicates, missing
    fields, unit mismatches, ...) over raw dicts; this one runs
    Pydantic schema validation over the same raw dicts and reports
    any violation as a ``ValidationIssue`` with code
    ``"schema_violation"``. Neither replaces the other -- both are
    opt-in and read-only.
    """
    messages = library.find_schema_violations()
    issues = [
        ValidationIssue(code="schema_violation", message=message)
        for message in messages
    ]
    return ValidationReport(subject=library.metadata.name, issues=issues)


# ---------------------------------------------------------------------
# Faz 2.4.1A: thread-specific validation.
#
# Everything below is scoped to ``thread library`` records and
# opt-in (not wired into ``validate_library`` / ``validate_records``
# above, which stay Faz-1.4-generic and unchanged). Metric-geometry
# checks (designation<->diameter, minor-diameter/stress-area
# tolerance) only ever apply to ``thread_series == "ISO_METRIC"``
# records -- the pre-existing UNC/UNF/UNEF/BSP/NPT/Trapezoidal
# records use different national-standard profiles and are always
# skipped by those checks, never flagged for not matching ISO 724.
# ---------------------------------------------------------------------

#: "M10" or "M10x1.25" (metric designation, optional explicit pitch
#: suffix). Distinct from ``_THREAD_PATTERN`` above (which also
#: accepts a bare integer-only variant used for the bolt/nut
#: cross-reference check); this one is used only to parse the nominal
#: diameter back out of an ISO_METRIC thread record's own designation.
_METRIC_DESIGNATION_RE = re.compile(r"^M(\d+(?:\.\d+)?)(?:[xX](\d+(?:\.\d+)?))?$")

#: Field names ``ThreadRecord`` actually declares (schema + pre-
#: existing), used by ``find_thread_unknown_fields`` to report
#: unknown keys as a batch of ``ValidationIssue`` (rather than as a
#: single raised ``ValidationError`` -- see that function's docstring
#: for why both layers exist).
_KNOWN_THREAD_FIELDS = frozenset(ThreadRecord.model_fields)


def is_iso_metric_thread_record(record: Dict[str, Any]) -> bool:
    """True if ``record`` is in Faz 2.4.1A's own scope."""
    return record.get("thread_series") == "ISO_METRIC"


def find_duplicate_thread_designation_pitch(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag records that reuse the same ``(designation, pitch_mm)``
    pair seen earlier in the list."""
    seen: Dict[Any, int] = {}
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        key = (record.get("designation"), record.get("pitch_mm"))
        if key in seen:
            issues.append(
                ValidationIssue(
                    code="duplicate_thread_designation_pitch",
                    message=(
                        f"Duplicate designation+pitch {key!r} "
                        f"(first seen at index {seen[key]})"
                    ),
                    record_index=index,
                    field="designation",
                )
            )
        else:
            seen[key] = index
    return issues


def find_non_positive_thread_dimensions(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag records whose ``nominal_diameter_mm`` or ``pitch_mm`` is
    missing, zero, or negative."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        for field_name in ("nominal_diameter_mm", "pitch_mm"):
            value = record.get(field_name)
            if not isinstance(value, (int, float)) or value <= 0:
                issues.append(
                    ValidationIssue(
                        code="non_positive_dimension",
                        message=f"{field_name} must be > 0, got {value!r}",
                        record_index=index,
                        field=field_name,
                    )
                )
    return issues


def find_thread_designation_diameter_mismatches(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """For ISO_METRIC records only: flag a ``designation`` whose
    parsed nominal diameter (e.g. "M10" -> 10, "M10x1.25" -> 10)
    disagrees with the record's own ``nominal_diameter_mm``, or a
    designation that doesn't parse as a metric designation at all."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if not is_iso_metric_thread_record(record):
            continue
        designation = record.get("designation", "")
        match = _METRIC_DESIGNATION_RE.match(designation)
        if not match:
            issues.append(
                ValidationIssue(
                    code="unparseable_metric_designation",
                    message=f"Not a parseable ISO metric designation: {designation!r}",
                    record_index=index,
                    field="designation",
                )
            )
            continue
        parsed_diameter = float(match.group(1))
        actual_diameter = record.get("nominal_diameter_mm")
        if actual_diameter != parsed_diameter:
            issues.append(
                ValidationIssue(
                    code="designation_diameter_mismatch",
                    message=(
                        f"designation {designation!r} implies nominal_diameter_mm="
                        f"{parsed_diameter}, but record has {actual_diameter!r}"
                    ),
                    record_index=index,
                    field="nominal_diameter_mm",
                )
            )
    return issues


def find_thread_pitch_type_classification_mismatches(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """For ISO_METRIC records only: flag a ``pitch_type`` that
    disagrees with the pre-existing ``series`` field (they must
    encode the same coarse/fine/extra-fine classification), or a
    ``pitch_type`` outside {"coarse", "fine", "extra_fine"}."""
    series_to_pitch_type = {"Coarse": "coarse", "Fine": "fine", "Extra Fine": "extra_fine"}
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if not is_iso_metric_thread_record(record):
            continue
        pitch_type = record.get("pitch_type")
        series = record.get("series", "")
        expected = series_to_pitch_type.get(series)
        if pitch_type not in ("coarse", "fine", "extra_fine"):
            issues.append(
                ValidationIssue(
                    code="invalid_pitch_type",
                    message=f"Unrecognised pitch_type {pitch_type!r}",
                    record_index=index,
                    field="pitch_type",
                )
            )
        elif pitch_type != expected:
            issues.append(
                ValidationIssue(
                    code="pitch_type_series_mismatch",
                    message=(
                        f"pitch_type {pitch_type!r} does not match series "
                        f"{series!r} (expected {expected!r})"
                    ),
                    record_index=index,
                    field="pitch_type",
                )
            )
    return issues


def find_thread_schema_version_issues(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag any thread record whose ``schema_version`` is not exactly
    ``THREAD_SCHEMA_VERSION``."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        value = record.get("schema_version")
        if value != THREAD_SCHEMA_VERSION:
            issues.append(
                ValidationIssue(
                    code="schema_version_mismatch",
                    message=(
                        f"schema_version {value!r} != expected "
                        f"{THREAD_SCHEMA_VERSION!r}"
                    ),
                    record_index=index,
                    field="schema_version",
                )
            )
    return issues


def find_thread_unknown_fields(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Batch-report every field name not declared on ``ThreadRecord``
    (see ``ThreadRecord.model_config['extra'] == "forbid"``, which
    already rejects these at parse time by raising on the *first*
    invalid record). This function exists alongside that Pydantic
    layer so a caller can see every unknown field across every record
    in one report instead of stopping at the first
    ``ValidationError``."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        unknown = sorted(set(record) - _KNOWN_THREAD_FIELDS)
        for field_name in unknown:
            issues.append(
                ValidationIssue(
                    code="unknown_field",
                    message=f"Unrecognised field {field_name!r}",
                    record_index=index,
                    field=field_name,
                )
            )
    return issues


def find_thread_series_scope_issues(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag any thread record whose ``thread_series`` is outside
    ``KNOWN_THREAD_SERIES`` (typo/unrecognised series label)."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        value = record.get("thread_series")
        if value not in KNOWN_THREAD_SERIES:
            issues.append(
                ValidationIssue(
                    code="unknown_thread_series",
                    message=f"Unrecognised thread_series {value!r}",
                    record_index=index,
                    field="thread_series",
                )
            )
    return issues


def find_thread_minor_diameter_tolerance_violations(
    records: Sequence[Dict[str, Any]], tolerance_mm: float = 0.001,
) -> List[ValidationIssue]:
    """For ISO_METRIC records only: recompute the external (d3) and
    internal (D1) minor diameters via the central ISO 724 helper
    (``thread_geometry.py``) and flag a stored value that differs
    from the recomputed one by more than ``tolerance_mm``."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if not is_iso_metric_thread_record(record):
            continue
        diameter = record.get("nominal_diameter_mm")
        pitch = record.get("pitch_mm")
        if not isinstance(diameter, (int, float)) or not isinstance(pitch, (int, float)):
            continue
        expected_ext = basic_minor_diameter_external_mm(diameter, pitch)
        expected_int = basic_minor_diameter_internal_mm(diameter, pitch)
        for field_name, expected in (
            ("minor_diameter_external_mm", expected_ext),
            ("minor_diameter_internal_mm", expected_int),
        ):
            actual = record.get(field_name)
            if not isinstance(actual, (int, float)) or abs(actual - expected) > tolerance_mm:
                issues.append(
                    ValidationIssue(
                        code="minor_diameter_tolerance",
                        message=(
                            f"{field_name}={actual!r} differs from ISO 724 basic "
                            f"value {round(expected, 4)} by more than "
                            f"{tolerance_mm} mm"
                        ),
                        record_index=index,
                        field=field_name,
                    )
                )
    return issues


def find_thread_stress_area_tolerance_violations(
    records: Sequence[Dict[str, Any]], tolerance_mm2: float = 0.05,
) -> List[ValidationIssue]:
    """For ISO_METRIC records only: recompute the tensile stress area
    via the ISO 898-1 formula already recorded in each record's own
    ``stress_area_source`` (``0.7854*(d-0.9382P)^2``) and flag a
    stored ``stress_area_mm2`` that differs by more than
    ``tolerance_mm2``. Uses the same formula named in the data, not a
    new one -- this is a consistency check, not a re-derivation from
    a different formula."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if not is_iso_metric_thread_record(record):
            continue
        diameter = record.get("nominal_diameter_mm")
        pitch = record.get("pitch_mm")
        stored = record.get("stress_area_mm2")
        if not isinstance(diameter, (int, float)) or not isinstance(pitch, (int, float)):
            continue
        expected = 0.7854 * (diameter - 0.9382 * pitch) ** 2
        if not isinstance(stored, (int, float)) or abs(stored - expected) > tolerance_mm2:
            issues.append(
                ValidationIssue(
                    code="stress_area_tolerance",
                    message=(
                        f"stress_area_mm2={stored!r} differs from ISO 898-1 "
                        f"value {round(expected, 3)} by more than "
                        f"{tolerance_mm2} mm^2"
                    ),
                    record_index=index,
                    field="stress_area_mm2",
                )
            )
    return issues


def validate_thread_library(
    records: Sequence[Dict[str, Any]],
) -> ValidationReport:
    """Run every Faz 2.4.1A thread-specific check over ``records`` in
    one pass. Combines with (does not replace) ``validate_library`` /
    ``validate_schema`` above, which already cover the Faz-1.4/2.4.0
    generic checks (duplicate id, missing field, schema)."""
    issues: List[ValidationIssue] = []
    issues.extend(find_duplicate_thread_designation_pitch(records))
    issues.extend(find_non_positive_thread_dimensions(records))
    issues.extend(find_thread_designation_diameter_mismatches(records))
    issues.extend(find_thread_pitch_type_classification_mismatches(records))
    issues.extend(find_thread_schema_version_issues(records))
    issues.extend(find_thread_unknown_fields(records))
    issues.extend(find_thread_series_scope_issues(records))
    issues.extend(find_thread_minor_diameter_tolerance_violations(records))
    issues.extend(find_thread_stress_area_tolerance_violations(records))
    return ValidationReport(subject="Thread Library (Faz 2.4.1A)", issues=issues)


# ---------------------------------------------------------------------
# Faz 2.4.1B: bolt/nut engineering-database validation.
#
# Scoped to ``bolt library`` / ``nut library`` records and opt-in (not
# wired into ``validate_library`` / ``validate_records`` above, which
# stay Faz-1.4-generic and unchanged). Mirrors the Faz 2.4.1A
# thread-validation pattern: one ``find_*`` function per check, each
# returning a list of ``ValidationIssue``, plus a
# ``validate_bolt_library`` / ``validate_nut_library`` /
# ``validate_bolt_nut_compatibility_rules`` aggregator that runs every
# check in one pass.
# ---------------------------------------------------------------------

#: Recognised bolt property-class format, e.g. "8.8", "10.9", "12.9".
_BOLT_STRENGTH_CLASS_RE = re.compile(r"^\d{1,2}\.\d$")

#: Metric designation with an optional explicit fine-pitch suffix,
#: e.g. "M10" (implicit coarse) or "M10x1.25" (explicit pitch).
_BOLT_NUT_DESIGNATION_RE = re.compile(r"^M(\d+(?:\.\d+)?)(?:[xX](\d+(?:\.\d+)?))?$")

#: Coarse-pitch table (ISO 724), used to check an implicit-pitch
#: designation ("M10", no explicit "xP" suffix) against the pitch the
#: record actually declares. Independent from -- but numerically
#: identical to -- the live Thread Library data; kept as a local
#: constant so this check has no import-order dependency on
#: ``population.py`` (which itself imports ``validator`` -- see
#: ``population.validate_thread_library_records``).
_ISO_724_COARSE_PITCH_MM = {
    3: 0.5, 3.5: 0.6, 4: 0.7, 5: 0.8, 6: 1.0, 7: 1.0, 8: 1.25, 10: 1.5,
    12: 1.75, 14: 2.0, 16: 2.0, 18: 2.5, 20: 2.5, 22: 2.5, 24: 3.0,
    27: 3.0, 30: 3.5, 33: 3.5, 36: 4.0,
}

_HARDNESS_RANGE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)")


def find_duplicate_designation_standard_dimension(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag records that reuse the same (``designation``,
    ``source_standard``, ``nominal_diameter_mm`` or ``diameter_mm``)
    combination seen earlier -- the same physical part should not be
    entered twice under different ids."""
    seen: Dict[Any, int] = {}
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        dimension = record.get("nominal_diameter_mm", record.get("diameter_mm"))
        key = (record.get("designation"), record.get("source_standard"), dimension)
        if key in seen:
            issues.append(
                ValidationIssue(
                    code="duplicate_designation_standard_dimension",
                    message=(
                        f"Duplicate designation+standard+dimension {key!r} "
                        f"(first seen at index {seen[key]})"
                    ),
                    record_index=index,
                    field="designation",
                )
            )
        else:
            seen[key] = index
    return issues


def find_non_positive_nominal_diameter(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag records whose ``nominal_diameter_mm`` (falling back to the
    pre-existing ``diameter_mm``) is present but zero or negative.
    Records carrying neither field are skipped -- this checks the
    *value* of a declared diameter, not whether one was declared."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if "nominal_diameter_mm" not in record and "diameter_mm" not in record:
            continue
        value = record.get("nominal_diameter_mm", record.get("diameter_mm"))
        if not isinstance(value, (int, float)) or value <= 0:
            issues.append(
                ValidationIssue(
                    code="non_positive_nominal_diameter",
                    message=f"nominal diameter must be > 0, got {value!r}",
                    record_index=index,
                    field="nominal_diameter_mm",
                )
            )
    return issues


def find_non_positive_pitch(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """Flag records whose ``pitch_mm`` (falling back to
    ``pitch_coarse_mm`` for bolt records that predate the structured
    field) is present but zero or negative. Records carrying neither
    field are skipped."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if "pitch_mm" not in record and "pitch_coarse_mm" not in record:
            continue
        value = record.get("pitch_mm", record.get("pitch_coarse_mm"))
        if not isinstance(value, (int, float)) or value <= 0:
            issues.append(
                ValidationIssue(
                    code="non_positive_pitch",
                    message=f"pitch_mm must be > 0, got {value!r}",
                    record_index=index,
                    field="pitch_mm",
                )
            )
    return issues


def find_pitch_designation_mismatches(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag a record whose ``designation`` doesn't parse as a metric
    thread designation, or whose declared ``pitch_mm`` disagrees with
    the pitch implied by the designation: an explicit "MxxPyy" suffix
    must match ``pitch_mm`` exactly; a bare "Mxx" (implicit coarse)
    must match the ISO 724 coarse-pitch table for that diameter (only
    checked for diameters in that table -- see
    ``_ISO_724_COARSE_PITCH_MM``)."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        # Nut records prefix `designation` with the standard name
        # (e.g. "ISO 4032 M3"); `thread` is always the bare metric
        # designation ("M3") on both bolt and nut records -- prefer
        # it, falling back to `designation` for records without a
        # `thread` field.
        designation = record.get("thread") or record.get("designation", "")
        pitch = record.get("pitch_mm")
        if not isinstance(pitch, (int, float)):
            continue
        match = _BOLT_NUT_DESIGNATION_RE.match(designation.strip())
        if not match:
            issues.append(
                ValidationIssue(
                    code="unparseable_designation",
                    message=f"Not a parseable metric designation: {designation!r}",
                    record_index=index,
                    field="designation",
                )
            )
            continue
        diameter = float(match.group(1))
        explicit_pitch = match.group(2)
        expected: Optional[float]
        if explicit_pitch is not None:
            expected = float(explicit_pitch)
            if abs(pitch - expected) > 1e-6:
                issues.append(
                    ValidationIssue(
                        code="pitch_designation_mismatch",
                        message=(
                            f"designation {designation!r} implies pitch_mm="
                            f"{expected}, but record has {pitch!r}"
                        ),
                        record_index=index,
                        field="pitch_mm",
                    )
                )
        else:
            expected = _ISO_724_COARSE_PITCH_MM.get(diameter)
            if expected is not None and abs(pitch - expected) > 1e-6:
                issues.append(
                    ValidationIssue(
                        code="pitch_designation_mismatch",
                        message=(
                            f"designation {designation!r} implies coarse "
                            f"pitch_mm={expected}, but record has {pitch!r}"
                        ),
                        record_index=index,
                        field="pitch_mm",
                    )
                )
    return issues


def find_invalid_bolt_strength_class_format(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag bolt records whose ``property_class`` doesn't match the
    ISO 898-1 "x.y" format (e.g. "8.8", "10.9")."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        value = record.get("property_class", "")
        if not isinstance(value, str) or not _BOLT_STRENGTH_CLASS_RE.match(value):
            issues.append(
                ValidationIssue(
                    code="invalid_bolt_strength_class_format",
                    message=f"Not a valid ISO 898-1 bolt strength class: {value!r}",
                    record_index=index,
                    field="property_class",
                )
            )
    return issues


def find_invalid_nut_strength_class_format(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag nut records whose ``property_class`` is not one of the
    recognised ISO 898-2 class numbers (see ``KNOWN_NUT_CLASSES``)."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        value = record.get("property_class", "")
        if value not in KNOWN_NUT_CLASSES:
            issues.append(
                ValidationIssue(
                    code="invalid_nut_strength_class_format",
                    message=f"Not a recognised ISO 898-2 nut class: {value!r}",
                    record_index=index,
                    field="property_class",
                )
            )
    return issues


def find_non_positive_stress_area(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag records whose ``stress_area_mm2`` is present but not
    strictly positive."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if "stress_area_mm2" not in record:
            continue
        value = record["stress_area_mm2"]
        if not isinstance(value, (int, float)) or value <= 0:
            issues.append(
                ValidationIssue(
                    code="non_positive_stress_area",
                    message=f"stress_area_mm2 must be > 0, got {value!r}",
                    record_index=index,
                    field="stress_area_mm2",
                )
            )
    return issues


def find_bolt_head_geometry_inconsistencies(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag hex-headed bolt records where the head-across-corners
    dimension is not strictly greater than the head-across-flats
    dimension (a hex head's corner-to-corner span is always larger
    than its flat-to-flat span -- a physical consistency check, not a
    standard-table lookup). Scoped to ``head_type in {"Hex",
    "Flange"}`` -- socket-head and headless records reuse the same
    field names for a different geometric concept (the round head's
    own diameter, not a hex span) and are not comparable this way."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if record.get("head_type") not in ("Hex", "Flange"):
            continue
        flats = record.get("head_across_flats_mm")
        corners = record.get("head_across_corners_mm")
        if not isinstance(flats, (int, float)) or not isinstance(corners, (int, float)):
            continue
        if corners <= flats:
            issues.append(
                ValidationIssue(
                    code="head_geometry_inconsistent",
                    message=(
                        f"head_across_corners_mm={corners} must be > "
                        f"head_across_flats_mm={flats}"
                    ),
                    record_index=index,
                    field="head_across_corners_mm",
                )
            )
    return issues


def find_nut_width_geometry_inconsistencies(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Nut counterpart of ``find_bolt_head_geometry_inconsistencies``:
    ``width_across_corners_mm`` must be strictly greater than
    ``width_across_flats_mm`` when both are present."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        flats = record.get("width_across_flats_mm")
        corners = record.get("width_across_corners_mm")
        if not isinstance(flats, (int, float)) or not isinstance(corners, (int, float)):
            continue
        if corners <= flats:
            issues.append(
                ValidationIssue(
                    code="nut_width_geometry_inconsistent",
                    message=(
                        f"width_across_corners_mm={corners} must be > "
                        f"width_across_flats_mm={flats}"
                    ),
                    record_index=index,
                    field="width_across_corners_mm",
                )
            )
    return issues


def find_strength_ordering_violations(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag bolt records where the ISO 898-1 strength ordering
    ``proof_strength_mpa <= yield_strength_mpa <=
    minimum_tensile_strength_mpa`` is violated. Fields absent (older
    or non-bolt records) are skipped, not flagged."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        proof = record.get("proof_strength_mpa")
        yield_ = record.get("yield_strength_mpa")
        tensile = record.get("minimum_tensile_strength_mpa")
        values = [v for v in (proof, yield_, tensile) if v is not None]
        if len(values) < 2:
            continue
        if proof is not None and yield_ is not None and proof > yield_:
            issues.append(
                ValidationIssue(
                    code="strength_ordering_violation",
                    message=f"proof_strength_mpa={proof} > yield_strength_mpa={yield_}",
                    record_index=index,
                    field="proof_strength_mpa",
                )
            )
        if yield_ is not None and tensile is not None and yield_ > tensile:
            issues.append(
                ValidationIssue(
                    code="strength_ordering_violation",
                    message=(
                        f"yield_strength_mpa={yield_} > "
                        f"minimum_tensile_strength_mpa={tensile}"
                    ),
                    record_index=index,
                    field="yield_strength_mpa",
                )
            )
    return issues


def find_hardness_range_violations(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag records whose ``hardness_range`` string (e.g. "255-335
    HV") has a minimum greater than its maximum, or doesn't parse at
    all when non-empty."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        value = record.get("hardness_range", "")
        if not value:
            continue
        match = _HARDNESS_RANGE_RE.match(value.strip())
        if not match:
            issues.append(
                ValidationIssue(
                    code="unparseable_hardness_range",
                    message=f"Not a parseable hardness range: {value!r}",
                    record_index=index,
                    field="hardness_range",
                )
            )
            continue
        low, high = float(match.group(1)), float(match.group(2))
        if low > high:
            issues.append(
                ValidationIssue(
                    code="hardness_range_violation",
                    message=f"hardness_range min {low} > max {high}",
                    record_index=index,
                    field="hardness_range",
                )
            )
    return issues


def find_temperature_range_violations(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag records whose ``operating_temperature_min_c`` exceeds
    ``operating_temperature_max_c`` (both must be present)."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        low = record.get("operating_temperature_min_c")
        high = record.get("operating_temperature_max_c")
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
            continue
        if low > high:
            issues.append(
                ValidationIssue(
                    code="temperature_range_violation",
                    message=(
                        f"operating_temperature_min_c={low} > "
                        f"operating_temperature_max_c={high}"
                    ),
                    record_index=index,
                    field="operating_temperature_min_c",
                )
            )
    return issues


def find_missing_source(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """Flag records where neither ``source`` nor ``source_standard``
    is populated -- every record must be traceable to a source."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if not record.get("source") and not record.get("source_standard"):
            issues.append(
                ValidationIssue(
                    code="missing_source",
                    message="Neither source nor source_standard is populated",
                    record_index=index,
                    field="source",
                )
            )
    return issues


def find_verified_missing_revision(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag records marked ``validation_status == "validated"`` or
    ``verification_status == "verified"`` that have no ``revision``
    (year/date) recorded."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        is_verified = (
            record.get("validation_status") == "validated"
            or record.get("verification_status") == "verified"
        )
        if is_verified and not record.get("revision"):
            issues.append(
                ValidationIssue(
                    code="verified_missing_revision",
                    message="Verified record has no revision/year recorded",
                    record_index=index,
                    field="revision",
                )
            )
    return issues


#: Nut families/locking types that are lock nuts by design -- these
#: must declare a non-empty ``locking_principle``.
_LOCK_NUT_LOCKING_TYPES = frozenset({
    "Nylon insert", "All-metal (deformed thread)",
})


def find_lock_nut_missing_locking_principle(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag lock-nut records (identified by ``nut_family`` containing
    "lock nut" or a recognised locking ``locking_type``) that have no
    ``locking_principle`` populated."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        family = record.get("nut_family", "")
        locking_type = record.get("locking_type", "None")
        is_lock_nut = "lock nut" in family.lower() or locking_type in _LOCK_NUT_LOCKING_TYPES
        if is_lock_nut and not record.get("locking_principle"):
            issues.append(
                ValidationIssue(
                    code="lock_nut_missing_locking_principle",
                    message="Lock nut record has no locking_principle populated",
                    record_index=index,
                    field="locking_principle",
                )
            )
    return issues


def find_prevailing_torque_nut_missing_reuse_info(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag prevailing-torque nut records (identified by a non-empty
    ``prevailing_torque_category`` or a ``nut_family`` of "Prevailing
    torque nut") that have no ``reusable`` (True/False) declared."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        is_prevailing_torque = (
            bool(record.get("prevailing_torque_category"))
            or record.get("nut_family") == "Prevailing torque nut"
        )
        if is_prevailing_torque and record.get("reusable") is None:
            issues.append(
                ValidationIssue(
                    code="prevailing_torque_nut_missing_reuse_info",
                    message="Prevailing torque nut record has no reusable flag declared",
                    record_index=index,
                    field="reusable",
                )
            )
    return issues


def validate_bolt_library(records: Sequence[Dict[str, Any]]) -> ValidationReport:
    """Run every Faz 2.4.1B bolt-specific check over ``records`` in
    one pass."""
    issues: List[ValidationIssue] = []
    issues.extend(find_duplicate_ids(records))
    issues.extend(find_duplicate_designation_standard_dimension(records))
    issues.extend(find_non_positive_nominal_diameter(records))
    issues.extend(find_non_positive_pitch(records))
    issues.extend(find_pitch_designation_mismatches(records))
    issues.extend(find_invalid_bolt_strength_class_format(records))
    issues.extend(find_non_positive_stress_area(records))
    issues.extend(find_bolt_head_geometry_inconsistencies(records))
    issues.extend(find_strength_ordering_violations(records))
    issues.extend(find_hardness_range_violations(records))
    issues.extend(find_temperature_range_violations(records))
    issues.extend(find_missing_source(records))
    issues.extend(find_verified_missing_revision(records))
    return ValidationReport(subject="Bolt Library (Faz 2.4.1B)", issues=issues)


def validate_nut_library(records: Sequence[Dict[str, Any]]) -> ValidationReport:
    """Run every Faz 2.4.1B nut-specific check over ``records`` in one
    pass."""
    issues: List[ValidationIssue] = []
    issues.extend(find_duplicate_ids(records))
    issues.extend(find_duplicate_designation_standard_dimension(records))
    issues.extend(find_non_positive_nominal_diameter(records))
    issues.extend(find_non_positive_pitch(records))
    issues.extend(find_pitch_designation_mismatches(records))
    issues.extend(find_invalid_nut_strength_class_format(records))
    issues.extend(find_nut_width_geometry_inconsistencies(records))
    issues.extend(find_hardness_range_violations(records))
    issues.extend(find_temperature_range_violations(records))
    issues.extend(find_missing_source(records))
    issues.extend(find_verified_missing_revision(records))
    issues.extend(find_lock_nut_missing_locking_principle(records))
    issues.extend(find_prevailing_torque_nut_missing_reuse_info(records))
    return ValidationReport(subject="Nut Library (Faz 2.4.1B)", issues=issues)


# ---------------------------------------------------------------------
# Faz 2.4.1C: washer-specific checks
# ---------------------------------------------------------------------

# Metric bolt-size tokens such as "M3" or "M3.5" (no pitch suffix --
# ``compatible_bolt_sizes`` entries identify a nominal diameter only).
_BOLT_SIZE_PATTERN = re.compile(r"^M\d{1,3}(\.\d{1,2})?$")


def find_non_positive_washer_dimensions(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag washer records whose ``inner_diameter_mm``,
    ``outer_diameter_mm`` or ``thickness_mm`` is present but zero or
    negative. A field that is simply absent/``None`` is skipped --
    this checks the *value* of a declared dimension, not whether one
    was declared."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        for field_name in ("inner_diameter_mm", "outer_diameter_mm", "thickness_mm"):
            value = record.get(field_name)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or value <= 0:
                issues.append(
                    ValidationIssue(
                        code="non_positive_washer_dimension",
                        message=f"{field_name} must be > 0, got {value!r}",
                        record_index=index,
                        field=field_name,
                    )
                )
    return issues


def find_inner_diameter_not_less_than_outer(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag washer records where ``inner_diameter_mm`` is not
    strictly less than ``outer_diameter_mm`` (both must be present
    and numeric to be checked)."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        inner = record.get("inner_diameter_mm")
        outer = record.get("outer_diameter_mm")
        if not isinstance(inner, (int, float)) or not isinstance(outer, (int, float)):
            continue
        if inner >= outer:
            issues.append(
                ValidationIssue(
                    code="inner_diameter_not_less_than_outer",
                    message=f"inner_diameter_mm={inner} >= outer_diameter_mm={outer}",
                    record_index=index,
                    field="inner_diameter_mm",
                )
            )
    return issues


def find_invalid_compatible_bolt_size_format(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag washer records whose ``compatible_bolt_sizes`` entries do
    not match the ``M<diameter>`` pattern (e.g. "M3", "M3.5"). An
    empty/absent list is not flagged -- this checks the *format* of
    declared entries, not whether any were declared."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        sizes = record.get("compatible_bolt_sizes") or []
        for size in sizes:
            if not isinstance(size, str) or not _BOLT_SIZE_PATTERN.match(size):
                issues.append(
                    ValidationIssue(
                        code="invalid_compatible_bolt_size_format",
                        message=f"Not a valid bolt-size token: {size!r}",
                        record_index=index,
                        field="compatible_bolt_sizes",
                    )
                )
    return issues


def validate_washer_library(records: Sequence[Dict[str, Any]]) -> ValidationReport:
    """Run every Faz 2.4.1C washer-specific check over ``records`` in
    one pass, reusing the pre-existing generic checks
    (``find_duplicate_ids``, ``find_duplicate_designation_standard_dimension``,
    ``find_temperature_range_violations``, ``find_missing_source``)
    rather than duplicating their logic."""
    issues: List[ValidationIssue] = []
    issues.extend(find_duplicate_ids(records))
    issues.extend(find_duplicate_designation_standard_dimension(records))
    issues.extend(find_non_positive_washer_dimensions(records))
    issues.extend(find_inner_diameter_not_less_than_outer(records))
    issues.extend(find_invalid_compatible_bolt_size_format(records))
    issues.extend(find_temperature_range_violations(records))
    issues.extend(find_missing_source(records))
    return ValidationReport(subject="Washer Library (Faz 2.4.1C)", issues=issues)


# ---------------------------------------------------------------------
# Faz 2.4.1C: joint hardware checks (shell -- no domain-specific
# numeric standard rule is encoded here; see module note below)
# ---------------------------------------------------------------------


def find_non_positive_joint_hardware_dimensions(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag joint hardware records whose ``inner_diameter_mm``,
    ``outer_diameter_mm`` or ``length_mm`` is present but zero or
    negative. Generic positivity check -- reuses the same shape as
    :func:`find_non_positive_washer_dimensions`; no hardware-type-
    specific numeric rule (e.g. a particular dowel-pin tolerance
    class) is encoded here, per the Faz 2.4.1C brief."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        for field_name in ("inner_diameter_mm", "outer_diameter_mm", "length_mm"):
            value = record.get(field_name)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or value <= 0:
                issues.append(
                    ValidationIssue(
                        code="non_positive_joint_hardware_dimension",
                        message=f"{field_name} must be > 0, got {value!r}",
                        record_index=index,
                        field=field_name,
                    )
                )
    return issues


def find_missing_hardware_identity(
    records: Sequence[Dict[str, Any]],
) -> List[ValidationIssue]:
    """Flag joint hardware records with an empty ``designation`` or
    an empty ``source_standard`` -- every record must declare both
    what it is and what standard it comes from."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if not record.get("designation"):
            issues.append(
                ValidationIssue(
                    code="missing_designation",
                    message="designation is empty",
                    record_index=index,
                    field="designation",
                )
            )
        if not record.get("source_standard"):
            issues.append(
                ValidationIssue(
                    code="missing_source_standard",
                    message="source_standard is empty",
                    record_index=index,
                    field="source_standard",
                )
            )
    return issues


def validate_joint_hardware_library(
    records: Sequence[Dict[str, Any]],
) -> ValidationReport:
    """Run every Faz 2.4.1C joint-hardware check over ``records`` in
    one pass, reusing the pre-existing generic checks
    (``find_duplicate_ids``, ``find_temperature_range_violations``,
    ``find_missing_source``) rather than duplicating their logic.
    Deliberately encodes no hardware-type-specific numeric standard
    rule (e.g. dowel-pin tolerance classes) -- the data file has no
    records yet (see ``joint_hardware_library.py``), so there is
    nothing yet to validate such a rule against."""
    issues: List[ValidationIssue] = []
    issues.extend(find_duplicate_ids(records))
    issues.extend(find_non_positive_joint_hardware_dimensions(records))
    issues.extend(find_missing_hardware_identity(records))
    issues.extend(find_temperature_range_violations(records))
    issues.extend(find_missing_source(records))
    subject = "Joint Hardware Library (Faz 2.4.1C)"
    return ValidationReport(subject=subject, issues=issues)
