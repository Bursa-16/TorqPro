
import os, json, uuid
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)

def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}

def test_quality_gate_detects_invalid_record():
    h=auth()
    payload={"dataset":"proof_load","filename":"bad.json","content":json.dumps([{"x":1}]),
             "source_title":"test","source_page":"1","confidence":4,"note":str(uuid.uuid4())}
    r=client.post("/api/admin/data-packages",json=payload,headers=h)
    assert r.status_code==200,r.text
    q=client.get("/api/admin/quality-gate",headers=h)
    assert q.status_code==200
    assert any(not p["valid"] for p in q.json()["packages"])

def test_golden_case_passes():
    h=auth()
    r=client.post("/api/admin/golden-cases",json={"name":"M10","thread":"M10","property_class":"10.9",
        "reference_torque_nm":70,"program_torque_nm":69.3,"tolerance_pct":5},headers=h)
    assert r.status_code==200,r.text
    assert r.json()["passed"]==1

def test_release_certificate_is_honest():
    h=auth()
    r=client.post("/api/admin/release-certificate",headers=h)
    assert r.status_code==200,r.text
    assert r.json()["decision"] in ("ONAYLI ÜRETİM SÜRÜMÜ","MÜHENDİSLİK ÖN DEĞERLENDİRMESİ")
