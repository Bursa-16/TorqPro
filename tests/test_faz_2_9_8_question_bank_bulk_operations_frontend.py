"""Faz 2.9.8 tests: Question Bank bulk lifecycle + tag operations
frontend (frontend/index.html).

Structural only (no browser, no Node/vm behavioral harness -- same
minimum bar as tests/test_faz_2_9_7_question_bank_admin_ui_frontend.py:
JS *syntax* validity via `node --check`, everything else via plain
text/regex assertions against the file). Covers: checkbox column +
select-all presence, selected-count UI, bulk toolbar presence, bulk
transition/tags endpoint wiring, every lifecycle bulk action function,
tag add/remove wiring, the double-submit guard, bulk result rendering,
QB_BULK_SELECTED state, qb.bulk.* TR/EN key parity, and that every
referenced qb.bulk.* key actually exists in both languages.

Does not modify frontend/index.html from this file, and does not touch
the backend Faz 2.9.8 files (see
tests/test_faz_2_9_8_question_bank_bulk_operations.py for that).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"

NODE_AVAILABLE = shutil.which("node") is not None


@pytest.fixture(scope="module")
def frontend_html() -> str:
    return FRONTEND_PATH.read_text(encoding="utf-8")


def _extract_script(html: str) -> str:
    m = re.search(r"<script>([\s\S]*?)</script>", html)
    assert m, "no <script> block found"
    return m.group(1)


def _extract_lang_dict_literal(script: str, lang: str) -> str:
    idx = script.index("const I18N = {")
    lang_idx = script.index(f"{lang}: {{", idx)
    start = script.index("{", lang_idx)
    depth = 0
    i = start
    for i in range(start, len(script)):
        if script[i] == "{":
            depth += 1
        elif script[i] == "}":
            depth -= 1
            if depth == 0:
                break
    return script[start:i + 1]


def _keys_in_literal(literal: str) -> list:
    return re.findall(r"'([a-zA-Z0-9_.]+)':", literal)


def _qb_section_text(html: str) -> str:
    start = html.index("// ========== QUESTION BANK ADMIN UI (Faz 2.9.7) ==========")
    end = html.index("// ========== BAŞLAT ==========")
    return html[start:end]


@pytest.fixture(scope="module")
def qb_js(frontend_html):
    return _qb_section_text(frontend_html)


# ---------------------------------------------------------------------
# 1. Checkbox column + select-all
# ---------------------------------------------------------------------


def test_select_all_checkbox_present_in_table_header(frontend_html):
    assert 'id="qb-select-all"' in frontend_html
    assert "qbToggleSelectAll(this.checked)" in frontend_html


def test_select_all_is_inside_the_question_list_table_head(frontend_html):
    table_idx = frontend_html.index('id="qb-list-table"')
    thead_end = frontend_html.index("</thead>", table_idx)
    assert 'id="qb-select-all"' in frontend_html[table_idx:thead_end]


def test_row_checkbox_wired_in_render_list(qb_js):
    idx = qb_js.index("function qbRenderList(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "qb-row-select" in body
    assert "qbToggleRowSelect(" in body
    assert "QB_BULK_SELECTED.has(r.question_id)" in body


def test_row_checkbox_click_does_not_open_detail(qb_js):
    """The row <tr> itself opens the detail view on click
    (qbOpenDetail); the checkbox <td> must stop that click from
    bubbling, or every checkbox toggle would also open the detail
    panel."""
    idx = qb_js.index("function qbRenderList(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "event.stopPropagation()" in body


def test_select_all_checkbox_state_synced_after_render(qb_js):
    assert "function qbSyncSelectAllCheckbox(" in qb_js
    idx = qb_js.index("function qbRenderList(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "qbSyncSelectAllCheckbox()" in body


# ---------------------------------------------------------------------
# 2. Bulk toolbar + selected-count UI
# ---------------------------------------------------------------------


def test_bulk_toolbar_present(frontend_html):
    assert 'id="qb-bulk-toolbar"' in frontend_html
    assert 'id="qb-bulk-count"' in frontend_html
    assert 'id="qb-bulk-result"' in frontend_html


def test_bulk_toolbar_hidden_by_default(frontend_html):
    idx = frontend_html.index('id="qb-bulk-toolbar"')
    tag_end = frontend_html.index(">", idx)
    tag = frontend_html[idx:tag_end]
    assert "display:none" in tag


def test_selected_count_updated_by_qbupdatebulktoolbar(qb_js):
    assert "function qbUpdateBulkToolbar(" in qb_js
    idx = qb_js.index("function qbUpdateBulkToolbar(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "qb-bulk-count" in body
    assert "qb.bulk.selected_count" in body
    assert "QB_BULK_SELECTED.size" in body


def test_bulk_toolbar_role_gates_privileged_actions(qb_js):
    idx = qb_js.index("function qbUpdateBulkToolbar(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "qb-bulk-privileged" in body
    assert "CURRENT_ROLE === 'admin' || CURRENT_ROLE === 'engineer'" in body


# ---------------------------------------------------------------------
# 3. Selection helper functions
# ---------------------------------------------------------------------


def test_selection_helper_functions_present(qb_js):
    for fn in (
        "qbToggleSelectAll", "qbToggleRowSelect", "qbClearBulkSelection",
        "qbUpdateBulkToolbar", "qbSyncSelectAllCheckbox",
    ):
        assert f"function {fn}(" in qb_js, f"missing function: {fn}"


def test_clear_selection_resets_state_and_rerenders(qb_js):
    idx = qb_js.index("function qbClearBulkSelection(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "QB_BULK_SELECTED.clear()" in body
    assert "qbRenderList()" in body
    assert "qbUpdateBulkToolbar()" in body


def test_qb_bulk_selected_state_declared(frontend_html):
    assert "let QB_BULK_SELECTED = new Set();" in frontend_html


def test_load_list_prunes_stale_selection_without_clearing_present_ids(qb_js):
    """Faz 2.9.8 requirement: selection must survive a list re-render
    for any question_id still present -- qbLoadList() must only prune
    ids that disappeared from the freshly loaded list, never wipe the
    whole selection unconditionally."""
    idx = qb_js.index("async function qbLoadList(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "QB_BULK_SELECTED.delete(qid)" in body
    assert "QB_BULK_SELECTED.clear()" not in body


# ---------------------------------------------------------------------
# 4. Double-submit guard
# ---------------------------------------------------------------------


def test_bulk_action_in_flight_guard_declared(frontend_html):
    assert "let QB_BULK_ACTION_IN_FLIGHT = false;" in frontend_html


def test_run_bulk_action_enforces_double_submit_guard(qb_js):
    assert "async function qbRunBulkAction(" in qb_js
    idx = qb_js.index("async function qbRunBulkAction(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "if (QB_BULK_ACTION_IN_FLIGHT) return;" in body
    assert "QB_BULK_ACTION_IN_FLIGHT = true;" in body
    assert "QB_BULK_ACTION_IN_FLIGHT = false;" in body


def test_toolbar_buttons_disabled_while_action_in_flight(qb_js):
    idx = qb_js.index("function qbUpdateBulkToolbar(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "btn.disabled = QB_BULK_ACTION_IN_FLIGHT" in body


def test_run_bulk_action_reconciles_selection_and_reloads_list(qb_js):
    idx = qb_js.index("async function qbRunBulkAction(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "QB_BULK_SELECTED.clear()" in body
    assert "await qbLoadList()" in body


# ---------------------------------------------------------------------
# 5. Bulk lifecycle action functions + endpoint wiring
# ---------------------------------------------------------------------


def test_all_bulk_lifecycle_action_functions_present(qb_js):
    for fn in (
        "qbBulkSubmitForReview", "qbBulkValidate", "qbBulkReject",
        "qbBulkDeprecate", "qbBulkArchive",
    ):
        assert f"async function {fn}(" in qb_js, f"missing bulk lifecycle action function: {fn}"


def test_bulk_transition_endpoint_used_by_every_lifecycle_action(qb_js):
    for fn in (
        "qbBulkSubmitForReview", "qbBulkValidate", "qbBulkReject",
        "qbBulkDeprecate", "qbBulkArchive",
    ):
        start = qb_js.index(f"async function {fn}(")
        brace_start = qb_js.index("{", start)
        depth = 0
        i = brace_start
        for i in range(brace_start, len(qb_js)):
            if qb_js[i] == "{":
                depth += 1
            elif qb_js[i] == "}":
                depth -= 1
                if depth == 0:
                    break
        body = qb_js[brace_start:i + 1]
        assert "/api/question-bank/questions/bulk/transition" in body, (
            f"{fn} does not call the bulk transition endpoint"
        )
        assert "qbRunBulkAction(" in body, f"{fn} does not go through qbRunBulkAction"


def test_bulk_lifecycle_actions_send_the_matching_action_value(qb_js):
    expectations = {
        "qbBulkSubmitForReview": "'submit-for-review'",
        "qbBulkValidate": "'validate'",
        "qbBulkReject": "'reject'",
        "qbBulkDeprecate": "'deprecate'",
        "qbBulkArchive": "'archive'",
    }
    for fn, expected_action in expectations.items():
        start = qb_js.index(f"async function {fn}(")
        end = qb_js.index("\n}\n", start)
        body = qb_js[start:end]
        assert f"action: {expected_action}" in body, f"{fn} does not send action: {expected_action}"


def test_bulk_actions_never_loop_over_single_item_routes(qb_js):
    """Instruction: 'Do not call single-question endpoints in a
    frontend loop.' Every bulk action function's body must call the
    batch route, never one of the per-question routes
    (.../{question_id}/submit-for-review etc.) inside a .map()/
    forEach() loop."""
    for fn in (
        "qbBulkSubmitForReview", "qbBulkValidate", "qbBulkReject",
        "qbBulkDeprecate", "qbBulkArchive",
    ):
        start = qb_js.index(f"async function {fn}(")
        end = qb_js.index("\n}\n", start)
        body = qb_js[start:end]
        assert "/submit-for-review'" not in body
        assert "/validate'" not in body
        assert "/reject'" not in body
        assert "/deprecate'" not in body


def test_bulk_items_resolved_from_currently_loaded_list(qb_js):
    assert "function qbBulkTransitionItems(" in qb_js
    idx = qb_js.index("function qbBulkTransitionItems(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "QB_LIST" in body
    assert "QB_BULK_SELECTED.has(r.question_id)" in body
    assert "content_version" in body


def test_bulk_validate_and_reject_reuse_existing_prompt_pattern(qb_js):
    """Reuses the exact same prompt()-based input collection the
    single-item qbValidate/qbReject actions already use, rather than
    inventing a new input UI."""
    for fn in ("qbBulkValidate", "qbBulkReject"):
        start = qb_js.index(f"async function {fn}(")
        end = qb_js.index("\n}\n", start)
        body = qb_js[start:end]
        assert "prompt(" in body


def test_bulk_deprecate_and_archive_reuse_existing_confirmdialog_pattern(qb_js):
    """Reuses the exact same confirmDialog() gating convention the
    single-item qbDeprecate/qbArchive actions already use for
    high-impact actions."""
    for fn in ("qbBulkDeprecate", "qbBulkArchive"):
        start = qb_js.index(f"async function {fn}(")
        end = qb_js.index("\n}\n", start)
        body = qb_js[start:end]
        assert "confirmDialog(" in body


def test_bulk_archive_sends_items_without_requiring_content_version(qb_js):
    """archive acts on the whole question_id (Faz 2.9.4 semantics),
    not a single content_version -- the bulk archive call must not
    depend on qbBulkTransitionItems()'s content_version resolution."""
    idx = qb_js.index("async function qbBulkArchive(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "qbBulkQuestionIds()" in body
    assert "question_id: qid" in body


# ---------------------------------------------------------------------
# 6. Bulk tag add/remove functions + endpoint wiring
# ---------------------------------------------------------------------


def test_bulk_tag_functions_present(qb_js):
    for fn in ("qbBulkAddTags", "qbBulkRemoveTags"):
        assert f"async function {fn}(" in qb_js, f"missing function: {fn}"


def test_bulk_tags_endpoint_used_by_both_tag_actions(qb_js):
    for fn, key in (("qbBulkAddTags", "add"), ("qbBulkRemoveTags", "remove")):
        idx = qb_js.index(f"async function {fn}(")
        end = qb_js.index("\n}\n", idx)
        body = qb_js[idx:end]
        assert "/api/question-bank/questions/bulk/tags" in body
        assert f"{key}: tags" in body
        assert "qbRunBulkAction(" in body


def test_bulk_tag_actions_reuse_existing_tag_parsing_pattern(qb_js):
    """Must reuse the exact same comma-split/trim/filter tag-parsing
    convention already used by qbCollectFormPayload() for the
    qb_f_tags field, rather than introducing a second tag-parsing
    implementation."""
    existing_pattern = "split(',').map(s => s.trim()).filter(Boolean)"
    assert existing_pattern in qb_js  # sanity: the pre-existing pattern is present at all
    for fn in ("qbBulkAddTags", "qbBulkRemoveTags"):
        idx = qb_js.index(f"async function {fn}(")
        end = qb_js.index("\n}\n", idx)
        body = qb_js[idx:end]
        assert existing_pattern in body


# ---------------------------------------------------------------------
# 7. Bulk result rendering (partial-success handling)
# ---------------------------------------------------------------------


def test_render_bulk_result_function_present(qb_js):
    assert "function qbRenderBulkResult(" in qb_js


def test_render_bulk_result_shows_summary_and_failed_details(qb_js):
    idx = qb_js.index("function qbRenderBulkResult(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "succeeded_count" in body
    assert "failed_count" in body
    assert "qb.bulk.result_summary" in body
    assert "result.failed" in body
    assert "qb.bulk.result.col.question_id" in body
    assert "qb.bulk.result.col.error" in body


def test_run_bulk_action_calls_render_result_on_success(qb_js):
    idx = qb_js.index("async function qbRunBulkAction(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "qbRenderBulkResult(result)" in body


def test_partial_success_is_not_treated_as_an_http_error(qb_js):
    """A 200 response with failed_count > 0 is a normal success path
    (rendered via qbRenderBulkResult), never routed through the
    catch/alert error branch -- only a genuine request failure
    (network error, 401/403/422 at the whole-request level) is."""
    idx = qb_js.index("async function qbRunBulkAction(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    try_idx = body.index("try {")
    catch_idx = body.index("} catch")
    try_block = body[try_idx:catch_idx]
    assert "qbRenderBulkResult(result)" in try_block


# ---------------------------------------------------------------------
# 8. i18n: qb.bulk.* key parity + no missing referenced keys
# ---------------------------------------------------------------------


def test_qb_bulk_key_parity_between_tr_and_en(frontend_html):
    script = _extract_script(frontend_html)
    en_all = _keys_in_literal(_extract_lang_dict_literal(script, "en"))
    tr_all = _keys_in_literal(_extract_lang_dict_literal(script, "tr"))
    en_bulk = {k for k in en_all if k.startswith("qb.bulk.")}
    tr_bulk = {k for k in tr_all if k.startswith("qb.bulk.")}
    assert en_bulk, "expected at least one qb.bulk.* EN key"
    assert en_bulk == tr_bulk, (
        f"qb.bulk.* key parity broken -- only in en: {sorted(en_bulk - tr_bulk)}, "
        f"only in tr: {sorted(tr_bulk - en_bulk)}"
    )


def test_qb_bulk_values_actually_translated(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        return dict(re.findall(r"'(qb\.bulk\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values, "no qb.bulk.* key/value pairs extracted"
    assert en_values.keys() == tr_values.keys()
    identical = {k for k in en_values if en_values[k] == tr_values[k]}
    assert not identical, f"untranslated (identical TR/EN) qb.bulk.* values: {sorted(identical)}"


def test_no_qb_bulk_t_call_references_a_missing_key(frontend_html):
    """Every t('qb.bulk....') call anywhere in the QB section must
    resolve to a key that actually exists in both I18N.en and
    I18N.tr -- catches a typo'd key reference that would silently
    render as the raw key string at runtime."""
    qb_js = _qb_section_text(frontend_html)
    referenced = set(re.findall(r"t\('(qb\.bulk\.[a-zA-Z0-9_.]+)'\)", qb_js))
    assert referenced, "expected at least one t('qb.bulk....') call in the QB section"

    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))

    missing_en = referenced - en_keys
    missing_tr = referenced - tr_keys
    assert not missing_en, f"referenced but missing from EN I18N: {sorted(missing_en)}"
    assert not missing_tr, f"referenced but missing from TR I18N: {sorted(missing_tr)}"


def test_qb_bulk_required_keys_present(frontend_html):
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    required = {
        "qb.bulk.selected_count", "qb.bulk.action.add_tags", "qb.bulk.action.remove_tags",
        "qb.bulk.clear_selection", "qb.bulk.confirm_add_tags", "qb.bulk.confirm_remove_tags",
        "qb.bulk.confirm_archive_title", "qb.bulk.confirm_deprecate_title", "qb.bulk.running",
        "qb.bulk.error_prefix", "qb.bulk.result_summary", "qb.bulk.result.col.question_id",
        "qb.bulk.result.col.error",
    }
    assert required <= en_keys, f"missing required EN keys: {sorted(required - en_keys)}"
    assert required <= tr_keys, f"missing required TR keys: {sorted(required - tr_keys)}"


def test_no_new_duplicate_qb_bulk_translation_keys(frontend_html):
    script = _extract_script(frontend_html)
    for lang in ("en", "tr"):
        literal = _extract_lang_dict_literal(script, lang)
        keys = [k for k in _keys_in_literal(literal) if k.startswith("qb.bulk.")]
        assert len(keys) == len(set(keys)), f"duplicate qb.bulk.* key(s) in {lang!r}"


# ---------------------------------------------------------------------
# 9. JS syntax remains valid
# ---------------------------------------------------------------------


@pytest.mark.skipif(not NODE_AVAILABLE, reason="node is not available on PATH in this environment")
def test_frontend_js_syntax_is_valid(tmp_path):
    scripts = re.findall(r"<script>(.*?)</script>", FRONTEND_PATH.read_text(encoding="utf-8"), re.S)
    assert scripts
    js_file = tmp_path / "extracted.js"
    js_file.write_text("\n;\n".join(scripts), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 10. Existing (Faz 2.9.7) behaviour untouched by these additions
# ---------------------------------------------------------------------


def test_existing_lifecycle_action_functions_still_present(qb_js):
    """Regression guard: the Faz 2.9.7 single-item lifecycle action
    functions must be completely unaffected by this phase's additions."""
    for fn in (
        "qbSubmitForReview", "qbValidate", "qbReject", "qbDeprecate",
        "qbArchive", "qbRestore", "qbDelete",
    ):
        assert f"async function {fn}(" in qb_js, f"missing pre-existing function: {fn}"


def test_list_render_still_includes_all_pre_existing_columns(qb_js):
    idx = qb_js.index("function qbRenderList(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    for expected in (
        "r.question_id", "truncated", "qbCategoryLabel(r.category)",
        "(r.tags || [])", "qbLabel('difficulty', r.difficulty)",
        "qbStatusBadgeHtml(r.validation_status)",
    ):
        assert expected in body, f"list row is missing rendering of: {expected!r}"
