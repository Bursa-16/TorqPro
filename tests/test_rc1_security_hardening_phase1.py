"""v3.0.0-rc.1 Security Hardening Phase 1 -- targeted regression tests.

Covers the three items implemented in this phase (see the Stage 0
discovery report for the underlying findings):

* B1 -- ``TORQPRO_ALLOWED_HOSTS`` is now parsed and enforced via
  Starlette's ``TrustedHostMiddleware``. It was previously documented
  in ``.env.example`` but never read anywhere in ``backend/app.py``.
* B2 -- ``/docs``, ``/redoc``, ``/openapi.json`` are now disabled when
  ``TORQPRO_ENV=production``; every other environment (including the
  test suite's, which never sets ``TORQPRO_ENV``) keeps today's
  behavior.
* B3 -- cross-user ownership regression coverage for ``calculations``
  and ``projects``, including a regression test for a genuine
  authorization gap this phase found and fixed: ``POST
  /api/calculations`` accepted an arbitrary ``project_id`` without
  verifying the caller owned that project, silently attaching the new
  calculation to someone else's project (and, through it, leaking into
  that other user's ``GET /api/projects/{id}/traceability`` and
  release-package reports, and corrupting that project's
  ``calculation_count``).

B1 and B2 depend on module-level state that is fixed at
``backend.app`` import time (the single ``app`` FastAPI instance is
built once, with ``TORQPRO_ALLOWED_HOSTS``/``TORQPRO_ENV`` read at
that point). The already-imported, session-scoped ``app`` used
elsewhere in this suite was built with neither variable set, so its
behavior cannot be changed after the fact by monkeypatching
``os.environ``. Both are therefore verified in a fresh child process
with the relevant variable(s) set before import -- the same pattern
already used in
``tests/governance/test_joint_revision_api.py::test_joint_revision_route_reachable_via_testclient_in_a_clean_process``.

B3 uses the repository's existing shared fixtures (``client``,
``auth_headers``, ``login_as`` from ``tests/conftest.py``) and the
``_make_user`` factory pattern already established in
``tests/ai/reasoning/test_http_route_reasoning.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------
# Shared subprocess helper for B1/B2
# ---------------------------------------------------------------------


def _run_in_fresh_process(script: str, tmp_path, extra_env: dict | None = None):
    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(tmp_path / f"rc1_sec_p1_{uuid.uuid4().hex[:8]}.db")
    # A stale TORQPRO_ALLOWED_HOSTS/TORQPRO_ENV from the outer test
    # runner's own environment must never leak into a child process
    # that a test wants "unset" -- only extra_env's explicit values
    # (if any) are authoritative for these two variables.
    env.pop("TORQPRO_ALLOWED_HOSTS", None)
    env.pop("TORQPRO_ENV", None)
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


_HEALTH_CHECK_SCRIPT = (
    "from backend.app import app, migrate; migrate(); "
    "from fastapi.testclient import TestClient; "
    "c = TestClient(app, base_url={base_url!r}); "
    "r = c.get('/api/health'); "
    "print('STATUS', r.status_code)"
)


# ---------------------------------------------------------------------
# B1 -- TORQPRO_ALLOWED_HOSTS / TrustedHostMiddleware
# ---------------------------------------------------------------------


def test_parse_allowed_hosts_single_value():
    from backend.app import _parse_allowed_hosts

    assert _parse_allowed_hosts("torqpro.example.com") == ["torqpro.example.com"]


def test_parse_allowed_hosts_multiple_values_comma_separated_with_whitespace():
    from backend.app import _parse_allowed_hosts

    result = _parse_allowed_hosts(" a.example.com ,b.example.com,, c.example.com ")
    assert result == ["a.example.com", "b.example.com", "c.example.com"]


@pytest.mark.parametrize("raw", [None, "", "   ", ",,,", " , , "])
def test_parse_allowed_hosts_edge_cases_return_none(raw):
    """Unset, empty, whitespace-only, or separator-only input must all
    resolve to "no host restriction configured" -- never raise, never
    silently produce an empty allow-list (which would reject every
    host, a much more disruptive failure mode than doing nothing)."""
    from backend.app import _parse_allowed_hosts

    assert _parse_allowed_hosts(raw) is None


def test_allowed_hosts_unset_accepts_any_host(tmp_path):
    """Dev/test default: TORQPRO_ALLOWED_HOSTS unset -> no
    TrustedHostMiddleware attached -> any Host header accepted,
    identical to pre-Phase-1 behavior."""
    script = _HEALTH_CHECK_SCRIPT.format(base_url="http://anything-goes.invalid")
    result = _run_in_fresh_process(script, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 200" in result.stdout


def test_allowed_hosts_configured_accepts_listed_host(tmp_path):
    script = _HEALTH_CHECK_SCRIPT.format(base_url="http://torqpro.example.com")
    result = _run_in_fresh_process(
        script, tmp_path, extra_env={"TORQPRO_ALLOWED_HOSTS": "torqpro.example.com"}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 200" in result.stdout


def test_allowed_hosts_configured_rejects_unlisted_host(tmp_path):
    script = _HEALTH_CHECK_SCRIPT.format(base_url="http://attacker.invalid")
    result = _run_in_fresh_process(
        script, tmp_path, extra_env={"TORQPRO_ALLOWED_HOSTS": "torqpro.example.com"}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 400" in result.stdout


def test_allowed_hosts_multiple_hosts_each_accepted(tmp_path):
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c1 = TestClient(app, base_url='http://a.example.com'); "
        "c2 = TestClient(app, base_url='http://b.example.com'); "
        "r1 = c1.get('/api/health'); r2 = c2.get('/api/health'); "
        "print('STATUS', r1.status_code, r2.status_code)"
    )
    result = _run_in_fresh_process(
        script, tmp_path, extra_env={"TORQPRO_ALLOWED_HOSTS": "a.example.com,b.example.com"}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 200 200" in result.stdout


def test_allowed_hosts_multiple_hosts_rejects_third_unlisted_host(tmp_path):
    script = _HEALTH_CHECK_SCRIPT.format(base_url="http://c.example.com")
    result = _run_in_fresh_process(
        script, tmp_path, extra_env={"TORQPRO_ALLOWED_HOSTS": "a.example.com,b.example.com"}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 400" in result.stdout


def test_allowed_hosts_blank_string_behaves_like_unset(tmp_path):
    """Edge case: variable present in the environment but empty
    (TORQPRO_ALLOWED_HOSTS="") must not crash and must not attach the
    middleware -- same as unset, not "reject everything"."""
    script = _HEALTH_CHECK_SCRIPT.format(base_url="http://anything-goes.invalid")
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ALLOWED_HOSTS": ""})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 200" in result.stdout


def test_allowed_hosts_separators_only_behaves_like_unset(tmp_path):
    """Edge case: TORQPRO_ALLOWED_HOSTS=" , , " (garbage separators,
    no actual hostnames) must not crash and must not attach the
    middleware."""
    script = _HEALTH_CHECK_SCRIPT.format(base_url="http://anything-goes.invalid")
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ALLOWED_HOSTS": " , , "})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 200" in result.stdout


# ---------------------------------------------------------------------
# B2 -- production API documentation exposure
# ---------------------------------------------------------------------


def test_docs_endpoints_available_when_torqpro_env_unset(tmp_path):
    """Default/dev/test behavior (TORQPRO_ENV unset, exactly as in the
    rest of this suite) must be unchanged: docs/redoc/openapi all
    served."""
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r1 = c.get('/docs'); r2 = c.get('/redoc'); r3 = c.get('/openapi.json'); "
        "print('STATUS', r1.status_code, r2.status_code, r3.status_code)"
    )
    result = _run_in_fresh_process(script, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 200 200 200" in result.stdout


@pytest.mark.parametrize("env_value", ["development", "staging", ""])
def test_docs_endpoints_available_for_non_production_value(tmp_path, env_value):
    """Only an exact (case-insensitive-after-strip) TORQPRO_ENV=production
    disables the docs -- any other named environment (or an explicitly
    empty value) must not disable them."""
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r1 = c.get('/docs'); r2 = c.get('/redoc'); r3 = c.get('/openapi.json'); "
        "print('STATUS', r1.status_code, r2.status_code, r3.status_code)"
    )
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ENV": env_value})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 200 200 200" in result.stdout


def test_docs_endpoints_disabled_when_torqpro_env_is_production(tmp_path):
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r1 = c.get('/docs'); r2 = c.get('/redoc'); r3 = c.get('/openapi.json'); "
        "print('STATUS', r1.status_code, r2.status_code, r3.status_code)"
    )
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ENV": "production"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 404 404 404" in result.stdout


def test_docs_endpoints_disabled_case_and_whitespace_tolerant(tmp_path):
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r1 = c.get('/docs'); r2 = c.get('/redoc'); r3 = c.get('/openapi.json'); "
        "print('STATUS', r1.status_code, r2.status_code, r3.status_code)"
    )
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ENV": " Production "})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 404 404 404" in result.stdout


def test_normal_api_endpoints_unaffected_by_production_docs_toggle(tmp_path):
    """Disabling docs/redoc/openapi must not touch any real /api/...
    route -- login and health must both keep working exactly as
    before under TORQPRO_ENV=production."""
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from fastapi.testclient import TestClient; "
        "c = TestClient(app); "
        "r1 = c.get('/api/health'); "
        "r2 = c.post('/api/login', json={'username': 'Protype Lab', 'password': 'A1234'}); "
        "print('STATUS', r1.status_code, r2.status_code)"
    )
    result = _run_in_fresh_process(script, tmp_path, extra_env={"TORQPRO_ENV": "production"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS 200 200" in result.stdout


# ---------------------------------------------------------------------
# B3 -- cross-user ownership regression coverage: calculations, projects
# ---------------------------------------------------------------------


def _make_user(client, auth_headers, login_as, role: str = "engineer") -> dict:
    username = f"rc1sec_{role}_{uuid.uuid4().hex[:8]}"
    password = "Rc1SecTest1"
    r = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "display_name": f"RC1 Security {role.title()} User",
            "password": password,
            "role": role,
        },
    )
    assert r.status_code == 200, r.text
    return login_as(username, password)


def _create_project(client, headers, name: str = "RC1 Sec Project") -> dict:
    r = client.post("/api/projects", headers=headers, json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def _create_calculation(client, headers, project_id: int | None = None) -> dict:
    payload = {"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230"}
    if project_id is not None:
        payload["project_id"] = project_id
    r = client.post("/api/calculations", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# --- calculations -------------------------------------------------


def test_cross_user_cannot_list_another_users_calculation(client, auth_headers, login_as):
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    calc = _create_calculation(client, owner)

    r = client.get("/api/calculations", headers=other)
    assert r.status_code == 200, r.text
    assert calc["record_no"] not in {row["record_no"] for row in r.json()}


def test_cross_user_cannot_read_another_users_calculation_trace(client, auth_headers, login_as):
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    calc = _create_calculation(client, owner)

    r = client.get(f"/api/calculations/{calc['id']}/data-trace", headers=other)
    assert r.status_code == 404, r.text


def test_cross_user_cannot_delete_another_users_calculation(client, auth_headers, login_as):
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    calc = _create_calculation(client, owner)

    r = client.delete(f"/api/calculations/{calc['id']}", headers=other)
    assert r.status_code == 404, r.text

    # And the owner can still see/delete it afterwards -- proves the
    # rejected cross-user delete had no side effect on the real record.
    r_list = client.get("/api/calculations", headers=owner)
    assert calc["record_no"] in {row["record_no"] for row in r_list.json()}


def test_no_update_endpoint_exists_for_calculations(client, auth_headers, login_as):
    """Calculations are immutable by design (ADR-0008); there is no
    PATCH/PUT endpoint at all, so "User B cannot UPDATE User A's
    calculation" holds trivially and unconditionally, not merely
    per-ownership. This test pins that absence down so the guarantee
    is not silently lost if an update endpoint is ever added without
    an ownership check."""
    owner = _make_user(client, auth_headers, login_as)
    calc = _create_calculation(client, owner)

    r_patch = client.patch(f"/api/calculations/{calc['id']}", headers=owner, json={"torque_nm": 99})
    r_put = client.put(f"/api/calculations/{calc['id']}", headers=owner, json={"torque_nm": 99})
    assert r_patch.status_code in (404, 405), r_patch.text
    assert r_put.status_code in (404, 405), r_put.text


# --- projects -------------------------------------------------------


def test_cross_user_cannot_list_another_users_project(client, auth_headers, login_as):
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    project = _create_project(client, owner)

    r = client.get("/api/projects", headers=other)
    assert r.status_code == 200, r.text
    assert project["id"] not in {row["id"] for row in r.json()}


def test_cross_user_cannot_read_another_users_project_traceability(client, auth_headers, login_as):
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    project = _create_project(client, owner)

    r = client.get(f"/api/projects/{project['id']}/traceability", headers=other)
    assert r.status_code == 404, r.text


def test_cross_user_cannot_create_another_users_release_package(client, auth_headers, login_as):
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    project = _create_project(client, owner)

    r = client.get(f"/api/projects/{project['id']}/release-package", headers=other)
    assert r.status_code == 404, r.text


def test_cross_user_cannot_list_another_users_release_packages(client, auth_headers, login_as):
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    project = _create_project(client, owner)

    r = client.get(f"/api/projects/{project['id']}/release-packages", headers=other)
    assert r.status_code == 404, r.text


# --- the actual bug this phase found and fixed -----------------------


def test_cannot_attach_a_calculation_to_another_users_project(client, auth_headers, login_as):
    """Regression test for the real authorization gap found while
    implementing B3: POST /api/calculations accepted any project_id
    without checking that the caller owned that project. Before the
    fix in backend/app.py's add() handler, this call would return 200
    and silently associate the new calculation with owner's project --
    inflating owner's project calculation_count and leaking into
    owner's own traceability/release-package reports despite the
    calculation itself being created and "owned" (user_id) by other."""
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    project = _create_project(client, owner)

    r = client.post(
        "/api/calculations",
        headers=other,
        json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230", "project_id": project["id"]},
    )
    assert r.status_code == 404, r.text


def test_foreign_project_id_does_not_pollute_owners_calculation_count_or_traceability(
    client, auth_headers, login_as
):
    """End-to-end confirmation that the fix closes the actual
    observable damage: owner's project calculation_count and
    traceability report only ever reflect owner's own calculations,
    even after other repeatedly tries (and fails) to attach one."""
    owner = _make_user(client, auth_headers, login_as)
    other = _make_user(client, auth_headers, login_as)
    project = _create_project(client, owner)
    own_calc = _create_calculation(client, owner, project_id=project["id"])

    for _ in range(3):
        r = client.post(
            "/api/calculations",
            headers=other,
            json={"thread": "M8", "torque_nm": 20.0, "standard": "VDI2230", "project_id": project["id"]},
        )
        assert r.status_code == 404, r.text

    r_list = client.get("/api/projects", headers=owner)
    assert r_list.status_code == 200, r_list.text
    listed = next(p for p in r_list.json() if p["id"] == project["id"])
    assert listed["calculation_count"] == 1

    r_trace = client.get(f"/api/projects/{project['id']}/traceability", headers=owner)
    assert r_trace.status_code == 200, r_trace.text
    trace_ids = {row["id"] for row in r_trace.json()}
    assert trace_ids == {own_calc["id"]}


def test_own_project_id_on_calculation_creation_still_works(client, auth_headers, login_as):
    """Non-regression: creating a calculation under a project the
    caller genuinely owns must keep working exactly as before."""
    owner = _make_user(client, auth_headers, login_as)
    project = _create_project(client, owner)

    r = client.post(
        "/api/calculations",
        headers=owner,
        json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230", "project_id": project["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["project_id"] == project["id"]


def test_calculation_without_project_id_still_works(client, auth_headers, login_as):
    """Non-regression: project_id remains optional; omitting it must
    not trigger the new ownership check at all."""
    owner = _make_user(client, auth_headers, login_as)

    r = client.post(
        "/api/calculations",
        headers=owner,
        json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["project_id"] is None


def test_admin_is_not_granted_implicit_project_ownership(client, auth_headers, login_as):
    """The new check reuses the existing _get_owned_project helper as
    already used by traceability/release-package -- consistent with
    that pre-existing semantics, admin has no special bypass here
    either (matching, not widening, current project-route behavior)."""
    owner = _make_user(client, auth_headers, login_as)
    project = _create_project(client, owner)

    r = client.post(
        "/api/calculations",
        headers=auth_headers,  # default admin user, not the project owner
        json={"thread": "M10", "torque_nm": 45.0, "standard": "VDI2230", "project_id": project["id"]},
    )
    assert r.status_code == 404, r.text
