"""Faz 2.8.21 tests: Engineering Core Traceability and Governance Foundation.

Governance and traceability tests ONLY -- this phase changes no
formula, coefficient, or numerical result. See
``docs/phases/PHASE_2.8.21_ENGINEERING_CORE_TRACEABILITY.md``.

Golden values used below are tagged per the phase's stated policy:
LEGACY_REGRESSION_ONLY (locks in pre-existing, unchanged numerical
behaviour) -- never sourced from the question bank, never promoted to
"engineering-authoritative".
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.calculation_engine import formula_validation as fv
from backend.engineering_core import trace as engcore_trace
from backend.engineering_core.geometry import thread_shear_area_mm2
from backend.engineering_core.joint import evaluate_joint
from backend.vdi2230_core import trace as vdi_trace

client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parent.parent


def auth():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def auth_headers():
    return auth()


# ---------------------------------------------------------------------
# 1. Every live engineering_core formula has a stable registry entry
# ---------------------------------------------------------------------
class TestRegistryCoverage:
    #: The complete, closed set of formulas this phase found actually
    #: reachable from evaluate_joint() (Stage 2 inventory). Deliberately
    #: not expanded beyond what exists -- see TestNoFabricatedEntries.
    EXPECTED_IDS = {
        "ENGCORE_TIGHTENING_TORQUE",
        "ENGCORE_THREAD_FRICTION_ANGLE",
        "ENGCORE_PITCH_DIAMETER",
        "ENGCORE_MINOR_DIAMETER",
        "ENGCORE_HELIX_ANGLE",
        "ENGCORE_THREAD_SHEAR_AREA",
        "ENGCORE_SHEAR_STRENGTH_FROM_RM",
        "ENGCORE_PRELOAD_FROM_YIELD",
        "ENGCORE_PROOF_LOAD_UTILIZATION",
        "ENGCORE_JOINT_CHECK",
    }

    def test_exactly_ten_live_formulas_registered(self):
        traces = engcore_trace.all_traces()
        assert {fid.value for fid in traces} == self.EXPECTED_IDS
        assert len(traces) == 10

    def test_get_trace_resolves_every_registered_id(self):
        for formula_id in engcore_trace.EngineeringCoreFormulaId:
            t = engcore_trace.get_trace(formula_id)
            assert t.formula_id == formula_id

    def test_get_trace_raises_for_unregistered_lookup(self):
        # Exercise the guard path directly: temporarily remove one
        # catalog entry, confirm get_trace() raises, then restore it
        # so the rest of the suite is unaffected.
        formula_id = engcore_trace.EngineeringCoreFormulaId.ENGCORE_TIGHTENING_TORQUE
        saved = engcore_trace._CATALOG.pop(formula_id)
        try:
            with pytest.raises(engcore_trace.MissingEngineeringCoreFormulaError):
                engcore_trace.get_trace(formula_id)
        finally:
            engcore_trace._CATALOG[formula_id] = saved


class TestNoFabricatedEntries:
    """Stage 2 explicitly excludes topics requested but not found in
    engineering_core (plain tensile stress from a bare force/area,
    torsional stress, von Mises equivalent stress, bearing/contact
    pressure). This must stay true -- no placeholder entry for any of
    them."""

    FORBIDDEN_SUBSTRINGS = (
        "TORSIONAL", "VON_MISES", "BEARING_PRESSURE", "CONTACT_PRESSURE",
        "TENSILE_STRESS", "EQUIVALENT_STRESS",
    )

    def test_no_placeholder_ids_for_unimplemented_formulas(self):
        ids = {fid.value for fid in engcore_trace.EngineeringCoreFormulaId}
        for forbidden in self.FORBIDDEN_SUBSTRINGS:
            assert not any(forbidden in i for i in ids), (
                f"Found a registry id containing {forbidden!r}, but no such "
                "formula exists in backend.engineering_core -- placeholder "
                "entries are prohibited by this phase's rules."
            )

    def test_engineering_core_package_genuinely_has_no_such_functions(self):
        # Cross-check the exclusion claim against the actual source,
        # not just the registry -- catches the case where someone adds
        # the real formula later without adding its trace entry too.
        import backend.engineering_core.geometry as geometry_mod
        import backend.engineering_core.materials as materials_mod
        import backend.engineering_core.torque as torque_mod

        names = set(dir(geometry_mod)) | set(dir(materials_mod)) | set(dir(torque_mod))
        for forbidden_fn in (
            "bearing_pressure_mpa", "contact_pressure_mpa",
            "von_mises_stress_mpa", "torsional_stress_mpa",
            "tensile_stress_mpa",
        ):
            assert forbidden_fn not in names


# ---------------------------------------------------------------------
# 2/3/4/5. Status validity, source_level, limitations, APPROVED guard
# ---------------------------------------------------------------------
class TestMetadataInvariants:
    def test_every_entry_has_a_valid_status(self):
        for t in engcore_trace.all_traces().values():
            assert t.status in engcore_trace.VALID_STATUSES

    def test_every_entry_has_a_non_empty_source_level(self):
        for t in engcore_trace.all_traces().values():
            assert t.source_level and t.source_level.strip()

    def test_every_provisional_or_unverified_entry_has_limitations(self):
        for t in engcore_trace.all_traces().values():
            if t.status in (engcore_trace.PROVISIONAL, engcore_trace.UNVERIFIED):
                assert t.limitations, f"{t.formula_id} is {t.status} but has no limitations"

    def test_no_entry_is_currently_approved(self):
        # Explicit, deliberate outcome of this phase: none of these
        # formulas has completed source sign-off + golden-case +
        # engineering review, so none may be APPROVED yet.
        approved = [
            t for t in engcore_trace.all_traces().values()
            if t.status == engcore_trace.APPROVED
        ]
        assert approved == []

    def test_dataclass_rejects_an_invalid_status_at_construction(self):
        # Structural guard for item 5: an APPROVED-or-any status entry
        # cannot exist without passing through the same validated
        # dataclass shape (formula_id, source_reference, etc. are all
        # required positional/keyword fields; status is checked in
        # __post_init__).
        with pytest.raises(ValueError):
            engcore_trace.EngineeringCoreFormulaTrace(
                formula_id=engcore_trace.EngineeringCoreFormulaId.ENGCORE_TIGHTENING_TORQUE,
                name="x", domain="x", implementation="x", source_level="x",
                source_reference="x", status="NOT_A_REAL_STATUS", confidence="LOW",
                assumptions=(), limitations=("x",), intended_use="x",
                prohibited_claims=(), validation_basis="x", affected_outputs=(),
            )

    def test_approved_status_constant_is_imported_not_redefined(self):
        # Point 2 of the accepted plan: shared status semantics live in
        # one place (vdi2230_core.trace), not duplicated.
        assert engcore_trace.APPROVED is vdi_trace.APPROVED
        assert engcore_trace.PROVISIONAL is vdi_trace.PROVISIONAL


# ---------------------------------------------------------------------
# 6. internal_thread_sf / external_thread_sf reference registered IDs
# ---------------------------------------------------------------------
class TestOutputGovernanceLinkage:
    def _payload(self):
        return {
            "diameter_mm": 10, "pitch_mm": 1.5, "stress_area_mm2": 58.0, "rp02_mpa": 900,
            "target_yield_ratio": 0.75, "mu_thread_min": 0.10, "mu_thread_nom": 0.12,
            "mu_thread_max": 0.14, "mu_bearing_min": 0.10, "mu_bearing_nom": 0.12,
            "mu_bearing_max": 0.14, "effective_bearing_diameter_mm": 15.0,
            "engagement_mm": 10.0, "internal_rm_mpa": 500, "bolt_rm_mpa": 1000,
            "nut_proof_mpa": 830,
        }

    def test_thread_sf_outputs_reference_a_registered_model_id(self, auth_headers):
        r = client.post("/api/engineering/check", json=self._payload(), headers=auth_headers)
        assert r.status_code == 200, r.text
        gov = r.json()["formula_governance"]
        valid_ids = {fid.value for fid in engcore_trace.EngineeringCoreFormulaId}
        assert gov["internal_thread_sf"]["model_id"] in valid_ids
        assert gov["external_thread_sf"]["model_id"] in valid_ids
        assert gov["internal_thread_sf"]["model_id"] == "ENGCORE_THREAD_SHEAR_AREA"
        assert gov["external_thread_sf"]["model_id"] == "ENGCORE_THREAD_SHEAR_AREA"

    def test_thread_sf_governance_reports_provisional_status(self, auth_headers):
        r = client.post("/api/engineering/check", json=self._payload(), headers=auth_headers)
        gov = r.json()["formula_governance"]
        assert gov["internal_thread_sf"]["status"] == engcore_trace.PROVISIONAL
        assert gov["external_thread_sf"]["status"] == engcore_trace.PROVISIONAL

    def test_thread_sf_governance_reports_d2_d3_basis_and_coefficient(self, auth_headers):
        r = client.post("/api/engineering/check", json=self._payload(), headers=auth_headers)
        gov = r.json()["formula_governance"]
        assert gov["internal_thread_sf"]["diameter_basis"] == "d2 (pitch diameter)"
        assert gov["external_thread_sf"]["diameter_basis"] == "d3 (minor diameter)"
        assert gov["internal_thread_sf"]["coefficient"] == 0.5
        assert gov["external_thread_sf"]["coefficient"] == 0.5

    def test_thread_sf_governance_names_no_standards_compliance(self, auth_headers):
        r = client.post("/api/engineering/check", json=self._payload(), headers=auth_headers)
        gov = r.json()["formula_governance"]
        for key in ("internal_thread_sf", "external_thread_sf"):
            claims = gov[key]["prohibited_claims"]
            assert "ISO 16224 compliant" in claims
            assert "VDI 2230 compliant" in claims
            assert "FCA C2001 compliant" in claims
            assert "ASME validated" in claims


# ---------------------------------------------------------------------
# 7. thread_shear_area_mm2 historical behaviour unchanged
# ---------------------------------------------------------------------
class TestThreadShearAreaUnchanged:
    #: LEGACY_REGRESSION_ONLY -- locks the pre-existing 0.5*pi*d*Le
    #: behaviour exactly as found before this phase. Not sourced from
    #: the question bank; not a claim of engineering correctness.
    @pytest.mark.parametrize("d,le,expected", [
        (10.0, 12.0, 188.49555921538757),
        (6.0, 9.0, 84.82300164692441),
        (16.0, 24.0, 603.1857894892403),
    ])
    def test_formula_still_computes_half_pi_d_le(self, d, le, expected):
        assert thread_shear_area_mm2(d, le) == pytest.approx(expected)

    def test_coefficient_is_still_exactly_one_half(self):
        # d*Le held at 1 so the result IS the coefficient times pi.
        import math
        assert thread_shear_area_mm2(1.0, 1.0) == pytest.approx(0.5 * math.pi)


# ---------------------------------------------------------------------
# 8. No educational pi*d*Le function was introduced into the joint path
# ---------------------------------------------------------------------
class TestNoEducationalFormulaIntroduced:
    def test_geometry_module_defines_no_naive_cylindrical_area_function(self):
        source = Path("backend/engineering_core/geometry.py").read_text(encoding="utf-8")
        for banned in (
            "cylindrical_engagement_area", "naive_shear_area",
            "educational_shear_area", "simple_shear_area",
        ):
            assert banned not in source

    def test_evaluate_joint_calls_thread_shear_area_mm2_exactly_twice(self):
        source = Path("backend/engineering_core/joint.py").read_text(encoding="utf-8")
        assert source.count("thread_shear_area_mm2(") == 2

    def test_thread_shear_area_mm2_source_still_contains_the_half_coefficient(self):
        source = Path("backend/engineering_core/geometry.py").read_text(encoding="utf-8")
        assert "* .5" in source or "* 0.5" in source


# ---------------------------------------------------------------------
# 9. API changes are additive
# ---------------------------------------------------------------------
class TestAPIAdditiveOnly:
    PRE_EXISTING_KEYS = (
        "preload_n", "torque_min_nm", "torque_nom_nm", "torque_max_nm",
        "nut_proof_util_pct", "internal_thread_sf", "external_thread_sf",
    )

    def _payload(self):
        return TestOutputGovernanceLinkage()._payload()

    def test_all_pre_existing_response_keys_still_present(self, auth_headers):
        r = client.post("/api/engineering/check", json=self._payload(), headers=auth_headers)
        d = r.json()
        for key in self.PRE_EXISTING_KEYS:
            assert key in d

    def test_new_key_is_additive_not_a_replacement(self, auth_headers):
        r = client.post("/api/engineering/check", json=self._payload(), headers=auth_headers)
        d = r.json()
        assert "formula_governance" in d
        assert set(self.PRE_EXISTING_KEYS).issubset(d.keys())

    def test_formula_validation_endpoint_entries_gained_fields_not_lost_any(self, auth_headers):
        r = client.get(
            "/api/engineering/formula-validation?lang=tr", headers=auth_headers
        )
        assert r.status_code == 200
        entry = r.json()["entries"][0]
        for pre_existing_key in (
            "formula_id", "symbol", "unit", "source", "classification",
            "validation_status", "catalog",
        ):
            assert pre_existing_key in entry


# ---------------------------------------------------------------------
# 10. Frontend status label maps to the correct backend/registry status
# ---------------------------------------------------------------------
class TestFrontendLabel:
    def test_provisional_label_key_defined_in_both_languages(self):
        source = Path("frontend/index.html").read_text(encoding="utf-8")
        assert source.count("'hizli.model_status_provisional':") == 2

    def test_label_rendered_next_to_thread_strip_safety_row(self):
        source = Path("frontend/index.html").read_text(encoding="utf-8")
        idx = source.index("hizli.result_thread_strip_safety')}</span><span class=\"result-val")
        # The provisional label must appear within the same template
        # literal line as the thread-strip safety row, not somewhere
        # disconnected from it.
        line_end = source.index("</div>", idx)
        assert "hizli.model_status_provisional" in source[idx:line_end]

    def test_no_standards_compliance_wording_near_the_label(self):
        source = Path("frontend/index.html").read_text(encoding="utf-8")
        idx = source.index("hizli.model_status_provisional': 'Provisional model'")
        window = source[max(0, idx - 200):idx + 200]
        for banned in ("ISO 16224", "VDI 2230 compliant", "FCA C2001", "ASME validated"):
            assert banned not in window

    def test_no_modal_or_large_warning_block_introduced(self):
        # Structural guard: the label additions are the only new
        # frontend surface for this phase -- no new <div class="modal
        # ...> or alert-danger-style block was introduced alongside them.
        source = Path("frontend/index.html").read_text(encoding="utf-8")
        idx = source.index("hizli.model_status_provisional': 'Provisional model'")
        assert "modal" not in source[idx:idx + 500].lower()


# ---------------------------------------------------------------------
# 11. Existing VDI registry behaviour unchanged
# ---------------------------------------------------------------------
class TestVdiRegistryUnchanged:
    def test_still_exactly_seven_vdi_entries_two_approved_five_provisional(self):
        traces = vdi_trace.all_traces()
        assert len(traces) == 7
        approved = sum(1 for t in traces.values() if t.validation_status == vdi_trace.APPROVED)
        provisional = sum(1 for t in traces.values() if t.validation_status == vdi_trace.PROVISIONAL)
        assert approved == 2
        assert provisional == 5

    def test_phi_and_fs_remain_approved(self):
        traces = vdi_trace.all_traces()
        by_symbol = {t.symbol: t.validation_status for t in traces.values()}
        assert by_symbol["Phi"] == vdi_trace.APPROVED
        assert by_symbol["F_S"] == vdi_trace.APPROVED

    def test_vdi2230_core_isolation_still_holds(self):
        # Re-assert the pre-existing isolation guarantee is untouched
        # by this phase's additions elsewhere in the tree.
        import ast as ast_mod
        forbidden = {"engineering_core", "standards", "library", "calculation_engine", "app"}
        pkg_dir = Path(vdi_trace.__file__).resolve().parent
        for path in pkg_dir.rglob("*.py"):
            tree = ast_mod.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = set()
            for node in ast_mod.walk(tree):
                if isinstance(node, ast_mod.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast_mod.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            assert not (imported & forbidden), f"{path} imports {imported & forbidden}"


# ---------------------------------------------------------------------
# 12. Numerical results unchanged vs. pre-Faz-2.8.21 baseline
# ---------------------------------------------------------------------
class TestNumericalRegressionBaseline:
    """LEGACY_REGRESSION_ONLY golden values, captured from
    evaluate_joint() on main (commit bc0d73f, pre-Faz-2.8.21) with a
    fixed payload. Not from the question bank; not an engineering
    authority claim -- a pure software-consistency lock."""

    PAYLOAD = dict(
        diameter_mm=10, pitch_mm=1.5, stress_area_mm2=58.0, rp02_mpa=900,
        target_yield_ratio=0.75, mu_thread_min=0.10, mu_thread_nom=0.12,
        mu_thread_max=0.14, mu_bearing_min=0.10, mu_bearing_nom=0.12,
        mu_bearing_max=0.14, effective_bearing_diameter_mm=15.0,
        engagement_mm=10.0, internal_rm_mpa=500, bolt_rm_mpa=1000,
        nut_proof_mpa=830,
    )
    EXPECTED = {
        "preload_n": 39150.0,
        "torque_min_nm": 59.29284065733501,
        "torque_nom_nm": 69.3125332345851,
        "torque_max_nm": 79.34244629911926,
        "nut_proof_util_pct": 81.32530120481928,
        "internal_thread_sf": 1.050193699745855,
        "external_thread_sf": 1.8988367774714041,
    }

    def test_evaluate_joint_output_bit_for_bit_matches_pre_phase_baseline(self):
        result = evaluate_joint(**self.PAYLOAD)
        for key, expected_value in self.EXPECTED.items():
            assert result[key] == expected_value, (
                f"{key}: {result[key]!r} != baseline {expected_value!r} -- "
                "a numerical result changed, which this phase must never do"
            )

    def test_api_endpoint_output_matches_the_same_baseline(self, auth_headers):
        r = client.post(
            "/api/engineering/check", json=self.PAYLOAD, headers=auth_headers
        )
        d = r.json()
        for key, expected_value in self.EXPECTED.items():
            assert d[key] == expected_value


# ---------------------------------------------------------------------
# Read-only boundary (mirrors TestReadOnlyBoundary in
# test_faz_2_8_8_formula_validation.py, applied to the new module)
# ---------------------------------------------------------------------
class TestReadOnlyBoundary:
    def test_trace_module_calls_no_calculation_function(self):
        source = Path("backend/engineering_core/trace.py").read_text(encoding="utf-8")
        for banned in (
            "tightening_torque_nm(", "thread_shear_area_mm2(", "evaluate_joint(",
            "preload_from_yield_n(", "shear_strength_mpa(",
        ):
            assert banned not in source, banned

    def test_trace_module_imports_no_calculation_function(self):
        tree = ast.parse(Path("backend/engineering_core/trace.py").read_text(encoding="utf-8"))
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names.update(alias.name for alias in node.names)
        calculation_functions = {
            "tightening_torque_nm", "thread_shear_area_mm2", "evaluate_joint",
            "preload_from_yield_n", "shear_strength_mpa", "thread_friction_angle_rad",
            "pitch_diameter_mm", "minor_diameter_mm", "helix_angle_rad",
            "proof_load_utilization_pct",
        }
        assert not (imported_names & calculation_functions)
