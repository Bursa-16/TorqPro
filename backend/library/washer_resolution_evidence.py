"""TorqPro Engineering Library - Faz 2.8.20 Stage 1 washer resolution
evidence domain model.

This module defines a structured, immutable-identity, verifiable
evidence record that can be associated with a
``backend.library.washer_resolution.WasherResolutionRecord``. It is a
pure domain-model layer: no persistence, no JSON ledger, no API, no
frontend, and no closure/readiness logic live here (those are later
Faz 2.8.20 stages, out of scope for Stage 1).

Design constraints (Stage 1 task brief, enforced structurally):

  - This module never writes to ``washer_resolution_ledger.json``,
    ``washer_resolution_decisions.json``, ``washer_library.json`` or
    ``washer_provenance_evidence.json`` -- it has no filesystem I/O
    of any kind.
  - ``WasherResolutionEvidence`` uses ``extra="forbid"`` and is
    frozen (immutable once constructed), mirroring
    ``WasherResolutionRecord`` (Faz 2.8.5) and
    ``WasherResolutionDecision`` (Faz 2.8.9): a closed set of
    evidence-workflow fields that structurally cannot carry a washer
    geometry/material override, a binary attachment, or the evidence
    document's own content -- only a reference/locator to where that
    evidence lives.
  - Checksum computation follows the project's canonical pattern
    (see ``backend.library.washer_resolution_decisions_store.
    compute_integrity_checksum``): ``sha256`` over
    ``json.dumps(payload, sort_keys=True, ensure_ascii=False)``, with
    ``integrity_checksum`` itself excluded from the payload it
    protects. ``sort_keys=True`` makes the digest independent of
    field/kwarg ordering by construction.
  - ``created_at``/``verified_at`` are plain, format-validated
    strings -- this module never calls a wall-clock function inside
    the Pydantic model itself. :func:`utc_now_iso` is the single
    wall-clock source, called only by :func:`create_washer_resolution_evidence`
    (mirrors ``washer_resolution_service.now_utc_iso8601``'s
    contract: the *caller*, not the model, decides when "now" is).
  - No closure-readiness scoring, no evidence-type weighting, no
    minimum-evidence-count enforcement, no cross-reference against
    ``washer_resolution_ledger.json`` or
    ``washer_provenance_evidence.json`` -- all deliberately deferred
    to a later stage (or explicitly never in scope), per the Stage 1
    task brief.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_validator,
    model_validator,
)

__all__ = [
    "EvidenceType",
    "EvidenceVerificationStatus",
    "WasherResolutionEvidence",
    "UTC_ISO8601_PATTERN",
    "is_valid_utc_iso8601",
    "SHA256_HEX_PATTERN",
    "is_valid_sha256_hex",
    "generate_evidence_id",
    "utc_now_iso",
    "compute_evidence_checksum",
    "verify_evidence_integrity",
    "create_washer_resolution_evidence",
]


# ---------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------


class EvidenceType(str, Enum):
    """Closed vocabulary for *what kind* of evidence a
    :class:`WasherResolutionEvidence` record represents.

    This stage assigns no closure weight or readiness score to any
    member -- that is explicitly out of scope (task brief rule)."""

    AUTHORITATIVE_STANDARD = "authoritative_standard"
    MANUFACTURER_DOCUMENT = "manufacturer_document"
    APPROVED_ENGINEERING_SOURCE = "approved_engineering_source"
    INTERNAL_MEASUREMENT = "internal_measurement"
    COMPARISON_ANALYSIS = "comparison_analysis"
    LEGACY_PROVENANCE_REFERENCE = "legacy_provenance_reference"
    OTHER = "other"


class EvidenceVerificationStatus(str, Enum):
    """Lifecycle status of one evidence record's own verification --
    distinct from (and never written back to) the washer resolution's
    own ``resolution_status``/effective status.

    Stage 1 only *carries* this value; no state-transition service
    exists yet. A newly created evidence record is always
    ``unverified`` -- see :func:`create_washer_resolution_evidence`."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"


# ---------------------------------------------------------------------
# Timestamp format validation (UTC ISO-8601, backend-generated only)
# ---------------------------------------------------------------------

#: Strict UTC ISO-8601: ``YYYY-MM-DDTHH:MM:SS(.ffffff)?Z``. Mirrors
#: ``washer_resolution_decisions.UTC_ISO8601_PATTERN`` exactly -- only
#: the ``Z`` (Zulu/UTC) offset form is accepted, since
#: :func:`utc_now_iso` is the only legitimate producer of
#: ``created_at``/``verified_at`` values.
UTC_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"
)


def is_valid_utc_iso8601(value: str) -> bool:
    """``True`` if ``value`` matches :data:`UTC_ISO8601_PATTERN`."""
    return bool(UTC_ISO8601_PATTERN.match(value))


# ---------------------------------------------------------------------
# Checksum format validation
# ---------------------------------------------------------------------

#: Lowercase, 64-character hex string -- the shape of a SHA-256
#: digest as produced by ``hashlib.sha256(...).hexdigest()``.
#: Deliberately case-sensitive (lowercase only): a checksum computed
#: by this module is always lowercase, so an uppercase value could
#: only originate from hand-editing or a different algorithm, and
#: must be rejected rather than case-normalized.
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def is_valid_sha256_hex(value: str) -> bool:
    """``True`` if ``value`` matches :data:`SHA256_HEX_PATTERN`."""
    return bool(SHA256_HEX_PATTERN.match(value))


# ---------------------------------------------------------------------
# ID / timestamp generation
# ---------------------------------------------------------------------


def generate_evidence_id() -> str:
    """Generate a unique evidence identifier. Not required to be
    deterministic -- only uniqueness and a readable ``WRE-`` prefix
    matter, mirroring the existing ``DEC-<uuid4>`` convention used by
    ``washer_resolution_service.decide_resolution`` for decision ids.
    """
    return f"WRE-{uuid.uuid4()}"


def utc_now_iso() -> str:
    """Backend-generated UTC ISO-8601 timestamp, ``Z``-suffixed,
    microsecond precision. Mirrors
    ``washer_resolution_service.now_utc_iso8601`` /
    ``washer_resolution_sync.now_utc_iso8601`` exactly -- the only
    wall-clock call in this module (see module docstring)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# ---------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------


def _normalize_required(value: str, field_name: str) -> str:
    """Strip surrounding whitespace; raise if the result is empty.
    Shared by every required string field's validator."""
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be blank")
    return stripped


def _normalize_optional(value: Optional[str], field_name: str) -> Optional[str]:
    """``None`` passes through unchanged. A provided value is
    stripped; a whitespace-only provided value is rejected rather
    than silently coerced to ``None``."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be whitespace-only")
    return stripped


class WasherResolutionEvidence(BaseModel):
    """One structured evidence record associated with a single
    ``backend.library.washer_resolution.WasherResolutionRecord`` (via
    ``resolution_id``). ``extra="forbid"`` and ``frozen=True`` are
    deliberate (see module docstring): a closed, immutable set of
    evidence-workflow fields. This model never stores the evidence
    document itself -- only a reference/locator to where it lives
    (``source_reference``, ``source_locator``, ``source_url``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    resolution_id: str
    evidence_type: EvidenceType
    title: str
    description: str
    source_reference: str
    source_locator: Optional[str] = None
    source_url: Optional[str] = None
    source_standard: Optional[str] = None
    verification_status: EvidenceVerificationStatus = EvidenceVerificationStatus.UNVERIFIED
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    created_by: str
    created_at: str
    integrity_checksum: str

    # -- required-field normalization (strip + reject blank) --------
    # One validator across all six required string fields;
    # ValidationInfo.field_name supplies the field name to
    # _normalize_required per-field, so error messages stay
    # field-specific without a separate function per field.

    @field_validator(
        "evidence_id", "resolution_id", "title", "description",
        "source_reference", "created_by",
    )
    @classmethod
    def _required_not_blank(cls, value: str, info: ValidationInfo) -> str:
        return _normalize_required(value, info.field_name)

    # -- optional-field normalization (strip + reject whitespace-only) --

    @field_validator("source_locator", "source_standard", "verified_by")
    @classmethod
    def _optional_normalize(
        cls, value: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        return _normalize_optional(value, info.field_name)

    # -- source_url: normalize, then require http(s):// prefix ------

    @field_validator("source_url")
    @classmethod
    def _source_url_normalize_and_validate(cls, value: Optional[str]) -> Optional[str]:
        normalized = _normalize_optional(value, "source_url")
        if normalized is not None and not (
            normalized.startswith("http://") or normalized.startswith("https://")
        ):
            raise ValueError("source_url must start with 'http://' or 'https://'")
        return normalized

    # -- timestamp format validation ---------------------------------

    @field_validator("created_at")
    @classmethod
    def _created_at_is_utc_iso8601(cls, value: str) -> str:
        if not is_valid_utc_iso8601(value):
            raise ValueError(
                "created_at must be UTC ISO-8601 with a 'Z' suffix, "
                f"got: {value!r}"
            )
        return value

    @field_validator("verified_at")
    @classmethod
    def _verified_at_is_utc_iso8601(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not is_valid_utc_iso8601(value):
            raise ValueError(
                "verified_at must be UTC ISO-8601 with a 'Z' suffix, "
                f"got: {value!r}"
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

    # -- cross-field rules --------------------------------------------

    @model_validator(mode="after")
    def _verification_fields_match_status(self) -> "WasherResolutionEvidence":
        if self.verification_status in (
            EvidenceVerificationStatus.VERIFIED,
            EvidenceVerificationStatus.REJECTED,
        ):
            if self.verified_by is None:
                raise ValueError(
                    f"verified_by is required when verification_status is "
                    f"'{self.verification_status.value}'"
                )
            if self.verified_at is None:
                raise ValueError(
                    f"verified_at is required when verification_status is "
                    f"'{self.verification_status.value}'"
                )
        else:  # UNVERIFIED
            if self.verified_by is not None:
                raise ValueError(
                    "verified_by must not be set when verification_status "
                    "is 'unverified'"
                )
            if self.verified_at is not None:
                raise ValueError(
                    "verified_at must not be set when verification_status "
                    "is 'unverified'"
                )
        return self

    @model_validator(mode="after")
    def _authoritative_standard_requires_source_standard(
        self,
    ) -> "WasherResolutionEvidence":
        if (
            self.evidence_type == EvidenceType.AUTHORITATIVE_STANDARD
            and self.source_standard is None
        ):
            raise ValueError(
                "source_standard is required when evidence_type is "
                "'authoritative_standard'"
            )
        return self

    # -- projection ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe projection (enums -> their ``.value``)."""
        return self.model_dump(mode="json")


# ---------------------------------------------------------------------
# Canonical checksum
# ---------------------------------------------------------------------


def compute_evidence_checksum(fields: Dict[str, Any]) -> str:
    """Canonical project checksum (mirrors
    ``washer_resolution_decisions_store.compute_integrity_checksum``)
    over every field in ``fields`` **except** ``integrity_checksum``
    itself, so the digest can be recomputed later from a persisted
    record to detect tampering.

    ``fields`` must already be JSON-safe (enum ``.value`` strings, not
    enum members). ``sort_keys=True`` makes the result independent of
    the input dict's key ordering; the same logical payload always
    produces the same checksum regardless of field order. Operates
    purely on the in-memory ``fields`` mapping -- no file is read or
    written.
    """
    payload = {k: v for k, v in fields.items() if k != "integrity_checksum"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_evidence_integrity(evidence: WasherResolutionEvidence) -> bool:
    """``True`` if ``evidence.integrity_checksum`` matches a fresh
    recomputation over its own fields -- i.e. the record has not been
    tampered with or hand-edited since it was created. Any change to
    a protected field (anything other than ``integrity_checksum``
    itself) makes this return ``False``."""
    payload = evidence.to_dict()
    return payload["integrity_checksum"] == compute_evidence_checksum(payload)


# ---------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------


def create_washer_resolution_evidence(
    *,
    resolution_id: str,
    evidence_type: EvidenceType,
    title: str,
    description: str,
    source_reference: str,
    created_by: str,
    source_locator: Optional[str] = None,
    source_url: Optional[str] = None,
    source_standard: Optional[str] = None,
) -> WasherResolutionEvidence:
    """Construct a fully-populated, checksummed, ``unverified``
    :class:`WasherResolutionEvidence`.

    Generates ``evidence_id`` (:func:`generate_evidence_id`) and
    ``created_at`` (:func:`utc_now_iso`) itself -- neither is accepted
    as a caller argument, so a caller can never backdate a record or
    forge its identity. ``verification_status`` is always
    ``unverified`` on creation (``verified_by``/``verified_at`` are
    always ``None``); recording a verification decision is a later
    stage's responsibility, not this factory's. Never writes to the
    filesystem (see module docstring).
    """
    evidence_id = generate_evidence_id()
    created_at = utc_now_iso()
    verification_status = EvidenceVerificationStatus.UNVERIFIED

    fields: Dict[str, Any] = {
        "evidence_id": evidence_id,
        "resolution_id": resolution_id,
        "evidence_type": getattr(evidence_type, "value", evidence_type),
        "title": title,
        "description": description,
        "source_reference": source_reference,
        "source_locator": source_locator,
        "source_url": source_url,
        "source_standard": source_standard,
        "verification_status": verification_status.value,
        "verified_by": None,
        "verified_at": None,
        "created_by": created_by,
        "created_at": created_at,
    }
    checksum = compute_evidence_checksum(fields)

    return WasherResolutionEvidence(
        evidence_id=evidence_id,
        resolution_id=resolution_id,
        evidence_type=evidence_type,
        title=title,
        description=description,
        source_reference=source_reference,
        source_locator=source_locator,
        source_url=source_url,
        source_standard=source_standard,
        verification_status=verification_status,
        verified_by=None,
        verified_at=None,
        created_by=created_by,
        created_at=created_at,
        integrity_checksum=checksum,
    )
