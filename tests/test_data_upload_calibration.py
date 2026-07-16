
import os, json
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)

def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}

def test_upload_draft_and_approval_policy():
    h=auth()
    payload={"dataset":"proof_load","filename":"proof.json","content":json.dumps([{"thread":"M10","proof_load_n":1000}]),
             "source_title":"Test source","source_page":"p1","confidence":3,"note":"test"}
    r=client.post("/api/admin/data-packages",json=payload,headers=h)
    assert r.status_code==200,r.text
    pid=r.json()["id"]
    r=client.patch(f"/api/admin/data-packages/{pid}/status",json={"status":"approved"},headers=h)
    assert r.status_code==400

def test_calibration_case():
    h=auth()
    r=client.post("/api/calibration/cases",json={"thread":"M10","program_value":69.3,"reference_value":70.0,"tolerance_pct":5.0},headers=h)
    assert r.status_code==200,r.text
    d=r.json()
    assert d["passed"]==1
    assert d["error_pct"]<5
