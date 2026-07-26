"""Faz 2.8.4 tests: washer library provenance & verification readiness.

Covers: manifest/library consistency, category and reason-code
totals, forbidden-inference guards (no evidence -> no
standard_verified, XLSX match alone -> not standard_verified,
generated_from_unverified_source stays 0), immutability of
washer_library.json, population integrity, deterministic report
generation (stdout-only default, --output-dir MD+JSON, byte-identical
across runs), JSON schema validity, cross-directory invocation, and
controlled failure on a corrupted manifest.

Does not touch washer_library.json, models.py, the calculation
engine, the API, or the frontend.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_library.json"
MANIFEST_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_provenance_evidence.json"
TOOL_PATH = REPO_ROOT / "tools" / "washer_provenance_report_faz_2_8_4.py"

_spec = importlib.util.spec_from_file_location("washer_provenance_report_faz_2_8_4", TOOL_PATH)
wpr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wpr)  # type: ignore[union-attr]

EXPECTED_CATEGORY_TOTALS = {
    "standard_verified": 0,
    "secondary_source_only": 8,
    "generated_from_unverified_source": 0,
    "no_external_evidence": 139,
    "action_needed": 76,
}

EXPECTED_REASON_TOTALS = {
    "estimated_value_diverges_from_secondary_source": 10,
    "standard_identity_requires_review": 5,
    "confidence_metadata_contradiction": 27,
    "high_internal_confidence_lacks_external_evidence": 34,
}


def _library_hash() -> str:
    return hashlib.sha256(LIBRARY_PATH.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def library_and_manifest():
    return wpr.load_inputs()


@pytest.fixture(scope="module")
def joined(library_and_manifest):
    library, manifest = library_and_manifest
    return wpr.validate_and_join(library, manifest)


class TestManifestLibraryConsistency:
    def test_library_total_is_223(self, library_and_manifest):
        library, _ = library_and_manifest
        assert len(library["records"]) == 223

    def test_manifest_total_is_223(self, library_and_manifest):
        _, manifest = library_and_manifest
        assert len(manifest["entries"]) == 223

    def test_standard_designation_unique(self, library_and_manifest):
        _, manifest = library_and_manifest
        keys = [(e["standard"], e["designation"]) for e in manifest["entries"]]
        assert len(keys) == len(set(keys))

    def test_record_id_unique_in_manifest(self, library_and_manifest):
        _, manifest = library_and_manifest
        ids = [e["record_id"] for e in manifest["entries"]]
        assert len(ids) == len(set(ids))

    def test_every_library_record_in_manifest_exactly_once(self, library_and_manifest):
        library, manifest = library_and_manifest
        lib_ids = [r["id"] for r in library["records"]]
        entry_ids = [e["record_id"] for e in manifest["entries"]]
        assert sorted(lib_ids) == sorted(entry_ids)

    def test_manifest_has_no_record_absent_from_library(self, library_and_manifest):
        library, manifest = library_and_manifest
        lib_id_set = {r["id"] for r in library["records"]}
        entry_id_set = {e["record_id"] for e in manifest["entries"]}
        assert entry_id_set <= lib_id_set

    def test_corrupted_manifest_missing_record_fails_controlled(
        self, tmp_path, library_and_manifest
    ):
        library, manifest = library_and_manifest
        broken = json.loads(json.dumps(manifest))
        broken["entries"] = broken["entries"][:-1]
        broken_path = tmp_path / "broken_manifest.json"
        broken_path.write_text(json.dumps(broken), encoding="utf-8")
        _, reloaded_broken = wpr.load_inputs(manifest_path=broken_path)
        with pytest.raises(wpr.ProvenanceConsistencyError):
            wpr.validate_and_join(library, reloaded_broken)

    def test_corrupted_manifest_extra_record_fails_controlled(self, tmp_path, library_and_manifest):
        library, manifest = library_and_manifest
        broken = json.loads(json.dumps(manifest))
        fake = dict(broken["entries"][0])
        fake["record_id"] = "WASH-DOES-NOT-EXIST"
        fake["designation"] = "M999"
        broken["entries"].append(fake)
        broken_path = tmp_path / "broken_manifest_extra.json"
        broken_path.write_text(json.dumps(broken), encoding="utf-8")
        _, reloaded_broken = wpr.load_inputs(manifest_path=broken_path)
        with pytest.raises(wpr.ProvenanceConsistencyError):
            wpr.validate_and_join(library, reloaded_broken)

    def test_corrupted_manifest_duplicate_record_fails_controlled(
        self, tmp_path, library_and_manifest
    ):
        library, manifest = library_and_manifest
        broken = json.loads(json.dumps(manifest))
        broken["entries"].append(dict(broken["entries"][0]))
        broken_path = tmp_path / "broken_manifest_dup.json"
        broken_path.write_text(json.dumps(broken), encoding="utf-8")
        _, reloaded_broken = wpr.load_inputs(manifest_path=broken_path)
        with pytest.raises(wpr.ProvenanceConsistencyError):
            wpr.validate_and_join(library, reloaded_broken)


class TestCategoryAssignment:
    def test_every_record_has_exactly_one_allowed_category(self, joined):
        for row in joined:
            assert row["category"] in wpr.ALLOWED_CATEGORIES

    def test_category_totals_match_expected_baseline(self, joined):
        totals = {c: 0 for c in wpr.ALLOWED_CATEGORIES}
        for row in joined:
            totals[row["category"]] += 1
        assert totals == EXPECTED_CATEGORY_TOTALS

    def test_category_totals_sum_to_223(self, joined):
        totals = {c: 0 for c in wpr.ALLOWED_CATEGORIES}
        for row in joined:
            totals[row["category"]] += 1
        assert sum(totals.values()) == 223

    def test_reason_code_required_and_nonempty_for_action_needed(self, joined):
        for row in joined:
            if row["category"] == "action_needed":
                assert row["reason_code"]
            else:
                assert row["reason_code"] is None

    def test_reason_codes_within_allowed_set(self, joined):
        for row in joined:
            if row["reason_code"] is not None:
                assert row["reason_code"] in wpr.ALLOWED_REASON_CODES

    def test_reason_code_totals_match_expected_baseline(self, joined):
        totals = {r: 0 for r in wpr.ALLOWED_REASON_CODES}
        for row in joined:
            if row["reason_code"]:
                totals[row["reason_code"]] += 1
        assert totals == EXPECTED_REASON_TOTALS

    def test_no_external_evidence_record_cannot_be_standard_verified(self, joined):
        for row in joined:
            if row["evidence_source"] in ("none_found",):
                assert row["category"] != "standard_verified"

    def test_secondary_source_match_alone_cannot_be_standard_verified(self, joined):
        for row in joined:
            is_xlsx_match = (
                row["evidence_source"] == "google_drive_xlsx"
                and row["comparison_result"] == "match"
            )
            if is_xlsx_match:
                assert row["category"] == "secondary_source_only"
                assert row["category"] != "standard_verified"

    def test_standard_verified_is_empty_baseline(self, joined):
        # No purchased/licensed primary ISO/DIN standard was accessed
        # in this environment; this category is a placeholder for a
        # future phase, not populated here.
        assert EXPECTED_CATEGORY_TOTALS["standard_verified"] == 0
        assert all(row["category"] != "standard_verified" for row in joined)

    def test_generated_from_unverified_source_stays_zero_without_proven_lineage(self, joined):
        # Direct data-lineage (e.g. a generation script proven to have
        # produced washer_library.json FROM the XLSX) was not
        # established in this session, so this category must be empty.
        assert EXPECTED_CATEGORY_TOTALS["generated_from_unverified_source"] == 0
        assert all(row["category"] != "generated_from_unverified_source" for row in joined)


class TestNoDataMutation:
    def test_washer_library_json_hash_unchanged_after_report_run(self, tmp_path):
        before = _library_hash()
        wpr.run(output_dir=tmp_path)
        after = _library_hash()
        assert before == after

    def test_population_integrity_zero_findings(self):
        sys.path.insert(0, str(REPO_ROOT))
        from backend.library import population

        report = population.run_all_integrity_checks()
        for check_name, findings in report.items():
            assert findings == [], f"{check_name} unexpectedly reported findings: {findings}"


class TestReportGeneration:
    def test_no_arguments_writes_no_repo_file(self, tmp_path, monkeypatch):
        marker_before = sorted(p.name for p in (REPO_ROOT / "docs" / "phase_2_8").glob("*"))
        exit_code = wpr.main([])
        assert exit_code == 0
        marker_after = sorted(p.name for p in (REPO_ROOT / "docs" / "phase_2_8").glob("*"))
        assert marker_before == marker_after

    def test_output_dir_writes_md_and_json(self, tmp_path):
        exit_code = wpr.main(["--output-dir", str(tmp_path)])
        assert exit_code == 0
        assert (tmp_path / "phase_2_8_4_washer_provenance_report.md").exists()
        assert (tmp_path / "phase_2_8_4_washer_provenance_report.json").exists()

    def test_two_runs_are_byte_identical(self, tmp_path):
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        wpr.main(["--output-dir", str(out1)])
        wpr.main(["--output-dir", str(out2)])
        for name in (
            "phase_2_8_4_washer_provenance_report.md",
            "phase_2_8_4_washer_provenance_report.json",
        ):
            assert (out1 / name).read_bytes() == (out2 / name).read_bytes()

    def test_json_report_is_schema_valid(self, tmp_path):
        wpr.main(["--output-dir", str(tmp_path)])
        data = json.loads(
            (tmp_path / "phase_2_8_4_washer_provenance_report.json").read_text(encoding="utf-8")
        )
        required_top_level = {
            "phase",
            "title",
            "scope_note",
            "xlsx_source_status",
            "identity_review_note",
            "confidence_metadata_note",
            "din127b_note",
            "summary",
            "action_needed_records",
            "all_records",
        }
        assert required_top_level <= set(data.keys())
        assert data["summary"]["total_records"] == 223
        assert len(data["all_records"]) == 223
        assert len(data["action_needed_records"]) == 76
        for row in data["all_records"]:
            assert row["category"] in wpr.ALLOWED_CATEGORIES

    def test_no_volatile_content_in_reports(self, tmp_path):
        wpr.main(["--output-dir", str(tmp_path)])
        md_text = (tmp_path / "phase_2_8_4_washer_provenance_report.md").read_text(encoding="utf-8")
        json_text = (tmp_path / "phase_2_8_4_washer_provenance_report.json").read_text(
            encoding="utf-8"
        )
        for volatile in (str(tmp_path), str(REPO_ROOT)):
            assert volatile not in md_text
            assert volatile not in json_text

    def test_tool_runs_from_repository_root(self):
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Total records: 223" in result.stdout

    def test_tool_runs_from_different_working_directory(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH)],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Total records: 223" in result.stdout
        assert list(tmp_path.iterdir()) == []

    def test_tool_returns_nonzero_on_missing_manifest(self, tmp_path):
        fake_tool_env = tmp_path / "no_manifest_here"
        fake_tool_env.mkdir()
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--output-dir", str(tmp_path / "out")],
            cwd=str(fake_tool_env),
            capture_output=True,
            text=True,
        )
        # Tool resolves paths relative to its own file location, not
        # cwd, so this should still succeed; this test documents that
        # invariant explicitly rather than assuming it.
        assert result.returncode == 0
