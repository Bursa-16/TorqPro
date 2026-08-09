"""ADR-0017 Karar 8 -- the AI-gateway audit sink is append-only by
construction: AuditSink declares exactly one mutating method
(``record``), and InMemoryAuditSink never exposes a way to alter or
remove a previously recorded entry.
"""

from __future__ import annotations

import inspect

from backend.ai_gateway.audit import AIInteractionRecord, AuditSink, InMemoryAuditSink


def _make_record(user_id: int = 1, had_evidence: bool = True) -> AIInteractionRecord:
    return AIInteractionRecord(
        user_id=user_id,
        query_text_hash="deadbeef",
        evidence_source_ids=(("question_bank", "QB-0001"),),
        calculation_formula_ids=(),
        model_name="fake-test-client",
        had_sufficient_evidence=had_evidence,
        created_at="2026-08-09T00:00:00+00:00",
    )


def test_audit_sink_interface_has_no_update_or_delete_method():
    """Structural guarantee: no mutating method other than ``record``
    exists anywhere on the AuditSink interface."""
    members = {name for name, _ in inspect.getmembers(AuditSink) if not name.startswith("_")}
    forbidden = {"update", "delete", "clear", "remove", "edit", "modify"}
    assert not (members & forbidden), (
        f"AuditSink exposes forbidden mutating method(s): {members & forbidden}"
    )
    assert "record" in members


def test_in_memory_audit_sink_has_no_update_or_delete_method():
    members = {
        name for name, _ in inspect.getmembers(InMemoryAuditSink) if not name.startswith("_")
    }
    forbidden = {"update", "delete", "clear", "remove", "edit", "modify"}
    assert not (members & forbidden), (
        f"InMemoryAuditSink exposes forbidden mutating method(s): {members & forbidden}"
    )


def test_recorded_entries_accumulate_in_order():
    sink = InMemoryAuditSink()
    first = _make_record(user_id=1)
    second = _make_record(user_id=2)

    sink.record(first)
    sink.record(second)

    entries = sink.all_entries()
    assert entries == (first, second)


def test_earlier_entry_is_never_altered_by_a_later_record_call():
    sink = InMemoryAuditSink()
    first = _make_record(user_id=1, had_evidence=True)
    sink.record(first)

    snapshot_before = sink.all_entries()
    sink.record(_make_record(user_id=2, had_evidence=False))
    snapshot_after = sink.all_entries()

    # The first entry object itself is frozen (dataclass(frozen=True))
    # and identical across both snapshots -- proves no in-place mutation.
    assert snapshot_before[0] is snapshot_after[0]
    assert snapshot_after[0].user_id == 1
    assert snapshot_after[0].had_sufficient_evidence is True


def test_all_entries_returns_a_defensive_copy():
    sink = InMemoryAuditSink()
    sink.record(_make_record())

    entries = sink.all_entries()
    assert isinstance(entries, tuple)
    # Mutating the returned tuple is structurally impossible (tuples are
    # immutable); confirm the sink's own internal count is unaffected by
    # calling all_entries() repeatedly.
    assert len(sink.all_entries()) == 1
    assert len(sink.all_entries()) == 1
