from tests.production_validation.conftest import (
    admin_headers, client, create_dataset, create_study, make_full_context,
    make_second_reviewer,
)


def test_create_and_get_study():
    study = create_study()
    r = client.get(f"/api/validation-studies/{study['id']}", headers=admin_headers())
    assert r.status_code == 200
    assert r.json()["study_code"] == study["study_code"]
    assert r.json()["specification_id"] is not None


def test_study_code_must_be_unique():
    ctx = make_full_context(study_code="VS-DUPLICATE-API")
    r1 = client.post("/api/validation-studies", headers=admin_headers(), json=ctx)
    assert r1.status_code == 200
    r2 = client.post("/api/validation-studies", headers=admin_headers(), json=ctx)
    assert r2.status_code == 409


def test_list_validation_studies_filters_by_project():
    study = create_study()
    r = client.get(
        "/api/validation-studies", headers=admin_headers(),
        params={"project_id": study["project_id"]},
    )
    assert r.status_code == 200
    assert any(s["id"] == study["id"] for s in r.json())


def test_create_dataset_and_list():
    study = create_study()
    dataset = create_dataset(study["id"])
    r = client.get(
        f"/api/validation-studies/{study['id']}/datasets", headers=admin_headers()
    )
    assert r.status_code == 200
    assert any(d["id"] == dataset["id"] for d in r.json())
    reloaded_study = client.get(
        f"/api/validation-studies/{study['id']}", headers=admin_headers()
    ).json()
    assert reloaded_study["status"] == "data_collection"


def test_invalid_spec_limits_rejected():
    study = create_study()
    r = client.post(
        f"/api/validation-studies/{study['id']}/datasets",
        headers=admin_headers(),
        json={
            "dataset_code": "DS-BADLIMITS", "name": "Bad", "characteristic_name": "torque",
            "characteristic_type": "tightening_torque", "unit": "Nm",
            "lower_spec_limit": 50.0, "upper_spec_limit": 40.0,
        },
    )
    assert r.status_code == 422


def test_create_measurement_record_and_list():
    study = create_study()
    dataset = create_dataset(study["id"])
    r = client.post(
        f"/api/measurement-datasets/{dataset['id']}/records",
        headers=admin_headers(),
        json={"sample_id": "S-1", "measured_value": 45.2},
    )
    assert r.status_code == 200
    assert r.json()["sequence_number"] == 1
    r2 = client.get(f"/api/measurement-datasets/{dataset['id']}/records", headers=admin_headers())
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_infinity_rejected():
    study = create_study()
    dataset = create_dataset(study["id"])
    body = '{"sample_id":"S-inf","measured_value":Infinity}'
    r = client.post(
        f"/api/measurement-datasets/{dataset['id']}/records",
        headers={**admin_headers(), "Content-Type": "application/json"},
        content=body,
    )
    assert r.status_code in (400, 422)


def test_dataset_lock_blocks_new_records():
    study = create_study()
    dataset = create_dataset(study["id"])
    r = client.post(f"/api/measurement-datasets/{dataset['id']}/lock", headers=admin_headers())
    assert r.status_code == 200
    r2 = client.post(
        f"/api/measurement-datasets/{dataset['id']}/records",
        headers=admin_headers(),
        json={"sample_id": "S-2", "measured_value": 44.0},
    )
    assert r2.status_code == 400


def test_record_invalidate_requires_reason():
    study = create_study()
    dataset = create_dataset(study["id"])
    rec = client.post(
        f"/api/measurement-datasets/{dataset['id']}/records",
        headers=admin_headers(),
        json={"sample_id": "S-3", "measured_value": 46.0},
    ).json()
    bad = client.post(
        f"/api/measurement-records/{rec['id']}/invalidate",
        headers=admin_headers(), json={"invalid_reason": ""},
    )
    assert bad.status_code == 422
    ok = client.post(
        f"/api/measurement-records/{rec['id']}/invalidate",
        headers=admin_headers(), json={"invalid_reason": "kalibrasyon dışı"},
    )
    assert ok.status_code == 200
    assert ok.json()["is_valid"] == 0


def test_complete_requires_at_least_one_valid_measurement():
    study = create_study()
    dataset = create_dataset(study["id"])
    r = client.post(f"/api/validation-studies/{study['id']}/complete", headers=admin_headers())
    assert r.status_code == 422
    client.post(
        f"/api/measurement-datasets/{dataset['id']}/records",
        headers=admin_headers(),
        json={"sample_id": "S-4", "measured_value": 45.0},
    )
    r2 = client.post(f"/api/validation-studies/{study['id']}/complete", headers=admin_headers())
    assert r2.status_code == 200
    assert r2.json()["status"] == "completed"


def test_full_approval_flow_and_unauthorized_role():
    study = create_study()
    dataset = create_dataset(study["id"])
    client.post(
        f"/api/measurement-datasets/{dataset['id']}/records",
        headers=admin_headers(),
        json={"sample_id": "S-5", "measured_value": 45.0},
    )
    client.post(f"/api/validation-studies/{study['id']}/complete", headers=admin_headers())
    client.post(f"/api/validation-studies/{study['id']}/submit", headers=admin_headers())

    viewer_headers = _make_viewer()
    forbidden = client.post(
        f"/api/validation-studies/{study['id']}/approve", headers=viewer_headers
    )
    assert forbidden.status_code == 422

    approver = make_second_reviewer("pv_approver_flow")
    approved = client.post(f"/api/validation-studies/{study['id']}/approve", headers=approver)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    locked = client.patch(
        f"/api/validation-studies/{study['id']}", headers=admin_headers(), json={"notes": "x"}
    )
    assert locked.status_code == 400


def _make_viewer():
    ah = admin_headers()
    client.post("/api/admin/users", headers=ah, json={
        "username": "pv_viewer_role", "display_name": "PV Viewer",
        "password": "viewerpass1", "role": "viewer",
    })
    from tests.production_validation.conftest import hdr, token
    return hdr(token("pv_viewer_role", "viewerpass1"))
