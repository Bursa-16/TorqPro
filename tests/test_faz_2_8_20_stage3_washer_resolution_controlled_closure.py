"""Faz 2.8.20 Stage 3 tests: closure domain model, closure persistence,
and the controlled closure service functions added to
``washer_resolution_service.py``.

Every test isolates all four ledgers it touches (source, decisions,
evidence, closure) via ``tmp_path``/``monkeypatch``, mirroring
``tests/test_faz_2_8_9_stage2_persistence.py`` and
``tests/test_faz_2_8_20_stage2_washer_resolution_evidence_persistence.py``.
No test ever writes to any real ``backend/library/data/*.json`` file.
"""

from __future__ import annotations

import json
import threading

import pytest
from pydantic import ValidationError

from backend.library import washer_resolution as wr
from backend.library import washer_resolution_closure as wc
from backend.library import washer_resolution_closure_store as wc_store
from backend.library import washer_resolution_decisions_store as decisions_store
from backend.library import washer_resolution_evidence as we
from backend.library import washer_resolution_evidence_store as we_store
from backend.library import washer_resolution_service as svc


# ---------------------------------------------------------------------
# Full-stack isolation fixture (source + decisions + evidence + closure)
# ---------------------------------------------------------------------


@pytest.fixture()
def isolated_stack(tmp_path, monkeypatch):
    """Isolates all four ledgers the closure service cross-references,
    seeded with three controlled source-ledger records:

      - ``RES-TEST-OPEN``: normal, undecided record.
      - ``RES-TEST-BLOCKED``: ``blocked_authoritative_source``.
      - ``RES-TEST-SECOND``: a second normal, undecided record.
    """
    ledger_path = tmp_path / "washer_resolution_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "name": "Test Ledger",
                "version": "test",
                "record_count": 3,
                "records": [
                    {
                        "resolution_id": "RES-TEST-OPEN",
                        "washer_record_id": "WASH-TEST-1",
                        "issue_type": "source_missing",
                    },
                    {
                        "resolution_id": "RES-TEST-BLOCKED",
                        "washer_record_id": "WASH-TEST-2",
                        "issue_type": "standard_identity_ambiguous",
                        "resolution_status": "blocked_authoritative_source",
                        "requires_authoritative_source": True,
                    },
                    {
                        "resolution_id": "RES-TEST-SECOND",
                        "washer_record_id": "WASH-TEST-3",
                        "issue_type": "verification_pending",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(wr, "DATA_PATH", ledger_path)
    wr.reload()

    decisions_path = tmp_path / "washer_resolution_decisions.json"
    decisions_path.write_text(
        json.dumps({"metadata": {"record_count": 0}, "decisions": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(decisions_store, "DATA_PATH", decisions_path)
    monkeypatch.setattr(decisions_store, "_LOCK_PATH", decisions_path.with_suffix(".lock"))
    decisions_store.reload()

    evidence_path = tmp_path / "washer_resolution_evidence.json"
    evidence_path.write_text(
        json.dumps({"metadata": {"record_count": 0}, "evidence": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(we_store, "DATA_PATH", evidence_path)
    monkeypatch.setattr(we_store, "_LOCK_PATH", evidence_path.with_suffix(".lock"))
    we_store.reload()

    closure_path = tmp_path / "washer_resolution_closure.json"
    closure_path.write_text(
        json.dumps({"metadata": {"record_count": 0}, "closures": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(wc_store, "DATA_PATH", closure_path)
    monkeypatch.setattr(wc_store, "_LOCK_PATH", closure_path.with_suffix(".lock"))
    wc_store.reload()

    yield {
        "ledger_path": ledger_path,
        "decisions_path": decisions_path,
        "evidence_path": evidence_path,
        "closure_path": closure_path,
    }

    wr.reload()
    decisions_store.reload()
    we_store.reload()
    wc_store.reload()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _add_verified_evidence(resolution_id="RES-TEST-OPEN", verification_status=we.EvidenceVerificationStatus.VERIFIED, **overrides):
    evidence = we.create_washer_resolution_evidence(
        resolution_id=resolution_id,
        evidence_type=we.EvidenceType.MANUFACTURER_DOCUMENT,
        title="Test evidence",
        description="Test evidence description.",
        source_reference="Test Catalog 2026, p. 1",
        created_by="ilhan",
    )
    if verification_status != we.EvidenceVerificationStatus.UNVERIFIED:
        fields = evidence.model_dump(mode="json")
        fields["verification_status"] = verification_status.value
        fields["verified_by"] = "reviewer1"
        fields["verified_at"] = "2026-01-16T09:00:00.000000Z"
        checksum = we.compute_evidence_checksum(fields)
        evidence = we.WasherResolutionEvidence(
            evidence_id=fields["evidence_id"],
            resolution_id=fields["resolution_id"],
            evidence_type=we.EvidenceType(fields["evidence_type"]),
            title=fields["title"],
            description=fields["description"],
            source_reference=fields["source_reference"],
            source_locator=fields["source_locator"],
            source_url=fields["source_url"],
            source_standard=fields["source_standard"],
            verification_status=verification_status,
            verified_by=fields["verified_by"],
            verified_at=fields["verified_at"],
            created_by=fields["created_by"],
            created_at=fields["created_at"],
            integrity_checksum=checksum,
        )
    we_store.append_evidence(evidence)
    return evidence


def _decide_to_terminal(resolution_id="RES-TEST-OPEN", new_status=wr.WasherResolutionStatus.RESOLVED):
    decision, _ = svc.decide_resolution(
        resolution_id=resolution_id,
        new_status=new_status,
        resolution_note="Resolved for test purposes.",
        evidence_reference="test-evidence-ref",
        resolved_by="ilhan",
        idempotency_key=f"idem-{resolution_id}-{new_status.value}",
    )
    return decision


# =======================================================================
# WasherResolutionClosure domain model
# =======================================================================


def _valid_closure_payload():
    return {
        "closure_id": "CLR-11111111-1111-1111-1111-111111111111",
        "resolution_id": "RES-TEST-OPEN",
        "closure_status": "closed",
        "closure_rationale": "All evidence verified; closing.",
        "closed_by": "ilhan",
        "evidence_ids": ["WRE-aaaa", "WRE-bbbb"],
        "decision_id": "DEC-cccc",
        "closed_at": "2026-01-20T10:00:00.000000Z",
    }


def _closure_kwargs(**overrides):
    payload = _valid_closure_payload()
    payload.update(overrides)
    checksum = wc.compute_closure_checksum(payload)
    kwargs = dict(payload)
    kwargs["integrity_checksum"] = checksum
    return kwargs


class TestClosureDomainModel:
    def test_minimum_valid_closure_model(self):
        closure = wc.WasherResolutionClosure(**_closure_kwargs())
        assert closure.closure_status == "closed"

    def test_extra_field_rejected(self):
        kwargs = _closure_kwargs()
        kwargs["reopened_at"] = "2026-01-21T10:00:00.000000Z"
        with pytest.raises(ValidationError):
            wc.WasherResolutionClosure(**kwargs)

    def test_blank_closure_rationale_rejected(self):
        kwargs = _closure_kwargs(closure_rationale="   ")
        with pytest.raises(ValidationError):
            wc.WasherResolutionClosure(**kwargs)

    def test_blank_closed_by_rejected(self):
        kwargs = _closure_kwargs(closed_by="")
        with pytest.raises(ValidationError):
            wc.WasherResolutionClosure(**kwargs)

    def test_non_utc_closed_at_rejected(self):
        kwargs = _closure_kwargs(closed_at="2026-01-20T10:00:00.000000+02:00")
        with pytest.raises(ValidationError):
            wc.WasherResolutionClosure(**kwargs)

    def test_empty_evidence_ids_rejected(self):
        kwargs = _closure_kwargs(evidence_ids=[])
        with pytest.raises(ValidationError):
            wc.WasherResolutionClosure(**kwargs)

    def test_duplicate_evidence_ids_rejected(self):
        kwargs = _closure_kwargs(evidence_ids=["WRE-aaaa", "WRE-aaaa"])
        with pytest.raises(ValidationError):
            wc.WasherResolutionClosure(**kwargs)

    def test_invalid_checksum_rejected(self):
        kwargs = _closure_kwargs()
        kwargs["integrity_checksum"] = "not-a-checksum"
        with pytest.raises(ValidationError):
            wc.WasherResolutionClosure(**kwargs)

    def test_closure_status_other_than_closed_rejected(self):
        payload = _valid_closure_payload()
        payload["closure_status"] = "reopened"
        checksum = wc.compute_closure_checksum(payload)
        kwargs = dict(payload)
        kwargs["integrity_checksum"] = checksum
        with pytest.raises(ValidationError):
            wc.WasherResolutionClosure(**kwargs)

    def test_checksum_is_deterministic(self):
        payload = _valid_closure_payload()
        assert wc.compute_closure_checksum(payload) == wc.compute_closure_checksum(dict(payload))

    def test_tamper_detection(self):
        closure = wc.WasherResolutionClosure(**_closure_kwargs())
        tampered = closure.model_copy(update={"closure_rationale": "Tampered"})
        assert wc.verify_closure_integrity(tampered) is False

    def test_correct_closure_passes_integrity_verification(self):
        closure = wc.WasherResolutionClosure(**_closure_kwargs())
        assert wc.verify_closure_integrity(closure) is True

    def test_factory_produces_valid_closed_closure(self):
        closure = wc.create_washer_resolution_closure(
            resolution_id="RES-TEST-OPEN",
            closure_rationale="Closing for test.",
            closed_by="ilhan",
            evidence_ids=["WRE-aaaa"],
            decision_id="DEC-bbbb",
        )
        assert closure.closure_status == "closed"
        assert closure.closure_id.startswith("CLR-")
        assert wc.verify_closure_integrity(closure) is True

    def test_model_has_no_reopen_field(self):
        assert "reopened_at" not in wc.WasherResolutionClosure.model_fields
        assert "reopened_by" not in wc.WasherResolutionClosure.model_fields


# =======================================================================
# Closure persistence
# =======================================================================


class TestClosureStore:
    def test_append_get_list(self, isolated_stack):
        closure = wc.create_washer_resolution_closure(
            resolution_id="RES-TEST-OPEN",
            closure_rationale="r",
            closed_by="ilhan",
            evidence_ids=["WRE-1"],
            decision_id="DEC-1",
        )
        wc_store.append_closure(closure)
        assert wc_store.get_closure_for_resolution("RES-TEST-OPEN").closure_id == closure.closure_id
        assert len(wc_store.list_all_closures()) == 1

    def test_duplicate_resolution_closure_rejected(self, isolated_stack):
        closure = wc.create_washer_resolution_closure(
            resolution_id="RES-TEST-OPEN", closure_rationale="r", closed_by="ilhan",
            evidence_ids=["WRE-1"], decision_id="DEC-1",
        )
        wc_store.append_closure(closure)
        second = wc.create_washer_resolution_closure(
            resolution_id="RES-TEST-OPEN", closure_rationale="r2", closed_by="ilhan",
            evidence_ids=["WRE-2"], decision_id="DEC-2",
        )
        with pytest.raises(wc_store.DuplicateClosureError):
            wc_store.append_closure(second)

    def test_append_order_preserved(self, isolated_stack):
        first = wc.create_washer_resolution_closure(
            resolution_id="RES-TEST-OPEN", closure_rationale="r", closed_by="ilhan",
            evidence_ids=["WRE-1"], decision_id="DEC-1",
        )
        second = wc.create_washer_resolution_closure(
            resolution_id="RES-TEST-SECOND", closure_rationale="r", closed_by="ilhan",
            evidence_ids=["WRE-2"], decision_id="DEC-2",
        )
        wc_store.append_closure(first)
        wc_store.append_closure(second)
        ids = [c.closure_id for c in wc_store.list_all_closures()]
        assert ids == [first.closure_id, second.closure_id]

    def test_concurrent_same_resolution_only_one_succeeds(self, isolated_stack):
        results, errors = [], []

        def _attempt(rationale):
            closure = wc.create_washer_resolution_closure(
                resolution_id="RES-TEST-OPEN", closure_rationale=rationale, closed_by="ilhan",
                evidence_ids=["WRE-1"], decision_id="DEC-1",
            )
            try:
                wc_store.append_closure(closure)
                results.append("ok")
            except wc_store.DuplicateClosureError:
                errors.append("duplicate")

        threads = [threading.Thread(target=_attempt, args=(f"r{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results == ["ok"]
        assert len(errors) == 4
        assert len(wc_store.list_all_closures()) == 1

    def test_no_update_or_delete_method_exists(self):
        assert not hasattr(wc_store, "update_closure")
        assert not hasattr(wc_store, "delete_closure")
        assert not hasattr(wc_store, "reopen_closure")

    def test_real_closure_ledger_unchanged(self):
        with wc_store.DATA_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        assert payload["closures"] == []
        assert payload["metadata"]["record_count"] == 0


# =======================================================================
# Service: record_resolution_evidence / resolution_evidence_for
# =======================================================================


class TestRecordAndFetchEvidence:
    def test_resolution_not_found_rejects_evidence(self, isolated_stack):
        with pytest.raises(svc.ResolutionNotFoundError):
            svc.record_resolution_evidence(
                resolution_id="RES-DOES-NOT-EXIST",
                evidence_type=we.EvidenceType.OTHER,
                title="t", description="d", source_reference="s", created_by="u",
            )

    def test_record_resolution_evidence_persists(self, isolated_stack):
        evidence = svc.record_resolution_evidence(
            resolution_id="RES-TEST-OPEN",
            evidence_type=we.EvidenceType.MANUFACTURER_DOCUMENT,
            title="t", description="d", source_reference="s", created_by="u",
        )
        assert we_store.get_evidence(evidence.evidence_id) is not None

    def test_resolution_evidence_for_rejects_corrupted_persisted_evidence(self, isolated_stack):
        evidence = _add_verified_evidence()
        # Hand-corrupt the persisted record.
        payload = json.loads(isolated_stack["evidence_path"].read_text(encoding="utf-8"))
        payload["evidence"][0]["title"] = "Tampered by hand"
        isolated_stack["evidence_path"].write_text(json.dumps(payload), encoding="utf-8")
        we_store.reload()
        with pytest.raises(svc.EvidenceIntegrityError):
            svc.resolution_evidence_for("RES-TEST-OPEN")

    def test_resolution_evidence_for_unknown_resolution_rejected(self, isolated_stack):
        with pytest.raises(svc.ResolutionNotFoundError):
            svc.resolution_evidence_for("RES-DOES-NOT-EXIST")


# =======================================================================
# Service: evaluate_closure_readiness
# =======================================================================


class TestClosureReadiness:
    def test_no_evidence_not_ready(self, isolated_stack):
        _decide_to_terminal()
        readiness = svc.evaluate_closure_readiness("RES-TEST-OPEN")
        assert readiness.is_ready is False
        assert any("verified evidence" in r for r in readiness.blocking_reasons)

    def test_only_unverified_evidence_not_ready(self, isolated_stack):
        _decide_to_terminal()
        _add_verified_evidence(verification_status=we.EvidenceVerificationStatus.UNVERIFIED)
        readiness = svc.evaluate_closure_readiness("RES-TEST-OPEN")
        assert readiness.is_ready is False
        assert readiness.verified_evidence_ids == []
        assert len(readiness.unverified_evidence_ids) == 1

    def test_only_rejected_evidence_not_ready(self, isolated_stack):
        _decide_to_terminal()
        _add_verified_evidence(verification_status=we.EvidenceVerificationStatus.REJECTED)
        readiness = svc.evaluate_closure_readiness("RES-TEST-OPEN")
        assert readiness.is_ready is False
        assert readiness.verified_evidence_ids == []
        assert len(readiness.rejected_evidence_ids) == 1

    def test_verified_evidence_but_non_terminal_decision_not_ready(self, isolated_stack):
        svc.decide_resolution(
            resolution_id="RES-TEST-OPEN",
            new_status=wr.WasherResolutionStatus.UNDER_REVIEW,
            resolution_note="Escalated.", evidence_reference="ref", resolved_by="ilhan",
            idempotency_key="idem-under-review",
        )
        _add_verified_evidence()
        readiness = svc.evaluate_closure_readiness("RES-TEST-OPEN")
        assert readiness.is_ready is False
        assert any("not terminal" in r for r in readiness.blocking_reasons)

    def test_terminal_decision_and_verified_evidence_ready(self, isolated_stack):
        decision = _decide_to_terminal()
        evidence = _add_verified_evidence()
        readiness = svc.evaluate_closure_readiness("RES-TEST-OPEN")
        assert readiness.is_ready is True
        assert readiness.verified_evidence_ids == [evidence.evidence_id]
        assert readiness.decision_id == decision.decision_id

    def test_blocked_authoritative_source_not_ready(self, isolated_stack):
        readiness = svc.evaluate_closure_readiness("RES-TEST-BLOCKED")
        assert readiness.is_ready is False
        assert any("blocked_authoritative_source" in r for r in readiness.blocking_reasons)

    def test_corrupted_evidence_blocks_readiness(self, isolated_stack):
        _decide_to_terminal()
        _add_verified_evidence()
        payload = json.loads(isolated_stack["evidence_path"].read_text(encoding="utf-8"))
        payload["evidence"][0]["title"] = "Tampered by hand"
        isolated_stack["evidence_path"].write_text(json.dumps(payload), encoding="utf-8")
        we_store.reload()
        readiness = svc.evaluate_closure_readiness("RES-TEST-OPEN")
        assert readiness.is_ready is False
        assert len(readiness.corrupted_evidence_ids) == 1
        assert any("integrity verification" in r for r in readiness.blocking_reasons)

    def test_resolution_not_found(self, isolated_stack):
        with pytest.raises(svc.ResolutionNotFoundError):
            svc.evaluate_closure_readiness("RES-DOES-NOT-EXIST")


# =======================================================================
# Service: close_resolution / get_resolution_closure
# =======================================================================


class TestCloseResolution:
    def test_successful_close_carries_correct_evidence_and_decision(self, isolated_stack):
        decision = _decide_to_terminal()
        verified = _add_verified_evidence()
        _add_verified_evidence(verification_status=we.EvidenceVerificationStatus.UNVERIFIED)
        closure = svc.close_resolution(
            resolution_id="RES-TEST-OPEN", closure_rationale="Closing.", closed_by="ilhan",
        )
        assert closure.evidence_ids == [verified.evidence_id]
        assert closure.decision_id == decision.decision_id
        assert closure.closure_status == "closed"

    def test_second_close_attempt_rejected(self, isolated_stack):
        _decide_to_terminal()
        _add_verified_evidence()
        svc.close_resolution(resolution_id="RES-TEST-OPEN", closure_rationale="r", closed_by="ilhan")
        with pytest.raises(svc.DuplicateClosureError):
            svc.close_resolution(resolution_id="RES-TEST-OPEN", closure_rationale="r2", closed_by="ilhan")

    def test_close_not_ready_raises(self, isolated_stack):
        with pytest.raises(svc.ClosureNotReadyError):
            svc.close_resolution(resolution_id="RES-TEST-OPEN", closure_rationale="r", closed_by="ilhan")

    def test_blocked_resolution_close_rejected(self, isolated_stack):
        with pytest.raises(svc.BlockedRecordDecisionError):
            svc.close_resolution(resolution_id="RES-TEST-BLOCKED", closure_rationale="r", closed_by="ilhan")

    def test_close_resolution_not_found(self, isolated_stack):
        with pytest.raises(svc.ResolutionNotFoundError):
            svc.close_resolution(resolution_id="RES-DOES-NOT-EXIST", closure_rationale="r", closed_by="ilhan")

    def test_close_rejects_ready_result_with_missing_decision_id(self, isolated_stack, monkeypatch):
        """Defense-in-depth guard: if evaluate_closure_readiness() ever
        reports is_ready=True with decision_id=None (structurally
        unreachable through the real computation, but not assumed),
        close_resolution() must raise ClosureNotReadyError rather than
        proceed to build a closure with a None decision_id."""
        crafted_readiness = svc.ClosureReadiness(
            resolution_id="RES-TEST-OPEN",
            effective_status=wr.WasherResolutionStatus.RESOLVED,
            is_ready=True,
            decision_id=None,
            verified_evidence_ids=["WRE-fake-0001"],
        )
        monkeypatch.setattr(svc, "evaluate_closure_readiness", lambda resolution_id: crafted_readiness)
        with pytest.raises(svc.ClosureNotReadyError):
            svc.close_resolution(resolution_id="RES-TEST-OPEN", closure_rationale="r", closed_by="ilhan")
        assert wc_store.get_closure_for_resolution("RES-TEST-OPEN") is None

    def test_close_does_not_mutate_evidence_or_decision_ledgers(self, isolated_stack):
        _decide_to_terminal()
        _add_verified_evidence()
        decisions_before = json.loads(isolated_stack["decisions_path"].read_text(encoding="utf-8"))
        evidence_before = json.loads(isolated_stack["evidence_path"].read_text(encoding="utf-8"))
        svc.close_resolution(resolution_id="RES-TEST-OPEN", closure_rationale="r", closed_by="ilhan")
        decisions_after = json.loads(isolated_stack["decisions_path"].read_text(encoding="utf-8"))
        evidence_after = json.loads(isolated_stack["evidence_path"].read_text(encoding="utf-8"))
        assert decisions_before == decisions_after
        assert evidence_before == evidence_after

    def test_concurrent_close_attempts_only_one_succeeds(self, isolated_stack):
        _decide_to_terminal()
        _add_verified_evidence()
        results, errors = [], []

        def _attempt():
            try:
                svc.close_resolution(resolution_id="RES-TEST-OPEN", closure_rationale="r", closed_by="ilhan")
                results.append("ok")
            except (svc.DuplicateClosureError, svc.ClosureNotReadyError):
                errors.append("blocked")

        threads = [threading.Thread(target=_attempt) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 1
        assert len(errors) == 4
        assert len(wc_store.list_all_closures()) == 1

    def test_get_resolution_closure_none_when_absent(self, isolated_stack):
        assert svc.get_resolution_closure("RES-TEST-OPEN") is None

    def test_get_resolution_closure_returns_closure(self, isolated_stack):
        _decide_to_terminal()
        _add_verified_evidence()
        closure = svc.close_resolution(resolution_id="RES-TEST-OPEN", closure_rationale="r", closed_by="ilhan")
        fetched = svc.get_resolution_closure("RES-TEST-OPEN")
        assert fetched.closure_id == closure.closure_id

    def test_get_resolution_closure_not_found(self, isolated_stack):
        with pytest.raises(svc.ResolutionNotFoundError):
            svc.get_resolution_closure("RES-DOES-NOT-EXIST")


# =======================================================================
# No reopen / update / delete public surface anywhere in Stage 3
# =======================================================================


class TestNoReopenSurface:
    def test_service_has_no_reopen_function(self):
        for name in dir(svc):
            assert "reopen" not in name.lower()

    def test_closure_module_has_no_reopen_function(self):
        for name in dir(wc):
            assert "reopen" not in name.lower()

    def test_closure_store_has_no_reopen_function(self):
        for name in dir(wc_store):
            assert "reopen" not in name.lower()
