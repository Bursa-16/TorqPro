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

# Faz 2.9.4: columns added to ``question_bank_records`` for soft-delete
# / archive lifecycle management. Listed once here as the single
# source of truth for both the fresh-DB DDL below and the idempotent
# ALTER-TABLE migration path used against pre-2.9.4 databases (see
# ``migrate()``).
_LIFECYCLE_MANAGEMENT_COLUMNS = (
    ("is_deleted", "INTEGER NOT NULL DEFAULT 0"),
    ("archived_at", "TEXT"),
    ("archived_by", "TEXT"),
    ("modified_at", "TEXT"),
    ("modified_by", "TEXT"),
)

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


def _delete_question_content_version(
    question_id: str, content_version: int, path: Optional[Path] = None
) -> bool:
    """Faz 2.9.3 failure-compensation helper. **Not** a general edit/
    delete capability -- underscore-prefixed and used from exactly one
    call site (``backend.question_bank.service.update_question``'s
    SQLite-write-failure rollback path) to undo *that same call's own*
    JSON append when the paired SQLite lifecycle registration failed
    and was rolled back.

    This does not weaken the append-only contract
    :func:`save_question_content` enforces: that contract protects any
    content_version a caller could ever have *completed and observed*
    (i.e. one with a matching SQLite lifecycle row) from being
    overwritten or silently mutated. A content_version whose paired
    SQLite write never succeeded was never such a committed revision --
    it is this module's own half-finished write, undone by the same
    logical operation that created it, not a later edit reaching back
    into history. No caller outside ``update_question``'s own exception
    handler should ever call this function.

    Returns ``True`` if a matching record was found and removed,
    ``False`` if no such ``(question_id, content_version)`` existed
    (e.g. a second failure already removed it, or it was never written
    at all) -- never raises for "not found", so a caller performing
    best-effort compensation never needs a second try/except layer just
    to tell "already gone" apart from a real I/O error.
    """
    resolved_path = path if path is not None else DATA_PATH
    with _json_lock:
        existing = _read_raw(resolved_path)
        remaining = [
            item
            for item in existing
            if not (
                item.get("question_id") == question_id
                and item.get("content_version") == content_version
            )
        ]
        if len(remaining) == len(existing):
            return False
        _write_raw(resolved_path, remaining)
        return True


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
  is_deleted INTEGER NOT NULL DEFAULT 0,
  archived_at TEXT,
  archived_by TEXT,
  modified_at TEXT,
  modified_by TEXT,
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

-- Faz 2.9.4: soft-delete / restore / archive audit trail.
--
-- Deliberately a *separate* table from ``question_bank_status_history``
-- above, not a repurposing of it. That table's ``to_status`` column is
-- consumed by ``backend.question_bank.validator.validate_transition_request``
-- as a ``backend.question_bank.transitions.ValidationStatus`` member
-- (draft/technical_review/validated/rejected/deprecated) -- every
-- existing reader of that table (``service.get_status_history``, the
-- Faz 2.9.1/2.9.3 tests) assumes every row's ``to_status`` is one of
-- those five values. Soft-delete/restore/archive are a second,
-- orthogonal lifecycle dimension (Faz 2.9.4 instruction: "validation_status
-- silme/arşivleme sırasında değişmesin") -- writing "soft_deleted" or
-- "archived" into ``to_status`` would silently corrupt that assumption
-- for every existing and future consumer. This table is purely
-- additive: it does not alter, rename, or repurpose any existing
-- table or column.
CREATE TABLE IF NOT EXISTS question_bank_lifecycle_audit(
  id INTEGER PRIMARY KEY,
  question_id TEXT NOT NULL,
  content_version INTEGER NOT NULL,
  action TEXT NOT NULL,
  actor TEXT NOT NULL,
  actor_role TEXT,
  previous_is_deleted INTEGER NOT NULL,
  new_is_deleted INTEGER NOT NULL,
  previous_archived_at TEXT,
  new_archived_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_question_bank_lifecycle_audit_question_id
  ON question_bank_lifecycle_audit(question_id, created_at);
"""


def _ensure_lifecycle_management_columns(c: sqlite3.Connection) -> None:
    """Idempotent ``ALTER TABLE ... ADD COLUMN`` backfill for databases
    created before Faz 2.9.4 (SQLite has no ``ADD COLUMN IF NOT
    EXISTS``, so existence is checked via ``PRAGMA table_info`` first).
    A fresh database created by the DDL above already has every one of
    these columns from ``CREATE TABLE``, so on a fresh DB this is a
    correctly-idempotent no-op (every column already present, nothing
    is added twice); on a pre-2.9.4 DB it backfills exactly the
    missing columns, safe to call on every startup and any number of
    times in the same process."""
    existing = {row[1] for row in c.execute("PRAGMA table_info(question_bank_records)")}
    for column_name, column_ddl in _LIFECYCLE_MANAGEMENT_COLUMNS:
        if column_name not in existing:
            c.execute(
                f"ALTER TABLE question_bank_records ADD COLUMN {column_name} {column_ddl}"
            )


def migrate(c: sqlite3.Connection) -> None:
    """Additive, idempotent -- ``CREATE TABLE IF NOT EXISTS`` /
    ``CREATE INDEX IF NOT EXISTS`` throughout, matching
    ``backend.production_validation.repository.migrate``'s exact
    pattern. Safe to call on every startup and multiple times in the
    same test run."""
    c.executescript(DDL)
    _ensure_lifecycle_management_columns(c)
    # This index references is_deleted, which on a pre-2.9.4 database
    # only exists *after* _ensure_lifecycle_management_columns() above
    # has run -- kept as a separate statement (not part of the DDL
    # script executed first) specifically so this ordering is
    # guaranteed rather than accidental.
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_question_bank_records_is_deleted "
        "ON question_bank_records(is_deleted)"
    )


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


def fetch_records_by_question_id(c: sqlite3.Connection, question_id: str) -> list:
    """Every SQLite lifecycle row for ``question_id``, across all
    ``content_version`` values, ordered by ``content_version``. Faz
    2.9.4 lifecycle actions (soft-delete/restore/archive) always act on
    this whole set at once -- a single ``question_id`` may have several
    ``content_version`` rows, and the instruction is explicit that all
    of them move together in one transaction, never a subset."""
    return c.execute(
        "SELECT * FROM question_bank_records WHERE question_id=? ORDER BY content_version",
        (question_id,),
    ).fetchall()


def set_records_deleted_flag(
    c: sqlite3.Connection,
    *,
    question_id: str,
    is_deleted: bool,
    now_iso: str,
    actor: str,
) -> None:
    """Updates ``is_deleted``, ``modified_at``, ``modified_by`` for
    every ``content_version`` row of ``question_id``. Never touches
    ``validation_status``, ``archived_at``, or ``archived_by`` -- those
    are each a separate, orthogonal piece of state (Faz 2.9.4
    instructions: validation_status must not change on delete/archive;
    restore must not clear archived_at/archived_by)."""
    c.execute(
        "UPDATE question_bank_records SET is_deleted=?, modified_at=?, modified_by=?"
        " WHERE question_id=?",
        (1 if is_deleted else 0, now_iso, actor, question_id),
    )


def set_records_archived(
    c: sqlite3.Connection,
    *,
    question_id: str,
    now_iso: str,
    actor: str,
) -> None:
    """Sets ``archived_at``/``archived_by`` (to ``now_iso``/``actor``)
    and ``modified_at``/``modified_by`` for every ``content_version``
    row of ``question_id``. Never touches ``is_deleted`` or
    ``validation_status``. There is deliberately no corresponding
    "unarchive" setter in Faz 2.9.4 -- that capability is explicitly
    out of this phase's scope."""
    c.execute(
        "UPDATE question_bank_records SET archived_at=?, archived_by=?,"
        " modified_at=?, modified_by=? WHERE question_id=?",
        (now_iso, actor, now_iso, actor, question_id),
    )


def append_lifecycle_audit(
    c: sqlite3.Connection,
    *,
    question_id: str,
    content_version: int,
    action: str,
    actor: str,
    actor_role: Optional[str],
    previous_is_deleted: bool,
    new_is_deleted: bool,
    previous_archived_at: Optional[str],
    new_archived_at: Optional[str],
    now_iso: str,
) -> None:
    """Append-only by construction, exactly like
    ``append_status_history`` -- no UPDATE/DELETE statement against
    ``question_bank_lifecycle_audit`` exists anywhere in this module."""
    c.execute(
        "INSERT INTO question_bank_lifecycle_audit"
        "(question_id,content_version,action,actor,actor_role,"
        "previous_is_deleted,new_is_deleted,previous_archived_at,new_archived_at,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            question_id,
            content_version,
            action,
            actor,
            actor_role,
            1 if previous_is_deleted else 0,
            1 if new_is_deleted else 0,
            previous_archived_at,
            new_archived_at,
            now_iso,
        ),
    )


def fetch_lifecycle_audit(c: sqlite3.Connection, question_id: str) -> list:
    return c.execute(
        "SELECT * FROM question_bank_lifecycle_audit WHERE question_id=? ORDER BY id",
        (question_id,),
    ).fetchall()


def fetch_all_records(c: sqlite3.Connection) -> list:
    """Returns every ``question_bank_records`` row regardless of
    ``validation_status`` (Faz 2.9.2). Unlike
    :func:`fetch_publishable_candidates`, this is not itself a
    visibility rule -- it is a plain bulk read used by
    ``backend.question_bank.retrieval`` to build a
    ``(question_id, content_version) -> validation_status`` lookup for
    filtering. Callers remain responsible for applying
    ``backend.question_bank.validator.validate_publishable`` (or any
    other visibility rule) themselves; this function never decides
    what is publishable."""
    return c.execute("SELECT * FROM question_bank_records").fetchall()
