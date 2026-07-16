
import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"});assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
def test_health_endpoints():
    assert client.get("/health/live").status_code==200
    assert client.get("/health/ready").status_code==200
def test_cloud_readiness():
    r=client.get("/api/admin/cloud-readiness",headers=auth())
    assert r.status_code==200
    assert len(r.json()["checks"])>=5
