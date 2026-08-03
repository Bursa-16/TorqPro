"""Faz 2.8.19 Stage 2 tests: Washer Resolution Queue / Detail frontend.

Two layers, mirroring the Faz 2.8.9 Stage 5B frontend test conventions
(tests/test_faz_2_8_9_stage5_frontend.py):

1. Behavioral: tests/js/run_washer_resolution_queue_tests.js (a
   dependency-free Node/vm harness) is run as a subprocess against
   the *actual* declarations extracted live from frontend/index.html.
2. Structural (this module, no browser required): page section
   presence, API endpoint string usage through the established
   `apiRequest` utility, no POST /decide anywhere in this scope,
   render-function presence, i18n key parity, JS syntax via
   `node --check`, and a static overflow-risk proxy (same technique
   as the Stage 5 wrapper, no browser dependency).

Does not modify frontend/index.html from this file, and does not
touch any backend file (Stage 2 is frontend-only by design -- the
backend/API layer was already completed and tested in Stage 1).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_washer_resolution_queue_tests.js"
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"

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
        "Washer Resolution Queue harness reported failures:\n"
        + result.stdout
        + result.stderr
    )


def test_harness_file_is_dependency_free():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "require('jsdom')" not in text
    assert "require('puppeteer')" not in text
    assert "require('playwright')" not in text
    assert "require(" not in text.replace("require('fs')", "").replace(
        "require('path')", ""
    ).replace("require('vm')", "").replace("require('./harness_common')", "")


def test_harness_uses_awaited_main_not_bare_process_exit():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "async function main()" in text
    assert re.search(r"await\s+testFn\(\)", text)
    assert "main().catch(" in text
    assert "process.exit(" not in text
    assert "process.exitCode" in text


def test_harness_never_calls_decide_endpoint():
    """Structural guard, independent of the harness's own runtime
    assertions: the harness source text itself must never reference
    a POST /decide call or a decide-endpoint path as something it
    exercises (only as a string it explicitly checks was NOT
    called)."""
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "method:'POST'" not in text
    assert 'method: "POST"' not in text
    assert "method:\"POST\"" not in text


def test_harness_js_syntax_is_valid():
    result = subprocess.run(
        ["node", "--check", str(HARNESS_PATH)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 2. Structural: section presence
# ---------------------------------------------------------------------


def test_queue_section_present(frontend_html):
    assert 'id="wrr-queue-status"' in frontend_html
    assert 'id="wrr-queue-content"' in frontend_html
    assert 'id="wrr-queue-table"' in frontend_html


def test_detail_section_present(frontend_html):
    assert 'id="wrr-detail-card"' in frontend_html
    assert 'id="wrr-detail-status"' in frontend_html
    assert 'id="wrr-detail-content"' in frontend_html


def test_new_sections_are_inside_the_existing_washer_resolution_page(frontend_html):
    start = frontend_html.index('<div id="page-washerresolution" class="page">')
    end = frontend_html.index('<div id="page-governance" class="page">')
    section = frontend_html[start:end]
    assert 'id="wrr-queue-table"' in section
    assert 'id="wrr-detail-content"' in section
    # And the pre-existing report section is still there, unmoved.
    assert 'id="wrr-summary-cards"' in section


def test_showpage_dispatcher_wires_queue_load(frontend_html):
    idx = frontend_html.index("id==='washerresolution'")
    end = frontend_html.index("}", idx)
    dispatch = frontend_html[idx:end]
    assert "loadWasherResolutionReport()" in dispatch
    assert "loadWasherResolutionQueue()" in dispatch


# ---------------------------------------------------------------------
# 3. Structural: endpoints used through apiRequest(), no /decide
# ---------------------------------------------------------------------


def test_queue_uses_apirequest_with_correct_endpoint(frontend_html):
    idx = frontend_html.index("async function loadWasherResolutionQueue")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "apiRequest('/api/library/washers/resolutions/queue')" in body
    assert "fetch(" not in body


def test_detail_uses_apirequest_with_resolution_id(frontend_html):
    idx = frontend_html.index("async function wrrLoadResolutionDetail")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "apiRequest(" in body
    assert "/api/library/washers/resolutions/" in body
    assert "encodeURIComponent(resolutionId)" in body
    assert "fetch(" not in body


def test_no_post_decide_anywhere_in_frontend_stage2_additions(frontend_html):
    """Stage 2 is read-only by design: no decision-entry form, no
    POST /decide call, anywhere in the new queue/detail code. Checks
    for the quoted-path-fragment pattern an actual call would use
    (e.g. `'/decide'`) rather than a bare substring match, since the
    section's own doc comments legitimately mention "POST /decide"
    in prose to explain what is deliberately NOT called."""
    start = frontend_html.index("Faz 2.8.19 Stage 2: Washer Resolution Queue")
    end = frontend_html.index("function miReapplyLanguage(")
    section = frontend_html[start:end]
    assert "/decide'" not in section
    assert '/decide"' not in section
    assert "method:'POST'" not in section
    assert "method: 'POST'" not in section


def test_no_decision_form_fields_introduced(frontend_html):
    """No new_status/resolution_note/evidence_reference/resolved_by
    input fields anywhere in the new Stage 2 markup -- those belong
    to a future decision-entry stage, explicitly out of scope here."""
    start = frontend_html.index('<!-- Faz 2.8.19 Stage 2:')
    end = frontend_html.index('<div id="page-governance" class="page">')
    section = frontend_html[start:end]
    for forbidden in ("id=\"wrr-decide-", "new_status", "idempotency_key"):
        assert forbidden not in section, f"unexpected decision-form artifact: {forbidden!r}"


# ---------------------------------------------------------------------
# 4. Structural: render functions present, reuse of existing helpers
# ---------------------------------------------------------------------


def test_render_functions_present(frontend_html):
    for fn in (
        "function wrrRenderQueueTable",
        "async function wrrLoadResolutionDetail",
        "function wrrRenderDetail",
        "function wrrDetailField",
        "function wrrQueueRecordIsWellFormed",
        "function wrrDetailIsWellFormed",
    ):
        assert fn in frontend_html, f"missing: {fn}"


def test_queue_table_reuses_existing_status_label_helper(frontend_html):
    """No second status->label mapping is introduced -- the queue
    table calls the same wrrStatusLabel() the report section already
    uses, per the Faz 2.8.9 no-duplicated-status-logic principle."""
    idx = frontend_html.index("function wrrRenderQueueTable")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "wrrStatusLabel(r.source_status)" in body
    assert "wrrStatusLabel(r.effective_status)" in body


def test_queue_required_fields_match_stage1_api_contract(frontend_html):
    idx = frontend_html.index("const WRR_QUEUE_REQUIRED_FIELDS")
    end = frontend_html.index("];", idx)
    literal = frontend_html[idx:end]
    for field in (
        "resolution_id", "washer_record_id", "issue_type", "source_status",
        "effective_status", "decision_count", "is_blocked", "is_terminal",
    ):
        assert field in literal, f"{field} not gated by WRR_QUEUE_REQUIRED_FIELDS"


def test_detail_required_fields_match_stage1_api_contract(frontend_html):
    idx = frontend_html.index("const WRR_DETAIL_REQUIRED_FIELDS")
    end = frontend_html.index("];", idx)
    literal = frontend_html[idx:end]
    for field in (
        "resolution_id", "washer_record_id", "issue_type", "reason_code",
        "source_status", "effective_status", "decision_count", "is_blocked",
        "is_terminal", "resolution_note", "evidence_reference",
        "resolved_standard", "resolved_by", "resolved_at", "confidence_level",
        "requires_authoritative_source",
    ):
        assert field in literal, f"{field} not gated by WRR_DETAIL_REQUIRED_FIELDS"


def test_loading_and_error_states_present(frontend_html):
    fn_names = (
        "async function loadWasherResolutionQueue",
        "async function wrrLoadResolutionDetail",
    )
    for fn_name in fn_names:
        idx = frontend_html.index(fn_name)
        end = frontend_html.index("\n}", idx)
        body = frontend_html[idx:end]
        assert "wrr.loading" in body
        assert "catch (e)" in body
        assert "wrr.api_error_prefix" in body
        assert "alert-danger" in body


def test_malformed_response_protection_present(frontend_html):
    idx = frontend_html.index("async function loadWasherResolutionQueue")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "wrrQueueRecordIsWellFormed" in body
    assert "wrr.malformed_response" in body

    idx2 = frontend_html.index("async function wrrLoadResolutionDetail")
    end2 = frontend_html.index("\n}", idx2)
    body2 = frontend_html[idx2:end2]
    assert "wrrDetailIsWellFormed" in body2
    assert "wrr.malformed_response" in body2


def test_report_render_functions_untouched(frontend_html):
    """The pre-existing report render functions must still be
    present, unmodified in name/signature -- Stage 2 is additive
    only."""
    for fn in (
        "function wrrRenderAll",
        "function wrrRenderSummaryCards",
        "function wrrRenderDistribution",
        "function wrrRenderIssueTypeDistribution",
        "function wrrRenderLatestDecisions",
        "function wrrRenderIntegrity",
    ):
        assert fn in frontend_html, f"missing (regressed): {fn}"


# ---------------------------------------------------------------------
# 5. Translation key parity (scoped + whole-file via the Stage 5
#    wrapper's own parity tests, not duplicated here)
# ---------------------------------------------------------------------


def test_new_wrr_keys_present_in_both_languages(frontend_html):
    new_keys = (
        "wrr.queue.title", "wrr.queue.subtitle", "wrr.queue.detail_button",
        "wrr.queue.col.washer_record_id", "wrr.queue.col.issue_type",
        "wrr.queue.col.source_status", "wrr.queue.col.is_blocked", "wrr.queue.col.is_terminal",
        "wrr.detail.title", "wrr.detail.subtitle", "wrr.detail.reason_code",
        "wrr.detail.resolution_note", "wrr.detail.evidence_reference",
        "wrr.detail.resolved_standard", "wrr.detail.resolved_by", "wrr.detail.resolved_at",
        "wrr.detail.confidence_level", "wrr.detail.requires_authoritative_source",
        "wrr.bool.yes", "wrr.bool.no",
    )
    for key in new_keys:
        occurrences = frontend_html.count("'" + key + "':")
        assert occurrences == 2, (
            f"expected exactly 2 occurrences (TR + EN) of {key!r}, got {occurrences}"
        )


# ---------------------------------------------------------------------
# 6. JS syntax
# ---------------------------------------------------------------------


def test_frontend_js_syntax_is_valid(tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", FRONTEND_PATH.read_text(encoding="utf-8"), re.S)
    assert scripts
    js_file = tmp_path / "extracted.js"
    js_file.write_text("\n;\n".join(scripts), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 7. 1366x768 overflow-risk proxy (same technique as the Stage 5
#    wrapper, no browser dependency)
# ---------------------------------------------------------------------


def _wrr_section_html(frontend_html: str) -> str:
    start = frontend_html.index('<div id="page-washerresolution" class="page">')
    end = frontend_html.index('<div id="page-governance" class="page">')
    return frontend_html[start:end]


def test_no_fixed_large_pixel_widths_introduced(frontend_html):
    section = _wrr_section_html(frontend_html)
    widths = re.findall(r"width\s*:\s*(\d+)px", section)
    oversized = [w for w in widths if int(w) > 1200]
    assert not oversized, f"fixed pixel width(s) that could overflow 1366px: {oversized}"


def test_queue_table_uses_existing_scrollable_table_class(frontend_html):
    idx = frontend_html.index("function wrrRenderQueueTable")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "sc-table" in body
    assert "sc-table-wrap" in body


# ---------------------------------------------------------------------
# 8. Backend/VERSION/README/CHANGELOG untouched (Stage 2 is
#    frontend-only)
# ---------------------------------------------------------------------


def test_stage2_touches_no_backend_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "58ca1d487c0f4bdfd7ac0937ed260d5ed98f6732", "HEAD"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout with the expected Stage 1 commit reachable")
    changed = [f for f in result.stdout.splitlines() if f.strip()]
    for f in changed:
        assert not f.startswith("backend/"), f"unexpected backend file changed in Stage 2: {f}"
    assert "VERSION" not in changed
    assert "README.md" not in changed
    assert "docs/CHANGELOG.md" not in changed
