
import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"});assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
def test_organization_update():
    h=auth()
    r=client.put("/api/admin/organization",json={"name":"Test Corp","report_title":"Test Report"},headers=h)
    assert r.status_code==200,r.text
    g=client.get("/api/admin/organization",headers=h)
    assert g.status_code==200 and g.json()["name"]=="Test Corp"
def test_license_activation():
    h=auth()
    r=client.post("/api/admin/license/activate",json={"license_key":"TP-TRIAL-90"},headers=h)
    assert r.status_code==200,r.text
    g=client.get("/api/admin/license",headers=h)
    assert g.status_code==200 and g.json()["active"] is True
def test_invalid_license_rejected():
    h=auth()
    r=client.post("/api/admin/license/activate",json={"license_key":"BAD-KEY"},headers=h)
    assert r.status_code==400
