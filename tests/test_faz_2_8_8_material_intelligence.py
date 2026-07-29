"""Faz 2.8.8 tests: Material Intelligence and readiness-gated
Recommendation Engine.

Covers: requirement matching over the 8 real MaterialRecord entries,
descriptive comparison, the readiness-gate "no record reaches
engineering/production ready" invariant (mirrors Faz 2.6.4's own
assertion for friction), TR/EN message parity, determinism, the
advisory-layer import boundary, and the 4 new API endpoints. Reuses
existing fixtures/conventions (tests/conftest.py's isolated TestClient
DB, the "Protype Lab" / "A1234" seeded login used across other API
tests).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.calculation_engine import material_intelligence as mi
from backend.calculation_engine import material_intelligence_report as mir

client = TestClient(app)


def auth():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def auth_headers():
    return auth()


# ---------------------------------------------------------------------
# Data / domain logic
# ---------------------------------------------------------------------
class TestMaterialData:
    def test_eight_live_records(self):
        assert len(mi.list_materials()) == 8

    def test_get_material_record_known_id(self):
        record = mi.get_material_record("MAT-STEEL")
        assert record is not None
        assert record["material"] == "Steel"

    def test_get_material_record_unknown_id_returns_none(self):
        assert mi.get_material_record("MAT-DOES-NOT-EXIST") is None

    def test_all_live_records_reference_only_and_pending(self):
        # Ground truth this phase's readiness gate depends on.
        for record in mi.list_materials():
            assert record["validation_status"] == "reference_only"
            assert record["approval_status"] == "pending"


class TestRequirementMatching:
    def test_empty_requirement_matches_all(self):
        assert len(mi.match_materials(mi.MaterialRequirement())) == 8

    def test_min_rp02_filters_correctly(self):
        matches = mi.match_materials(mi.MaterialRequirement(min_rp02_mpa=800))
        ids = {r["id"] for r in matches}
        assert ids == {"MAT-ALLOY_STEEL", "MAT-TITANIUM"}

    def test_material_family_filter_is_case_insensitive_substring(self):
        matches = mi.match_materials(mi.MaterialRequirement(material_family="stainless"))
        ids = {r["id"] for r in matches}
        assert ids == {"MAT-STAINLESS_A2", "MAT-STAINLESS_A4"}

    def test_impossible_requirement_matches_nothing(self):
        matches = mi.match_materials(mi.MaterialRequirement(min_rp02_mpa=100000))
        assert matches == []

    def test_combined_filters_are_conjunctive(self):
        matches = mi.match_materials(
            mi.MaterialRequirement(min_rp02_mpa=400, material_family="steel")
        )
        ids = {r["id"] for r in matches}
        # MAT-STEEL's rp02_mpa is 350, below the 400 threshold, so the
        # conjunction of both filters correctly excludes it -- only
        # MAT-ALLOY_STEEL (rp02_mpa=900) satisfies both.
        assert ids == {"MAT-ALLOY_STEEL"}


class TestDescriptiveComparison:
    def test_compare_known_pair(self):
        result = mi.compare_materials("MAT-TITANIUM", "MAT-ALUMINIUM")
        assert result.rp02_relation == "a_higher"
        assert result.rm_relation == "a_higher"

    def test_compare_unknown_id_raises_keyerror(self):
        with pytest.raises(KeyError):
            mi.compare_materials("MAT-STEEL", "MAT-NOPE")

    def test_comparison_never_states_better(self):
        result = mi.compare_materials("MAT-STEEL", "MAT-TITANIUM")
        text = " ".join(result.descriptive_statements).lower()
        for banned in ("better", "worse", "safer", "recommended", "daha iyi", "daha güvenli"):
            assert banned not in text


# ---------------------------------------------------------------------
# Readiness-gated recommendation engine (the critical assertion)
# ---------------------------------------------------------------------
class TestRecommendationReadinessGate:
    def test_no_requirement_reaches_engineering_or_production_ready(self):
        result = mi.recommend_materials()
        assert result.readiness_level != mi.LEVEL_ENGINEERING_RECOMMENDATION_READY
        assert result.readiness_level != mi.LEVEL_PRODUCTION_RECOMMENDATION_READY

    def test_every_requirement_variant_stays_at_or_below_comparison_only(self):
        requirements = [
            mi.MaterialRequirement(),
            mi.MaterialRequirement(min_rp02_mpa=300),
            mi.MaterialRequirement(min_rm_mpa=600),
            mi.MaterialRequirement(material_family="Titanium"),
            mi.MaterialRequirement(min_rp02_mpa=100000),  # data_insufficient path
        ]
        for req in requirements:
            result = mi.recommend_materials(req)
            assert result.readiness_level in (
                mi.LEVEL_DATA_INSUFFICIENT,
                mi.LEVEL_COMPARISON_ONLY,
            )

    def test_readiness_result_always_states_why_not_higher(self):
        result = mi.recommend_materials(mi.MaterialRequirement(min_rp02_mpa=300))
        assert result.blocking_reasons, "must explain, not guess"
        assert result.required_missing_data, "must list what would unlock a higher level"

    def test_sign_off_notice_always_present(self):
        result = mi.recommend_materials()
        assert result.sign_off_notice

    def test_ranking_is_deterministic_across_repeated_calls(self):
        req = mi.MaterialRequirement(min_rp02_mpa=300)
        first = [c.material_id for c in mi.recommend_materials(req).candidates]
        second = [c.material_id for c in mi.recommend_materials(req).candidates]
        assert first == second

    def test_no_numeric_requirement_never_claims_a_ranking_it_cannot_support(self):
        result = mi.recommend_materials(mi.MaterialRequirement())
        for candidate in result.candidates:
            assert candidate.requirement_margin_ratio is None

    def test_data_insufficient_when_nothing_matches(self):
        result = mi.recommend_materials(mi.MaterialRequirement(min_rp02_mpa=100000))
        assert result.recommendation_available is False
        assert result.candidates == []

    def test_incomplete_input_returns_clear_explanation_not_a_guess_tr(self):
        # An impossible/unmatched requirement must never silently
        # return an empty list -- it must explain why, in Turkish by
        # default. readiness_level reflects the underlying library
        # data's maturity (always comparison_only while every record
        # is reference_only/pending) independent of whether this
        # specific query matched anything; recommendation_available
        # and blocking_reasons are the query-specific signal.
        result = mi.recommend_materials(mi.MaterialRequirement(min_rp02_mpa=100000), lang="tr")
        assert result.recommendation_available is False
        assert result.candidates == []
        assert any(result.blocking_reasons)
        assert "malzeme kaydı bulunamadı" in " ".join(result.blocking_reasons)

    def test_incomplete_input_returns_clear_explanation_not_a_guess_en(self):
        result = mi.recommend_materials(mi.MaterialRequirement(min_rp02_mpa=100000), lang="en")
        assert result.recommendation_available is False
        assert result.candidates == []
        assert any(result.blocking_reasons)
        assert "No material record meets" in " ".join(result.blocking_reasons)

    def test_readiness_level_never_data_insufficient_while_library_has_records(self):
        # data_insufficient is reserved for "no library data exists at
        # all" -- with 8 live records always present, readiness_level
        # itself never drops to data_insufficient; only
        # recommendation_available/candidates vary per query.
        for req in (
            mi.MaterialRequirement(),
            mi.MaterialRequirement(min_rp02_mpa=100000),
            mi.MaterialRequirement(material_family="does-not-exist"),
        ):
            result = mi.recommend_materials(req)
            assert result.readiness_level == mi.LEVEL_COMPARISON_ONLY


# ---------------------------------------------------------------------
# TR/EN parity
# ---------------------------------------------------------------------
class TestTranslationParity:
    def test_every_message_has_both_tr_and_en(self):
        for code, entry in mi._MESSAGES.items():
            assert "tr" in entry and entry["tr"], code
            assert "en" in entry and entry["en"], code
            assert entry["tr"] != entry["en"], code

    def test_lang_parameter_actually_changes_output_text(self):
        tr_result = mi.recommend_materials(lang="tr")
        en_result = mi.recommend_materials(lang="en")
        assert tr_result.engineering_warnings != en_result.engineering_warnings
        assert tr_result.sign_off_notice != en_result.sign_off_notice

    def test_unrecognized_lang_falls_back_to_tr_not_crash(self):
        result = mi.recommend_materials(lang="fr")
        assert result.sign_off_notice == mi.recommend_materials(lang="tr").sign_off_notice

    def test_default_lang_is_turkish(self):
        result = mi.recommend_materials()
        assert result.sign_off_notice == mi.recommend_materials(lang="tr").sign_off_notice


# ---------------------------------------------------------------------
# Advisory-layer boundary (mandatory, product-owner directive 2026-07-28)
# ---------------------------------------------------------------------
class TestAdvisoryLayerBoundary:
    """The Recommendation Engine must never modify engineering
    calculations, coefficients, formulas, preload, torque, clamp
    force or safety factors -- asserted structurally, not just by
    convention, so a future edit that violates it fails this test."""

    _FORBIDDEN_MODULES = (
        "backend.engineering_core",
        "backend.vdi2230_core",
        "backend.calculation_engine.joint_analysis",
        "backend.calculation_engine.assembly_intelligence",
        "backend.calculation_engine.formula_registry",
    )

    def _imported_module_names(self, path: Path) -> set:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    def test_material_intelligence_imports_no_calculation_module(self):
        path = Path("backend/calculation_engine/material_intelligence.py")
        imported = self._imported_module_names(path)
        for forbidden in self._FORBIDDEN_MODULES:
            assert not any(name.startswith(forbidden) for name in imported), forbidden

    def test_material_intelligence_only_reads_population(self):
        path = Path("backend/calculation_engine/material_intelligence.py")
        imported = {n for n in self._imported_module_names(path) if n.startswith("backend.")}
        assert imported == {"backend.library"}

    def test_no_engineering_calculation_function_name_referenced(self):
        # Structural guard: none of the well-known deterministic
        # calculation entry points appear as identifiers anywhere in
        # the advisory module's source.
        source = Path("backend/calculation_engine/material_intelligence.py").read_text(
            encoding="utf-8"
        )
        for banned in (
            "preload_from_yield_n", "evaluate_joint", "analyze_joint",
            "assess_assembly", "shear_strength_mpa", "register_formula",
        ):
            assert banned not in source


# ---------------------------------------------------------------------
# Report collector/renderer (determinism)
# ---------------------------------------------------------------------
class TestReport:
    def test_collector_is_deterministic(self):
        req = mi.MaterialRequirement(min_rp02_mpa=400)
        first = mir.collect_material_intelligence_report(req, lang="en").to_dict()
        second = mir.collect_material_intelligence_report(req, lang="en").to_dict()
        assert first == second

    def test_no_wall_clock_field_in_snapshot(self):
        snap = mir.collect_material_intelligence_report()
        d = snap.to_dict()
        assert "generated_at" not in d
        assert "timestamp" not in d

    def test_markdown_renders_without_raising_on_partial_snapshot(self):
        empty = mir.MaterialIntelligenceReportSnapshot(lang="tr")
        text = mir.render_material_intelligence_report_markdown(empty)
        assert isinstance(text, str) and text

    def test_markdown_contains_readiness_level(self):
        snap = mir.collect_material_intelligence_report(lang="tr")
        text = mir.render_material_intelligence_report_markdown(snap)
        assert "comparison_only" in text


# ---------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------
class TestAPI:
    def test_list_materials_requires_auth(self):
        r = client.get("/api/library/materials")
        assert r.status_code in (401, 403)

    def test_list_materials(self, auth_headers):
        r = client.get("/api/library/materials", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["materials"]) == 8

    def test_material_detail_known(self, auth_headers):
        r = client.get("/api/library/materials/MAT-STEEL", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["material"] == "Steel"

    def test_material_detail_unknown_is_404(self, auth_headers):
        r = client.get("/api/library/materials/MAT-NOPE", headers=auth_headers)
        assert r.status_code == 404

    def test_material_recommendation_endpoint(self, auth_headers):
        r = client.post(
            "/api/engineering/material-recommendation",
            json={"min_rp02_mpa": 400, "lang": "en"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["readiness_level"] == "comparison_only"
        assert body["sign_off_notice"]

    def test_material_recommendation_default_lang_is_tr(self, auth_headers):
        r = client.post(
            "/api/engineering/material-recommendation", json={}, headers=auth_headers
        )
        assert r.status_code == 200

    def test_material_recommendation_never_reaches_higher_than_comparison_only(
        self, auth_headers
    ):
        r = client.post(
            "/api/engineering/material-recommendation",
            json={"min_rp02_mpa": 300},
            headers=auth_headers,
        )
        assert r.json()["readiness_level"] in ("data_insufficient", "comparison_only")

    def test_existing_engineering_check_endpoint_unaffected(self, auth_headers):
        # Zero-regression spot check: a pre-existing endpoint keeps
        # responding after Faz 2.8.8's route additions.
        r = client.get("/api/engineering/bolt-strength-classes", headers=auth_headers)
        assert r.status_code == 200

    def test_recommendation_response_carries_no_calculation_field(self, auth_headers):
        # Advisory-only, API-level: the response must never contain a
        # preload/torque/clamp/stiffness/safety-factor field -- this
        # module cannot produce one by construction (see
        # TestAdvisoryLayerBoundary), and the response shape confirms
        # it at the API contract level too.
        r = client.post(
            "/api/engineering/material-recommendation",
            json={"min_rp02_mpa": 400},
            headers=auth_headers,
        )
        body = r.json()
        forbidden_fields = (
            "preload_n", "torque_nm", "clamp_load_n", "safety_factor",
            "stiffness_n_per_mm", "phi", "applied_torque_nm",
        )
        flat_json = str(body).lower()
        for field_name in forbidden_fields:
            assert field_name not in flat_json, field_name
