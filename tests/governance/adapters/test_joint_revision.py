"""Faz 2.8.12 Stage 4.2 tests:
backend.governance.adapters.joint_revision.

Uses the shared, already-migrated temp SQLite DB every other test in
this suite uses (set once by tests/conftest.py via TORQPRO_DB_PATH) --
matching tests/test_joints_foundation.py's own convention (no
per-test isolated-DB fixture needed for joints, unlike washer's
JSON-ledger monkeypatching).
"""

from __future__ import annotations

from backend.app import conn, now_iso
from backend.governance.adapters.joint_revision import (
    ProjectionOutcome,
    project_joint_revision,
)
from backend.governance.enums import LifecycleGroup, ReviewStatus
from backend.joints import service as joints_svc
from backend.joints.exceptions import JointCodeConflictError


def _make_project(name="Governance Joint Revision Test Project"):
    with conn() as c:
        c.execute(
            "INSERT INTO projects(name,status,created_at) VALUES(?,?,?)",
            (name, "open", now_iso()),
        )
        c.commit()
        return c.execute("SELECT id FROM projects WHERE id=last_insert_rowid()").fetchone()["id"]


def _make_joint_and_revision(joint_code_suffix):
    pid = _make_project()
    try:
        joint = joints_svc.create_joint(
            pid, f"J-GOV-{joint_code_suffix}", "Governance Test Joint", None, 1
        )
    except JointCodeConflictError:  # pragma: no cover - defensive, unique suffix expected
        joint = joints_svc.create_joint(
            pid, f"J-GOV-{joint_code_suffix}-2", "Governance Test Joint", None, 1
        )
    revision = joints_svc.create_joint_revision(joint["id"], {"thread": "M10"}, "initial", 1)
    return joint, revision


# ---------------------------------------------------------------------
# The exact four-state mapping
# ---------------------------------------------------------------------


def test_draft_maps_to_review_status_draft():
    _, revision = _make_joint_and_revision("draft")
    projection = project_joint_revision(revision["id"])
    assert projection.outcome == ProjectionOutcome.SUPPORTED.value
    assert projection.source_status == "draft"
    assert projection.canonical_status == ReviewStatus.DRAFT.value
    assert projection.lifecycle_group == LifecycleGroup.REVIEW


def test_review_maps_to_review_status_under_review():
    _, revision = _make_joint_and_revision("review")
    joints_svc.submit_joint_revision(revision["id"], 1)
    projection = project_joint_revision(revision["id"])
    assert projection.outcome == ProjectionOutcome.SUPPORTED.value
    assert projection.source_status == "review"
    assert projection.canonical_status == ReviewStatus.UNDER_REVIEW.value


def test_approved_maps_to_review_status_approved():
    _, revision = _make_joint_and_revision("approved")
    joints_svc.submit_joint_revision(revision["id"], 1)
    joints_svc.approve_joint_revision(revision["id"], 2)
    projection = project_joint_revision(revision["id"])
    assert projection.outcome == ProjectionOutcome.SUPPORTED.value
    assert projection.source_status == "approved"
    assert projection.canonical_status == ReviewStatus.APPROVED.value


def test_rejected_maps_to_review_status_rejected():
    _, revision = _make_joint_and_revision("rejected")
    joints_svc.submit_joint_revision(revision["id"], 1)
    joints_svc.reject_joint_revision(revision["id"], 2)
    projection = project_joint_revision(revision["id"])
    assert projection.outcome == ProjectionOutcome.SUPPORTED.value
    assert projection.source_status == "rejected"
    assert projection.canonical_status == ReviewStatus.REJECTED.value


def test_all_four_states_covered_by_a_single_source_of_truth_table():
    from backend.governance.adapters.joint_revision import _STATUS_MAP
    from backend.joints.schema import JOINT_REVISION_STATUSES

    assert set(_STATUS_MAP.keys()) == set(JOINT_REVISION_STATUSES)
    assert len(_STATUS_MAP) == 4


# ---------------------------------------------------------------------
# not_found / unsupported / invalid classification -- never guessed
# ---------------------------------------------------------------------


def test_nonexistent_revision_id_is_not_found():
    projection = project_joint_revision(999999999)
    assert projection.outcome == ProjectionOutcome.NOT_FOUND.value
    assert projection.source_status is None
    assert projection.canonical_status is None
    assert projection.lifecycle_group is None


def test_unknown_status_string_is_unsupported_not_guessed(monkeypatch):
    """A status value outside the closed vocabulary must never be
    silently mapped to the 'nearest' canonical status."""
    import backend.joints.service as joints_service_module

    _, revision = _make_joint_and_revision("unknown-status")

    def _fake_get_joint_revision(revision_id):
        return {"id": revision_id, "status": "some_future_status_not_in_vocabulary"}

    monkeypatch.setattr(joints_service_module, "get_joint_revision", _fake_get_joint_revision)

    projection = project_joint_revision(revision["id"])
    assert projection.outcome == ProjectionOutcome.UNSUPPORTED_STATUS.value
    assert projection.source_status == "some_future_status_not_in_vocabulary"
    assert projection.canonical_status is None
    assert projection.safe_reason is not None


def test_missing_status_field_is_invalid_source_record(monkeypatch):
    import backend.joints.service as joints_service_module

    def _fake_get_joint_revision(revision_id):
        return {"id": revision_id}  # no "status" key at all

    monkeypatch.setattr(joints_service_module, "get_joint_revision", _fake_get_joint_revision)

    projection = project_joint_revision(1)
    assert projection.outcome == ProjectionOutcome.INVALID_SOURCE_RECORD.value
    assert projection.canonical_status is None


def test_non_string_status_field_is_invalid_source_record(monkeypatch):
    import backend.joints.service as joints_service_module

    def _fake_get_joint_revision(revision_id):
        return {"id": revision_id, "status": 12345}

    monkeypatch.setattr(joints_service_module, "get_joint_revision", _fake_get_joint_revision)

    projection = project_joint_revision(1)
    assert projection.outcome == ProjectionOutcome.INVALID_SOURCE_RECORD.value


def test_non_dict_record_is_invalid_source_record(monkeypatch):
    import backend.joints.service as joints_service_module

    monkeypatch.setattr(joints_service_module, "get_joint_revision", lambda revision_id: None)

    projection = project_joint_revision(1)
    assert projection.outcome == ProjectionOutcome.INVALID_SOURCE_RECORD.value


def test_source_read_failure_is_source_unavailable_not_a_raw_exception(monkeypatch):
    import backend.joints.service as joints_service_module

    def _boom(revision_id):
        raise RuntimeError("simulated sqlite3.OperationalError: disk I/O error at /secret/path")

    monkeypatch.setattr(joints_service_module, "get_joint_revision", _boom)

    projection = project_joint_revision(1)
    assert projection.outcome == ProjectionOutcome.SOURCE_UNAVAILABLE.value
    assert "/secret/path" not in (projection.safe_reason or "")
    assert "OperationalError" not in (projection.safe_reason or "")


# ---------------------------------------------------------------------
# Read-only boundary / never raises
# ---------------------------------------------------------------------


def test_projection_never_raises_for_any_input():
    for bad_id in (-1, 0, 999999999):
        result = project_joint_revision(bad_id)
        assert result.outcome in {o.value for o in ProjectionOutcome}


def test_projection_does_not_mutate_the_source_revision():
    _, revision = _make_joint_and_revision("immutable-check")
    before = joints_svc.get_joint_revision(revision["id"])
    project_joint_revision(revision["id"])
    project_joint_revision(revision["id"])
    after = joints_svc.get_joint_revision(revision["id"])
    assert before == after


def test_result_never_contains_reviewed_by_or_internal_ids_beyond_the_contract():
    """The projection exposes only the documented fields -- extra=
    'forbid' on the Pydantic model already enforces this structurally,
    exercised here."""
    _, revision = _make_joint_and_revision("field-contract")
    projection = project_joint_revision(revision["id"])
    assert set(projection.model_dump().keys()) == {
        "source_system",
        "joint_revision_id",
        "source_status",
        "lifecycle_group",
        "canonical_status",
        "outcome",
        "safe_reason",
    }


# ---------------------------------------------------------------------
# Existing joint revision business behaviour unchanged
# ---------------------------------------------------------------------


def test_existing_self_approval_rule_still_enforced_independently_of_governance():
    """The adapter never touches this rule -- it lives entirely in
    backend.joints.service, exercised here only as a regression guard
    that Stage 4.2 changed nothing about it."""
    from backend.joints.exceptions import JointRevisionStateError

    _, revision = _make_joint_and_revision("self-approval")
    joints_svc.submit_joint_revision(revision["id"], 1)
    try:
        joints_svc.approve_joint_revision(revision["id"], 1)
        assert False, "expected JointRevisionStateError (reviewer == submitter)"
    except JointRevisionStateError:
        pass
    # Still projectable afterward, still 'review' (unapproved).
    projection = project_joint_revision(revision["id"])
    assert projection.source_status == "review"
