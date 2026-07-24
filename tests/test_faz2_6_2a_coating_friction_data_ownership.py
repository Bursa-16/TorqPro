"""Faz 2.6.2A -- Coating and Friction Data Ownership Decision.

Scope of this test module (see
docs/adr/ADR-0010-coating-lubrication-friction-data-ownership.md and
docs/phases/PHASE_2.6.2A_COATING_FRICTION_DATA_OWNERSHIP.md):

- The new ``FrictionConditionRecord`` schema and
  ``friction_condition_library.py``/``.json`` registry shell exist,
  are wired into ``LIBRARY_RECORD_MODELS`` /
  ``population.POPULATION_SOURCES`` / ``search.CATEGORY_LIBRARY_MAP``,
  and validate correctly. As of Faz 2.6.2B it carries 18
  deterministically-sourced records (re-homed from already-approved
  ``CoatingRecord``/``LubricationRecord`` friction ranges) -- it
  shipped with 0 records through Faz 2.6.2A (decision/schema phase
  only, no data population).
- The Faz 2.6.2A additive fields on ``CoatingRecord``
  (``coating_family``, ``substrate_applicability``,
  ``regulatory_warning``, source-traceability fields) and
  ``LubricationRecord`` (``lubricant_family``) are backward
  compatible: every one of the 10 coating records and 23 lubrication
  records still parses unchanged.
- No API/service behaviour changed (import/smoke only, no route
  touched by this phase).
"""

from __future__ import annotations

import json

from backend.library.models import (
    CoatingRecord,
    FrictionConditionRecord,
    FrictionModelType,
    LIBRARY_RECORD_MODELS,
    LubricationRecord,
    Status,
)

COATING_DATA_PATH = "backend/library/data/coating_library.json"
LUBRICATION_DATA_PATH = "backend/library/data/lubrication_library.json"
FRICTION_CONDITION_DATA_PATH = "backend/library/data/friction_condition_library.json"


def _load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["records"]


# ---------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------

def test_friction_condition_library_registered_in_library_record_models():
    assert LIBRARY_RECORD_MODELS["friction condition library"] is FrictionConditionRecord


def test_friction_condition_library_module_importable_and_registered():
    from backend.library import friction_condition_library
    from backend.library.registry import get_library

    assert friction_condition_library.FRICTION_CONDITION_LIBRARY is not None
    lib = get_library("friction condition library")
    assert lib.metadata.name == "Friction Condition Library"
    assert lib.metadata.status == "draft"
    assert lib.metadata.record_count == 0


def test_friction_condition_category_searchable():
    from backend.library.search import search_by_category

    lib = search_by_category("friction_condition")
    assert lib is not None
    assert lib.metadata.key == "friction condition library"


def test_population_sources_include_friction_condition_library():
    from backend.library import population

    assert population.POPULATION_SOURCES["friction condition library"] == (
        "friction_condition_library.json"
    )


# ---------------------------------------------------------------------
# Faz 2.6.2A/B: friction condition library population state
# ---------------------------------------------------------------------

def test_friction_condition_data_file_was_empty_in_faz_2_6_2a_now_populated_in_2_6_2b():
    records = _load(FRICTION_CONDITION_DATA_PATH)
    # Faz 2.6.2B populated this library with deterministically-sourced
    # records only -- every id is one of the two known generated
    # prefixes (FC-COAT-* from CoatingRecord, FC-LUBE-* from
    # LubricationRecord); no hand-authored or guessed record exists.
    assert records
    for r in records:
        assert r["id"].startswith("FC-COAT-") or r["id"].startswith("FC-LUBE-")
        assert r["source_reference"] != ""


def test_friction_condition_library_validator_report_is_empty():
    from backend.library import population

    assert population.validate_friction_condition_library_records() == []


def test_run_all_integrity_checks_includes_friction_condition_key():
    from backend.library import population

    report = population.run_all_integrity_checks()
    assert report["friction_condition_library_faz2_6_2a"] == []
    assert report["broken_friction_condition_references"] == []


# ---------------------------------------------------------------------
# FrictionConditionRecord schema shape
# ---------------------------------------------------------------------

def test_friction_condition_record_minimal_construction():
    record = FrictionConditionRecord.model_validate({"id": "FC-TEST"})
    assert record.coating_id == ""
    assert record.lubricant_id == ""
    assert record.friction_model is FrictionModelType.UNSPECIFIED
    assert record.overall_friction_coefficient_min is None
    assert record.mu_thread_min is None
    assert record.mu_bearing_min is None
    assert record.k_factor_min is None
    assert record.scatter_percent is None


def test_friction_condition_record_can_reference_coating_and_lubricant_ids():
    record = FrictionConditionRecord.model_validate({
        "id": "FC-TEST-2",
        "coating_id": "COAT-GEOMET",
        "lubricant_id": "LUBE-MOS2",
        "surface_condition": "Fosfatlanmis",
        "friction_model": "combined_or_unspecified",
        "overall_friction_coefficient_min": 0.1,
        "overall_friction_coefficient_max": 0.15,
        "source_reference": "Example Source",
    })
    assert record.coating_id == "COAT-GEOMET"
    assert record.lubricant_id == "LUBE-MOS2"
    assert record.friction_model is FrictionModelType.COMBINED_OR_UNSPECIFIED


def test_friction_condition_record_bounds_enforced():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FrictionConditionRecord.model_validate({"id": "x", "mu_thread_min": -0.1})
    with pytest.raises(ValidationError):
        FrictionConditionRecord.model_validate({"id": "x", "overall_friction_coefficient_min": 1.2})


def test_friction_condition_raw_dicts_pass_shared_friction_validators():
    """The same find_* validator functions used for LubricationRecord
    apply unchanged to FrictionConditionRecord raw dicts (ADR-0010:
    intentionally shared field-name shape)."""
    from backend.library.validator import find_friction_min_max_violations

    bad = [{"id": "x", "overall_friction_coefficient_min": 0.3,
            "overall_friction_coefficient_max": 0.1}]
    issues = find_friction_min_max_violations(bad)
    assert len(issues) == 1


# ---------------------------------------------------------------------
# CoatingRecord: Faz 2.6.2A additive fields, backward compatibility
# ---------------------------------------------------------------------

def test_coating_record_minimal_still_validates():
    record = CoatingRecord.model_validate({"id": "COAT-OLD"})
    assert record.coating_family == ""
    assert record.substrate_applicability == ""
    assert record.regulatory_warning == ""
    assert record.source_reference == ""
    assert record.source_type == ""
    assert record.source_page_or_table == ""
    assert record.verification_status == ""
    assert record.applicability == ""
    assert record.engineering_notes == ""


def test_all_ten_coating_records_unaffected():
    records = _load(COATING_DATA_PATH)
    assert len(records) == 10
    for raw in records:
        typed = CoatingRecord.model_validate(raw)
        assert typed.id.startswith("COAT-")
        assert typed.designation != ""
        # None of the 10 live records carry Faz 2.6.2A data yet.
        assert typed.coating_family == ""
        assert typed.regulatory_warning == ""
    # Domain-ownership check (ADR-0010): the coatings the original
    # Faz 2.6 request named as "lubricants" already exist here and
    # must not be re-created inside LubricationRecord.
    ids = {r["id"] for r in records}
    assert {"COAT-GEOMET", "COAT-DACROMET", "COAT-DELTA_PROTEKT", "COAT-PHOSPHATE"} <= ids


# ---------------------------------------------------------------------
# LubricationRecord: Faz 2.6.2A additive field, backward compatibility
# ---------------------------------------------------------------------

def test_lubrication_record_gains_lubricant_family_field():
    record = LubricationRecord.model_validate({"id": "LUBE-OLD-2"})
    assert record.lubricant_family == ""


def test_all_twenty_three_lubrication_records_still_unaffected():
    records = _load(LUBRICATION_DATA_PATH)
    assert len(records) == 23
    for raw in records:
        typed = LubricationRecord.model_validate(raw)
        assert typed.id.startswith("LUBE-")
        assert typed.lubricant_family == ""
    # Domain-key check: the two record "shapes" living on this one
    # library file are distinguishable by id prefix, not just count.
    surf_ids = [r["id"] for r in records if r["id"].startswith("LUBE-SURF-")]
    product_ids = [r["id"] for r in records if not r["id"].startswith("LUBE-SURF-")]
    assert len(surf_ids) + len(product_ids) == len(records)
    assert surf_ids and product_ids


# ---------------------------------------------------------------------
# API/service layer: import/smoke only, no route touched by this phase
# ---------------------------------------------------------------------

def test_backend_app_still_imports_and_constructs():
    import backend.app as app_module

    assert app_module.app is not None


def test_status_enum_unaffected_by_faz_2_6_2a():
    assert Status.RESTRICTED_LEGACY.value == "restricted_legacy"
    assert Status.DRAFT.value == "draft"
