"""TorqPro Engineering Governance - Faz 2.8.11 Stage 3 append-only
event store.

Two things live here: an abstract :class:`GovernanceEventStore`
contract, and one concrete, deterministic, file-backed
implementation (:class:`FileGovernanceEventStore`). Both are
additive and self-contained -- this module never reads, writes, or
imports anything from ``backend.library.washer_resolution*`` or any
other existing mechanism's ledger/table (see the package
``__init__.py`` for the full compatibility contract).

Design constraints (Faz 2.8.11 Stage 3 scope, enforced structurally):

  - **Append-only.** There is no update or delete method on either
    the abstract contract or the concrete implementation. The only
    write operation is :meth:`FileGovernanceEventStore.append`.
  - **Atomic writes.** Every write is: read the current file (or
    treat a missing file as empty), append the new event to an
    in-memory list, serialize the *whole* list to a temp file in the
    same directory, ``fsync`` it, then ``os.replace`` it over the
    real path. Either the previous complete file or the new complete
    file is ever observable -- never a partial write -- even if the
    process is killed mid-write. This is the same pattern
    ``backend.library.washer_resolution_decisions_store`` already
    uses (duplicated here, not imported, to keep this package
    decoupled from ``backend.library`` -- see package
    ``__init__.py``).
  - **Windows-compatible locking.** An advisory ``fcntl.flock`` over
    a sidecar ``.lock`` file provides a cross-process guard on POSIX;
    on platforms without ``fcntl`` (Windows), only an in-process
    ``threading.Lock`` is used. Module import never fails for lack of
    ``fcntl``.
  - **Deterministic serialization.** ``json.dumps(..., sort_keys=True,
    ensure_ascii=False, indent=2)`` -- the same canonical style as
    every other JSON artifact in this repository. ``ensure_ascii=False``
    is load-bearing for Turkish-character content (a known project
    pitfall -- see ``docs/12_CLAUDE_CONTEXT.md`` / ``CLAUDE.md``).
  - **UTF-8 encoding**, explicit on every file open.
  - **Corruption detection.** Malformed JSON, an unexpected top-level
    shape, or a record that fails :class:`~backend.governance.events.
    GovernanceEvent` validation all raise
    :class:`~backend.governance.exceptions.GovernanceCorruptionError`
    rather than silently returning partial or wrong data.
  - **No absolute filesystem paths or traceback leakage in public
    errors.** Every raised error carries a fixed, generic message
    (see ``backend.governance.exceptions``); the store never
    interpolates ``self._path`` or a caught exception's own message
    into anything raised to a caller. Underlying exceptions are
    suppressed with ``raise ... from None``.
  - **Configurable storage path for tests.**
    ``FileGovernanceEventStore.__init__`` takes an explicit ``path``;
    there is no hard-coded default path and no module-level global
    store instance. A caller (tests, and later a Stage 4 API layer)
    is fully responsible for choosing where events are persisted.
  - **Empty-store behavior is valid.** A store backed by a
    nonexistent file behaves exactly like a store backed by a file
    containing ``{"events": []}`` -- reading it returns an empty
    list, never an error.
  - **The existing washer resolution ledger is never read, modified,
    migrated, or reused.** This module has no import from, and no
    path reference to, ``backend/library/data/
    washer_resolution_ledger.json`` or
    ``washer_resolution_decisions.json``.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows has no fcntl module
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False

from pydantic import ValidationError

from .events import GovernanceEvent
from .exceptions import GovernanceCorruptionError, GovernanceStoreError


class GovernanceEventStore(ABC):
    """Abstract append-only governance event store contract. Every
    method here is read-only except :meth:`append`; there is no
    update or delete method anywhere on this contract."""

    @abstractmethod
    def append(self, event: GovernanceEvent) -> GovernanceEvent:
        """Persist ``event``. Must never overwrite or remove any
        previously-appended event. Returns ``event`` unchanged on
        success."""

    @abstractmethod
    def all_events(self) -> List[GovernanceEvent]:
        """Every event ever appended, in append order (oldest
        first). An empty store returns ``[]``, not an error."""

    @abstractmethod
    def events_for_aggregate(self, aggregate_id: str) -> List[GovernanceEvent]:
        """Every event for ``aggregate_id``, in append order."""

    @abstractmethod
    def find_by_decision_id(self, decision_id: str) -> Optional[GovernanceEvent]:
        """The event with this ``decision_id``, or ``None``."""

    @abstractmethod
    def find_by_idempotency_key(self, idempotency_key: str) -> Optional[GovernanceEvent]:
        """The event with this ``idempotency_key``, or ``None``."""


class FileGovernanceEventStore(GovernanceEventStore):
    """Deterministic, file-backed, append-only implementation of
    :class:`GovernanceEventStore`.

    One JSON file, ``{"events": [...]}``, replaced atomically on
    every append. ``path`` is required and fully caller-controlled --
    see module docstring, "Configurable storage path for tests"."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock_path = self._path.with_suffix(self._path.suffix + ".lock")
        self._process_lock = threading.Lock()

    # -------------------------------------------------------------
    # Locking
    # -------------------------------------------------------------

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Serialize concurrent read-check-write cycles for the
        duration of the ``with`` block. On POSIX, an advisory
        ``fcntl.flock`` over a sidecar lock file provides a
        cross-process guard in addition to the in-process
        ``threading.Lock``; on platforms without ``fcntl`` (Windows),
        only the in-process lock is used -- this still prevents
        concurrent-thread races within one running process. A
        multi-process guarantee on such platforms is out of scope for
        this stage (single-node deployment, matching ADR-0006's
        existing SQLite-architecture precedent)."""
        if _HAS_FCNTL:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._lock_path, "w", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle, fcntl.LOCK_EX)
                try:
                    with self._process_lock:
                        yield
                finally:
                    fcntl.flock(lock_handle, fcntl.LOCK_UN)
        else:  # pragma: no cover - exercised via _HAS_FCNTL monkeypatch, not real Windows
            with self._process_lock:
                yield

    # -------------------------------------------------------------
    # Raw file I/O
    # -------------------------------------------------------------

    def _read_raw(self) -> Dict[str, Any]:
        """Return ``{"events": [...]}`` as a plain dict, without
        validating individual event shapes yet (that happens in
        :meth:`all_events`, where a validation failure becomes
        :class:`GovernanceCorruptionError`). A missing file is valid
        empty-store behavior, not an error."""
        if not self._path.exists():
            return {"events": []}
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            raise GovernanceStoreError("failed to read the governance event store") from None
        if not text.strip():
            return {"events": []}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise GovernanceCorruptionError(
                "governance event store content is not valid JSON"
            ) from None
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise GovernanceCorruptionError(
                "governance event store content does not have the expected shape"
            ) from None
        return payload

    def _write_raw_atomic(self, payload: Dict[str, Any]) -> None:
        """Write ``payload`` to :data:`self._path` via a temp file in
        the same directory plus ``os.replace`` -- either the old
        complete file or the new complete file is ever observable,
        never a partial write."""
        directory = self._path.parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=".governance_events.", suffix=".tmp", dir=str(directory)
            )
        except OSError:
            raise GovernanceStoreError("failed to prepare governance event store write") from None
        try:
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_handle:
                    json.dump(payload, tmp_handle, indent=2, sort_keys=True, ensure_ascii=False)
                    tmp_handle.write("\n")
                    tmp_handle.flush()
                    os.fsync(tmp_handle.fileno())
                os.replace(tmp_name, self._path)
            except OSError:
                raise GovernanceStoreError("failed to persist governance event") from None
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:  # pragma: no cover - best-effort cleanup only
                    pass

    # -------------------------------------------------------------
    # Validated read accessors
    # -------------------------------------------------------------

    def all_events(self) -> List[GovernanceEvent]:
        payload = self._read_raw()
        events: List[GovernanceEvent] = []
        for raw in payload["events"]:
            try:
                events.append(GovernanceEvent.model_validate(raw))
            except ValidationError:
                raise GovernanceCorruptionError(
                    "governance event store contains a record that failed validation"
                ) from None
        return events

    def events_for_aggregate(self, aggregate_id: str) -> List[GovernanceEvent]:
        return [e for e in self.all_events() if e.aggregate_id == aggregate_id]

    def find_by_decision_id(self, decision_id: str) -> Optional[GovernanceEvent]:
        for event in self.all_events():
            if event.decision_id == decision_id:
                return event
        return None

    def find_by_idempotency_key(self, idempotency_key: str) -> Optional[GovernanceEvent]:
        if not idempotency_key:
            return None
        for event in self.all_events():
            if event.idempotency_key == idempotency_key:
                return event
        return None

    # -------------------------------------------------------------
    # Write path
    # -------------------------------------------------------------

    def append(self, event: GovernanceEvent) -> GovernanceEvent:
        """Append ``event``. Acquires the advisory lock for the full
        read-modify-write cycle so two concurrent callers cannot
        interleave writes and silently drop one of them. Does not
        itself enforce idempotency-key or decision_id uniqueness --
        that business-level check (with its "legitimate retry"
        exception) belongs to
        :mod:`backend.governance.service`, which is expected to have
        already resolved it before calling this method."""
        with self._locked():
            payload = self._read_raw()
            payload["events"].append(event.model_dump(mode="json"))
            self._write_raw_atomic(payload)
        return event


__all__ = ["GovernanceEventStore", "FileGovernanceEventStore"]
