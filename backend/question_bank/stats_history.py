"""Question Bank statistics trend / history (Faz 2.9.12).

Single responsibility: persist and retrieve point-in-time snapshots of
:func:`backend.question_bank.stats.compute_stats`'s existing output --
this module introduces no new aggregation logic and never recomputes
a count itself. It is a thin persistence layer on top of two things
that already exist:

- :func:`backend.question_bank.stats.compute_stats` (Faz 2.9.10) is
  reused verbatim to produce the payload every snapshot stores --
  exactly the same aggregation ``GET /api/question-bank/stats``
  already returns, computed the exact same way (same
  ``publishable_only=False``/``include_deleted=False``/
  ``include_archived=False`` defaults, same four breakdowns). This
  module never re-implements or re-interprets that counting logic.
- ``question_bank_stats_snapshots`` (Faz 2.9.12's one new table, see
  :data:`backend.question_bank.store.DDL`) is a simple append-only
  ``(id, created_at, stats_json)`` log -- no new content schema, no
  new lifecycle/business rule, no relationship to any existing table.

Two operations:

- :func:`create_snapshot` computes the current stats and appends one
  row.
- :func:`list_snapshots` reads rows back out, oldest-first
  (deterministic chronological order, tie-broken by the existing
  autoincrement ``id`` convention every other table in this package's
  DDL already relies on -- see ``store.DDL``'s Faz 2.9.12 comment), and
  optionally limited to the most recent ``limit`` snapshots.

A snapshot's ``stats_json`` column is expected to always be exactly
what :func:`create_snapshot` itself last wrote (valid JSON, decoding
to a ``dict`` with ``compute_stats()``'s five keys). If a row is ever
found to violate that -- a hand-edited/corrupted database, a
manually-inserted row from outside this module -- :func:`list_snapshots`
raises :class:`backend.question_bank.errors.SnapshotDataError` rather
than silently skipping the row or returning malformed data to a
caller expecting the normal shape.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import stats as qb_stats
from .errors import SnapshotDataError

#: The exact key set every valid ``compute_stats()`` payload has --
#: used to validate a decoded ``stats_json`` value before handing it
#: back to a caller (see :func:`_decode_stats_json`).
_EXPECTED_STATS_KEYS = {
    "total",
    "by_validation_status",
    "by_category",
    "by_difficulty",
    "by_question_type",
}


def _now_iso() -> str:
    """Same convention as
    ``backend.question_bank.service._now_iso``: timezone-aware UTC,
    second precision (this module never needs sub-second ordering --
    :data:`question_bank_stats_snapshots.id` is the tie-break for
    same-second snapshots, not ``created_at``)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _encode_stats_json(stats_payload: dict) -> str:
    """Canonical JSON encoding, matching
    ``backend.question_bank.store._checksum``'s existing
    ``sort_keys=True, ensure_ascii=False`` convention (mandatory for
    Turkish-character bucket labels -- see that helper's own
    docstring)."""
    return json.dumps(stats_payload, sort_keys=True, ensure_ascii=False)


def _decode_stats_json(raw: str, *, snapshot_id: Any) -> dict:
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise SnapshotDataError(
            f"stats snapshot id={snapshot_id!r} için stored stats_json geçersiz JSON"
        ) from exc
    if not isinstance(decoded, dict) or not _EXPECTED_STATS_KEYS.issubset(decoded.keys()):
        raise SnapshotDataError(
            f"stats snapshot id={snapshot_id!r} beklenen compute_stats() alanlarını içermiyor"
        )
    return decoded


def _row_to_snapshot(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "stats": _decode_stats_json(row["stats_json"], snapshot_id=row["id"]),
    }


def create_snapshot(c: sqlite3.Connection) -> Dict[str, Any]:
    """Computes the Question Bank's current stats
    (:func:`backend.question_bank.stats.compute_stats`) and appends one
    row to ``question_bank_stats_snapshots``. Returns the created
    snapshot in the exact same ``{"id", "created_at", "stats"}`` shape
    :func:`list_snapshots` returns each entry as -- one representation,
    used by both the write and the read path.

    Explicit ``BEGIN``/``commit``/``rollback``, matching
    ``backend.question_bank.service.register_question``'s own
    transaction convention -- not left to an implicit transaction, so
    this function composes safely with other write helpers in this
    package on the same connection within a single request/test (an
    implicit transaction left open by a bare ``INSERT`` would collide
    with the next explicit ``c.execute("BEGIN")`` a sibling helper
    issues, since SQLite does not allow nested transactions).
    """
    stats_payload = qb_stats.compute_stats(c)
    created_at = _now_iso()
    try:
        c.execute("BEGIN")
        cur = c.execute(
            "INSERT INTO question_bank_stats_snapshots(created_at, stats_json) VALUES(?,?)",
            (created_at, _encode_stats_json(stats_payload)),
        )
        c.commit()
    except Exception:
        c.rollback()
        raise
    return {
        "id": cur.lastrowid,
        "created_at": created_at,
        "stats": stats_payload,
    }


def list_snapshots(c: sqlite3.Connection, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Returns every stored snapshot, oldest-first (see module
    docstring for the ``id``-tie-break ordering rationale).

    ``limit`` (when given) returns only the most recent ``limit``
    snapshots -- still in oldest-first order, so a caller charting a
    trend never has to sort the response itself. ``limit=None``
    (the default) returns the full history. A non-positive ``limit``
    (``<= 0``) returns an empty list rather than raising -- "show the
    most recent zero snapshots" is a degenerate but well-defined
    request, not an error.
    """
    if limit is not None and limit <= 0:
        return []
    if limit is None:
        rows = c.execute(
            "SELECT id, created_at, stats_json FROM question_bank_stats_snapshots ORDER BY id ASC"
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT id, created_at, stats_json FROM question_bank_stats_snapshots"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        rows = list(reversed(rows))
    return [_row_to_snapshot(row) for row in rows]


__all__ = ["create_snapshot", "list_snapshots"]
