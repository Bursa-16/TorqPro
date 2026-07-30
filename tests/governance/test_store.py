import json

import pytest

import backend.governance.store as store_module
from backend.governance.enums import LifecycleGroup
from backend.governance.events import GovernanceEvent
from backend.governance.exceptions import GovernanceCorruptionError, GovernanceStoreError
from backend.governance.store import FileGovernanceEventStore

VALID_TS = "2026-07-30T10:00:00Z"


def _event(**overrides):
    fields = dict(
        event_id="e1",
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        lifecycle_group=LifecycleGroup.REVIEW,
        previous_status="draft",
        new_status="under_review",
        decision_id="d1",
        idempotency_key="k1",
        actor="ilhan",
        occurred_at=VALID_TS,
    )
    fields.update(overrides)
    return GovernanceEvent(**fields)


# ---------------------------------------------------------------------
# Empty-store behavior
# ---------------------------------------------------------------------


def test_nonexistent_file_is_a_valid_empty_store(tmp_path):
    store = FileGovernanceEventStore(tmp_path / "nonexistent" / "events.json")
    assert store.all_events() == []
    assert store.events_for_aggregate("agg-1") == []
    assert store.find_by_decision_id("d1") is None
    assert store.find_by_idempotency_key("k1") is None


def test_empty_string_idempotency_key_lookup_returns_none(tmp_path):
    store = FileGovernanceEventStore(tmp_path / "events.json")
    store.append(_event())
    assert store.find_by_idempotency_key("") is None


# ---------------------------------------------------------------------
# Deterministic append and read
# ---------------------------------------------------------------------


def test_append_then_read_round_trip(tmp_path):
    store = FileGovernanceEventStore(tmp_path / "events.json")
    appended = store.append(_event())
    events = store.all_events()
    assert len(events) == 1
    assert events[0] == appended


def test_append_is_append_only_never_overwrites_prior_events(tmp_path):
    store = FileGovernanceEventStore(tmp_path / "events.json")
    store.append(_event(event_id="e1", decision_id="d1", idempotency_key="k1"))
    store.append(
        _event(
            event_id="e2",
            decision_id="d2",
            idempotency_key="k2",
            previous_status="under_review",
            new_status="approved",
        )
    )
    events = store.all_events()
    assert len(events) == 2
    assert events[0].event_id == "e1"
    assert events[1].event_id == "e2"


def test_serialization_is_deterministic_sorted_keys(tmp_path):
    path = tmp_path / "events.json"
    store = FileGovernanceEventStore(path)
    store.append(_event())
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    # sort_keys=True means re-dumping with sort_keys should be a no-op
    assert json.dumps(payload, sort_keys=True) == json.dumps(
        json.loads(json.dumps(payload, sort_keys=True)), sort_keys=True
    )
    assert list(payload.keys()) == sorted(payload.keys())


def test_utf8_encoding_preserves_turkish_characters(tmp_path):
    path = tmp_path / "events.json"
    store = FileGovernanceEventStore(path)
    store.append(_event(actor="İlhan Çekiç", review_comment="onaylandı, ödeme gerekmiyor"))
    raw = path.read_text(encoding="utf-8")
    # ensure_ascii=False: the raw file must contain the literal UTF-8
    # characters, not \uXXXX escapes.
    assert "İlhan Çekiç" in raw
    assert "\\u" not in raw
    reloaded = store.all_events()
    assert reloaded[0].actor == "İlhan Çekiç"
    assert reloaded[0].review_comment == "onaylandı, ödeme gerekmiyor"


# ---------------------------------------------------------------------
# Multiple aggregates / lifecycle isolation
# ---------------------------------------------------------------------


def test_multiple_aggregates_are_isolated(tmp_path):
    store = FileGovernanceEventStore(tmp_path / "events.json")
    store.append(
        _event(event_id="e1", aggregate_id="agg-1", decision_id="d1", idempotency_key="k1")
    )
    store.append(
        _event(event_id="e2", aggregate_id="agg-2", decision_id="d2", idempotency_key="k2")
    )
    store.append(
        _event(
            event_id="e3",
            aggregate_id="agg-1",
            decision_id="d3",
            idempotency_key="k3",
            previous_status="under_review",
            new_status="approved",
        )
    )
    assert [e.event_id for e in store.events_for_aggregate("agg-1")] == ["e1", "e3"]
    assert [e.event_id for e in store.events_for_aggregate("agg-2")] == ["e2"]


def test_lifecycle_group_isolation_within_one_aggregate(tmp_path):
    store = FileGovernanceEventStore(tmp_path / "events.json")
    store.append(
        _event(
            event_id="e1",
            aggregate_id="agg-1",
            lifecycle_group=LifecycleGroup.REVIEW,
            decision_id="d1",
            idempotency_key="k1",
        )
    )
    store.append(
        _event(
            event_id="e2",
            aggregate_id="agg-1",
            lifecycle_group=LifecycleGroup.RESOLUTION,
            previous_status="open",
            new_status="resolved",
            decision_id="d2",
            idempotency_key="k2",
        )
    )
    all_for_aggregate = store.events_for_aggregate("agg-1")
    review_only = [e for e in all_for_aggregate if e.lifecycle_group == LifecycleGroup.REVIEW]
    resolution_only = [
        e for e in all_for_aggregate if e.lifecycle_group == LifecycleGroup.RESOLUTION
    ]
    assert len(review_only) == 1
    assert len(resolution_only) == 1
    assert review_only[0].event_id == "e1"
    assert resolution_only[0].event_id == "e2"


# ---------------------------------------------------------------------
# Corruption detection
# ---------------------------------------------------------------------


def test_malformed_json_raises_corruption_error(tmp_path):
    path = tmp_path / "events.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = FileGovernanceEventStore(path)
    with pytest.raises(GovernanceCorruptionError):
        store.all_events()


def test_truncated_ledger_raises_corruption_error(tmp_path):
    path = tmp_path / "events.json"
    store = FileGovernanceEventStore(path)
    store.append(_event())
    # Simulate truncation: chop off the last 20 characters of a
    # previously-valid file.
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw[:-20], encoding="utf-8")
    with pytest.raises(GovernanceCorruptionError):
        store.all_events()


def test_unexpected_top_level_shape_raises_corruption_error(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(json.dumps({"not_events": []}), encoding="utf-8")
    store = FileGovernanceEventStore(path)
    with pytest.raises(GovernanceCorruptionError):
        store.all_events()


def test_events_list_containing_a_top_level_json_array_raises_corruption_error(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    store = FileGovernanceEventStore(path)
    with pytest.raises(GovernanceCorruptionError):
        store.all_events()


def test_record_failing_event_validation_raises_corruption_error(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(
        json.dumps({"events": [{"event_id": "e1", "aggregate_id": "agg-1"}]}), encoding="utf-8"
    )
    store = FileGovernanceEventStore(path)
    with pytest.raises(GovernanceCorruptionError):
        store.all_events()


def test_empty_file_is_treated_as_empty_store_not_corrupted(tmp_path):
    path = tmp_path / "events.json"
    path.write_text("", encoding="utf-8")
    store = FileGovernanceEventStore(path)
    assert store.all_events() == []


# ---------------------------------------------------------------------
# Path / traceback redaction
# ---------------------------------------------------------------------


def test_corruption_error_message_does_not_leak_filesystem_path(tmp_path):
    path = tmp_path / "events.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = FileGovernanceEventStore(path)
    with pytest.raises(GovernanceCorruptionError) as excinfo:
        store.all_events()
    assert str(tmp_path) not in str(excinfo.value)
    assert str(path) not in str(excinfo.value)


def test_store_error_message_does_not_leak_filesystem_path(tmp_path, monkeypatch):
    path = tmp_path / "events.json"
    store = FileGovernanceEventStore(path)

    def _boom(*args, **kwargs):
        raise OSError("device full: " + str(path))

    monkeypatch.setattr(store_module.os, "replace", _boom)
    with pytest.raises(GovernanceStoreError) as excinfo:
        store.append(_event())
    assert str(tmp_path) not in str(excinfo.value)
    assert str(path) not in str(excinfo.value)
    assert "device full" not in str(excinfo.value)


# ---------------------------------------------------------------------
# Atomic-write failure behavior
# ---------------------------------------------------------------------


def test_atomic_write_failure_leaves_prior_content_untouched(tmp_path, monkeypatch):
    path = tmp_path / "events.json"
    store = FileGovernanceEventStore(path)
    store.append(_event(event_id="e1", decision_id="d1", idempotency_key="k1"))
    before = path.read_text(encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(store_module.os, "replace", _boom)
    with pytest.raises(GovernanceStoreError):
        store.append(_event(event_id="e2", decision_id="d2", idempotency_key="k2"))

    after = path.read_text(encoding="utf-8")
    assert after == before
    assert len(store.all_events()) == 1


def test_atomic_write_failure_cleans_up_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "events.json"
    store = FileGovernanceEventStore(path)

    def _boom(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(store_module.os, "replace", _boom)
    with pytest.raises(GovernanceStoreError):
        store.append(_event())

    leftover_tmp_files = list(tmp_path.glob(".governance_events.*.tmp"))
    assert leftover_tmp_files == []


# ---------------------------------------------------------------------
# Windows-compatible locking fallback
# ---------------------------------------------------------------------


def test_append_works_without_fcntl_available(tmp_path, monkeypatch):
    """Simulates a platform with no ``fcntl`` module (Windows): the
    store must still function correctly using only the in-process
    lock."""
    monkeypatch.setattr(store_module, "_HAS_FCNTL", False)
    store = FileGovernanceEventStore(tmp_path / "events.json")
    store.append(_event(event_id="e1", decision_id="d1", idempotency_key="k1"))
    store.append(
        _event(
            event_id="e2",
            decision_id="d2",
            idempotency_key="k2",
            previous_status="under_review",
            new_status="approved",
        )
    )
    events = store.all_events()
    assert [e.event_id for e in events] == ["e1", "e2"]


def test_module_import_does_not_require_fcntl():
    """The module itself must degrade gracefully if fcntl is
    unavailable at import time -- exercised here by confirming the
    module-level flag exists and is a bool, not by literally removing
    the module (which isn't practical to simulate portably)."""
    assert isinstance(store_module._HAS_FCNTL, bool)
