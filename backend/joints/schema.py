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
    """Apply joint-foundation DDL against an open sqlite3 connection."""
    c.executescript(DDL)
