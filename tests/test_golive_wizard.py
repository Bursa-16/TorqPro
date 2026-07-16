
import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
def test_profile():
    r=client.put("/api/admin/golive-profile",json={"server_ip":"192.0.2.10","domain":"app.example.com","https_status":"planned"},headers=auth())
    assert r.status_code==200
    assert r.json()["dns_planned"]==1
