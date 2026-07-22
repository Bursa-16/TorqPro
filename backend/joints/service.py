"""Minimum Joint / JointRevision service layer (Faz 2.5A prerequisite).

Scope: joint identity, joint-code uniqueness within a project, and a
draft -> review -> approved/rejected revision lifecycle with immutability
after approval. No component tree, no interface/load-case editor, no
calculation orchestration - those remain out of scope (see ADR 2.5A).
"""
from __future__ import annotations

import json

from backend.app import audit, conn, now_iso
from backend.joints.exceptions import (
    JointArchivedError,
    JointCodeConflictError,
    JointNotFoundError,
    JointRevisionConflictError,
    JointRevisionImmutableError,
    JointRevisionNotFoundError,
    JointRevisionStateError,
)
from backend.joints.schema import JOINT_REVISION_STATUSES, JOINT_STATUSES


def _row(r):
    return dict(r) if r is not None else None


def create_joint(
    project_id: int, joint_code: str, name: str, description: str | None, created_by: int | None
) -> dict:
    with conn() as c:
        project = c.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise JointNotFoundError(f"project {project_id} not found")
        exists = c.execute(
            "SELECT 1 FROM joints WHERE project_id=? AND joint_code=?",
            (project_id, joint_code),
        ).fetchone()
        if exists:
            raise JointCodeConflictError(
                f"joint_code '{joint_code}' already used in project {project_id}"
            )
        ts = now_iso()
        c.execute(
            "INSERT INTO joints(project_id,joint_code,name,description,status,created_by,"
            "created_at,updated_at) VALUES(?,?,?,?,'draft',?,?,?)",
            (project_id, joint_code, name, description, created_by, ts, ts),
        )
        c.commit()
        row = c.execute("SELECT * FROM joints WHERE id=last_insert_rowid()").fetchone()
    audit(created_by, "joint_create", joint_code)
    return _row(row)


def get_joint(joint_id: int) -> dict:
    with conn() as c:
        row = c.execute("SELECT * FROM joints WHERE id=?", (joint_id,)).fetchone()
    if not row:
        raise JointNotFoundError(f"joint {joint_id} not found")
    return _row(row)


def list_joints(project_id: int | None = None) -> list:
    with conn() as c:
        if project_id is not None:
            rows = c.execute(
                "SELECT * FROM joints WHERE project_id=? ORDER BY id", (project_id,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM joints ORDER BY id").fetchall()
    return [_row(r) for r in rows]


def archive_joint(joint_id: int, actor_id: int | None) -> dict:
    joint = get_joint(joint_id)
    if joint["status"] == "archived":
        return joint
    with conn() as c:
        c.execute(
            "UPDATE joints SET status='archived',archived_at=?,updated_at=? WHERE id=?",
            (now_iso(), now_iso(), joint_id),
        )
        c.commit()
        row = c.execute("SELECT * FROM joints WHERE id=?", (joint_id,)).fetchone()
    audit(actor_id, "joint_archive", str(joint_id))
    return _row(row)


def create_joint_revision(
    joint_id: int, snapshot: dict, change_summary: str | None, created_by: int | None
) -> dict:
    joint = get_joint(joint_id)
    if joint["status"] == "archived":
        raise JointArchivedError(f"joint {joint_id} is archived")
    with conn() as c:
        rev_no = c.execute(
            "SELECT COALESCE(MAX(revision_no),0)+1 n FROM joint_revisions WHERE joint_id=?",
            (joint_id,),
        ).fetchone()["n"]
        ts = now_iso()
        c.execute(
            "INSERT INTO joint_revisions(joint_id,revision_no,status,snapshot_json,change_summary,"
            "created_by,created_at) VALUES(?,?,'draft',?,?,?,?)",
            (joint_id, rev_no, json.dumps(snapshot or {}, ensure_ascii=False),
             change_summary, created_by, ts),
        )
        c.commit()
        row = c.execute("SELECT * FROM joint_revisions WHERE id=last_insert_rowid()").fetchone()
    audit(created_by, "joint_revision_create", f"joint={joint_id} rev={rev_no}")
    return _row(row)


def get_joint_revision(revision_id: int) -> dict:
    with conn() as c:
        row = c.execute("SELECT * FROM joint_revisions WHERE id=?", (revision_id,)).fetchone()
    if not row:
        raise JointRevisionNotFoundError(f"joint revision {revision_id} not found")
    return _row(row)


def submit_joint_revision(revision_id: int, actor_id: int | None) -> dict:
    rev = get_joint_revision(revision_id)
    if rev["status"] != "draft":
        raise JointRevisionStateError("only a draft revision can be submitted")
    with conn() as c:
        c.execute(
            "UPDATE joint_revisions SET status='review',submitted_at=? WHERE id=?",
            (now_iso(), revision_id),
        )
        c.commit()
        row = c.execute("SELECT * FROM joint_revisions WHERE id=?", (revision_id,)).fetchone()
    audit(actor_id, "joint_revision_submit", str(revision_id))
    return _row(row)


def approve_joint_revision(revision_id: int, actor_id: int | None) -> dict:
    rev = get_joint_revision(revision_id)
    if rev["status"] != "review":
        raise JointRevisionStateError("only a revision under review can be approved")
    if rev["created_by"] == actor_id:
        raise JointRevisionStateError("a reviewer cannot approve their own revision")
    ts = now_iso()
    with conn() as c:
        c.execute(
            "UPDATE joint_revisions SET status='approved',reviewed_by=?,reviewed_at=?,"
            "approved_at=? WHERE id=?",
            (actor_id, ts, ts, revision_id),
        )
        c.execute(
            "UPDATE joints SET current_revision_id=?,status='active',updated_at=? WHERE id=?",
            (revision_id, ts, rev["joint_id"]),
        )
        c.commit()
        row = c.execute("SELECT * FROM joint_revisions WHERE id=?", (revision_id,)).fetchone()
    audit(actor_id, "joint_revision_approve", str(revision_id))
    return _row(row)


def reject_joint_revision(revision_id: int, actor_id: int | None) -> dict:
    rev = get_joint_revision(revision_id)
    if rev["status"] != "review":
        raise JointRevisionStateError("only a revision under review can be rejected")
    if rev["created_by"] == actor_id:
        raise JointRevisionStateError("a reviewer cannot reject their own revision")
    with conn() as c:
        c.execute(
            "UPDATE joint_revisions SET status='rejected',reviewed_by=?,reviewed_at=? WHERE id=?",
            (actor_id, now_iso(), revision_id),
        )
        c.commit()
        row = c.execute("SELECT * FROM joint_revisions WHERE id=?", (revision_id,)).fetchone()
    audit(actor_id, "joint_revision_reject", str(revision_id))
    return _row(row)


def assert_revision_belongs_to_joint(joint_revision_id: int, joint_id: int) -> None:
    rev = get_joint_revision(joint_revision_id)
    if rev["joint_id"] != joint_id:
        raise JointRevisionConflictError(
            f"joint_revision {joint_revision_id} does not belong to joint {joint_id}"
        )


__all__ = [
    "JOINT_STATUSES",
    "JOINT_REVISION_STATUSES",
    "create_joint",
    "get_joint",
    "list_joints",
    "archive_joint",
    "create_joint_revision",
    "get_joint_revision",
    "submit_joint_revision",
    "approve_joint_revision",
    "reject_joint_revision",
    "assert_revision_belongs_to_joint",
    "JointNotFoundError",
    "JointCodeConflictError",
    "JointArchivedError",
    "JointRevisionNotFoundError",
    "JointRevisionConflictError",
    "JointRevisionImmutableError",
    "JointRevisionStateError",
]
