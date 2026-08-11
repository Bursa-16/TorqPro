"""ADR-0017 Karar 10 -- TorqPro must work completely unaffected by the
presence of the AI layer, whether or not it is wired to an HTTP route.

v3.0.0-alpha.1 through v3.0.0-alpha.3 had no HTTP route and no
``app.py`` change at all (see ADR-0017 Karar 12/13); that "AI disabled"
state was simply "AI has never been wired in". v3.0.0-alpha.4
intentionally wires exactly one read-only HTTP route
(``POST /api/ai/query``, ``backend/api/routes/ai_gateway.py``) into
``backend/app.py`` via the exact same minimal
``import + app.include_router(...)`` pattern already used for every
other route module (``joints``, ``production_validation``,
``question_bank``, ``washer_resolution_closure``). The two tests below
that specifically asserted "no AI route/reference exists yet" are
updated accordingly, in place, to assert this phase's actual (still
narrow, still additive) scope instead -- every other test in this file
is unchanged and still proves TorqPro's non-AI surface is unaffected.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend import app as app_module

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_app_py_touch_for_ai_route_stays_minimal():
    """v3.0.0-alpha.4: app.py now references the new route module
    (via ``backend.api.routes.ai_gateway``), by design -- but nothing
    inside ``backend.ai_gateway`` itself is imported into app.py, and
    the touch is exactly the same shape (one import line, one
    ``include_router`` call) every other route module already uses.
    Supersedes the pre-alpha.4 "zero ai_gateway reference" assertion,
    which is now intentionally obsolete."""
    source = (REPO_ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    assert "backend.api.routes.ai_gateway" in source
    assert source.count("ai_gateway_router") == 2  # one import, one include_router
    # app.py must still never import backend.ai_gateway's internals
    # directly -- only the thin route module is referenced.
    assert "from backend.ai_gateway" not in source
    assert "import backend.ai_gateway" not in source


def test_no_api_ai_route_package_exists():
    """v3.0.0-alpha.4 followed the repository's existing
    ``backend/api/routes/<domain>.py`` convention (matching joints.py/
    production_validation.py/question_bank.py) rather than the
    alternative ``backend/api/ai/`` package path speculated in earlier
    phases' docstrings -- so this still holds, unchanged, in this
    phase too."""
    assert not (REPO_ROOT / "backend" / "api" / "ai").exists()


def test_existing_app_starts_and_serves_health_without_ai_gateway():
    """Functional proof, not just a source-text check: the existing
    FastAPI app (with its existing 5 include_router calls, unchanged)
    starts and serves a representative existing endpoint normally."""
    client = TestClient(app_module.app)

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert "version" in body or "status" in body or body  # non-empty response


def test_existing_login_and_engineering_endpoints_still_work(client, auth_headers):
    """Reuses the shared session-scoped client/auth_headers fixtures
    (tests/conftest.py) to prove a real authenticated, pre-existing
    workflow (materials library read) is completely unaffected."""
    response = client.get("/api/library/materials", headers=auth_headers)

    assert response.status_code == 200


def test_ai_gateway_package_import_registers_no_extra_routes():
    """Importing backend.ai_gateway (as this test suite does) must not,
    by itself, register anything into backend.app's FastAPI app
    instance beyond the routes this phase deliberately wires --
    proves deletion-safety (ADR-0017 Karar 10) at the object level, not
    just the source-text level. Supersedes the pre-alpha.4 "zero
    /api/ai paths" assertion, which is now intentionally obsolete now
    that v3.0.0-alpha.4 wired in the first such path.

    v3.0.0-alpha.5 (ADR-0020) note: updated in place, following this
    same file's own alpha.4-era precedent (see module docstring) --
    three new, deliberately-scoped read-only paths were added
    (``GET /api/ai/providers``, ``GET /api/ai/audit``,
    ``GET /api/ai/audit/{audit_id}``); no other route was added or
    removed, and the full guarded-path count (4) is asserted
    explicitly so a future, unreviewed fifth route would fail this
    test rather than silently pass."""
    import backend.ai_gateway.orchestrator  # noqa: F401 - import side-effect check only

    # openapi() flattens every mounted/included router into a single
    # path list regardless of the FastAPI/Starlette version's internal
    # route-wrapping representation, so this check is robust to that
    # internal detail (unlike walking app.routes directly).
    openapi_paths = set(app_module.app.openapi()["paths"].keys())
    ai_paths = {path for path in openapi_paths if path.startswith("/api/ai")}
    assert ai_paths == {
        "/api/ai/query",
        "/api/ai/providers",
        "/api/ai/audit",
        "/api/ai/audit/{audit_id}",
    }
