import pytest

from backend.production_validation import service as svc
from backend.production_validation.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationDataError,
)
from backend.production_validation.schemas import ValidationStudyCreate
from tests.production_validation.conftest import (
    admin_headers, make_calculation, make_calculation_revision, make_full_context,
    make_joint, make_joint_revision, make_project,
)


def _actor():
    return {"id": 1, "role": "admin"}


def test_create_study_via_service_sets_specification_id():
    ctx = make_full_context()
    study = svc.create_study(ValidationStudyCreate(**ctx), _actor())
    assert study["specification_id"] is not None
    assert study["status"] == "draft"


def test_create_study_rejects_unknown_project():
    ctx = make_full_context()
    ctx["project_id"] = 999999999
    with pytest.raises(NotFoundError):
        svc.create_study(ValidationStudyCreate(**ctx), _actor())


def test_create_study_rejects_joint_from_other_project():
    ctx = make_full_context()
    other_project_id = make_project("Other Project")
    other_joint = make_joint(other_project_id)
    other_rev = make_joint_revision(other_joint["id"])
    ctx["joint_id"] = other_joint["id"]
    ctx["joint_revision_id"] = other_rev["id"]
    with pytest.raises(ValidationDataError):
        svc.create_study(ValidationStudyCreate(**ctx), _actor())


def test_create_study_rejects_revision_from_other_joint():
    ctx = make_full_context()
    other_joint = make_joint(ctx["project_id"])
    other_rev = make_joint_revision(other_joint["id"])
    ctx["joint_revision_id"] = other_rev["id"]
    with pytest.raises(ValidationDataError):
        svc.create_study(ValidationStudyCreate(**ctx), _actor())


def test_create_study_rejects_calculation_revision_from_other_calculation():
    ctx = make_full_context()
    other_calc_id = make_calculation(project_id=ctx["project_id"])
    other_rev_id = make_calculation_revision(other_calc_id)
    ctx["calculation_revision_id"] = other_rev_id
    with pytest.raises(ValidationDataError):
        svc.create_study(ValidationStudyCreate(**ctx), _actor())


def test_create_study_duplicate_study_code_conflict():
    ctx = make_full_context(study_code="VS-SERVICE-DUP")
    svc.create_study(ValidationStudyCreate(**ctx), _actor())
    ctx2 = make_full_context(study_code="VS-SERVICE-DUP")
    with pytest.raises(ConflictError):
        svc.create_study(ValidationStudyCreate(**ctx2), _actor())


def test_specification_snapshot_immutable_after_later_changes():
    ctx = make_full_context()
    study = svc.create_study(ValidationStudyCreate(**ctx), _actor())
    from backend.app import conn
    with conn() as c:
        snap = c.execute(
            "SELECT * FROM specification_snapshots WHERE id=?", (study["specification_id"],)
        ).fetchone()
    assert snap["lower_spec_limit"] == ctx["lower_spec_limit"]
    assert snap["calculation_snapshot_id"] == ctx["calculation_revision_id"]
    # Changing the underlying calculation later must not retroactively change the snapshot.
    from tests.production_validation.conftest import client
    client.post(
        "/api/calculations", headers=admin_headers(),
        json={"thread": "M12", "torque_nm": 99},
    )
    with conn() as c:
        snap_again = c.execute(
            "SELECT * FROM specification_snapshots WHERE id=?", (study["specification_id"],)
        ).fetchone()
    assert snap_again["lower_spec_limit"] == snap["lower_spec_limit"]
