
import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"});assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
def test_release_package_is_not_ready_without_approval():
    h=auth()
    p=client.post("/api/projects",json={"name":"Release Test","customer":"OEM"},headers=h).json()
    c=client.post("/api/calculations",json={"project_id":p["id"],"thread":"M10","torque_nm":70,"preload_n":39000,"confidence":3},headers=h)
    assert c.status_code==200,c.text
    r=client.get(f"/api/projects/{p['id']}/release-package",headers=h)
    assert r.status_code==200,r.text
    assert r.json()["summary"]["release_ready"] is False
def test_traceability_endpoint():
    h=auth()
    p=client.post("/api/projects",json={"name":"Trace Test"},headers=h).json()
    client.post("/api/calculations",json={"project_id":p["id"],"thread":"M8","torque_nm":25,"preload_n":17000,"confidence":2},headers=h)
    r=client.get(f"/api/projects/{p['id']}/traceability",headers=h)
    assert r.status_code==200
    assert len(r.json())>=1
