"""Faz Stage 2 -- System Health visibility & backend authorization.

Scope: guards against the concrete gap this stage fixed (GET
/api/runtime/status was reachable without authentication and returned
a record count, license status, and env-config presence) and locks in
the existing, already-correct authorization posture of GET /api/health
and GET /api/admin/system so neither regresses.

Uses the repository's existing shared fixtures (tests/conftest.py):
``client`` (session TestClient), ``auth_headers`` (default admin
bearer token), ``login_as`` (factory to authenticate as an arbitrary
user). No independent role table, role constant, or alternate
authorization path is introduced anywhere in this file -- every
assertion here exercises the same Depends(user)/Depends(admin)
dependency chain already used throughout backend/app.py.
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------
# Shared helper: create-and-login a fresh non-admin user for a given
# role, so authorization tests never depend on a shared/global viewer
# account that other test files might mutate.
# ---------------------------------------------------------------------


def _make_user(client, auth_headers, login_as, role: str) -> dict:
    username = f"stage2_{role}_{uuid.uuid4().hex[:8]}"
    password = "Stage2Test1"
    r = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "display_name": f"Stage2 {role.title()} User",
            "password": password,
            "role": role,
        },
    )
    assert r.status_code == 200, r.text
    return login_as(username, password)


# ---------------------------------------------------------------------
# A. Public health endpoint (GET /api/health)
# ---------------------------------------------------------------------

# The approved minimal field set for the public health response. Any
# field appearing in the response that is NOT in this set fails the
# test below -- this is an exact-set check, not just a "does it avoid
# a few named fields" check, so a future accidental addition of a
# sensitive field is caught even if nobody thinks to add it to the
# forbidden list first.
APPROVED_PUBLIC_HEALTH_FIELDS = {"status", "version", "database_ok", "server_time"}

# Fields that must never appear in the public response, named
# explicitly per the Stage 2 policy (kept even though they overlap
# with the exact-set check above, so the failure message is specific
# about *which* sensitive category leaked if the exact-set check is
# ever loosened in the future).
FORBIDDEN_PUBLIC_HEALTH_FIELDS = {
    "active_datasets", "user_count", "users", "total_users", "active_users",
    "database_size", "database_size_kb", "schema_version", "license",
    "readiness", "deployment", "cloud", "environment", "configuration",
    "calculation_count", "audit_count",
}


def test_health_unauthenticated_request_succeeds(client):
    """Existing intended contract: /api/health is public (no auth
    required) -- this is what the frontend version-loader and the
    topbar rely on before a user has logged in."""
    r = client.get("/api/health")
    assert r.status_code == 200, r.text


def test_health_public_response_contains_only_approved_fields(client):
    r = client.get("/api/health")
    body = r.json()
    assert set(body.keys()) == APPROVED_PUBLIC_HEALTH_FIELDS, (
        f"unexpected public /api/health field set: {set(body.keys())}"
    )


def test_health_public_response_does_not_leak_sensitive_fields(client):
    r = client.get("/api/health")
    body = r.json()
    leaked = FORBIDDEN_PUBLIC_HEALTH_FIELDS & set(body.keys())
    assert not leaked, f"sensitive fields leaked from public /api/health: {leaked}"


def test_health_preserves_centralized_version_behavior(client):
    """Guards the existing version-centralization contract (see
    tests/test_version_centralization.py) is untouched by this stage:
    /api/health still reports the same VERSION-file-derived value."""
    from pathlib import Path

    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    expected = version_file.read_text(encoding="utf-8").strip()
    r = client.get("/api/health")
    assert r.json()["version"] == expected


# ---------------------------------------------------------------------
# B. Runtime status endpoint (GET /api/runtime/status)
# ---------------------------------------------------------------------


def test_runtime_status_unauthenticated_is_rejected(client):
    r = client.get("/api/runtime/status")
    assert r.status_code == 401, r.text
    assert "detail" in r.json()


def test_runtime_status_authenticated_non_admin_is_rejected(client, auth_headers, login_as):
    viewer_headers = _make_user(client, auth_headers, login_as, "viewer")
    r = client.get("/api/runtime/status", headers=viewer_headers)
    assert r.status_code == 403, r.text
    assert "detail" in r.json()

    engineer_headers = _make_user(client, auth_headers, login_as, "engineer")
    r2 = client.get("/api/runtime/status", headers=engineer_headers)
    assert r2.status_code == 403, r2.text


def test_runtime_status_authenticated_admin_succeeds(client, auth_headers):
    r = client.get("/api/runtime/status", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Preserve the existing expected schema (frontend loadRuntimeHealth()
    # reads exactly these fields -- see frontend/index.html).
    for field in ("app", "version", "liveness", "readiness", "database", "license", "active_datasets"):
        assert field in body, f"missing expected field: {field}"
    assert body["app"] == "TorqPro"


# ---------------------------------------------------------------------
# C. Existing detailed system endpoint (GET /api/admin/system)
# ---------------------------------------------------------------------


def test_admin_system_unauthenticated_is_rejected(client):
    r = client.get("/api/admin/system")
    assert r.status_code == 401, r.text


def test_admin_system_authenticated_non_admin_is_rejected(client, auth_headers, login_as):
    viewer_headers = _make_user(client, auth_headers, login_as, "viewer")
    r = client.get("/api/admin/system", headers=viewer_headers)
    assert r.status_code == 403, r.text


def test_admin_system_authenticated_admin_succeeds_with_expected_fields(client, auth_headers):
    r = client.get("/api/admin/system", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for field in (
        "status", "version", "database_ok", "database_size_kb",
        "total_users", "active_users", "calculation_count",
        "audit_count", "schema_version", "server_time",
    ):
        assert field in body, f"missing expected admin field: {field}"


# ---------------------------------------------------------------------
# D. Authorization consistency: no independent role model introduced
# ---------------------------------------------------------------------


def test_runtime_status_route_reuses_existing_admin_dependency():
    """Static source check: the fix must reuse the same `admin`
    dependency every other /api/admin/* route already depends on, not
    a new/duplicated role-check mechanism."""
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "backend" / "app.py").read_text(encoding="utf-8")
    idx = src.index('@app.get("/api/runtime/status")')
    # The route's def line (immediately following the decorator) must
    # depend on the same `admin` dependency object used elsewhere in
    # this module (defined once, at `def admin(u=Depends(user)):`).
    def_line_end = src.index("\n", idx)
    def_line = src[idx:src.index("\n", def_line_end + 1)]
    assert "Depends(admin)" in def_line, (
        "expected /api/runtime/status to depend on the existing admin dependency, got: " + def_line
    )
    # Exactly one `admin` dependency function is defined in this module
    # (guards against a second, parallel role-check function being
    # introduced instead of reusing the existing one).
    assert src.count("def admin(u=Depends(user)):") == 1


def test_only_one_admin_dependency_function_exists_in_backend():
    """Guards against introducing a second independent role model
    anywhere in the dependency modules used by the API."""
    from pathlib import Path

    app_src = (Path(__file__).resolve().parent.parent / "backend" / "app.py").read_text(encoding="utf-8")
    deps_src = (
        Path(__file__).resolve().parent.parent / "backend" / "api" / "dependencies.py"
    ).read_text(encoding="utf-8")
    # backend/app.py defines the one `admin` function actually used by
    # every /api/admin/* route (including the Stage 2 fix); dependencies.py
    # separately defines its own unused `admin` (pre-existing, not
    # wired into any route) -- this test only guards that Stage 2 did
    # not add a *third* one anywhere.
    import re

    admin_def_count = len(re.findall(r"^def admin\(", app_src, re.M)) + len(
        re.findall(r"^def admin\(", deps_src, re.M)
    )
    assert admin_def_count == 2, f"expected exactly 2 pre-existing `admin` dependency functions, found {admin_def_count}"
