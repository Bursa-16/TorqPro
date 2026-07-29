"""Faz 2.8.10 Stage 2 -- shared pytest fixtures (tests/conftest.py).

Validates the three opt-in, additive fixtures introduced in Stage 2
(``client``, ``auth_headers``, ``login_as``) that generalize the
previously per-file-duplicated TestClient/login boilerplate identified
in the Stage 1 Quality Gap Report (Sec. 2.2): 25 of the ~85 existing
test files hardcoded the admin credential and 16 independently defined
a local ``auth()``/``token()`` helper.

This file does not modify, replace, or depend on any existing test
file's local helpers -- it only exercises the new shared fixtures on
their own, proving they behave exactly like the pattern already
established in tests/production_validation/conftest.py and
tests/test_faz_2_8_9_stage3_api.py (module-scoped ``auth_headers``
wrapping the same ``/api/login`` call), just available at the suite
root instead of being re-derived per file.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

DEFAULT_USERNAME_FOR_NEGATIVE_TEST = "Protype Lab"


def test_client_fixture_returns_working_test_client(client):
    assert isinstance(client, TestClient)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["database_ok"] is True


def test_auth_headers_fixture_authenticates_default_admin(client, auth_headers):
    assert "Authorization" in auth_headers
    assert auth_headers["Authorization"].startswith("Bearer ")
    # A protected admin endpoint must accept the shared token.
    r = client.get("/api/admin/system", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["schema_version"] >= 3


_captured_token: dict = {}


def test_auth_headers_fixture_is_session_scoped_first_capture(auth_headers):
    # Capture the token issued to this session-scoped fixture so a later,
    # independent test function can confirm it was reused rather than a
    # fresh login being performed each time a test requests it.
    _captured_token["value"] = auth_headers["Authorization"]


def test_auth_headers_fixture_is_session_scoped_and_reused(auth_headers):
    # Re-requesting the fixture from a different test function within the
    # same session must yield the exact same token rather than performing
    # a second login -- this is the duplication/overhead reduction the
    # fixture exists for.
    assert _captured_token["value"] == auth_headers["Authorization"]


def test_unauthenticated_request_is_rejected(client):
    r = client.get("/api/admin/system")
    assert r.status_code in (401, 403)


def test_login_as_fixture_authenticates_a_newly_created_user(client, auth_headers, login_as):
    username = f"stage2_fixture_user_{uuid.uuid4().hex[:8]}"
    password = "FixtureTest1"
    r = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={
            "username": username,
            "display_name": "Stage 2 Fixture User",
            "password": password,
            "role": "viewer",
        },
    )
    assert r.status_code == 200, r.text

    viewer_headers = login_as(username, password)
    assert viewer_headers["Authorization"].startswith("Bearer ")

    # The new user's token is independently valid and distinct from the
    # shared admin token.
    r = client.get("/api/health", headers=viewer_headers)
    assert r.status_code == 200
    assert viewer_headers != auth_headers


def test_login_as_fixture_rejects_wrong_password(client, login_as):
    with pytest.raises(AssertionError):
        login_as(DEFAULT_USERNAME_FOR_NEGATIVE_TEST, "definitely-wrong-password")
