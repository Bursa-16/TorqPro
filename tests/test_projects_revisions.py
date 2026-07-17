import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)

def _token(u="Protype Lab",p="A1234"):
    r=client.post("/api/login",json={"username":u,"password":p});assert r.status_code==200,r.text;return r.json()["token"]

def _hdr(t):return {"Authorization":"Bearer "+t}

def _ensure_viewer(admin_h):
    client.post("/api/admin/users",headers=admin_h,json={"username":"rbac_viewer","display_name":"RBAC Viewer","password":"viewerpass1","role":"viewer"})
    return _token("rbac_viewer","viewerpass1")

def test_viewer_cannot_create_project():
    vh=_hdr(_ensure_viewer(_hdr(_token())))
    r=client.post("/api/projects",headers=vh,json={"name":"ViewerProjesi"})
    assert r.status_code==403

def test_viewer_cannot_reject_revision():
    ah=_hdr(_token());vh=_hdr(_ensure_viewer(ah))
    cid=client.post("/api/calculations",headers=ah,json={"thread":"M10","torque_nm":45}).json()["id"]
    rid=client.post("/api/revisions",headers=ah,json={"calculation_id":cid,"note":"rbac"}).json()["id"]
    r=client.post(f"/api/revisions/{rid}/reject",headers=vh,json={"note":"viewer reddi"})
    assert r.status_code==403

def test_reject_missing_revision_returns_404():
    ah=_hdr(_token())
    r=client.post("/api/revisions/999999/reject",headers=ah,json={"note":"x"})
    assert r.status_code==404

def test_cannot_reject_own_revision():
    ah=_hdr(_token())
    cid=client.post("/api/calculations",headers=ah,json={"thread":"M12","torque_nm":80}).json()["id"]
    rid=client.post("/api/revisions",headers=ah,json={"calculation_id":cid,"note":"self"}).json()["id"]
    r=client.post(f"/api/revisions/{rid}/reject",headers=ah,json={"note":"self reject"})
    assert r.status_code==400
