
import os, json
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"});assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
def test_deployment_profile():
    h=auth()
    r=client.put("/api/admin/deployment-profile",json={"environment":"Test","install_type":"standalone","host":"127.0.0.1","port":8000,"backup_frequency":"daily","update_channel":"stable"},headers=h)
    assert r.status_code==200,r.text
def test_export_and_validate_import():
    h=auth()
    e=client.post("/api/admin/system-export",headers=h)
    assert e.status_code==200,e.text
    p=e.json()
    r=client.post("/api/admin/system-import",json={"content":json.dumps(p)},headers=h)
    assert r.status_code==200,r.text
    assert r.json()["status"]=="validated"
def test_diagnostics():
    h=auth()
    r=client.get("/api/admin/diagnostics",headers=h)
    assert r.status_code==200
    assert len(r.json()["checks"])>=5
