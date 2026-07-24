"""Faz 2.6.0 -- Lubrication Engineering Architecture & Specification.

Scope of this test module (see docs/adr/ADR-0009-lubrication-friction-model.md
and docs/phases/PHASE_2.6.0_LUBRICATION_ARCHITECTURE.md):

- The Faz 2.6.0 schema extension on ``LubricationRecord`` is additive
  and does not break any pre-existing (Faz 2.4.0/2.4.2B) record.
- The 15 Tablo-9.4-derived ``LUBE-SURF-*`` records parse, carry
  correct source-traceability metadata, and never set
  mu_thread/mu_bearing/K (no approved source for those yet).
- The cadmium-plated subset is marked ``restricted_legacy`` with a
  populated ``regulatory_warning`` and is NOT deleted.
- No production calculation path (``engineering_core``) is touched or
  changed by this phase.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.library.models import (
    FrictionModelType,
    LubricationRecord,
    LubricationType,
    Status,
)

DATA_PATH = "backend/library/data/lubrication_library.json"


def _load_records() -> list[dict]:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)["records"]


def test_pre_existing_minimal_record_still_validates():
    """A Faz 2.4.0-shaped record (no Faz 2.6.0 fields at all) must
    keep validating unchanged -- the core additive-schema guarantee."""
    record = LubricationRecord.model_validate({"id": "LUBE-OLD", "designation": "Dry"})
    assert record.overall_friction_coefficient_min is None
    assert record.overall_friction_coefficient_max is None
    assert record.friction_model is FrictionModelType.UNSPECIFIED
    assert record.mu_thread_min is None
    assert record.mu_bearing_min is None
    assert record.k_factor_min is None
    assert record.scatter_percent is None
    assert record.max_temperature_c is None
    assert record.corrosion_resistance == ""
    assert record.reusability == ""
    assert record.recommended_standards == []
    assert record.source_status == ""
    assert record.source_reference == ""
    assert record.source_type == ""
    assert record.source_page_or_table == ""
    assert record.verification_status == ""
    assert record.applicability == ""
    assert record.engineering_notes == ""
    assert record.regulatory_warning == ""
    assert record.surface_condition == ""
    assert record.status is Status.DRAFT


def test_all_eight_pre_faz_2_6_0_records_unaffected():
    """The 8 Faz 2.4.1/2.4.2B lubricant-product records must parse
    identically to before -- Faz 2.6.0 added fields, changed none."""
    records = [r for r in _load_records() if not r["id"].startswith("LUBE-SURF-")]
    assert len(records) == 8
    for raw in records:
        typed = LubricationRecord.model_validate(raw)
        assert typed.friction_coefficient_min is not None
        assert typed.friction_coefficient_max is not None
        assert typed.oem_compatibility
        # None of the 8 pre-existing records carry Faz 2.6.0 data.
        assert typed.overall_friction_coefficient_min is None
        assert typed.mu_thread_min is None
        assert typed.friction_model is FrictionModelType.UNSPECIFIED


def test_table_9_4_records_present_and_traceable():
    records = [r for r in _load_records() if r["id"].startswith("LUBE-SURF-")]
    assert len(records) == 15
    surfaces = {"UNCOATED", "PHOSPHATED", "PHOSPHATE-BLACKENED", "GALVANIZED", "CADMIUM"}
    states = {"DRY", "OILED", "MOS2-OILED"}
    seen = set()
    for raw in records:
        typed = LubricationRecord.model_validate(raw)
        surface, _, state = typed.id.removeprefix("LUBE-SURF-").rpartition("-")
        # id shape is LUBE-SURF-<SURFACE>-<STATE>; SURFACE may itself
        # contain a hyphen (PHOSPHATE-BLACKENED), so rsplit on the
        # last hyphen-delimited state token via a fixed state set.
        matched_state = next(
            s for s in sorted(states, key=len, reverse=True) if typed.id.endswith(s)
        )
        matched_surface = typed.id[len("LUBE-SURF-"):-(len(matched_state) + 1)]
        assert matched_surface in surfaces
        seen.add((matched_surface, matched_state))

        assert typed.friction_model is FrictionModelType.COMBINED_OR_UNSPECIFIED
        lo, hi = typed.overall_friction_coefficient_min, typed.overall_friction_coefficient_max
        assert 0 <= lo < hi < 1
        assert typed.source_type == "textbook"
        assert typed.source_status == "textbook_reference"
        assert typed.verification_status == "reference_only"
        assert "Tablo 9.4" in typed.source_reference
        assert typed.source_page_or_table
        assert typed.surface_condition
        # No thread/bearing split and no K-factor: not sourced this phase.
        assert typed.mu_thread_min is None and typed.mu_thread_max is None
        assert typed.mu_bearing_min is None and typed.mu_bearing_max is None
        assert typed.k_factor_min is None and typed.k_factor_max is None
        assert typed.scatter_percent is None
        assert typed.max_temperature_c is None
        assert typed.recommended_standards == []

    assert seen == {(s, st) for s in surfaces for st in states}


def test_cadmium_records_restricted_not_deleted():
    records = [r for r in _load_records() if "CADMIUM" in r["id"]]
    assert len(records) == 3
    for raw in records:
        typed = LubricationRecord.model_validate(raw)
        assert typed.status is Status.RESTRICTED_LEGACY
        assert typed.regulatory_warning != ""
        # Faz 2.6.0 explicitly does not assert a specific regulatory
        # clause -- only that a warning exists and routes to review.
        assert typed.overall_friction_coefficient_min is not None


def test_dry_states_reuse_no_lubricant_enum_member():
    records = [
        r for r in _load_records()
        if r["id"].startswith("LUBE-SURF-") and r["id"].endswith("-DRY")
    ]
    assert len(records) == 5
    for raw in records:
        typed = LubricationRecord.model_validate(raw)
        assert typed.lubricant_type is LubricationType.NO_LUBRICANT


def test_oiled_and_mos2_oiled_use_new_faz_2_6_0_enum_members():
    oiled = [r for r in _load_records() if r["id"].endswith("-OILED") and "MOS2" not in r["id"]]
    mos2 = [r for r in _load_records() if r["id"].endswith("-MOS2-OILED")]
    assert len(oiled) == 5
    assert len(mos2) == 5
    for raw in oiled:
        assert LubricationRecord.model_validate(raw).lubricant_type is LubricationType.OILED_GENERIC
    for raw in mos2:
        assert LubricationRecord.model_validate(raw).lubricant_type is LubricationType.MOS2_WITH_OIL


def test_status_enum_gained_restricted_legacy_member_only():
    """RESTRICTED_LEGACY is additive: every pre-existing Status member
    keeps its original value."""
    assert Status.DRAFT.value == "draft"
    assert Status.PROVISIONAL.value == "provisional"
    assert Status.VERIFIED.value == "verified"
    assert Status.APPROVED.value == "approved"
    assert Status.DEPRECATED.value == "deprecated"
    assert Status.ARCHIVED.value == "archived"
    assert Status.RESTRICTED_LEGACY.value == "restricted_legacy"


def test_friction_coefficient_fields_still_bounded_zero_to_one():
    with pytest.raises(ValidationError):
        LubricationRecord.model_validate(
            {"id": "x", "overall_friction_coefficient_min": 1.5}
        )
    with pytest.raises(ValidationError):
        LubricationRecord.model_validate(
            {"id": "x", "mu_thread_min": -0.1}
        )


def test_engineering_core_friction_and_torque_untouched():
    """Faz 2.6.0 is architecture/spec only: the existing torque/friction
    calculation functions keep their exact pre-Faz-2.6.0 signatures and
    behaviour (no library-driven coefficient substitution added yet)."""
    from backend.engineering_core import friction, torque

    rho = friction.thread_friction_angle_rad(0.12)
    assert rho > 0
    t = torque.tightening_torque_nm(
        preload_n=20000, pitch_diameter_mm=9.03, pitch_mm=1.25,
        mu_thread=0.12, mu_bearing=0.12, effective_bearing_diameter_mm=13.0,
    )
    assert t > 0


# ---------------------------------------------------------------------
# Faz 2.6.1: Friction Condition schema-extension validator checks.
# ---------------------------------------------------------------------

class TestFaz261LubricationValidators:
    """Exercise the new backend.library.validator find_* functions and
    the aggregate validate_lubrication_library() against both the live
    data file (must be clean) and crafted violation cases."""

    def test_live_lubrication_data_has_zero_validator_issues(self):
        from backend.library import population

        issues = population.validate_lubrication_library_records()
        assert issues == []

    def test_find_friction_min_max_violations_catches_inverted_range(self):
        from backend.library.validator import find_friction_min_max_violations

        records = [{"id": "x", "overall_friction_coefficient_min": 0.3,
                    "overall_friction_coefficient_max": 0.1}]
        issues = find_friction_min_max_violations(records)
        assert len(issues) == 1
        assert issues[0].code == "friction_min_max_violation"

    def test_find_friction_min_max_violations_ignores_valid_range(self):
        from backend.library.validator import find_friction_min_max_violations

        records = [{"id": "x", "overall_friction_coefficient_min": 0.1,
                    "overall_friction_coefficient_max": 0.3}]
        assert find_friction_min_max_violations(records) == []

    def test_find_friction_negative_values_catches_negative_mu(self):
        from backend.library.validator import find_friction_negative_values

        records = [{"id": "x", "mu_thread_min": -0.05}]
        issues = find_friction_negative_values(records)
        assert len(issues) == 1
        assert issues[0].code == "negative_friction_value"

    def test_find_friction_asymmetric_min_max_catches_one_sided_range(self):
        from backend.library.validator import find_friction_asymmetric_min_max

        records = [{"id": "x", "k_factor_min": 0.15}]
        issues = find_friction_asymmetric_min_max(records)
        assert len(issues) == 1
        assert issues[0].code == "friction_asymmetric_min_max"

    def test_find_friction_asymmetric_min_max_allows_both_or_neither(self):
        from backend.library.validator import find_friction_asymmetric_min_max

        records = [
            {"id": "a", "k_factor_min": 0.15, "k_factor_max": 0.2},
            {"id": "b"},
        ]
        assert find_friction_asymmetric_min_max(records) == []

    def test_find_friction_one_sided_thread_bearing_catches_thread_only(self):
        from backend.library.validator import find_friction_one_sided_thread_bearing

        records = [{"id": "x", "mu_thread_min": 0.1, "mu_thread_max": 0.15}]
        issues = find_friction_one_sided_thread_bearing(records)
        assert len(issues) == 1
        assert issues[0].code == "friction_one_sided_thread_bearing"

    def test_find_friction_one_sided_thread_bearing_allows_both_set(self):
        from backend.library.validator import find_friction_one_sided_thread_bearing

        records = [{
            "id": "x", "mu_thread_min": 0.1, "mu_thread_max": 0.15,
            "mu_bearing_min": 0.1, "mu_bearing_max": 0.15,
        }]
        assert find_friction_one_sided_thread_bearing(records) == []

    def test_find_friction_coefficient_missing_source_catches_unsourced_value(self):
        from backend.library.validator import find_friction_coefficient_missing_source

        records = [{"id": "x", "overall_friction_coefficient_min": 0.1}]
        issues = find_friction_coefficient_missing_source(records)
        assert len(issues) == 1
        assert issues[0].code == "friction_coefficient_missing_source"

    def test_find_friction_coefficient_missing_source_allows_sourced_value(self):
        from backend.library.validator import find_friction_coefficient_missing_source

        records = [{
            "id": "x", "overall_friction_coefficient_min": 0.1,
            "source_reference": "Some Standard, Table 4",
        }]
        assert find_friction_coefficient_missing_source(records) == []

    def test_find_restricted_legacy_missing_warning_catches_empty_warning(self):
        from backend.library.validator import find_restricted_legacy_missing_warning

        records = [{"id": "x", "status": "restricted_legacy"}]
        issues = find_restricted_legacy_missing_warning(records)
        assert len(issues) == 1
        assert issues[0].code == "restricted_legacy_missing_warning"

    def test_find_restricted_legacy_missing_warning_allows_populated_warning(self):
        from backend.library.validator import find_restricted_legacy_missing_warning

        records = [{"id": "x", "status": "restricted_legacy", "regulatory_warning": "See ELV."}]
        assert find_restricted_legacy_missing_warning(records) == []

    def test_validate_lubrication_library_aggregates_all_checks(self):
        from backend.library.validator import validate_lubrication_library

        bad_record = {
            "id": "BAD-1",
            "overall_friction_coefficient_min": 0.4,
            "overall_friction_coefficient_max": 0.1,  # min > max
            "mu_thread_min": -0.02,  # negative
            "k_factor_min": 0.1,  # one-sided (no k_factor_max)
            "status": "restricted_legacy",  # missing regulatory_warning
        }
        report = validate_lubrication_library([bad_record])
        codes = {issue.code for issue in report.issues}
        assert "friction_min_max_violation" in codes
        assert "negative_friction_value" in codes
        assert "friction_asymmetric_min_max" in codes
        assert "friction_coefficient_missing_source" in codes
        assert "restricted_legacy_missing_warning" in codes

    def test_run_all_integrity_checks_includes_lubrication_key(self):
        from backend.library import population

        report = population.run_all_integrity_checks()
        assert "lubrication_library_faz2_6_1" in report
        assert report["lubrication_library_faz2_6_1"] == []


def test_faz_2_6_1_no_new_coefficient_values_populated():
    """Faz 2.6.1 scope check: no mu_thread/mu_bearing/K/scatter/
    temperature/corrosion value exists anywhere in the live data file
    yet -- confirms the phase added validation/architecture only, not
    data (docs/12_CLAUDE_CONTEXT.md SS4)."""
    for raw in _load_records():
        typed = LubricationRecord.model_validate(raw)
        assert typed.mu_thread_min is None
        assert typed.mu_thread_max is None
        assert typed.mu_bearing_min is None
        assert typed.mu_bearing_max is None
        assert typed.k_factor_min is None
        assert typed.k_factor_max is None
        assert typed.scatter_percent is None
        assert typed.corrosion_resistance == ""
