"""ADR-0017 Karar 10 -- TorqPro must work completely unaffected while
the AI layer is not wired to anything.

v3.0.0-alpha.1 has no HTTP route and no ``app.py`` change at all (see
ADR-0017 Karar 12/13), so this phase's "AI disabled" state is simply
"AI has never been wired in" -- this test proves that state as a fact
about the current repository, not as a feature flag.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend import app as app_module

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_app_py_source_contains_no_ai_gateway_reference():
    """Static proof that this phase touched zero lines of app.py
    (ADR-0017 Karar 12/13, GO criterion 4)."""
    source = (REPO_ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    assert "ai_gateway" not in source
    assert "backend.api.ai" not in source


def test_no_api_ai_route_package_exists_yet():
    """ADR-0017 Karar 12: backend/api/ai/routes is explicitly deferred
    to a later phase and must not exist yet."""
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


def test_ai_gateway_package_has_no_effect_on_module_import_order():
    """Importing backend.ai_gateway (as this test suite does) must not
    have registered anything into backend.app's FastAPI app instance --
    proves deletion-safety (ADR-0017 Karar 10) at the object level, not
    just the source-text level."""
    import backend.ai_gateway.orchestrator  # noqa: F401 - import side-effect check only

    # openapi() flattens every mounted/included router into a single
    # path list regardless of the FastAPI/Starlette version's internal
    # route-wrapping representation, so this check is robust to that
    # internal detail (unlike walking app.routes directly).
    openapi_paths = set(app_module.app.openapi()["paths"].keys())
    assert not any(path.startswith("/api/ai") for path in openapi_paths)
