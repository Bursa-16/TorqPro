"""Faz 2.8.20 Stage 4 tests: washer resolution evidence & controlled
closure HTTP API (backend/api/routes/washer_resolution_closure.py).

Every test isolates all four ledgers the underlying service layer
cross-references (source, decisions, evidence, closure) via
``tmp_path``/``monkeypatch``, mirroring
``tests/test_faz_2_8_20_stage3_washer_resolution_controlled_closure.py``
and ``tests/test_faz_2_8_9_stage3_api.py``'s own ``TestClient`` +
real ``/api/login`` conventions. No test ever writes to any real
``backend/library/data/*.json`` file.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.library import washer_resolution as wr
from backend.library import washer_resolution_closure_store as wc_store
from backend.library import washer_resolution_decisions_store as decisions_store
from backend.library import washer_resolution_evidence as we
from backend.library import washer_resolution_evidence_store as we_store
from backend.library import washer_resolution_service as svc

client = TestClient(app)

BASE = "/api/library/washers/resolutions"


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------


def _login():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def auth_headers():
    return _login()


# ---------------------------------------------------------------------
# Full-stack isolation fixture (mirrors Stage 3's isolated_stack)
# ---------------------------------------------------------------------


@pytest.fixture()
def isolated_stack(tmp_path, monkeypatch):
    ledger_path = tmp_path / "washer_resolution_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "name": "Test Ledger",
                "version": "test",
                "record_count": 3,
                "records": [
                    {
                        "resolution_id": "RES-TEST-OPEN",
                        "washer_record_id": "WASH-TEST-1",
                        "issue_type": "source_missing",
                    },
                    {
                        "resolution_id": "RES-TEST-BLOCKED",
                        "washer_record_id": "WASH-TEST-2",
                        "issue_type": "standard_identity_ambiguous",
                        "resolution_status": "blocked_authoritative_source",
                        "requires_authoritative_source": True,
                    },
                    {
                        "resolution_id": "RES-TEST-SECOND",
                        "washer_record_id": "WASH-TEST-3",
                        "issue_type": "verification_pending",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(wr, "DATA_PATH", ledger_path)
    wr.reload()

    decisions_path = tmp_path / "washer_resolution_decisions.json"
    decisions_path.write_text(
        json.dumps({"metadata": {"record_count": 0}, "decisions": []}), encoding="utf-8"
    )
    monkeypatch.setattr(decisions_store, "DATA_PATH", decisions_path)
    monkeypatch.setattr(decisions_store, "_LOCK_PATH", decisions_path.with_suffix(".lock"))
    decisions_store.reload()

    evidence_path = tmp_path / "washer_resolution_evidence.json"
    evidence_path.write_text(
        json.dumps({"metadata": {"record_count": 0}, "evidence": []}), encoding="utf-8"
    )
    monkeypatch.setattr(we_store, "DATA_PATH", evidence_path)
    monkeypatch.setattr(we_store, "_LOCK_PATH", evidence_path.with_suffix(".lock"))
    we_store.reload()

    closure_path = tmp_path / "washer_resolution_closure.json"
    closure_path.write_text(
        json.dumps({"metadata": {"record_count": 0}, "closures": []}), encoding="utf-8"
    )
    monkeypatch.setattr(wc_store, "DATA_PATH", closure_path)
    monkeypatch.setattr(wc_store, "_LOCK_PATH", closure_path.with_suffix(".lock"))
    wc_store.reload()

    yield {
        "ledger_path": ledger_path,
        "decisions_path": decisions_path,
        "evidence_path": evidence_path,
        "closure_path": closure_path,
    }

    wr.reload()
    decisions_store.reload()
    we_store.reload()
    wc_store.reload()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

VALID_EVIDENCE_BODY = {
    "evidence_type": "manufacturer_document",
    "title": "Test evidence",
    "description": "Test evidence description.",
    "source_reference": "Test Catalog 2026, p. 1",
    "created_by": "ilhan",
}


def _post_evidence(resolution_id, headers, body=None):
    return client.post(f"{BASE}/{resolution_id}/evidence", headers=headers, json=body or VALID_EVIDENCE_BODY)


def _get_evidence(resolution_id, headers):
    return client.get(f"{BASE}/{resolution_id}/evidence", headers=headers)


def _get_readiness(resolution_id, headers):
    return client.get(f"{BASE}/{resolution_id}/closure-readiness", headers=headers)


def _post_close(resolution_id, headers, body=None):
    body = body or {"closure_rationale": "Closing for test.", "closed_by": "ilhan"}
    return client.post(f"{BASE}/{resolution_id}/close", headers=headers, json=body)


def _get_closure(resolution_id, headers):
    return client.get(f"{BASE}/{resolution_id}/closure", headers=headers)


def _make_verified_evidence_directly(resolution_id="RES-TEST-OPEN"):
    evidence = we.create_washer_resolution_evidence(
        resolution_id=resolution_id,
        evidence_type=we.EvidenceType.MANUFACTURER_DOCUMENT,
        title="Test evidence", description="Test evidence description.",
        source_reference="Test Catalog 2026, p. 1", created_by="ilhan",
    )
    fields = evidence.model_dump(mode="json")
    fields["verification_status"] = we.EvidenceVerificationStatus.VERIFIED.value
    fields["verified_by"] = "reviewer1"
    fields["verified_at"] = "2026-01-16T09:00:00.000000Z"
    checksum = we.compute_evidence_checksum(fields)
    evidence = we.WasherResolutionEvidence(
        evidence_id=fields["evidence_id"], resolution_id=fields["resolution_id"],
        evidence_type=we.EvidenceType(fields["evidence_type"]), title=fields["title"],
        description=fields["description"], source_reference=fields["source_reference"],
        source_locator=fields["source_locator"], source_url=fields["source_url"],
        source_standard=fields["source_standard"],
        verification_status=we.EvidenceVerificationStatus.VERIFIED,
        verified_by=fields["verified_by"], verified_at=fields["verified_at"],
        created_by=fields["created_by"], created_at=fields["created_at"],
        integrity_checksum=checksum,
    )
    we_store.append_evidence(evidence)
    return evidence


def _decide_to_terminal(resolution_id="RES-TEST-OPEN"):
    decision, _ = svc.decide_resolution(
        resolution_id=resolution_id,
        new_status=wr.WasherResolutionStatus.RESOLVED,
        resolution_note="Resolved for test purposes.", evidence_reference="ref",
        resolved_by="ilhan", idempotency_key=f"idem-{resolution_id}",
    )
    return decision


def _make_ready_for_closure(resolution_id="RES-TEST-OPEN"):
    _decide_to_terminal(resolution_id)
    return _make_verified_evidence_directly(resolution_id)


# =======================================================================
# AUTH (1-5)
# =======================================================================


@pytest.mark.parametrize(
    "method,path_suffix",
    [
        ("post", "/evidence"),
        ("get", "/evidence"),
        ("get", "/closure-readiness"),
        ("post", "/close"),
        ("get", "/closure"),
    ],
)
def test_endpoint_requires_auth(isolated_stack, method, path_suffix):
    url = f"{BASE}/RES-TEST-OPEN{path_suffix}"
    if method == "post":
        response = client.post(url, json={})
    else:
        response = client.get(url)
    assert response.status_code == 401


# =======================================================================
# EVIDENCE POST (6-15)
# =======================================================================


class TestEvidencePost:
    def test_valid_evidence_creation_200(self, isolated_stack, auth_headers):
        r = _post_evidence("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 200, r.text

    def test_response_wrapper_evidence(self, isolated_stack, auth_headers):
        r = _post_evidence("RES-TEST-OPEN", auth_headers)
        assert "evidence" in r.json()

    def test_backend_generated_evidence_id(self, isolated_stack, auth_headers):
        r = _post_evidence("RES-TEST-OPEN", auth_headers)
        assert r.json()["evidence"]["evidence_id"].startswith("WRE-")

    def test_backend_generated_created_at(self, isolated_stack, auth_headers):
        r = _post_evidence("RES-TEST-OPEN", auth_headers)
        assert r.json()["evidence"]["created_at"].endswith("Z")

    @pytest.mark.parametrize(
        "extra_field,extra_value",
        [
            ("created_at", "2026-01-01T00:00:00.000000Z"),
            ("integrity_checksum", "a" * 64),
            ("evidence_id", "WRE-forged"),
        ],
    )
    def test_backend_generated_field_in_request_rejected_422(
        self, isolated_stack, auth_headers, extra_field, extra_value
    ):
        body = dict(VALID_EVIDENCE_BODY)
        body[extra_field] = extra_value
        r = _post_evidence("RES-TEST-OPEN", auth_headers, body=body)
        assert r.status_code == 422, r.text

    def test_unknown_resolution_404(self, isolated_stack, auth_headers):
        r = _post_evidence("RES-DOES-NOT-EXIST", auth_headers)
        assert r.status_code == 404

    def test_invalid_evidence_type_422(self, isolated_stack, auth_headers):
        body = dict(VALID_EVIDENCE_BODY)
        body["evidence_type"] = "not_a_real_type"
        r = _post_evidence("RES-TEST-OPEN", auth_headers, body=body)
        assert r.status_code == 422

    def test_evidence_integrity_error_mapped_422(self, isolated_stack, auth_headers, monkeypatch):
        monkeypatch.setattr(
            svc, "record_resolution_evidence",
            lambda **kwargs: (_ for _ in ()).throw(svc.EvidenceIntegrityError("WRE-fake")),
        )
        r = _post_evidence("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 422


# =======================================================================
# EVIDENCE GET (16-20)
# =======================================================================


class TestEvidenceGet:
    def test_evidence_list_200(self, isolated_stack, auth_headers):
        _post_evidence("RES-TEST-OPEN", auth_headers)
        r = _get_evidence("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 200
        assert len(r.json()["records"]) == 1

    def test_empty_evidence_list_200(self, isolated_stack, auth_headers):
        r = _get_evidence("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 200
        assert r.json()["records"] == []

    def test_append_order_preserved(self, isolated_stack, auth_headers):
        _post_evidence("RES-TEST-OPEN", auth_headers, body={**VALID_EVIDENCE_BODY, "title": "first"})
        _post_evidence("RES-TEST-OPEN", auth_headers, body={**VALID_EVIDENCE_BODY, "title": "second"})
        r = _get_evidence("RES-TEST-OPEN", auth_headers)
        titles = [rec["title"] for rec in r.json()["records"]]
        assert titles == ["first", "second"]

    def test_unknown_resolution_404(self, isolated_stack, auth_headers):
        r = _get_evidence("RES-DOES-NOT-EXIST", auth_headers)
        assert r.status_code == 404

    def test_evidence_integrity_error_mapped_422(self, isolated_stack, auth_headers):
        _make_verified_evidence_directly()
        payload = json.loads(isolated_stack["evidence_path"].read_text(encoding="utf-8"))
        payload["evidence"][0]["title"] = "Tampered by hand"
        isolated_stack["evidence_path"].write_text(json.dumps(payload), encoding="utf-8")
        we_store.reload()
        r = _get_evidence("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 422


# =======================================================================
# READINESS (21-26)
# =======================================================================


class TestReadiness:
    def test_readiness_response_200(self, isolated_stack, auth_headers):
        r = _get_readiness("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 200

    def test_effective_status_is_string(self, isolated_stack, auth_headers):
        r = _get_readiness("RES-TEST-OPEN", auth_headers)
        assert isinstance(r.json()["effective_status"], str)
        assert r.json()["effective_status"] == "open"

    def test_decision_id_can_be_null(self, isolated_stack, auth_headers):
        r = _get_readiness("RES-TEST-OPEN", auth_headers)
        assert r.json()["decision_id"] is None

    def test_blocking_reasons_is_list(self, isolated_stack, auth_headers):
        r = _get_readiness("RES-TEST-OPEN", auth_headers)
        assert isinstance(r.json()["blocking_reasons"], list)
        assert len(r.json()["blocking_reasons"]) > 0

    def test_unknown_resolution_404(self, isolated_stack, auth_headers):
        r = _get_readiness("RES-DOES-NOT-EXIST", auth_headers)
        assert r.status_code == 404

    def test_ready_when_terminal_decision_and_verified_evidence(self, isolated_stack, auth_headers):
        _make_ready_for_closure()
        r = _get_readiness("RES-TEST-OPEN", auth_headers)
        assert r.json()["is_ready"] is True
        assert r.json()["decision_id"] is not None

    def test_corrupted_evidence_reflected_in_response(self, isolated_stack, auth_headers):
        _make_ready_for_closure()
        payload = json.loads(isolated_stack["evidence_path"].read_text(encoding="utf-8"))
        payload["evidence"][0]["title"] = "Tampered by hand"
        isolated_stack["evidence_path"].write_text(json.dumps(payload), encoding="utf-8")
        we_store.reload()
        r = _get_readiness("RES-TEST-OPEN", auth_headers)
        # evaluate_closure_readiness() classifies corrupted evidence
        # internally rather than raising -- service contract preserved:
        # readiness reports is_ready=False with the corruption visible.
        assert r.status_code == 200
        assert r.json()["is_ready"] is False
        assert len(r.json()["corrupted_evidence_ids"]) == 1


# =======================================================================
# CLOSE POST (27-38)
# =======================================================================


class TestClosePost:
    def test_successful_close_200(self, isolated_stack, auth_headers):
        _make_ready_for_closure()
        r = _post_close("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 200, r.text

    def test_response_wrapper_closure(self, isolated_stack, auth_headers):
        _make_ready_for_closure()
        r = _post_close("RES-TEST-OPEN", auth_headers)
        assert "closure" in r.json()

    def test_backend_generated_closed_at(self, isolated_stack, auth_headers):
        _make_ready_for_closure()
        r = _post_close("RES-TEST-OPEN", auth_headers)
        assert r.json()["closure"]["closed_at"].endswith("Z")

    def test_backend_generated_closure_id(self, isolated_stack, auth_headers):
        _make_ready_for_closure()
        r = _post_close("RES-TEST-OPEN", auth_headers)
        assert r.json()["closure"]["closure_id"].startswith("CLR-")

    @pytest.mark.parametrize(
        "extra_field,extra_value",
        [
            ("closed_at", "2026-01-01T00:00:00.000000Z"),
            ("closure_id", "CLR-forged"),
            ("integrity_checksum", "a" * 64),
        ],
    )
    def test_backend_generated_field_in_request_rejected_422(
        self, isolated_stack, auth_headers, extra_field, extra_value
    ):
        body = {"closure_rationale": "r", "closed_by": "ilhan", extra_field: extra_value}
        r = _post_close("RES-TEST-OPEN", auth_headers, body=body)
        assert r.status_code == 422, r.text

    def test_unknown_resolution_404(self, isolated_stack, auth_headers):
        r = _post_close("RES-DOES-NOT-EXIST", auth_headers)
        assert r.status_code == 404

    def test_not_ready_409(self, isolated_stack, auth_headers):
        r = _post_close("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 409

    def test_duplicate_closure_409(self, isolated_stack, auth_headers):
        _make_ready_for_closure()
        _post_close("RES-TEST-OPEN", auth_headers)
        r = _post_close("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 409

    def test_blocked_authoritative_source_409(self, isolated_stack, auth_headers):
        r = _post_close("RES-TEST-BLOCKED", auth_headers)
        assert r.status_code == 409

    def test_closure_integrity_error_mapped_422(self, isolated_stack, auth_headers, monkeypatch):
        monkeypatch.setattr(
            svc, "close_resolution",
            lambda **kwargs: (_ for _ in ()).throw(svc.ClosureIntegrityError("RES-TEST-OPEN")),
        )
        r = _post_close("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 422


# =======================================================================
# CLOSURE GET (39-42)
# =======================================================================


class TestClosureGet:
    def test_closure_exists_200_with_object(self, isolated_stack, auth_headers):
        _make_ready_for_closure()
        _post_close("RES-TEST-OPEN", auth_headers)
        r = _get_closure("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 200
        assert r.json()["closure"] is not None
        assert r.json()["closure"]["closure_status"] == "closed"

    def test_closure_absent_200_with_null(self, isolated_stack, auth_headers):
        r = _get_closure("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 200
        assert r.json() == {"closure": None}

    def test_unknown_resolution_404(self, isolated_stack, auth_headers):
        r = _get_closure("RES-DOES-NOT-EXIST", auth_headers)
        assert r.status_code == 404

    def test_closure_integrity_error_mapped_422(self, isolated_stack, auth_headers, monkeypatch):
        monkeypatch.setattr(
            svc, "get_resolution_closure",
            lambda resolution_id: (_ for _ in ()).throw(svc.ClosureIntegrityError(resolution_id)),
        )
        r = _get_closure("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 422


# =======================================================================
# GENERIC ERROR (43-44)
# =======================================================================


class TestGenericError:
    def test_unexpected_exception_mapped_500(self, isolated_stack, auth_headers, monkeypatch):
        monkeypatch.setattr(
            svc, "resolution_evidence_for",
            lambda resolution_id: (_ for _ in ()).throw(RuntimeError("kaboom: /secret/path/leak")),
        )
        r = _get_evidence("RES-TEST-OPEN", auth_headers)
        assert r.status_code == 500

    def test_500_response_does_not_leak_internal_detail(self, isolated_stack, auth_headers, monkeypatch):
        monkeypatch.setattr(
            svc, "resolution_evidence_for",
            lambda resolution_id: (_ for _ in ()).throw(RuntimeError("kaboom: /secret/path/leak")),
        )
        r = _get_evidence("RES-TEST-OPEN", auth_headers)
        assert "kaboom" not in r.text
        assert "/secret/path" not in r.text


# =======================================================================
# BACKWARD COMPATIBILITY (45-49)
# =======================================================================


class TestBackwardCompatibility:
    def test_existing_queue_endpoint_works(self, isolated_stack, auth_headers):
        r = client.get(f"{BASE}/queue", headers=auth_headers)
        assert r.status_code == 200

    def test_existing_detail_endpoint_works(self, isolated_stack, auth_headers):
        r = client.get(f"{BASE}/RES-TEST-OPEN", headers=auth_headers)
        assert r.status_code == 200

    def test_existing_decide_endpoint_works(self, isolated_stack, auth_headers):
        r = client.post(
            f"{BASE}/RES-TEST-OPEN/decide",
            headers=auth_headers,
            json={
                "new_status": "resolved", "resolution_note": "n", "evidence_reference": "e",
                "resolved_by": "ilhan", "idempotency_key": "idem-compat-check",
            },
        )
        assert r.status_code == 200

    def test_router_included_exactly_once(self):
        count = sum(
            1 for r in app.router.routes
            if type(r).__name__ == "_IncludedRouter"
        )
        # production_validation, governance, joints, washer_resolution_closure
        assert count == 4

    def test_five_new_routes_registered_exactly_once(self):
        expected_new_paths = {
            ("POST", f"{BASE}/{{resolution_id}}/evidence"),
            ("GET", f"{BASE}/{{resolution_id}}/evidence"),
            ("GET", f"{BASE}/{{resolution_id}}/closure-readiness"),
            ("POST", f"{BASE}/{{resolution_id}}/close"),
            ("GET", f"{BASE}/{{resolution_id}}/closure"),
        }
        from backend.api.routes.washer_resolution_closure import router as new_router
        found = set()
        for r in new_router.routes:
            for method in r.methods:
                found.add((method, r.path))
        assert found == expected_new_paths


# =======================================================================
# REAL LEDGER SAFETY (50)
# =======================================================================


def test_real_ledgers_unchanged_after_full_flow(isolated_stack, auth_headers):
    """Runs a full evidence + close HTTP flow against the *isolated*
    stack, then reads the four real, committed data files directly
    from their fixed repository paths (independent of any
    monkeypatch state) to confirm none of them changed."""
    _make_ready_for_closure()
    _post_close("RES-TEST-OPEN", auth_headers)

    repo_data_dir = pathlib.Path(__file__).resolve().parent.parent / "backend" / "library" / "data"

    real_ledger = json.loads((repo_data_dir / "washer_resolution_ledger.json").read_text(encoding="utf-8"))
    real_decisions = json.loads((repo_data_dir / "washer_resolution_decisions.json").read_text(encoding="utf-8"))
    real_evidence = json.loads((repo_data_dir / "washer_resolution_evidence.json").read_text(encoding="utf-8"))
    real_closure = json.loads((repo_data_dir / "washer_resolution_closure.json").read_text(encoding="utf-8"))

    assert real_decisions["decisions"] == []
    assert real_evidence["evidence"] == []
    assert real_closure["closures"] == []
    assert len(real_ledger.get("records", [])) == 76
