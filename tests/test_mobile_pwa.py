
import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"});assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
def test_manifest_and_service_worker():
    assert client.get("/manifest.webmanifest").status_code==200
    assert client.get("/service-worker.js").status_code==200
def test_mobile_access_info():
    r=client.get("/api/mobile/access-info",headers=auth())
    assert r.status_code==200,r.text
    assert "local_url" in r.json()
