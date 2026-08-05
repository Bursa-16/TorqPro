"""Faz 2.8.20 Stage 2 tests: append-only persistence, duplicate-id
rejection, atomic write, locking and checksum integrity for the
washer resolution evidence ledger.

Every test in this file monkeypatches
``washer_resolution_evidence_store.DATA_PATH`` (and its derived lock
path) to a ``tmp_path`` fixture file, mirroring
``tests/test_faz_2_8_9_stage2_persistence.py``'s ``isolated_ledger``
pattern. No test ever writes to the real
``backend/library/data/washer_resolution_evidence.json`` or to any
other washer-resolution ledger file.
"""

from __future__ import annotations

import json
import threading

import pytest

from backend.library import washer_resolution_evidence_store as store
from backend.library.washer_resolution_evidence import (
    EvidenceType,
    WasherResolutionEvidence,
    compute_evidence_checksum,
    create_washer_resolution_evidence,
    verify_evidence_integrity,
)


@pytest.fixture()
def isolated_ledger(tmp_path, monkeypatch):
    """Point the store at an empty, isolated evidence ledger file for
    the duration of one test."""
    ledger_path = tmp_path / "washer_resolution_evidence.json"
    ledger_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "name": "Washer Resolution Evidence Ledger",
                    "version": "test",
                    "record_count": 0,
                },
                "evidence": [],
            }
        ),
        encoding="utf-8",
    )
    lock_path = ledger_path.with_suffix(".lock")
    monkeypatch.setattr(store, "DATA_PATH", ledger_path)
    monkeypatch.setattr(store, "_LOCK_PATH", lock_path)
    store.reload()
    yield ledger_path
    store.reload()


def _sample_evidence(resolution_id="RES-TEST-0001", **overrides) -> WasherResolutionEvidence:
    kwargs = dict(
        resolution_id=resolution_id,
        evidence_type=EvidenceType.MANUFACTURER_DOCUMENT,
        title="Test evidence",
        description="Test evidence description.",
        source_reference="Test Catalog 2026, p. 1",
        created_by="ilhan",
    )
    kwargs.update(overrides)
    return create_washer_resolution_evidence(**kwargs)


# ---------------------------------------------------------------------
# Append-only behaviour
# ---------------------------------------------------------------------


class TestAppendBehaviour:
    def test_append_and_list(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        all_evidence = store.list_all_evidence()
        assert len(all_evidence) == 1
        assert all_evidence[0].evidence_id == evidence.evidence_id

    def test_written_file_is_valid_json_and_sorted(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        raw_text = isolated_ledger.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
        assert payload["evidence"][0]["evidence_id"] == evidence.evidence_id
        # sort_keys=True: top-level keys are alphabetical.
        assert list(payload.keys()) == sorted(payload.keys())

    def test_prior_entries_survive_a_second_append(self, isolated_ledger):
        first = _sample_evidence(resolution_id="RES-TEST-0001")
        second = _sample_evidence(resolution_id="RES-TEST-0002")
        store.append_evidence(first)
        store.append_evidence(second)
        all_evidence = store.list_all_evidence()
        assert len(all_evidence) == 2
        assert {e.evidence_id for e in all_evidence} == {
            first.evidence_id,
            second.evidence_id,
        }

    def test_metadata_record_count_updates_on_append(self, isolated_ledger):
        store.append_evidence(_sample_evidence())
        store.append_evidence(_sample_evidence())
        payload = json.loads(isolated_ledger.read_text(encoding="utf-8"))
        assert payload["metadata"]["record_count"] == 2

    def test_no_update_or_delete_method_exists(self):
        """Confirms the append-only design surface directly: no
        update/delete function is exported by this module."""
        assert not hasattr(store, "update_evidence")
        assert not hasattr(store, "delete_evidence")
        assert not hasattr(store, "remove_evidence")


# ---------------------------------------------------------------------
# Duplicate evidence_id rejection
# ---------------------------------------------------------------------


class TestDuplicateIdRejection:
    def test_duplicate_evidence_id_rejected(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        with pytest.raises(store.DuplicateEvidenceIdError):
            store.append_evidence(evidence)

    def test_duplicate_rejection_does_not_corrupt_existing_entry(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        with pytest.raises(store.DuplicateEvidenceIdError):
            store.append_evidence(evidence)
        all_evidence = store.list_all_evidence()
        assert len(all_evidence) == 1
        assert all_evidence[0].evidence_id == evidence.evidence_id

    def test_duplicate_error_message_contains_evidence_id(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        with pytest.raises(store.DuplicateEvidenceIdError) as excinfo:
            store.append_evidence(evidence)
        assert evidence.evidence_id in str(excinfo.value)
        assert excinfo.value.evidence_id == evidence.evidence_id


# ---------------------------------------------------------------------
# Listing / lookup
# ---------------------------------------------------------------------


class TestListingAndLookup:
    def test_get_evidence_by_id(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        found = store.get_evidence(evidence.evidence_id)
        assert found is not None
        assert found.evidence_id == evidence.evidence_id

    def test_get_evidence_missing_id_returns_none(self, isolated_ledger):
        assert store.get_evidence("WRE-does-not-exist") is None

    def test_list_all_evidence_empty_ledger_returns_empty_list(self, isolated_ledger):
        assert store.list_all_evidence() == []

    def test_list_all_evidence_preserves_append_order(self, isolated_ledger):
        first = _sample_evidence(resolution_id="RES-TEST-0001")
        second = _sample_evidence(resolution_id="RES-TEST-0002")
        third = _sample_evidence(resolution_id="RES-TEST-0003")
        store.append_evidence(first)
        store.append_evidence(second)
        store.append_evidence(third)
        ids_in_order = [e.evidence_id for e in store.list_all_evidence()]
        assert ids_in_order == [first.evidence_id, second.evidence_id, third.evidence_id]


# ---------------------------------------------------------------------
# resolution_id filtering
# ---------------------------------------------------------------------


class TestResolutionFiltering:
    def test_evidence_for_resolution_returns_matching_only(self, isolated_ledger):
        match_a = _sample_evidence(resolution_id="RES-TEST-0001")
        match_b = _sample_evidence(resolution_id="RES-TEST-0001")
        other = _sample_evidence(resolution_id="RES-TEST-0002")
        store.append_evidence(match_a)
        store.append_evidence(match_b)
        store.append_evidence(other)
        result = store.evidence_for_resolution("RES-TEST-0001")
        assert {e.evidence_id for e in result} == {match_a.evidence_id, match_b.evidence_id}

    def test_evidence_for_resolution_no_match_returns_empty_list(self, isolated_ledger):
        store.append_evidence(_sample_evidence(resolution_id="RES-TEST-0001"))
        assert store.evidence_for_resolution("RES-TEST-9999") == []

    def test_evidence_for_resolution_does_not_validate_against_ledger(self, isolated_ledger):
        """Task brief decision 1: no resolution_id existence check.
        A resolution_id that does not exist in
        washer_resolution_ledger.json is still accepted and stored."""
        evidence = _sample_evidence(resolution_id="RES-DOES-NOT-EXIST-IN-LEDGER")
        store.append_evidence(evidence)
        assert store.evidence_for_resolution("RES-DOES-NOT-EXIST-IN-LEDGER") == [evidence]


# ---------------------------------------------------------------------
# Checksum integrity (imported unchanged from Stage 1, not reimplemented)
# ---------------------------------------------------------------------


class TestChecksumIntegrity:
    def test_persisted_evidence_passes_integrity_verification(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        reloaded = store.get_evidence(evidence.evidence_id)
        assert verify_evidence_integrity(reloaded) is True

    def test_checksum_survives_json_roundtrip_unchanged(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        reloaded = store.get_evidence(evidence.evidence_id)
        assert reloaded.integrity_checksum == evidence.integrity_checksum

    def test_hand_edited_file_fails_integrity_verification(self, isolated_ledger):
        evidence = _sample_evidence()
        store.append_evidence(evidence)
        payload = json.loads(isolated_ledger.read_text(encoding="utf-8"))
        payload["evidence"][0]["title"] = "Tampered by hand"
        isolated_ledger.write_text(json.dumps(payload), encoding="utf-8")
        store.reload()
        tampered = store.get_evidence(evidence.evidence_id)
        assert verify_evidence_integrity(tampered) is False

    def test_this_module_does_not_reimplement_checksum_computation(self):
        """Structural check for task brief decision 3: the store
        module has no local checksum function of its own -- it only
        imports the WasherResolutionEvidence model, which already
        carries its own checksum."""
        assert not hasattr(store, "compute_integrity_checksum")
        assert not hasattr(store, "compute_evidence_checksum")
        assert compute_evidence_checksum is not None  # imported and usable directly


# ---------------------------------------------------------------------
# Atomic write behaviour
# ---------------------------------------------------------------------


class TestAtomicWrite:
    def test_no_temp_files_left_behind_after_append(self, isolated_ledger):
        store.append_evidence(_sample_evidence())
        leftovers = list(isolated_ledger.parent.glob(".washer_resolution_evidence.*.tmp"))
        assert leftovers == []

    def test_write_uses_os_replace_not_in_place_edit(self, isolated_ledger, monkeypatch):
        """Verifies the atomic-replace call is actually exercised."""
        calls = []
        original_replace = store.os.replace

        def _tracking_replace(src, dst):
            calls.append((src, dst))
            return original_replace(src, dst)

        monkeypatch.setattr(store.os, "replace", _tracking_replace)
        store.append_evidence(_sample_evidence())
        assert len(calls) == 1
        assert str(calls[0][1]) == str(isolated_ledger)


# ---------------------------------------------------------------------
# Locking / concurrency
# ---------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_distinct_appends_all_persist(self, isolated_ledger):
        evidences = [_sample_evidence(resolution_id=f"RES-TEST-{i:04d}") for i in range(8)]
        errors = []

        def _append(item):
            try:
                store.append_evidence(item)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_append, args=(e,)) for e in evidences]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        stored_ids = {e.evidence_id for e in store.list_all_evidence()}
        assert stored_ids == {e.evidence_id for e in evidences}

    def test_concurrent_duplicate_appends_only_one_succeeds(self, isolated_ledger):
        evidence = _sample_evidence()
        results = []
        errors = []

        def _append():
            try:
                store.append_evidence(evidence)
                results.append("ok")
            except store.DuplicateEvidenceIdError:
                errors.append("duplicate")

        threads = [threading.Thread(target=_append) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results == ["ok"]
        assert len(errors) == 4
        assert len(store.list_all_evidence()) == 1


# ---------------------------------------------------------------------
# Real data file untouched
# ---------------------------------------------------------------------


class TestRealLedgerFileUntouched:
    def test_real_evidence_ledger_still_empty(self):
        with store.DATA_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        assert payload["evidence"] == []
        assert payload["metadata"]["record_count"] == 0

    def test_real_source_ledger_and_decisions_ledger_unaffected(self):
        from backend.library import washer_resolution as wr
        from backend.library.washer_resolution_decisions_store import (
            list_decisions,
        )

        assert len(wr.list_washer_resolutions()) == 76
        assert list_decisions() == []
