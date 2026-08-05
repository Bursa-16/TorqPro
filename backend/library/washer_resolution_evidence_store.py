"""TorqPro Engineering Library - Faz 2.8.20 Stage 2 washer resolution
evidence persistence layer (append-only ledger I/O).

This module owns exactly one file:
``backend/library/data/washer_resolution_evidence.json``. It never
reads or writes ``washer_resolution_ledger.json`` (Faz 2.8.5),
``washer_resolution_decisions.json`` (Faz 2.8.9), or
``washer_provenance_evidence.json`` (Faz 2.8.4) -- none of those
files are touched by anything in this module.

Mirrors ``backend.library.washer_resolution_decisions_store`` (Faz
2.8.9 Stage 2) exactly: the same locked/atomic/append-only file I/O
pattern, the same ``_load()``/``reload()`` caching shape, the same
``DuplicateXIdError`` fail-closed guard. The two modules are
deliberately parallel, not shared, so each washer-resolution ledger
(decisions, evidence) can evolve independently without coupling one
persistence module to another's schema.

Responsibilities, deliberately narrow:

  - Append-only writes: an existing ``evidence_id`` can never be
    overwritten (:class:`DuplicateEvidenceIdError`); the file is
    replaced atomically (temp file + ``os.replace``) so a crash
    mid-write cannot corrupt or truncate prior entries.
  - A simple advisory file lock (``fcntl.flock`` on POSIX, plus an
    in-process ``threading.Lock`` on every platform) around every
    read-check-write cycle, so two concurrent callers cannot both
    pass a duplicate-id check and both append.
  - Read accessors: by id, by resolution_id, and the full list.

This module does **not** validate business rules -- checksum
computation and integrity verification are Stage 1's responsibility
(``backend.library.washer_resolution_evidence.compute_evidence_checksum``
/ ``verify_evidence_integrity``), imported here unchanged, never
reimplemented. This module also never checks whether a
``resolution_id`` exists in ``washer_resolution_ledger.json`` -- that
cross-reference, if ever needed, belongs to a future service layer,
not to persistence (task brief decision 1). No idempotency-key
mechanism exists here either (task brief decision 2): unlike a
resolution *decision*, adding a piece of *evidence* is not a
retry-sensitive state transition -- appending the same evidence twice
simply yields two evidence records, which is a service-layer/caller
concern, not a persistence-layer one.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows has no fcntl module
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False

from .washer_resolution_evidence import WasherResolutionEvidence

__all__ = [
    "DATA_PATH",
    "DuplicateEvidenceIdError",
    "reload",
    "list_all_evidence",
    "get_evidence",
    "evidence_for_resolution",
    "append_evidence",
]

DATA_PATH = Path(__file__).resolve().parent / "data" / "washer_resolution_evidence.json"

#: Advisory lock file, sitting next to the ledger it protects. Never
#: itself contains ledger data. Mirrors
#: ``washer_resolution_decisions_store._LOCK_PATH``.
_LOCK_PATH = DATA_PATH.with_suffix(".lock")

_CACHE: Optional[List[WasherResolutionEvidence]] = None


class DuplicateEvidenceIdError(Exception):
    """Raised by :func:`append_evidence` if ``evidence_id`` already
    exists in the ledger. The ledger is append-only: this is a hard
    stop, not a merge or overwrite. Practically unreachable in normal
    use (``evidence_id`` is a server-generated ``WRE-<uuid4>``), but a
    ledger-level id collision is a conflict with existing state and
    must fail closed rather than silently overwrite."""

    def __init__(self, evidence_id: str):
        self.evidence_id = evidence_id
        super().__init__(f"evidence_id '{evidence_id}' already exists in the ledger.")


# ---------------------------------------------------------------------
# File I/O (locked, atomic, append-only)
# ---------------------------------------------------------------------

#: Extra in-process guard against thread races, layered on top of the
#: cross-process file lock (when available). Always used, on every
#: platform -- harmless on POSIX (flock already serializes there too)
#: and load-bearing on platforms without fcntl (e.g. Windows).
_PROCESS_LOCK = threading.Lock()


@contextmanager
def _locked() -> Iterator[None]:
    """Serialize concurrent read-check-write cycles for the duration
    of the ``with`` block, released automatically (even on exception)
    when the block exits.

    On POSIX, an advisory ``fcntl.flock`` over :data:`_LOCK_PATH`
    provides a cross-process guard, in addition to the in-process
    :data:`_PROCESS_LOCK`. On platforms without ``fcntl`` (e.g.
    Windows), only :data:`_PROCESS_LOCK` is used -- this still
    prevents concurrent-thread races within one running process; a
    multi-process guard on such platforms is out of scope, mirroring
    ``washer_resolution_decisions_store._locked``'s accepted
    limitation. Module import never fails for lack of ``fcntl`` -- see
    the top-of-module try/except.
    """
    if _HAS_FCNTL:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOCK_PATH, "w", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle, fcntl.LOCK_EX)
            try:
                with _PROCESS_LOCK:
                    yield
            finally:
                fcntl.flock(lock_handle, fcntl.LOCK_UN)
    else:  # pragma: no cover - exercised via _HAS_FCNTL monkeypatch, not real Windows
        with _PROCESS_LOCK:
            yield


def _read_raw() -> Dict[str, Any]:
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_raw_atomic(payload: Dict[str, Any]) -> None:
    """Write ``payload`` to :data:`DATA_PATH` via a temp file in the
    same directory plus ``os.replace`` -- either the old complete
    file or the new complete file is ever observable, never a partial
    write, even if the process is killed mid-write."""
    directory = DATA_PATH.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=".washer_resolution_evidence.", suffix=".tmp", dir=str(directory)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_handle:
            json.dump(payload, tmp_handle, indent=2, sort_keys=True, ensure_ascii=False)
            tmp_handle.write("\n")
            tmp_handle.flush()
            os.fsync(tmp_handle.fileno())
        os.replace(tmp_name, DATA_PATH)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def reload() -> None:
    """Drop the cached evidence list; the next read re-parses the
    ledger JSON file from disk. Mirrors
    ``washer_resolution_decisions_store.reload()``."""
    global _CACHE
    _CACHE = None


def _load() -> List[WasherResolutionEvidence]:
    global _CACHE
    if _CACHE is None:
        payload = _read_raw()
        _CACHE = [
            WasherResolutionEvidence.model_validate(raw)
            for raw in payload.get("evidence", [])
        ]
    return _CACHE


# ---------------------------------------------------------------------
# Read accessors
# ---------------------------------------------------------------------


def list_all_evidence() -> List[WasherResolutionEvidence]:
    """Every recorded evidence record, in append order (oldest
    first)."""
    return list(_load())


def get_evidence(evidence_id: str) -> Optional[WasherResolutionEvidence]:
    """The evidence record with this ``evidence_id``, or ``None`` if
    it does not exist."""
    for evidence in _load():
        if evidence.evidence_id == evidence_id:
            return evidence
    return None


def evidence_for_resolution(resolution_id: str) -> List[WasherResolutionEvidence]:
    """Every evidence record for this ``resolution_id``, in append
    order. Does not check whether ``resolution_id`` exists in
    ``washer_resolution_ledger.json`` -- see module docstring."""
    return [e for e in _load() if e.resolution_id == resolution_id]


# ---------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------


def append_evidence(evidence: WasherResolutionEvidence) -> WasherResolutionEvidence:
    """Append ``evidence`` to the ledger. Raises
    :class:`DuplicateEvidenceIdError` if its ``evidence_id`` already
    exists -- this file is append-only, never an overwrite target. No
    other write operation exists on this module: no update, no
    delete.

    Acquires the advisory lock for the full read-check-write cycle so
    two concurrent callers cannot both observe "not present yet" and
    both append.
    """
    with _locked():
        payload = _read_raw()
        existing_ids = {rec["evidence_id"] for rec in payload.get("evidence", [])}
        if evidence.evidence_id in existing_ids:
            raise DuplicateEvidenceIdError(evidence.evidence_id)
        payload.setdefault("evidence", []).append(evidence.to_dict())
        payload.setdefault("metadata", {})["record_count"] = len(payload["evidence"])
        _write_raw_atomic(payload)
    reload()
    return evidence
