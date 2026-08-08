"""Faz 2.9.11 tests: Question Bank Statistics / Coverage dashboard
frontend (frontend/index.html).

Structural only (no browser, no Node/vm behavioral harness -- same
minimum bar as tests/test_faz_2_9_{7,8,9}_question_bank_*_frontend.py:
JS *syntax* validity via `node --check`, everything else via plain
text/regex assertions against the file). Covers: the Statistics /
Coverage card's presence and placement, its loading/empty/error-state
handling, that it renders the exact `GET /api/question-bank/stats`
response (Faz 2.9.10) verbatim (total, by_validation_status,
by_category, by_difficulty, by_question_type) without re-implementing
any aggregation client-side, that it participates in the existing
qbInit()/qbReapplyLanguage() lifecycle, qb.stats.* TR/EN key parity,
and that every referenced qb.stats.* key actually exists in both
languages.

Does not modify frontend/index.html from this file, and does not
touch backend/question_bank/stats.py or
backend/api/routes/question_bank.py (see
tests/test_faz_2_9_10_question_bank_stats.py for that -- this phase
reuses the Faz 2.9.10 endpoint verbatim, no backend change).
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
# 1. Statistics / Coverage card presence + placement
# ---------------------------------------------------------------------


def test_stats_card_title_and_refresh_button_present(frontend_html):
    assert 'data-i18n="qb.stats.title"' in frontend_html
    assert 'data-i18n="qb.stats.sub"' in frontend_html
    assert "qbLoadStats()" in frontend_html
    assert 'data-i18n="qb.stats.refresh_button"' in frontend_html


def test_stats_status_and_body_containers_present(frontend_html):
    assert 'id="qb-stats-status"' in frontend_html
    assert 'id="qb-stats-body"' in frontend_html


def test_stats_card_is_inside_questionbank_page(frontend_html):
    page_start = frontend_html.index('id="page-questionbank"')
    page_end = frontend_html.index('id="page-materialintelligence"')
    between = frontend_html[page_start:page_end]
    assert 'id="qb-stats-status"' in between
    assert 'id="qb-stats-body"' in between


def test_stats_card_appears_after_questions_list_card(frontend_html):
    """Placement check: the stats card should follow the existing
    Questions list card, not precede or interleave with it."""
    list_table_idx = frontend_html.index('id="qb-list-table"')
    stats_idx = frontend_html.index('id="qb-stats-body"')
    assert stats_idx > list_table_idx


# ---------------------------------------------------------------------
# 2. qbLoadStats(): API wiring, reuses the existing Faz 2.9.10 endpoint
#    verbatim, no query parameters, no client-side re-aggregation
# ---------------------------------------------------------------------


def test_load_stats_function_present(qb_js):
    assert "async function qbLoadStats(" in qb_js


def test_load_stats_calls_existing_stats_endpoint(qb_js):
    body = _function_body(qb_js, "async function qbLoadStats(")
    assert "/api/question-bank/stats" in body
    assert "apiRequest(" in body


def test_load_stats_endpoint_call_takes_no_query_parameters(qb_js):
    """Faz 2.9.10's stats endpoint takes no query parameters --
    the frontend must not invent one (e.g. must not build a
    qbBuildListQuery()-style query string for this call)."""
    body = _function_body(qb_js, "async function qbLoadStats(")
    assert "apiRequest('/api/question-bank/stats')" in body


def test_load_stats_stores_result_in_module_state(qb_js):
    body = _function_body(qb_js, "async function qbLoadStats(")
    assert "QB_STATS = await apiRequest" in body


def test_load_stats_handles_loading_and_error_states(qb_js):
    body = _function_body(qb_js, "async function qbLoadStats(")
    assert "qb.stats.loading" in body
    assert "qb.stats.error_prefix" in body
    assert "qb-stats-status" in body


def test_load_stats_resets_state_on_error(qb_js):
    """An error must not leave a stale successful QB_STATS behind --
    a failed refresh should not silently keep showing the previous
    (potentially now-wrong) numbers without any error indication."""
    body = _function_body(qb_js, "async function qbLoadStats(")
    catch_clause = body[body.index("catch"):]
    assert "QB_STATS = null" in catch_clause


# ---------------------------------------------------------------------
# 3. qbRenderStats(): renders total + all four breakdowns verbatim,
#    empty-state handling, no re-implemented aggregation
# ---------------------------------------------------------------------


def test_render_stats_function_present(qb_js):
    assert "function qbRenderStats(" in qb_js


def test_render_stats_uses_total_field_directly(qb_js):
    body = _function_body(qb_js, "function qbRenderStats(")
    assert "QB_STATS.total" in body


def test_render_stats_covers_all_four_breakdowns(qb_js):
    """qbRenderStats() iterates QB_STATS_BREAKDOWNS (indexing
    QB_STATS[key] generically) rather than naming each of the four
    breakdown keys as a literal -- so the coverage check is on the
    breakdowns table definition itself, exercised together with
    test_stats_breakdown_table_definition_lists_all_four_keys."""
    body = _function_body(qb_js, "function qbRenderStats(")
    assert "QB_STATS_BREAKDOWNS" in body
    assert "QB_STATS[key]" in body


def test_render_stats_handles_empty_state(qb_js):
    body = _function_body(qb_js, "function qbRenderStats(")
    assert "qb.stats.empty" in body


def test_render_stats_does_not_reimplement_counting(qb_js):
    """The dashboard must treat the API response as the single source
    of truth: no client-side loop that increments a counter per
    question record (that would be re-implementing
    backend.question_bank.stats.compute_stats client-side, which is
    explicitly out of scope for Faz 2.9.11)."""
    body = _function_body(qb_js, "function qbRenderStats(")
    assert "QB_LIST" not in body


def test_stats_breakdown_table_definition_lists_all_four_keys(qb_js):
    assert "QB_STATS_BREAKDOWNS" in qb_js
    start = qb_js.index("QB_STATS_BREAKDOWNS")
    breakdowns_block = qb_js[start:qb_js.index("];", start)]
    for key in ("by_validation_status", "by_category", "by_difficulty", "by_question_type"):
        assert f"'{key}'" in breakdowns_block


# ---------------------------------------------------------------------
# 4. Lifecycle wiring: qbInit() loads stats, qbReapplyLanguage()
#    re-renders them (language switch must not require a re-fetch)
# ---------------------------------------------------------------------


def test_qb_init_loads_stats(qb_js):
    body = _function_body(qb_js, "function qbInit(")
    assert "qbLoadStats()" in body


def test_reapply_language_rerenders_stats_without_refetching(qb_js):
    body = _function_body(qb_js, "function qbReapplyLanguage(")
    assert "qbRenderStats()" in body
    assert "qbLoadStats()" not in body


# ---------------------------------------------------------------------
# 5. i18n: qb.stats.* key parity + no missing referenced keys
# ---------------------------------------------------------------------


def test_qb_stats_key_parity_between_tr_and_en(frontend_html):
    script = _extract_script(frontend_html)
    en_all = _keys_in_literal(_extract_lang_dict_literal(script, "en"))
    tr_all = _keys_in_literal(_extract_lang_dict_literal(script, "tr"))
    en_stats = {k for k in en_all if k.startswith("qb.stats.")}
    tr_stats = {k for k in tr_all if k.startswith("qb.stats.")}
    assert en_stats, "expected at least one qb.stats.* EN key"
    assert en_stats == tr_stats, (
        f"qb.stats.* key parity broken -- only in en: {sorted(en_stats - tr_stats)}, "
        f"only in tr: {sorted(tr_stats - en_stats)}"
    )


def test_qb_stats_values_actually_translated(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        return dict(re.findall(r"'(qb\.stats\.[a-zA-Z0-9_.]+)':\s*'([^']*)'", literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values, "no qb.stats.* key/value pairs extracted"
    assert en_values.keys() == tr_values.keys()
    identical = {k for k in en_values if en_values[k] == tr_values[k]}
    assert not identical, f"untranslated (identical TR/EN) qb.stats.* values: {sorted(identical)}"


def test_no_qb_stats_t_call_references_a_missing_key(frontend_html):
    """Every t('qb.stats....') call anywhere in the QB section must
    resolve to a key that actually exists in both I18N.en and
    I18N.tr."""
    qb_js = _qb_section_text(frontend_html)
    referenced = set(re.findall(r"t\('(qb\.stats\.[a-zA-Z0-9_.]+)'\)", qb_js))
    assert referenced, "expected at least one t('qb.stats....') call in the QB section"

    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))

    missing_en = referenced - en_keys
    missing_tr = referenced - tr_keys
    assert not missing_en, f"referenced but missing from EN I18N: {sorted(missing_en)}"
    assert not missing_tr, f"referenced but missing from TR I18N: {sorted(missing_tr)}"


def test_qb_stats_required_keys_present(frontend_html):
    required = (
        "qb.stats.title",
        "qb.stats.sub",
        "qb.stats.refresh_button",
        "qb.stats.loading",
        "qb.stats.empty",
        "qb.stats.error_prefix",
        "qb.stats.total_label",
        "qb.stats.by_validation_status",
        "qb.stats.by_category",
        "qb.stats.by_difficulty",
        "qb.stats.by_question_type",
        "qb.stats.unknown_bucket",
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
