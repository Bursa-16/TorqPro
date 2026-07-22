from backend.app import conn
from backend.production_validation import service as svc
from backend.production_validation.schemas import MeasurementRecordCreate
from tests.production_validation.conftest import create_dataset, create_study

ACTOR = {"id": 1, "role": "admin"}


def _audit_actions(detail_substr=None, action=None):
    with conn() as c:
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if action:
            sql += " AND action=?"
            params.append(action)
        if detail_substr:
            sql += " AND detail LIKE ?"
            params.append(f"%{detail_substr}%")
        return c.execute(sql, params).fetchall()


def test_study_create_is_audited():
    study = create_study()
    rows = _audit_actions(action="validation_study_create", detail_substr=study["study_code"])
    assert len(rows) == 1


def test_dataset_create_is_audited():
    study = create_study()
    dataset = create_dataset(study["id"])
    rows = _audit_actions(
        action="measurement_dataset_create", detail_substr=dataset["dataset_code"]
    )
    assert len(rows) == 1


def test_csv_import_is_audited():
    study = create_study()
    dataset = create_dataset(study["id"])
    svc.import_csv_records(
        dataset["id"], "trace.csv", "sample_id,measured_value\nS-1,45.0\n", ACTOR
    )
    rows = _audit_actions(action="measurement_csv_import")
    assert any(f"dataset={dataset['id']}" in r["detail"] for r in rows)


def test_record_invalidation_is_audited():
    study = create_study()
    dataset = create_dataset(study["id"])
    rec = svc.create_record(
        dataset["id"], MeasurementRecordCreate(sample_id="S-1", measured_value=45.0), ACTOR
    )
    svc.invalidate_record(rec["id"], "kalibrasyon dışı", ACTOR)
    rows = _audit_actions(action="measurement_record_invalidate", detail_substr=str(rec["id"]))
    assert len(rows) == 1


def test_dataset_lock_is_audited():
    study = create_study()
    dataset = create_dataset(study["id"])
    svc.lock_dataset(dataset["id"], ACTOR)
    rows = _audit_actions(action="measurement_dataset_lock", detail_substr=str(dataset["id"]))
    assert len(rows) == 1


def test_study_complete_submit_approve_reject_archive_are_audited():
    study = create_study()
    dataset = create_dataset(study["id"])
    svc.create_record(
        dataset["id"], MeasurementRecordCreate(sample_id="S-1", measured_value=45.0), ACTOR
    )
    svc.complete_study(study["id"], ACTOR)
    svc.submit_study(study["id"], ACTOR)
    approver = {"id": 2, "role": "admin"}
    svc.approve_study(study["id"], approver)
    actions = ("validation_study_complete", "validation_study_submit", "validation_study_approve")
    for action in actions:
        rows = _audit_actions(action=action, detail_substr=str(study["id"]))
        assert len(rows) == 1, f"missing audit row for {action}"

    study2 = create_study()
    svc.archive_study(study2["id"], ACTOR)
    rows = _audit_actions(action="validation_study_archive", detail_substr=str(study2["id"]))
    assert len(rows) == 1


def test_specification_snapshot_traces_to_calculation_revision():
    study = create_study()
    with conn() as c:
        snap = c.execute(
            "SELECT * FROM specification_snapshots WHERE id=?", (study["specification_id"],)
        ).fetchone()
        study_row = c.execute(
            "SELECT * FROM validation_studies WHERE id=?", (study["id"],)
        ).fetchone()
        joint_rev = c.execute(
            "SELECT * FROM joint_revisions WHERE id=?", (study_row["joint_revision_id"],)
        ).fetchone()
        calc_rev = c.execute(
            "SELECT * FROM calculation_revisions WHERE id=?",
            (study_row["calculation_revision_id"],),
        ).fetchone()
    assert snap["calculation_snapshot_id"] == study_row["calculation_revision_id"]
    assert joint_rev["joint_id"] == study_row["joint_id"]
    assert calc_rev["calculation_id"] == study_row["calculation_id"]
    assert snap["snapshot_hash"]


def test_measurement_record_correction_preserves_history_instead_of_overwrite():
    study = create_study()
    dataset = create_dataset(study["id"])
    original = svc.create_record(
        dataset["id"], MeasurementRecordCreate(sample_id="S-1", measured_value=45.0), ACTOR
    )
    correction = svc.create_record(
        dataset["id"],
        MeasurementRecordCreate(
            sample_id="S-1-corrected", measured_value=45.3, correction_of_id=original["id"]
        ),
        ACTOR,
    )
    records = svc.list_records(dataset["id"])
    by_id = {r["id"]: r for r in records}
    assert by_id[original["id"]]["is_valid"] == 0
    assert "correction" in (by_id[original["id"]]["invalid_reason"] or "")
    assert by_id[correction["id"]]["is_valid"] == 1
    assert by_id[correction["id"]]["correction_of_id"] == original["id"]
