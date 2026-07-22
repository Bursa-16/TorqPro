"""SQLite schema and raw data-access functions for production_validation.

Route handlers must not execute SQL directly; they call service.py, which
calls this module. This module contains no business rules other than what
the database schema itself enforces (FK/UNIQUE/NOT NULL).
"""
from __future__ import annotations

from backend.app import conn

DDL = """
CREATE TABLE IF NOT EXISTS tool_references(
  id INTEGER PRIMARY KEY,
  tool_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  manufacturer TEXT,
  model TEXT,
  serial_number TEXT,
  tool_type TEXT,
  unit TEXT,
  range_min REAL,
  range_max REAL,
  calibration_status TEXT,
  last_calibration_date TEXT,
  next_calibration_date TEXT,
  certificate_reference TEXT,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS validation_studies(
  id INTEGER PRIMARY KEY,
  study_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  study_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  project_id INTEGER NOT NULL REFERENCES projects(id),
  joint_id INTEGER NOT NULL REFERENCES joints(id),
  joint_revision_id INTEGER NOT NULL REFERENCES joint_revisions(id),
  calculation_id INTEGER NOT NULL REFERENCES calculations(id),
  calculation_revision_id INTEGER NOT NULL REFERENCES calculation_revisions(id),
  specification_id INTEGER,
  created_by INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT,
  started_at TEXT,
  completed_at TEXT,
  approved_at TEXT,
  approved_by INTEGER,
  source TEXT,
  notes TEXT,
  version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS specification_snapshots(
  id INTEGER PRIMARY KEY,
  validation_study_id INTEGER NOT NULL REFERENCES validation_studies(id),
  characteristic_name TEXT NOT NULL,
  unit TEXT NOT NULL,
  nominal_value REAL,
  lower_spec_limit REAL NOT NULL,
  upper_spec_limit REAL NOT NULL,
  target_value REAL,
  source_standard TEXT,
  source_document TEXT,
  source_revision TEXT,
  rule_pack_version TEXT,
  calculation_snapshot_id INTEGER NOT NULL REFERENCES calculation_revisions(id),
  created_at TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS measurement_datasets(
  id INTEGER PRIMARY KEY,
  validation_study_id INTEGER NOT NULL REFERENCES validation_studies(id),
  dataset_code TEXT NOT NULL,
  name TEXT NOT NULL,
  characteristic_name TEXT NOT NULL,
  characteristic_type TEXT NOT NULL,
  unit TEXT NOT NULL,
  nominal_value REAL,
  lower_spec_limit REAL NOT NULL,
  upper_spec_limit REAL NOT NULL,
  target_value REAL,
  sampling_strategy TEXT,
  subgroup_size INTEGER,
  source_type TEXT,
  source_filename TEXT,
  source_checksum TEXT,
  imported_at TEXT,
  imported_by INTEGER,
  is_locked INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT,
  UNIQUE(validation_study_id, dataset_code)
);
CREATE TABLE IF NOT EXISTS measurement_records(
  id INTEGER PRIMARY KEY,
  dataset_id INTEGER NOT NULL REFERENCES measurement_datasets(id),
  sequence_number INTEGER NOT NULL,
  sample_id TEXT NOT NULL,
  subgroup_id TEXT,
  measured_value REAL NOT NULL,
  measured_at TEXT,
  production_date TEXT,
  shift TEXT,
  batch_number TEXT,
  lot_number TEXT,
  serial_number TEXT,
  part_number TEXT,
  station TEXT,
  line TEXT,
  machine TEXT,
  tool_id INTEGER REFERENCES tool_references(id),
  measurement_device_id INTEGER REFERENCES tool_references(id),
  operator_reference TEXT,
  environment_temperature REAL,
  environment_humidity REAL,
  is_valid INTEGER NOT NULL DEFAULT 1,
  invalid_reason TEXT,
  comment TEXT,
  correction_of_id INTEGER REFERENCES measurement_records(id),
  created_at TEXT NOT NULL,
  UNIQUE(dataset_id, sequence_number)
);
CREATE INDEX IF NOT EXISTS idx_vs_study_code ON validation_studies(study_code);
CREATE INDEX IF NOT EXISTS idx_vs_project_id ON validation_studies(project_id);
CREATE INDEX IF NOT EXISTS idx_vs_joint_id ON validation_studies(joint_id);
CREATE INDEX IF NOT EXISTS idx_vs_status ON validation_studies(status);
CREATE INDEX IF NOT EXISTS idx_md_validation_study_id ON measurement_datasets(validation_study_id);
CREATE INDEX IF NOT EXISTS idx_mr_dataset_id ON measurement_records(dataset_id);
CREATE INDEX IF NOT EXISTS idx_mr_sample_id ON measurement_records(sample_id);
CREATE INDEX IF NOT EXISTS idx_mr_subgroup_id ON measurement_records(subgroup_id);
CREATE INDEX IF NOT EXISTS idx_mr_measured_at ON measurement_records(measured_at);
CREATE INDEX IF NOT EXISTS idx_mr_batch_number ON measurement_records(batch_number);
CREATE INDEX IF NOT EXISTS idx_mr_lot_number ON measurement_records(lot_number);
CREATE INDEX IF NOT EXISTS idx_mr_tool_id ON measurement_records(tool_id);
CREATE INDEX IF NOT EXISTS idx_tool_references_tool_code ON tool_references(tool_code);
"""


def migrate(c) -> None:
    c.executescript(DDL)


# --- validation_studies -----------------------------------------------------

def fetch_study(c, study_id: int):
    return c.execute("SELECT * FROM validation_studies WHERE id=?", (study_id,)).fetchone()


def fetch_study_by_code(c, study_code: str):
    return c.execute(
        "SELECT * FROM validation_studies WHERE study_code=?", (study_code,)
    ).fetchone()


def list_studies(c, project_id: int | None = None, status: str | None = None):
    sql = "SELECT * FROM validation_studies WHERE 1=1"
    params: list = []
    if project_id is not None:
        sql += " AND project_id=?"
        params.append(project_id)
    if status is not None:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY id DESC"
    return c.execute(sql, params).fetchall()


# --- measurement_datasets ----------------------------------------------------

def fetch_dataset(c, dataset_id: int):
    return c.execute("SELECT * FROM measurement_datasets WHERE id=?", (dataset_id,)).fetchone()


def fetch_dataset_by_code(c, validation_study_id: int, dataset_code: str):
    return c.execute(
        "SELECT * FROM measurement_datasets WHERE validation_study_id=? AND dataset_code=?",
        (validation_study_id, dataset_code),
    ).fetchone()


def list_datasets(c, validation_study_id: int):
    return c.execute(
        "SELECT * FROM measurement_datasets WHERE validation_study_id=? ORDER BY id",
        (validation_study_id,),
    ).fetchall()


# --- measurement_records ------------------------------------------------------

def fetch_record(c, record_id: int):
    return c.execute("SELECT * FROM measurement_records WHERE id=?", (record_id,)).fetchone()


def list_records(c, dataset_id: int, valid_only: bool = False):
    sql = "SELECT * FROM measurement_records WHERE dataset_id=?"
    params = [dataset_id]
    if valid_only:
        sql += " AND is_valid=1"
    sql += " ORDER BY sequence_number"
    return c.execute(sql, params).fetchall()


def next_sequence_number(c, dataset_id: int) -> int:
    row = c.execute(
        "SELECT COALESCE(MAX(sequence_number),0)+1 n FROM measurement_records WHERE dataset_id=?",
        (dataset_id,),
    ).fetchone()
    return row["n"]


def count_records(c, dataset_id: int):
    row = c.execute(
        "SELECT COUNT(*) total, SUM(is_valid) valid FROM measurement_records WHERE dataset_id=?",
        (dataset_id,),
    ).fetchone()
    total = row["total"] or 0
    valid = row["valid"] or 0
    return total, valid


__all__ = [
    "migrate",
    "fetch_study",
    "fetch_study_by_code",
    "list_studies",
    "fetch_dataset",
    "fetch_dataset_by_code",
    "list_datasets",
    "fetch_record",
    "list_records",
    "next_sequence_number",
    "count_records",
    "conn",
]
