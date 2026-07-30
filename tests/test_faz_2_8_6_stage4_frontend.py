"""Faz 2.8.6 Stage 4 tests: Assembly Intelligence Frontend Integration.

Two layers, mirroring the existing frontend test conventions:

1. Behavioral: tests/js/run_assembly_intelligence_tests.js (a
   dependency-free Node/vm harness, same technique as
   tests/js/run_i18n_tests.js -- Faz 2.6.8) is run as a subprocess.
   That harness covers payload cleanliness, numeric conversion,
   include_report boolean, double-submit guard, 200/401/422/network-
   error handling, loading state, not_assessable rendering, checks[]/
   suggested_action/critical_incompatibilities rendering, the critical
   banner's prominence regardless of score, report visibility
   toggling, deterministic rendering, TR/EN live re-render without
   refetch, and a static-source guard against client-side score
   recalculation.

2. Structural (this module, no browser required): sidebar entry
   presence, page id presence, static TR/EN markup text, translation
   key parity, duplicate-key check (scoped so pre-existing unrelated
   duplicates are not flagged as new), HTML id uniqueness, JS syntax
   via `node --check`, and that no new framework/bundler reference was
   introduced.

Does not modify frontend/index.html from this file, and does not
touch Stage 1/2/3 backend files.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_assembly_intelligence_tests.js"
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

def test_assembly_intelligence_harness_all_assertions_pass():
    result = _run_harness()
    assert result.returncode == 0, (
        "Assembly Intelligence harness reported failures:\n" + result.stdout + result.stderr
    )


def test_assembly_intelligence_harness_reports_a_nonzero_assertion_count():
    result = _run_harness()
    m = re.search(r"(\d+) assertions, (\d+) passed, (\d+) failed", result.stdout)
    assert m, "harness output missing expected summary line:\n" + result.stdout
    total, passed, failed = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert failed == 0
    assert total > 0
    assert passed == total


def test_harness_file_is_dependency_free():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "require('jsdom')" not in text
    assert "require('puppeteer')" not in text
    assert "require('playwright')" not in text
    # require('./harness_common') is Faz 2.8.10 Stage 3's shared,
    # dependency-free, in-repo helper module (see tests/js/harness_common.js) --
    # not an external package, so it is allowed alongside the Node builtins.
    assert "require(" not in text.replace("require('fs')", "").replace(
        "require('path')", ""
    ).replace("require('vm')", "").replace("require('./harness_common')", "")


# ---------------------------------------------------------------------
# 2. Structural: sidebar + page presence (mirrors
#    test_frontend_navigation_item_present in the Faz 2.6.6 file)
# ---------------------------------------------------------------------

def test_sidebar_entry_present(frontend_html):
    assert "showPage('assemblyintelligence')" in frontend_html
    assert 'id="page-assemblyintelligence"' in frontend_html


def test_sidebar_entry_uses_existing_showpage_mechanism(frontend_html):
    """Not a bespoke navigation mechanism -- reuses the same
    onclick="showPage(...)" pattern every other sidebar item uses."""
    start = frontend_html.index("showPage('assemblyintelligence')")
    line_start = frontend_html.rfind("\n", 0, start)
    line_end = frontend_html.index("\n", start)
    line = frontend_html[line_start:line_end]
    assert 'class="sidebar-item"' in line
    assert "sidebar-icon" in line


def test_page_opens_after_sidebar_item(frontend_html):
    """The page div immediately reachable / present in the document
    (structural stand-in for 'sayfanın açılması' without a browser)."""
    idx = frontend_html.index('id="page-assemblyintelligence"')
    assert 'class="page"' in frontend_html[idx:idx + 60]


# ---------------------------------------------------------------------
# 3. Structural: TR/EN static text present
# ---------------------------------------------------------------------

def test_tr_static_text_present(frontend_html):
    for phrase in (
        "Montaj Zekâsı", "Montajı Değerlendir", "Kritik uyumsuzluk tespit edildi",
        "Kritik Uyumsuzluklar", "Değerlendirme için yeterli veri bulunmuyor",
    ):
        assert phrase in frontend_html, f"missing TR phrase: {phrase!r}"


def test_en_static_text_present(frontend_html):
    for phrase in (
        "Assembly Intelligence", "Assess Assembly", "Critical incompatibility detected",
        "Critical Incompatibilities", "There is not enough data for an assessment",
    ):
        assert phrase in frontend_html, f"missing EN phrase: {phrase!r}"


# ---------------------------------------------------------------------
# 4. Translation key parity + duplicate-key check (scoped to avoid
#    flagging the two pre-existing, unrelated duplicates as new)
# ---------------------------------------------------------------------

_PRE_EXISTING_DUPLICATE_KEYS = {"hizli.enter_parameters", "yetenek.oem_tmin_tmax"}


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


def test_no_new_duplicate_translation_keys(frontend_html):
    script = _extract_script(frontend_html)
    for lang in ("en", "tr"):
        literal = _extract_lang_dict_literal(script, lang)
        keys = _keys_in_literal(literal)
        counts = Counter(keys)
        dups = {k for k, c in counts.items() if c > 1}
        new_dups = dups - _PRE_EXISTING_DUPLICATE_KEYS
        assert not new_dups, f"new duplicate key(s) in {lang!r}: {sorted(new_dups)}"


def test_assembly_intelligence_keys_present_and_paired(frontend_html):
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    required_min = {
        "sidebar.assemblyintelligence", "ai.page_title", "ai.assess_button",
        "ai.overall_score", "ai.coverage", "ai.overall_status", "ai.risk_level",
        "ai.passed", "ai.warnings", "ai.failed", "ai.detected_problems",
        "ai.recommendations", "ai.compatibility", "ai.critical_incompatibilities",
        "ai.critical_detected", "ai.suggested_action", "ai.data_source",
        "ai.field.include_report", "ai.assessment_completed", "ai.assessment_failed",
        "ai.loading", "ai.no_critical_incompatibility", "ai.no_recommendation",
    }
    missing_en = required_min - en_keys
    missing_tr = required_min - tr_keys
    assert not missing_en, f"missing required EN keys: {sorted(missing_en)}"
    assert not missing_tr, f"missing required TR keys: {sorted(missing_tr)}"


# ---------------------------------------------------------------------
# 5. HTML element ID uniqueness (whole document, not just ai-*)
# ---------------------------------------------------------------------

def test_all_html_ids_are_unique(frontend_html):
    ids = re.findall(r'id="([a-zA-Z0-9_-]+)"', frontend_html)
    counts = Counter(ids)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert not dups, f"duplicate HTML ids found: {dups}"


def test_assembly_intelligence_field_ids_are_unique(frontend_html):
    ai_ids = re.findall(r'id="(ai-[a-z0-9-]+)"', frontend_html)
    assert ai_ids
    assert len(ai_ids) == len(set(ai_ids))


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
# 8. Frontend never recalculates engine results (structural guard,
#    complements the harness's static-source check with a check on
#    the raw file text)
# ---------------------------------------------------------------------

def test_no_forbidden_score_recalculation_language(frontend_html):
    start = frontend_html.index("function aiRenderResult(")
    end = frontend_html.index("function aiReapplyLanguage(")
    section = frontend_html[start:end]
    for forbidden in ("score * ", "coverage * ", "/ total_checks", "/ assessed_checks"):
        assert forbidden not in section


# ---------------------------------------------------------------------
# 9. Uses the existing apiRequest/auth helper, not a bespoke fetch
# ---------------------------------------------------------------------

def test_uses_existing_api_request_helper(frontend_html):
    start = frontend_html.index("async function aiAssessAssembly(")
    end = frontend_html.index("function aiRenderResult(")
    section = frontend_html[start:end]
    assert "apiRequest('/api/assembly-intelligence/assess'" in section
    assert "fetch(" not in section


# ---------------------------------------------------------------------
# 10. Regression: existing pages/sidebar sections still present
# ---------------------------------------------------------------------

def test_existing_navigation_items_unaffected(frontend_html):
    for item in (
        "showPage('frictioncondition')", "showPage('strengthclasses')", "showPage('norm')",
        "showPage('dashboard')", "showPage('oem')",
    ):
        assert item in frontend_html


def test_existing_pages_unaffected(frontend_html):
    for page_id in (
        'id="page-frictioncondition"', 'id="page-strengthclasses"', 'id="page-norm"',
        'id="page-dashboard"',
    ):
        assert page_id in frontend_html
