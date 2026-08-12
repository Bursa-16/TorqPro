"""v3.0.0-rc.1 Security Hardening Phase 2 -- targeted regression tests.

Covers the three implementation items from this phase (B7 -- CI/
dependency scanning -- has no application-level behavior to test and
is validated directly via ``pip-audit`` in the final report instead):

* B4 -- general API rate limiting, opt-in via
  ``TORQPRO_API_RATE_LIMIT="<max>/<window_seconds>"``. Default
  (unset, as in the rest of this suite): unchanged behavior, no
  limiting at all. When enabled: a centralized, per-Authorization-
  header sliding-window limiter applied to ``/api/...`` paths, always
  excluding ``/api/login`` (which keeps its own separate, stricter,
  per-username limiter) and ``/api/health``.
* B5 -- Content-Security-Policy (always present, ``'unsafe-inline'``
  for script-src/style-src because ``frontend/index.html`` is a
  single-file SPA with one inline ``<script>`` block and ~220 inline
  ``style="..."`` attributes -- see the middleware's own comment in
  ``backend/app.py`` for the full rationale) and
  Strict-Transport-Security (only when ``TORQPRO_ENV=production``,
  reusing the same flag B2 already introduced).
* B6 -- regression tests for the four exception-detail-leakage fixes
  made in this phase: ``GET /health/ready``,
  ``GET /api/engineering/bolt-strength-classes``,
  ``GET /api/engineering/nut-property-classes``, and
  ``POST /api/engineering/bolt-nut-compatibility``. Each now returns a
  fixed, generic message instead of interpolating the raw exception
  text into the response body.

B4 depends on module-level state fixed at ``backend.app`` import time
(the rate-limiting middleware itself is only registered at all when
``TORQPRO_API_RATE_LIMIT`` is set), so -- like B1/B2 in Phase 1 -- it
is verified in a fresh child process. B5's CSP/HSTS split
(HSTS depends on ``TORQPRO_ENV``, CSP does not) is verified the same
way for the production-only assertions, and directly against the
already-imported session ``client`` fixture for the always-on CSP/
X-Content-Type-Options/X-Frame-Options/Referrer-Policy assertions
(unaffected by env, so no fresh process is needed there). B6 uses the
existing shared ``client``/``auth_headers`` fixtures.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_in_fresh_process(script: str, tmp_path, extra_env: dict | None = None):
    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(tmp_path / f"rc1_sec_p2_{uuid.uuid4().hex[:8]}.db")
    env.pop("TORQPRO_ALLOWED_HOSTS", None)
    env.pop("TORQPRO_ENV", None)
    env.pop("TORQPRO_API_RATE_LIMIT", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------
# B4 -- general API rate limiting
# ---------------------------------------------------------------------


def test_parse_rate_limit_valid_value():
    from backend.app import _parse_rate_limit

    assert _parse_rate_limit("300/60") == (300, 60.0)


@pytest.mark.parametrize("raw", [None, "", "   ", "not-a-number", "300", "0/60", "300/0", "-1/60"])
def test_parse_rate_limit_edge_cases_return_none(raw):
    from backend.app import _parse_rate_limit

    assert _parse_rate_limit(raw) is None


def test_rate_limit_disabled_by_default_unchanged_behavior(tmp_path):
    """TORQPRO_API_RATE_LIMIT unset (the default, and this suite's own
    environment): no middleware attached, no request is ever limited,
    regardless of volume."""
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r = c.post('/api/login', json={'username': 'Protype Lab', 'password': 'A1234'}); "
        "assert r.status_code == 200, r.text; "
        "token = r.json()['token']; headers = {'Authorization': 'Bearer ' + token}; "
        "statuses = [c.get('/api/calculations', headers=headers).status_code for _ in range(20)]; "
        "print('STATUSES', set(statuses))"
    )
    result = _run_in_fresh_process(script, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUSES {200}" in result.stdout


def test_rate_limit_enabled_returns_429_over_threshold(tmp_path):
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r = c.post('/api/login', json={'username': 'Protype Lab', 'password': 'A1234'}); "
        "assert r.status_code == 200, r.text; "
        "token = r.json()['token']; headers = {'Authorization': 'Bearer ' + token}; "
        "statuses = [c.get('/api/calculations', headers=headers).status_code for _ in range(5)]; "
        "print('STATUSES', statuses)"
    )
    # Threshold of 3 requests / 60s window -- the 4th and 5th calls
    # (same token, same process, well inside the window) must be
    # rejected with 429.
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_API_RATE_LIMIT": "3/60"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUSES [200, 200, 200, 429, 429]" in result.stdout


def test_rate_limit_different_tokens_are_independent_buckets(tmp_path):
    """Two different authenticated sessions must not share a bucket --
    one user hitting the limit must not affect another."""
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r = c.post('/api/login', json={'username': 'Protype Lab', 'password': 'A1234'}); "
        "assert r.status_code == 200, r.text; "
        "token = r.json()['token']; headers = {'Authorization': 'Bearer ' + token}; "
        "r2 = c.post('/api/admin/users', headers=headers, json={"
        "'username': 'rc1sec_p2_ratelimit', 'display_name': 'RL User', "
        "'password': 'Rc1SecRate1', 'role': 'engineer'}); "
        "assert r2.status_code == 200, r2.text; "
        "r3 = c.post('/api/login', json={'username': 'rc1sec_p2_ratelimit', 'password': 'Rc1SecRate1'}); "
        "assert r3.status_code == 200, r3.text; "
        "other_headers = {'Authorization': 'Bearer ' + r3.json()['token']}; "
        "owner_statuses = [c.get('/api/calculations', headers=headers).status_code for _ in range(3)]; "
        "other_status = c.get('/api/calculations', headers=other_headers).status_code; "
        "print('OWNER', owner_statuses, 'OTHER', other_status)"
    )
    # Threshold of 4/60: owner_headers (admin token) makes exactly 4
    # rate-limited requests in this script (1 POST /api/admin/users to
    # create the second user, then 3 GET /api/calculations) -- all
    # must succeed. A completely different token (the freshly created
    # second user) must independently get 200 on its own first call,
    # proving the two are separate buckets rather than one shared one.
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_API_RATE_LIMIT": "4/60"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OWNER [200, 200, 200] OTHER 200" in result.stdout


def test_rate_limit_enabled_does_not_affect_login_endpoint(tmp_path):
    """/api/login is exempt from the general limiter -- it keeps only
    its own, separate, stricter per-username limiter (5 failed
    attempts / 300s). A tight general-API threshold must not make
    /api/login itself start returning 429 for legitimate repeated
    (successful) login calls."""
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "statuses = [c.post('/api/login', json={'username': 'Protype Lab', 'password': 'A1234'}).status_code for _ in range(5)]; "
        "print('STATUSES', statuses)"
    )
    # Threshold of 1/60 -- if /api/login were subject to the general
    # limiter, every call after the first would be 429. It must not
    # be: all 5 succeed.
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_API_RATE_LIMIT": "1/60"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUSES [200, 200, 200, 200, 200]" in result.stdout


def test_rate_limit_enabled_does_not_affect_health_endpoint(tmp_path):
    """/api/health is exempt -- a public, side-effect-free liveness
    check must not be throttled by the general API limiter."""
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "statuses = [c.get('/api/health').status_code for _ in range(5)]; "
        "print('STATUSES', statuses)"
    )
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_API_RATE_LIMIT": "1/60"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUSES [200, 200, 200, 200, 200]" in result.stdout


# ---------------------------------------------------------------------
# B5 -- Content-Security-Policy / Strict-Transport-Security
# ---------------------------------------------------------------------


def test_csp_present_with_unsafe_inline_for_script_and_style(client):
    """CSP is always present (not env-gated, unlike HSTS) -- and must
    explicitly allow inline script/style, since frontend/index.html's
    single inline <script> block and ~220 inline style="..."
    attributes would otherwise be blocked outright."""
    r = client.get("/api/health")
    csp = r.headers.get("content-security-policy")
    assert csp is not None
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_existing_security_headers_unchanged(client):
    """X-Content-Type-Options / X-Frame-Options / Referrer-Policy must
    still be exactly what they were before this phase."""
    r = client.get("/api/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_hsts_absent_when_torqpro_env_unset(client):
    """Default/dev/test (this suite's own environment): no HSTS --
    sending it over a plain HTTP/localhost connection would be
    misleading."""
    r = client.get("/api/health")
    assert "strict-transport-security" not in {k.lower() for k in r.headers.keys()}


def test_hsts_present_only_when_torqpro_env_is_production(tmp_path):
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r = c.get('/api/health'); "
        "print('HSTS', r.headers.get('strict-transport-security'))"
    )
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ENV": "production"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HSTS max-age=31536000; includeSubDomains" in result.stdout


def test_hsts_still_absent_for_non_production_env_value(tmp_path):
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r = c.get('/api/health'); "
        "print('HSTS', r.headers.get('strict-transport-security'))"
    )
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ENV": "staging"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HSTS None" in result.stdout


def test_csp_present_even_in_production_alongside_hsts(tmp_path):
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r = c.get('/api/health'); "
        "csp = r.headers.get('content-security-policy'); "
        "hsts = r.headers.get('strict-transport-security'); "
        "print('CSP_OK', csp is not None and \"unsafe-inline\" in csp); "
        "print('HSTS_OK', hsts is not None)"
    )
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ENV": "production"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CSP_OK True" in result.stdout
    assert "HSTS_OK True" in result.stdout


def test_normal_api_and_frontend_responses_unaffected_by_headers(client, auth_headers):
    """Adding CSP/HSTS must not change status codes or bodies of
    ordinary API/frontend responses."""
    r_root = client.get("/")
    assert r_root.status_code == 200
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] in ("ok", "degraded")
    r_calc = client.get("/api/calculations", headers=auth_headers)
    assert r_calc.status_code == 200


# ---------------------------------------------------------------------
# B6 -- exception detail leakage: regression tests for the four fixes
# ---------------------------------------------------------------------


def test_health_ready_does_not_leak_raw_exception_text(tmp_path):
    """Force a real failure (invalid TORQPRO_DB_PATH pointing at a
    directory that cannot hold a SQLite file) and confirm the 503
    body is the fixed generic message, not an interpolated raw
    exception (which could include a filesystem path or sqlite3
    driver internals)."""
    bad_db_dir = tmp_path / "not_a_file_dir"
    bad_db_dir.mkdir()
    script = (
        "from backend.app import app; "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r = c.get('/health/ready'); "
        "print('STATUS', r.status_code); "
        "print('BODY', r.json())"
    )
    # Point TORQPRO_DB_PATH at a directory (not a file) so sqlite3
    # connect/execute fails inside health_ready()'s try block --
    # deliberately not calling migrate() here, so the very first
    # `conn()` use inside the route itself is what fails.
    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(bad_db_dir)
    env.pop("TORQPRO_ALLOWED_HOSTS", None)
    env.pop("TORQPRO_ENV", None)
    env.pop("TORQPRO_API_RATE_LIMIT", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 503" in result.stdout
    assert "'detail': 'Database not ready'" in result.stdout
    # The fixed message must not contain the directory path, "sqlite3",
    # or any other internal detail that str(exc) would have included.
    assert str(bad_db_dir) not in result.stdout
    assert "sqlite3" not in result.stdout.lower()


def test_bolt_strength_classes_filter_error_does_not_leak_exception_text(client, auth_headers, monkeypatch):
    """Force list_bolt_strength_classes() to raise, and confirm the
    400 body is the fixed generic message, not str(exc)."""
    import backend.library.strength_classes as strength_classes_module

    def _boom(*args, **kwargs):
        raise RuntimeError("internal parsing failure at /some/internal/path.json line 42")

    monkeypatch.setattr(strength_classes_module, "list_bolt_strength_classes", _boom)

    r = client.get("/api/engineering/bolt-strength-classes", headers=auth_headers)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Geçersiz filtre parametreleri"
    assert "internal parsing failure" not in r.text
    assert "/some/internal/path.json" not in r.text


def test_nut_property_classes_filter_error_does_not_leak_exception_text(client, auth_headers, monkeypatch):
    import backend.library.strength_classes as strength_classes_module

    def _boom(*args, **kwargs):
        raise RuntimeError("internal parsing failure at /some/internal/path.json line 42")

    monkeypatch.setattr(strength_classes_module, "list_nut_property_classes", _boom)

    r = client.get("/api/engineering/nut-property-classes", headers=auth_headers)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Geçersiz filtre parametreleri"
    assert "internal parsing failure" not in r.text
    assert "/some/internal/path.json" not in r.text


def test_bolt_nut_compatibility_error_does_not_leak_exception_text(client, auth_headers, monkeypatch):
    import backend.library.strength_compatibility as strength_compat_module

    def _boom(*args, **kwargs):
        raise RuntimeError("internal parsing failure at /some/internal/path.json line 42")

    monkeypatch.setattr(strength_compat_module, "check_bolt_nut_strength_compatibility", _boom)

    r = client.post(
        "/api/engineering/bolt-nut-compatibility",
        headers=auth_headers,
        json={"bolt_strength_class": "8.8", "nut_property_class": "8"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Uyumluluk kontrolü yapılamadı"
    assert "internal parsing failure" not in r.text
    assert "/some/internal/path.json" not in r.text


def test_bolt_strength_classes_normal_success_path_unaffected(client, auth_headers):
    """Non-regression: the fix only changes the error path -- a normal
    successful call must behave exactly as before."""
    r = client.get("/api/engineering/bolt-strength-classes", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_bolt_strength_class_unknown_designation_404_unaffected(client, auth_headers):
    """Non-regression: the pre-existing, intentional 404-for-unknown-
    designation path (a different route, untouched by this phase) is
    unaffected."""
    r = client.get(
        "/api/engineering/bolt-strength-classes/__definitely_unknown__", headers=auth_headers
    )
    assert r.status_code == 404, r.text


def test_health_ready_normal_success_path_unaffected(client):
    r = client.get("/health/ready")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready"
