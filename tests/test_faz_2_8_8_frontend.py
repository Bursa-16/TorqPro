"""Faz 2.8.8 tests: Material Intelligence / Formula Validation Frontend.

Two layers, mirroring the Faz 2.8.7 frontend test conventions:

1. Behavioral: tests/js/run_material_intelligence_tests.js (a
   dependency-free Node/vm harness, same technique as
   tests/js/run_i18n_tests.js and tests/js/run_joint_analysis_tests.js)
   is run as a subprocess against the *actual* declarations extracted
   live from frontend/index.html.
2. Structural (this module, no browser required): sidebar entry
   presence, page id presence, static TR/EN markup text, translation
   key parity, duplicate-key check, HTML id uniqueness, JS syntax via
   `node --check`, no new framework/bundler reference, and that no
   unsupported-capability claim ("production-ready", "certified",
   "AI-recommended", etc.) leaked into the new UI text.

Does not modify frontend/index.html from this file, and does not
touch backend Faz 2.8.8 files.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_material_intelligence_tests.js"
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


def test_material_intelligence_harness_all_assertions_pass():
    result = _run_harness()
    assert result.returncode == 0, (
        "Material Intelligence harness reported failures:\n" + result.stdout + result.stderr
    )


def test_material_intelligence_harness_reports_a_nonzero_assertion_count():
    result = _run_harness()
    m = re.search(r"(\d+) assertions, (\d+) passed, (\d+) failed", result.stdout)
    assert m, "harness output missing expected summary line:\n" + result.stdout
    total, passed, failed = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert failed == 0
    assert passed == total
    assert total > 0


def test_material_intelligence_harness_assertion_count_exceeds_original_sync_only_count():
    """Faz 2.8.11 Stage 5: this harness's async scenarios were
    previously invoked as bare, unawaited top-level IIFEs -- the
    synchronous summary/process.exit() block ran before several
    scenarios' check() calls (sitting inside a `.then()` callback)
    had a chance to execute, so the harness silently reported a
    'clean' but incomplete result. Now fixed to the same awaited
    `async function main()` pattern as
    tests/js/run_washer_resolution_report_tests.js and
    tests/js/run_governance_workspace_tests.js. This is the
    regression guard: the real count must stay materially above what
    the synchronous-only portion of the 19 scenarios could ever
    report on its own."""
    result = _run_harness()
    m = re.search(r"(\d+) assertions, (\d+) passed, (\d+) failed", result.stdout)
    assert m, "harness output missing expected summary line:\n" + result.stdout
    total, passed, failed = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert failed == 0
    assert passed == total
    assert total > 19, f"only {total} assertions ran -- async scenarios may not be awaited"


def test_harness_uses_awaited_main_not_bare_process_exit():
    """Structural guard against regressing back to the Faz 2.8.8
    defect: the harness must funnel every scenario through an
    awaited `main()`, never call `process.exit()` unconditionally
    before all promises have settled."""
    text = HARNESS_PATH.read_text(encoding="utf-8")
    code_only = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("//")
    )
    assert "async function main()" in code_only
    assert re.search(r"await\s+testFn\(\)", code_only)
    assert "main().catch(" in code_only
    assert "process.exit(" not in code_only
    assert "process.exitCode" in code_only


def test_every_scenario_in_all_tests_is_declared_async():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    idx = text.index("const ALL_TESTS = [")
    end = text.index("];", idx)
    names = re.findall(r"\n\s*(test\w+),?", text[idx:end])
    assert len(names) == 19
    for name in names:
        assert re.search(r"async function " + re.escape(name) + r"\(", text), (
            f"{name} is listed in ALL_TESTS but is not declared async"
        )


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
# 2. Structural: sidebar + page presence
# ---------------------------------------------------------------------


def test_sidebar_entry_present(frontend_html):
    assert "showPage('materialintelligence')" in frontend_html
    assert 'id="page-materialintelligence"' in frontend_html


def test_sidebar_entry_uses_existing_showpage_mechanism(frontend_html):
    """Not a bespoke navigation mechanism -- reuses the same
    onclick="showPage(...)" pattern every other sidebar item uses."""
    start = frontend_html.index("showPage('materialintelligence')")
    line_start = frontend_html.rfind("\n", 0, start)
    line_end = frontend_html.index("\n", start)
    line = frontend_html[line_start:line_end]
    assert 'class="sidebar-item"' in line
    assert "sidebar-icon" in line


def test_page_opens_after_sidebar_item(frontend_html):
    idx = frontend_html.index('id="page-materialintelligence"')
    assert 'class="page"' in frontend_html[idx:idx + 60]


def test_recommend_button_present(frontend_html):
    assert 'onclick="miRecommend()"' in frontend_html


def test_showpage_dispatcher_wires_material_intelligence(frontend_html):
    assert "loadMaterialIntelligenceWorkspace()" in frontend_html


# ---------------------------------------------------------------------
# 3. Structural: TR/EN static text present
# ---------------------------------------------------------------------


def test_tr_static_text_present(frontend_html):
    for phrase in (
        "Malzeme Zekası", "Malzeme Kütüphanesi", "Malzeme Önerisi",
    ):
        assert phrase in frontend_html, f"missing TR phrase: {phrase!r}"


def test_en_static_text_present(frontend_html):
    for phrase in (
        "Material Intelligence", "Material Library", "Material Recommendation",
        "Get Recommendation", "Engineering Formula Validation",
    ):
        assert phrase in frontend_html, f"missing EN phrase: {phrase!r}"


def test_advisory_boundary_banner_present_in_both_languages(frontend_html):
    # The UI-level restatement of the mandatory architectural
    # boundary (product-owner directive 2026-07-28): the workspace
    # must say, in both languages, that it never touches the
    # deterministic calculations.
    assert "mi.banner" in frontend_html
    en_banner_idx = frontend_html.index("'mi.banner':")
    en_banner = frontend_html[en_banner_idx:en_banner_idx + 400]
    assert "never modifies preload, torque, clamp force" in en_banner
    tr_banner_idx = frontend_html.rindex("'mi.banner':")
    assert tr_banner_idx != en_banner_idx, "TR mi.banner entry missing"


# ---------------------------------------------------------------------
# 4. Translation key parity + duplicate-key check
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
    """The whole-file parity check -- not scoped to mi.* -- catching
    any drift the Faz 2.8.8 edit introduced anywhere in the shared
    I18N dictionary."""
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


def test_material_intelligence_keys_present_and_paired(frontend_html):
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    required_min = {
        "sidebar.materialintelligence", "mi.page_title", "mi.page_subtitle", "mi.banner",
        "mi.materials_title", "mi.materials_sub", "mi.requirement_title", "mi.requirement_sub",
        "mi.field.min_rp02_mpa", "mi.field.min_rm_mpa", "mi.field.min_e_mpa",
        "mi.field.material_family", "mi.field.readiness_level", "mi.recommend_button",
        "mi.formula_validation_title", "mi.formula_validation_sub", "mi.loading",
        "mi.empty_state", "mi.no_candidates", "mi.api_error_prefix",
        "mi.col.id", "mi.col.material", "mi.col.grade", "mi.col.validation_status",
        "mi.col.approval_status", "mi.col.margin", "mi.col.symbol", "mi.col.classification",
        "mi.col.catalog", "mi.col.approved_count",
    }
    missing_en = required_min - en_keys
    missing_tr = required_min - tr_keys
    assert not missing_en, f"missing required EN keys: {sorted(missing_en)}"
    assert not missing_tr, f"missing required TR keys: {sorted(missing_tr)}"


def test_mi_key_count_matches_between_languages(frontend_html):
    script = _extract_script(frontend_html)
    en_all = _keys_in_literal(_extract_lang_dict_literal(script, "en"))
    tr_all = _keys_in_literal(_extract_lang_dict_literal(script, "tr"))
    en_keys = [k for k in en_all if k.startswith("mi.")]
    tr_keys = [k for k in tr_all if k.startswith("mi.")]
    assert len(en_keys) == len(tr_keys)
    assert len(set(en_keys)) == len(en_keys)  # no internal duplicates
    assert len(set(tr_keys)) == len(tr_keys)


def test_tr_and_en_text_actually_differ_for_every_mi_key(frontend_html):
    """Parity of *keys* is necessary but not sufficient -- a key that
    exists in both dicts with identical (untranslated) text would
    still fail the TR/EN mandate. Spot-checks every mi.* value pair."""
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        return dict(re.findall(r"'(mi\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values, "no mi.* key/value pairs extracted -- regex or structure changed"
    assert en_values.keys() == tr_values.keys()
    identical = {k for k in en_values if en_values[k] == tr_values[k] and en_values[k] != ""}
    assert not identical, f"untranslated (identical TR/EN) values: {sorted(identical)}"


# ---------------------------------------------------------------------
# 5. HTML element ID uniqueness
# ---------------------------------------------------------------------


def test_all_html_ids_are_unique(frontend_html):
    ids = re.findall(r'id="([a-zA-Z0-9_-]+)"', frontend_html)
    counts = Counter(ids)
    dups = {k: v for k, v in counts.items() if v > 1}
    assert not dups, f"duplicate HTML ids found: {dups}"


def test_material_intelligence_field_ids_are_unique(frontend_html):
    mi_ids = re.findall(r'id="(mi-[a-z0-9-]+)"', frontend_html)
    assert mi_ids
    assert len(mi_ids) == len(set(mi_ids))


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
# 8. No unsupported-capability claims in the new UI text
# ---------------------------------------------------------------------


def _mi_section_text(frontend_html: str) -> str:
    start = frontend_html.index('<!-- MATERIAL INTELLIGENCE (Faz 2.8.8) -->')
    end = frontend_html.index('<!-- NORM REHBERİ -->')
    return frontend_html[start:end]


def test_no_unsupported_claims_in_material_intelligence_section(frontend_html):
    section = _mi_section_text(frontend_html).lower()
    forbidden = (
        "production-approved", "production approved", "certified", "iso 16047 certified",
        "ai-recommended", "ai recommended", "guaranteed", "best material", "en iyi malzeme",
        "sertifikalı", "onaylanmış malzeme",
    )
    for phrase in forbidden:
        assert phrase not in section, f"unsupported claim leaked into UI: {phrase!r}"


def test_no_unsupported_claims_in_mi_translation_values(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")
    mi_en_text = " ".join(re.findall(r"'mi\.[a-zA-Z0-9_.]+':\s*'([^']*)'", en_literal)).lower()
    mi_tr_text = " ".join(re.findall(r"'mi\.[a-zA-Z0-9_.]+':\s*'([^']*)'", tr_literal)).lower()
    for phrase in ("certified", "guaranteed", "production-approved", "sertifikalı", "garantili"):
        assert phrase not in mi_en_text, phrase
        assert phrase not in mi_tr_text, phrase
