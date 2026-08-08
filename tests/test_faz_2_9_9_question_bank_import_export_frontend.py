"""Faz 2.9.9 tests: Question Bank JSON import/export frontend
(frontend/index.html).

Structural only (no browser, no Node/vm behavioral harness -- same
minimum bar as tests/test_faz_2_9_{7,8}_question_bank_*_frontend.py:
JS *syntax* validity via `node --check`, everything else via plain
text/regex assertions against the file). Covers: Export/Import button
presence in the Questions card header, the hidden JSON file input,
export/import endpoint wiring, empty-file/invalid-JSON/invalid-shape
client-side guards, the created/skipped/rejected result rendering,
error-message rendering, qb.ie.* TR/EN key parity, and that every
referenced qb.ie.* key actually exists in both languages.

Does not modify frontend/index.html from this file, and does not
touch the backend Faz 2.9.9 files (see
tests/test_faz_2_9_9_question_bank_import_export.py for that).
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


def _function_body(js: str, signature: str) -> str:
    start = js.index(signature)
    brace_start = js.index("{", start)
    depth = 0
    i = brace_start
    for i in range(brace_start, len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                break
    return js[brace_start:i + 1]


@pytest.fixture(scope="module")
def qb_js(frontend_html):
    return _qb_section_text(frontend_html)


# ---------------------------------------------------------------------
# 1. Export/Import buttons + file input presence
# ---------------------------------------------------------------------


def test_export_and_import_buttons_present(frontend_html):
    assert "qbExportQuestions()" in frontend_html
    assert "qbTriggerImportFilePicker()" in frontend_html
    assert 'data-i18n="qb.ie.export_button"' in frontend_html
    assert 'data-i18n="qb.ie.import_button"' in frontend_html


def test_import_file_input_present_and_hidden(frontend_html):
    id_idx = frontend_html.index('id="qb-import-file-input"')
    tag_start = frontend_html.rindex("<input", 0, id_idx)
    tag_end = frontend_html.index(">", id_idx)
    tag = frontend_html[tag_start:tag_end]
    assert 'type="file"' in tag
    assert "display:none" in tag
    assert 'accept="application/json,.json"' in tag
    assert "qbImportFileSelected(event)" in tag


def test_export_import_buttons_in_questions_card_header(frontend_html):
    """The Export/Import controls must live in the same card header as
    the existing '+ New Question' button, not some other card."""
    header_idx = frontend_html.index('data-i18n="qb.list_title"')
    new_question_idx = frontend_html.index("qbShowCreateForm()", header_idx)
    between = frontend_html[header_idx:new_question_idx]
    assert "qbExportQuestions()" in between
    assert "qbTriggerImportFilePicker()" in between


def test_import_export_result_container_present(frontend_html):
    assert 'id="qb-ie-result"' in frontend_html


# ---------------------------------------------------------------------
# 2. Export wiring
# ---------------------------------------------------------------------


def test_export_function_present(qb_js):
    assert "async function qbExportQuestions(" in qb_js


def test_export_calls_export_endpoint(qb_js):
    body = _function_body(qb_js, "async function qbExportQuestions(")
    assert "/api/question-bank/export" in body


def test_export_reuses_existing_list_filter_query_builder(qb_js):
    """Faz 2.9.9 requirement: preserve existing filter/search/tag/
    lifecycle selections on export -- must reuse qbBuildListQuery(),
    not re-implement filter collection."""
    body = _function_body(qb_js, "async function qbExportQuestions(")
    assert "qbBuildListQuery()" in body


def test_export_triggers_a_client_side_file_download(qb_js):
    body = _function_body(qb_js, "async function qbExportQuestions(")
    assert "new Blob(" in body
    assert "URL.createObjectURL(blob)" in body
    assert ".download =" in body


def test_export_renders_success_and_error_messages(qb_js):
    body = _function_body(qb_js, "async function qbExportQuestions(")
    assert "qb.ie.export_success" in body
    assert "qb.ie.error_prefix" in body
    assert "qb-ie-result" in body


# ---------------------------------------------------------------------
# 3. Import wiring: file read, JSON parse, shape validation, endpoint
# ---------------------------------------------------------------------


def test_import_file_selected_handler_present(qb_js):
    assert "async function qbImportFileSelected(" in qb_js


def test_import_handles_empty_file(qb_js):
    body = _function_body(qb_js, "async function qbImportFileSelected(")
    assert "qb.ie.empty_file" in body


def test_import_handles_invalid_json(qb_js):
    body = _function_body(qb_js, "async function qbImportFileSelected(")
    assert "JSON.parse(text)" in body
    assert "qb.ie.invalid_json" in body


def test_import_handles_invalid_shape(qb_js):
    body = _function_body(qb_js, "async function qbImportFileSelected(")
    assert "qb.ie.invalid_shape" in body
    # Accepts both a bare array and the {questions:[...]} export shape.
    assert "Array.isArray(parsed)" in body
    assert "parsed.questions" in body


def test_import_calls_import_endpoint(qb_js):
    body = _function_body(qb_js, "async function qbImportFileSelected(")
    assert "/api/question-bank/import" in body
    assert "method: 'POST'" in body


def test_import_refreshes_list_after_completion(qb_js):
    body = _function_body(qb_js, "async function qbImportFileSelected(")
    assert "await qbLoadList()" in body


def test_import_file_input_resets_value_to_allow_reselection(qb_js):
    body = _function_body(qb_js, "async function qbImportFileSelected(")
    assert "event.target.value = ''" in body


# ---------------------------------------------------------------------
# 4. Import result rendering: created / skipped / rejected
# ---------------------------------------------------------------------


def test_render_import_result_function_present(qb_js):
    assert "function qbRenderImportResult(" in qb_js


def test_import_result_rendering_shows_created_skipped_rejected_counts(qb_js):
    body = _function_body(qb_js, "function qbRenderImportResult(")
    assert "result.created_count" in body
    assert "result.skipped_count" in body
    assert "result.rejected_count" in body
    assert "qb.ie.result_summary" in body


def test_import_result_rendering_shows_rejected_reasons_table(qb_js):
    body = _function_body(qb_js, "function qbRenderImportResult(")
    assert "result.rejected" in body
    assert "r.reasons" in body


def test_import_file_selected_calls_render_import_result(qb_js):
    body = _function_body(qb_js, "async function qbImportFileSelected(")
    assert "qbRenderImportResult(result)" in body


# ---------------------------------------------------------------------
# 5. i18n: qb.ie.* key parity + no missing referenced keys
# ---------------------------------------------------------------------


def test_qb_ie_key_parity_between_tr_and_en(frontend_html):
    script = _extract_script(frontend_html)
    en_all = _keys_in_literal(_extract_lang_dict_literal(script, "en"))
    tr_all = _keys_in_literal(_extract_lang_dict_literal(script, "tr"))
    en_ie = {k for k in en_all if k.startswith("qb.ie.")}
    tr_ie = {k for k in tr_all if k.startswith("qb.ie.")}
    assert en_ie, "expected at least one qb.ie.* EN key"
    assert en_ie == tr_ie, (
        f"qb.ie.* key parity broken -- only in en: {sorted(en_ie - tr_ie)}, "
        f"only in tr: {sorted(tr_ie - en_ie)}"
    )


def test_qb_ie_values_actually_translated(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        return dict(re.findall(r"'(qb\.ie\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values, "no qb.ie.* key/value pairs extracted"
    assert en_values.keys() == tr_values.keys()
    identical = {k for k in en_values if en_values[k] == tr_values[k]}
    assert not identical, f"untranslated (identical TR/EN) qb.ie.* values: {sorted(identical)}"


def test_no_qb_ie_t_call_references_a_missing_key(frontend_html):
    """Every t('qb.ie....') call anywhere in the QB section must
    resolve to a key that actually exists in both I18N.en and
    I18N.tr."""
    qb_js = _qb_section_text(frontend_html)
    referenced = set(re.findall(r"t\('(qb\.ie\.[a-zA-Z0-9_.]+)'\)", qb_js))
    assert referenced, "expected at least one t('qb.ie....') call in the QB section"

    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))

    missing_en = referenced - en_keys
    missing_tr = referenced - tr_keys
    assert not missing_en, f"referenced but missing from EN I18N: {sorted(missing_en)}"
    assert not missing_tr, f"referenced but missing from TR I18N: {sorted(missing_tr)}"


def test_qb_ie_required_keys_present(frontend_html):
    required = (
        "qb.ie.export_button",
        "qb.ie.import_button",
        "qb.ie.exporting",
        "qb.ie.importing",
        "qb.ie.export_success",
        "qb.ie.empty_file",
        "qb.ie.invalid_json",
        "qb.ie.invalid_shape",
        "qb.ie.error_prefix",
        "qb.ie.result_summary",
        "qb.ie.result.col.question_id",
        "qb.ie.result.col.reason",
    )
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    for key in required:
        assert key in en_keys, f"missing required EN key: {key}"
        assert key in tr_keys, f"missing required TR key: {key}"


# ---------------------------------------------------------------------
# 6. JS syntax validity (whole <script> block)
# ---------------------------------------------------------------------


@pytest.mark.skipif(not NODE_AVAILABLE, reason="node is not available in this environment")
def test_script_block_is_syntactically_valid_js(frontend_html, tmp_path):
    script = _extract_script(frontend_html)
    js_path = tmp_path / "extracted.js"
    js_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["node", "--check", str(js_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
