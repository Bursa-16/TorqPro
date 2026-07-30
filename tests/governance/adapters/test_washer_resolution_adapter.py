"""Faz 2.8.11 Stage 5 tests: washer resolution compatibility adapter.

Read-only against the real, committed washer resolution ledgers (the
same data the existing Faz 2.8.9 workflow already reads) -- this
adapter must never write anywhere, so these tests assert ledger
content is byte-identical before and after every call.
"""

from __future__ import annotations

from pathlib import Path

from backend.governance.adapters import (
    AdapterSourceRecordNotFoundError,
    CompatibilityProjection,
    MappingQuality,
    project_washer_resolution,
)
from backend.governance.enums import LifecycleGroup, ResolutionStatus
from backend.library import washer_resolution as wr

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LEDGER_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_resolution_ledger.json"
DECISIONS_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_resolution_decisions.json"


def _ledger_snapshot():
    ledger = LEDGER_PATH.read_bytes() if LEDGER_PATH.exists() else None
    decisions = DECISIONS_PATH.read_bytes() if DECISIONS_PATH.exists() else None
    return ledger, decisions


def test_projects_a_real_open_record_as_exact():
    records = wr.list_washer_resolutions()
    open_record = next(
        r for r in records if r.resolution_status == wr.WasherResolutionStatus.OPEN
    )
    projection = project_washer_resolution(open_record.resolution_id)
    assert projection.source_system == "washer_resolution"
    assert projection.source_record_id == open_record.resolution_id
    assert projection.source_status == "open"
    assert projection.canonical_status == ResolutionStatus.OPEN.value
    assert projection.lifecycle_group == LifecycleGroup.RESOLUTION
    assert projection.mapping_quality == MappingQuality.EXACT


def test_projects_blocked_authoritative_source_as_unsupported():
    records = wr.list_washer_resolutions()
    blocked = [
        r
        for r in records
        if r.resolution_status == wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE
    ]
    assert blocked, "fixture assumption: at least one blocked_authoritative_source record exists"
    projection = project_washer_resolution(blocked[0].resolution_id)
    assert projection.mapping_quality == MappingQuality.UNSUPPORTED
    assert projection.canonical_status is None
    assert projection.lifecycle_group is None


def test_unknown_resolution_id_raises_not_found():
    try:
        project_washer_resolution("NOT-A-REAL-RESOLUTION-ID")
        assert False, "expected AdapterSourceRecordNotFoundError"
    except AdapterSourceRecordNotFoundError as exc:
        assert exc.source_system == "washer_resolution"
        assert exc.source_record_id == "NOT-A-REAL-RESOLUTION-ID"


def test_mapping_quality_is_always_from_closed_vocabulary():
    for record in wr.list_washer_resolutions():
        projection = project_washer_resolution(record.resolution_id)
        assert projection.mapping_quality in MappingQuality.ALL


def test_unsupported_mapping_never_carries_a_guessed_canonical_status():
    for record in wr.list_washer_resolutions():
        projection = project_washer_resolution(record.resolution_id)
        if projection.mapping_quality == MappingQuality.UNSUPPORTED:
            assert projection.canonical_status is None
            assert projection.lifecycle_group is None


def test_projection_never_writes_to_source_ledgers():
    before = _ledger_snapshot()
    for record in wr.list_washer_resolutions()[:10]:
        project_washer_resolution(record.resolution_id)
    after = _ledger_snapshot()
    assert before == after


def test_projection_rejects_unknown_fields():
    """extra='forbid' on CompatibilityProjection -- closed schema."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CompatibilityProjection(
            source_system="x",
            source_record_id="y",
            source_status="open",
            mapping_quality=MappingQuality.EXACT,
            metadata={},
            unexpected_field="not allowed",
        )


def test_metadata_includes_washer_record_id_and_issue_type():
    records = wr.list_washer_resolutions()
    projection = project_washer_resolution(records[0].resolution_id)
    assert "washer_record_id" in projection.metadata
    assert "issue_type" in projection.metadata
    assert "decision_count" in projection.metadata


def test_adapter_does_not_write_a_governance_event(tmp_path):
    """Calling the adapter must never append to a governance event
    store, even incidentally -- there is no store parameter on
    project_washer_resolution() at all, so this is structurally
    guaranteed; this test documents that guarantee explicitly."""
    import inspect

    sig = inspect.signature(project_washer_resolution)
    assert "store" not in sig.parameters
