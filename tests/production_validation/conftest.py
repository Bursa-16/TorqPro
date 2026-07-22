import os
os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

import pytest
from fastapi.testclient import TestClient

from backend.app import app, conn, now_iso
from backend.joints import service as joints_svc

client = TestClient(app)


def token(u="Protype Lab", p="A1234"):
    r = client.post("/api/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def hdr(t):
    return {"Authorization": "Bearer " + t}


def admin_headers():
    return hdr(token())


def make_second_reviewer(username="pv_reviewer"):
    ah = admin_headers()
    client.post("/api/admin/users", headers=ah, json={
        "username": username, "display_name": "PV Reviewer",
        "password": "reviewerpass1", "role": "engineer",
    })
    return hdr(token(username, "reviewerpass1"))


def make_project(name="PV Project", code=None):
    with conn() as c:
        c.execute(
            "INSERT INTO projects(name,project_code,status,created_at) VALUES(?,?,?,?)",
            (name, code, "open", now_iso()),
        )
        c.commit()
        return c.execute("SELECT id FROM projects WHERE id=last_insert_rowid()").fetchone()["id"]


def make_calculation(project_id=None, torque_nm=45.0):
    ah = admin_headers()
    payload = {"thread": "M10", "torque_nm": torque_nm, "standard": "VDI2230"}
    if project_id is not None:
        payload["project_id"] = project_id
    r = client.post("/api/calculations", headers=ah, json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def make_calculation_revision(calculation_id):
    ah = admin_headers()
    r = client.post(
        "/api/revisions", headers=ah,
        json={"calculation_id": calculation_id, "note": "pv fixture"},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def make_joint(project_id, joint_code=None, created_by=None):
    import uuid
    code = joint_code or f"J-{uuid.uuid4().hex[:8]}"
    return joints_svc.create_joint(project_id, code, "PV Joint", None, created_by)


def make_joint_revision(joint_id, created_by=None):
    return joints_svc.create_joint_revision(joint_id, {"thread": "M10"}, "pv fixture", created_by)


def make_full_context(study_code=None):
    """Create project + joint + joint_revision + calculation + calculation_revision,
    ready to be referenced by a ValidationStudy."""
    import uuid
    project_id = make_project()
    joint = make_joint(project_id)
    joint_rev = make_joint_revision(joint["id"])
    calc_id = make_calculation(project_id=project_id)
    calc_rev_id = make_calculation_revision(calc_id)
    return {
        "study_code": study_code or f"VS-{uuid.uuid4().hex[:8]}",
        "name": "PV Study",
        "study_type": "torque_validation",
        "project_id": project_id,
        "joint_id": joint["id"],
        "joint_revision_id": joint_rev["id"],
        "calculation_id": calc_id,
        "calculation_revision_id": calc_rev_id,
        "characteristic_name": "tightening_torque",
        "unit": "Nm",
        "lower_spec_limit": 40.0,
        "upper_spec_limit": 50.0,
        "target_value": 45.0,
    }


def create_study(headers=None, **overrides):
    payload = make_full_context()
    payload.update(overrides)
    r = client.post("/api/validation-studies", headers=headers or admin_headers(), json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def create_dataset(study_id, headers=None, **overrides):
    import uuid
    payload = {
        "dataset_code": f"DS-{uuid.uuid4().hex[:8]}",
        "name": "Torque Dataset",
        "characteristic_name": "tightening_torque",
        "characteristic_type": "tightening_torque",
        "unit": "Nm",
        "lower_spec_limit": 40.0,
        "upper_spec_limit": 50.0,
        "target_value": 45.0,
    }
    payload.update(overrides)
    r = client.post(
        f"/api/validation-studies/{study_id}/datasets",
        headers=headers or admin_headers(), json=payload,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def api():
    return client
