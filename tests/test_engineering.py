
import os
os.environ["TORQPRO_SECRET_KEY"]="x"*64
from fastapi.testclient import TestClient
from backend.app import app
client=TestClient(app)

def auth():
    r=client.post("/api/login",json={"username":"Protype Lab","password":"A1234"})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}

def test_engineering_check_monotonic_torque():
    payload={
      "diameter_mm":10,"pitch_mm":1.5,"stress_area_mm2":58.0,"rp02_mpa":900,
      "target_yield_ratio":0.75,"mu_thread_min":0.10,"mu_thread_nom":0.12,"mu_thread_max":0.14,
      "mu_bearing_min":0.10,"mu_bearing_nom":0.12,"mu_bearing_max":0.14,
      "effective_bearing_diameter_mm":15.0,"engagement_mm":10.0,
      "internal_rm_mpa":500,"bolt_rm_mpa":1000,"nut_proof_mpa":830
    }
    r=client.post("/api/engineering/check",json=payload,headers=auth())
    assert r.status_code==200,r.text
    d=r.json()
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]
    assert d["internal_thread_sf"] > 0
    assert d["external_thread_sf"] > 0
