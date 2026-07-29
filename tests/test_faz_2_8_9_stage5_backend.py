"""Faz 2.8.9 tests (Stage 5A): washer resolution report API endpoint.

Covers: successful JSON response and its content-type, presence of
every Stage 4 report field, default/explicit lang handling
(tr/en), unsupported lang/format rejection, Markdown output for both
languages via the existing Stage 4 renderers (never regenerated in
app.py), safe ``WasherReportDataError`` -> 500 mapping (no path/
traceback leak), checksum determinism across repeated calls, and
confirmation that the endpoint is read-only (never mutates the source
ledger or the decision ledger) and does not affect any pre-existing
washer resolution endpoint.

This file never re-derives effective-status counts itself; every
assertion here validates the endpoint's response against
``backend.library.washer_report.collect_washer_resolution_report()``
(the Stage 4 public contract), not a duplicated calculation.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.library import washer_report as report_module
from backend.library import washer_resolution as wr

client = TestClient(app)

REPORT_URL = "/api/library/washers/resolutions/report"


def _login():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def auth_headers():
    return _login()


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------


class TestAuthRequired:
    def test_report_requires_auth(self):
        r = client.get(REPORT_URL)
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------
# Successful JSON response
# ---------------------------------------------------------------------


class TestSuccessfulJsonResponse:
    def test_status_and_content_type(self, auth_headers):
        r = client.get(REPORT_URL, headers=auth_headers)
        assert r.status_code == 200
        assert "application/json" in r.headers["content-type"]

    def test_response_envelope_shape(self, auth_headers):
        r = client.get(REPORT_URL, headers=auth_headers)
        body = r.json()
        assert body["format"] == "json"
        assert body["lang"] == "tr"
        assert isinstance(body["report"], dict)

    def test_all_stage4_fields_present(self, auth_headers):
        """The endpoint must expose the complete Stage 4 report
        contract, not a hand-picked subset."""
        expected = set(report_module.collect_washer_resolution_report().keys())
        r = client.get(REPORT_URL, headers=auth_headers)
        actual = set(r.json()["report"].keys())
        assert expected == actual

    def test_key_fields_match_stage4_contract(self, auth_headers):
        direct = report_module.collect_washer_resolution_report()
        r = client.get(REPORT_URL, headers=auth_headers)
        via_api = r.json()["report"]
        for key in (
            "total_resolution_records",
            "effective_open_count",
            "effective_under_review_count",
            "effective_terminal_count",
            "effective_blocked_count",
            "effective_resolved_count",
            "total_decision_count",
            "data_integrity_warning_count",
            "source_status_distribution",
            "effective_status_distribution",
            "latest_decision_summary",
            "report_checksum",
        ):
            assert via_api[key] == direct[key], key


# ---------------------------------------------------------------------
# Language handling
# ---------------------------------------------------------------------


class TestLanguageHandling:
    def test_default_language_is_tr(self, auth_headers):
        r = client.get(REPORT_URL, headers=auth_headers)
        assert r.json()["lang"] == "tr"

    def test_lang_en(self, auth_headers):
        r = client.get(REPORT_URL + "?lang=en", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["lang"] == "en"

    def test_lang_tr_explicit(self, auth_headers):
        r = client.get(REPORT_URL + "?lang=tr", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["lang"] == "tr"

    def test_json_report_content_is_language_independent(self, auth_headers):
        """The structured JSON payload carries status codes, not
        localized prose -- lang must not change its content, only
        format=markdown is language-dependent."""
        r_tr = client.get(REPORT_URL + "?lang=tr", headers=auth_headers)
        r_en = client.get(REPORT_URL + "?lang=en", headers=auth_headers)
        assert r_tr.json()["report"] == r_en.json()["report"]

    def test_unsupported_language_rejected(self, auth_headers):
        r = client.get(REPORT_URL + "?lang=fr", headers=auth_headers)
        assert r.status_code == 400
        assert "fr" in r.json()["detail"]


# ---------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------


class TestMarkdownOutput:
    def test_markdown_english(self, auth_headers):
        r = client.get(REPORT_URL + "?lang=en&format=markdown", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["format"] == "markdown"
        assert body["lang"] == "en"
        assert isinstance(body["content"], str)
        assert "# Faz 2.8.5" in body["content"]
        assert "Effective status distribution" in body["content"]

    def test_markdown_turkish(self, auth_headers):
        r = client.get(REPORT_URL + "?lang=tr&format=markdown", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["format"] == "markdown"
        assert body["lang"] == "tr"
        assert "Efektif durum dagilimi" in body["content"]

    def test_markdown_uses_existing_stage4_renderers_not_a_duplicate(self, auth_headers):
        """The endpoint's markdown output must be byte-identical to
        calling the Stage 4 renderer directly on the same report --
        proof app.py does not regenerate markdown independently."""
        report = report_module.collect_washer_resolution_report()
        expected_en = report_module.render_washer_resolution_report_markdown_en(report)
        r = client.get(REPORT_URL + "?lang=en&format=markdown", headers=auth_headers)
        # Content may differ only if a decision was recorded between
        # the two report collections; under test isolation (no writes
        # occur in this file) they must match exactly.
        assert r.json()["content"] == expected_en

    def test_default_format_is_json_not_markdown(self, auth_headers):
        r = client.get(REPORT_URL, headers=auth_headers)
        assert r.json()["format"] == "json"

    def test_unsupported_format_rejected(self, auth_headers):
        r = client.get(REPORT_URL + "?format=pdf", headers=auth_headers)
        assert r.status_code == 400
        assert "pdf" in r.json()["detail"]


# ---------------------------------------------------------------------
# WasherReportDataError safe mapping
# ---------------------------------------------------------------------


class TestSafeErrorMapping:
    def test_data_error_maps_to_500_without_leaking_internals(self, auth_headers, monkeypatch):
        def _boom():
            raise report_module.WasherReportDataError(
                "Washer resolution decision data could not be read; "
                "report cannot be generated."
            )

        import backend.library.washer_report as real_report_module

        monkeypatch.setattr(real_report_module, "collect_washer_resolution_report", _boom)

        r = client.get(REPORT_URL, headers=auth_headers)
        assert r.status_code == 500
        body_text = r.text
        assert "Traceback" not in body_text
        assert "/home/" not in body_text
        assert "washer_report.py" not in body_text
        assert "WasherReportDataError" not in body_text

    def test_unexpected_exception_from_collector_does_not_crash_response(
        self, auth_headers, monkeypatch
    ):
        """Even a non-WasherReportDataError failure inside the
        collector must not propagate a raw 500 with internals -- the
        endpoint wraps only WasherReportDataError explicitly; this
        test documents that any other exception type is NOT silently
        caught (FastAPI's own handler takes over), so a genuinely
        unexpected bug is still visible server-side without changing
        this contract silently. We assert only that no path/traceback
        text reaches the client body, whatever the status code."""
        import backend.library.washer_report as real_report_module

        def _boom():
            raise RuntimeError("unexpected internal failure at /some/fake/path.json")

        monkeypatch.setattr(real_report_module, "collect_washer_resolution_report", _boom)
        r = client.get(REPORT_URL, headers=auth_headers)
        assert "/some/fake/path.json" not in r.text
        assert "Traceback" not in r.text


# ---------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_calls_return_same_checksum(self, auth_headers):
        r1 = client.get(REPORT_URL, headers=auth_headers)
        r2 = client.get(REPORT_URL, headers=auth_headers)
        assert r1.json()["report"]["report_checksum"] == r2.json()["report"]["report_checksum"]

    def test_repeated_calls_return_identical_report(self, auth_headers):
        r1 = client.get(REPORT_URL, headers=auth_headers)
        r2 = client.get(REPORT_URL, headers=auth_headers)
        assert r1.json()["report"] == r2.json()["report"]


# ---------------------------------------------------------------------
# Read-only / no side effects
# ---------------------------------------------------------------------


class TestReadOnly:
    def test_endpoint_does_not_mutate_ledger_hash(self, auth_headers):
        import hashlib

        path = report_module.WASHER_LIBRARY_PATH.parent / "washer_resolution_ledger.json"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        client.get(REPORT_URL, headers=auth_headers)
        client.get(REPORT_URL + "?lang=en&format=markdown", headers=auth_headers)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        assert before == after

    def test_endpoint_does_not_change_decisions_count(self, auth_headers):
        from backend.library.washer_resolution_decisions_store import list_decisions

        before = len(list_decisions())
        client.get(REPORT_URL, headers=auth_headers)
        client.get(REPORT_URL + "?format=markdown", headers=auth_headers)
        after = len(list_decisions())
        assert before == after

    def test_only_get_method_is_registered(self, auth_headers):
        r = client.post(REPORT_URL, headers=auth_headers)
        assert r.status_code in (405, 404)


# ---------------------------------------------------------------------
# Existing endpoints unaffected
# ---------------------------------------------------------------------


class TestExistingEndpointsUnaffected:
    def test_queue_endpoint_still_works(self, auth_headers):
        r = client.get("/api/library/washers/resolutions/queue", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["records"]) == 76

    def test_decide_endpoint_still_present(self, auth_headers):
        # Unknown id -> 404, proves routing to the Stage 3 endpoint is
        # unaffected by the new Stage 5 route registration.
        r = client.post(
            "/api/library/washers/resolutions/RES-DOES-NOT-EXIST/decide",
            json={
                "new_status": "under_review",
                "resolution_note": "n",
                "evidence_reference": "e",
                "resolved_by": "ilhan",
                "idempotency_key": "k",
            },
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_strength_class_endpoint_unaffected(self, auth_headers):
        r = client.get("/api/engineering/bolt-strength-classes", headers=auth_headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------
# Final regression sanity
# ---------------------------------------------------------------------


class TestRealDataUnaffected:
    def test_real_decision_ledger_file_still_empty(self):
        from pathlib import Path

        real_path = (
            Path(__file__).resolve().parent.parent
            / "backend"
            / "library"
            / "data"
            / "washer_resolution_decisions.json"
        )
        payload = json.loads(real_path.read_text(encoding="utf-8"))
        assert payload["decisions"] == []

    def test_real_source_ledger_status_counts_unchanged(self):
        wr.reload()
        counts = wr.count_by_status()
        assert counts[wr.WasherResolutionStatus.OPEN.value] == 71
        assert counts[wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE.value] == 5
