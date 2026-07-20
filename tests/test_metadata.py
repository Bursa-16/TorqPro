"""Faz 2.4.1 tests: per-record provenance metadata.

Every population record must carry id, revision, source, version,
validation_status, approval_status, checksum and metadata (spec
"Hedef" section) -- and every file's own top-level metadata block
must be present and complete.
"""

from __future__ import annotations

import hashlib
import json

from backend.library import population

REQUIRED_FIELDS = {
    "id", "revision", "source", "version",
    "validation_status", "approval_status", "checksum", "metadata",
}
KNOWN_VALIDATION_STATUS = population.KNOWN_VALIDATION_STATUS
KNOWN_APPROVAL_STATUS = population.KNOWN_APPROVAL_STATUS


def _all_domain_records():
    for key in population.POPULATION_SOURCES:
        for record in population.load_population_records(key):
            yield key, record
    for record in population.oem_catalog():
        yield "oem library", record


def test_every_record_has_all_required_provenance_fields():
    for key, record in _all_domain_records():
        missing = REQUIRED_FIELDS - record.keys()
        assert not missing, f"{key}/{record.get('id')}: missing {missing}"


def test_every_record_id_is_nonempty_and_unique_within_its_domain():
    for key in population.POPULATION_SOURCES:
        records = population.load_population_records(key)
        ids = [r["id"] for r in records]
        assert all(ids), f"{key}: empty id present"
        assert len(ids) == len(set(ids)), f"{key}: duplicate ids"


def test_confidence_is_within_the_g1_g4_range():
    for key, record in _all_domain_records():
        assert record["confidence"] in (1, 2, 3, 4), f"{key}/{record['id']}"


def test_validation_and_approval_status_use_known_values():
    for key, record in _all_domain_records():
        assert record["validation_status"] in KNOWN_VALIDATION_STATUS, key
        assert record["approval_status"] in KNOWN_APPROVAL_STATUS, key


def test_only_validated_records_may_be_approved():
    # "Kaynağı doğrulanamayan hiçbir sayısal kayıt approved veya
    # validated durumunda bulunmamalı" -- approved implies validated.
    for key, record in _all_domain_records():
        if record["approval_status"] == "approved":
            assert record["validation_status"] == "validated", (
                f"{key}/{record['id']}: approved without validated"
            )


def test_metadata_only_and_provisional_records_are_never_approved():
    for key, record in _all_domain_records():
        if record["validation_status"] in ("metadata_only", "provisional", "reference_only"):
            assert record["approval_status"] == "pending", (
                f"{key}/{record['id']}: {record['validation_status']} "
                "record must not be approved"
            )


def test_checksum_is_a_valid_sha256_hex_digest():
    for key, record in _all_domain_records():
        checksum = record["checksum"]
        assert isinstance(checksum, str)
        assert len(checksum) == 64
        int(checksum, 16)  # raises ValueError if not valid hex


def test_checksum_matches_recomputation_over_the_rest_of_the_record():
    for key, record in _all_domain_records():
        payload = {k: v for k, v in record.items() if k != "checksum"}
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert record["checksum"] == expected, f"{key}/{record['id']}"


def test_every_data_file_has_top_level_metadata_block():
    for key, filename in population.POPULATION_SOURCES.items():
        import os

        path = os.path.join(population.DATA_DIR, filename)
        payload = json.load(open(path, encoding="utf-8"))
        meta = payload.get("metadata")
        assert meta, key
        assert meta.get("name")
        assert meta.get("version")
        assert meta.get("description")
