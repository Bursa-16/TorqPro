"""TorqPro Engineering Library - Faz 2.8.20 Stage 3 washer resolution
controlled closure domain model.

This module defines a structured, immutable-identity, verifiable
closure record that marks a single ``resolution_id`` as
evidence-backed and formally closed. It is a pure domain-model layer:
no persistence, no JSON ledger, no API, no reopen logic live here.

Design constraints (Stage 3 task brief, enforced structurally):

  - This module never writes to ``washer_resolution_ledger.json``,
    ``washer_resolution_decisions.json``, or
    ``washer_resolution_evidence.json`` -- it has no filesystem I/O
    of any kind.
  - ``WasherResolutionClosure`` uses ``extra="forbid"`` and is frozen
    (immutable once constructed), mirroring
    ``WasherResolutionEvidence`` (Stage 1) and
    ``WasherResolutionDecision`` (Faz 2.8.9): a closed set of
    closure-workflow fields.
  - Checksum computation follows the project's canonical pattern
    (see ``backend.library.washer_resolution_evidence.
    compute_evidence_checksum``): ``sha256`` over
    ``json.dumps(payload, sort_keys=True, ensure_ascii=False)``, with
    ``integrity_checksum`` itself excluded from the payload it
    protects.
  - ``closed_at`` is a plain, format-validated string -- this module
    never calls a wall-clock function inside the Pydantic model
    itself. :func:`utc_now_iso` is the single wall-clock source,
    called only by :func:`create_washer_resolution_closure`.
  - ``closure_status`` accepts exactly one value, ``"closed"``, in
    this stage. Reopen is out of scope (ADR-0013, task brief decision
    12): there is no ``"reopened"``/``"open"`` counterpart here, and
    no transition logic exists in this module at all -- a closure
    either exists (closed) or does not exist (not yet closed); there
    is no third state to represent.
  - This module never checks whether ``resolution_id``,
    ``evidence_ids``, or ``decision_id`` refer to real records in any
    other ledger -- that cross-reference is the service layer's job
    (``backend.library.washer_resolution_service``), not this
    domain model's.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

__all__ = [
    "WasherResolutionClosure",
    "UTC_ISO8601_PATTERN",
    "is_valid_utc_iso8601",
    "SHA256_HEX_PATTERN",
    "is_valid_sha256_hex",
    "generate_closure_id",
    "utc_now_iso",
    "compute_closure_checksum",
    "verify_closure_integrity",
    "create_washer_resolution_closure",
]

#: Only legal value for ``closure_status`` in this stage. No reopen
#: counterpart exists (see module docstring).
CLOSURE_STATUS_CLOSED = "closed"


# ---------------------------------------------------------------------
# Timestamp format validation (UTC ISO-8601, backend-generated only)
# ---------------------------------------------------------------------

UTC_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"
)


def is_valid_utc_iso8601(value: str) -> bool:
    """``True`` if ``value`` matches :data:`UTC_ISO8601_PATTERN`."""
    return bool(UTC_ISO8601_PATTERN.match(value))


# ---------------------------------------------------------------------
# Checksum format validation
# ---------------------------------------------------------------------

SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def is_valid_sha256_hex(value: str) -> bool:
    """``True`` if ``value`` matches :data:`SHA256_HEX_PATTERN`."""
    return bool(SHA256_HEX_PATTERN.match(value))


# ---------------------------------------------------------------------
# ID / timestamp generation
# ---------------------------------------------------------------------


def generate_closure_id() -> str:
    """Generate a unique closure identifier. Not required to be
    deterministic -- only uniqueness and a readable ``CLR-`` prefix
    matter, mirroring ``generate_evidence_id``'s ``WRE-`` convention
    and ``decide_resolution``'s ``DEC-<uuid4>`` convention."""
    return f"CLR-{uuid.uuid4()}"


def utc_now_iso() -> str:
    """Backend-generated UTC ISO-8601 timestamp, ``Z``-suffixed,
    microsecond precision. Mirrors
    ``washer_resolution_evidence.utc_now_iso`` exactly -- the only
    wall-clock call in this module."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# ---------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------


def _normalize_required(value: str, field_name: str) -> str:
    """Strip surrounding whitespace; raise if the result is empty."""
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be blank")
    return stripped


class WasherResolutionClosure(BaseModel):
    """One immutable record marking ``resolution_id`` as formally,
    evidence-backed closed.

    ``extra="forbid"`` and ``frozen=True`` are deliberate (see module
    docstring): a closed set of closure-workflow fields. No reopen
    field exists anywhere on this model.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    closure_id: str
    resolution_id: str
    closure_status: str
    closure_rationale: str
    closed_by: str
    closed_at: str
    evidence_ids: List[str]
    decision_id: str
    integrity_checksum: str

    # -- required-field normalization (strip + reject blank) --------

    @field_validator("closure_id", "resolution_id", "closure_rationale", "closed_by", "decision_id")
    @classmethod
    def _required_not_blank(cls, value: str, info: ValidationInfo) -> str:
        return _normalize_required(value, info.field_name)

    # -- closure_status: exactly one legal value in this stage -------

    @field_validator("closure_status")
    @classmethod
    def _closure_status_is_closed(cls, value: str) -> str:
        if value != CLOSURE_STATUS_CLOSED:
            raise ValueError(
                f"closure_status must be '{CLOSURE_STATUS_CLOSED}', got: {value!r}"
            )
        return value

    # -- evidence_ids: non-empty, no duplicates, each non-blank ------

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_ids_valid(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("evidence_ids must not be empty")
        normalized = []
        for item in value:
            stripped = item.strip() if isinstance(item, str) else item
            if not stripped:
                raise ValueError("evidence_ids must not contain blank entries")
            normalized.append(stripped)
        if len(set(normalized)) != len(normalized):
            raise ValueError("evidence_ids must not contain duplicate values")
        return normalized

    # -- timestamp format validation ---------------------------------

    @field_validator("closed_at")
    @classmethod
    def _closed_at_is_utc_iso8601(cls, value: str) -> str:
        if not is_valid_utc_iso8601(value):
            raise ValueError(
                f"closed_at must be UTC ISO-8601 with a 'Z' suffix, got: {value!r}"
            )
        return value

    # -- checksum format validation ----------------------------------

    @field_validator("integrity_checksum")
    @classmethod
    def _integrity_checksum_is_sha256_hex(cls, value: str) -> str:
        if not is_valid_sha256_hex(value):
            raise ValueError(
                "integrity_checksum must be a 64-character lowercase "
                f"SHA-256 hex digest, got: {value!r}"
            )
        return value

    # -- projection ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe projection."""
        return self.model_dump(mode="json")


# ---------------------------------------------------------------------
# Canonical checksum
# ---------------------------------------------------------------------


def compute_closure_checksum(fields: Dict[str, Any]) -> str:
    """Canonical project checksum (mirrors
    ``washer_resolution_evidence.compute_evidence_checksum``) over
    every field in ``fields`` **except** ``integrity_checksum``
    itself. Operates purely on the in-memory ``fields`` mapping -- no
    file is read or written."""
    payload = {k: v for k, v in fields.items() if k != "integrity_checksum"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_closure_integrity(closure: WasherResolutionClosure) -> bool:
    """``True`` if ``closure.integrity_checksum`` matches a fresh
    recomputation over its own fields -- i.e. the record has not been
    tampered with or hand-edited since it was created."""
    payload = closure.to_dict()
    return payload["integrity_checksum"] == compute_closure_checksum(payload)


# ---------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------


def create_washer_resolution_closure(
    *,
    resolution_id: str,
    closure_rationale: str,
    closed_by: str,
    evidence_ids: List[str],
    decision_id: str,
) -> WasherResolutionClosure:
    """Construct a fully-populated, checksummed
    :class:`WasherResolutionClosure`.

    Generates ``closure_id`` (:func:`generate_closure_id`),
    ``closed_at`` (:func:`utc_now_iso`), and ``closure_status``
    (always ``"closed"``) itself -- none are accepted as caller
    arguments. Never writes to the filesystem.
    """
    closure_id = generate_closure_id()
    closed_at = utc_now_iso()

    fields: Dict[str, Any] = {
        "closure_id": closure_id,
        "resolution_id": resolution_id,
        "closure_status": CLOSURE_STATUS_CLOSED,
        "closure_rationale": closure_rationale,
        "closed_by": closed_by,
        "closed_at": closed_at,
        "evidence_ids": list(evidence_ids),
        "decision_id": decision_id,
    }
    checksum = compute_closure_checksum(fields)

    return WasherResolutionClosure(
        closure_id=closure_id,
        resolution_id=resolution_id,
        closure_status=CLOSURE_STATUS_CLOSED,
        closure_rationale=closure_rationale,
        closed_by=closed_by,
        closed_at=closed_at,
        evidence_ids=list(evidence_ids),
        decision_id=decision_id,
        integrity_checksum=checksum,
    )
