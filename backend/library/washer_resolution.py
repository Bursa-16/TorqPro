"""TorqPro Engineering Library - Faz 2.8.5 washer correction &
resolution workflow.

Additive, self-contained typed layer over a new ledger data file
(``backend/library/data/washer_resolution_ledger.json``), generated
deterministically by
``tools/generate_faz_2_8_5_washer_resolution_ledger.py`` from the Faz
2.8.4 provenance report. Mirrors the pattern already established by
``strength_classes.py`` (Faz 2.8.3): a dedicated Pydantic model plus a
lazily-cached JSON loader, not registered with
``backend.library.registry`` / ``backend.library.population`` (the
12-key population architecture is unchanged this phase).

Design constraints (Faz 2.8.5 task brief, enforced structurally):

  - This module never writes to ``washer_library.json`` and never
    estimates a geometric or mechanical washer value. It only tracks
    the *state of the review conversation* about a washer record.
  - ``WasherResolutionRecord`` uses ``extra="forbid"``: any field not
    in this schema -- including any washer geometry/material field
    such as ``inner_diameter_mm`` or ``hardness`` -- is rejected at
    parse time. A resolution record structurally cannot carry a
    washer-data mutation. See
    ``washer_resolution_validator.find_washer_data_mutation_attempt``
    for the equivalent pre-parse check over raw dicts.
  - ``resolved_at`` is a plain string, populated by a caller (or left
    empty) -- never auto-stamped with ``datetime.now()`` by this
    module, so nothing here is a source of non-determinism.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from .models import ConfidenceLevel

DATA_PATH = Path(__file__).resolve().parent / "data" / "washer_resolution_ledger.json"


class WasherIssueType(str, Enum):
    """Faz 2.8.5 classification of *why* a washer record needs
    review. A broader, resolution-workflow-facing vocabulary than the
    four Faz 2.8.4 ``reason_code`` values it is derived from (see
    ``tools/generate_faz_2_8_5_washer_resolution_ledger.py``'s
    ``REASON_CODE_TO_ISSUE_TYPE`` mapping) -- ``source_ambiguous``,
    ``duplicate_or_alias`` and ``other`` are not produced by that
    mapping today but are part of the declared vocabulary for any
    issue raised directly against the ledger in a future phase."""

    SOURCE_MISSING = "source_missing"
    SOURCE_AMBIGUOUS = "source_ambiguous"
    STANDARD_IDENTITY_AMBIGUOUS = "standard_identity_ambiguous"
    DIMENSIONAL_CONFLICT = "dimensional_conflict"
    DUPLICATE_OR_ALIAS = "duplicate_or_alias"
    VERIFICATION_PENDING = "verification_pending"
    OTHER = "other"


class WasherResolutionStatus(str, Enum):
    """Lifecycle status of one washer resolution record (task brief
    section 3's exact vocabulary)."""

    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    ACCEPTED_AS_IS = "accepted_as_is"
    BLOCKED_AUTHORITATIVE_SOURCE = "blocked_authoritative_source"
    REJECTED = "rejected"


#: Statuses that represent an unfinished review -- used by the report
#: module's "unresolved" count/list and by the validator's duplicate-
#: active-resolution check. ``blocked_authoritative_source`` counts as
#: unresolved (it is explicitly not a correctness claim either way).
ACTIVE_STATUSES = frozenset(
    {
        WasherResolutionStatus.OPEN,
        WasherResolutionStatus.UNDER_REVIEW,
        WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE,
    }
)

#: Statuses that represent a closed review, whatever the outcome.
TERMINAL_STATUSES = frozenset(
    {
        WasherResolutionStatus.RESOLVED,
        WasherResolutionStatus.ACCEPTED_AS_IS,
        WasherResolutionStatus.REJECTED,
    }
)


class WasherResolutionRecord(BaseModel):
    """One correction/resolution ledger entry for a single washer
    record + issue pairing.

    ``extra="forbid"`` is deliberate (see module docstring): this
    schema is a closed set of resolution-workflow fields, not an
    open-ended bag that could smuggle in a washer geometry override.
    """

    model_config = ConfigDict(extra="forbid")

    resolution_id: str
    washer_record_id: str
    issue_type: WasherIssueType
    reason_code: Optional[str] = None
    resolution_status: WasherResolutionStatus = WasherResolutionStatus.OPEN
    resolution_note: str = ""
    evidence_reference: str = ""
    resolved_standard: Optional[str] = None
    resolved_by: str = ""
    resolved_at: str = ""
    confidence_level: Optional[ConfidenceLevel] = None
    requires_authoritative_source: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe projection (enums -> their ``.value``)."""
        return self.model_dump(mode="json")


_CACHE: Optional[List[WasherResolutionRecord]] = None


def _raw_ledger() -> Dict[str, Any]:
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load() -> List[WasherResolutionRecord]:
    global _CACHE
    if _CACHE is None:
        payload = _raw_ledger()
        _CACHE = [
            WasherResolutionRecord.model_validate(raw)
            for raw in payload.get("records", [])
        ]
    return _CACHE


def reload() -> None:
    """Drop the cached ledger; the next read re-parses the JSON file
    from disk. Mirrors ``strength_classes.reload()``."""
    global _CACHE
    _CACHE = None


def list_washer_resolutions() -> List[WasherResolutionRecord]:
    """Return every resolution ledger record, in file order (sorted by
    ``washer_record_id`` at generation time -- see the generator
    tool's ``build_ledger_records``)."""
    return list(_load())


def get_washer_resolution(resolution_id: str) -> Optional[WasherResolutionRecord]:
    """Return the resolution record with this ``resolution_id``, or
    ``None`` if it does not exist."""
    for record in _load():
        if record.resolution_id == resolution_id:
            return record
    return None


def resolutions_for_washer_record(washer_record_id: str) -> List[WasherResolutionRecord]:
    """Every resolution ledger entry referencing this washer record id
    (normally zero or one today, since the Faz 2.8.5 seed data opens
    exactly one resolution per action_needed record, but a washer
    record may in principle accumulate more than one tracked issue)."""
    return [r for r in _load() if r.washer_record_id == washer_record_id]


def resolutions_by_status(status: WasherResolutionStatus) -> List[WasherResolutionRecord]:
    return [r for r in _load() if r.resolution_status == status]


def resolutions_by_issue_type(issue_type: WasherIssueType) -> List[WasherResolutionRecord]:
    return [r for r in _load() if r.issue_type == issue_type]


def count_by_status() -> Dict[str, int]:
    """Deterministic ``{status_value: count}``, including zero-count
    statuses (every :class:`WasherResolutionStatus` member is present
    in the returned dict, sorted by enum declaration order)."""
    counts: Dict[str, int] = {status.value: 0 for status in WasherResolutionStatus}
    for record in _load():
        counts[record.resolution_status.value] += 1
    return counts


def count_by_issue_type() -> Dict[str, int]:
    """Deterministic ``{issue_type_value: count}``, including
    zero-count issue types."""
    counts: Dict[str, int] = {issue.value: 0 for issue in WasherIssueType}
    for record in _load():
        counts[record.issue_type.value] += 1
    return counts


def unresolved_washer_resolutions() -> List[WasherResolutionRecord]:
    """Every resolution record whose status is in :data:`ACTIVE_STATUSES`."""
    return [r for r in _load() if r.resolution_status in ACTIVE_STATUSES]


def ledger_metadata() -> Dict[str, Any]:
    """The ledger file's own ``metadata`` block, unmodified."""
    return dict(_raw_ledger().get("metadata", {}))


__all__ = [
    "DATA_PATH",
    "WasherIssueType",
    "WasherResolutionStatus",
    "WasherResolutionRecord",
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "reload",
    "list_washer_resolutions",
    "get_washer_resolution",
    "resolutions_for_washer_record",
    "resolutions_by_status",
    "resolutions_by_issue_type",
    "count_by_status",
    "count_by_issue_type",
    "unresolved_washer_resolutions",
    "ledger_metadata",
]
