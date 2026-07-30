import os, sys, tempfile
from pathlib import Path

import pytest

# Ortam, backend.app import edilmeden ÖNCE hazırlanır.
os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)
_tmpdir = tempfile.mkdtemp(prefix="torqpro-test-")
os.environ["TORQPRO_DB_PATH"] = str(Path(_tmpdir) / "torqpro_test.db")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import app as _appmod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# TestClient with-bloğu kullanılmadığında lifespan tetiklenmez;
# temiz ortamda şema garantisi burada verilir.
_appmod.migrate()

# ---------------------------------------------------------------------------
# Faz 2.8.10 Stage 2 -- shared, opt-in fixtures.
#
# These are purely additive: no existing test file is modified or required
# to use them. Every existing file's local `client = TestClient(app)` /
# `def auth()` / `def token()` helper keeps working exactly as before --
# this only gives *new or later-touched* test files a shared alternative,
# matching the pattern already proven in
# tests/production_validation/conftest.py (client + auth_headers +
# builder functions) and tests/test_faz_2_8_9_stage3_api.py (module-scoped
# auth_headers fixture wrapping the same login call), generalized to the
# whole suite so future files don't have to keep re-deriving it locally.
# ---------------------------------------------------------------------------

DEFAULT_USERNAME = "Protype Lab"
DEFAULT_PASSWORD = "A1234"


def _login(test_client, username=DEFAULT_USERNAME, password=DEFAULT_PASSWORD):
    r = test_client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="session")
def client():
    """Shared FastAPI TestClient bound to the single migrated test DB.

    Session-scoped: TestClient itself holds no per-test state (auth is
    carried per-request via the Authorization header, not cookies), so
    sharing one instance across the whole session is safe and avoids
    re-instantiating it in every file that opts in.
    """
    return TestClient(_appmod.app)


@pytest.fixture(scope="session")
def auth_headers(client):
    """Shared bearer-token auth headers for the default admin user
    ("Protype Lab" / "A1234"). Session-scoped: the access token is valid
    for ACCESS_TOKEN_MINUTES (480 minutes in backend/app.py) -- far
    longer than a full local test run -- so one login is reused for the
    whole session instead of every opted-in test/file re-authenticating.
    """
    return _login(client)


@pytest.fixture()
def login_as(client):
    """Factory fixture for logging in as an arbitrary (non-default) user,
    e.g. a second reviewer created within a test -- generalizes the
    ad-hoc `make_second_reviewer()` pattern already used in
    tests/production_validation/conftest.py. Returns a callable
    ``login_as(username, password) -> {"Authorization": "Bearer ..."}``.
    """

    def _factory(username: str, password: str) -> dict:
        return _login(client, username, password)

    return _factory
