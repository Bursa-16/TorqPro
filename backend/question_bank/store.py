"""Question Bank persistence: JSON canonical content + SQLite
lifecycle/audit.

Windows compatibility note (Faz 2.9.1 explicit constraint): unlike
``backend/library/washer_resolution_decisions_store.py`` (which uses
``fcntl.flock`` and is documented there as non-functional on Windows),
this module uses only a plain in-process ``threading.Lock`` for the
JSON side, plus atomic replace (temp file + ``os.replace``, which
*is* atomic on Windows too) for crash-safety. This does not protect
against two separate OS processes writing concurrently -- that
limitation is accepted deliberately in exchange for Windows
compatibility; the SQLite side (where true multi-actor concurrency
actually matters for this module -- reviewers deciding on questions)
uses SQLite's own locking instead, which is not affected by this
trade-off (see ``migrate``/``register_record``/``append_status_history``
below, all executed through the project's shared ``sqlite3``
connection).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

from .errors import ContentNotFoundError, DuplicateContentVersionError, DuplicateQuestionIdError
from .schema import QuestionRecord

DATA_PATH = Path(__file__).resolve().parent / "data" / "question_bank.v1.json"

_json_lock = threading.Lock()


# ---------------------------------------------------------------------
# JSON canonical content store
# ---------------------------------------------------------------------


def _checksum(payload: dict) -> str:
    """Canonical checksum: sha256 over sort_keys=True,
    ensure_ascii=False JSON -- same algorithm as
    ``backend.library.population.find_checksum_mismatches``, critical
    for correctness with Turkish characters (memory: a prior phase's
    ensure_ascii=True vs False mismatch caused silent checksum
    failures for Turkish-character records)."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _read_raw(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("questions", []) if isinstance(raw, dict) else raw


def _write_raw(path: Path, questions: List[dict]) -> None:
    """Atomic write: temp file in the same directory + os.replace, so
    a crash mid-write can never truncate or corrupt the existing file
    (atomic on POSIX and Windows alike -- unlike the fcntl-based
    locking this module deliberately avoids)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "questions": questions}
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def load_all_question_content(path: Optional[Path] = None) -> List[QuestionRecord]:
    """``path`` defaults to the *current* value of this module's
    ``DATA_PATH`` global, looked up at call time (not at function-
    definition time) so that tests can ``monkeypatch.setattr(store,
    "DATA_PATH", tmp_path)`` and have every caller that omits ``path``
    pick it up -- a ``path: Path = DATA_PATH`` default parameter would
    instead freeze the value present at import time."""
    resolved_path = path if path is not None else DATA_PATH
    raw_list = _read_raw(resolved_path)
    records = [QuestionRecord.model_validate(item) for item in raw_list]
    return records


def load_question_content(
    question_id: str, content_version: Optional[int] = None, path: Optional[Path] = None
) -> QuestionRecord:
    resolved_path = path if path is not None else DATA_PATH
    records = load_all_question_content(resolved_path)
    matches = [r for r in records if r.question_id == question_id]
    if not matches:
        raise ContentNotFoundError(f"question_id '{question_id}' JSON içeriğinde bulunamadı")
    if content_version is None:
        return max(matches, key=lambda r: r.content_version)
    for r in matches:
        if r.content_version == content_version:
            return r
    raise ContentNotFoundError(
        f"question_id '{question_id}' için content_version={content_version} bulunamadı"
    )


def save_question_content(record: QuestionRecord, path: Optional[Path] = None) -> None:
    """Append-only: raises :class:`DuplicateContentVersionError` if
    this exact ``(question_id, content_version)`` already exists.
    Never overwrites silently -- a content change must always arrive
    as a strictly new ``content_version``."""
    resolved_path = path if path is not None else DATA_PATH
    with _json_lock:
        existing = _read_raw(resolved_path)
        for item in existing:
            if item.get("question_id") == record.question_id and item.get(
                "content_version"
            ) == record.content_version:
                raise DuplicateContentVersionError(
                    f"{record.question_id}@v{record.content_version} JSON içeriğinde zaten mevcut "
                    "-- sessiz overwrite yasak"
                )
        existing.append(json.loads(record.model_dump_json()))
        _write_raw(resolved_path, existing)


# ---------------------------------------------------------------------
# SQLite lifecycle + audit store
# ---------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS question_bank_records(
  id INTEGER PRIMARY KEY,
  question_id TEXT NOT NULL,
  content_version INTEGER NOT NULL,
  validation_status TEXT NOT NULL DEFAULT 'draft',
  reviewed_by INTEGER,
  review_date TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(question_id, content_version)
);
CREATE INDEX IF NOT EXISTS idx_question_bank_records_question_id
  ON question_bank_records(question_id);
CREATE INDEX IF NOT EXISTS idx_question_bank_records_status
  ON question_bank_records(validation_status);

CREATE TABLE IF NOT EXISTS question_bank_status_history(
  id INTEGER PRIMARY KEY,
  question_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  revision_reason TEXT,
  actor TEXT NOT NULL,
  content_version_before INTEGER,
  content_version_after INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_question_bank_status_history_question_id
  ON question_bank_status_history(question_id, created_at);
"""


def migrate(c: sqlite3.Connection) -> None:
    """Additive, idempotent -- ``CREATE TABLE IF NOT EXISTS`` /
    ``CREATE INDEX IF NOT EXISTS`` throughout, matching
    ``backend.production_validation.repository.migrate``'s exact
    pattern. Safe to call on every startup and multiple times in the
    same test run."""
    c.executescript(DDL)


def register_record(
    c: sqlite3.Connection,
    *,
    question_id: str,
    content_version: int,
    now_iso: str,
    validation_status: str = "draft",
) -> None:
    """Raises :class:`DuplicateContentVersionError` (backstopped by
    the DB's own ``UNIQUE(question_id, content_version)`` constraint,
    not only by application-level checking -- Faz 2.9.0 Sec. 7's
    argument for SQLite's structural integrity guarantee over JSON's
    application-level-only duplicate checking)."""
    try:
        c.execute(
            "INSERT INTO question_bank_records"
            "(question_id,content_version,validation_status,created_at,updated_at)"
            " VALUES(?,?,?,?,?)",
            (question_id, content_version, validation_status, now_iso, now_iso),
        )
    except sqlite3.IntegrityError as exc:
        raise DuplicateContentVersionError(
            f"{question_id}@v{content_version} SQLite kaydı zaten mevcut"
        ) from exc


def fetch_record(c: sqlite3.Connection, question_id: str, content_version: int):
    return c.execute(
        "SELECT * FROM question_bank_records WHERE question_id=? AND content_version=?",
        (question_id, content_version),
    ).fetchone()


def update_record_status(
    c: sqlite3.Connection,
    *,
    question_id: str,
    content_version: int,
    new_status: str,
    now_iso: str,
    reviewed_by: Optional[str] = None,
    review_date: Optional[str] = None,
) -> None:
    c.execute(
        "UPDATE question_bank_records SET validation_status=?, updated_at=?,"
        " reviewed_by=COALESCE(?,reviewed_by), review_date=COALESCE(?,review_date)"
        " WHERE question_id=? AND content_version=?",
        (new_status, now_iso, reviewed_by, review_date, question_id, content_version),
    )


def append_status_history(
    c: sqlite3.Connection,
    *,
    question_id: str,
    from_status: Optional[str],
    to_status: str,
    actor: str,
    now_iso: str,
    revision_reason: Optional[str] = None,
    content_version_before: Optional[int] = None,
    content_version_after: Optional[int] = None,
) -> None:
    """Append-only by construction: no UPDATE/DELETE statement against
    this table exists anywhere in this module."""
    c.execute(
        "INSERT INTO question_bank_status_history"
        "(question_id,from_status,to_status,revision_reason,actor,"
        "content_version_before,content_version_after,created_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (
            question_id,
            from_status,
            to_status,
            revision_reason,
            actor,
            content_version_before,
            content_version_after,
            now_iso,
        ),
    )


def fetch_status_history(c: sqlite3.Connection, question_id: str) -> list:
    return c.execute(
        "SELECT * FROM question_bank_status_history WHERE question_id=? ORDER BY id",
        (question_id,),
    ).fetchall()


def fetch_publishable_candidates(c: sqlite3.Connection) -> list:
    """Returns SQLite rows with ``validation_status='validated'``
    only. ``deprecated`` and every other status are excluded here, at
    the query level -- not filtered later in Python -- so a
    programming mistake downstream cannot accidentally re-include
    them."""
    return c.execute(
        "SELECT * FROM question_bank_records WHERE validation_status='validated'"
    ).fetchall()
