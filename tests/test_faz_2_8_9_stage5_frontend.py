"""Faz 2.8.9 tests (Stage 5B): Washer Resolution Report frontend.

Two layers, mirroring the Faz 2.8.8 frontend test conventions
(tests/test_faz_2_8_8_frontend.py):

1. Behavioral: tests/js/run_washer_resolution_report_tests.js (a
   dependency-free Node/vm harness) is run as a subprocess against
   the *actual* declarations extracted live from frontend/index.html.
2. Structural (this module, no browser required): sidebar entry
   presence, page id presence (exactly once), sidebar-target/page-id
   match, API endpoint string usage through the established
   `apiRequest` utility, render-function presence, i18n key parity/
   duplication, no-guessing/no-fabrication text checks, JS syntax via
   `node --check`, and a static proxy check for 1366x768 overflow
   risk (no fixed large-pixel-width styling introduced by this page --
   the same reasoning basis used when Faz 2.6.6 was verified with
   Playwright, applied here without a browser dependency).

Does not modify frontend/index.html from this file, and does not
touch backend Faz 2.8.9 files.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_washer_resolution_report_tests.js"
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
        "Washer Resolution Report harness reported failures:\n"
        + result.stdout
        + result.stderr
    )


def test_harness_assertion_count_exceeds_original_sync_only_count():
    """The harness originally (before its async/await fix) silently
    reported only 8 assertions -- every async scenario's checks never
    ran. This is the regression guard: the real count must be
    materially higher, proving the async scenarios now execute."""
    result = _run_harness()
    m = re.search(r"(\d+) assertions, (\d+) passed, (\d+) failed", result.stdout)
    assert m, "harness output missing expected summary line:\n" + result.stdout
    total, passed, failed = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert failed == 0
    assert passed == total
    assert total > 8, (
        f"only {total} assertions ran -- async scenarios may not be awaited again"
    )


def test_harness_file_is_dependency_free():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "require('jsdom')" not in text
    assert "require('puppeteer')" not in text
    assert "require('playwright')" not in text
    assert "require(" not in text.replace("require('fs')", "").replace(
        "require('path')", ""
    ).replace("require('vm')", "")


def test_harness_uses_awaited_main_not_bare_process_exit():
    """Structural guard against regressing back to the original
    defect: the harness must funnel every scenario through an
    awaited `main()`, never call `process.exit()` unconditionally
    before all promises have settled."""
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "async function main()" in text
    assert re.search(r"await\s+testFn\(\)", text)
    assert "main().catch(" in text
    # The bare, unguarded process.exit() calls (the original defect)
    # must be gone -- process.exitCode is used instead, which lets
    # Node drain the event loop / any settled promises naturally.
    assert "process.exit(" not in text
    assert "process.exitCode" in text


# ---------------------------------------------------------------------
# 2. Structural: sidebar + page presence
# ---------------------------------------------------------------------


def test_sidebar_entry_present(frontend_html):
    assert "showPage('washerresolution')" in frontend_html
    assert 'id="page-washerresolution"' in frontend_html


def test_page_id_appears_exactly_once(frontend_html):
    assert frontend_html.count('id="page-washerresolution"') == 1


def test_sidebar_target_matches_page_id(frontend_html):
    """The sidebar item's showPage('washerresolution') target must
    correspond to page-washerresolution -- same naming convention
    every other sidebar item uses (showPage('X') <-> page-X)."""
    assert "showPage('washerresolution')" in frontend_html
    assert 'id="page-washerresolution"' in frontend_html


def test_sidebar_entry_uses_existing_showpage_mechanism(frontend_html):
    start = frontend_html.index("showPage('washerresolution')")
    line_start = frontend_html.rfind("\n", 0, start)
    line_end = frontend_html.index("\n", start)
    line = frontend_html[line_start:line_end]
    assert 'class="sidebar-item"' in line
    assert "sidebar-icon" in line


def test_showpage_dispatcher_wires_washer_resolution(frontend_html):
    assert "loadWasherResolutionReport()" in frontend_html


def test_api_endpoint_called_through_apirequest_utility(frontend_html):
    """The report must be fetched through the established apiRequest()
    helper (auth header injection, error normalization), not a raw
    fetch() call."""
    idx = frontend_html.index("async function loadWasherResolutionReport")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "apiRequest('/api/library/washers/resolutions/report')" in body
    assert "fetch(" not in body


# ---------------------------------------------------------------------
# 3. Structural: render functions present
# ---------------------------------------------------------------------


def test_render_functions_present(frontend_html):
    for fn in (
        "function wrrRenderAll",
        "function wrrRenderSummaryCards",
        "function wrrRenderDistribution",
        "function wrrRenderIssueTypeDistribution",
        "function wrrRenderLatestDecisions",
        "function wrrRenderIntegrity",
    ):
        assert fn in frontend_html, f"missing: {fn}"


def test_summary_cards_cover_required_metrics(frontend_html):
    idx = frontend_html.index("function wrrRenderSummaryCards")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    for key in (
        "wrr.card.total_records", "wrr.card.effective_open", "wrr.card.under_review",
        "wrr.card.terminal", "wrr.card.blocked", "wrr.card.resolved",
        "wrr.card.total_decisions", "wrr.card.integrity_warnings",
    ):
        assert key in body, f"missing summary card for {key}"


def test_source_and_effective_distributions_both_rendered(frontend_html):
    idx = frontend_html.index("function wrrRenderAll")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "report.source_status_distribution" in body
    assert "report.effective_status_distribution" in body


def test_source_immutability_explained_via_i18n(frontend_html):
    """'source ledger is immutable / effective status is derived'
    must be present as translated (i18n-backed) UI text, not only in
    code comments."""
    assert 'data-i18n="wrr.source_notice"' in frontend_html


def test_no_decision_empty_state_present(frontend_html):
    idx = frontend_html.index("function wrrRenderLatestDecisions")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "wrr.no_decisions" in body
    assert "rows.length" in body  # branches on emptiness, not a static table


def test_integrity_warning_state_present(frontend_html):
    idx = frontend_html.index("function wrrRenderIntegrity")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "warningCount > 0" in body
    assert "alert-warning" in body


def test_loading_state_present(frontend_html):
    idx = frontend_html.index("async function loadWasherResolutionReport")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "wrr.loading" in body


def test_api_error_state_present(frontend_html):
    idx = frontend_html.index("async function loadWasherResolutionReport")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "catch (e)" in body
    assert "wrr.api_error_prefix" in body
    assert "alert-danger" in body


def test_malformed_response_protection_present(frontend_html):
    assert "function wrrIsWellFormed" in frontend_html
    idx = frontend_html.index("async function loadWasherResolutionReport")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "wrrIsWellFormed(report)" in body
    assert "wrr.malformed_response" in body


def test_missing_values_are_not_guessed(frontend_html):
    """WRR_REQUIRED_FIELDS gates rendering -- a response missing any
    required field is rejected outright rather than rendered with
    fabricated/defaulted engineering values."""
    idx = frontend_html.index("const WRR_REQUIRED_FIELDS")
    end = frontend_html.index("];", idx)
    literal = frontend_html[idx:end]
    for field in (
        "total_resolution_records", "effective_open_count", "effective_resolved_count",
        "effective_blocked_count", "data_integrity_warning_count", "report_checksum",
    ):
        assert field in literal, f"{field} not gated by wrrIsWellFormed's required-field list"


def test_wrr_reapply_language_present_and_wired(frontend_html):
    assert "function wrrReapplyLanguage" in frontend_html
    idx = frontend_html.index("function setLanguage(")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "wrrReapplyLanguage()" in body


# ---------------------------------------------------------------------
# 4. Translation key parity + duplicate-key check (whole-file, same
#    technique as the Faz 2.8.8 wrapper)
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


def test_wrr_key_parity_exact_count(frontend_html):
    script = _extract_script(frontend_html)
    en_all = _keys_in_literal(_extract_lang_dict_literal(script, "en"))
    tr_all = _keys_in_literal(_extract_lang_dict_literal(script, "tr"))
    en_wrr = [k for k in en_all if k.startswith("wrr.")]
    tr_wrr = [k for k in tr_all if k.startswith("wrr.")]
    assert len(en_wrr) == len(tr_wrr) == 38, (
        f"expected 38/38 wrr.* key parity, got {len(en_wrr)} EN / {len(tr_wrr)} TR"
    )
    assert len(set(en_wrr)) == len(en_wrr)
    assert len(set(tr_wrr)) == len(tr_wrr)
    assert set(en_wrr) == set(tr_wrr)


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


def test_tr_and_en_text_actually_differ_for_every_wrr_key(frontend_html):
    """Key parity is necessary but not sufficient -- catches an
    untranslated (identical TR/EN) value slipping through. A small
    allow-list covers legitimate technical tokens that are correctly
    identical in both languages (there are none for wrr.* today, but
    the mechanism mirrors the Faz 2.8.8 precedent for future-proofing)."""
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        return dict(re.findall(r"'(wrr\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values, "no wrr.* key/value pairs extracted -- regex or structure changed"
    assert en_values.keys() == tr_values.keys()
    legitimate_identical_allowlist = set()
    identical = {
        k for k in en_values
        if en_values[k] == tr_values[k]
        and en_values[k] != ""
        and k not in legitimate_identical_allowlist
    }
    assert not identical, f"untranslated (identical TR/EN) values: {sorted(identical)}"


def test_turkish_values_use_turkish_characters_where_expected(frontend_html):
    """Spot-check: several wrr.* Turkish values are expected to
    contain at least one Turkish-specific character (ç, ğ, ı, ö, ş,
    ü or their uppercase forms) -- guards against an ASCII-only
    placeholder slipping in as a 'translation'."""
    script = _extract_script(frontend_html)
    tr_literal = _extract_lang_dict_literal(script, "tr")
    values = dict(re.findall(r"'(wrr\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", tr_literal))
    turkish_chars = set("çğıöşüÇĞİÖŞÜ")
    expected_to_contain_turkish_chars = [
        "wrr.page_title", "wrr.source_notice", "wrr.card.total_records",
        "wrr.card.under_review", "wrr.card.resolved", "wrr.col.decided_by",
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


def test_wrr_field_ids_are_unique(frontend_html):
    wrr_ids = re.findall(r'id="(wrr-[a-z0-9-]+)"', frontend_html)
    assert wrr_ids
    assert len(wrr_ids) == len(set(wrr_ids))


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
# 8. 1366x768 overflow-risk proxy (no browser available in this
#    environment -- static structural checks in place of Playwright)
# ---------------------------------------------------------------------


def _wrr_section_html(frontend_html: str) -> str:
    start = frontend_html.index('<div id="page-washerresolution" class="page">')
    end = frontend_html.index('<div id="page-materialintelligence" class="page">')
    return frontend_html[start:end]


def test_no_fixed_large_pixel_widths_introduced(frontend_html):
    """A hard-coded wide fixed-pixel width is the most common cause
    of horizontal overflow at 1366px. The new section must rely on
    the existing responsive classes (card/grid2/ai-form-grid), not a
    custom fixed-width container."""
    section = _wrr_section_html(frontend_html)
    widths = re.findall(r"width\s*:\s*(\d+)px", section)
    oversized = [w for w in widths if int(w) > 1200]
    assert not oversized, f"fixed pixel width(s) that could overflow 1366px: {oversized}"


def test_reuses_existing_responsive_layout_classes(frontend_html):
    section = _wrr_section_html(frontend_html)
    assert 'class="card"' in section
    assert 'class="grid2"' in section
    assert 'class="ai-form-grid"' in section


def test_tables_use_existing_scrollable_table_class(frontend_html):
    """Tables generated by wrrRenderLatestDecisions use the existing
    sc-table class (same one Material Intelligence/Strength Classes
    already rely on), not a bespoke fixed layout."""
    idx = frontend_html.index("function wrrRenderLatestDecisions")
    end = frontend_html.index("\n}", idx)
    body = frontend_html[idx:end]
    assert "sc-table" in body


# ---------------------------------------------------------------------
# 9. No unsupported-capability / no-invention claims in new UI text
# ---------------------------------------------------------------------


def test_no_unsupported_claims_in_wrr_text(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    en_values = dict(re.findall(r"'(wrr\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", en_literal))
    forbidden_phrases = (
        "production-ready", "certified", "ai-recommended", "guaranteed", "verified automatically",
    )
    joined = " ".join(en_values.values()).lower()
    for phrase in forbidden_phrases:
        assert phrase not in joined, f"unsupported claim found in wrr.* text: {phrase!r}"
