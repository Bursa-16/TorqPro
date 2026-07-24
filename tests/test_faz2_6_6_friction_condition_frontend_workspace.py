"""Faz 2.6.6 -- Friction Condition Frontend Workspace.

Backend scope: a minimal, additive, read-only GET /api/friction-condition
list endpoint for the frontend condition selector. Assess/report-preview
endpoints (Faz 2.6.4/2.6.5) are unaffected -- regression-tested here.

Frontend scope (structural, non-browser checks -- see
docs/phases/PHASE_2.6.6_FRICTION_CONDITION_FRONTEND_WORKSPACE.md for
the manual/Playwright browser verification record): JS syntax,
presence of the new navigation item and page, panel id uniqueness,
absence of forbidden recommendation terms in the shipped markup, and
that no external framework/bundler dependency was introduced.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.library import population  # noqa: E402

client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"


def _auth():
    r = client.post("/api/login", json={"username": "Protype Lab", "password": "A1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def _base_payload(**overrides):
    payload = {
        "diameter_mm": 10, "pitch_mm": 1.5, "stress_area_mm2": 58.0, "rp02_mpa": 900,
        "target_yield_ratio": 0.75, "mu_thread_min": 0.10, "mu_thread_nom": 0.12,
        "mu_thread_max": 0.14, "mu_bearing_min": 0.10, "mu_bearing_nom": 0.12,
        "mu_bearing_max": 0.14, "effective_bearing_diameter_mm": 15.0,
        "engagement_mm": 10.0, "internal_rm_mpa": 500, "bolt_rm_mpa": 1000,
        "nut_proof_mpa": 830,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------
# Backend: GET /api/friction-condition list endpoint
# ---------------------------------------------------------------------

def test_list_endpoint_returns_all_live_records():
    r = client.get("/api/friction-condition", headers=_auth())
    assert r.status_code == 200, r.text
    body = r.json()
    live = population.load_population_records("friction condition library")
    assert len(body) == len(live)


def test_list_endpoint_fields_are_minimal():
    r = client.get("/api/friction-condition", headers=_auth())
    body = r.json()
    assert body  # 18 live records
    expected_keys = {
        "id", "coating_reference", "lubricant_reference", "friction_model",
        "overall_friction_coefficient_min", "overall_friction_coefficient_max",
        "verification_status", "source_type", "status",
    }
    for item in body:
        assert set(item.keys()) == expected_keys


def test_list_endpoint_omits_full_traceability_fields():
    """The list must not carry source_reference/engineering_notes/
    checksum -- those belong to report-preview, not the selector
    list (directive: "gereksiz tüm veri setini göndermesin")."""
    r = client.get("/api/friction-condition", headers=_auth())
    body = r.json()
    for item in body:
        assert "source_reference" not in item
        assert "engineering_notes" not in item
        assert "checksum" not in item


def test_list_endpoint_requires_auth():
    r = client.get("/api/friction-condition")
    assert r.status_code in (401, 403)


def test_list_endpoint_json_serializable_and_deterministic():
    r1 = client.get("/api/friction-condition", headers=_auth())
    r2 = client.get("/api/friction-condition", headers=_auth())
    assert r1.json() == r2.json()


# ---------------------------------------------------------------------
# Backend regression: assess / report-preview / engineering-check
# ---------------------------------------------------------------------

def test_assess_endpoint_regression_unaffected():
    payload = {"friction_condition_id": "FC-COAT-GEOMET"}
    r = client.post("/api/friction-condition/assess", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["friction_condition_id"] == "FC-COAT-GEOMET"


def test_report_preview_endpoint_regression_unaffected():
    payload = {"friction_condition_id": "FC-COAT-GEOMET"}
    r = client.post("/api/friction-condition/report-preview", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    assert "safety_labels" in r.json()


def test_engineering_check_regression_unaffected():
    r = client.post("/api/engineering/check", json=_base_payload(), headers=_auth())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["torque_min_nm"] < d["torque_nom_nm"] < d["torque_max_nm"]


def test_list_endpoint_unknown_route_variants_return_404_not_500():
    r = client.get("/api/friction-condition/does-not-exist", headers=_auth())
    assert r.status_code == 404


# ---------------------------------------------------------------------
# Frontend: structural checks (no browser required)
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def frontend_html() -> str:
    return FRONTEND_PATH.read_text(encoding="utf-8")


def test_frontend_still_a_single_file():
    """No new HTML/JS/CSS file was introduced -- the workspace lives
    entirely inside the existing single-file frontend."""
    frontend_files = list((REPO_ROOT / "frontend").iterdir())
    names = {f.name for f in frontend_files}
    assert names == {"index.html", "manifest.webmanifest", "service-worker.js"}


def test_frontend_navigation_item_present(frontend_html):
    assert "showPage('frictioncondition')" in frontend_html
    assert 'id="page-frictioncondition"' in frontend_html


def test_frontend_module_named_friction_condition_not_lubrication_module(frontend_html):
    start = frontend_html.index('id="page-frictioncondition"')
    end = frontend_html.index('id="page-norm"')
    section = frontend_html[start:end]
    assert "Friction Condition" in section
    assert "Lubrication Module" not in section


def test_frontend_panel_ids_are_unique(frontend_html):
    panel_ids = re.findall(r'id="(fc-[a-z0-9-]+)"', frontend_html)
    assert panel_ids  # at least one found
    assert len(panel_ids) == len(set(panel_ids)), "duplicate fc- panel ids found"


def test_frontend_js_syntax_is_valid(tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", FRONTEND_PATH.read_text(encoding="utf-8"), re.S)
    assert scripts
    js_file = tmp_path / "extracted.js"
    js_file.write_text("\n;\n".join(scripts), encoding="utf-8")
    result = subprocess.run(
        ["node", "--check", str(js_file)], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_frontend_no_new_framework_or_bundler_reference(frontend_html):
    lowered = frontend_html.lower()
    forbidden_refs = (
        "webpack", "vite.config", "cdnjs.cloudflare.com/ajax/libs/react",
        "cdnjs.cloudflare.com/ajax/libs/vue", "angular.min.js",
    )
    for forbidden in forbidden_refs:
        assert forbidden not in lowered, f"unexpected framework/bundler reference: {forbidden!r}"


def test_frontend_no_forbidden_recommendation_terms(frontend_html):
    start = frontend_html.index('id="page-frictioncondition"')
    end = frontend_html.index('id="page-norm"')
    section = frontend_html[start:end].lower()
    script_start = frontend_html.index("<script>")
    fc_js = frontend_html[script_start:]
    forbidden = (
        "recommended torque", "torque reduction percentage", "best lubricant",
        "best coating", "production approved", "certified iso 16047",
        "torque decomposition graph", "preload estimate",
    )
    for phrase in forbidden:
        assert phrase not in section, f"forbidden phrase in HTML: {phrase!r}"
        assert phrase not in fc_js.lower(), f"forbidden phrase in JS: {phrase!r}"


def test_frontend_uses_text_escaping_helper_before_interpolation(frontend_html):
    """Guard against unescaped backend text reaching innerHTML: the
    workspace's render functions must route dynamic values through
    fcEsc/fcEscRaw/fcFmtLabel, not raw template interpolation of
    report fields."""
    assert "function fcEsc(" in frontend_html
    assert "function fcEscRaw(" in frontend_html


def test_frontend_stale_response_guard_present(frontend_html):
    assert "FC_REQUEST_SEQ" in frontend_html
    assert "seq !== FC_REQUEST_SEQ" in frontend_html


def test_frontend_self_comparison_label_present(frontend_html):
    assert "Self-comparison" in frontend_html
    assert "is_self_comparison" in frontend_html


def test_frontend_download_reuses_existing_download_helper(frontend_html):
    """No new parallel download mechanism -- reuses downloadText()."""
    assert "downloadText('FrictionCondition_" in frontend_html


def test_frontend_json_download_function_exists(frontend_html):
    assert "function downloadFrictionConditionReportJSON()" in frontend_html


# ---------------------------------------------------------------------
# Faz 2.6.7 -- Intended Use control (closes the gap where
# INTENDED_USE_MINIMUM_LEVEL / friction_intended_use existed on the
# backend since Faz 2.6.4/2.6.5 but had no frontend input control, so
# the intended-use gap warning could never be triggered from the UI).
# ---------------------------------------------------------------------

def test_frontend_intended_use_selector_present(frontend_html):
    assert 'id="fc-intended-use"' in frontend_html
    for value in ("reference_comparison", "engineering_calculation", "production_release"):
        assert f'value="{value}"' in frontend_html


def test_frontend_intended_use_selector_matches_backend_enum(frontend_html):
    """The three option values must be exactly the keys backend
    INTENDED_USE_MINIMUM_LEVEL recognizes -- no invented values."""
    from backend.calculation_engine.friction_recommendations import INTENDED_USE_MINIMUM_LEVEL
    start = frontend_html.index('id="fc-intended-use"')
    end = frontend_html.index("</select>", start)
    section = frontend_html[start:end]
    # Attribute-order-agnostic: Faz 2.6.8 added a data-i18n attribute
    # between value="..." and the closing ">" for i18n wiring; only
    # the value itself (what's actually sent to the API) matters here.
    option_values = set(re.findall(r'<option value="([a-z_]+)"[^>]*>', section))
    assert option_values == set(INTENDED_USE_MINIMUM_LEVEL.keys())


def test_frontend_intended_use_sent_as_friction_intended_use_field(frontend_html):
    """Guards against payload key drift: the API model field is
    ``friction_intended_use`` (FrictionConditionReportPreview), not
    ``intended_use`` (that name belongs to the /assess model)."""
    assert "payload.friction_intended_use" in frontend_html
    assert "getElementById('fc-intended-use')" in frontend_html


def test_frontend_intended_use_resets_on_condition_change(frontend_html):
    start = frontend_html.index("async function selectFrictionCondition(id)")
    end = frontend_html.index("\n}", start)
    section = frontend_html[start:end]
    assert "fc-intended-use" in section


def test_report_preview_surfaces_intended_use_gap_warning():
    """End-to-end: an intended_use that exceeds what FC-COAT-GEOMET's
    data supports must produce a gap warning in engineering_warnings,
    the same list fcRenderWarnings() reads."""
    payload = {
        "friction_condition_id": "FC-COAT-GEOMET",
        "friction_intended_use": "production_release",
    }
    r = client.post("/api/friction-condition/report-preview", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    warnings = r.json()["engineering_warnings"]
    assert any("intended_use='production_release'" in w for w in warnings)


def test_report_preview_no_gap_warning_when_intended_use_omitted():
    payload = {"friction_condition_id": "FC-COAT-GEOMET"}
    r = client.post("/api/friction-condition/report-preview", json=payload, headers=_auth())
    assert r.status_code == 200, r.text
    warnings = r.json()["engineering_warnings"]
    assert not any("intended_use=" in w for w in warnings)
