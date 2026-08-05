"""TorqPro Engineering Library - Faz 2.8.20 Stage 3 washer resolution
closure persistence layer (append-only ledger I/O).

This module owns exactly one file:
``backend/library/data/washer_resolution_closure.json``. It never
reads or writes ``washer_resolution_ledger.json``,
``washer_resolution_decisions.json``, or
``washer_resolution_evidence.json`` -- none of those files are
touched by anything in this module.

Mirrors ``backend.library.washer_resolution_evidence_store`` (Stage
2) exactly: the same locked/atomic/append-only file I/O pattern, the
same ``_load()``/``reload()`` caching shape.

One deliberate structural difference from both
``washer_resolution_decisions_store.py`` and
``washer_resolution_evidence_store.py``: the duplicate guard here is
keyed on ``resolution_id``, not on the record's own primary id
(``closure_id``). A ``closure_id`` is always a freshly-generated
``CLR-<uuid4>`` value (see
``washer_resolution_closure.generate_closure_id``), so a
``closure_id``-keyed duplicate check could never actually fire -- it
would not catch a second closure attempt against an
already-closed resolution, which is exactly the scenario that must
be rejected (task brief decision 6: "Bir resolution yalnızca bir kez
kapatılabilecek"). This is the reverse of ``append_decision``'s and
``append_evidence``'s guards, which are correctly keyed on their own
primary id because *multiple* decisions/evidence per ``resolution_id``
are legal; at most one closure per ``resolution_id`` is legal.

This module does **not** validate business rules -- checksum
computation and integrity verification are the domain model's
responsibility (``backend.library.washer_resolution_closure.
compute_closure_checksum`` / ``verify_closure_integrity``), imported
here unchanged, never reimplemented. This module also never checks
whether ``resolution_id``, ``evidence_ids``, or ``decision_id`` refer
to real records elsewhere, and never checks readiness rules -- both
are the service layer's job.
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

from .washer_resolution_closure import WasherResolutionClosure

__all__ = [
    "DATA_PATH",
    "DuplicateClosureError",
    "reload",
    "list_all_closures",
    "get_closure_for_resolution",
    "append_closure",
]

DATA_PATH = Path(__file__).resolve().parent / "data" / "washer_resolution_closure.json"

#: Advisory lock file, sitting next to the ledger it protects.
_LOCK_PATH = DATA_PATH.with_suffix(".lock")

_CACHE: Optional[List[WasherResolutionClosure]] = None


class DuplicateClosureError(Exception):
    """Raised by :func:`append_closure` if ``resolution_id`` already
    has a closure recorded. The ledger is append-only and at most one
    closure per ``resolution_id`` is legal in this stage (no reopen) --
    this is a hard stop, not a merge or overwrite. Deliberately keyed
    on ``resolution_id``, not ``closure_id`` -- see module docstring."""

    def __init__(self, resolution_id: str):
        self.resolution_id = resolution_id
        super().__init__(
            f"resolution_id '{resolution_id}' already has a closure recorded."
        )


# ---------------------------------------------------------------------
# File I/O (locked, atomic, append-only)
# ---------------------------------------------------------------------

_PROCESS_LOCK = threading.Lock()


@contextmanager
def _locked() -> Iterator[None]:
    """Serialize concurrent read-check-write cycles for the duration
    of the ``with`` block. Mirrors
    ``washer_resolution_evidence_store._locked`` exactly, including
    its accepted Windows limitation (in-process guard only when
    ``fcntl`` is unavailable)."""
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
        prefix=".washer_resolution_closure.", suffix=".tmp", dir=str(directory)
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
    """Drop the cached closure list; the next read re-parses the
    ledger JSON file from disk."""
    global _CACHE
    _CACHE = None


def _load() -> List[WasherResolutionClosure]:
    global _CACHE
    if _CACHE is None:
        payload = _read_raw()
        _CACHE = [
            WasherResolutionClosure.model_validate(raw)
            for raw in payload.get("closures", [])
        ]
    return _CACHE


# ---------------------------------------------------------------------
# Read accessors
# ---------------------------------------------------------------------


def list_all_closures() -> List[WasherResolutionClosure]:
    """Every recorded closure, in append order (oldest first)."""
    return list(_load())


def get_closure_for_resolution(resolution_id: str) -> Optional[WasherResolutionClosure]:
    """The closure record for this ``resolution_id``, or ``None`` if
    it has not been closed. At most one closure per ``resolution_id``
    can ever exist (enforced by :func:`append_closure`), so this is a
    genuine single-record lookup, not "the first of several"."""
    for closure in _load():
        if closure.resolution_id == resolution_id:
            return closure
    return None


# ---------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------


def append_closure(closure: WasherResolutionClosure) -> WasherResolutionClosure:
    """Append ``closure`` to the ledger. Raises
    :class:`DuplicateClosureError` if its ``resolution_id`` already
    has a closure recorded -- this file is append-only, never an
    overwrite target, and no update/delete function exists on this
    module.

    Acquires the advisory lock for the full read-check-write cycle so
    two concurrent callers cannot both observe "not yet closed" and
    both append a closure for the same ``resolution_id``.
    """
    with _locked():
        payload = _read_raw()
        existing_resolution_ids = {
            rec["resolution_id"] for rec in payload.get("closures", [])
        }
        if closure.resolution_id in existing_resolution_ids:
            raise DuplicateClosureError(closure.resolution_id)
        payload.setdefault("closures", []).append(closure.to_dict())
        payload.setdefault("metadata", {})["record_count"] = len(payload["closures"])
        _write_raw_atomic(payload)
    reload()
    return closure
