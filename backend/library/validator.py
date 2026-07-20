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
