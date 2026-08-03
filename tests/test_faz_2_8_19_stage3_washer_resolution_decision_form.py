"""Faz 2.8.19 Stage 3 tests: Washer Resolution Decision Entry Form.

Two layers, mirroring the Faz 2.8.19 Stage 2 conventions
(tests/test_faz_2_8_19_stage2_washer_resolution_queue_frontend.py):

1. Behavioral: tests/js/run_washer_resolution_decision_form_tests.js
   (a dependency-free Node/vm harness) run as a subprocess against
   the *actual* declarations extracted live from frontend/index.html.
2. Structural (this module, no browser required): form markup
   presence, POST URL/body contract, no backend/VERSION/README/
   CHANGELOG changes, no decision-history UI, no bulk/AI behavior,
   i18n key parity, JS syntax, and quality-gate harness registration.

Does not modify frontend/index.html from this file, and does not
touch any backend file (Stage 3 is frontend-only -- the backend
POST /decide endpoint was already completed and tested in Faz 2.8.9).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_washer_resolution_decision_form_tests.js"
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"
QUALITY_GATE_PATH = REPO_ROOT / "tools" / "run_quality_gate.py"

STAGE2_COMMIT = "2481b21d240b51f49cd0f5b08b2e8ffdde48f29e"

NODE_AVAILABLE = shutil.which("node") is not None
pytestmark = pytest.mark.skipif(
    not NODE_AVAILABLE, reason="node is not available on PATH in this environment"
)


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
        "Washer Resolution Decision Form harness reported failures:\n"
        + result.stdout
        + result.stderr
    )


def test_harness_js_syntax_is_valid():
    result = subprocess.run(
        ["node", "--check", str(HARNESS_PATH)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 2. Structural: form markup presence
# ---------------------------------------------------------------------


def test_decision_form_card_present(frontend_html):
    for element_id in (
        "wrr-decision-form-card", "wrr-decide-blocked-notice", "wrr-decide-terminal-notice",
        "wrr-decide-new-status", "wrr-decide-resolution-note", "wrr-decide-evidence-reference",
        "wrr-decide-resolved-by", "wrr-decide-confidence-level",
        "wrr-decide-validation-error", "wrr-decide-status", "wrr-decide-submit-btn",
    ):
        assert f'id="{element_id}"' in frontend_html, f"missing: {element_id}"


def test_decision_form_is_inside_washer_resolution_page(frontend_html):
    start = frontend_html.index('<div id="page-washerresolution" class="page">')
    end = frontend_html.index('<div id="page-governance" class="page">')
    section = frontend_html[start:end]
    assert 'id="wrr-decision-form-card"' in section


def test_decision_form_hidden_by_default(frontend_html):
    idx = frontend_html.index('id="wrr-decision-form-card"')
    line_start = frontend_html.rfind("<div", 0, idx)
    line_end = frontend_html.index(">", idx)
    tag = frontend_html[line_start:line_end]
    assert 'style="display:none"' in tag


# ---------------------------------------------------------------------
# 3. Structural: request contract
# ---------------------------------------------------------------------


def test_submit_uses_apirequest_post_with_correct_endpoint(frontend_html):
    idx = frontend_html.index("async function wrrSubmitDecision")
    end = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    body = frontend_html[idx:end]
    assert "apiRequest(" in body
    assert "/decide'" in body
    assert "method: 'POST'" in body
    assert "encodeURIComponent(detail.resolution_id)" in body
    assert "fetch(" not in body


def test_request_body_fields_match_backend_contract(frontend_html):
    idx = frontend_html.index("async function wrrSubmitDecision")
    end = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    body = frontend_html[idx:end]
    for field in (
        "new_status", "resolution_note", "evidence_reference",
        "resolved_by", "idempotency_key", "confidence_level",
    ):
        assert field in body, f"missing field in request payload: {field}"
    # decided_at is deliberately never sent by the client -- the
    # backend always generates it server-side (Faz 2.8.9 contract).
    assert "decided_at" not in body


def test_resolution_id_comes_from_loaded_detail_not_a_free_text_input(frontend_html):
    idx = frontend_html.index("async function wrrSubmitDecision")
    end = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    body = frontend_html[idx:end]
    assert "WRR_LAST_DETAIL" in body
    assert "detail.resolution_id" in body
    # No input element for resolution_id anywhere in the form.
    form_start = frontend_html.index('id="wrr-decision-form-card"')
    form_end = frontend_html.index("</div>\n\n  <!-- Faz 2.8.19 Stage 2:") \
        if "</div>\n\n  <!-- Faz 2.8.19 Stage 2:" in frontend_html \
        else frontend_html.index('<div id="page-governance" class="page">')
    form_section = frontend_html[form_start:form_end]
    assert 'id="wrr-decide-resolution-id"' not in form_section


# ---------------------------------------------------------------------
# 4. Structural: idempotency, double-submit guard
# ---------------------------------------------------------------------


def test_idempotency_key_generated_client_side_not_reimplementing_backend(frontend_html):
    idx = frontend_html.index("function wrrGenerateIdempotencyKey")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    # A uniqueness token only -- no conflict-detection or comparison
    # logic (that stays server-side, per Faz 2.8.9's own contract).
    assert "Date.now()" in body or "Math.random()" in body
    assert "ALLOWED_TRANSITIONS" not in body


def test_in_flight_guard_present(frontend_html):
    idx = frontend_html.index("async function wrrSubmitDecision")
    end = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    body = frontend_html[idx:end]
    assert "WRR_DECIDE_IN_FLIGHT" in body
    assert "if (WRR_DECIDE_IN_FLIGHT) return;" in body


def test_key_persists_on_retry_reset_only_on_new_record_or_success(frontend_html):
    reset_idx = frontend_html.index("function wrrResetDecisionForm")
    reset_end = frontend_html.index("\n}", reset_idx)
    reset_body = frontend_html[reset_idx:reset_end]
    assert "wrrGenerateIdempotencyKey()" in reset_body

    submit_idx = frontend_html.index("async function wrrSubmitDecision")
    submit_end = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    submit_body = frontend_html[submit_idx:submit_end]
    catch_idx = submit_body.index("} catch (e) {")
    catch_block = submit_body[catch_idx:]
    assert "wrrResetDecisionForm()" not in catch_block
    assert "WRR_DECIDE_IDEMPOTENCY_KEY = " not in catch_block


# ---------------------------------------------------------------------
# 5. Structural: post-success refresh, blocked/terminal, no forbidden
#    behavior
# ---------------------------------------------------------------------


def test_success_path_refreshes_queue_and_detail(frontend_html):
    idx = frontend_html.index("async function wrrSubmitDecision")
    end = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    body = frontend_html[idx:end]
    assert "await loadWasherResolutionQueue();" in body
    assert "await wrrLoadResolutionDetail(detail.resolution_id);" in body
    assert "wrrResetDecisionForm();" in body


def test_blocked_and_terminal_read_only_from_backend_fields(frontend_html):
    idx = frontend_html.index("function wrrShowDecisionFormForDetail")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "detail.is_blocked" in body
    assert "detail.is_terminal" in body
    # No client-side transition table / status-permission logic.
    assert "ALLOWED_TRANSITIONS" not in body
    assert "TERMINAL_STATUSES" not in body


def test_no_decision_history_endpoint_called(frontend_html):
    idx = frontend_html.index("Faz 2.8.19 Stage 3: Washer Resolution Decision Entry Form")
    end = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    section = frontend_html[idx:end]
    assert "/decisions'" not in section
    assert "/decisions\"" not in section


def test_no_bulk_or_ai_behavior(frontend_html):
    idx = frontend_html.index("Faz 2.8.19 Stage 3: Washer Resolution Decision Entry Form")
    end = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    section = frontend_html[idx:end].lower()
    # Narrowed to code-artifact-like terms only: the section's own
    # doc comment legitimately uses prose like "nothing here is
    # inferred, suggested, or computed" to disclaim exactly these
    # behaviors, which a broader substring match would misfire on.
    for forbidden in ("bulk", "/ai/"):
        assert forbidden not in section, f"unexpected forbidden term: {forbidden!r}"


def test_no_automatic_status_or_confidence_selection(frontend_html):
    idx = frontend_html.index("function wrrValidateDecisionForm")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    # Validation only checks presence/blankness -- it never assigns
    # a default status or confidence value.
    assert "payload.new_status =" not in body
    assert "payload.confidence_level =" not in body


# ---------------------------------------------------------------------
# 6. Backend / VERSION / README / CHANGELOG untouched
# ---------------------------------------------------------------------


def test_stage3_touches_no_backend_or_version_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", STAGE2_COMMIT, "HEAD"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout with the expected Stage 2 commit reachable")
    changed = [f for f in result.stdout.splitlines() if f.strip()]
    for f in changed:
        assert not f.startswith("backend/"), f"unexpected backend file changed in Stage 3: {f}"
    assert "VERSION" not in changed
    assert "README.md" not in changed
    assert "docs/CHANGELOG.md" not in changed


# ---------------------------------------------------------------------
# 7. Translation key parity (scoped)
# ---------------------------------------------------------------------


def test_new_decide_keys_present_in_both_languages(frontend_html):
    new_keys = (
        "wrr.decide.title", "wrr.decide.subtitle", "wrr.decide.blocked_notice",
        "wrr.decide.terminal_notice", "wrr.decide.select_placeholder",
        "wrr.decide.new_status_label", "wrr.decide.resolution_note_label",
        "wrr.decide.evidence_reference_label", "wrr.decide.resolved_by_label",
        "wrr.decide.confidence_level_label", "wrr.decide.confidence_none",
        "wrr.decide.submit_button", "wrr.decide.submitting", "wrr.decide.success",
        "wrr.decide.validation_error_prefix",
    )
    for key in new_keys:
        occurrences = frontend_html.count("'" + key + "':")
        assert occurrences == 2, (
            f"expected exactly 2 occurrences (TR + EN) of {key!r}, got {occurrences}"
        )


# ---------------------------------------------------------------------
# 8. JS syntax (whole file)
# ---------------------------------------------------------------------


def test_frontend_js_syntax_is_valid(tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", FRONTEND_PATH.read_text(encoding="utf-8"), re.S)
    assert scripts
    js_file = tmp_path / "extracted.js"
    js_file.write_text("\n;\n".join(scripts), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 9. Quality gate harness registration
# ---------------------------------------------------------------------


def test_harness_registered_in_quality_gate():
    text = QUALITY_GATE_PATH.read_text(encoding="utf-8")
    assert '"run_washer_resolution_decision_form_tests.js"' in text


def test_prior_stage_2_harness_still_registered():
    text = QUALITY_GATE_PATH.read_text(encoding="utf-8")
    assert '"run_washer_resolution_queue_tests.js"' in text
