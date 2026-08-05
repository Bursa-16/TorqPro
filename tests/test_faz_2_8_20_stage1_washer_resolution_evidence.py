"""Faz 2.8.20 Stage 1 - unit tests for
``backend.library.washer_resolution_evidence``.

Pure domain-model tests: no filesystem I/O, no ledger, no API, no
frontend. Mirrors the test style of
``tests/test_faz_2_8_9_washer_resolution_workflow.py``.
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from backend.library.washer_resolution_evidence import (
    EvidenceType,
    EvidenceVerificationStatus,
    WasherResolutionEvidence,
    compute_evidence_checksum,
    create_washer_resolution_evidence,
    generate_evidence_id,
    is_valid_sha256_hex,
    is_valid_utc_iso8601,
    utc_now_iso,
    verify_evidence_integrity,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _valid_checksum_payload() -> dict:
    """A fields dict shaped exactly like
    ``create_washer_resolution_evidence`` would build internally,
    used to derive a real, matching checksum for direct-construction
    tests."""
    return {
        "evidence_id": "WRE-11111111-1111-1111-1111-111111111111",
        "resolution_id": "RES-WASH-DIN127B-M10",
        "evidence_type": EvidenceType.AUTHORITATIVE_STANDARD.value,
        "title": "DIN 125 boyut doğrulaması",
        "description": "Resmi DIN 125 standardı ile boyut karşılaştırması.",
        "source_reference": "DIN 125-1:1990, Tablo 2",
        "source_locator": None,
        "source_url": None,
        "source_standard": "DIN 125",
        "verification_status": EvidenceVerificationStatus.UNVERIFIED.value,
        "verified_by": None,
        "verified_at": None,
        "created_by": "ilhan",
        "created_at": "2026-01-15T10:00:00.000000Z",
    }


def _make_evidence(**overrides) -> WasherResolutionEvidence:
    payload = _valid_checksum_payload()
    payload.update(overrides)
    checksum = compute_evidence_checksum(payload)

    kwargs = dict(payload)
    kwargs.pop("verification_status")
    kwargs["evidence_type"] = EvidenceType(payload["evidence_type"])
    kwargs["verification_status"] = EvidenceVerificationStatus(
        payload["verification_status"]
    )
    kwargs["integrity_checksum"] = checksum
    return WasherResolutionEvidence(**kwargs)


def _minimal_kwargs(**overrides) -> dict:
    payload = _valid_checksum_payload()
    payload.update(overrides)
    checksum = compute_evidence_checksum(payload)
    kwargs = dict(payload)
    kwargs["evidence_type"] = EvidenceType(payload["evidence_type"])
    kwargs["verification_status"] = EvidenceVerificationStatus(
        payload["verification_status"]
    )
    kwargs["integrity_checksum"] = checksum
    return kwargs


# ---------------------------------------------------------------------
# 1-2. Enum membership
# ---------------------------------------------------------------------


def test_evidence_type_enum_values():
    assert {member.value for member in EvidenceType} == {
        "authoritative_standard",
        "manufacturer_document",
        "approved_engineering_source",
        "internal_measurement",
        "comparison_analysis",
        "legacy_provenance_reference",
        "other",
    }


def test_evidence_verification_status_enum_values():
    assert {member.value for member in EvidenceVerificationStatus} == {
        "unverified",
        "verified",
        "rejected",
    }


# ---------------------------------------------------------------------
# 3. Minimum valid model
# ---------------------------------------------------------------------


def test_minimum_valid_evidence_model_can_be_created():
    evidence = _make_evidence()
    assert evidence.evidence_id == "WRE-11111111-1111-1111-1111-111111111111"
    assert evidence.verification_status == EvidenceVerificationStatus.UNVERIFIED


# ---------------------------------------------------------------------
# 4. extra="forbid"
# ---------------------------------------------------------------------


def test_unknown_field_is_rejected():
    kwargs = _minimal_kwargs()
    kwargs["inner_diameter_mm"] = 10.5
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


# ---------------------------------------------------------------------
# 5-10. Required-field blank rejection
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    [
        "evidence_id",
        "resolution_id",
        "title",
        "description",
        "source_reference",
        "created_by",
    ],
)
def test_blank_required_field_is_rejected(field_name):
    kwargs = _minimal_kwargs()
    kwargs[field_name] = ""
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


# ---------------------------------------------------------------------
# 11. Whitespace-only values rejected
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    [
        "evidence_id",
        "resolution_id",
        "title",
        "description",
        "source_reference",
        "created_by",
    ],
)
def test_whitespace_only_required_field_is_rejected(field_name):
    kwargs = _minimal_kwargs()
    kwargs[field_name] = "   \t  "
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


def test_whitespace_only_optional_field_is_rejected():
    kwargs = _minimal_kwargs(source_locator="   ")
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


# ---------------------------------------------------------------------
# 12. String trim normalization
# ---------------------------------------------------------------------


def test_string_trim_normalization():
    kwargs = _minimal_kwargs()
    kwargs["title"] = "  DIN 125 boyut doğrulaması  "
    # Recompute checksum against the *stripped* value the model will
    # actually store, since compute_evidence_checksum expects the
    # already-normalized payload the factory would have used.
    payload = _valid_checksum_payload()
    payload["title"] = "DIN 125 boyut doğrulaması"
    kwargs["integrity_checksum"] = compute_evidence_checksum(payload)
    evidence = WasherResolutionEvidence(**kwargs)
    assert evidence.title == "DIN 125 boyut doğrulaması"


# ---------------------------------------------------------------------
# 13-14. created_at format validation
# ---------------------------------------------------------------------


def test_invalid_created_at_is_rejected():
    kwargs = _minimal_kwargs(created_at="not-a-timestamp")
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


def test_non_utc_timestamp_is_rejected():
    kwargs = _minimal_kwargs(created_at="2026-01-15T10:00:00.000000+02:00")
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


# ---------------------------------------------------------------------
# 15-16. Checksum format validation
# ---------------------------------------------------------------------


def test_invalid_checksum_is_rejected():
    kwargs = _minimal_kwargs()
    kwargs["integrity_checksum"] = "not-a-checksum"
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


def test_uppercase_checksum_is_rejected():
    kwargs = _minimal_kwargs()
    kwargs["integrity_checksum"] = kwargs["integrity_checksum"].upper()
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


# ---------------------------------------------------------------------
# 17-19. source_url validation
# ---------------------------------------------------------------------


def test_invalid_source_url_is_rejected():
    kwargs = _minimal_kwargs(source_url="ftp://example.com/doc.pdf")
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


@pytest.mark.parametrize(
    "url", ["http://example.com/doc.pdf", "https://example.com/doc.pdf"]
)
def test_valid_source_url_scheme_is_accepted(url):
    payload = _valid_checksum_payload()
    payload["source_url"] = url
    kwargs = dict(payload)
    kwargs["evidence_type"] = EvidenceType(payload["evidence_type"])
    kwargs["verification_status"] = EvidenceVerificationStatus(
        payload["verification_status"]
    )
    kwargs["integrity_checksum"] = compute_evidence_checksum(payload)
    evidence = WasherResolutionEvidence(**kwargs)
    assert evidence.source_url == url


# ---------------------------------------------------------------------
# 20-25. verification_status cross-field rules
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "verification_status,verified_by,verified_at",
    [
        # verified: missing verified_by / missing verified_at
        (EvidenceVerificationStatus.VERIFIED, None, "2026-01-16T09:00:00.000000Z"),
        (EvidenceVerificationStatus.VERIFIED, "reviewer1", None),
        # rejected: missing verified_by / missing verified_at
        (EvidenceVerificationStatus.REJECTED, None, "2026-01-16T09:00:00.000000Z"),
        (EvidenceVerificationStatus.REJECTED, "reviewer1", None),
        # unverified: verified_by set / verified_at set (must be absent)
        (EvidenceVerificationStatus.UNVERIFIED, "reviewer1", None),
        (EvidenceVerificationStatus.UNVERIFIED, None, "2026-01-16T09:00:00.000000Z"),
    ],
)
def test_verification_status_cross_field_violation_is_rejected(
    verification_status, verified_by, verified_at
):
    payload = _valid_checksum_payload()
    if verified_by is not None:
        payload["verified_by"] = verified_by
    if verified_at is not None:
        payload["verified_at"] = verified_at
    kwargs = dict(payload)
    kwargs["evidence_type"] = EvidenceType(payload["evidence_type"])
    kwargs["verification_status"] = verification_status
    kwargs["integrity_checksum"] = compute_evidence_checksum(payload)
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


def test_verified_status_with_both_fields_is_accepted():
    payload = _valid_checksum_payload()
    payload["verification_status"] = EvidenceVerificationStatus.VERIFIED.value
    payload["verified_by"] = "reviewer1"
    payload["verified_at"] = "2026-01-16T09:00:00.000000Z"
    kwargs = dict(payload)
    kwargs["evidence_type"] = EvidenceType(payload["evidence_type"])
    kwargs["verification_status"] = EvidenceVerificationStatus.VERIFIED
    kwargs["integrity_checksum"] = compute_evidence_checksum(payload)
    evidence = WasherResolutionEvidence(**kwargs)
    assert evidence.verification_status == EvidenceVerificationStatus.VERIFIED


# ---------------------------------------------------------------------
# 26-27. authoritative_standard requires source_standard
# ---------------------------------------------------------------------


def test_authoritative_standard_without_source_standard_is_rejected():
    payload = _valid_checksum_payload()
    payload["source_standard"] = None
    kwargs = dict(payload)
    kwargs["evidence_type"] = EvidenceType.AUTHORITATIVE_STANDARD
    kwargs["verification_status"] = EvidenceVerificationStatus.UNVERIFIED
    kwargs["integrity_checksum"] = compute_evidence_checksum(payload)
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)


def test_authoritative_standard_with_source_standard_is_accepted():
    evidence = _make_evidence(
        evidence_type=EvidenceType.AUTHORITATIVE_STANDARD.value,
        source_standard="DIN 125",
    )
    assert evidence.source_standard == "DIN 125"


# ---------------------------------------------------------------------
# 28. legacy_provenance_reference accepted without runtime file check
# ---------------------------------------------------------------------


def test_legacy_provenance_reference_accepted_without_file_verification():
    evidence = _make_evidence(
        evidence_type=EvidenceType.LEGACY_PROVENANCE_REFERENCE.value,
        source_reference=(
            "docs/phase_2_8/phase_2_8_4_washer_provenance_report.json"
            "#action_needed_records[record_id=WASH-DIN127B-M10]"
        ),
        source_standard=None,
    )
    assert evidence.evidence_type == EvidenceType.LEGACY_PROVENANCE_REFERENCE


# ---------------------------------------------------------------------
# 29-30. generate_evidence_id
# ---------------------------------------------------------------------


def test_generate_evidence_id_has_expected_prefix():
    evidence_id = generate_evidence_id()
    assert evidence_id.startswith("WRE-")


def test_two_generated_evidence_ids_are_unique():
    assert generate_evidence_id() != generate_evidence_id()


# ---------------------------------------------------------------------
# 31. utc_now_iso
# ---------------------------------------------------------------------


def test_utc_now_iso_produces_utc_z_suffix():
    value = utc_now_iso()
    assert value.endswith("Z")
    assert is_valid_utc_iso8601(value)


# ---------------------------------------------------------------------
# 32-34. Checksum determinism
# ---------------------------------------------------------------------


def test_same_payload_produces_same_checksum():
    payload = _valid_checksum_payload()
    assert compute_evidence_checksum(payload) == compute_evidence_checksum(
        copy.deepcopy(payload)
    )


def test_unicode_content_produces_deterministic_checksum():
    payload = _valid_checksum_payload()
    payload["description"] = "Ölçüm sonucu: ÇĞİÖŞÜ karakterleri içerir."
    checksum_a = compute_evidence_checksum(payload)
    checksum_b = compute_evidence_checksum(copy.deepcopy(payload))
    assert checksum_a == checksum_b
    assert is_valid_sha256_hex(checksum_a)


def test_field_ordering_does_not_change_checksum():
    payload = _valid_checksum_payload()
    reordered = dict(reversed(list(payload.items())))
    assert compute_evidence_checksum(payload) == compute_evidence_checksum(reordered)


# ---------------------------------------------------------------------
# 35-36. Integrity verification
# ---------------------------------------------------------------------


def test_tampered_protected_field_fails_integrity_verification():
    evidence = _make_evidence()
    tampered = evidence.model_copy(update={"title": "Tampered title"})
    assert verify_evidence_integrity(tampered) is False


def test_correct_model_passes_integrity_verification():
    evidence = _make_evidence()
    assert verify_evidence_integrity(evidence) is True


# ---------------------------------------------------------------------
# 37-39. Factory behaviour
# ---------------------------------------------------------------------


def test_factory_produces_valid_unverified_evidence():
    evidence = create_washer_resolution_evidence(
        resolution_id="RES-WASH-DIN127B-M10",
        evidence_type=EvidenceType.MANUFACTURER_DOCUMENT,
        title="Üretici datasheet karşılaştırması",
        description="Üretici katalog verisiyle boyutsal karşılaştırma.",
        source_reference="Acme Fasteners Catalog 2025, s. 42",
        created_by="ilhan",
    )
    assert evidence.verification_status == EvidenceVerificationStatus.UNVERIFIED
    assert evidence.verified_by is None
    assert evidence.verified_at is None
    assert evidence.evidence_id.startswith("WRE-")
    assert is_valid_utc_iso8601(evidence.created_at)
    assert verify_evidence_integrity(evidence) is True


def test_factory_does_not_accept_caller_provided_checksum_or_created_at():
    import inspect

    signature = inspect.signature(create_washer_resolution_evidence)
    assert "integrity_checksum" not in signature.parameters
    assert "created_at" not in signature.parameters
    assert "evidence_id" not in signature.parameters


def test_factory_does_not_create_filesystem_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    create_washer_resolution_evidence(
        resolution_id="RES-WASH-DIN127B-M10",
        evidence_type=EvidenceType.INTERNAL_MEASUREMENT,
        title="CMM ölçüm sonucu",
        description="Koordinat ölçüm makinesi ile doğrulama.",
        source_reference="CMM-REPORT-2026-01-15-001",
        created_by="ilhan",
    )
    after = set(tmp_path.iterdir())
    assert before == after


# ---------------------------------------------------------------------
# 40. Model rejects washer geometry fields
# ---------------------------------------------------------------------


def test_model_rejects_washer_geometry_fields():
    kwargs = _minimal_kwargs()
    kwargs["hardness"] = "HV200"
    with pytest.raises(ValidationError):
        WasherResolutionEvidence(**kwargs)
