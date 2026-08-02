"""Minimum Joint / JointRevision service layer (Faz 2.5A prerequisite).

Scope: joint identity, joint-code uniqueness within a project, and a
draft -> review -> approved/rejected revision lifecycle with immutability
after approval. No component tree, no interface/load-case editor, no
calculation orchestration - those remain out of scope (see ADR 2.5A).
"""
from __future__ import annotations

import json
import sqlite3

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


def list_joint_revisions(joint_id: int | None = None) -> list:
    """Read-only listing of joint revision records, optionally
    filtered by ``joint_id`` (Faz 2.8.14 Stage 2 — additive; mirrors
    :func:`list_joints`'s existing filter/ordering convention exactly,
    no new convention introduced).

    - Read-only: never inserts, updates, or deletes any row; never
      calls ``c.commit()``; no side effect of any kind.
    - Deterministic ordering: results are always returned in ascending
      revision ``id`` order, the same convention :func:`list_joints`
      already uses for joints.
    - Optional filter: ``joint_id=None`` (the default) returns every
      joint revision record across all joints; a given ``joint_id``
      restricts the result to that joint's own revisions only.
    - Empty-list behaviour: an unknown or non-matching ``joint_id``
      returns ``[]``, never an exception -- this function performs no
      existence check on ``joint_id``, exactly like
      ``list_joints(project_id=...)``'s existing behaviour for an
      unknown ``project_id``.
    - Every row has the same shape :func:`get_joint_revision` already
      returns (via the shared ``_row()`` conversion), so a caller that
      already knows that shape needs no new parsing logic.
    """
    with conn() as c:
        if joint_id is not None:
            rows = c.execute(
                "SELECT * FROM joint_revisions WHERE joint_id=? ORDER BY id", (joint_id,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM joint_revisions ORDER BY id").fetchall()
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


def _match_existing_idempotent_revision(
    c, joint_id: int, idempotency_key: str, normalized_snapshot: dict,
    change_summary: str | None, created_by: int | None,
) -> dict | None:
    """Faz 2.8.17 Stage 1 helper: look up any existing revision already
    recorded under ``(joint_id, idempotency_key)``.

    - No existing row for this key on this joint: returns ``None`` --
      caller proceeds to create one.
    - An existing row whose ``(snapshot, change_summary, created_by)``
      matches the incoming request *semantically* (dict equality on
      the parsed snapshot, not a raw string/hash comparison, so key
      order never affects the result): returns that row unchanged --
      this is a safe retry replay, not a new write.
    - An existing row whose request differs on any of those three
      fields: raises :class:`JointRevisionConflictError` -- the same
      key was reused for a materially different request, which is not
      idempotency, it is a key collision. The error message never
      includes the snapshot content, a file path, SQL, or a raw
      driver exception -- only a fixed, generic sentence.
    """
    existing = c.execute(
        "SELECT * FROM joint_revisions WHERE joint_id=? AND idempotency_key=?",
        (joint_id, idempotency_key),
    ).fetchone()
    if existing is None:
        return None
    existing_row = _row(existing)
    existing_snapshot = json.loads(existing_row["snapshot_json"] or "{}")
    if (
        existing_snapshot == normalized_snapshot
        and existing_row["change_summary"] == change_summary
        and existing_row["created_by"] == created_by
    ):
        return existing_row
    raise JointRevisionConflictError(
        "idempotency_key already used for this joint with a different request"
    )


def create_joint_revision(
    joint_id: int,
    snapshot: dict,
    change_summary: str | None,
    created_by: int | None,
    *,
    idempotency_key: str | None = None,
) -> dict:
    """Create a draft joint revision.

    Faz 2.8.17 Stage 1: ``idempotency_key`` is a new, keyword-only,
    optional parameter (default ``None``) -- every existing positional
    call site and test is unaffected, and the ``idempotency_key is
    None`` path below is byte-for-byte the same behaviour this
    function always had (one new revision per call, no lookup, no
    extra column written beyond its NULL default).

    When ``idempotency_key`` is provided, this call becomes a safe
    retry target: the same ``(joint_id, idempotency_key)`` pair with
    the same ``(snapshot, change_summary, created_by)`` returns the
    already-created revision instead of creating a second one (no new
    revision_no consumed, no second "joint_revision_create" audit
    entry); the same key with a *different* request raises
    :class:`JointRevisionConflictError` instead of silently
    overwriting or silently creating a duplicate. A different
    ``joint_id`` may reuse the same key freely -- the uniqueness scope
    is per-joint, matching the partial unique index in
    ``backend.joints.schema``.
    """
    joint = get_joint(joint_id)
    normalized_snapshot = snapshot or {}

    with conn() as c:
        if idempotency_key is not None:
            existing_row = _match_existing_idempotent_revision(
                c, joint_id, idempotency_key, normalized_snapshot, change_summary, created_by,
            )
            if existing_row is not None:
                return existing_row

        if joint["status"] == "archived":
            raise JointArchivedError(f"joint {joint_id} is archived")

        rev_no = c.execute(
            "SELECT COALESCE(MAX(revision_no),0)+1 n FROM joint_revisions WHERE joint_id=?",
            (joint_id,),
        ).fetchone()["n"]
        ts = now_iso()
        snapshot_json = json.dumps(normalized_snapshot, ensure_ascii=False)

        if idempotency_key is None:
            c.execute(
                "INSERT INTO joint_revisions(joint_id,revision_no,status,snapshot_json,"
                "change_summary,created_by,created_at) VALUES(?,?,'draft',?,?,?,?)",
                (joint_id, rev_no, snapshot_json, change_summary, created_by, ts),
            )
            c.commit()
        else:
            # Concurrency backstop (Stage 0 Sec. 5): the SELECT above and
            # this INSERT are not atomic across processes/threads, so a
            # concurrent writer could win the same (joint_id,
            # idempotency_key) pair between our lookup and our insert.
            # The partial unique index (backend.joints.schema) is the
            # real guarantee; this except clause only translates that
            # raw sqlite3.IntegrityError into the same safe, generic
            # JointRevisionConflictError (or a successful replay, if the
            # concurrent writer's request was semantically identical to
            # ours) that a non-racing caller already sees above -- a
            # caller never needs a sqlite-specific except clause of its
            # own to use this function safely.
            try:
                c.execute(
                    "INSERT INTO joint_revisions(joint_id,revision_no,status,snapshot_json,"
                    "change_summary,created_by,created_at,idempotency_key) "
                    "VALUES(?,?,'draft',?,?,?,?,?)",
                    (joint_id, rev_no, snapshot_json, change_summary, created_by, ts,
                     idempotency_key),
                )
                c.commit()
            except sqlite3.IntegrityError:
                c.rollback()
                existing_row = _match_existing_idempotent_revision(
                    c, joint_id, idempotency_key, normalized_snapshot, change_summary,
                    created_by,
                )
                if existing_row is not None:
                    return existing_row
                raise JointRevisionConflictError(
                    "joint revision could not be created due to a conflicting write"
                ) from None
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
    "list_joint_revisions",
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
