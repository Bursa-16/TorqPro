
import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def token():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"});assert r.status_code==200,r.text;return r.json()["token"]
def test_health():
    r=client.get("/api/health");assert r.status_code==200;assert r.json()["database_ok"] is True
def test_system():
    t=token();r=client.get("/api/admin/system",headers={"Authorization":"Bearer "+t});assert r.status_code==200;assert r.json()["schema_version"]>=3
def test_calculation():
    t=token();h={"Authorization":"Bearer "+t};r=client.post("/api/calculations",json={"standard":"ISO 4017","thread":"M10","property_class":"10.9","torque_nm":55,"preload_n":35000,"confidence":3},headers=h);assert r.status_code==200
