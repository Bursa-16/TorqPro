"""Faz 2.8.22 tests: "Örnek Tork Çalışması" / Sample Torque Study screen
UI/UX messaging corrections (PDF review, 2026-08-06).

Two layers, mirroring the Faz 2.8.8 / Material Intelligence frontend
test conventions:

1. Behavioral: tests/js/run_torque_study_ui_messaging_tests.js (a
   dependency-free Node/vm harness, same technique as
   tests/js/run_i18n_tests.js) is run as a subprocess against the
   *actual* declarations extracted live from frontend/index.html.
2. Structural (this module, no browser required): translation key
   parity/no-duplicates for the touched n01391.* keys, JS syntax via
   `node --check`, and that the previously leaked raw HTML markup in
   the title string does not reappear.

Scope: frontend/index.html only (title rendering, icon/popover
messaging, wording). Does not touch the calculation engine, the
bolt/nut class compatibility decision, or any backend file.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = REPO_ROOT / "tests" / "js" / "run_torque_study_ui_messaging_tests.js"
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


def test_torque_study_harness_all_assertions_pass():
    result = _run_harness()
    assert result.returncode == 0, (
        "Torque Study UI messaging harness reported failures:\n" + result.stdout + result.stderr
    )


def test_torque_study_harness_reports_a_nonzero_assertion_count():
    result = _run_harness()
    m = re.search(r"(\d+) assertions, (\d+) passed, (\d+) failed", result.stdout)
    assert m, "harness output missing expected summary line:\n" + result.stdout
    total, passed, failed = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert failed == 0
    assert passed == total
    assert total > 0


def test_harness_file_is_dependency_free():
    text = HARNESS_PATH.read_text(encoding="utf-8")
    assert "require('jsdom')" not in text
    assert "require('puppeteer')" not in text
    assert "require('playwright')" not in text
    assert "require(" not in text.replace("require('fs')", "").replace(
        "require('path')", ""
    ).replace("require('vm')", "").replace("require('./harness_common')", "")


# ---------------------------------------------------------------------
# 2. Structural: no raw HTML leaking into the title string (Item 1)
# ---------------------------------------------------------------------


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
    return script[start : i + 1]


def _keys_in_literal(literal: str) -> list:
    return re.findall(r"'([a-zA-Z0-9_.]+)':", literal)


def test_title_key_has_no_embedded_html_markup(frontend_html):
    script = _extract_script(frontend_html)
    for lang in ("en", "tr"):
        literal = _extract_lang_dict_literal(script, lang)
        m = re.search(r"'n01391\.title':\s*'([^']*)'", literal)
        assert m, f"n01391.title missing from {lang} dict"
        assert "<" not in m.group(1) and ">" not in m.group(1), (
            f"n01391.title ({lang}) still contains raw markup: {m.group(1)!r}"
        )


def test_title_static_markup_has_no_embedded_span(frontend_html):
    idx = frontend_html.index('data-i18n="n01391.title"')
    line_end = frontend_html.index("</div>", idx)
    fragment = frontend_html[idx:line_end]
    assert "<span" not in fragment, "leaked <span> markup reintroduced in static title markup"


# ---------------------------------------------------------------------
# 3. Structural: wording shortened (Item 5), old phrasing fully gone
# ---------------------------------------------------------------------


def test_old_general_oem_forecast_wording_is_gone(frontend_html):
    assert "genel öngörüsü" not in frontend_html
    assert "sample general OEM forecast" not in frontend_html


def test_new_short_estimate_wording_present(frontend_html):
    assert "örnek öngörüdür" in frontend_html
    assert "sample estimate" in frontend_html


# ---------------------------------------------------------------------
# 4. Structural: translation key parity + no new duplicate keys
# ---------------------------------------------------------------------


_PRE_EXISTING_DUPLICATE_KEYS = {"hizli.enter_parameters", "yetenek.oem_tmin_tmax"}


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


def test_new_icon_label_keys_present_and_paired(frontend_html):
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    required_min = {
        "n01391.scope_priority_icon_label",
        "n01391.ref_source_icon_label",
        "n01391.matching_rule_label",
        "n01391.matching_rule_icon_label",
        "n01391.mismatch_icon_label",
        "n01391.disclaimer_icon_label",
    }
    missing_en = required_min - en_keys
    missing_tr = required_min - tr_keys
    assert not missing_en, f"missing required EN keys: {sorted(missing_en)}"
    assert not missing_tr, f"missing required TR keys: {sorted(missing_tr)}"


def test_tr_and_en_text_differ_for_new_icon_label_keys(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        return dict(re.findall(r"'(n01391\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values.keys() == tr_values.keys()
    identical = {k for k in en_values if en_values[k] == tr_values[k] and en_values[k] != ""}
    assert not identical, f"untranslated (identical TR/EN) values: {sorted(identical)}"


# ---------------------------------------------------------------------
# 5. Structural: new CSS variants (error/reference) exist
# ---------------------------------------------------------------------


def test_error_and_ref_icon_css_variants_present(frontend_html):
    assert ".info-icon-btn.err" in frontend_html
    assert ".info-icon-btn.ref" in frontend_html


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
