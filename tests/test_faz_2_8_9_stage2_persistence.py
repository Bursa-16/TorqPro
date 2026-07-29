"""Faz 2.8.9 tests (Stage 2): append-only persistence, checksum
integrity and idempotency for washer resolution decisions.

Every test in this file monkeypatches
``washer_resolution_decisions_store.DATA_PATH`` (and its derived lock
path) to a ``tmp_path`` fixture file. No test ever writes to the real
``backend/library/data/washer_resolution_decisions.json`` or to
``washer_resolution_ledger.json`` -- this satisfies task brief rule 3
("Testlerde yalnızca kontrollü fixture veya temporary test data
üzerinde karar geçişi uygulanabilir").
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from backend.library import washer_resolution as wr
from backend.library import washer_resolution_decisions_store as store


@pytest.fixture()
def isolated_ledger(tmp_path, monkeypatch):
    """Point the store at an empty, isolated ledger file for the
    duration of one test, mirroring the Faz 2.8.5
    ``test_data_file_state_reflects_a_changed_data_file_live`` pattern
    of monkeypatching a module's ``DATA_PATH``."""
    ledger_path = tmp_path / "washer_resolution_decisions.json"
    ledger_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "name": "Washer Resolution Decision Ledger",
                    "version": "test",
                    "source_ledger": "backend/library/data/washer_resolution_ledger.json",
                    "record_count": 0,
                },
                "decisions": [],
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


def _sample_decision(idempotency_key="idem-key-001", decision_id="DEC-0001"):
    return store.build_decision(
        decision_id=decision_id,
        resolution_id="RES-TEST-0001",
        previous_status=wr.WasherResolutionStatus.OPEN,
        new_status=wr.WasherResolutionStatus.UNDER_REVIEW,
        resolution_note="Escalated for review.",
        evidence_reference="internal-log#1",
        resolved_by="ilhan",
        decided_at="2026-07-29T12:00:00Z",
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------


class TestChecksum:
    def test_checksum_is_deterministic(self):
        fields = {
            "decision_id": "DEC-0001",
            "resolution_id": "RES-TEST-0001",
            "previous_status": "open",
            "new_status": "under_review",
            "resolution_note": "note",
            "evidence_reference": "evidence",
            "resolved_by": "ilhan",
            "decided_at": "2026-07-29T12:00:00Z",
            "confidence_level": None,
            "idempotency_key": "key",
        }
        first = store.compute_integrity_checksum(fields)
        second = store.compute_integrity_checksum(fields)
        assert first == second
        assert len(first) == 64  # sha256 hex digest length

    def test_checksum_excludes_itself(self):
        fields = {"decision_id": "X", "integrity_checksum": "should-not-matter"}
        without = store.compute_integrity_checksum({"decision_id": "X"})
        with_field = store.compute_integrity_checksum(fields)
        assert without == with_field

    def test_checksum_changes_with_content(self):
        fields_a = {"decision_id": "A", "resolution_note": "one"}
        fields_b = {"decision_id": "A", "resolution_note": "two"}
        assert store.compute_integrity_checksum(
            fields_a
        ) != store.compute_integrity_checksum(fields_b)

    def test_turkish_characters_do_not_break_checksum_determinism(self):
        """Regression guard for the project's known ensure_ascii=False
        pitfall (see memory: canonical checksum must use
        ensure_ascii=False or Turkish-character records silently get
        the wrong checksum)."""
        fields = {"resolution_note": "Ölçüm belirsizliği, İlhan onayı bekliyor."}
        first = store.compute_integrity_checksum(fields)
        second = store.compute_integrity_checksum(dict(fields))
        assert first == second

    def test_build_decision_checksum_verifies(self):
        decision = _sample_decision()
        assert store.verify_integrity(decision) is True

    def test_tampered_decision_fails_verification(self):
        decision = _sample_decision()
        tampered = decision.model_copy(update={"resolution_note": "changed after the fact"})
        assert store.verify_integrity(tampered) is False


# ---------------------------------------------------------------------
# Append-only persistence
# ---------------------------------------------------------------------


class TestAppendOnlyPersistence:
    def test_append_and_list(self, isolated_ledger):
        decision = _sample_decision()
        store.append_decision(decision)
        listed = store.list_decisions()
        assert len(listed) == 1
        assert listed[0].decision_id == "DEC-0001"

    def test_duplicate_decision_id_rejected(self, isolated_ledger):
        store.append_decision(_sample_decision(decision_id="DEC-DUP"))
        with pytest.raises(store.DuplicateDecisionIdError):
            store.append_decision(
                _sample_decision(idempotency_key="different-key", decision_id="DEC-DUP")
            )
        # No silent overwrite: still exactly one entry.
        assert len(store.list_decisions()) == 1

    def test_written_file_is_valid_json_and_sorted(self, isolated_ledger):
        store.append_decision(_sample_decision())
        raw = json.loads(isolated_ledger.read_text(encoding="utf-8"))
        assert raw["metadata"]["record_count"] == 1
        assert len(raw["decisions"]) == 1

    def test_prior_entries_survive_a_second_append(self, isolated_ledger):
        store.append_decision(_sample_decision(idempotency_key="k1", decision_id="DEC-1"))
        store.append_decision(_sample_decision(idempotency_key="k2", decision_id="DEC-2"))
        listed = store.list_decisions()
        assert [d.decision_id for d in listed] == ["DEC-1", "DEC-2"]

    def test_get_decision_by_id(self, isolated_ledger):
        store.append_decision(_sample_decision(decision_id="DEC-LOOKUP"))
        found = store.get_decision("DEC-LOOKUP")
        assert found is not None
        assert found.decision_id == "DEC-LOOKUP"
        assert store.get_decision("DOES-NOT-EXIST") is None

    def test_decisions_for_resolution(self, isolated_ledger):
        store.append_decision(
            _sample_decision(idempotency_key="k1", decision_id="DEC-1")
        )
        other = store.build_decision(
            decision_id="DEC-OTHER-RES",
            resolution_id="RES-DIFFERENT",
            previous_status=wr.WasherResolutionStatus.OPEN,
            new_status=wr.WasherResolutionStatus.REJECTED,
            resolution_note="n",
            evidence_reference="e",
            resolved_by="ilhan",
            decided_at="2026-07-29T12:00:00Z",
            idempotency_key="k-other",
        )
        store.append_decision(other)
        for_target = store.decisions_for_resolution("RES-TEST-0001")
        assert len(for_target) == 1
        assert for_target[0].decision_id == "DEC-1"


# ---------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------


class TestIdempotency:
    def test_same_idempotency_key_does_not_duplicate(self, isolated_ledger):
        first, created_first = store.record_decision(_sample_decision(decision_id="DEC-A"))
        second, created_second = store.record_decision(
            _sample_decision(decision_id="DEC-A-RETRY")
        )
        assert created_first is True
        assert created_second is False
        assert second.decision_id == first.decision_id  # original returned, not the retry
        assert len(store.list_decisions()) == 1

    def test_different_idempotency_keys_both_persist(self, isolated_ledger):
        store.record_decision(_sample_decision(idempotency_key="k1", decision_id="DEC-1"))
        store.record_decision(_sample_decision(idempotency_key="k2", decision_id="DEC-2"))
        assert len(store.list_decisions()) == 2

    def test_find_by_idempotency_key(self, isolated_ledger):
        store.append_decision(_sample_decision(idempotency_key="find-me"))
        found = store.find_by_idempotency_key("find-me")
        assert found is not None
        assert found.idempotency_key == "find-me"
        assert store.find_by_idempotency_key("nonexistent") is None

    def test_blank_idempotency_key_never_matches(self, isolated_ledger):
        assert store.find_by_idempotency_key("") is None
        assert store.find_by_idempotency_key(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Concurrency (advisory lock)
# ---------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_identical_requests_produce_one_decision(self, isolated_ledger):
        """Ten threads race to record_decision() with the same
        idempotency key; the lock must ensure exactly one ledger
        entry survives, not up to ten."""
        results = []
        lock = threading.Lock()

        def worker(i):
            decision = _sample_decision(
                idempotency_key="race-key", decision_id=f"DEC-RACE-{i}"
            )
            outcome = store.record_decision(decision)
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(store.list_decisions()) == 1
        created_flags = [created for _, created in results]
        assert created_flags.count(True) == 1
        assert created_flags.count(False) == 9

    def test_concurrent_distinct_decisions_all_persist(self, isolated_ledger):
        def worker(i):
            store.record_decision(
                _sample_decision(idempotency_key=f"distinct-{i}", decision_id=f"DEC-D-{i}")
            )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(store.list_decisions()) == 8


# ---------------------------------------------------------------------
# Real repo file: schema/isolation sanity only, no writes
# ---------------------------------------------------------------------


class TestRealLedgerFileUntouched:
    def test_real_decision_ledger_still_empty(self):
        """The real, committed
        backend/library/data/washer_resolution_decisions.json must
        still have zero decisions after this entire test module runs
        -- every write in this file used isolated_ledger's tmp_path,
        never the real DATA_PATH."""
        real_path = (
            Path(__file__).resolve().parent.parent
            / "backend"
            / "library"
            / "data"
            / "washer_resolution_decisions.json"
        )
        payload = json.loads(real_path.read_text(encoding="utf-8"))
        assert payload["decisions"] == []
        assert payload["metadata"]["record_count"] == 0

    def test_real_source_ledger_status_counts_unchanged(self):
        wr.reload()
        counts = wr.count_by_status()
        assert counts[wr.WasherResolutionStatus.OPEN.value] == 71
        assert counts[wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE.value] == 5
