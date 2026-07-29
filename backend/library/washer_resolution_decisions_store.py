"""TorqPro Engineering Library - Faz 2.8.9 washer resolution decision
persistence layer (Stage 2: append-only ledger I/O, checksum and
idempotency).

This module owns exactly one file:
``backend/library/data/washer_resolution_decisions.json``. It never
reads or writes ``washer_resolution_ledger.json`` (the Faz 2.8.5
source ledger) -- that file's 76 records and their statuses are
untouched by anything in this module.

Responsibilities, deliberately narrow:

  - Deterministic checksum computation over a decision's own fields
    (tamper/integrity detection), using the project's canonical
    checksum algorithm (``sha256`` over ``json.dumps(...,
    sort_keys=True, ensure_ascii=False)`` -- see
    ``backend.library.population.find_checksum_mismatches`` for the
    same pattern applied to library records).
  - Append-only writes: an existing ``decision_id`` can never be
    overwritten (:class:`DuplicateDecisionIdError`); the file is
    replaced atomically (temp file + ``os.replace``) so a crash
    mid-write cannot corrupt or truncate prior entries.
  - Idempotency-key lookup, so a caller (the Stage 3 API layer) can
    detect a retried request and return the original decision instead
    of creating a second one.
  - A simple advisory file lock (``fcntl.flock``) around every
    read-check-write cycle, so two concurrent requests cannot both
    pass an idempotency/duplicate check and both append.

This module does **not** validate business rules (state-machine
legality, blank note/evidence) -- that is
``backend.library.washer_resolution_decisions``'s job, called by the
Stage 3 service layer *before* anything here is invoked. This module
also does not look up a ledger record's current status from
``washer_resolution_ledger.json`` -- that cross-reference is a Stage 3
service-layer concern, not a persistence concern.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .washer_resolution_decisions import WasherResolutionDecision

__all__ = [
    "DATA_PATH",
    "DuplicateDecisionIdError",
    "compute_integrity_checksum",
    "build_decision",
    "verify_integrity",
    "reload",
    "list_decisions",
    "get_decision",
    "decisions_for_resolution",
    "find_by_idempotency_key",
    "append_decision",
    "record_decision",
]

DATA_PATH = Path(__file__).resolve().parent / "data" / "washer_resolution_decisions.json"

#: Advisory lock file, sitting next to the ledger it protects. Never
#: itself contains ledger data.
_LOCK_PATH = DATA_PATH.with_suffix(".lock")

_CACHE: Optional[List[WasherResolutionDecision]] = None


class DuplicateDecisionIdError(Exception):
    """Raised by :func:`append_decision` if ``decision_id`` already
    exists in the ledger. The ledger is append-only: this is a hard
    stop, not a merge or overwrite."""

    def __init__(self, decision_id: str):
        self.decision_id = decision_id
        super().__init__(f"decision_id '{decision_id}' already exists in the ledger.")


# ---------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------


def compute_integrity_checksum(decision_fields: Dict[str, Any]) -> str:
    """Canonical project checksum (see module docstring) over every
    field in ``decision_fields`` **except** ``integrity_checksum``
    itself, so the digest can be recomputed later from the persisted
    record to detect tampering.

    ``decision_fields`` must already be JSON-safe (enum ``.value``
    strings, not enum members) -- callers pass the dict form, not the
    model, so this function has no Pydantic dependency.
    """
    payload = {k: v for k, v in decision_fields.items() if k != "integrity_checksum"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_decision(
    *,
    decision_id: str,
    resolution_id: str,
    previous_status,
    new_status,
    resolution_note: str,
    evidence_reference: str,
    resolved_by: str,
    decided_at: str,
    idempotency_key: Optional[str],
    confidence_level=None,
) -> WasherResolutionDecision:
    """Construct a fully-populated, checksummed
    :class:`WasherResolutionDecision`.

    Does not validate state-machine legality or field
    non-blankness -- callers (the Stage 3 service layer) must call
    ``washer_resolution_decisions.validate_transition`` and
    ``validate_decision_fields`` first. This function's only job is
    deterministic checksum computation over the exact fields being
    persisted, so the checksum always matches what
    :func:`append_decision` writes.
    """
    fields: Dict[str, Any] = {
        "decision_id": decision_id,
        "resolution_id": resolution_id,
        "previous_status": getattr(previous_status, "value", previous_status),
        "new_status": getattr(new_status, "value", new_status),
        "resolution_note": resolution_note,
        "evidence_reference": evidence_reference,
        "resolved_by": resolved_by,
        "decided_at": decided_at,
        "confidence_level": getattr(confidence_level, "value", confidence_level),
        "idempotency_key": idempotency_key,
    }
    checksum = compute_integrity_checksum(fields)
    return WasherResolutionDecision(
        decision_id=decision_id,
        resolution_id=resolution_id,
        previous_status=previous_status,
        new_status=new_status,
        resolution_note=resolution_note,
        evidence_reference=evidence_reference,
        resolved_by=resolved_by,
        decided_at=decided_at,
        confidence_level=confidence_level,
        integrity_checksum=checksum,
        idempotency_key=idempotency_key,
    )


def verify_integrity(decision: WasherResolutionDecision) -> bool:
    """``True`` if ``decision.integrity_checksum`` matches a fresh
    recomputation over its own fields -- i.e. the persisted record has
    not been tampered with or hand-edited since it was written."""
    payload = decision.to_dict()
    return payload["integrity_checksum"] == compute_integrity_checksum(payload)


# ---------------------------------------------------------------------
# File I/O (locked, atomic, append-only)
# ---------------------------------------------------------------------


@contextmanager
def _locked() -> Iterator[None]:
    """Advisory exclusive lock over the ledger file's lifetime for the
    duration of the ``with`` block, serializing concurrent
    read-check-write cycles across processes/threads. Released
    automatically (even on exception) when the block exits."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_PATH, "w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)


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
        prefix=".washer_resolution_decisions.", suffix=".tmp", dir=str(directory)
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
    """Drop the cached decision list; the next read re-parses the
    ledger JSON file from disk. Mirrors
    ``washer_resolution.reload()``."""
    global _CACHE
    _CACHE = None


def _load() -> List[WasherResolutionDecision]:
    global _CACHE
    if _CACHE is None:
        payload = _read_raw()
        _CACHE = [
            WasherResolutionDecision.model_validate(raw)
            for raw in payload.get("decisions", [])
        ]
    return _CACHE


# ---------------------------------------------------------------------
# Read accessors
# ---------------------------------------------------------------------


def list_decisions() -> List[WasherResolutionDecision]:
    """Every recorded decision, in append order (oldest first)."""
    return list(_load())


def get_decision(decision_id: str) -> Optional[WasherResolutionDecision]:
    for decision in _load():
        if decision.decision_id == decision_id:
            return decision
    return None


def decisions_for_resolution(resolution_id: str) -> List[WasherResolutionDecision]:
    """Every decision recorded against this ``resolution_id``, in
    append order -- the last element (if any) is the current decision
    history's most recent entry for that resolution."""
    return [d for d in _load() if d.resolution_id == resolution_id]


def find_by_idempotency_key(idempotency_key: str) -> Optional[WasherResolutionDecision]:
    if not idempotency_key:
        return None
    for decision in _load():
        if decision.idempotency_key == idempotency_key:
            return decision
    return None


# ---------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------


def append_decision(decision: WasherResolutionDecision) -> WasherResolutionDecision:
    """Append ``decision`` to the ledger. Raises
    :class:`DuplicateDecisionIdError` if its ``decision_id`` already
    exists -- this file is append-only, never an overwrite target.

    Acquires the advisory lock for the full read-check-write cycle so
    two concurrent callers cannot both observe "not present yet" and
    both append.
    """
    with _locked():
        payload = _read_raw()
        existing_ids = {rec["decision_id"] for rec in payload.get("decisions", [])}
        if decision.decision_id in existing_ids:
            raise DuplicateDecisionIdError(decision.decision_id)
        payload.setdefault("decisions", []).append(decision.to_dict())
        payload.setdefault("metadata", {})["record_count"] = len(payload["decisions"])
        _write_raw_atomic(payload)
    reload()
    return decision


def record_decision(
    decision: WasherResolutionDecision,
) -> "tuple[WasherResolutionDecision, bool]":
    """Idempotency-aware write: if ``decision.idempotency_key`` already
    matches a previously-recorded decision, that existing decision is
    returned unchanged and nothing new is appended (``created=False``).
    Otherwise ``decision`` is appended (``created=True``).

    The idempotency check and the append happen inside the same
    advisory-locked critical section, so a race between two identical
    concurrent requests cannot produce two ledger entries.

    Returns ``(effective_decision, created)``.
    """
    with _locked():
        payload = _read_raw()
        existing_ids = {rec["decision_id"] for rec in payload.get("decisions", [])}
        if decision.idempotency_key:
            for raw in payload.get("decisions", []):
                if raw.get("idempotency_key") == decision.idempotency_key:
                    reload()
                    return WasherResolutionDecision.model_validate(raw), False
        if decision.decision_id in existing_ids:
            raise DuplicateDecisionIdError(decision.decision_id)
        payload.setdefault("decisions", []).append(decision.to_dict())
        payload.setdefault("metadata", {})["record_count"] = len(payload["decisions"])
        _write_raw_atomic(payload)
    reload()
    return decision, True
