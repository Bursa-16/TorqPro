"""Centralized version source (VERSION file) for backend + frontend.

Scope:
- A single `VERSION` file at the repo root is the only place the
  application version is defined.
- `backend.app.APP_VERSION` reads it (no hardcoded literal).
- `/api/health` (unauthenticated) reports the same value.
- `frontend/index.html` contains no hardcoded old version string and
  fetches the version dynamically from `/api/health` instead of
  hardcoding a new one.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

from fastapi.testclient import TestClient  # noqa: E402

import backend.app as app_module  # noqa: E402
from backend.app import app  # noqa: E402

client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"


def test_version_file_exists_and_is_2_6_6():
    assert VERSION_FILE.exists()
    assert VERSION_FILE.read_text(encoding="utf-8").strip() == "2.6.6"


def test_backend_app_version_matches_version_file():
    assert app_module.APP_VERSION == VERSION_FILE.read_text(encoding="utf-8").strip()
    assert app_module.APP_VERSION == "2.6.6"


def test_backend_app_version_is_not_hardcoded_literal():
    """Guard against regressing to a hardcoded string: the source
    line assigning APP_VERSION must call the file-reading helper, not
    a literal."""
    source = (REPO_ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION="4.4"' not in source
    assert 'APP_VERSION = "4.4"' not in source
    assert "APP_VERSION=_read_app_version()" in source or \
        "APP_VERSION = _read_app_version()" in source


def test_health_endpoint_reports_same_version_unauthenticated():
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    assert r.json()["version"] == "2.6.6"


def test_fastapi_app_title_version_matches():
    """The FastAPI app object itself (used for e.g. OpenAPI docs) is
    also constructed with the same single-source version."""
    assert app.version == "2.6.6"


# ---------------------------------------------------------------------
# Frontend: no hardcoded old version, dynamic fetch present
# ---------------------------------------------------------------------

def test_frontend_has_no_hardcoded_v4_4():
    html = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "v4.4" not in html
    assert "v4.5" not in html


def test_frontend_has_no_hardcoded_version_in_title_or_login_or_topbar():
    html = FRONTEND_PATH.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert not re.search(r"v\d", title)
    login_sub = re.search(r'<div class="login-sub">(.*?)</div>', html).group(1)
    assert not re.search(r"v\d", login_sub)  # only the id="login-version" placeholder, no literal
    logo = re.search(r'<div class="logo">(.*?)</div>', html).group(1)
    assert not re.search(r"v\d", logo)


def test_frontend_fetches_version_from_api_health():
    html = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "fetch('/api/health')" in html
    assert "loadAppVersion" in html
    assert 'id="login-version"' in html
    assert 'id="topbar-version"' in html


def test_frontend_js_syntax_valid_after_version_change(tmp_path):
    import subprocess

    scripts = re.findall(r"<script>(.*?)</script>", FRONTEND_PATH.read_text(encoding="utf-8"), re.S)
    assert scripts
    js_file = tmp_path / "extracted.js"
    js_file.write_text("\n;\n".join(scripts), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
