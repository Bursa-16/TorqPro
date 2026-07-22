"""Independent FastAPI auth dependency module.

Extracted from backend/app.py so that route modules (e.g.
backend/api/routes/production_validation.py) do not need to import
anything from backend.app at module load time. backend.app imports
`user` back from here to preserve its existing behaviour unchanged.

Import of backend.app internals (conn/SECRET_KEY/ALGORITHM) is deferred
to inside the function body on purpose: backend.app is what imports this
module's *callers* (both app.py itself and the API route modules it
includes), so a module-level `from backend.app import ...` here would
recreate the same circular-import failure this module exists to avoid.
By the time `user()` actually runs (per-request), backend.app is always
fully initialized, so the deferred import is safe and behaves exactly
like the previous in-line implementation.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException


def user(authorization: str = Header(default="")):
    from backend.app import SECRET_KEY, ALGORITHM, conn
    import jwt

    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Oturum gerekli")
    try:
        p = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
        uid = int(p["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Geçersiz veya süresi dolmuş oturum")
    with conn() as c:
        r = c.execute(
            "SELECT id,username,display_name,is_active,role FROM users WHERE id=?", (uid,)
        ).fetchone()
    if not r or not r["is_active"]:
        raise HTTPException(401, "Kullanıcı aktif değil")
    return dict(r)


def admin(u=Depends(user)):
    if u["role"] != "admin":
        raise HTTPException(403, "Yönetici yetkisi gerekli")
    return u
