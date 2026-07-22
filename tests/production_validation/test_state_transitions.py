import pytest

from backend.production_validation import service as svc
from backend.production_validation.exceptions import StateTransitionError, ValidationDataError
from tests.production_validation.conftest import (
    admin_headers, client, create_dataset, create_study,
)

ACTOR = {"id": 1, "role": "admin"}


def _add_valid_record(dataset_id, sample_id="S-1"):
    return svc.create_record(
        dataset_id,
        _record_payload(sample_id),
        ACTOR,
    )


def _record_payload(sample_id):
    from backend.production_validation.schemas import MeasurementRecordCreate
    return MeasurementRecordCreate(sample_id=sample_id, measured_value=45.0)


def test_draft_moves_to_data_collection_on_first_dataset():
    study = create_study()
    assert study["status"] == "draft"
    create_dataset(study["id"])
    reloaded = svc.get_study(study["id"])
    assert reloaded["status"] == "data_collection"


def test_cannot_complete_draft_without_data_collection():
    study = create_study()
    with pytest.raises(StateTransitionError):
        svc.complete_study(study["id"], ACTOR)


def test_complete_requires_valid_measurement():
    study = create_study()
    dataset = create_dataset(study["id"])
    with pytest.raises(ValidationDataError):
        svc.complete_study(study["id"], ACTOR)
    _add_valid_record(dataset["id"])
    completed = svc.complete_study(study["id"], ACTOR)
    assert completed["status"] == "completed"


def test_full_forward_path_draft_to_approved():
    study = create_study()
    dataset = create_dataset(study["id"])
    _add_valid_record(dataset["id"])
    svc.complete_study(study["id"], ACTOR)
    svc.submit_study(study["id"], ACTOR)
    approver = {"id": 2, "role": "admin"}
    approved = svc.approve_study(study["id"], approver)
    assert approved["status"] == "approved"
    assert approved["approved_by"] == 2
    assert approved["approved_at"] is not None


def test_cannot_skip_states():
    study = create_study()
    with pytest.raises(StateTransitionError):
        svc.submit_study(study["id"], ACTOR)
    with pytest.raises(StateTransitionError):
        svc.approve_study(study["id"], ACTOR)


def test_under_review_can_be_rejected_then_returns_to_data_collection():
    study = create_study()
    dataset = create_dataset(study["id"])
    _add_valid_record(dataset["id"])
    svc.complete_study(study["id"], ACTOR)
    svc.submit_study(study["id"], ACTOR)
    rejected = svc.reject_study(study["id"], ACTOR)
    assert rejected["status"] == "rejected"
    resumed = _resume_after_rejection(study["id"])
    assert resumed["status"] == "data_collection"


def _resume_after_rejection(study_id):
    # rejected -> data_collection is the only forward path back into editing.
    from backend.app import conn, now_iso
    with conn() as c:
        c.execute(
            "UPDATE validation_studies SET status='data_collection',updated_at=? WHERE id=?",
            (now_iso(), study_id),
        )
        c.commit()
    return svc.get_study(study_id)


def test_approved_study_is_immutable_end_state():
    study = create_study()
    dataset = create_dataset(study["id"])
    _add_valid_record(dataset["id"])
    svc.complete_study(study["id"], ACTOR)
    svc.submit_study(study["id"], ACTOR)
    approver = {"id": 2, "role": "admin"}
    svc.approve_study(study["id"], approver)
    with pytest.raises(StateTransitionError):
        svc.submit_study(study["id"], ACTOR)
    with pytest.raises(StateTransitionError):
        svc.complete_study(study["id"], ACTOR)
    from backend.production_validation.exceptions import LockedError
    with pytest.raises(LockedError):
        from backend.production_validation.schemas import ValidationStudyPatch
        svc.patch_study(study["id"], ValidationStudyPatch(notes="late edit"), ACTOR)
    with pytest.raises(LockedError):
        create_dataset_direct(study["id"])


def create_dataset_direct(study_id):
    from backend.production_validation.schemas import MeasurementDatasetCreate
    payload = MeasurementDatasetCreate(
        dataset_code="DS-LATE", name="Late", characteristic_name="torque",
        characteristic_type="tightening_torque", unit="Nm",
        lower_spec_limit=40.0, upper_spec_limit=50.0,
    )
    return svc.create_dataset(study_id, payload, ACTOR)


def test_archive_reachable_from_multiple_states():
    study = create_study()
    archived = svc.archive_study(study["id"], ACTOR)
    assert archived["status"] == "archived"
    with pytest.raises(StateTransitionError):
        svc.archive_study(study["id"], ACTOR)


def test_approver_cannot_be_the_studys_own_creator():
    study = create_study()
    dataset = create_dataset(study["id"])
    _add_valid_record(dataset["id"])
    svc.complete_study(study["id"], ACTOR)
    svc.submit_study(study["id"], ACTOR)
    with pytest.raises(ValidationDataError):
        svc.approve_study(study["id"], ACTOR)


def test_api_rejects_invalid_transition_with_400():
    study = create_study()
    r = client.post(f"/api/validation-studies/{study['id']}/submit", headers=admin_headers())
    assert r.status_code == 400
