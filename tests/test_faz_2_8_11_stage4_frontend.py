"""Faz 2.8.11 Stage 4: Engineering Governance Workspace frontend.

Mirrors the established two-layer frontend test convention (see
tests/test_faz_2_8_9_stage5_frontend.py's module docstring for the
full rationale):

1. Behavioral: tests/js/run_governance_workspace_tests.js (a
   dependency-free Node/vm harness) run as a subprocess against the
   *actual* declarations extracted live from frontend/index.html.
2. Structural (this module, no browser required): sidebar entry
   presence, page id presence (exactly once), sidebar-target/page-id
   match, API endpoint calls through the established `apiRequest`
   utility, render-function presence, i18n key parity/duplication,
   no-guessing/no-fabrication text checks, JS syntax via
   `node --check`, and a static proxy check for 1366x768 overflow
   risk.

Does not modify frontend/index.html from this file, and does not
touch any Stage 1-3 governance backend file.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_governance_workspace_tests.js"
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
        "Governance workspace harness reported failures:\n" + result.stdout + result.stderr
    )


def test_harness_assertion_count_exceeds_structural_baseline():
    """The purely structural checks in this file (sidebar/page/i18n
    presence etc.) do not exercise any actual rendering or async
    behavior. The Node harness must contribute materially more
    assertions than that -- guards against an accidentally-inert
    harness (the Faz 2.8.8 defect class) silently reporting a
    trivially small, always-passing count."""
    result = _run_harness()
    m = re.search(r"(\d+) assertions, (\d+) passed, (\d+) failed", result.stdout)
    assert m, "harness output missing expected summary line:\n" + result.stdout
    total, passed, failed = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert failed == 0
    assert passed == total
    assert total > 20, f"only {total} assertions ran -- async scenarios may not be awaited"


def test_harness_file_is_dependency_free():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "require('jsdom')" not in text
    assert "require('puppeteer')" not in text
    assert "require('playwright')" not in text
    assert "require(" not in text.replace("require('path')", "").replace(
        "require('vm')", ""
    ).replace("require('./harness_common')", "").replace("require('fs')", "")


def test_harness_uses_awaited_main_not_bare_process_exit():
    """Structural guard against the Faz 2.8.8 defect class: the
    harness must funnel every scenario through an awaited `main()`,
    never call `process.exit()` unconditionally before all promises
    have settled."""
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "async function main()" in text
    assert re.search(r"await\s+testFn\(\)", text)
    assert "main().catch(" in text
    assert "process.exit(" not in text
    assert "process.exitCode" in text


def test_harness_scenarios_are_declared_async():
    """Every scenario in ALL_TESTS must itself be an `async function`
    so `await testFn()` inside main() is meaningful for every one of
    them, not just the ones that happen to contain a real await."""
    text = HARNESS_PATH.read_text(encoding="utf-8")
    idx = text.index("const ALL_TESTS = [")
    end = text.index("];", idx)
    names = re.findall(r"\n\s*(test\w+),?", text[idx:end])
    assert len(names) >= 15
    for name in names:
        assert re.search(r"async function " + re.escape(name) + r"\(", text), (
            f"{name} is listed in ALL_TESTS but is not declared async"
        )


# ---------------------------------------------------------------------
# 2. Structural: sidebar + page presence
# ---------------------------------------------------------------------


def test_sidebar_entry_present(frontend_html):
    assert "showPage('governance')" in frontend_html
    assert 'id="page-governance"' in frontend_html


def test_page_id_appears_exactly_once(frontend_html):
    assert frontend_html.count('id="page-governance"') == 1


def test_sidebar_target_matches_page_id(frontend_html):
    assert "showPage('governance')" in frontend_html
    assert 'id="page-governance"' in frontend_html


def test_sidebar_entry_uses_existing_showpage_mechanism(frontend_html):
    start = frontend_html.index("showPage('governance')")
    line_start = frontend_html.rfind("\n", 0, start)
    line_end = frontend_html.index("\n", start)
    line = frontend_html[line_start:line_end]
    assert 'class="sidebar-item"' in line
    assert "sidebar-icon" in line


def test_showpage_dispatcher_wires_governance(frontend_html):
    assert "if(id==='governance'){govInit();}" in frontend_html


def test_history_and_status_called_through_apirequest_utility(frontend_html):
    idx = frontend_html.index("async function govLoad")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "apiRequest(" in body
    assert "fetch(" not in body


def test_submit_command_called_through_apirequest_utility(frontend_html):
    idx = frontend_html.index("async function govSubmitCommand")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "apiRequest(" in body
    assert "fetch(" not in body


# ---------------------------------------------------------------------
# 3. Structural: required functions and behaviors present
# ---------------------------------------------------------------------


def test_required_functions_present(frontend_html):
    for fn in (
        "function govInit", "async function govLoad", "async function govSubmitCommand",
        "function govReapplyLanguage", "function govRenderStatus", "function govRenderHistory",
        "function govRenderError", "function govRenderLoading", "function govRenderEmpty",
        "function govIsWellFormedHistory", "function govIsWellFormedStatus",
        "function govOnActionChange", "function govClassifyError",
    ):
        assert fn in frontend_html, f"missing: {fn}"


def test_all_nine_actions_represented(frontend_html):
    idx = frontend_html.index("const GOV_ACTIONS")
    end = frontend_html.index("];", idx)
    body = frontend_html[idx:end]
    for action in (
        "review_submit", "review_approve", "review_reject",
        "publication_activate", "publication_supersede", "publication_archive",
        "resolution_resolve", "resolution_reject", "resolution_waive",
    ):
        assert f"'{action}'" in body, f"missing action: {action}"


def test_aggregate_id_and_type_controls_present(frontend_html):
    assert 'id="gov_aggregate_id"' in frontend_html
    assert 'id="gov_aggregate_type"' in frontend_html


def test_decision_idempotency_occurred_at_controls_present(frontend_html):
    assert 'id="gov_decision_id"' in frontend_html
    assert 'id="gov_idempotency_key"' in frontend_html
    assert 'id="gov_occurred_at"' in frontend_html
    assert 'id="gov_metadata"' in frontend_html


def test_supersede_field_is_conditional(frontend_html):
    """The superseded_by_id input must start hidden (display:none)
    and only be shown by govOnActionChange() for the supersede
    action -- never a permanently-visible field."""
    idx = frontend_html.index('id="gov-superseded-by-group"')
    line_start = frontend_html.rfind("<div", 0, idx)
    line_end = frontend_html.index(">", idx)
    tag = frontend_html[line_start:line_end]
    assert "display:none" in tag
    idx2 = frontend_html.index("function govOnActionChange")
    end2 = frontend_html.index("\n}", idx2)
    body = frontend_html[idx2:end2]
    assert "gov-superseded-by-group" in body
    assert "supersede" in body


def test_no_actor_or_previous_status_input_control(frontend_html):
    section_start = frontend_html.index('<div id="page-governance" class="page">')
    section_end = frontend_html.index('<div id="page-materialintelligence" class="page">')
    section = frontend_html[section_start:section_end]
    assert "gov_actor" not in section
    assert "gov_previous_status" not in section


def test_submit_command_body_excludes_actor_and_previous_status(frontend_html):
    idx = frontend_html.index("async function govSubmitCommand")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "body.actor" not in body
    assert "actor:" not in body
    assert "body.previous_status" not in body
    assert "previous_status:" not in body


def test_three_lifecycle_groups_rendered_separately(frontend_html):
    idx = frontend_html.index("function govRenderStatus")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "'review'" in body or '"review"' in body
    assert "'publication'" in body or '"publication"' in body
    assert "'resolution'" in body or '"resolution"' in body


def test_append_only_explanation_present_via_i18n(frontend_html):
    assert 'data-i18n="gov.notice_append_only"' in frontend_html


def test_effective_status_explanation_present_via_i18n(frontend_html):
    assert 'data-i18n="gov.notice_effective_status"' in frontend_html


def test_lifecycle_independence_explanation_present_via_i18n(frontend_html):
    assert 'data-i18n="gov.notice_lifecycle_independent"' in frontend_html


def test_stage4_generic_limitation_explained_via_i18n(frontend_html):
    assert 'data-i18n="gov.notice_stage4_generic"' in frontend_html


def test_malformed_response_protection_present(frontend_html):
    assert "function govIsWellFormedHistory" in frontend_html
    assert "function govIsWellFormedStatus" in frontend_html
    idx = frontend_html.index("async function govLoad")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "govIsWellFormedHistory" in body
    assert "govIsWellFormedStatus" in body
    assert "gov.malformed_response" in frontend_html


def test_no_lifecycle_state_machine_implemented_in_javascript(frontend_html):
    """The frontend must never encode a transition table -- no
    JS structure mapping a status to its allowed next statuses. This
    is a a proxy check: the known backend status-vocabulary literal
    pairs (e.g. 'draft' immediately followed by an array of allowed
    next statuses) must not appear in the governance JS section."""
    section_start = frontend_html.index("const GOV_ACTIONS")
    section_end = frontend_html.index("// ========== BAŞLAT ==========")
    section = frontend_html[section_start:section_end]
    forbidden_patterns = (
        "draft: ['under_review']", 'draft: ["under_review"]',
        "under_review: ['approved'", 'under_review: ["approved"',
        "ALLOWED_TRANSITIONS", "TRANSITION_TABLE", "STATE_MACHINE",
    )
    for pattern in forbidden_patterns:
        assert pattern not in section, f"apparent transition table found: {pattern!r}"


def test_gov_reapply_language_present_and_wired(frontend_html):
    assert "function govReapplyLanguage" in frontend_html
    idx = frontend_html.index("function setLanguage(")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "govReapplyLanguage()" in body


# ---------------------------------------------------------------------
# 4. Translation key parity + duplicate-key check
# ---------------------------------------------------------------------


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


def _extract_script(html: str) -> str:
    m = re.search(r"<script>([\s\S]*?)</script>", html)
    assert m, "no <script> block found"
    return m.group(1)


def _keys_in_literal(literal: str) -> list:
    return re.findall(r"'([a-zA-Z0-9_.]+)':", literal)


def test_translation_key_parity_between_tr_and_en(frontend_html):
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    assert en_keys == tr_keys, (
        f"key parity broken -- only in en: {sorted(en_keys - tr_keys)}, "
        f"only in tr: {sorted(tr_keys - en_keys)}"
    )


def test_gov_key_parity_exact_count(frontend_html):
    script = _extract_script(frontend_html)
    en_all = _keys_in_literal(_extract_lang_dict_literal(script, "en"))
    tr_all = _keys_in_literal(_extract_lang_dict_literal(script, "tr"))
    en_gov = [k for k in en_all if k.startswith("gov.") or k == "sidebar.governance"]
    tr_gov = [k for k in tr_all if k.startswith("gov.") or k == "sidebar.governance"]
    assert len(en_gov) == len(tr_gov) == 80, (
        f"expected 80/80 gov.*/sidebar.governance key parity, got "
        f"{len(en_gov)} EN / {len(tr_gov)} TR"
    )
    assert len(set(en_gov)) == len(en_gov)
    assert len(set(tr_gov)) == len(tr_gov)
    assert set(en_gov) == set(tr_gov)


def test_no_new_duplicate_translation_keys(frontend_html):
    script = _extract_script(frontend_html)
    pre_existing = {"hizli.enter_parameters", "yetenek.oem_tmin_tmax"}
    for lang in ("en", "tr"):
        literal = _extract_lang_dict_literal(script, lang)
        keys = _keys_in_literal(literal)
        counts = Counter(keys)
        dups = {k for k, c in counts.items() if c > 1}
        new_dups = dups - pre_existing
        assert not new_dups, f"new duplicate key(s) in {lang!r}: {sorted(new_dups)}"


def test_tr_and_en_text_actually_differ_for_every_gov_key(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        return dict(re.findall(r"'(gov\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values, "no gov.* key/value pairs extracted -- regex or structure changed"
    assert en_values.keys() == tr_values.keys()
    # 'metadata_placeholder' is legitimately identical in both
    # languages (a literal '{}' JSON placeholder, not prose).
    legitimate_identical_allowlist = {"gov.metadata_placeholder"}
    identical = {
        k for k in en_values
        if en_values[k] == tr_values[k]
        and en_values[k] != ""
        and k not in legitimate_identical_allowlist
    }
    assert not identical, f"untranslated (identical TR/EN) values: {sorted(identical)}"


def test_turkish_values_use_turkish_characters_where_expected(frontend_html):
    script = _extract_script(frontend_html)
    tr_literal = _extract_lang_dict_literal(script, "tr")
    values = dict(re.findall(r"'(gov\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", tr_literal))
    turkish_chars = set("çğıöşüÇĞİÖŞÜ")
    expected_to_contain_turkish_chars = [
        "gov.page_title", "gov.notice_append_only", "gov.notice_lifecycle_independent",
        "gov.aggregate_id_label", "gov.load_button", "gov.submit_button",
    ]
    for key in expected_to_contain_turkish_chars:
        assert key in values, f"missing TR value for {key}"
        assert any(c in turkish_chars for c in values[key]), (
            f"{key!r} TR value {values[key]!r} has no Turkish-specific character"
        )


# ---------------------------------------------------------------------
# 5. HTML element ID uniqueness
# ---------------------------------------------------------------------


def test_all_html_ids_are_unique(frontend_html):
    ids = re.findall(r'id="([a-zA-Z0-9_-]+)"', frontend_html)
    counts = Counter(ids)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert not dups, f"duplicate HTML ids found: {dups}"


def test_gov_field_ids_are_unique(frontend_html):
    gov_ids = re.findall(r'id="(gov[_-][a-zA-Z0-9_-]+)"', frontend_html)
    assert gov_ids
    assert len(gov_ids) == len(set(gov_ids))


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


def test_harness_js_syntax_is_valid():
    result = subprocess.run(
        ["node", "--check", str(HARNESS_PATH)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------
# 7. No new framework/bundler reference; single-file frontend intact
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
# 8. 1366x768 overflow-risk proxy
# ---------------------------------------------------------------------


def _gov_section_html(frontend_html: str) -> str:
    start = frontend_html.index('<div id="page-governance" class="page">')
    end = frontend_html.index('<div id="page-materialintelligence" class="page">')
    return frontend_html[start:end]


def test_no_fixed_large_pixel_widths_introduced(frontend_html):
    section = _gov_section_html(frontend_html)
    widths = re.findall(r"width\s*:\s*(\d+)px", section)
    oversized = [w for w in widths if int(w) > 1200]
    assert not oversized, f"fixed pixel width(s) that could overflow 1366px: {oversized}"


def test_reuses_existing_responsive_layout_classes(frontend_html):
    section = _gov_section_html(frontend_html)
    assert 'class="card"' in section
    assert 'class="ai-form-grid"' in section
    assert 'class="form-row3"' in section


def test_history_table_uses_existing_responsive_table_class(frontend_html):
    idx = frontend_html.index("function govRenderHistory")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert 'class="table"' in body


# ---------------------------------------------------------------------
# 9. No unsupported-capability / no-invention claims in new UI text
# ---------------------------------------------------------------------


def test_no_unsupported_claims_in_gov_text(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    en_values = dict(re.findall(r"'(gov\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", en_literal))
    forbidden_phrases = (
        "production-ready", "certified", "ai-recommended", "guaranteed", "verified automatically",
    )
    joined = " ".join(en_values.values()).lower()
    for phrase in forbidden_phrases:
        assert phrase not in joined, f"unsupported claim found in gov.* text: {phrase!r}"
