"""Faz 2.8.20 Stage 5 tests: Washer Resolution Evidence & Controlled
Closure frontend.

Two layers, mirroring the established Faz 2.8.19 frontend test
conventions (e.g.
tests/test_faz_2_8_19_stage2_washer_resolution_queue_frontend.py):

1. Behavioral: tests/js/run_washer_resolution_evidence_closure_tests.js
   (a dependency-free Node/vm harness) is run as a subprocess against
   the *actual* declarations extracted live from frontend/index.html.
2. Structural (this module, no browser required): quality-gate
   wiring, i18n key parity for the new wrr.evidence.*/wrr.closure.*
   keys, JS syntax, and a Stage-5-scoped "no backend file changed"
   guard (scoped to this stage's own commit range, not one of the
   three historical Faz 2.8.19 stage-boundary tests already known to
   be permanently fragile against any future backend/ addition -- see
   Faz 2.8.20 Stage 2 code review).

Does not modify frontend/index.html from this file, and does not
touch any backend file (Stage 5 is frontend-only by design -- the
backend/API layer was already completed and tested in Stage 4).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_washer_resolution_evidence_closure_tests.js"
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"
QUALITY_GATE_PATH = REPO_ROOT / "tools" / "run_quality_gate.py"

NODE_AVAILABLE = shutil.which("node") is not None
pytestmark = pytest.mark.skipif(
    not NODE_AVAILABLE, reason="node is not available on PATH in this environment"
)

#: Expected HEAD at the start of Stage 5 (the Stage 4 delivery
#: commit) -- the range this stage's own "no backend files changed"
#: guard is scoped to. Not a stand-in for the three permanently
#: fragile Faz 2.8.19 stage-boundary tests.
STAGE4_COMMIT = "8c557b6b9c9b99870410148fde7fea2d7e3252ae"


@pytest.fixture(scope="module")
def frontend_html() -> str:
    return FRONTEND_PATH.read_text(encoding="utf-8")


def _run_harness() -> subprocess.CompletedProcess:
    assert HARNESS_PATH.exists(), f"harness missing: {HARNESS_PATH}"
    return subprocess.run(
        ["node", str(HARNESS_PATH)], capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


# ---------------------------------------------------------------------
# 1. Behavioral: Node/vm harness (subprocess)
# ---------------------------------------------------------------------


def test_harness_all_assertions_pass():
    result = _run_harness()
    assert result.returncode == 0, (
        "Washer Resolution Evidence & Closure harness reported failures:\n"
        + result.stdout
        + result.stderr
    )


def test_harness_reports_success_marker():
    result = _run_harness()
    assert "SUCCESS: run_washer_resolution_evidence_closure_tests.js" in result.stdout


def test_harness_js_syntax_is_valid():
    result = subprocess.run(
        ["node", "--check", str(HARNESS_PATH)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_harness_uses_awaited_main_not_bare_process_exit():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "async function main()" in text
    assert re.search(r"await\s+testFn\(\)", text)
    assert "main().catch(" in text
    assert "process.exit(" not in text
    assert "process.exitCode" in text


def test_harness_file_is_dependency_free():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "require('jsdom')" not in text
    assert "require('puppeteer')" not in text
    assert "require('playwright')" not in text
    stripped = (
        text.replace("require('fs')", "")
        .replace("require('path')", "")
        .replace("require('vm')", "")
        .replace("require('./harness_common')", "")
    )
    assert "require(" not in stripped


# ---------------------------------------------------------------------
# 2. Structural: quality gate wiring
# ---------------------------------------------------------------------


def test_new_harness_registered_in_quality_gate():
    text = QUALITY_GATE_PATH.read_text(encoding="utf-8")
    assert '"run_washer_resolution_evidence_closure_tests.js"' in text


def test_quality_gate_harness_list_unchanged_otherwise():
    """Every pre-existing harness filename must still be present --
    Stage 5 only adds one entry, never removes or reorders others."""
    text = QUALITY_GATE_PATH.read_text(encoding="utf-8")
    for existing in (
        "run_assembly_intelligence_tests.js",
        "run_i18n_tests.js",
        "run_joint_analysis_tests.js",
        "run_material_intelligence_tests.js",
        "run_washer_resolution_report_tests.js",
        "run_joint_revision_list_ux_tests.js",
        "run_washer_resolution_queue_tests.js",
        "run_washer_resolution_decision_form_tests.js",
        "run_washer_resolution_decision_history_tests.js",
    ):
        assert f'"{existing}"' in text, f"missing (regressed): {existing}"


# ---------------------------------------------------------------------
# 3. Structural: new sections present, additive-only
# ---------------------------------------------------------------------


def test_new_evidence_closure_cards_present(frontend_html):
    for dom_id in (
        "wrr-evidence-card", "wrr-evidence-status", "wrr-evidence-content", "wrr-evidence-table",
        "wrr-evidence-form-card", "wrr-evidence-type", "wrr-evidence-title",
        "wrr-evidence-description", "wrr-evidence-source-reference",
        "wrr-evidence-source-locator", "wrr-evidence-source-url",
        "wrr-evidence-source-standard", "wrr-evidence-created-by",
        "wrr-evidence-submit-btn", "wrr-evidence-validation-error", "wrr-evidence-status-msg",
        "wrr-closure-readiness-card", "wrr-closure-readiness-status",
        "wrr-closure-readiness-content",
        "wrr-close-form-card", "wrr-close-rationale", "wrr-close-closed-by",
        "wrr-close-submit-btn", "wrr-close-validation-error", "wrr-close-status-msg",
        "wrr-closure-result-card", "wrr-closure-result-content",
    ):
        assert f'id="{dom_id}"' in frontend_html, f"missing DOM id: {dom_id}"


def test_new_sections_are_inside_the_existing_washer_resolution_page(frontend_html):
    start = frontend_html.index('<div id="page-washerresolution" class="page">')
    end = frontend_html.index('<div id="page-governance" class="page">')
    section = frontend_html[start:end]
    assert 'id="wrr-evidence-card"' in section
    assert 'id="wrr-closure-result-card"' in section
    # And the pre-existing queue/detail/decision/history sections are
    # still there, unmoved.
    assert 'id="wrr-queue-table"' in section
    assert 'id="wrr-detail-content"' in section
    assert 'id="wrr-decision-form-card"' in section
    assert 'id="wrr-history-card"' in section


def test_existing_cards_not_removed_or_reordered(frontend_html):
    """Queue < Detail < Decision Form < Decision History < (new Stage
    5 cards) -- the pre-existing four cards keep their relative
    order; Stage 5 only appends after them."""
    positions = [
        frontend_html.index('id="wrr-queue-content"'),
        frontend_html.index('id="wrr-detail-card"'),
        frontend_html.index('id="wrr-decision-form-card"'),
        frontend_html.index('id="wrr-history-card"'),
        frontend_html.index('id="wrr-evidence-card"'),
    ]
    assert positions == sorted(positions), "existing card order was disturbed"


def test_evidence_type_select_has_seven_options(frontend_html):
    m = re.search(
        r'<select class="form-select" id="wrr-evidence-type">(.*?)</select>',
        frontend_html, re.S,
    )
    assert m, "evidence-type select not found"
    options = re.findall(r'<option value="([^"]*)"', m.group(1))
    real_options = [o for o in options if o != ""]
    assert len(real_options) == 7, real_options
    assert set(real_options) == {
        "authoritative_standard", "manufacturer_document", "approved_engineering_source",
        "internal_measurement", "comparison_analysis", "legacy_provenance_reference", "other",
    }


def test_backend_generated_fields_absent_from_new_forms(frontend_html):
    start = frontend_html.index('id="wrr-evidence-card"')
    end = frontend_html.index('id="page-governance"')
    section = frontend_html[start:end]
    for forbidden in (
        'id="wrr-evidence-id"', 'id="wrr-evidence-created-at"',
        'id="wrr-evidence-checksum"', 'id="wrr-evidence-verification-status"',
        'id="wrr-close-id"', 'id="wrr-closed-at"', 'id="wrr-close-checksum"',
        "idempotency_key",
    ):
        assert forbidden not in section, f"unexpected backend-generated field artifact: {forbidden!r}"


def test_no_verify_reject_or_reopen_ui(frontend_html):
    start = frontend_html.index('id="wrr-evidence-card"')
    end = frontend_html.index('id="page-governance"')
    section = frontend_html[start:end]
    for forbidden in (
        'onclick="wrrVerify', 'onclick="wrrReject', 'onclick="wrrReopen',
        'id="wrr-reopen', 'id="wrr-verify', 'id="wrr-reject',
    ):
        assert forbidden not in section, f"unexpected out-of-scope UI action: {forbidden!r}"


def test_detail_load_calls_new_loaders(frontend_html):
    idx = frontend_html.index("async function wrrLoadResolutionDetail")
    end = frontend_html.index("\n}\n", idx)
    body = frontend_html[idx:end]
    for call in ("wrrLoadEvidence(detail.resolution_id)",
                 "wrrLoadClosureReadiness(detail.resolution_id)",
                 "wrrLoadClosure(detail.resolution_id)"):
        assert call in body, f"wrrLoadResolutionDetail no longer calls: {call}"
    # Existing calls must still be present, unremoved.
    assert "wrrShowDecisionFormForDetail(detail)" in body
    assert "wrrLoadResolutionHistory(detail.resolution_id)" in body


# ---------------------------------------------------------------------
# 4. Structural: render/state functions present
# ---------------------------------------------------------------------


def test_new_functions_present(frontend_html):
    for fn in (
        "async function wrrLoadEvidence", "function wrrRenderEvidenceTable",
        "function wrrShowEvidenceFormForDetail", "function wrrValidateEvidenceForm",
        "async function wrrSubmitEvidence",
        "async function wrrLoadClosureReadiness", "function wrrRenderClosureReadiness",
        "function wrrShowCloseFormForReadiness",
        "async function wrrLoadClosure", "function wrrRenderClosure",
        "function wrrValidateCloseForm", "async function wrrSubmitClosure",
        "function wrrResetEvidenceClosureState",
    ):
        assert fn in frontend_html, f"missing: {fn}"


def test_new_state_variables_present(frontend_html):
    for state in (
        "WRR_EVIDENCE_IN_FLIGHT", "WRR_CLOSE_IN_FLIGHT",
        "WRR_LAST_READINESS", "WRR_LAST_CLOSURE",
    ):
        assert state in frontend_html, f"missing state variable: {state}"


def test_apirequest_not_redefined(frontend_html):
    assert frontend_html.count("async function apiRequest(") == 1


# ---------------------------------------------------------------------
# 5. i18n key parity for the new namespace
# ---------------------------------------------------------------------


def test_new_wrr_evidence_closure_keys_present_in_both_languages(frontend_html):
    new_keys = (
        "wrr.evidence.list_title", "wrr.evidence.add_title", "wrr.evidence.type_label",
        "wrr.evidence.title_label", "wrr.evidence.description_label",
        "wrr.evidence.source_reference_label", "wrr.evidence.source_locator_label",
        "wrr.evidence.source_url_label", "wrr.evidence.source_standard_label",
        "wrr.evidence.created_by_label", "wrr.evidence.empty_state", "wrr.evidence.loading",
        "wrr.evidence.success", "wrr.evidence.status.unverified", "wrr.evidence.status.verified",
        "wrr.evidence.status.rejected",
        "wrr.closure.readiness_title", "wrr.closure.close_title", "wrr.closure.rationale_label",
        "wrr.closure.closed_by_label", "wrr.closure.ready", "wrr.closure.not_ready",
        "wrr.closure.blocking_reasons_label", "wrr.closure.result_title",
        "wrr.closure.closure_id_label", "wrr.closure.evidence_ids_label",
    )
    for key in new_keys:
        occurrences = frontend_html.count("'" + key + "':")
        assert occurrences == 2, (
            f"expected exactly 2 occurrences (EN + TR) of {key!r}, got {occurrences}"
        )


def test_i18n_key_parity_suite_passes():
    """Delegates to the existing, permanent, global TR/EN parity gate
    (tests/test_i18n_key_parity.py) rather than duplicating its whole-
    file walk here -- this module only asserts the *new* keys exist
    (above); overall en/tr set equality is that module's job."""
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/test_i18n_key_parity.py", "-q"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------
# 6. JS syntax (whole extracted <script> block)
# ---------------------------------------------------------------------


def test_frontend_js_syntax_is_valid(tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", FRONTEND_PATH.read_text(encoding="utf-8"), re.S)
    assert scripts
    js_file = tmp_path / "extracted.js"
    js_file.write_text("\n;\n".join(scripts), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 7. Backend files untouched in the Stage 5 commit range
# ---------------------------------------------------------------------


def test_stage5_touches_no_backend_files():
    """Scoped to this stage's own commit range (Stage 4 HEAD..HEAD),
    not a permanently-pinned historical boundary -- deliberately not
    one of the three known-fragile Faz 2.8.19 stage-boundary tests
    (see Faz 2.8.20 Stage 2 code review's root-cause analysis of why
    those are pinned against a moving HEAD)."""
    result = subprocess.run(
        ["git", "diff", "--name-only", STAGE4_COMMIT, "HEAD"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout with the expected Stage 4 commit reachable")
    changed = [f for f in result.stdout.splitlines() if f.strip()]
    for f in changed:
        assert not f.startswith("backend/"), f"unexpected backend file changed in Stage 5: {f}"
    assert "VERSION" not in changed
    assert "README.md" not in changed
    assert "docs/CHANGELOG.md" not in changed


def test_only_expected_files_changed_in_stage5():
    result = subprocess.run(
        ["git", "diff", "--name-only", STAGE4_COMMIT, "HEAD"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout with the expected Stage 4 commit reachable")
    changed = {f for f in result.stdout.splitlines() if f.strip()}
    allowed = {
        "frontend/index.html",
        "tests/js/run_washer_resolution_evidence_closure_tests.js",
        "tests/test_faz_2_8_20_stage5_washer_resolution_evidence_closure_frontend.py",
        "tools/run_quality_gate.py",
    }
    unexpected = changed - allowed
    assert not unexpected, f"unexpected files changed in Stage 5: {sorted(unexpected)}"
