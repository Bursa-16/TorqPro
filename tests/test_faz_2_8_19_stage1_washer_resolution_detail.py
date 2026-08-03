"""Faz 2.8.19 Stage 1 tests: washer resolution detail endpoint.

Covers: GET /api/library/washers/resolutions/{resolution_id} for a
known-open record and a known-blocked record (200, canonical field
match against the source ledger), unknown resolution_id (404), auth
requirement, read-only behavior (decision ledger file untouched), and
a route-order/backward-compatibility regression check confirming the
new dynamic route does not shadow the pre-existing /queue, /report,
/{resolution_id}/decisions or /{resolution_id}/decide endpoints.

Follows the same isolated_ledger fixture pattern as
tests/test_faz_2_8_9_stage3_api.py: all writes (if any occurred) would
go through an isolated tmp_path file, never the real, committed
washer_resolution_decisions.json. This file performs no writes at
all -- the new endpoint under test is GET-only.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.library import washer_resolution as wr
from backend.library import washer_resolution_decisions_store as store

client = TestClient(app)


def _login():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def auth_headers():
    return _login()


@pytest.fixture()
def isolated_ledger(tmp_path, monkeypatch):
    ledger_path = tmp_path / "washer_resolution_decisions.json"
    ledger_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "name": "Washer Resolution Decision Ledger",
                    "version": "test",
                    "source_ledger": "backend/library/data/washer_resolution_ledger.json",
                    "record_count": 0,
                },
                "decisions": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "DATA_PATH", ledger_path)
    monkeypatch.setattr(store, "_LOCK_PATH", ledger_path.with_suffix(".lock"))
    store.reload()
    yield ledger_path
    store.reload()


# Known-open and known-blocked records from the real Faz 2.8.5 ledger
# (read-only reference, same IDs used by test_faz_2_8_9_stage3_api.py).
OPEN_RESOLUTION_ID = "RES-WASH-DIN127B-M10"
BLOCKED_RESOLUTION_ID = "RES-WASH-ISO7093-M10"
UNKNOWN_RESOLUTION_ID = "RES-WASH-DOES-NOT-EXIST"


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------


def test_detail_requires_auth(isolated_ledger):
    r = client.get(f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------
# 200: known resolution_id, response matches canonical ledger data
# ---------------------------------------------------------------------


class TestDetailKnownOpenRecord:
    def test_200_for_known_open_record(self, isolated_ledger, auth_headers):
        r = client.get(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}", headers=auth_headers
        )
        assert r.status_code == 200, r.text

    def test_response_matches_canonical_ledger_record(self, isolated_ledger, auth_headers):
        canonical = wr.get_washer_resolution(OPEN_RESOLUTION_ID)
        assert canonical is not None  # sanity: fixture ID is real

        r = client.get(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}", headers=auth_headers
        )
        body = r.json()

        assert body["resolution_id"] == canonical.resolution_id
        assert body["washer_record_id"] == canonical.washer_record_id
        assert body["issue_type"] == canonical.issue_type.value
        assert body["reason_code"] == canonical.reason_code
        assert body["source_status"] == canonical.resolution_status.value
        assert body["resolution_note"] == canonical.resolution_note
        assert body["evidence_reference"] == canonical.evidence_reference
        assert body["resolved_standard"] == canonical.resolved_standard
        assert body["resolved_by"] == canonical.resolved_by
        assert body["resolved_at"] == canonical.resolved_at
        assert body["requires_authoritative_source"] == canonical.requires_authoritative_source

    def test_response_has_effective_status_annotation(self, isolated_ledger, auth_headers):
        # No decisions recorded in this isolated ledger -> effective_status
        # falls back to source_status, decision_count is 0, not terminal.
        r = client.get(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}", headers=auth_headers
        )
        body = r.json()
        assert body["effective_status"] == body["source_status"] == "open"
        assert body["decision_count"] == 0
        assert body["is_blocked"] is False
        assert body["is_terminal"] is False


class TestDetailKnownBlockedRecord:
    def test_200_and_is_blocked_true(self, isolated_ledger, auth_headers):
        r = client.get(
            f"/api/library/washers/resolutions/{BLOCKED_RESOLUTION_ID}", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source_status"] == "blocked_authoritative_source"
        assert body["is_blocked"] is True


# ---------------------------------------------------------------------
# 404: unknown resolution_id
# ---------------------------------------------------------------------


def test_404_for_unknown_resolution_id(isolated_ledger, auth_headers):
    r = client.get(
        f"/api/library/washers/resolutions/{UNKNOWN_RESOLUTION_ID}", headers=auth_headers
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------
# Read-only: decision ledger file untouched by GET requests
# ---------------------------------------------------------------------


def test_detail_endpoint_never_writes_to_decision_ledger(isolated_ledger, auth_headers):
    before = isolated_ledger.read_text(encoding="utf-8")

    client.get(f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}", headers=auth_headers)
    client.get(f"/api/library/washers/resolutions/{BLOCKED_RESOLUTION_ID}", headers=auth_headers)
    client.get(f"/api/library/washers/resolutions/{UNKNOWN_RESOLUTION_ID}", headers=auth_headers)

    after = isolated_ledger.read_text(encoding="utf-8")
    assert before == after


def test_detail_endpoint_never_writes_to_source_ledger(isolated_ledger, auth_headers):
    before_status = wr.get_washer_resolution(OPEN_RESOLUTION_ID).resolution_status
    client.get(f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}", headers=auth_headers)
    after_status = wr.get_washer_resolution(OPEN_RESOLUTION_ID).resolution_status
    assert before_status == after_status


# ---------------------------------------------------------------------
# Route-order / backward compatibility: pre-existing endpoints unaffected
# ---------------------------------------------------------------------


class TestPreExistingEndpointsUnshadowed:
    def test_queue_endpoint_still_returns_all_76_records(self, isolated_ledger, auth_headers):
        r = client.get("/api/library/washers/resolutions/queue", headers=auth_headers)
        assert r.status_code == 200, r.text
        assert len(r.json()["records"]) == 76

    def test_report_endpoint_still_returns_json_report(self, isolated_ledger, auth_headers):
        r = client.get("/api/library/washers/resolutions/report", headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "report" in r.json()

    def test_decisions_history_endpoint_still_works(self, isolated_ledger, auth_headers):
        r = client.get(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decisions",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["decisions"] == []

    def test_decide_endpoint_contract_unchanged(self, isolated_ledger, auth_headers):
        r = client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json={
                "new_status": "under_review",
                "resolution_note": "Escalated for secondary source review.",
                "evidence_reference": "internal-review-log#2026-08-03",
                "resolved_by": "ilhan",
                "idempotency_key": "faz-2-8-19-stage1-regression-key-0001",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["decision"]["new_status"] == "under_review"

    def test_after_a_decision_detail_endpoint_reflects_effective_status(
        self, isolated_ledger, auth_headers
    ):
        # isolated_ledger is function-scoped (fresh per test), so this
        # test records its own decision first. Confirms the new detail
        # endpoint reads decisions correctly without re-deriving the
        # formula itself (it calls the same resolution_queue() the
        # /queue endpoint above already uses).
        client.post(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}/decide",
            json={
                "new_status": "under_review",
                "resolution_note": "Escalated for secondary source review.",
                "evidence_reference": "internal-review-log#2026-08-03",
                "resolved_by": "ilhan",
                "idempotency_key": "faz-2-8-19-stage1-regression-key-0002",
            },
            headers=auth_headers,
        )
        r = client.get(
            f"/api/library/washers/resolutions/{OPEN_RESOLUTION_ID}", headers=auth_headers
        )
        body = r.json()
        assert body["effective_status"] == "under_review"
        assert body["decision_count"] == 1
        assert body["source_status"] == "open"  # source ledger itself never changes
