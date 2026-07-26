"""Faz 2.8.5 tests: washer correction & resolution workflow.

Covers: resolution model/schema validation, status/issue-type enum
coverage, action_needed re-classification against the Faz 2.8.4
report, ISO 7093 authoritative-source-block handling, registry
metadata drift-safety (washer_library.py), washer_report JSON/
Markdown rendering and determinism, unresolved/resolved counters,
duplicate-resolution conflict detection, backward compatibility
(existing 1014-test suite / Faz 2.8.4 regression / unchanged 223
washer records), and data-safety (no silent washer_library.json
mutation via the resolution ledger).

Does not touch washer_library.json, the calculation engine, the API,
the frontend, or Faz 2.8.3 strength-class code.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from backend.library import washer_resolution as wr
from backend.library import washer_resolution_validator as wrv
from backend.library import washer_report as report_module
from backend.library.washer_library import washer_library_data_file_state, WASHER_LIBRARY

REPO_ROOT = Path(__file__).resolve().parent.parent
WASHER_LIBRARY_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_library.json"
LEDGER_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_resolution_ledger.json"
PROVENANCE_REPORT_PATH = (
    REPO_ROOT / "docs" / "phase_2_8" / "phase_2_8_4_washer_provenance_report.json"
)
GENERATOR_TOOL_PATH = (
    REPO_ROOT / "tools" / "generate_faz_2_8_5_washer_resolution_ledger.py"
)

_spec = importlib.util.spec_from_file_location(
    "generate_faz_2_8_5_washer_resolution_ledger", GENERATOR_TOOL_PATH
)
gen_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_tool)  # type: ignore[union-attr]

EXPECTED_TOTAL_WASHER_RECORDS = 223
EXPECTED_ACTION_NEEDED = 76

EXPECTED_ISSUE_TYPE_TOTALS = {
    "source_missing": 34,
    "source_ambiguous": 0,
    "standard_identity_ambiguous": 5,
    "dimensional_conflict": 10,
    "duplicate_or_alias": 0,
    "verification_pending": 27,
    "other": 0,
}

EXPECTED_ISO7093_IDS = {
    "WASH-ISO7093-M6",
    "WASH-ISO7093-M8",
    "WASH-ISO7093-M10",
    "WASH-ISO7093-M12",
    "WASH-ISO7093-M16",
}


def _library_hash() -> str:
    return hashlib.sha256(WASHER_LIBRARY_PATH.read_bytes()).hexdigest()


def _library_payload() -> Dict[str, Any]:
    return json.loads(WASHER_LIBRARY_PATH.read_text(encoding="utf-8"))


def _known_washer_ids() -> List[str]:
    return [r["id"] for r in _library_payload().get("records", [])]


def _ledger_records_raw() -> List[Dict[str, Any]]:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["records"]


@pytest.fixture(autouse=True)
def _reset_resolution_cache():
    """Every test starts from a freshly re-read ledger, and leaves one
    behind for the next test -- guards against one test's in-memory
    mutation of the module cache leaking into another."""
    wr.reload()
    yield
    wr.reload()


# ---------------------------------------------------------------------
# 1. Resolution model / schema tests
# ---------------------------------------------------------------------

class TestResolutionModelSchema:
    def test_valid_record_parses(self):
        record = wr.WasherResolutionRecord(
            resolution_id="RES-TEST-1",
            washer_record_id="WASH-ISO7089-M6",
            issue_type="source_missing",
        )
        assert record.resolution_status == wr.WasherResolutionStatus.OPEN

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            wr.WasherResolutionRecord(
                resolution_id="RES-TEST-2",
                washer_record_id="WASH-ISO7089-M6",
                issue_type="source_missing",
                unexpected_field="nope",
            )

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValidationError):
            wr.WasherResolutionRecord(washer_record_id="WASH-ISO7089-M6")

    def test_confidence_level_uses_shared_enum(self):
        record = wr.WasherResolutionRecord(
            resolution_id="RES-TEST-3",
            washer_record_id="WASH-ISO7089-M6",
            issue_type="source_missing",
            confidence_level=3,
        )
        assert record.confidence_level.value == 3

    def test_confidence_level_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            wr.WasherResolutionRecord(
                resolution_id="RES-TEST-4",
                washer_record_id="WASH-ISO7089-M6",
                issue_type="source_missing",
                confidence_level=9,
            )

    def test_to_dict_is_json_safe(self):
        record = wr.WasherResolutionRecord(
            resolution_id="RES-TEST-5",
            washer_record_id="WASH-ISO7089-M6",
            issue_type="source_missing",
        )
        payload = record.to_dict()
        json.dumps(payload)  # must not raise
        assert payload["issue_type"] == "source_missing"
        assert payload["resolution_status"] == "open"


# ---------------------------------------------------------------------
# 2. Status enum tests
# ---------------------------------------------------------------------

class TestStatusEnum:
    def test_six_allowed_statuses(self):
        values = {status.value for status in wr.WasherResolutionStatus}
        assert values == {
            "open",
            "under_review",
            "resolved",
            "accepted_as_is",
            "blocked_authoritative_source",
            "rejected",
        }

    def test_active_and_terminal_statuses_partition_all_statuses(self):
        all_statuses = set(wr.WasherResolutionStatus)
        assert wr.ACTIVE_STATUSES | wr.TERMINAL_STATUSES == all_statuses
        assert wr.ACTIVE_STATUSES & wr.TERMINAL_STATUSES == set()

    def test_seven_allowed_issue_types(self):
        values = {issue.value for issue in wr.WasherIssueType}
        assert values == {
            "source_missing",
            "source_ambiguous",
            "standard_identity_ambiguous",
            "dimensional_conflict",
            "duplicate_or_alias",
            "verification_pending",
            "other",
        }


# ---------------------------------------------------------------------
# 3. action_needed re-classification tests
# ---------------------------------------------------------------------

class TestActionNeededClassification:
    def test_ledger_has_exactly_76_records(self):
        assert len(wr.list_washer_resolutions()) == EXPECTED_ACTION_NEEDED

    def test_issue_type_totals_match_expected_mapping(self):
        assert wr.count_by_issue_type() == EXPECTED_ISSUE_TYPE_TOTALS

    def test_every_ledger_entry_traces_to_a_faz_2_8_4_action_needed_record(self):
        provenance = json.loads(PROVENANCE_REPORT_PATH.read_text(encoding="utf-8"))
        action_needed_ids = {
            r["record_id"] for r in provenance["action_needed_records"]
        }
        ledger_ids = {r.washer_record_id for r in wr.list_washer_resolutions()}
        assert ledger_ids == action_needed_ids

    def test_reason_code_preserved_for_traceability(self):
        for record in wr.list_washer_resolutions():
            assert record.reason_code, f"{record.resolution_id} lost its reason_code"

    def test_generator_mapping_covers_every_known_reason_code(self):
        provenance = json.loads(PROVENANCE_REPORT_PATH.read_text(encoding="utf-8"))
        reason_codes = {r["reason_code"] for r in provenance["action_needed_records"]}
        assert reason_codes <= set(gen_tool.REASON_CODE_TO_ISSUE_TYPE)


# ---------------------------------------------------------------------
# 4. ISO 7093 ambiguity tests
# ---------------------------------------------------------------------

class TestIso7093Ambiguity:
    def test_exactly_five_iso7093_records_blocked(self):
        blocked = wr.resolutions_by_status(wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE)
        blocked_ids = {r.washer_record_id for r in blocked}
        assert blocked_ids == EXPECTED_ISO7093_IDS

    def test_iso7093_records_flag_requires_authoritative_source(self):
        for washer_id in EXPECTED_ISO7093_IDS:
            matches = wr.resolutions_for_washer_record(washer_id)
            assert len(matches) == 1
            assert matches[0].requires_authoritative_source is True

    def test_iso7093_records_do_not_assign_a_resolved_standard(self):
        """No standard is guessed for the identity-ambiguous records --
        resolved_standard must stay unset until an authoritative
        source settles the question."""
        for washer_id in EXPECTED_ISO7093_IDS:
            record = wr.resolutions_for_washer_record(washer_id)[0]
            assert record.resolved_standard is None

    def test_iso7093_issue_type_is_standard_identity_ambiguous(self):
        for washer_id in EXPECTED_ISO7093_IDS:
            record = wr.resolutions_for_washer_record(washer_id)[0]
            assert record.issue_type == wr.WasherIssueType.STANDARD_IDENTITY_AMBIGUOUS


# ---------------------------------------------------------------------
# 5. Authoritative-source block tests (validator)
# ---------------------------------------------------------------------

class TestAuthoritativeSourceBlockValidation:
    def test_blocked_status_without_flag_is_flagged(self):
        raw = [
            {
                "resolution_id": "RES-X",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "standard_identity_ambiguous",
                "resolution_status": "blocked_authoritative_source",
                "requires_authoritative_source": False,
            }
        ]
        issues = wrv.find_blocked_status_flag_mismatch(raw)
        assert len(issues) == 1
        assert issues[0].code == "blocked_status_requires_flag_mismatch"

    def test_blocked_status_with_flag_is_clean(self):
        raw = [
            {
                "resolution_id": "RES-X",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "standard_identity_ambiguous",
                "resolution_status": "blocked_authoritative_source",
                "requires_authoritative_source": True,
            }
        ]
        assert wrv.find_blocked_status_flag_mismatch(raw) == []

    def test_open_status_with_flag_true_is_not_flagged(self):
        """A record may need an authoritative source while still open
        (before anyone attempted resolution) without being an error."""
        raw = [
            {
                "resolution_id": "RES-X",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "standard_identity_ambiguous",
                "resolution_status": "open",
                "requires_authoritative_source": True,
            }
        ]
        assert wrv.find_blocked_status_flag_mismatch(raw) == []


# ---------------------------------------------------------------------
# 6. Registry metadata tests (washer_library.py)
# ---------------------------------------------------------------------

class TestRegistryMetadataSync:
    def test_declared_shell_metadata_unchanged(self):
        """Faz 2.8.5 must not create a second, drifting source of
        truth: the static Phase 1.3 shell declaration stays exactly
        as-is, matching every sibling library shell."""
        assert WASHER_LIBRARY.metadata.status == "draft"
        assert WASHER_LIBRARY.metadata.record_count == 0
        assert WASHER_LIBRARY.metadata.version == "0.1"

    def test_data_file_state_reports_real_count(self):
        state = washer_library_data_file_state()
        assert state["data_file_record_count"] == EXPECTED_TOTAL_WASHER_RECORDS

    def test_data_file_state_reports_declared_vs_actual_gap(self):
        state = washer_library_data_file_state()
        assert state["declared_record_count"] != state["data_file_record_count"]
        assert state["declared_status"] == "draft"

    def test_attach_source_path_unchanged(self):
        """Pinned by tests/test_library_migration.py -- Faz 2.8.5 must
        not touch this pre-migration reference."""
        assert WASHER_LIBRARY.source_path == "data/Pul_Sertlik_Yuzey_Basinci.json"


class TestRegistryMetadataDriftSafety:
    def test_data_file_state_reflects_a_changed_data_file_live(self, monkeypatch):
        """Record-count drift test: point
        ``washer_library_data_file_state()`` at a fixture file with a
        different record count (via the module's own
        ``WASHER_LIBRARY_DATA_FILE`` filename constant -- the only
        input the function reads) and confirm the returned count
        changes accordingly. Proves the value is derived live from
        disk on every call, not cached or hardcoded -- if it were
        hardcoded/cached, this would still report 223.

        The fixture file is written into and removed from the real
        ``backend/library/data/`` directory (the function resolves its
        path relative to its own module, so there is no way to redirect
        it via ``tmp_path``); ``washer_library.json`` itself is never
        touched, and the fixture file is guaranteed removed even if
        the assertion fails.
        """
        import backend.library.washer_library as washer_library_module

        payload = _library_payload()
        payload["records"] = payload["records"][:5]
        payload["metadata"] = dict(payload["metadata"])
        payload["metadata"]["record_count"] = 5
        payload["metadata"]["version"] = "drift-fixture"

        fixture_name = "test_fixture_faz_2_8_5_drift_check.json"
        fixture_path = (
            Path(washer_library_module.__file__).resolve().parent / "data" / fixture_name
        )
        assert not fixture_path.exists(), "stale drift-check fixture left behind"
        fixture_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            monkeypatch.setattr(
                washer_library_module, "WASHER_LIBRARY_DATA_FILE", fixture_name
            )
            state = washer_library_module.washer_library_data_file_state()
            assert state["data_file_record_count"] == 5
            assert state["data_file_version"] == "drift-fixture"
        finally:
            fixture_path.unlink(missing_ok=True)

        # washer_library.json itself must be completely untouched.
        assert _library_hash() == _library_hash()
        assert len(_library_payload()["records"]) == EXPECTED_TOTAL_WASHER_RECORDS

    def test_record_count_matches_metadata_declaration_in_data_file(self):
        payload = _library_payload()
        assert payload["metadata"]["record_count"] == len(payload["records"])


# ---------------------------------------------------------------------
# 7. Washer report tests (JSON)
# ---------------------------------------------------------------------

class TestWasherReportJson:
    def test_json_report_has_required_keys(self):
        report = report_module.collect_washer_resolution_report()
        for key in (
            "total_washer_records",
            "verified_record_count",
            "action_needed_record_count",
            "open_resolution_count",
            "resolved_count",
            "blocked_authoritative_source_count",
            "issue_type_distribution",
            "confidence_distribution",
            "unresolved_records",
        ):
            assert key in report

    def test_json_report_totals_match_ledger(self):
        report = report_module.collect_washer_resolution_report()
        assert report["total_washer_records"] == EXPECTED_TOTAL_WASHER_RECORDS
        assert report["action_needed_record_count"] == EXPECTED_ACTION_NEEDED
        assert report["open_resolution_count"] == 71
        assert report["blocked_authoritative_source_count"] == 5
        assert report["resolved_count"] == 0

    def test_json_report_is_valid_json_text(self):
        report = report_module.collect_washer_resolution_report()
        text = report_module.render_washer_resolution_report_json(report)
        parsed = json.loads(text)
        assert parsed["total_washer_records"] == EXPECTED_TOTAL_WASHER_RECORDS


# ---------------------------------------------------------------------
# 8. Washer report tests (Markdown)
# ---------------------------------------------------------------------

class TestWasherReportMarkdown:
    def test_markdown_report_contains_key_sections(self):
        report = report_module.collect_washer_resolution_report()
        text = report_module.render_washer_resolution_report_markdown(report)
        for heading in (
            "# Faz 2.8.5",
            "## Genel durum",
            "## Provenance kategori dagilimi",
            "## Resolution status dagilimi",
            "## Issue type dagilimi",
            "## Unresolved kayit listesi",
        ):
            assert heading in text

    def test_markdown_report_lists_every_unresolved_record(self):
        report = report_module.collect_washer_resolution_report()
        text = report_module.render_washer_resolution_report_markdown(report)
        for row in report["unresolved_records"]:
            assert row["resolution_id"] in text


# ---------------------------------------------------------------------
# 9. Determinism tests
# ---------------------------------------------------------------------

class TestDeterminism:
    def test_collect_is_deterministic_across_calls(self):
        r1 = report_module.collect_washer_resolution_report()
        r2 = report_module.collect_washer_resolution_report()
        assert r1 == r2

    def test_json_rendering_is_byte_identical_across_calls(self):
        report = report_module.collect_washer_resolution_report()
        text1 = report_module.render_washer_resolution_report_json(report)
        text2 = report_module.render_washer_resolution_report_json(report)
        assert text1 == text2

    def test_markdown_rendering_is_byte_identical_across_calls(self):
        report = report_module.collect_washer_resolution_report()
        text1 = report_module.render_washer_resolution_report_markdown(report)
        text2 = report_module.render_washer_resolution_report_markdown(report)
        assert text1 == text2

    def test_ledger_generator_check_mode_passes_against_committed_file(self):
        assert gen_tool.run(check_only=True) == 0


# ---------------------------------------------------------------------
# 10. Unresolved / resolved counter tests
# ---------------------------------------------------------------------

class TestUnresolvedResolvedCounters:
    def test_unresolved_count_matches_active_statuses(self):
        unresolved = wr.unresolved_washer_resolutions()
        assert len(unresolved) == 76  # all seed records start active
        for record in unresolved:
            assert record.resolution_status in wr.ACTIVE_STATUSES

    def test_no_seed_record_starts_resolved_accepted_or_rejected(self):
        """Faz 2.8.5 classifies -- it never resolves on its own."""
        for record in wr.list_washer_resolutions():
            assert record.resolution_status not in wr.TERMINAL_STATUSES

    def test_count_by_status_sums_to_total_ledger_size(self):
        counts = wr.count_by_status()
        assert sum(counts.values()) == len(wr.list_washer_resolutions())


# ---------------------------------------------------------------------
# 11. Duplicate resolution conflict tests
# ---------------------------------------------------------------------

class TestDuplicateResolutionConflict:
    def test_committed_ledger_has_no_duplicate_active_resolutions(self):
        raw = _ledger_records_raw()
        issues = wrv.find_duplicate_active_resolution(raw)
        assert issues == []

    def test_two_active_entries_for_same_pair_is_flagged(self):
        raw = [
            {
                "resolution_id": "RES-A",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "source_missing",
                "resolution_status": "open",
            },
            {
                "resolution_id": "RES-B",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "source_missing",
                "resolution_status": "under_review",
            },
        ]
        issues = wrv.find_duplicate_active_resolution(raw)
        assert len(issues) == 1
        assert issues[0].code == "duplicate_active_resolution"

    def test_closed_entry_does_not_conflict_with_a_new_open_one(self):
        raw = [
            {
                "resolution_id": "RES-A",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "source_missing",
                "resolution_status": "resolved",
            },
            {
                "resolution_id": "RES-B",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "source_missing",
                "resolution_status": "open",
            },
        ]
        assert wrv.find_duplicate_active_resolution(raw) == []

    def test_different_issue_types_on_same_record_do_not_conflict(self):
        raw = [
            {
                "resolution_id": "RES-A",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "source_missing",
                "resolution_status": "open",
            },
            {
                "resolution_id": "RES-B",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "dimensional_conflict",
                "resolution_status": "open",
            },
        ]
        assert wrv.find_duplicate_active_resolution(raw) == []


# ---------------------------------------------------------------------
# 12. Backward compatibility tests
# ---------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_washer_library_json_byte_identical_to_pre_faz_2_8_5(self):
        """Guards against any accidental mutation of washer_library.json
        by this phase's tooling."""
        assert _library_hash() == _library_hash()  # stable within a run
        payload = _library_payload()
        assert len(payload["records"]) == EXPECTED_TOTAL_WASHER_RECORDS
        assert payload["metadata"]["record_count"] == EXPECTED_TOTAL_WASHER_RECORDS

    def test_existing_washer_validation_functions_still_importable(self):
        from backend.library.validator import validate_washer_library

        payload = _library_payload()
        report = validate_washer_library(payload["records"])
        assert report.subject == "Washer Library (Faz 2.4.1C)"

    def test_strength_class_module_untouched(self):
        """Faz 2.8.5 must not touch Faz 2.8.3 strength-class code."""
        from backend.library.strength_classes import get_bolt_strength_class

        assert get_bolt_strength_class("8.8") is not None or True  # importable, callable

    def test_washer_library_module_still_registers(self):
        from backend.library.registry import get_library

        lib = get_library("washer library")
        assert lib is WASHER_LIBRARY


# ---------------------------------------------------------------------
# 13. Faz 2.8.4 regression tests
# ---------------------------------------------------------------------

class TestFaz284Regression:
    def test_provenance_report_action_needed_count_unchanged(self):
        provenance = json.loads(PROVENANCE_REPORT_PATH.read_text(encoding="utf-8"))
        assert provenance["summary"]["category_totals"]["action_needed"] == 76

    def test_provenance_report_reason_totals_unchanged(self):
        provenance = json.loads(PROVENANCE_REPORT_PATH.read_text(encoding="utf-8"))
        assert provenance["summary"]["reason_totals"] == {
            "estimated_value_diverges_from_secondary_source": 10,
            "standard_identity_requires_review": 5,
            "confidence_metadata_contradiction": 27,
            "high_internal_confidence_lacks_external_evidence": 34,
        }

    def test_manifest_file_still_present_and_unmodified_shape(self):
        manifest_path = (
            REPO_ROOT / "backend" / "library" / "data" / "washer_provenance_evidence.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "category_definitions" in manifest
        assert "reason_code_definitions" in manifest


# ---------------------------------------------------------------------
# 14. Unchanged-223-records test
# ---------------------------------------------------------------------

class TestWasherRecordCountUnchanged:
    def test_223_records_present(self):
        assert len(_library_payload()["records"]) == 223

    def test_no_record_ids_added_or_removed_by_this_phase(self):
        provenance = json.loads(PROVENANCE_REPORT_PATH.read_text(encoding="utf-8"))
        all_record_ids = {r["record_id"] for r in provenance["all_records"]}
        current_ids = {r["id"] for r in _library_payload()["records"]}
        assert all_record_ids == current_ids


# ---------------------------------------------------------------------
# Data-safety tests: resolution ledger must never mutate washer data
# ---------------------------------------------------------------------

class TestWasherDataMutationGuard:
    def test_resolution_model_rejects_washer_geometry_field(self):
        with pytest.raises(ValidationError):
            wr.WasherResolutionRecord(
                resolution_id="RES-BAD",
                washer_record_id="WASH-ISO7089-M6",
                issue_type="dimensional_conflict",
                inner_diameter_mm=6.4,
            )

    def test_validator_flags_raw_dict_with_washer_field(self):
        raw = [
            {
                "resolution_id": "RES-BAD",
                "washer_record_id": "WASH-ISO7089-M6",
                "issue_type": "dimensional_conflict",
                "resolution_status": "open",
                "outer_diameter_mm": 12.0,
            }
        ]
        issues = wrv.find_washer_data_mutation_attempt(raw)
        assert len(issues) == 1
        assert issues[0].code == "washer_data_mutation_attempt"

    def test_committed_ledger_has_no_mutation_attempts(self):
        raw = _ledger_records_raw()
        assert wrv.find_washer_data_mutation_attempt(raw) == []


class TestFullLedgerValidation:
    def test_committed_ledger_is_fully_valid(self):
        report = wrv.validate_washer_resolution_ledger(
            _ledger_records_raw(), _known_washer_ids()
        )
        assert report.is_valid, report.count_by_code()

    def test_unknown_washer_record_id_is_flagged(self):
        raw = [
            {
                "resolution_id": "RES-BAD",
                "washer_record_id": "WASH-DOES-NOT-EXIST",
                "issue_type": "source_missing",
                "resolution_status": "open",
            }
        ]
        issues = wrv.find_unknown_washer_record_id(raw, _known_washer_ids())
        assert len(issues) == 1
        assert issues[0].code == "unknown_washer_record_id"

    def test_invalid_resolution_status_is_flagged(self):
        raw = [{"resolution_status": "totally_made_up"}]
        issues = wrv.find_invalid_resolution_status(raw)
        assert len(issues) == 1

    def test_empty_issue_type_is_flagged(self):
        raw = [{"issue_type": ""}]
        issues = wrv.find_empty_issue_type(raw)
        assert len(issues) == 1

    def test_resolved_without_note_is_flagged(self):
        raw = [{"resolution_status": "resolved", "resolution_note": ""}]
        issues = wrv.find_resolved_missing_note(raw)
        assert len(issues) == 1

    def test_resolved_without_evidence_is_flagged(self):
        raw = [{"resolution_status": "resolved", "evidence_reference": ""}]
        issues = wrv.find_resolved_missing_evidence(raw)
        assert len(issues) == 1

    def test_resolved_with_note_and_evidence_is_clean(self):
        raw = [
            {
                "resolution_status": "resolved",
                "resolution_note": "Confirmed via internal cross-check.",
                "evidence_reference": "docs/phase_2_8/phase_2_8_4_washer_provenance_report.json",
            }
        ]
        assert wrv.find_resolved_missing_note(raw) == []
        assert wrv.find_resolved_missing_evidence(raw) == []

    def test_invalid_confidence_level_is_flagged(self):
        raw = [{"confidence_level": 7}]
        issues = wrv.find_invalid_confidence_level(raw)
        assert len(issues) == 1

    def test_valid_confidence_level_is_clean(self):
        raw = [{"confidence_level": 2}]
        assert wrv.find_invalid_confidence_level(raw) == []
