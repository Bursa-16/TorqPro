"""Faz 2.8.19 Stage 4 tests: Washer Resolution Decision History.

Mirrors the Faz 2.8.19 Stage 2/Stage 3 conventions:

1. Behavioral: tests/js/run_washer_resolution_decision_history_tests.js
   (a dependency-free Node/vm harness) run as a subprocess against
   the *actual* declarations extracted live from frontend/index.html.
2. Structural (this module, no browser required): history markup
   presence, decisions-endpoint URL usage, no mutation controls
   (edit/delete/rollback/replay/bulk), no backend/VERSION/README/
   CHANGELOG changes, i18n key parity, quality-gate harness
   registration, decide-success -> history-refresh wiring, and
   blocked/terminal visibility.

Does not modify frontend/index.html from this file, and does not
touch any backend file (Stage 4 is frontend-only -- the backend
GET /{resolution_id}/decisions endpoint was already completed and
tested in Faz 2.8.9).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_washer_resolution_decision_history_tests.js"
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"
QUALITY_GATE_PATH = REPO_ROOT / "tools" / "run_quality_gate.py"

STAGE3_COMMIT = "bdb5d3d3cd72a56e319fb1566aabbe7da3cae3b2"

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
        "Washer Resolution Decision History harness reported failures:\n"
        + result.stdout
        + result.stderr
    )


def test_harness_js_syntax_is_valid():
    result = subprocess.run(
        ["node", "--check", str(HARNESS_PATH)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 2. Structural: history markup presence
# ---------------------------------------------------------------------


def test_history_card_present(frontend_html):
    for element_id in ("wrr-history-card", "wrr-history-status", "wrr-history-content"):
        assert f'id="{element_id}"' in frontend_html, f"missing: {element_id}"


def test_history_card_is_inside_washer_resolution_page(frontend_html):
    start = frontend_html.index('<div id="page-washerresolution" class="page">')
    end = frontend_html.index('<div id="page-governance" class="page">')
    section = frontend_html[start:end]
    assert 'id="wrr-history-card"' in section


def test_history_card_hidden_by_default(frontend_html):
    idx = frontend_html.index('id="wrr-history-card"')
    line_start = frontend_html.rfind("<div", 0, idx)
    line_end = frontend_html.index(">", idx)
    tag = frontend_html[line_start:line_end]
    assert 'style="display:none"' in tag


# ---------------------------------------------------------------------
# 3. Structural: decisions-endpoint contract
# ---------------------------------------------------------------------


def test_history_uses_apirequest_with_correct_endpoint(frontend_html):
    idx = frontend_html.index("async function wrrLoadResolutionHistory")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "apiRequest(" in body
    assert "/decisions'" in body
    assert "encodeURIComponent(resolutionId)" in body
    assert "fetch(" not in body
    # GET only -- no method override to POST/PUT/DELETE.
    assert "method:" not in body


def test_history_required_fields_match_backend_contract(frontend_html):
    idx = frontend_html.index("const WRR_HISTORY_REQUIRED_FIELDS")
    end = frontend_html.index("];", idx)
    literal = frontend_html[idx:end]
    for field in (
        "decision_id", "resolution_id", "previous_status", "new_status",
        "resolution_note", "evidence_reference", "resolved_by", "decided_at",
    ):
        assert field in literal, f"{field} not gated by WRR_HISTORY_REQUIRED_FIELDS"


def test_history_response_order_never_resorted(frontend_html):
    idx = frontend_html.index("function wrrRenderHistoryTable")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    for forbidden in (".sort(", ".reverse("):
        assert forbidden not in body, f"unexpected client-side reordering: {forbidden!r}"
    assert "decisions.map(" in body


# ---------------------------------------------------------------------
# 4. Structural: read-only, no mutation controls
# ---------------------------------------------------------------------


def test_no_mutation_controls_in_history_render(frontend_html):
    idx = frontend_html.index("function wrrRenderHistoryTable")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    for forbidden in ("<button", "<input", "<select", "<textarea", "onclick="):
        msg = f"unexpected mutation control in history render: {forbidden!r}"
        assert forbidden not in body, msg


def test_no_edit_delete_rollback_functions(frontend_html):
    for forbidden_fn in (
        "function wrrEditDecision", "function wrrDeleteDecision",
        "function wrrRollbackDecision", "function wrrReplayDecision",
        "function wrrDuplicateDecision", "function wrrApproveDecision",
        "function wrrRejectDecision",
    ):
        assert forbidden_fn not in frontend_html, f"unexpected: {forbidden_fn}"


def test_no_bulk_or_ai_in_history_scope(frontend_html):
    idx = frontend_html.index("Faz 2.8.19 Stage 4: Washer Resolution Decision History")
    end = frontend_html.index("function miReapplyLanguage(")
    section = frontend_html[idx:end].lower()
    # Narrowed to code-artifact-like terms only: the section's own
    # doc comment legitimately says "no ... bulk action" in prose to
    # disclaim exactly this, which a broader substring match misfires on.
    for forbidden in ("bulkdecide", "'/bulk", "/ai/"):
        assert forbidden not in section, f"unexpected forbidden term: {forbidden!r}"


# ---------------------------------------------------------------------
# 5. Structural: decide-success -> history-refresh wiring
# ---------------------------------------------------------------------


def test_history_loaded_from_detail_success_path(frontend_html):
    idx = frontend_html.index("async function wrrLoadResolutionDetail")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "wrrLoadResolutionHistory(detail.resolution_id)" in body


def test_decide_success_indirectly_refreshes_history_via_detail_reload(frontend_html):
    """Stage 3's success path already calls
    wrrLoadResolutionDetail(detail.resolution_id) after a successful
    decide; Stage 4 hooks history loading into that same detail-load
    success path, so no separate history-refresh call needed to be
    added inside wrrSubmitDecision itself -- confirms both wirings
    are present and connected."""
    submit_idx = frontend_html.index("async function wrrSubmitDecision")
    submit_end = frontend_html.index("\nfunction miReapplyLanguage(")
    submit_body = frontend_html[submit_idx:submit_end]
    assert "await wrrLoadResolutionDetail(detail.resolution_id);" in submit_body

    detail_idx = frontend_html.index("async function wrrLoadResolutionDetail")
    detail_end = frontend_html.index("\n}", detail_idx)
    detail_body = frontend_html[detail_idx:detail_end]
    assert "wrrLoadResolutionHistory" in detail_body


# ---------------------------------------------------------------------
# 6. Structural: blocked/terminal visibility
# ---------------------------------------------------------------------


def test_history_hook_not_gated_by_blocked_or_terminal(frontend_html):
    """History loading is hooked unconditionally into
    wrrLoadResolutionDetail's success path -- it must never check
    detail.is_blocked or detail.is_terminal before loading, unlike
    the decision form which legitimately does gate on those."""
    idx = frontend_html.index("async function wrrLoadResolutionDetail")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    history_call_idx = body.index("wrrLoadResolutionHistory(detail.resolution_id)")
    preceding = body[:history_call_idx]
    # No is_blocked/is_terminal conditional immediately gating the
    # history call itself (they are used elsewhere in this function
    # for the decision form, which is fine and expected).
    tail = preceding[-200:]
    assert "if (detail.is_blocked" not in tail
    assert "if (detail.is_terminal" not in tail


# ---------------------------------------------------------------------
# 7. Backend / VERSION / README / CHANGELOG untouched
# ---------------------------------------------------------------------


def test_stage4_touches_no_backend_or_version_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", STAGE3_COMMIT, "HEAD"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout with the expected Stage 3 commit reachable")
    changed = [f for f in result.stdout.splitlines() if f.strip()]
    for f in changed:
        assert not f.startswith("backend/"), f"unexpected backend file changed in Stage 4: {f}"
    assert "VERSION" not in changed
    assert "README.md" not in changed
    assert "docs/CHANGELOG.md" not in changed


# ---------------------------------------------------------------------
# 8. Translation key parity (scoped)
# ---------------------------------------------------------------------


def test_new_history_keys_present_in_both_languages(frontend_html):
    new_keys = (
        "wrr.history.title", "wrr.history.subtitle", "wrr.history.empty_state",
        "wrr.history.col.decision_id", "wrr.history.col.previous_status",
        "wrr.history.col.new_status", "wrr.history.col.resolution_note",
        "wrr.history.col.evidence_reference", "wrr.history.col.resolved_by",
        "wrr.history.col.decided_at", "wrr.history.col.confidence_level",
    )
    for key in new_keys:
        occurrences = frontend_html.count("'" + key + "':")
        assert occurrences == 2, (
            f"expected exactly 2 occurrences (TR + EN) of {key!r}, got {occurrences}"
        )


# ---------------------------------------------------------------------
# 9. JS syntax (whole file)
# ---------------------------------------------------------------------


def test_frontend_js_syntax_is_valid(tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", FRONTEND_PATH.read_text(encoding="utf-8"), re.S)
    assert scripts
    js_file = tmp_path / "extracted.js"
    js_file.write_text("\n;\n".join(scripts), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 10. Quality gate harness registration
# ---------------------------------------------------------------------


def test_harness_registered_in_quality_gate():
    text = QUALITY_GATE_PATH.read_text(encoding="utf-8")
    assert '"run_washer_resolution_decision_history_tests.js"' in text


def test_prior_stage_harnesses_still_registered():
    text = QUALITY_GATE_PATH.read_text(encoding="utf-8")
    assert '"run_washer_resolution_queue_tests.js"' in text
    assert '"run_washer_resolution_decision_form_tests.js"' in text
