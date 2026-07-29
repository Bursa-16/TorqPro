"""Faz 2.8.9 tests (Stage 4): washer resolution report expansion.

Covers: effective-status aggregation (open/under_review/terminal/
blocked/resolved) computed via the Faz 2.8.9 decision ledger overlay
on top of the immutable Faz 2.8.5 source ledger, issue_type
distribution stability, "resolved" count coming only from real
terminal decisions (never inferred), deterministic ordering/JSON/
checksum, TR/EN section parity, and safe handling of missing/corrupt
decision data (no crash, no path/traceback leak).

Every test's decision-ledger writes go through
``backend.library.washer_resolution_decisions_store`` with
``DATA_PATH``/``_LOCK_PATH`` monkeypatched to an isolated ``tmp_path``
file. The real, committed ``washer_resolution_decisions.json`` and
``washer_resolution_ledger.json`` are never written to by this file.
"""

from __future__ import annotations

import json

import pytest

from backend.library import washer_report as report_module
from backend.library import washer_resolution as wr
from backend.library import washer_resolution_decisions_store as store
from backend.library import washer_resolution_service as svc

OPEN_A = "RES-WASH-DIN127B-M10"
OPEN_B = "RES-WASH-DIN127B-M12"
OPEN_C = "RES-WASH-DIN127B-M14"
BLOCKED = "RES-WASH-ISO7093-M10"


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


def _decide(resolution_id, new_status, idempotency_key, resolution_note="note"):
    return svc.decide_resolution(
        resolution_id=resolution_id,
        new_status=wr.WasherResolutionStatus(new_status),
        resolution_note=resolution_note,
        evidence_reference="evidence",
        resolved_by="ilhan",
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------
# No decisions yet
# ---------------------------------------------------------------------


class TestNoDecisions:
    def test_report_with_no_decisions_matches_source_distribution(self, isolated_ledger):
        report = report_module.collect_washer_resolution_report()
        assert report["effective_open_count"] == 71
        assert report["effective_blocked_count"] == 5
        assert report["effective_under_review_count"] == 0
        assert report["effective_terminal_count"] == 0
        assert report["effective_resolved_count"] == 0
        assert report["total_decision_count"] == 0
        assert report["latest_decision_summary"] == []
        assert report["data_integrity_warning_count"] == 0

    def test_existing_fields_unchanged_when_no_decisions(self, isolated_ledger):
        report = report_module.collect_washer_resolution_report()
        assert report["total_washer_records"] == 223
        assert report["open_resolution_count"] == 71
        assert report["resolved_count"] == 0  # existing source-status field, untouched
        assert report["blocked_authoritative_source_count"] == 5


# ---------------------------------------------------------------------
# Single-record scenarios
# ---------------------------------------------------------------------


class TestSingleRecordScenarios:
    def test_open_record_no_decision_counts_as_effective_open(self, isolated_ledger):
        report = report_module.collect_washer_resolution_report()
        assert report["effective_open_count"] == 71

    def test_under_review_decision(self, isolated_ledger):
        _decide(OPEN_A, "under_review", "k1")
        report = report_module.collect_washer_resolution_report()
        assert report["effective_under_review_count"] == 1
        assert report["effective_open_count"] == 70
        assert report["effective_resolved_count"] == 0

    def test_valid_terminal_resolution(self, isolated_ledger):
        _decide(OPEN_A, "resolved", "k1")
        report = report_module.collect_washer_resolution_report()
        assert report["effective_resolved_count"] == 1
        assert report["effective_terminal_count"] == 1
        assert report["effective_open_count"] == 70

    def test_terminal_accepted_as_is_counts_as_terminal_not_resolved(self, isolated_ledger):
        _decide(OPEN_A, "accepted_as_is", "k1")
        report = report_module.collect_washer_resolution_report()
        assert report["effective_terminal_count"] == 1
        assert report["effective_resolved_count"] == 0  # only real "resolved" counts here

    def test_blocked_record_stays_blocked(self, isolated_ledger):
        report = report_module.collect_washer_resolution_report()
        assert report["effective_blocked_count"] == 5
        # Sanity: attempting to decide a blocked record must fail and
        # must not be reflected in the report at all.
        with pytest.raises(svc.BlockedRecordDecisionError):
            _decide(BLOCKED, "resolved", "k-blocked")
        report_after = report_module.collect_washer_resolution_report()
        assert report_after["effective_blocked_count"] == 5
        assert report_after["total_decision_count"] == 0


# ---------------------------------------------------------------------
# Multiple washers / mixed effective statuses
# ---------------------------------------------------------------------


class TestMixedScenarios:
    def test_multiple_washers_mixed_statuses(self, isolated_ledger):
        _decide(OPEN_A, "under_review", "k1")
        _decide(OPEN_B, "resolved", "k2")
        _decide(OPEN_C, "rejected", "k3")
        report = report_module.collect_washer_resolution_report()
        assert report["effective_under_review_count"] == 1
        assert report["effective_terminal_count"] == 2  # resolved + rejected
        assert report["effective_resolved_count"] == 1
        assert report["effective_blocked_count"] == 5
        assert report["effective_open_count"] == 71 - 3
        assert report["total_decision_count"] == 3

    def test_issue_type_distribution_unaffected_by_decisions(self, isolated_ledger):
        before = report_module.collect_washer_resolution_report()["issue_type_distribution"]
        _decide(OPEN_A, "resolved", "k1")
        _decide(OPEN_B, "under_review", "k2")
        after = report_module.collect_washer_resolution_report()["issue_type_distribution"]
        assert before == after

    def test_latest_decision_in_history_wins_effective_status(self, isolated_ledger):
        _decide(OPEN_A, "under_review", "k1")
        _decide(OPEN_A, "resolved", "k2")
        report = report_module.collect_washer_resolution_report()
        assert report["effective_resolved_count"] == 1
        assert report["effective_under_review_count"] == 0
        row = next(
            r for r in report["latest_decision_summary"] if r["resolution_id"] == OPEN_A
        )
        assert row["last_decision_new_status"] == "resolved"
        assert row["decision_count"] == 2

    def test_resolved_count_only_from_real_terminal_decisions(self, isolated_ledger):
        # No "resolved" decisions anywhere -> must be exactly 0, never
        # inferred from the 71 open + 5 blocked records.
        report = report_module.collect_washer_resolution_report()
        assert report["effective_resolved_count"] == 0
        _decide(OPEN_A, "under_review", "k1")  # not terminal
        report2 = report_module.collect_washer_resolution_report()
        assert report2["effective_resolved_count"] == 0


# ---------------------------------------------------------------------
# Source ledger immutability
# ---------------------------------------------------------------------


class TestSourceLedgerUnmutated:
    def test_source_status_counts_unchanged_after_decisions(self, isolated_ledger):
        before = dict(wr.count_by_status())
        _decide(OPEN_A, "resolved", "k1")
        _decide(OPEN_B, "under_review", "k2")
        report_module.collect_washer_resolution_report()
        wr.reload()
        after = dict(wr.count_by_status())
        assert before == after
        assert after[wr.WasherResolutionStatus.OPEN.value] == 71
        assert after[wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE.value] == 5


# ---------------------------------------------------------------------
# Determinism / checksum
# ---------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_calls_identical(self, isolated_ledger):
        _decide(OPEN_A, "resolved", "k1")
        r1 = report_module.collect_washer_resolution_report()
        r2 = report_module.collect_washer_resolution_report()
        assert r1 == r2

    def test_json_rendering_is_byte_identical(self, isolated_ledger):
        _decide(OPEN_A, "under_review", "k1")
        r1 = report_module.collect_washer_resolution_report()
        r2 = report_module.collect_washer_resolution_report()
        j1 = report_module.render_washer_resolution_report_json(r1)
        j2 = report_module.render_washer_resolution_report_json(r2)
        assert j1 == j2

    def test_latest_decision_summary_order_deterministic(self, isolated_ledger):
        _decide(OPEN_C, "resolved", "k3")
        _decide(OPEN_A, "resolved", "k1")
        _decide(OPEN_B, "resolved", "k2")
        report = report_module.collect_washer_resolution_report()
        ids = [row["resolution_id"] for row in report["latest_decision_summary"]]
        assert ids == sorted(ids)

    def test_checksum_stable_for_same_content(self, isolated_ledger):
        _decide(OPEN_A, "resolved", "k1")
        r1 = report_module.collect_washer_resolution_report()
        r2 = report_module.collect_washer_resolution_report()
        assert r1["report_checksum"] == r2["report_checksum"]

    def test_checksum_changes_with_different_content(self, isolated_ledger):
        r_before = report_module.collect_washer_resolution_report()
        _decide(OPEN_A, "resolved", "k1")
        r_after = report_module.collect_washer_resolution_report()
        assert r_before["report_checksum"] != r_after["report_checksum"]

    def test_decision_insertion_order_across_resolutions_does_not_affect_aggregate(
        self, isolated_ledger
    ):
        """Two semantically-independent decision histories recorded in
        different relative order must still produce the same
        aggregate report, since each resolution's effective status
        only depends on its own history, not cross-resolution
        ordering."""
        _decide(OPEN_A, "resolved", "k1")
        _decide(OPEN_B, "under_review", "k2")
        report_order_1 = report_module.collect_washer_resolution_report()

        store.reload()
        # Rebuild ledger from scratch with the two decisions swapped.
        isolated_ledger.write_text(
            json.dumps({"metadata": {"record_count": 0}, "decisions": []}),
            encoding="utf-8",
        )
        store.reload()
        _decide(OPEN_B, "under_review", "k2-swap")
        _decide(OPEN_A, "resolved", "k1-swap")
        report_order_2 = report_module.collect_washer_resolution_report()

        for key in (
            "effective_open_count",
            "effective_under_review_count",
            "effective_terminal_count",
            "effective_resolved_count",
            "effective_blocked_count",
            "total_decision_count",
            "effective_status_distribution",
        ):
            assert report_order_1[key] == report_order_2[key]


# ---------------------------------------------------------------------
# TR/EN parity
# ---------------------------------------------------------------------


class TestTrEnParity:
    def test_same_number_of_sections(self, isolated_ledger):
        _decide(OPEN_A, "resolved", "k1")
        report = report_module.collect_washer_resolution_report()
        md_tr = report_module.render_washer_resolution_report_markdown(report)
        md_en = report_module.render_washer_resolution_report_markdown_en(report)
        assert md_tr.count("## ") == md_en.count("## ")

    def test_both_languages_contain_new_effective_fields(self, isolated_ledger):
        _decide(OPEN_A, "resolved", "k1")
        report = report_module.collect_washer_resolution_report()
        md_tr = report_module.render_washer_resolution_report_markdown(report)
        md_en = report_module.render_washer_resolution_report_markdown_en(report)
        assert str(report["effective_resolved_count"]) in md_tr
        assert str(report["effective_resolved_count"]) in md_en
        assert report["report_checksum"] in md_tr
        assert report["report_checksum"] in md_en

    def test_no_latest_decision_section_when_empty(self, isolated_ledger):
        report = report_module.collect_washer_resolution_report()
        md_tr = report_module.render_washer_resolution_report_markdown(report)
        md_en = report_module.render_washer_resolution_report_markdown_en(report)
        assert "Son karar ozeti" not in md_tr
        assert "Latest decision summary" not in md_en


# ---------------------------------------------------------------------
# Safe handling of missing/corrupt decision data
# ---------------------------------------------------------------------


class TestSafeErrorHandling:
    def test_fully_corrupted_ledger_raises_clean_domain_error(self, isolated_ledger):
        isolated_ledger.write_text("{ not valid json at all", encoding="utf-8")
        store.reload()
        with pytest.raises(report_module.WasherReportDataError) as exc_info:
            report_module.collect_washer_resolution_report()
        message = str(exc_info.value)
        assert "Traceback" not in message
        assert str(isolated_ledger) not in message
        assert "/home/" not in message

    def test_per_record_decision_read_failure_is_isolated_and_counted(
        self, isolated_ledger, monkeypatch
    ):
        """Simulate a single corrupted decision-history read (not a
        whole-ledger failure) by monkeypatching only
        washer_report's own bound reference to
        decisions_for_resolution -- resolution_queue() (used for the
        aggregate counts) keeps working via its own untouched
        reference, so only the per-row 'latest decision' detail step
        degrades safely instead of crashing the whole report."""
        _decide(OPEN_A, "resolved", "k1")

        def _boom(resolution_id):
            raise RuntimeError("simulated corrupt decision record")

        monkeypatch.setattr(report_module, "decisions_for_resolution", _boom)

        report = report_module.collect_washer_resolution_report()
        assert report["data_integrity_warning_count"] == 1
        assert report["latest_decision_summary"] == []
        # Aggregate counts (from resolution_queue(), untouched) still correct.
        assert report["effective_resolved_count"] == 1


# ---------------------------------------------------------------------
# Final regression sanity (real files, not isolated_ledger)
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

    def test_real_report_generation_does_not_write_anything(self):
        """collect_washer_resolution_report() against the real, empty
        decision ledger must succeed and report zero decisions --
        proving report generation itself never writes."""
        wr.reload()
        store.reload()
        report = report_module.collect_washer_resolution_report()
        assert report["total_decision_count"] == 0
        assert report["effective_open_count"] == 71
        assert report["effective_blocked_count"] == 5
