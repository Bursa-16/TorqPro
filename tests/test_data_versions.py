
import os, json, uuid
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)
def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"});assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
def test_version_activation():
    h=auth();content=json.dumps([{"id":str(uuid.uuid4()),"thread":"M10","value":1000}])
    r=client.post("/api/admin/data-packages",json={"dataset":"proof_load","filename":"x.json","content":content,"source_title":"Primary","source_page":"p1","confidence":4},headers=h);assert r.status_code==200,r.text
    pid=r.json()["id"];r=client.patch(f"/api/admin/data-packages/{pid}/status",json={"status":"approved"},headers=h);assert r.status_code==200,r.text
    versions=client.get("/api/admin/data-versions",headers=h).json();v=next(x for x in versions if x["package_id"]==pid)
    r=client.post(f"/api/admin/data-versions/{v['id']}/activate",headers=h);assert r.status_code==200,r.text
    active=client.get("/api/data/active",headers=h).json();assert active["datasets"]["proof_load"]["version_no"]==v["version_no"]
