"""Faz 2.6.2B -- Verified Friction Condition Data Population.

Scope (see docs/adr/ADR-0010-coating-lubrication-friction-data-ownership.md
and docs/phases/PHASE_2.6.2B_VERIFIED_FRICTION_DATA_POPULATION.md):

- 18 ``FrictionConditionRecord`` entries were added, each a
  deterministic 1:1 re-homing of an already-approved
  ``CoatingRecord``/``LubricationRecord`` friction range -- no new
  coefficient invented, derived or split.
- Reference integrity (coating_id/lubricant_id must resolve),
  duplicate-combination prevention, and source-traceability are all
  enforced and tested.
- The 10 coating + 23 lubrication records are unchanged.
- Generation is idempotent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from backend.library import population
from backend.library.models import FrictionConditionRecord
from backend.library.validator import (
    find_dangling_coating_references,
    find_dangling_lubricant_references,
    find_duplicate_friction_condition_combination,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FRICTION_CONDITION_PATH = REPO_ROOT / "backend/library/data/friction_condition_library.json"
COATING_PATH = REPO_ROOT / "backend/library/data/coating_library.json"
LUBRICATION_PATH = REPO_ROOT / "backend/library/data/lubrication_library.json"
GENERATOR_SCRIPT = REPO_ROOT / "tools/generate_faz_2_6_2b_friction_condition_records.py"


def _friction_condition_records() -> list[dict]:
    return json.loads(FRICTION_CONDITION_PATH.read_text(encoding="utf-8"))["records"]


def _coating_ids() -> set[str]:
    return {r["id"] for r in json.loads(COATING_PATH.read_text(encoding="utf-8"))["records"]}


def _lubrication_ids() -> set[str]:
    return {r["id"] for r in json.loads(LUBRICATION_PATH.read_text(encoding="utf-8"))["records"]}


# ---------------------------------------------------------------------
# Population source coverage: every generated record traces to a real
# CoatingRecord or LubricationRecord, split by the id-prefix convention
# the generator uses (not a hardcoded total count).
# ---------------------------------------------------------------------

def test_every_record_is_prefixed_fc_coat_or_fc_lube():
    records = _friction_condition_records()
    assert records  # non-empty as of Faz 2.6.2B
    for r in records:
        assert r["id"].startswith("FC-COAT-") or r["id"].startswith("FC-LUBE-")


def test_coating_derived_records_count_matches_coatings_with_a_friction_range():
    coatings = json.loads(COATING_PATH.read_text(encoding="utf-8"))["records"]
    expected_ids = {
        f"FC-{c['id']}" for c in coatings if c.get("friction_coefficient_range")
    }
    records = _friction_condition_records()
    coating_derived_ids = {r["id"] for r in records if r["id"].startswith("FC-COAT-")}
    assert coating_derived_ids == expected_ids


def test_lubrication_derived_records_count_matches_non_surf_lubricants_with_a_range():
    lubricants = json.loads(LUBRICATION_PATH.read_text(encoding="utf-8"))["records"]
    expected_ids = {
        f"FC-{r['id']}" for r in lubricants
        if not r["id"].startswith("LUBE-SURF-")
        and r.get("friction_coefficient_min") is not None
        and r.get("friction_coefficient_max") is not None
    }
    records = _friction_condition_records()
    lube_derived_ids = {r["id"] for r in records if r["id"].startswith("FC-LUBE-")}
    assert lube_derived_ids == expected_ids


def test_no_tablo_9_4_lube_surf_record_was_migrated():
    """Explicit scope guard: Faz 2.6.2B does not migrate any of the 15
    LUBE-SURF-* Tablo 9.4 records (no deterministic lubricant_id
    mapping -- see ADR-0010 migration plan)."""
    records = _friction_condition_records()
    for r in records:
        assert "SURF" not in r["id"]
        assert r.get("lubricant_id", "") != "" or r["id"].startswith("FC-COAT-") or (
            r.get("coating_id", "") == "" and r.get("lubricant_id", "").startswith("LUBE-")
        )


# ---------------------------------------------------------------------
# Reference integrity
# ---------------------------------------------------------------------

def test_every_coating_id_reference_resolves():
    records = _friction_condition_records()
    known = _coating_ids()
    issues = find_dangling_coating_references(records, known)
    assert issues == []


def test_every_lubricant_id_reference_resolves():
    records = _friction_condition_records()
    known = _lubrication_ids()
    issues = find_dangling_lubricant_references(records, known)
    assert issues == []


def test_unknown_coating_id_is_flagged():
    fake = [{"id": "x", "coating_id": "COAT-DOES-NOT-EXIST"}]
    issues = find_dangling_coating_references(fake, _coating_ids())
    assert len(issues) == 1
    assert issues[0].code == "dangling_coating_reference"


def test_empty_coating_id_is_not_flagged():
    fake = [{"id": "x", "coating_id": ""}]
    assert find_dangling_coating_references(fake, _coating_ids()) == []


def test_run_all_integrity_checks_reports_no_broken_friction_condition_references():
    report = population.run_all_integrity_checks()
    assert report["broken_friction_condition_references"] == []


# ---------------------------------------------------------------------
# Duplicate-combination prevention
# ---------------------------------------------------------------------

def test_live_data_has_no_duplicate_combinations():
    records = _friction_condition_records()
    assert find_duplicate_friction_condition_combination(records) == []


def test_duplicate_combination_is_flagged():
    duped = [
        {"id": "a", "coating_id": "COAT-X", "lubricant_id": "", "surface_condition": "",
         "thread_condition": "", "bearing_condition": "", "source_reference": "Src"},
        {"id": "b", "coating_id": "COAT-X", "lubricant_id": "", "surface_condition": "",
         "thread_condition": "", "bearing_condition": "", "source_reference": "Src"},
    ]
    issues = find_duplicate_friction_condition_combination(duped)
    assert len(issues) == 1
    assert issues[0].code == "duplicate_friction_condition_combination"


def test_same_coating_different_source_is_not_a_duplicate():
    distinct = [
        {"id": "a", "coating_id": "COAT-X", "lubricant_id": "", "surface_condition": "",
         "thread_condition": "", "bearing_condition": "", "source_reference": "Src A"},
        {"id": "b", "coating_id": "COAT-X", "lubricant_id": "", "surface_condition": "",
         "thread_condition": "", "bearing_condition": "", "source_reference": "Src B"},
    ]
    assert find_duplicate_friction_condition_combination(distinct) == []


# ---------------------------------------------------------------------
# Source traceability / min-max consistency (typed model + validator)
# ---------------------------------------------------------------------

def test_every_record_has_populated_source_reference():
    for raw in _friction_condition_records():
        typed = FrictionConditionRecord.model_validate(raw)
        assert typed.source_reference != ""
        assert typed.source_type != ""
        assert typed.verification_status != ""


def test_every_record_min_max_consistent_and_no_thread_bearing_split():
    for raw in _friction_condition_records():
        typed = FrictionConditionRecord.model_validate(raw)
        assert typed.overall_friction_coefficient_min is not None
        assert typed.overall_friction_coefficient_max is not None
        assert typed.overall_friction_coefficient_min <= typed.overall_friction_coefficient_max
        # No independent mu_thread/mu_bearing/K/scatter value exists
        # yet -- none was sourced (Faz 2.6.2B scope).
        assert typed.mu_thread_min is None and typed.mu_thread_max is None
        assert typed.mu_bearing_min is None and typed.mu_bearing_max is None
        assert typed.k_factor_min is None and typed.k_factor_max is None
        assert typed.scatter_percent is None
        assert typed.max_temperature_c is None


def test_full_validator_report_is_clean():
    assert population.validate_friction_condition_library_records() == []


# ---------------------------------------------------------------------
# Idempotent generation + checksum
# ---------------------------------------------------------------------

def test_checksum_matches_recomputed_hash_for_every_record():
    import hashlib

    for raw in _friction_condition_records():
        stored = raw.get("checksum", "")
        payload = {k: v for k, v in raw.items() if k != "checksum"}
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        assert stored == expected, f"{raw['id']}: checksum mismatch"


def test_no_checksum_mismatches_via_population_check():
    assert population.find_checksum_mismatches() == []


def test_generator_script_is_idempotent(tmp_path):
    """Running the generator twice produces byte-identical output."""
    before = FRICTION_CONDITION_PATH.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    after = FRICTION_CONDITION_PATH.read_text(encoding="utf-8")
    assert before == after


# ---------------------------------------------------------------------
# Backward compatibility: 10 coating + 23 lubrication untouched
# ---------------------------------------------------------------------

def test_coating_and_lubrication_files_unchanged_in_shape():
    coatings = json.loads(COATING_PATH.read_text(encoding="utf-8"))["records"]
    lubricants = json.loads(LUBRICATION_PATH.read_text(encoding="utf-8"))["records"]
    assert all(r["id"].startswith("COAT-") for r in coatings)
    assert all(r["id"].startswith("LUBE-") for r in lubricants)
    assert len(coatings) == 10
    assert len(lubricants) == 23


def test_coating_and_lubrication_checksum_integrity_still_clean():
    assert population.find_checksum_mismatches() == []


# ---------------------------------------------------------------------
# API/search smoke + empty/partial dataset safety
# ---------------------------------------------------------------------

def test_search_by_category_returns_populated_library():
    from backend.library.search import search_by_category

    lib = search_by_category("friction_condition")
    assert lib is not None
    assert lib.metadata.key == "friction condition library"


def test_backend_app_still_imports():
    import backend.app as app_module

    assert app_module.app is not None


def test_empty_record_list_does_not_error_in_any_check():
    """An empty or partial dataset must never raise -- every check
    function degrades to an empty issue list, not an exception."""
    empty: list[dict] = []
    assert find_dangling_coating_references(empty, _coating_ids()) == []
    assert find_dangling_lubricant_references(empty, _lubrication_ids()) == []
    assert find_duplicate_friction_condition_combination(empty) == []

    partial = [{"id": "x"}]  # no coating_id/lubricant_id/source at all
    assert find_dangling_coating_references(partial, _coating_ids()) == []
    assert find_dangling_lubricant_references(partial, _lubrication_ids()) == []
    assert find_duplicate_friction_condition_combination(partial) == []
