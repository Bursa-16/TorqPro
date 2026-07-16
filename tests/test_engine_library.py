
import os, json, uuid
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)

def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}

def upload_activate(dataset, records):
    h=auth()
    payload={
      "dataset":dataset,"filename":dataset+".json","content":json.dumps(records),
      "source_title":"Primary test source","source_page":"Table 1",
      "confidence":4,"note":str(uuid.uuid4())
    }
    r=client.post("/api/admin/data-packages",json=payload,headers=h)
    assert r.status_code==200,r.text
    pid=r.json()["id"]
    r=client.patch(f"/api/admin/data-packages/{pid}/status",json={"status":"approved"},headers=h)
    assert r.status_code==200,r.text
    versions=client.get("/api/admin/data-versions",headers=h).json()
    v=next(x for x in versions if x["package_id"]==pid)
    r=client.post(f"/api/admin/data-versions/{v['id']}/activate",headers=h)
    assert r.status_code==200,r.text
    return h

def test_engine_library_exposes_active_records():
    h=upload_activate("proof_load",[{"thread_code":"M10","nut_property_class":"10","proof_stress_mpa":830}])
    r=client.get("/api/data/engine-library",headers=h)
    assert r.status_code==200,r.text
    d=r.json()
    assert any(x["thread_code"]=="M10" for x in d["proof_load"])
    assert d["metadata"]["counts"]["proof_load"]>=1

def test_friction_records_are_available():
    h=upload_activate("friction",[{"coating":"zinc","mu_thread_min":0.10,"mu_thread_nom":0.12,"mu_thread_max":0.14,"mu_bearing_min":0.10,"mu_bearing_nom":0.12,"mu_bearing_max":0.14}])
    r=client.get("/api/data/engine-library",headers=h)
    assert r.status_code==200
    assert len(r.json()["friction"])>=1
