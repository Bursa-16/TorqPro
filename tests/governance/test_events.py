import pytest
from pydantic import ValidationError

from backend.governance.enums import LifecycleGroup
from backend.governance.events import GovernanceEvent

VALID_TS = "2026-07-30T10:00:00Z"


def _minimal_event(**overrides):
    fields = dict(
        event_id="e1",
        aggregate_id="agg-1",
        aggregate_type="calc_revision",
        lifecycle_group=LifecycleGroup.REVIEW,
        previous_status="draft",
        new_status="under_review",
        decision_id="d1",
        idempotency_key="k1",
        occurred_at=VALID_TS,
    )
    fields.update(overrides)
    return GovernanceEvent(**fields)


def test_minimal_event_round_trip():
    event = _minimal_event()
    assert event.aggregate_id == "agg-1"
    assert event.lifecycle_group == LifecycleGroup.REVIEW
    assert event.metadata == {}
    assert event.actor is None


def test_event_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _minimal_event(washer_geometry_override="not allowed")


def test_event_rejects_malformed_occurred_at():
    with pytest.raises(ValidationError):
        _minimal_event(occurred_at="2026-07-30 10:00:00")


def test_event_rejects_non_utc_offset():
    with pytest.raises(ValidationError):
        _minimal_event(occurred_at="2026-07-30T10:00:00+03:00")


def test_event_accepts_fractional_seconds_utc():
    event = _minimal_event(occurred_at="2026-07-30T10:00:00.123456Z")
    assert event.occurred_at == "2026-07-30T10:00:00.123456Z"


def test_event_metadata_defaults_to_empty_dict_and_is_independent_per_instance():
    e1 = _minimal_event()
    e2 = _minimal_event()
    e1.metadata["x"] = 1
    assert e2.metadata == {}


def test_event_carries_optional_lineage_fields():
    event = _minimal_event(
        lifecycle_group=LifecycleGroup.PUBLICATION,
        previous_status="active",
        new_status="superseded",
        revision_no=2,
        supersedes_id="agg-0",
        superseded_by_id="agg-2",
    )
    assert event.revision_no == 2
    assert event.supersedes_id == "agg-0"
    assert event.superseded_by_id == "agg-2"


def test_event_requires_decision_id_and_idempotency_key():
    with pytest.raises(ValidationError):
        GovernanceEvent(
            event_id="e1",
            aggregate_id="agg-1",
            aggregate_type="calc_revision",
            lifecycle_group=LifecycleGroup.REVIEW,
            previous_status="draft",
            new_status="under_review",
            occurred_at=VALID_TS,
        )


def test_event_lifecycle_group_rejects_unsupported_value():
    with pytest.raises(ValidationError):
        _minimal_event(lifecycle_group="not_a_real_lifecycle_group")
