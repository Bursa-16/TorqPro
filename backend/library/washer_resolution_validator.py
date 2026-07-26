"""TorqPro Engineering Library - Faz 2.8.5 washer resolution/
correction workflow validation.

Reuses the existing ``ValidationIssue`` dataclass from
``backend.library.validator`` (same shape, same conventions) rather
than inventing a new finding type -- mirrors the precedent already
set by ``strength_validator.py`` (Faz 2.8.3).

These checks run over **raw dicts**, before
``washer_resolution.WasherResolutionRecord`` Pydantic parsing (which
already enforces shape/type/``extra="forbid"``). That split matters:
a malformed raw ledger entry should produce a readable
``ValidationIssue`` here, not an opaque ``pydantic.ValidationError``
several layers away. Nothing here computes a physical result, invents
a washer dimension, or resolves an ISO/DIN identity question --
``resolved_standard`` is only ever read back, never assigned by this
module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .washer_resolution import (
    WasherIssueType,
    WasherResolutionStatus,
)
from .validator import ValidationIssue

#: Every field a raw washer library record (``WasherRecord`` /
#: ``LibraryRecordBase``) can carry that describes the washer itself
#: -- geometry, material, or any other engineering attribute. A
#: resolution ledger entry must never carry any of these keys: doing
#: so would be a silent attempt to mutate washer data through the
#: resolution workflow instead of ``washer_library.json`` itself.
#: Deliberately excludes fields the two schemas legitimately share by
#: *name coincidence* only if their meaning matches -- none do here,
#: this is an explicit, reviewed list, not derived by introspection
#: (introspecting ``WasherRecord.model_fields`` would also catch
#: administrative fields such as ``id``/``notes``/``source`` that a
#: resolution record is allowed to reference informationally).
WASHER_DATA_FIELDS = frozenset(
    {
        "designation",
        "inner_diameter_mm",
        "outer_diameter_mm",
        "thickness_mm",
        "hardness",
        "washer_type",
        "standard_organization",
        "material",
        "surface_finish",
        "coating",
        "compatible_bolt_sizes",
        "strength_class",
        "locking_principle",
        "operating_temperature_min_c",
        "operating_temperature_max_c",
    }
)

_VALID_STATUS_VALUES = frozenset(status.value for status in WasherResolutionStatus)
_VALID_ISSUE_TYPE_VALUES = frozenset(issue.value for issue in WasherIssueType)
_VALID_CONFIDENCE_LEVELS = frozenset({1, 2, 3, 4})


def _issue(code: str, message: str, index: int, field: str = "") -> ValidationIssue:
    return ValidationIssue(code=code, message=message, record_index=index, field=field or None)


def find_unknown_washer_record_id(
    records: Sequence[Dict[str, Any]], known_washer_record_ids: Sequence[str]
) -> List[ValidationIssue]:
    """Flag resolution entries whose ``washer_record_id`` does not
    exist in the live ``washer_library.json`` record set. Takes the
    known-id set as a parameter (rather than importing
    ``washer_library.json`` itself) so callers can validate against a
    specific snapshot -- e.g. a test fixture -- without this module
    hard-coding a data-file read."""
    known = set(known_washer_record_ids)
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        washer_record_id = record.get("washer_record_id")
        if washer_record_id not in known:
            issues.append(
                _issue(
                    "unknown_washer_record_id",
                    f"washer_record_id={washer_record_id!r} does not exist in "
                    "washer_library.json",
                    index,
                    "washer_record_id",
                )
            )
    return issues


def find_invalid_resolution_status(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """Flag entries whose ``resolution_status`` is not one of the six
    allowed values (open/under_review/resolved/accepted_as_is/
    blocked_authoritative_source/rejected)."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        status = record.get("resolution_status")
        if status not in _VALID_STATUS_VALUES:
            issues.append(
                _issue(
                    "invalid_resolution_status",
                    f"resolution_status={status!r} is not a recognised status",
                    index,
                    "resolution_status",
                )
            )
    return issues


def find_empty_issue_type(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """Flag entries with a missing, empty, or unrecognised
    ``issue_type``."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        issue_type = record.get("issue_type")
        if not issue_type or issue_type not in _VALID_ISSUE_TYPE_VALUES:
            issues.append(
                _issue(
                    "empty_or_invalid_issue_type",
                    f"issue_type={issue_type!r} must be a non-empty, recognised "
                    "issue type",
                    index,
                    "issue_type",
                )
            )
    return issues


def find_resolved_missing_note(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """A ``resolved`` entry must carry a non-empty ``resolution_note``
    explaining what was resolved and how."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if record.get("resolution_status") != WasherResolutionStatus.RESOLVED.value:
            continue
        note = record.get("resolution_note")
        if not note or not str(note).strip():
            issues.append(
                _issue(
                    "resolved_missing_note",
                    "resolution_status='resolved' requires a non-empty resolution_note",
                    index,
                    "resolution_note",
                )
            )
    return issues


def find_resolved_missing_evidence(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """A ``resolved`` entry must carry a non-empty
    ``evidence_reference``."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if record.get("resolution_status") != WasherResolutionStatus.RESOLVED.value:
            continue
        evidence = record.get("evidence_reference")
        if not evidence or not str(evidence).strip():
            issues.append(
                _issue(
                    "resolved_missing_evidence",
                    "resolution_status='resolved' requires a non-empty "
                    "evidence_reference",
                    index,
                    "evidence_reference",
                )
            )
    return issues


def find_duplicate_active_resolution(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """Flag more than one *active* (open/under_review/
    blocked_authoritative_source) resolution entry open against the
    same ``(washer_record_id, issue_type)`` pair -- two concurrent,
    unresolved conversations about the same issue on the same record
    is a workflow conflict, not a legitimate state. A closed entry
    (resolved/accepted_as_is/rejected) never conflicts with anything:
    re-opening an issue after closure is a new, separate entry, not a
    duplicate of the old one."""
    active_values = {
        WasherResolutionStatus.OPEN.value,
        WasherResolutionStatus.UNDER_REVIEW.value,
        WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE.value,
    }
    seen: Dict[tuple, int] = {}
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        if record.get("resolution_status") not in active_values:
            continue
        key = (record.get("washer_record_id"), record.get("issue_type"))
        if key in seen:
            issues.append(
                _issue(
                    "duplicate_active_resolution",
                    f"washer_record_id={key[0]!r} issue_type={key[1]!r} already has "
                    f"an active resolution at record_index={seen[key]}",
                    index,
                    "washer_record_id",
                )
            )
        else:
            seen[key] = index
    return issues


def find_blocked_status_flag_mismatch(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """``resolution_status='blocked_authoritative_source'`` requires
    ``requires_authoritative_source=True`` (and vice versa is *not*
    required -- a record may legitimately need an authoritative
    source while still sitting ``open``, before anyone has attempted
    to resolve it)."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        status = record.get("resolution_status")
        flag = record.get("requires_authoritative_source")
        if status == WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE.value and not flag:
            issues.append(
                _issue(
                    "blocked_status_requires_flag_mismatch",
                    "resolution_status='blocked_authoritative_source' requires "
                    "requires_authoritative_source=True",
                    index,
                    "requires_authoritative_source",
                )
            )
    return issues


def find_invalid_confidence_level(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """Flag a present-but-out-of-range ``confidence_level`` (must be
    1-4, matching ``backend.library.models.ConfidenceLevel``).
    ``None``/absent is not flagged -- confidence is optional until a
    reviewer has actually assessed the record."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        confidence = record.get("confidence_level")
        if confidence is None:
            continue
        if confidence not in _VALID_CONFIDENCE_LEVELS:
            issues.append(
                _issue(
                    "invalid_confidence_level",
                    f"confidence_level={confidence!r} must be one of 1, 2, 3, 4",
                    index,
                    "confidence_level",
                )
            )
    return issues


def find_washer_data_mutation_attempt(records: Sequence[Dict[str, Any]]) -> List[ValidationIssue]:
    """Flag a resolution entry that carries any key overlapping
    ``WASHER_DATA_FIELDS`` -- a resolution record attempting to smuggle
    in a washer geometry/material override instead of going through
    ``washer_library.json`` itself. This is a defence-in-depth check:
    ``WasherResolutionRecord``'s ``extra="forbid"`` already rejects
    these at Pydantic parse time, but this validator also runs over
    raw dicts that may never reach that parse step (e.g. a ledger file
    edited by hand before being loaded)."""
    issues: List[ValidationIssue] = []
    for index, record in enumerate(records):
        offending = sorted(set(record.keys()) & WASHER_DATA_FIELDS)
        if offending:
            issues.append(
                _issue(
                    "washer_data_mutation_attempt",
                    "resolution record must not carry washer data fields: "
                    f"{offending}",
                    index,
                    offending[0],
                )
            )
    return issues


def validate_washer_resolution_ledger(
    records: Sequence[Dict[str, Any]], known_washer_record_ids: Sequence[str]
):
    """Run every Faz 2.8.5 resolution-workflow check over ``records``
    in one pass. ``known_washer_record_ids`` should be the live
    ``washer_library.json`` id set (see
    :func:`find_unknown_washer_record_id`)."""
    from .validator import ValidationReport

    issues: List[ValidationIssue] = []
    issues.extend(find_unknown_washer_record_id(records, known_washer_record_ids))
    issues.extend(find_invalid_resolution_status(records))
    issues.extend(find_empty_issue_type(records))
    issues.extend(find_resolved_missing_note(records))
    issues.extend(find_resolved_missing_evidence(records))
    issues.extend(find_duplicate_active_resolution(records))
    issues.extend(find_blocked_status_flag_mismatch(records))
    issues.extend(find_invalid_confidence_level(records))
    issues.extend(find_washer_data_mutation_attempt(records))
    return ValidationReport(subject="Washer Resolution Ledger (Faz 2.8.5)", issues=issues)


__all__ = [
    "WASHER_DATA_FIELDS",
    "find_unknown_washer_record_id",
    "find_invalid_resolution_status",
    "find_empty_issue_type",
    "find_resolved_missing_note",
    "find_resolved_missing_evidence",
    "find_duplicate_active_resolution",
    "find_blocked_status_flag_mismatch",
    "find_invalid_confidence_level",
    "find_washer_data_mutation_attempt",
    "validate_washer_resolution_ledger",
]
