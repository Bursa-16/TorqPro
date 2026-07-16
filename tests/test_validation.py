
import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"});assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
def test_summary_honest():
    r=client.get("/api/validation/summary",headers=auth());assert r.status_code==200
    assert r.json()["production_ready"] is False
def test_compatibility_precheck():
    r=client.post("/api/validation/compatibility?bolt_class=10.9&nut_class=10",headers=auth());assert r.status_code==200
    assert r.json()["status"]=="compatible" and r.json()["production_ready"] is False
