"""SQLite schema for the joint foundation layer.

Mirrors the migration convention already used in backend/app.py::migrate()
(idempotent CREATE TABLE IF NOT EXISTS, executed against the same database).
"""
from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS joints(
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  joint_code TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  current_revision_id INTEGER,
  created_by INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT,
  archived_at TEXT,
  UNIQUE(project_id, joint_code)
);
CREATE TABLE IF NOT EXISTS joint_revisions(
  id INTEGER PRIMARY KEY,
  joint_id INTEGER NOT NULL REFERENCES joints(id),
  revision_no INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  snapshot_json TEXT,
  change_summary TEXT,
  created_by INTEGER,
  created_at TEXT NOT NULL,
  submitted_at TEXT,
  reviewed_by INTEGER,
  reviewed_at TEXT,
  approved_at TEXT,
  idempotency_key TEXT,
  UNIQUE(joint_id, revision_no)
);
CREATE INDEX IF NOT EXISTS idx_joints_project_id ON joints(project_id);
CREATE INDEX IF NOT EXISTS idx_joints_status ON joints(status);
CREATE INDEX IF NOT EXISTS idx_joint_revisions_joint_id ON joint_revisions(joint_id);
CREATE INDEX IF NOT EXISTS idx_joint_revisions_status ON joint_revisions(status);
"""

JOINT_STATUSES = ("draft", "active", "superseded", "archived")
JOINT_REVISION_STATUSES = ("draft", "review", "approved", "rejected")


def migrate(c) -> None:
    """Apply joint-foundation DDL against an open sqlite3 connection.

    Faz 2.8.17 Stage 1: additive, backward-compatible extension. A
    fresh database gets ``idempotency_key`` directly from the
    ``CREATE TABLE`` DDL above; an existing database (created before
    this column existed) is backfilled with an ``ALTER TABLE ... ADD
    COLUMN`` check, mirroring the identical idiom already used by
    ``backend.app::migrate()`` for ``calculations.project_id`` and
    ``audit_log.request_id`` (``PRAGMA table_info`` presence check,
    then a conditional ``ALTER TABLE ADD COLUMN``). Existing rows are
    never touched; the new column is nullable and defaults to NULL on
    every pre-existing row, so old records remain valid and unaffected.

    The partial unique index is created last, after the column is
    guaranteed to exist on both fresh and pre-existing databases --
    SQLite has no ``ADD CONSTRAINT``, so a composite ``UNIQUE`` on the
    table itself cannot be added without a full table rebuild; a
    partial unique index (``WHERE idempotency_key IS NOT NULL``)
    achieves the same guarantee additively: at most one row per
    ``(joint_id, idempotency_key)`` pair among rows that actually set
    a key, while rows with a NULL key (the default, and every
    pre-2.8.17 row) are excluded from the index entirely and may
    repeat without limit. ``CREATE UNIQUE INDEX IF NOT EXISTS`` makes
    re-running this migration idempotent, exactly like every
    ``CREATE TABLE IF NOT EXISTS`` above.
    """
    c.executescript(DDL)
    cols = [r["name"] for r in c.execute("PRAGMA table_info(joint_revisions)").fetchall()]
    if "idempotency_key" not in cols:
        c.execute("ALTER TABLE joint_revisions ADD COLUMN idempotency_key TEXT")
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_joint_revisions_idempotency_key "
        "ON joint_revisions(joint_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
    )
