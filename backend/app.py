
from __future__ import annotations
import csv, json, hashlib, hmac, io, logging, os, platform, secrets, socket, sqlite3, tempfile, time, uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import jwt
from pydantic import BaseModel, Field

# Engineering Core: deterministic calculation layer (Phase 1 refactor).
# Dual import path: repo root (backend.engineering_core) or backend/ on sys.path (CI import check).
try:
    from backend.engineering_core.joint import evaluate_joint
    from backend.engineering_core.validation import QUALITY_SCHEMAS, validate_package_records, deviation_pct, tolerance_passed
except ImportError:  # pragma: no cover - direct import with backend/ on sys.path
    from engineering_core.joint import evaluate_joint  # type: ignore[no-redef]
    from engineering_core.validation import QUALITY_SCHEMAS, validate_package_records, deviation_pct, tolerance_passed  # type: ignore[no-redef]

BASE=Path(__file__).resolve().parent.parent
APP_VERSION="4.4"
DB=Path(os.getenv("TORQPRO_DB_PATH") or (BASE/"torqpro.db")); FRONT=BASE/"frontend"; SECRET_FILE=BASE/".torqpro_secret"
ALGORITHM="HS256"; ACCESS_TOKEN_MINUTES=480; SCHEMA_VERSION=3
LOGIN_ATTEMPTS: dict[str, deque] = defaultdict(deque)
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s",
 handlers=[logging.FileHandler(BASE/"torqpro.log",encoding="utf-8"),logging.StreamHandler()])
log=logging.getLogger("torqpro")
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(_app):
    migrate();log.info("TorqPro API started")
    yield
app=FastAPI(title="TorqPro API",version=APP_VERSION,lifespan=lifespan)

def utcnow(): return datetime.now(timezone.utc)
def now_iso(): return utcnow().isoformat()
def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def secret():
    e=os.getenv("TORQPRO_SECRET_KEY")
    if e and len(e)>=32:return e
    if SECRET_FILE.exists():return SECRET_FILE.read_text(encoding="utf-8").strip()
    s=secrets.token_urlsafe(64);SECRET_FILE.write_text(s,encoding="utf-8");return s
SECRET_KEY=secret()
def hp(p,s=None):
    s=s or os.urandom(16);d=hashlib.pbkdf2_hmac("sha256",p.encode(),s,250000);return s.hex()+":"+d.hex()
def vp(p,h):
    s,d=h.split(":",1);t=hashlib.pbkdf2_hmac("sha256",p.encode(),bytes.fromhex(s),250000);return hmac.compare_digest(t.hex(),d)
def audit(uid,action,detail="",rid=""):
    with conn() as c:c.execute("INSERT INTO audit_log(user_id,action,detail,request_id,created_at) VALUES(?,?,?,?,?)",(uid,action,detail,rid,now_iso()));c.commit()
def migrate():
    with conn() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS schema_info(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,display_name TEXT,password_hash TEXT,is_active INTEGER DEFAULT 1,role TEXT DEFAULT 'engineer',created_at TEXT);
        CREATE TABLE IF NOT EXISTS calculations(id INTEGER PRIMARY KEY,record_no TEXT UNIQUE,user_id INTEGER,created_at TEXT,family TEXT,standard TEXT,thread TEXT,property_class TEXT,nut TEXT,washer TEXT,coating TEXT,mu_thread REAL,mu_bearing REAL,preload_ratio REAL,torque_nm REAL,preload_n REAL,confidence INTEGER,engagement_mm REAL,internal_material TEXT,bearing_limit_mpa REAL,source_mode TEXT);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY,user_id INTEGER,action TEXT,detail TEXT,request_id TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS data_packages(
          id INTEGER PRIMARY KEY,
          package_no TEXT UNIQUE,
          dataset TEXT NOT NULL,
          filename TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          content_text TEXT NOT NULL,
          source_title TEXT,
          source_page TEXT,
          confidence INTEGER NOT NULL,
          note TEXT,
          record_count INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'draft',
          created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          reviewed_by INTEGER,
          reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS calibration_cases(
          id INTEGER PRIMARY KEY,
          thread TEXT NOT NULL,
          program_value REAL NOT NULL,
          reference_value REAL NOT NULL,
          tolerance_pct REAL NOT NULL,
          error_pct REAL NOT NULL,
          passed INTEGER NOT NULL,
          source_id TEXT,
          note TEXT,
          created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS data_versions(
          id INTEGER PRIMARY KEY,
          dataset TEXT NOT NULL,
          version_no TEXT NOT NULL,
          package_id INTEGER NOT NULL,
          package_no TEXT NOT NULL,
          confidence INTEGER NOT NULL,
          content_hash TEXT NOT NULL,
          is_active INTEGER NOT NULL DEFAULT 0,
          activated_by INTEGER,
          activated_at TEXT,
          deactivated_at TEXT,
          created_at TEXT NOT NULL,
          UNIQUE(dataset,version_no)
        );
        CREATE TABLE IF NOT EXISTS calculation_data_trace(
          id INTEGER PRIMARY KEY,
          calculation_id INTEGER NOT NULL,
          dataset TEXT NOT NULL,
          version_id INTEGER,
          version_no TEXT,
          package_no TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS golden_cases(
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          thread TEXT NOT NULL,
          property_class TEXT NOT NULL,
          reference_torque_nm REAL NOT NULL,
          program_torque_nm REAL NOT NULL,
          tolerance_pct REAL NOT NULL,
          error_pct REAL NOT NULL,
          passed INTEGER NOT NULL,
          created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS release_certificates(
          id INTEGER PRIMARY KEY,
          certificate_no TEXT UNIQUE NOT NULL,
          version_signature TEXT,
          quality_gate_passed INTEGER NOT NULL,
          golden_total INTEGER NOT NULL,
          golden_passed INTEGER NOT NULL,
          production_ready INTEGER NOT NULL,
          decision TEXT NOT NULL,
          created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY,name TEXT NOT NULL,customer TEXT,product TEXT,project_code TEXT,note TEXT,status TEXT DEFAULT 'open',created_by INTEGER,created_at TEXT);
        CREATE TABLE IF NOT EXISTS calculation_revisions(id INTEGER PRIMARY KEY,calculation_id INTEGER,revision_no INTEGER,snapshot_json TEXT,note TEXT,change_reason TEXT,status TEXT DEFAULT 'draft',is_locked INTEGER DEFAULT 0,created_by INTEGER,created_at TEXT,submitted_at TEXT,reviewed_by INTEGER,reviewed_at TEXT,review_note TEXT,UNIQUE(calculation_id,revision_no));
        CREATE TABLE IF NOT EXISTS project_release_packages(
          id INTEGER PRIMARY KEY,
          package_no TEXT UNIQUE NOT NULL,
          project_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          release_ready INTEGER NOT NULL,
          decision TEXT NOT NULL,
          created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS organization_settings(
          id INTEGER PRIMARY KEY CHECK(id=1),
          name TEXT,
          code TEXT,
          contact TEXT,
          email TEXT,
          report_title TEXT,
          logo TEXT,
          footer TEXT,
          updated_by INTEGER,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS license_info(
          id INTEGER PRIMARY KEY CHECK(id=1),
          license_key_hash TEXT,
          plan TEXT,
          expires_at TEXT,
          max_users INTEGER,
          max_projects INTEGER,
          modules_json TEXT,
          active INTEGER DEFAULT 0,
          activated_by INTEGER,
          activated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS deployment_profile(
          id INTEGER PRIMARY KEY CHECK(id=1),
          environment TEXT,
          install_type TEXT,
          host TEXT,
          port INTEGER,
          backup_frequency TEXT,
          update_channel TEXT,
          updated_by INTEGER,
          updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS migration_history(
          id INTEGER PRIMARY KEY,
          operation_no TEXT UNIQUE,
          operation_type TEXT,
          status TEXT,
          checksum TEXT,
          table_count INTEGER,
          record_count INTEGER,
          created_by INTEGER,
          created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS golive_profile(
          id INTEGER PRIMARY KEY CHECK(id=1),
          server_ip TEXT,
          domain TEXT,
          https_status TEXT,
          dns_planned INTEGER DEFAULT 0,
          docker_ready INTEGER DEFAULT 0,
          health_ready INTEGER DEFAULT 0,
          updated_by INTEGER,
          updated_at TEXT
        );""")
        calc_cols=[r["name"] for r in c.execute("PRAGMA table_info(calculations)").fetchall()]
        if "project_id" not in calc_cols:c.execute("ALTER TABLE calculations ADD COLUMN project_id INTEGER")
        cols=[r["name"] for r in c.execute("PRAGMA table_info(audit_log)").fetchall()]
        if "request_id" not in cols:c.execute("ALTER TABLE audit_log ADD COLUMN request_id TEXT")
        if not c.execute("SELECT 1 FROM users WHERE username='protype lab'").fetchone():
            c.execute("INSERT INTO users(username,display_name,password_hash,is_active,role,created_at) VALUES(?,?,?,?,?,?)",("protype lab","Protype Lab",hp("A1234"),1,"admin",now_iso()))
        else:c.execute("UPDATE users SET role='admin' WHERE username='protype lab'")
        c.execute("INSERT INTO schema_info(id,version,updated_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,updated_at=excluded.updated_at",(SCHEMA_VERSION,now_iso()))
        if not c.execute("SELECT 1 FROM organization_settings WHERE id=1").fetchone():
            c.execute("INSERT INTO organization_settings(id,name,report_title,footer,updated_at) VALUES(1,?,?,?,?)",
                      ("Protype Lab","TorqPro Mühendislik Raporu","Bu rapor TorqPro ile oluşturulmuştur.",now_iso()))
        if not c.execute("SELECT 1 FROM license_info WHERE id=1").fetchone():
            c.execute("INSERT INTO license_info(id,plan,max_users,max_projects,modules_json,active) VALUES(1,'Trial',3,5,?,0)",
                      (json.dumps(["calculation","projects","reports"]),))
        if not c.execute("SELECT 1 FROM deployment_profile WHERE id=1").fetchone():
            c.execute("INSERT INTO deployment_profile(id,environment,install_type,host,port,backup_frequency,update_channel,updated_at) VALUES(1,'Production','standalone','127.0.0.1',8000,'daily','stable',?)",(now_iso(),))
        if not c.execute("SELECT 1 FROM golive_profile WHERE id=1").fetchone():
            c.execute("INSERT INTO golive_profile(id,https_status,dns_planned,docker_ready,health_ready,updated_at) VALUES(1,'planned',0,1,0,?)",(now_iso(),))

        # Faz 2.5A prerequisite: joint foundation.
        from backend.joints.schema import migrate as migrate_joints
        migrate_joints(c)
        from backend.production_validation.repository import migrate as migrate_production_validation
        migrate_production_validation(c)

        c.commit()

@app.middleware("http")
async def mw(request:Request,call_next):
    rid=request.headers.get("X-Request-ID") or str(uuid.uuid4());st=time.perf_counter()
    try:r=await call_next(request)
    except Exception:
        log.exception("Unhandled request_id=%s",rid);return JSONResponse(status_code=500,content={"detail":"Sunucu hatası","request_id":rid})
    r.headers["X-Request-ID"]=rid;r.headers["X-Process-Time-Ms"]=f"{(time.perf_counter()-st)*1000:.1f}"
    r.headers["X-Content-Type-Options"]="nosniff";r.headers["X-Frame-Options"]="DENY";r.headers["Referrer-Policy"]="no-referrer";return r

class Login(BaseModel):username:str;password:str
class Calc(BaseModel):
    project_id:Optional[int]=None
    family:Optional[str]=None;standard:Optional[str]=None;thread:Optional[str]=None;property_class:Optional[str]=None
    nut:Optional[str]=None;washer:Optional[str]=None;coating:Optional[str]=None
    mu_thread:Optional[float]=Field(default=None,ge=0,le=1);mu_bearing:Optional[float]=Field(default=None,ge=0,le=1)
    preload_ratio:Optional[float]=Field(default=None,ge=0,le=100);torque_nm:Optional[float]=Field(default=None,ge=0)
    preload_n:Optional[float]=Field(default=None,ge=0);confidence:Optional[int]=Field(default=None,ge=1,le=4)
    engagement_mm:Optional[float]=Field(default=None,ge=0);internal_material:Optional[str]=None
    bearing_limit_mpa:Optional[float]=Field(default=None,ge=0);source_mode:Optional[str]=None
class PasswordChange(BaseModel):current_password:str;new_password:str=Field(min_length=8,max_length=128)
class NewUser(BaseModel):username:str=Field(min_length=3);display_name:str=Field(min_length=2);password:str=Field(min_length=8);role:str="engineer"
class UserPatch(BaseModel):role:Optional[str]=None;is_active:Optional[int]=None
class ResetPassword(BaseModel):new_password:str=Field(min_length=8)

def token(r):
    return jwt.encode({"sub":str(r["id"]),"name":r["display_name"],"role":r["role"],"exp":int((utcnow()+timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),"jti":secrets.token_hex(16)},SECRET_KEY,algorithm=ALGORITHM)
def user(authorization:str=Header(default="")):
    if not authorization.startswith("Bearer "):raise HTTPException(401,"Oturum gerekli")
    try:p=jwt.decode(authorization[7:],SECRET_KEY,algorithms=[ALGORITHM]);uid=int(p["sub"])
    except (jwt.PyJWTError,KeyError,ValueError):raise HTTPException(401,"Geçersiz veya süresi dolmuş oturum")
    with conn() as c:r=c.execute("SELECT id,username,display_name,is_active,role FROM users WHERE id=?",(uid,)).fetchone()
    if not r or not r["is_active"]:raise HTTPException(401,"Kullanıcı aktif değil")
    return dict(r)
def admin(u=Depends(user)):
    if u["role"]!="admin":raise HTTPException(403,"Yönetici yetkisi gerekli")
    return u
def limit(name):
    q=LOGIN_ATTEMPTS[name.lower().strip()];n=time.time()
    while q and n-q[0]>300:q.popleft()
    if len(q)>=5:raise HTTPException(429,"Çok fazla başarısız giriş. 5 dakika sonra tekrar deneyin.")
    return q

@app.get("/api/health")
def health():
    try:
        with conn() as c:c.execute("SELECT 1").fetchone()
        ok=True
    except Exception:ok=False
    return {"status":"ok" if ok else "degraded","version":APP_VERSION,"database_ok":ok,"server_time":now_iso()}

@app.post("/api/login")
def login(x:Login,request:Request):
    q=limit(x.username)
    with conn() as c:r=c.execute("SELECT * FROM users WHERE username=? AND is_active=1",(x.username.strip().lower(),)).fetchone()
    if not r or not vp(x.password,r["password_hash"]):
        q.append(time.time());audit(r["id"] if r else None,"login_failed",x.username,request.headers.get("X-Request-ID",""));raise HTTPException(401,"Kullanıcı adı veya şifre hatalı")
    q.clear();audit(r["id"],"login","Başarılı giriş");return {"token":token(r),"display_name":r["display_name"],"role":r["role"],"expires_in":ACCESS_TOKEN_MINUTES*60}

@app.post("/api/change-password")
def chg(x:PasswordChange,u=Depends(user)):
    with conn() as c:r=c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
    if not r or not vp(x.current_password,r["password_hash"]):raise HTTPException(400,"Mevcut şifre yanlış")
    with conn() as c:c.execute("UPDATE users SET password_hash=? WHERE id=?",(hp(x.new_password),u["id"]));c.commit()
    audit(u["id"],"password_change");return {"ok":True}

@app.post("/api/calculations")
def add(x:Calc,u=Depends(user)):
    if u["role"]=="viewer":raise HTTPException(403,"Viewer rolü kayıt oluşturamaz")
    n=utcnow();no="TP-"+n.strftime("%Y%m%d-%H%M%S-%f");d=x.model_dump()
    cols=["project_id","family","standard","thread","property_class","nut","washer","coating","mu_thread","mu_bearing","preload_ratio","torque_nm","preload_n","confidence","engagement_mm","internal_material","bearing_limit_mpa","source_mode"]
    with conn() as c:
        c.execute("INSERT INTO calculations(record_no,user_id,created_at,"+",".join(cols)+") VALUES("+",".join(["?"]*(3+len(cols)))+")",[no,u["id"],n.isoformat()]+[d[k] for k in cols]);c.commit()
        r=c.execute("SELECT * FROM calculations WHERE record_no=?",(no,)).fetchone()
    with conn() as c:
        for v in c.execute("SELECT * FROM data_versions WHERE is_active=1").fetchall():
            c.execute("INSERT INTO calculation_data_trace(calculation_id,dataset,version_id,version_no,package_no,created_at) VALUES(?,?,?,?,?,?)",
                      (r["id"],v["dataset"],v["id"],v["version_no"],v["package_no"],now_iso()))
        c.commit()
    audit(u["id"],"calculation_create",no);return dict(r)

@app.get("/api/calculations")
def lst(q:str="",u=Depends(user)):
    sql="SELECT * FROM calculations WHERE user_id=?";p=[u["id"]]
    if q:sql+=" AND (record_no LIKE ? OR standard LIKE ? OR thread LIKE ? OR property_class LIKE ? OR family LIKE ?)";like="%"+q+"%";p += [like]*5
    sql+=" ORDER BY id DESC LIMIT 1000"
    with conn() as c:r=c.execute(sql,p).fetchall()
    return [dict(x) for x in r]

@app.delete("/api/calculations/{cid}")
def dele(cid:int,u=Depends(user)):
    if u["role"]=="viewer":raise HTTPException(403,"Viewer rolü kayıt silemez")
    with conn() as c:cur=c.execute("DELETE FROM calculations WHERE id=? AND user_id=?",(cid,u["id"]));c.commit()
    if not cur.rowcount:raise HTTPException(404,"Kayıt bulunamadı")
    audit(u["id"],"calculation_delete",str(cid));return {"ok":True}

@app.delete("/api/calculations")
def clear(u=Depends(user)):
    if u["role"]=="viewer":raise HTTPException(403,"Viewer rolü arşivi silemez")
    with conn() as c:c.execute("DELETE FROM calculations WHERE user_id=?",(u["id"],));c.commit()
    audit(u["id"],"calculation_clear");return {"ok":True}

@app.get("/api/calculations/export.csv")
def export(u=Depends(user)):
    with conn() as c:r=c.execute("SELECT * FROM calculations WHERE user_id=? ORDER BY id DESC",(u["id"],)).fetchall()
    s=io.StringIO()
    if r:
        w=csv.DictWriter(s,fieldnames=r[0].keys(),delimiter=";");w.writeheader();w.writerows([dict(x) for x in r])
    return StreamingResponse(iter([("\ufeff"+s.getvalue()).encode("utf-8")]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=TorqPro_Arsiv.csv"})

@app.get("/api/admin/users")
def au(u=Depends(admin)):
    with conn() as c:r=c.execute("SELECT id,username,display_name,is_active,role,created_at FROM users ORDER BY id").fetchall()
    return [dict(x) for x in r]
@app.post("/api/admin/users")
def ac(x:NewUser,u=Depends(admin)):
    role=x.role if x.role in ("admin","engineer","viewer") else "engineer"
    try:
        with conn() as c:c.execute("INSERT INTO users(username,display_name,password_hash,is_active,role,created_at) VALUES(?,?,?,?,?,?)",(x.username.strip().lower(),x.display_name.strip(),hp(x.password),1,role,now_iso()));c.commit()
    except sqlite3.IntegrityError:raise HTTPException(400,"Kullanıcı adı zaten mevcut")
    audit(u["id"],"user_create",x.username);return {"ok":True}
@app.patch("/api/admin/users/{uid}")
def uu(uid:int,x:UserPatch,u=Depends(admin)):
    sets:list[str]=[];vals:list[str|int]=[]
    if x.role is not None:
        if x.role not in ("admin","engineer","viewer"):raise HTTPException(400,"Geçersiz rol")
        sets.append("role=?");vals.append(x.role)
    if x.is_active is not None:
        if uid==u["id"] and x.is_active==0:raise HTTPException(400,"Kendi hesabınızı pasifleştiremezsiniz")
        sets.append("is_active=?");vals.append(1 if x.is_active else 0)
    if sets:
        vals.append(uid)
        with conn() as c:c.execute("UPDATE users SET "+",".join(sets)+" WHERE id=?",vals);c.commit()
    audit(u["id"],"user_update",str(uid));return {"ok":True}
@app.post("/api/admin/users/{uid}/reset-password")
def rp(uid:int,x:ResetPassword,u=Depends(admin)):
    with conn() as c:c.execute("UPDATE users SET password_hash=? WHERE id=?",(hp(x.new_password),uid));c.commit()
    audit(u["id"],"user_password_reset",str(uid));return {"ok":True}
@app.get("/api/admin/audit")
def aa(u=Depends(admin)):
    with conn() as c:r=c.execute("SELECT a.id,a.action,a.detail,a.request_id,a.created_at,us.username FROM audit_log a LEFT JOIN users us ON us.id=a.user_id ORDER BY a.id DESC LIMIT 500").fetchall()
    return [dict(x) for x in r]
@app.get("/api/admin/system")
def system(u=Depends(admin)):
    with conn() as c:
        tu=c.execute("SELECT COUNT(*) c FROM users").fetchone()["c"];auu=c.execute("SELECT COUNT(*) c FROM users WHERE is_active=1").fetchone()["c"]
        cc=c.execute("SELECT COUNT(*) c FROM calculations").fetchone()["c"];acn=c.execute("SELECT COUNT(*) c FROM audit_log").fetchone()["c"];sv=c.execute("SELECT version FROM schema_info WHERE id=1").fetchone()["version"]
    return {"status":"ok","version":APP_VERSION,"database_ok":True,"database_size_kb":round(DB.stat().st_size/1024,1) if DB.exists() else 0,"total_users":tu,"active_users":auu,"calculation_count":cc,"audit_count":acn,"schema_version":sv,"server_time":now_iso()}
@app.get("/api/admin/backup")
def backup(u=Depends(admin)):
    fd,path=tempfile.mkstemp(suffix=".db");os.close(fd)
    with conn() as src,sqlite3.connect(path) as dst:src.backup(dst)
    audit(u["id"],"database_backup");return FileResponse(path,media_type="application/octet-stream",filename="TorqPro_Backup.db")


class EngineeringCheck(BaseModel):
    diameter_mm: float = Field(gt=0)
    pitch_mm: float = Field(gt=0)
    stress_area_mm2: float = Field(gt=0)
    rp02_mpa: float = Field(gt=0)
    target_yield_ratio: float = Field(gt=0, le=0.95)
    mu_thread_min: float = Field(ge=0, le=1)
    mu_thread_nom: float = Field(ge=0, le=1)
    mu_thread_max: float = Field(ge=0, le=1)
    mu_bearing_min: float = Field(ge=0, le=1)
    mu_bearing_nom: float = Field(ge=0, le=1)
    mu_bearing_max: float = Field(ge=0, le=1)
    effective_bearing_diameter_mm: float = Field(gt=0)
    engagement_mm: float = Field(gt=0)
    internal_rm_mpa: float = Field(gt=0)
    bolt_rm_mpa: float = Field(gt=0)
    nut_proof_mpa: float = Field(gt=0)

@app.post("/api/engineering/check")
def engineering_check(x: EngineeringCheck, u=Depends(user)):
    # Orchestration only: input validated by Pydantic, calculation in engineering_core.
    return evaluate_joint(**x.model_dump())


DATA_DIR=BASE/"data"
def load_data(name):
    p=DATA_DIR/name
    if not p.exists():raise HTTPException(404,"Veri dosyası bulunamadı")
    return json.loads(p.read_text(encoding="utf-8"))

@app.get("/api/validation/datasets")
def validation_datasets(u=Depends(user)):
    files=["ISO_898_2_Somun_Proof_Load.json","Civata_Somun_Uyumluluk.json","Pul_Sertlik_Yuzey_Basinci.json","Surtunme_Veritabani.json","Teknik_Kaynak_Kayitlari.json"]
    out=[]
    for f in files:
        d=load_data(f);rows=d.get("records",d.get("rules",[]))
        out.append({"file":f,"metadata":d.get("metadata",{}),"record_count":len(rows)})
    return out

@app.get("/api/validation/summary")
def validation_summary(u=Depends(user)):
    p=load_data("ISO_898_2_Somun_Proof_Load.json");f=load_data("Surtunme_Veritabani.json")
    pc=len(p.get("records",[]));vf=[r for r in f.get("records",[]) if r.get("confidence",0)>=4 and r.get("test_report_id")]
    ready=pc>0 and len(vf)>0
    return {"version":APP_VERSION,"proof_load_records":pc,"verified_friction_records":len(vf),"production_ready":ready,"decision":"production_ready" if ready else "engineering_precheck_only"}

@app.post("/api/validation/compatibility")
def validation_compatibility(bolt_class:str,nut_class:str,u=Depends(user)):
    rules=load_data("Civata_Somun_Uyumluluk.json").get("rules",[])
    r=next((x for x in rules if x["bolt_class"]==bolt_class),None)
    if not r:return {"status":"unknown","production_ready":False}
    try:ok=float(nut_class)>=float(r["minimum_nut_class"])
    except ValueError:ok=False
    return {"status":"compatible" if ok else "incompatible","minimum_nut_class":r["minimum_nut_class"],"confidence":r["confidence"],"production_ready":False,"reason":"Proof-load tablosu doğrulanmadan yalnız ön kontroldür."}


class DataPackageIn(BaseModel):
    dataset:str
    filename:str
    content:str
    source_title:Optional[str]=None
    source_page:Optional[str]=None
    confidence:int=Field(ge=1,le=4)
    note:Optional[str]=None

class DataPackageStatus(BaseModel):
    status:str

class CalibrationCaseIn(BaseModel):
    thread:str
    program_value:float
    reference_value:float
    tolerance_pct:float=Field(ge=0)
    source_id:Optional[str]=None
    note:Optional[str]=None

def parse_uploaded_content(filename:str,content:str):
    if filename.lower().endswith(".json"):
        obj=json.loads(content)
        if isinstance(obj,list): return obj
        if isinstance(obj,dict):
            return obj.get("records",obj.get("rules",[obj]))
        raise HTTPException(400,"JSON yapısı desteklenmiyor")
    if filename.lower().endswith(".csv"):
        import csv as _csv, io as _io
        sample=content[:2048]
        try: dialect=_csv.Sniffer().sniff(sample,delimiters=";,")
        except Exception: dialect=_csv.excel
        return list(_csv.DictReader(_io.StringIO(content),dialect=dialect))
    raise HTTPException(400,"Yalnız JSON veya CSV desteklenir")

@app.post("/api/admin/data-packages")
def create_data_package(x:DataPackageIn,u=Depends(admin)):
    allowed={"proof_load","friction","washer","compatibility"}
    if x.dataset not in allowed:raise HTTPException(400,"Geçersiz veri seti")
    try:records=parse_uploaded_content(x.filename,x.content)
    except json.JSONDecodeError as e:raise HTTPException(400,f"JSON hatası: {e}")
    if len(records)>50000:raise HTTPException(400,"Paket çok büyük")
    h=hashlib.sha256(x.content.encode("utf-8")).hexdigest()
    no="DP-"+utcnow().strftime("%Y%m%d-%H%M%S-%f")
    with conn() as c:
        if c.execute("SELECT 1 FROM data_packages WHERE content_hash=?",(h,)).fetchone():
            raise HTTPException(400,"Aynı içerik daha önce yüklenmiş")
        c.execute("""INSERT INTO data_packages(package_no,dataset,filename,content_hash,content_text,source_title,source_page,confidence,note,record_count,status,created_by,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (no,x.dataset,x.filename,h,x.content,x.source_title,x.source_page,x.confidence,x.note,len(records),"draft",u["id"],now_iso()))
        c.commit()
        row=c.execute("SELECT * FROM data_packages WHERE package_no=?",(no,)).fetchone()
    audit(u["id"],"data_package_create",no)
    return dict(row)

@app.get("/api/admin/data-packages")
def list_data_packages(u=Depends(admin)):
    with conn() as c:rows=c.execute("SELECT id,package_no,dataset,filename,source_title,source_page,confidence,note,record_count,status,created_at,reviewed_at FROM data_packages ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]

@app.patch("/api/admin/data-packages/{pid}/status")
def set_data_package_status(pid:int,x:DataPackageStatus,u=Depends(admin)):
    if x.status not in ("draft","review","approved","rejected"):raise HTTPException(400,"Geçersiz durum")
    with conn() as c:
        row=c.execute("SELECT * FROM data_packages WHERE id=?",(pid,)).fetchone()
        if not row:raise HTTPException(404,"Paket bulunamadı")
        if x.status=="approved" and row["confidence"]<4:
            raise HTTPException(400,"Yalnız Güven 4 paket onaylanabilir")
        c.execute("UPDATE data_packages SET status=?,reviewed_by=?,reviewed_at=? WHERE id=?",(x.status,u["id"],now_iso(),pid))
        if x.status=="approved":
            existing=c.execute("SELECT COUNT(*) c FROM data_versions WHERE dataset=?",(row["dataset"],)).fetchone()["c"]
            version_no="v"+str(existing+1)
            c.execute("INSERT OR IGNORE INTO data_versions(dataset,version_no,package_id,package_no,confidence,content_hash,is_active,created_at) VALUES(?,?,?,?,?,?,0,?)",
                      (row["dataset"],version_no,row["id"],row["package_no"],row["confidence"],row["content_hash"],now_iso()))
        c.commit()
    audit(u["id"],"data_package_status",f"{pid}:{x.status}")
    return {"ok":True}

@app.get("/api/admin/data-packages/summary")
def data_package_summary(u=Depends(admin)):
    with conn() as c:
        rows=c.execute("SELECT dataset,status,COUNT(*) c,SUM(record_count) records FROM data_packages GROUP BY dataset,status").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/calibration/cases")
def create_calibration_case(x:CalibrationCaseIn,u=Depends(user)):
    if x.reference_value==0:raise HTTPException(400,"Referans sıfır olamaz")
    err=deviation_pct(x.program_value,x.reference_value)
    passed=tolerance_passed(err,x.tolerance_pct)
    with conn() as c:
        c.execute("""INSERT INTO calibration_cases(thread,program_value,reference_value,tolerance_pct,error_pct,passed,source_id,note,created_by,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (x.thread,x.program_value,x.reference_value,x.tolerance_pct,err,passed,x.source_id,x.note,u["id"],now_iso()))
        c.commit()
        row=c.execute("SELECT * FROM calibration_cases WHERE id=last_insert_rowid()").fetchone()
    audit(u["id"],"calibration_case_create",x.thread)
    return dict(row)

@app.get("/api/calibration/cases")
def list_calibration_cases(u=Depends(user)):
    with conn() as c:rows=c.execute("SELECT * FROM calibration_cases ORDER BY id DESC LIMIT 1000").fetchall()
    return [dict(r) for r in rows]

@app.get("/api/calibration/summary")
def calibration_summary(u=Depends(user)):
    with conn() as c:
        row=c.execute("SELECT COUNT(*) total,SUM(passed) passed,AVG(error_pct) avg_error,MAX(error_pct) max_error FROM calibration_cases").fetchone()
    total=row["total"] or 0;passed=row["passed"] or 0
    return {"total":total,"passed":passed,"failed":total-passed,"pass_rate_pct":(passed/total*100 if total else 0),"avg_error_pct":row["avg_error"] or 0,"max_error_pct":row["max_error"] or 0}


@app.get("/api/admin/data-versions")
def data_versions(u=Depends(admin)):
    with conn() as c:r=c.execute("SELECT v.*,p.filename,p.source_title,p.source_page FROM data_versions v JOIN data_packages p ON p.id=v.package_id ORDER BY v.dataset,v.id DESC").fetchall()
    return [dict(x) for x in r]

@app.post("/api/admin/data-versions/{vid}/activate")
def activate_version(vid:int,u=Depends(admin)):
    with conn() as c:
        r=c.execute("SELECT * FROM data_versions WHERE id=?",(vid,)).fetchone()
        if not r:raise HTTPException(404,"Sürüm bulunamadı")
        p=c.execute("SELECT * FROM data_packages WHERE id=?",(r["package_id"],)).fetchone()
        if not p or p["status"]!="approved" or p["confidence"]<4:raise HTTPException(400,"Yalnız onaylı Güven 4 paket aktifleştirilebilir")
        c.execute("UPDATE data_versions SET is_active=0,deactivated_at=? WHERE dataset=? AND is_active=1",(now_iso(),r["dataset"]))
        c.execute("UPDATE data_versions SET is_active=1,activated_by=?,activated_at=?,deactivated_at=NULL WHERE id=?",(u["id"],now_iso(),vid));c.commit()
    audit(u["id"],"data_version_activate",r["dataset"]+":"+r["version_no"]);return {"ok":True}

@app.post("/api/admin/data-versions/{vid}/rollback")
def rollback_version(vid:int,u=Depends(admin)):
    with conn() as c:
        r=c.execute("SELECT * FROM data_versions WHERE id=?",(vid,)).fetchone()
        if not r:raise HTTPException(404,"Sürüm bulunamadı")
        p=c.execute("SELECT * FROM data_versions WHERE dataset=? AND id<? AND confidence=4 ORDER BY id DESC LIMIT 1",(r["dataset"],r["id"])).fetchone()
        if not p:raise HTTPException(400,"Önceki Güven 4 sürüm yok")
        c.execute("UPDATE data_versions SET is_active=0,deactivated_at=? WHERE dataset=? AND is_active=1",(now_iso(),r["dataset"]))
        c.execute("UPDATE data_versions SET is_active=1,activated_by=?,activated_at=?,deactivated_at=NULL WHERE id=?",(u["id"],now_iso(),p["id"]));c.commit()
    audit(u["id"],"data_version_rollback",r["dataset"]+":"+r["version_no"]+"->"+p["version_no"]);return {"ok":True,"active_version":p["version_no"]}

@app.get("/api/data/active")
def active_data(u=Depends(user)):
    with conn() as c:r=c.execute("SELECT v.*,p.filename,p.source_title,p.source_page FROM data_versions v JOIN data_packages p ON p.id=v.package_id WHERE v.is_active=1").fetchall()
    ds={x["dataset"]:dict(x) for x in r};required={"proof_load","friction","washer","compatibility"}
    sig="|".join(k+":"+ds[k]["version_no"] for k in sorted(ds)) if ds else None
    return {"version":APP_VERSION,"datasets":ds,"production_ready":required.issubset(set(ds)),"version_signature":sig}

@app.get("/api/admin/data-versions/impact")
def version_impact(dataset:str,limit:int=100,u=Depends(admin)):
    if limit<1 or limit>1000:raise HTTPException(400,"Limit 1-1000 arasında olmalı")
    with conn() as c:
        a=c.execute("SELECT * FROM data_versions WHERE dataset=? AND is_active=1",(dataset,)).fetchone()
        total=c.execute("SELECT COUNT(*) c FROM calculations").fetchone()["c"]
        affected=c.execute("SELECT COUNT(DISTINCT calculation_id) c FROM calculation_data_trace WHERE dataset=?",(dataset,)).fetchone()["c"]
    return {"dataset":dataset,"calculation_count":min(total,limit),"active_version":a["version_no"] if a else None,"affected_count":min(affected,limit),"note":"Kayıtlı hesapların veri sürümü izleri sayıldı."}

@app.get("/api/calculations/{cid}/data-trace")
def calc_trace(cid:int,u=Depends(user)):
    with conn() as c:
        calc=c.execute("SELECT * FROM calculations WHERE id=? AND user_id=?",(cid,u["id"])).fetchone()
        if not calc:raise HTTPException(404,"Hesap bulunamadı")
        r=c.execute("SELECT * FROM calculation_data_trace WHERE calculation_id=? ORDER BY dataset",(cid,)).fetchall()
    return {"record_no":calc["record_no"],"data_versions":[dict(x) for x in r]}


def normalize_engine_records(dataset, records):
    out=[]
    for raw in records:
        if not isinstance(raw,dict):
            continue
        r={str(k).strip():v for k,v in raw.items()}
        r["_dataset"]=dataset
        out.append(r)
    return out

@app.get("/api/data/engine-library")
def engine_library(u=Depends(user)):
    datasets={"proof_load":[],"friction":[],"washer":[],"compatibility":[]}
    versions={}
    with conn() as c:
        rows=c.execute("""SELECT v.dataset,v.version_no,v.package_no,v.confidence,p.content_text,p.filename,p.source_title,p.source_page
                          FROM data_versions v JOIN data_packages p ON p.id=v.package_id
                          WHERE v.is_active=1""").fetchall()
    for row in rows:
        try:
            records=parse_uploaded_content(row["filename"],row["content_text"])
        except Exception as exc:
            log.error("Active package parse failed %s: %s",row["package_no"],exc)
            records=[]
        if row["dataset"] in datasets:
            normalized=normalize_engine_records(row["dataset"],records)
            for item in normalized:
                item["_version_no"]=row["version_no"]
                item["_package_no"]=row["package_no"]
                item["_confidence"]=row["confidence"]
                item["_source_title"]=row["source_title"]
                item["_source_page"]=row["source_page"]
            datasets[row["dataset"]].extend(normalized)
            versions[row["dataset"]]={
                "version_no":row["version_no"],"package_no":row["package_no"],
                "confidence":row["confidence"],"source_title":row["source_title"],"source_page":row["source_page"]
            }
    signature="|".join(f"{k}:{versions[k]['version_no']}" for k in sorted(versions)) if versions else None
    return {
      **datasets,
      "metadata":{"versions":versions,"counts":{k:len(v) for k,v in datasets.items()}},
      "version_signature":signature,
      "production_ready":set(datasets.keys()).issubset(set(versions.keys()))
    }


# QUALITY_SCHEMAS ve validate_package_records artık engineering_core.validation içinde (Faz 1 taşıma).

@app.get("/api/admin/quality-gate")
def quality_gate(u=Depends(admin)):
    with conn() as c:rows=c.execute("SELECT * FROM data_packages ORDER BY id DESC").fetchall()
    out=[];passed=0
    for row in rows:
        try:records=parse_uploaded_content(row["filename"],row["content_text"])
        except Exception as exc:records=[];valid=False;errors=[str(exc)]
        else:valid,errors=validate_package_records(row["dataset"],records)
        if valid:passed+=1
        out.append({"id":row["id"],"package_no":row["package_no"],"dataset":row["dataset"],"filename":row["filename"],
                    "record_count":len(records),"valid":valid,"error_count":len(errors),"errors":errors})
    return {"summary":{"total":len(out),"passed":passed,"failed":len(out)-passed},"packages":out}

class GoldenCaseIn(BaseModel):
    name:str
    thread:str
    property_class:str
    reference_torque_nm:float
    program_torque_nm:float
    tolerance_pct:float=Field(ge=0)

@app.post("/api/admin/golden-cases")
def create_golden_case(x:GoldenCaseIn,u=Depends(admin)):
    if x.reference_torque_nm==0:raise HTTPException(400,"Referans tork sıfır olamaz")
    err=deviation_pct(x.program_torque_nm,x.reference_torque_nm)
    passed=tolerance_passed(err,x.tolerance_pct)
    with conn() as c:
        c.execute("INSERT INTO golden_cases(name,thread,property_class,reference_torque_nm,program_torque_nm,tolerance_pct,error_pct,passed,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (x.name,x.thread,x.property_class,x.reference_torque_nm,x.program_torque_nm,x.tolerance_pct,err,passed,u["id"],now_iso()))
        c.commit()
        row=c.execute("SELECT * FROM golden_cases WHERE id=last_insert_rowid()").fetchone()
    audit(u["id"],"golden_case_create",x.name)
    return dict(row)

@app.get("/api/admin/golden-cases")
def list_golden_cases(u=Depends(admin)):
    with conn() as c:rows=c.execute("SELECT * FROM golden_cases ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/admin/release-certificate")
def create_release_certificate(u=Depends(admin)):
    with conn() as c:
        active=c.execute("SELECT dataset,version_no FROM data_versions WHERE is_active=1 ORDER BY dataset").fetchall()
        packages=c.execute("SELECT * FROM data_packages").fetchall()
        golden=c.execute("SELECT COUNT(*) total,SUM(passed) passed FROM golden_cases").fetchone()
    signature="|".join(f"{r['dataset']}:{r['version_no']}" for r in active) if active else None
    qg_ok=True
    for row in packages:
        try:records=parse_uploaded_content(row["filename"],row["content_text"])
        except Exception:qg_ok=False;break
        valid,_=validate_package_records(row["dataset"],records)
        if not valid:qg_ok=False;break
    golden_total=golden["total"] or 0;golden_passed=golden["passed"] or 0
    required={"proof_load","friction","washer","compatibility"}
    active_sets={r["dataset"] for r in active}
    production_ready=qg_ok and required.issubset(active_sets) and golden_total>0 and golden_total==golden_passed
    decision="ONAYLI ÜRETİM SÜRÜMÜ" if production_ready else "MÜHENDİSLİK ÖN DEĞERLENDİRMESİ"
    cert="CERT-"+utcnow().strftime("%Y%m%d-%H%M%S-%f")
    with conn() as c:
        c.execute("INSERT INTO release_certificates(certificate_no,version_signature,quality_gate_passed,golden_total,golden_passed,production_ready,decision,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (cert,signature,1 if qg_ok else 0,golden_total,golden_passed,1 if production_ready else 0,decision,u["id"],now_iso()))
        c.commit()
        row=c.execute("SELECT * FROM release_certificates WHERE certificate_no=?",(cert,)).fetchone()
    audit(u["id"],"release_certificate_create",cert)
    return dict(row)


class ProjectIn(BaseModel):
    name:str
    customer:Optional[str]=None
    product:Optional[str]=None
    project_code:Optional[str]=None
class RevisionIn(BaseModel):
    calculation_id:int
    note:Optional[str]=None
    change_reason:Optional[str]=None
class ReviewIn(BaseModel):
    note:Optional[str]=None

@app.post("/api/projects")
def create_project(x:ProjectIn,u=Depends(user)):
    if u["role"]=="viewer":raise HTTPException(403,"Viewer rolü proje oluşturamaz")
    with conn() as c:
        c.execute("INSERT INTO projects(name,customer,product,project_code,status,created_by,created_at) VALUES(?,?,?,?,'open',?,?)",(x.name,x.customer,x.product,x.project_code,u["id"],now_iso()));c.commit()
        r=c.execute("SELECT * FROM projects WHERE id=last_insert_rowid()").fetchone()
    return dict(r)

@app.get("/api/projects")
def list_projects(u=Depends(user)):
    with conn() as c:r=c.execute("SELECT p.*,COUNT(cal.id) calculation_count FROM projects p LEFT JOIN calculations cal ON cal.project_id=p.id GROUP BY p.id ORDER BY p.id DESC").fetchall()
    return [dict(x) for x in r]

@app.post("/api/revisions")
def create_revision(x:RevisionIn,u=Depends(user)):
    with conn() as c:
        calc=c.execute("SELECT * FROM calculations WHERE id=? AND user_id=?",(x.calculation_id,u["id"])).fetchone()
        if not calc:raise HTTPException(404,"Hesap bulunamadı")
        if c.execute("SELECT 1 FROM calculation_revisions WHERE calculation_id=? AND is_locked=1",(x.calculation_id,)).fetchone():raise HTTPException(400,"Onaylı hesap kilitlidir")
        rev=c.execute("SELECT COALESCE(MAX(revision_no),0)+1 n FROM calculation_revisions WHERE calculation_id=?",(x.calculation_id,)).fetchone()["n"]
        c.execute("INSERT INTO calculation_revisions(calculation_id,revision_no,snapshot_json,note,change_reason,status,is_locked,created_by,created_at) VALUES(?,?,?,?,?,'draft',0,?,?)",(x.calculation_id,rev,json.dumps(dict(calc),ensure_ascii=False),x.note,x.change_reason,u["id"],now_iso()));c.commit()
        r=c.execute("SELECT * FROM calculation_revisions WHERE id=last_insert_rowid()").fetchone()
    return dict(r)

@app.get("/api/revisions")
def list_revisions(u=Depends(user)):
    with conn() as c:r=c.execute("SELECT r.*,cal.record_no,us.display_name created_by_name FROM calculation_revisions r JOIN calculations cal ON cal.id=r.calculation_id LEFT JOIN users us ON us.id=r.created_by WHERE cal.user_id=? ORDER BY r.id DESC",(u["id"],)).fetchall()
    return [dict(x) for x in r]

@app.post("/api/revisions/{rid}/submit")
def submit_revision(rid:int,u=Depends(user)):
    with conn() as c:
        r=c.execute("SELECT r.*,cal.user_id FROM calculation_revisions r JOIN calculations cal ON cal.id=r.calculation_id WHERE r.id=?",(rid,)).fetchone()
        if not r or r["user_id"]!=u["id"]:raise HTTPException(404,"Revizyon bulunamadı")
        if r["status"]!="draft":raise HTTPException(400,"Yalnız taslak gönderilebilir")
        c.execute("UPDATE calculation_revisions SET status='review',submitted_at=? WHERE id=?",(now_iso(),rid));c.commit()
    return {"ok":True}

@app.get("/api/approvals/queue")
def approval_queue(u=Depends(user)):
    if u["role"] not in ("admin","engineer"):raise HTTPException(403,"Yetki gerekli")
    with conn() as c:r=c.execute("SELECT r.*,cal.record_no,us.display_name creator_name FROM calculation_revisions r JOIN calculations cal ON cal.id=r.calculation_id LEFT JOIN users us ON us.id=r.created_by WHERE r.status='review' ORDER BY r.submitted_at").fetchall()
    return [dict(x) for x in r]

@app.post("/api/revisions/{rid}/approve")
def approve_revision(rid:int,x:ReviewIn,u=Depends(user)):
    if u["role"] not in ("admin","engineer"):raise HTTPException(403,"Yetki gerekli")
    with conn() as c:
        r=c.execute("SELECT * FROM calculation_revisions WHERE id=?",(rid,)).fetchone()
        if not r:raise HTTPException(404,"Revizyon bulunamadı")
        if r["created_by"]==u["id"]:raise HTTPException(400,"Kendi revizyonunuzu onaylayamazsınız")
        c.execute("UPDATE calculation_revisions SET status='approved',is_locked=1,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?",(u["id"],now_iso(),x.note,rid));c.commit()
    return {"ok":True}

@app.post("/api/revisions/{rid}/reject")
def reject_revision(rid:int,x:ReviewIn,u=Depends(user)):
    if u["role"] not in ("admin","engineer"):raise HTTPException(403,"Yetki gerekli")
    with conn() as c:
        r=c.execute("SELECT * FROM calculation_revisions WHERE id=?",(rid,)).fetchone()
        if not r:raise HTTPException(404,"Revizyon bulunamadı")
        if r["created_by"]==u["id"]:raise HTTPException(400,"Kendi revizyonunuzu reddedemezsiniz")
        c.execute("UPDATE calculation_revisions SET status='rejected',reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?",(u["id"],now_iso(),x.note,rid));c.commit()
    audit(u["id"],"revision_reject",str(rid))
    return {"ok":True}

@app.get("/api/projects/{project_id}/traceability")
def project_traceability(project_id:int,u=Depends(user)):
    with conn() as c:
        project=c.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()
        if not project:raise HTTPException(404,"Proje bulunamadı")
        calcs=c.execute("SELECT * FROM calculations WHERE project_id=? ORDER BY id",(project_id,)).fetchall()
        out=[]
        for calc in calcs:
            rev=c.execute("""SELECT r.*,creator.display_name creator_name,reviewer.display_name reviewer_name
                             FROM calculation_revisions r
                             LEFT JOIN users creator ON creator.id=r.created_by
                             LEFT JOIN users reviewer ON reviewer.id=r.reviewed_by
                             WHERE r.calculation_id=? ORDER BY r.revision_no DESC LIMIT 1""",(calc["id"],)).fetchone()
            traces=c.execute("SELECT dataset,version_no,package_no FROM calculation_data_trace WHERE calculation_id=? ORDER BY dataset",(calc["id"],)).fetchall()
            row=dict(calc)
            row.update({
              "revision_no":rev["revision_no"] if rev else None,
              "revision_status":rev["status"] if rev else None,
              "creator_name":rev["creator_name"] if rev else None,
              "reviewer_name":rev["reviewer_name"] if rev else None,
              "reviewed_at":rev["reviewed_at"] if rev else None,
              "data_versions":[dict(t) for t in traces]
            })
            out.append(row)
    return out

@app.get("/api/projects/{project_id}/release-package")
def project_release_package(project_id:int,title:str="Bağlantı Elemanları Tork Doğrulama Raporu",u=Depends(user)):
    with conn() as c:
        project=c.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()
        if not project:raise HTTPException(404,"Proje bulunamadı")
    trace=project_traceability(project_id,u)
    items=[]
    approved=0
    open_count=0
    for x in trace:
        versions=x.get("data_versions",[])
        signature="|".join(f"{v['dataset']}:{v['version_no']}" for v in versions) if versions else None
        if x.get("revision_status")=="approved":approved+=1
        else:open_count+=1
        items.append({
          "calculation_id":x["id"],"record_no":x["record_no"],"standard":x["standard"],"thread":x["thread"],
          "property_class":x["property_class"],"torque_nm":x["torque_nm"],"preload_n":x["preload_n"],
          "revision_no":x.get("revision_no"),"revision_status":x.get("revision_status"),
          "reviewer_name":x.get("reviewer_name"),"reviewed_at":x.get("reviewed_at"),
          "version_signature":signature
        })
    total=len(items)
    release_ready=total>0 and approved==total
    decision="PROJE RELEASE İÇİN HAZIR" if release_ready else "AÇIK VEYA ONAYSIZ HESAPLAR BULUNUYOR"
    no="PRP-"+utcnow().strftime("%Y%m%d-%H%M%S-%f")
    payload={
      "package_no":no,"title":title,"created_at":now_iso(),"project":dict(project),
      "summary":{"total_calculations":total,"approved_revisions":approved,"open_revisions":open_count,"release_ready":release_ready},
      "decision":decision,"items":items
    }
    with conn() as c:
        c.execute("INSERT INTO project_release_packages(package_no,project_id,title,payload_json,release_ready,decision,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (no,project_id,title,json.dumps(payload,ensure_ascii=False),1 if release_ready else 0,decision,u["id"],payload["created_at"]))
        c.commit()
    audit(u["id"],"project_release_package_create",no)
    return payload

@app.get("/api/projects/{project_id}/release-packages")
def list_release_packages(project_id:int,u=Depends(user)):
    with conn() as c:rows=c.execute("SELECT id,package_no,title,release_ready,decision,created_at FROM project_release_packages WHERE project_id=? ORDER BY id DESC",(project_id,)).fetchall()
    return [dict(r) for r in rows]

class OrganizationIn(BaseModel):
    name:Optional[str]=None
    code:Optional[str]=None
    contact:Optional[str]=None
    email:Optional[str]=None
    report_title:Optional[str]=None
    logo:Optional[str]=None
    footer:Optional[str]=None

class LicenseActivateIn(BaseModel):
    license_key:str

def license_payload_from_key(key:str):
    clean=key.strip().upper()
    demo_keys={
      "TP-ENTERPRISE-2027":{"plan":"Enterprise","expires_at":"2027-12-31T23:59:59+00:00","max_users":100,"max_projects":1000,
                            "modules":["calculation","projects","reports","standards","calibration","approval","release","audit"]},
      "TP-PRO-2027":{"plan":"Professional","expires_at":"2027-12-31T23:59:59+00:00","max_users":20,"max_projects":100,
                     "modules":["calculation","projects","reports","approval","release"]},
      "TP-TRIAL-90":{"plan":"Trial","expires_at":(utcnow()+timedelta(days=90)).isoformat(),"max_users":3,"max_projects":5,
                     "modules":["calculation","projects","reports"]}
    }
    return demo_keys.get(clean)

def current_license():
    with conn() as c:r=c.execute("SELECT * FROM license_info WHERE id=1").fetchone()
    if not r:return {"active":False,"modules":[]}
    d=dict(r);d["modules"]=json.loads(d.pop("modules_json") or "[]")
    if d.get("expires_at"):
        try:d["active"]=bool(d["active"]) and datetime.fromisoformat(d["expires_at"])>utcnow()
        except Exception:d["active"]=False
    else:d["active"]=bool(d["active"])
    return d

@app.get("/api/admin/organization")
def get_organization(u=Depends(admin)):
    with conn() as c:r=c.execute("SELECT * FROM organization_settings WHERE id=1").fetchone()
    return dict(r) if r else {}

@app.put("/api/admin/organization")
def update_organization(x:OrganizationIn,u=Depends(admin)):
    with conn() as c:
        c.execute("""INSERT INTO organization_settings(id,name,code,contact,email,report_title,logo,footer,updated_by,updated_at)
                     VALUES(1,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(id) DO UPDATE SET name=excluded.name,code=excluded.code,contact=excluded.contact,email=excluded.email,
                     report_title=excluded.report_title,logo=excluded.logo,footer=excluded.footer,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                  (x.name,x.code,x.contact,x.email,x.report_title,x.logo,x.footer,u["id"],now_iso()))
        c.commit()
    audit(u["id"],"organization_update",x.name or "")
    return {"ok":True}

@app.get("/api/admin/license")
def get_license(u=Depends(admin)):
    return current_license()

@app.post("/api/admin/license/activate")
def activate_license(x:LicenseActivateIn,u=Depends(admin)):
    payload=license_payload_from_key(x.license_key)
    if not payload:raise HTTPException(400,"Geçersiz aktivasyon kodu")
    h=hashlib.sha256(x.license_key.strip().upper().encode()).hexdigest()
    with conn() as c:
        c.execute("""INSERT INTO license_info(id,license_key_hash,plan,expires_at,max_users,max_projects,modules_json,active,activated_by,activated_at)
                     VALUES(1,?,?,?,?,?,?,1,?,?)
                     ON CONFLICT(id) DO UPDATE SET license_key_hash=excluded.license_key_hash,plan=excluded.plan,expires_at=excluded.expires_at,
                     max_users=excluded.max_users,max_projects=excluded.max_projects,modules_json=excluded.modules_json,active=1,
                     activated_by=excluded.activated_by,activated_at=excluded.activated_at""",
                  (h,payload["plan"],payload["expires_at"],payload["max_users"],payload["max_projects"],json.dumps(payload["modules"]),u["id"],now_iso()))
        c.commit()
    audit(u["id"],"license_activate",payload["plan"])
    return {"ok":True}

@app.get("/api/admin/usage-summary")
def usage_summary(u=Depends(admin)):
    lic=current_license()
    with conn() as c:
        users=c.execute("SELECT COUNT(*) c FROM users WHERE is_active=1").fetchone()["c"]
        projects=c.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
        calculations=c.execute("SELECT COUNT(*) c FROM calculations").fetchone()["c"]
        releases=c.execute("SELECT COUNT(*) c FROM project_release_packages").fetchone()["c"]
    return {"users":users,"projects":projects,"calculations":calculations,"release_packages":releases,
            "max_users":lic.get("max_users",0),"max_projects":lic.get("max_projects",0),"license_active":lic.get("active",False)}


class DeploymentProfileIn(BaseModel):
    environment:str
    install_type:str
    host:str
    port:int=Field(ge=1,le=65535)
    backup_frequency:str
    update_channel:str

class SystemImportIn(BaseModel):
    content:str

EXPORT_TABLES=["organization_settings","license_info","deployment_profile","users","projects","calculations",
               "calculation_revisions","calculation_data_trace","data_packages","data_versions","golden_cases",
               "release_certificates","project_release_packages"]

@app.get("/api/admin/deployment-profile")
def get_deployment_profile(u=Depends(admin)):
    with conn() as c:r=c.execute("SELECT * FROM deployment_profile WHERE id=1").fetchone()
    return dict(r) if r else {}

@app.put("/api/admin/deployment-profile")
def update_deployment_profile(x:DeploymentProfileIn,u=Depends(admin)):
    if x.install_type not in ("standalone","lan","cloud"):raise HTTPException(400,"Geçersiz kurulum tipi")
    if x.backup_frequency not in ("daily","weekly","manual"):raise HTTPException(400,"Geçersiz yedekleme sıklığı")
    if x.update_channel not in ("stable","pilot","offline"):raise HTTPException(400,"Geçersiz güncelleme kanalı")
    with conn() as c:
        c.execute("""INSERT INTO deployment_profile(id,environment,install_type,host,port,backup_frequency,update_channel,updated_by,updated_at)
                     VALUES(1,?,?,?,?,?,?,?,?)
                     ON CONFLICT(id) DO UPDATE SET environment=excluded.environment,install_type=excluded.install_type,
                     host=excluded.host,port=excluded.port,backup_frequency=excluded.backup_frequency,
                     update_channel=excluded.update_channel,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                  (x.environment,x.install_type,x.host,x.port,x.backup_frequency,x.update_channel,u["id"],now_iso()))
        c.commit()
    audit(u["id"],"deployment_profile_update",x.environment);return {"ok":True}

def build_system_export():
    payload={"format":"torqpro-system-export","schema_version":SCHEMA_VERSION,"app_version":APP_VERSION,"created_at":now_iso(),"tables":{}}
    total=0
    with conn() as c:
        for table in EXPORT_TABLES:
            try:rows=[dict(r) for r in c.execute(f"SELECT * FROM {table}").fetchall()]
            except Exception:rows=[]
            payload["tables"][table]=rows;total+=len(rows)
    payload["record_count"]=total
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True)
    payload["checksum"]=hashlib.sha256(raw.encode()).hexdigest()
    return payload

@app.post("/api/admin/system-export")
def system_export(u=Depends(admin)):
    payload=build_system_export()
    no="EXP-"+utcnow().strftime("%Y%m%d-%H%M%S-%f")
    payload["export_no"]=no
    with conn() as c:
        c.execute("INSERT INTO migration_history(operation_no,operation_type,status,checksum,table_count,record_count,created_by,created_at) VALUES(?,?,'completed',?,?,?,?,?)",
                  (no,"export",payload["checksum"],len(payload["tables"]),payload["record_count"],u["id"],now_iso()));c.commit()
    audit(u["id"],"system_export",no);return payload

@app.post("/api/admin/system-import")
def system_import(x:SystemImportIn,u=Depends(admin)):
    try:payload=json.loads(x.content)
    except Exception as exc:raise HTTPException(400,f"JSON hatası: {exc}")
    if payload.get("format")!="torqpro-system-export":raise HTTPException(400,"Geçersiz TorqPro taşıma paketi")
    tables=payload.get("tables")
    if not isinstance(tables,dict):raise HTTPException(400,"Tablo bölümü eksik")
    raw=dict(payload);given=raw.pop("checksum",None);raw.pop("export_no",None)
    calc=hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    if given and given!=calc:raise HTTPException(400,"Paket bütünlük kontrolü başarısız")
    unknown=[t for t in tables if t not in EXPORT_TABLES]
    if unknown:raise HTTPException(400,"Desteklenmeyen tablolar: "+",".join(unknown))
    # Safety: validate only, no destructive overwrite in this release.
    total=sum(len(v) for v in tables.values() if isinstance(v,list))
    no="IMP-"+utcnow().strftime("%Y%m%d-%H%M%S-%f")
    with conn() as c:
        c.execute("INSERT INTO migration_history(operation_no,operation_type,status,checksum,table_count,record_count,created_by,created_at) VALUES(?,?,'validated',?,?,?,?,?)",
                  (no,"import",given or calc,len(tables),total,u["id"],now_iso()));c.commit()
    audit(u["id"],"system_import_validate",no)
    return {"ok":True,"import_no":no,"status":"validated","table_count":len(tables),"record_count":total,
            "note":"Güvenlik nedeniyle bu sürüm içe aktarma paketini doğrular; mevcut veriyi otomatik olarak ezmez."}

@app.get("/api/admin/migration-history")
def migration_history(u=Depends(admin)):
    with conn() as c:r=c.execute("SELECT * FROM migration_history ORDER BY id DESC LIMIT 100").fetchall()
    return [dict(x) for x in r]

@app.get("/api/admin/diagnostics")
def diagnostics(u=Depends(admin)):
    checks=[]
    def add(name,value,ok,detail=""):checks.append({"name":name,"value":value,"ok":bool(ok),"detail":detail})
    add("Uygulama sürümü",APP_VERSION,True)
    add("Python sürümü",platform.python_version(),True)
    add("İşletim sistemi",platform.platform(),True)
    add("Veritabanı dosyası",str(DB),DB.exists())
    try:
        size=DB.stat().st_size if DB.exists() else 0
        add("Veritabanı boyutu",size,True,f"{size/1024/1024:.2f} MB")
    except Exception as exc:add("Veritabanı boyutu","—",False,str(exc))
    try:
        with conn() as c:
            integrity=c.execute("PRAGMA integrity_check").fetchone()[0]
            tables=c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        add("SQLite bütünlüğü",integrity,integrity=="ok")
        add("Tablo sayısı",tables,tables>0)
    except Exception as exc:add("SQLite bağlantısı","—",False,str(exc))
    lic=current_license();add("Lisans",lic.get("plan","—"),lic.get("active",False),"Aktif" if lic.get("active") else "Pasif veya süresi dolmuş")
    with conn() as c:
        active_versions=c.execute("SELECT COUNT(*) FROM data_versions WHERE is_active=1").fetchone()[0]
        users=c.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
    add("Aktif veri sürümleri",active_versions,active_versions>=0)
    add("Aktif kullanıcılar",users,users>0)
    overall=all(c["ok"] for c in checks if c["name"] not in ("Lisans",))
    return {"generated_at":now_iso(),"overall_ok":overall,"checks":checks}


def detect_local_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect(("8.8.8.8",80))
        ip=s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@app.get("/manifest.webmanifest")
def pwa_manifest():
    return FileResponse(FRONT/"manifest.webmanifest",media_type="application/manifest+json")

@app.get("/service-worker.js")
def pwa_service_worker():
    return FileResponse(FRONT/"service-worker.js",media_type="application/javascript")

@app.get("/api/mobile/access-info")
def mobile_access_info(u=Depends(user)):
    with conn() as c:r=c.execute("SELECT * FROM deployment_profile WHERE id=1").fetchone()
    profile=dict(r) if r else {}
    port=profile.get("port") or 8000
    ip=detect_local_ip()
    checks=[
      {"name":"Yerel IP","value":ip,"ok":ip!="127.0.0.1"},
      {"name":"Port","value":port,"ok":1<=int(port)<=65535},
      {"name":"Kurulum Tipi","value":profile.get("install_type","standalone"),"ok":True},
      {"name":"PWA Manifest","value":"Hazır","ok":(FRONT/"manifest.webmanifest").exists()},
      {"name":"Service Worker","value":"Hazır","ok":(FRONT/"service-worker.js").exists()}
    ]
    return {"host":ip,"port":port,"local_url":f"http://{ip}:{port}","pwa_ready":all(c["ok"] for c in checks[-2:]),"checks":checks}


@app.get("/api/runtime/status")
def runtime_status():
    db_ok=False
    active_count=0
    try:
        with conn() as c:
            c.execute("SELECT 1").fetchone()
            db_ok=True
            active_count=c.execute("SELECT COUNT(*) FROM data_versions WHERE is_active=1").fetchone()[0]
    except Exception:
        db_ok=False
    lic=current_license()
    readiness=db_ok and bool(os.environ.get("TORQPRO_SECRET_KEY"))
    return {
      "app":"TorqPro","version":APP_VERSION,"liveness":True,"readiness":readiness,
      "database":"OK" if db_ok else "ERROR",
      "license":"ACTIVE" if lic.get("active") else "INACTIVE",
      "active_datasets":active_count
    }

@app.get("/health/live")
def health_live():
    return {"status":"ok","service":"torqpro"}

@app.get("/health/ready")
def health_ready():
    try:
        with conn() as c:c.execute("SELECT 1").fetchone()
        secret_ok=bool(os.environ.get("TORQPRO_SECRET_KEY"))
        if not secret_ok:raise HTTPException(503,"TORQPRO_SECRET_KEY missing")
        return {"status":"ready","database":"ok","secret":"configured"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503,f"Database not ready: {exc}")

@app.get("/api/admin/cloud-readiness")
def cloud_readiness(u=Depends(admin)):
    secret_ok=bool(os.environ.get("TORQPRO_SECRET_KEY"))
    db_ok=DB.exists()
    docker_ok=(BASE/"Dockerfile").exists() and (BASE/"docker-compose.yml").exists()
    proxy_ok=(BASE/"deploy"/"nginx.conf").exists()
    env_ok=(BASE/".env.example").exists()
    checks=[
      {"name":"Dockerfile","value":"Mevcut" if (BASE/"Dockerfile").exists() else "Eksik","ok":(BASE/"Dockerfile").exists()},
      {"name":"Docker Compose","value":"Mevcut" if (BASE/"docker-compose.yml").exists() else "Eksik","ok":(BASE/"docker-compose.yml").exists()},
      {"name":"Reverse Proxy","value":"Nginx","ok":proxy_ok},
      {"name":"Ortam Değişkeni Şablonu","value":".env.example","ok":env_ok},
      {"name":"Secret Key","value":"Yapılandırılmış" if secret_ok else "Eksik","ok":secret_ok},
      {"name":"Veritabanı","value":"Mevcut" if db_ok else "İlk çalıştırmada oluşur","ok":True}
    ]
    return {"ready":all(c["ok"] for c in checks),"checks":checks}


class GoLiveProfileIn(BaseModel):
    server_ip:Optional[str]=None
    domain:Optional[str]=None
    https_status:str="planned"

@app.get("/api/admin/golive-profile")
def get_golive_profile(u=Depends(admin)):
    with conn() as c:r=c.execute("SELECT * FROM golive_profile WHERE id=1").fetchone()
    return dict(r) if r else {}

@app.put("/api/admin/golive-profile")
def update_golive_profile(x:GoLiveProfileIn,u=Depends(admin)):
    if x.https_status not in ("planned","ready"):raise HTTPException(400,"Geçersiz HTTPS durumu")
    dns_planned=1 if x.domain else 0
    docker_ready=1 if (BASE/"Dockerfile").exists() and (BASE/"docker-compose.yml").exists() else 0
    try:
        with conn() as c:c.execute("SELECT 1").fetchone()
        health_ready=1 if os.environ.get("TORQPRO_SECRET_KEY") else 0
    except Exception:health_ready=0
    with conn() as c:
        c.execute("""INSERT INTO golive_profile(id,server_ip,domain,https_status,dns_planned,docker_ready,health_ready,updated_by,updated_at)
                     VALUES(1,?,?,?,?,?,?,?,?)
                     ON CONFLICT(id) DO UPDATE SET server_ip=excluded.server_ip,domain=excluded.domain,https_status=excluded.https_status,
                     dns_planned=excluded.dns_planned,docker_ready=excluded.docker_ready,health_ready=excluded.health_ready,
                     updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                  (x.server_ip,x.domain,x.https_status,dns_planned,docker_ready,health_ready,u["id"],now_iso()))
        c.commit();r=c.execute("SELECT * FROM golive_profile WHERE id=1").fetchone()
    return dict(r)

@app.get("/api/admin/dns-check")
def dns_check(domain:str,expected_ip:str="",u=Depends(admin)):
    try:
        infos=socket.getaddrinfo(domain,None)
        ips=sorted({i[4][0] for i in infos if i and i[4]})
    except Exception as exc:
        raise HTTPException(400,f"DNS çözümleme başarısız: {exc}")
    matches=(expected_ip in ips) if expected_ip else bool(ips)
    with conn() as c:p=c.execute("SELECT * FROM golive_profile WHERE id=1").fetchone()
    https_ready=bool(p and p["https_status"]=="ready")
    return {"domain":domain,"resolved_ips":ips,"expected_ip":expected_ip,"matches_expected":matches,
            "https_ready":https_ready,"status":"YAYINA HAZIR" if matches and https_ready else "EKSİKLER VAR"}

@app.get("/")
def root():return FileResponse(FRONT/"index.html")
app.mount("/",StaticFiles(directory=FRONT,html=True),name="frontend")
