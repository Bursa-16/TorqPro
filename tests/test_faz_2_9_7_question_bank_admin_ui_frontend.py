"""Faz 2.9.7 tests: Question Bank Admin UI frontend (frontend/index.html).

Structural only (no browser, no Node/vm behavioral harness -- this
phase's implementation instruction explicitly asks not to add a large
new harness for a single admin-UI addition; JS *syntax* validity is
still checked via `node --check`, matching every other frontend test
file's minimum bar). Covers: sidebar entry and page presence, showPage
dispatcher wiring, setLanguage() reapply wiring, static TR/EN markup
text, qb.* translation key parity (both against the whole-file check
and a qb.*-scoped one), no new duplicate translation keys, HTML id
uniqueness, presence of every lifecycle-action function required by
the Faz 2.9.7 instruction (submit-for-review / validate / reject /
deprecate / archive / restore / delete), confirmation-gating for
destructive actions, and that the new include_status=true opt-in
backend parameter (added in this same phase) is actually used by the
new list/detail fetch calls.

Does not modify frontend/index.html from this file, and does not
touch the backend Faz 2.9.7 files (see
tests/test_faz_2_9_7_question_bank_admin_ui_backend.py for that).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
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


# ---------------------------------------------------------------------
# 1. Sidebar entry + page presence + navigation wiring
# ---------------------------------------------------------------------


def test_sidebar_entry_present(frontend_html):
    assert "showPage('questionbank')" in frontend_html
    assert 'id="page-questionbank"' in frontend_html


def test_sidebar_entry_uses_existing_showpage_mechanism(frontend_html):
    start = frontend_html.index("showPage('questionbank')")
    line_start = frontend_html.rfind("\n", 0, start)
    line_end = frontend_html.index("\n", start)
    line = frontend_html[line_start:line_end]
    assert 'class="sidebar-item"' in line
    assert "sidebar-icon" in line


def test_page_opens_with_page_class(frontend_html):
    idx = frontend_html.index('id="page-questionbank"')
    assert 'class="page"' in frontend_html[idx:idx + 40]


def test_showpage_dispatcher_wires_question_bank(frontend_html):
    assert "if(id==='questionbank'){qbInit();}" in frontend_html


def test_setlanguage_reapplies_question_bank_translations(frontend_html):
    idx = frontend_html.index("function setLanguage(lang)")
    end = frontend_html.index("\nfunction ", idx + 10)
    body = frontend_html[idx:end]
    assert "qbReapplyLanguage" in body


# ---------------------------------------------------------------------
# 2. Static TR/EN text present
# ---------------------------------------------------------------------


def test_tr_static_text_present(frontend_html):
    for phrase in ("Soru Bankası", "Yeni Soru", "İncelemeye Gönder", "Arşivle", "Geri Yükle"):
        assert phrase in frontend_html, f"missing TR phrase: {phrase!r}"


def test_en_static_text_present(frontend_html):
    for phrase in (
        "Question Bank", "New Question", "Submit for Review", "Archive", "Restore",
        "Create Question", "Save Changes",
    ):
        assert phrase in frontend_html, f"missing EN phrase: {phrase!r}"


def test_scope_banner_present_in_both_languages(frontend_html):
    assert "qb.banner" in frontend_html
    en_idx = frontend_html.index("'qb.banner':")
    en_banner = frontend_html[en_idx:en_idx + 400]
    assert "never runs a quiz" in en_banner
    tr_idx = frontend_html.rindex("'qb.banner':")
    assert tr_idx != en_idx, "TR qb.banner entry missing"
    tr_banner = frontend_html[tr_idx:tr_idx + 400]
    assert "Hiçbir sınav çalıştırmaz" in tr_banner


# ---------------------------------------------------------------------
# 3. Translation key parity + duplicate-key check
# ---------------------------------------------------------------------

_PRE_EXISTING_DUPLICATE_KEYS = {"hizli.enter_parameters", "yetenek.oem_tmin_tmax"}


def test_translation_key_parity_between_tr_and_en(frontend_html):
    """Whole-file parity check -- catches any drift the Faz 2.9.7 edit
    introduced anywhere in the shared I18N dictionary, not just
    within qb.*."""
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    assert en_keys == tr_keys, (
        f"key parity broken -- only in en: {sorted(en_keys - tr_keys)}, "
        f"only in tr: {sorted(tr_keys - en_keys)}"
    )


def test_no_new_duplicate_translation_keys(frontend_html):
    script = _extract_script(frontend_html)
    for lang in ("en", "tr"):
        literal = _extract_lang_dict_literal(script, lang)
        keys = _keys_in_literal(literal)
        counts = Counter(keys)
        dups = {k for k, c in counts.items() if c > 1}
        new_dups = dups - _PRE_EXISTING_DUPLICATE_KEYS
        assert not new_dups, f"new duplicate key(s) in {lang!r}: {sorted(new_dups)}"


def test_qb_key_count_matches_between_languages(frontend_html):
    script = _extract_script(frontend_html)
    en_all = _keys_in_literal(_extract_lang_dict_literal(script, "en"))
    tr_all = _keys_in_literal(_extract_lang_dict_literal(script, "tr"))
    en_keys = [k for k in en_all if k.startswith("qb.") or k == "sidebar.questionbank"]
    tr_keys = [k for k in tr_all if k.startswith("qb.") or k == "sidebar.questionbank"]
    assert len(en_keys) == len(tr_keys)
    assert len(set(en_keys)) == len(en_keys)
    assert len(set(tr_keys)) == len(tr_keys)
    assert len(en_keys) > 100, "expected the full Faz 2.9.7 qb.* key set"


def test_qb_required_keys_present_and_paired(frontend_html):
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    required_min = {
        "sidebar.questionbank", "qb.page_title", "qb.page_subtitle", "qb.banner",
        "qb.list_title", "qb.new_question_button", "qb.search_placeholder",
        "qb.filter_category_all", "qb.filter_difficulty_all", "qb.filter_tag_placeholder",
        "qb.filter_status_all", "qb.filter_include_archived", "qb.col.id", "qb.col.question",
        "qb.col.category", "qb.col.tags", "qb.col.difficulty", "qb.col.status",
        "qb.detail_title", "qb.edit_button", "qb.close_button", "qb.lifecycle_title",
        "qb.status_history_title", "qb.audit_title", "qb.create_form_title", "qb.edit_form_title",
        "qb.field.question_id", "qb.field.content_version", "qb.field.category",
        "qb.field.difficulty", "qb.field.question_type", "qb.field.question_tr",
        "qb.field.question_en", "qb.field.correct_answer", "qb.field.technical_explanation_tr",
        "qb.field.technical_explanation_en", "qb.field.traceability_level",
        "qb.field.engineering_risk_level", "qb.field.learning_objective",
        "qb.action.submit_for_review", "qb.action.validate", "qb.action.reject",
        "qb.action.deprecate", "qb.action.archive", "qb.action.restore", "qb.action.delete",
        "qb.validation_error_prefix", "qb.create_success", "qb.save_success",
    }
    missing_en = required_min - en_keys
    missing_tr = required_min - tr_keys
    assert not missing_en, f"missing required EN keys: {sorted(missing_en)}"
    assert not missing_tr, f"missing required TR keys: {sorted(missing_tr)}"


def test_tr_and_en_text_actually_differ_for_every_qb_key(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        return dict(re.findall(r"'(qb\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values, "no qb.* key/value pairs extracted -- regex or structure changed"
    assert en_values.keys() == tr_values.keys()
    identical = {k for k in en_values if en_values[k] == tr_values[k] and en_values[k] != ""}
    assert not identical, f"untranslated (identical TR/EN) qb.* values: {sorted(identical)}"


# ---------------------------------------------------------------------
# 4. HTML element ID uniqueness
# ---------------------------------------------------------------------


def test_all_html_ids_are_unique(frontend_html):
    ids = re.findall(r'id="([a-zA-Z0-9_-]+)"', frontend_html)
    counts = Counter(ids)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert not dups, f"duplicate HTML ids found: {dups}"


def test_question_bank_field_ids_are_unique(frontend_html):
    qb_ids = re.findall(r'id="(qb[-_][a-zA-Z0-9_-]+)"', frontend_html)
    assert qb_ids
    assert len(qb_ids) == len(set(qb_ids))


# ---------------------------------------------------------------------
# 5. JS syntax
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
# 6. No new framework/bundler reference; single-file frontend intact
# ---------------------------------------------------------------------


def test_no_new_framework_or_bundler_reference(frontend_html):
    lowered = frontend_html.lower()
    forbidden_refs = (
        "webpack", "vite.config", "cdnjs.cloudflare.com/ajax/libs/react",
        "cdnjs.cloudflare.com/ajax/libs/vue", "angular.min.js", "playwright", "puppeteer",
    )
    for forbidden in forbidden_refs:
        assert forbidden not in lowered, f"unexpected framework/bundler reference: {forbidden!r}"


def test_frontend_still_a_single_file():
    frontend_files = list((REPO_ROOT / "frontend").iterdir())
    names = {f.name for f in frontend_files}
    assert names == {"index.html", "manifest.webmanifest", "service-worker.js"}


# ---------------------------------------------------------------------
# 7. Required list/search/detail/create/edit/lifecycle functions exist
# ---------------------------------------------------------------------


def _qb_section_text(frontend_html: str) -> str:
    start = frontend_html.index("// ========== QUESTION BANK ADMIN UI (Faz 2.9.7) ==========")
    end = frontend_html.index("// ========== BAŞLAT ==========")
    return frontend_html[start:end]


@pytest.fixture(scope="module")
def qb_js(frontend_html):
    return _qb_section_text(frontend_html)


def test_list_and_filter_functions_present(qb_js):
    for fn in ("qbInit", "qbLoadList", "qbRenderList", "qbBuildListQuery", "qbDebouncedLoadList"):
        assert f"function {fn}(" in qb_js, f"missing function: {fn}"


def test_detail_functions_present(qb_js):
    for fn in (
        "qbOpenDetail", "qbRenderDetail", "qbCloseDetail", "qbRenderStatusHistory", "qbRenderAudit",
    ):
        assert f"function {fn}(" in qb_js, f"missing function: {fn}"


def test_create_edit_functions_present(qb_js):
    for fn in (
        "qbShowCreateForm", "qbShowEditForm", "qbSubmitForm", "qbCollectFormPayload",
        "qbParseCorrectAnswer", "qbValidateRequiredFields", "qbCancelForm",
    ):
        assert f"function {fn}(" in qb_js, f"missing function: {fn}"


def test_all_required_lifecycle_action_functions_present(qb_js):
    for fn in (
        "qbSubmitForReview", "qbValidate", "qbReject", "qbDeprecate", "qbArchive", "qbRestore",
        "qbDelete",
    ):
        assert f"async function {fn}(" in qb_js, f"missing lifecycle action function: {fn}"


def test_lifecycle_actions_call_the_expected_routes(qb_js):
    assert "/submit-for-review'" in qb_js
    assert "/validate'" in qb_js
    assert "/reject'" in qb_js
    assert "/deprecate'" in qb_js
    assert "/archive'" in qb_js
    assert "/restore'" in qb_js
    assert "{ method: 'DELETE' }" in qb_js


def test_destructive_actions_are_confirmation_gated(qb_js):
    """Faz 2.9.7 instruction: 'gerekli confirmation/prompt akışları'.
    Archive/restore/delete/deprecate must all go through
    confirmDialog() before issuing their write call; reject/validate
    must go through prompt() to collect the required reason/reviewer
    fields the backend demands."""

    def _function_body(name: str) -> str:
        marker = f"async function {name}("
        start = qb_js.index(marker)
        # crude brace-matched body extraction, good enough for this
        # file's flat (non-nested-function) action bodies
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
        return qb_js[brace_start:i + 1]

    assert "confirmDialog(" in _function_body("qbArchive")
    assert "confirmDialog(" in _function_body("qbRestore")
    assert "confirmDialog(" in _function_body("qbDelete")
    assert "confirmDialog(" in _function_body("qbDeprecate")
    assert "prompt(" in _function_body("qbValidate")
    assert "prompt(" in _function_body("qbReject")


def test_role_gating_uses_existing_current_role_convention(qb_js):
    """Lifecycle actions requiring admin/engineer authorization on the
    backend (archive/restore/delete/validate/reject/deprecate --
    backend.question_bank.service.default_role_authorization) must be
    hidden client-side for any other role, reusing the existing
    CURRENT_ROLE global rather than inventing a second role system."""
    assert "CURRENT_ROLE === 'admin' || CURRENT_ROLE === 'engineer'" in qb_js


# ---------------------------------------------------------------------
# 8. include_status=true opt-in usage (Faz 2.9.7 backend addition)
# ---------------------------------------------------------------------


def test_list_query_requests_include_status(qb_js):
    idx = qb_js.index("function qbBuildListQuery(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "include_status" in body
    assert "'true'" in body


def test_detail_fetch_requests_include_status(qb_js):
    idx = qb_js.index("async function qbOpenDetail(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "include_status=true" in body


def test_list_query_defaults_publishable_only_false_for_review_workspace(qb_js):
    """Faz 2.9.7 admin UI is exactly the 'review workspace' case the
    backend route's own docstring calls out as needing
    publishable_only=false -- draft/technical_review/rejected content
    must stay visible in this workspace."""
    idx = qb_js.index("function qbBuildListQuery(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    assert "publishable_only" in body and "'false'" in body


# ---------------------------------------------------------------------
# 9. Required list columns (question_id, question, category, tags,
#    difficulty, lifecycle status) are actually rendered
# ---------------------------------------------------------------------


def test_list_render_includes_all_required_columns(qb_js):
    idx = qb_js.index("function qbRenderList(")
    end = qb_js.index("\n}\n", idx)
    body = qb_js[idx:end]
    for expected in (
        "r.question_id", "truncated", "qbCategoryLabel(r.category)",
        "(r.tags || [])", "qbLabel('difficulty', r.difficulty)",
        "qbStatusBadgeHtml(r.validation_status)",
    ):
        assert expected in body, f"list row is missing rendering of: {expected!r}"


def test_no_client_side_reimplementation_of_backend_search_filtering(qb_js):
    """Faz 2.9.7 instruction #2: 'use the existing Faz 2.9.5 backend
    functionality; do not duplicate backend search logic in the
    frontend'. The list must be re-fetched from the server on every
    filter change (qbLoadList as the change handler), never filtered
    client-side out of an already-fetched QB_LIST with an Array
    .filter() call."""
    assert "QB_LIST.filter(" not in qb_js
    assert "onchange=\"qbLoadList()\"" in Path(FRONTEND_PATH).read_text(encoding="utf-8")
