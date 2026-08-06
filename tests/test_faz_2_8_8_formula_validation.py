"""Faz 2.8.8 tests: Engineering Formula Validation.

Covers: read-only aggregation over vdi2230_core.trace and
formula_registry, TR/EN parity, determinism, the read-only/no-mutation
structural boundary, and the API endpoint. Reuses existing fixtures/
conventions (tests/conftest.py's isolated TestClient DB, the
"Protype Lab" / "A1234" seeded login used across other API tests).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.calculation_engine import formula_validation as fv
from backend.calculation_engine import formula_registry
from backend.vdi2230_core import trace as vdi_trace

client = TestClient(app)


def auth():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def auth_headers():
    return auth()


class TestAggregation:
    def test_reports_seven_vdi2230_entries(self):
        report = fv.build_formula_validation_report()
        vdi_entries = [e for e in report.entries if e.catalog == "vdi2230_core.trace"]
        assert len(vdi_entries) == 7

    def test_approved_and_provisional_counts_match_known_catalog(self):
        # Faz 2.8.21: engineering_core.trace added as a third,
        # read-only source (10 entries: 9 PROVISIONAL + 1 UNVERIFIED).
        # vdi2230_core.trace's own 7-entry split (2 APPROVED / 5
        # PROVISIONAL) is unchanged -- see
        # test_reports_seven_vdi2230_entries above.
        report = fv.build_formula_validation_report()
        assert report.approved_count == 2
        assert report.provisional_count == 14
        assert report.other_status_count == 1
        assert report.total_count == 17

    def test_formula_registry_currently_empty_is_not_an_error(self):
        assert formula_registry.all_formulas() == {}
        report = fv.build_formula_validation_report()
        # Faz 2.8.21: total_count now includes engineering_core.trace's
        # 10 entries alongside vdi2230_core's 7; formula_registry's own
        # contribution remains 0, which is still not an error.
        assert report.total_count == 17

    def test_phi_and_fs_are_approved(self):
        report = fv.build_formula_validation_report()
        by_symbol = {e.symbol: e.validation_status for e in report.entries}
        assert by_symbol["Phi"] == fv.APPROVED
        assert by_symbol["F_S"] == fv.APPROVED


class TestTranslationParity:
    def test_every_message_has_both_tr_and_en(self):
        for code, entry in fv._MESSAGES.items():
            assert "tr" in entry and entry["tr"], code
            assert "en" in entry and entry["en"], code
            assert entry["tr"] != entry["en"], code

    def test_lang_changes_notice_text(self):
        tr_report = fv.build_formula_validation_report(lang="tr")
        en_report = fv.build_formula_validation_report(lang="en")
        assert tr_report.notices != en_report.notices

    def test_default_lang_is_turkish(self):
        default_report = fv.build_formula_validation_report()
        tr_report = fv.build_formula_validation_report(lang="tr")
        assert default_report.notices == tr_report.notices


class TestDeterminism:
    def test_repeated_calls_produce_identical_report(self):
        first = fv.build_formula_validation_report(lang="en").to_dict()
        second = fv.build_formula_validation_report(lang="en").to_dict()
        assert first == second

    def test_reading_the_report_does_not_mutate_source_catalogs(self):
        before = dict(vdi_trace.all_traces())
        fv.build_formula_validation_report()
        after = dict(vdi_trace.all_traces())
        assert before.keys() == after.keys()
        for key in before:
            assert before[key] == after[key]


# ---------------------------------------------------------------------
# Read-only boundary (mandatory, product-owner directive 2026-07-28)
# ---------------------------------------------------------------------
class TestReadOnlyBoundary:
    """Formula Validation must never alter or replace any engineering
    formula or coefficient -- asserted structurally so a future edit
    that adds a mutation path fails this test."""

    def test_module_calls_no_register_or_setter_function(self):
        # Strip the module docstring (which documents the boundary in
        # prose and mentions these names descriptively) before
        # checking for actual calls in code.
        path = Path("backend/calculation_engine/formula_validation.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        tree.body = tree.body[1:]  # drop module docstring Expr node
        code_only = ast.unparse(tree)
        for banned in ("register_formula(", "_CATALOG[", "_REGISTRY["):
            assert banned not in code_only, banned

    def test_module_imports_only_read_accessors(self):
        tree = ast.parse(
            Path("backend/calculation_engine/formula_validation.py").read_text(
                encoding="utf-8"
            )
        )
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        assert names == {
            "__future__",
            "dataclasses",
            "typing",
            "backend.calculation_engine",
            "backend.engineering_core",  # Faz 2.8.21: read-only trace accessor
            "backend.vdi2230_core",
        }

    def test_no_engineering_calculation_function_referenced(self):
        source = Path("backend/calculation_engine/formula_validation.py").read_text(
            encoding="utf-8"
        )
        for banned in (
            "preload_from_yield_n", "evaluate_joint", "analyze_joint",
            "assess_assembly", "shear_strength_mpa",
        ):
            assert banned not in source


class TestAPI:
    def test_endpoint_requires_auth(self):
        r = client.get("/api/engineering/formula-validation")
        assert r.status_code in (401, 403)

    def test_endpoint_returns_report(self, auth_headers):
        r = client.get("/api/engineering/formula-validation", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        # Faz 2.8.21: engineering_core.trace adds 10 entries (see
        # TestAggregation.test_approved_and_provisional_counts_match_known_catalog).
        assert body["total_count"] == 17
        assert body["approved_count"] == 2

    def test_endpoint_lang_query_param(self, auth_headers):
        r_tr = client.get(
            "/api/engineering/formula-validation?lang=tr", headers=auth_headers
        )
        r_en = client.get(
            "/api/engineering/formula-validation?lang=en", headers=auth_headers
        )
        assert r_tr.json()["notices"] != r_en.json()["notices"]

    def test_existing_joint_analysis_endpoint_unaffected(self, auth_headers):
        r = client.post("/api/engineering/joint-analysis", json={}, headers=auth_headers)
        assert r.status_code == 200
