"""Faz 2.9.12 frontend tests: Question Bank Statistics Trend / History
panel (frontend/index.html).

Structural only -- same minimum bar as
``tests/test_faz_2_9_11_question_bank_statistics_dashboard_frontend.py``:
JS *syntax* validity via ``node --check``, everything else via plain
text/regex assertions against the file. Covers: the Trend / History
card's presence and placement (after the existing Faz 2.9.11
Statistics/Coverage card, still inside ``page-questionbank``), its
loading/empty/error-state handling, that it renders the Faz 2.9.12
``GET /api/question-bank/stats/history`` response verbatim (each
entry's ``created_at``/``stats.total``) without re-implementing any
aggregation client-side, the snapshot-creation button wiring to
``POST /api/question-bank/stats/snapshot``, that it participates in
the existing ``qbInit()``/``qbReapplyLanguage()`` lifecycle, ``qb.
stats.history.*`` TR/EN key parity, and that no charting library is
introduced anywhere in the file.

Does not modify ``frontend/index.html`` from this file, and does not
touch ``backend/question_bank/stats_history.py`` or
``backend/api/routes/question_bank.py`` (see
``tests/test_faz_2_9_12_question_bank_stats_history.py`` for that).
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
# 1. Trend / History card presence + placement
# ---------------------------------------------------------------------


def test_history_card_title_and_buttons_present(frontend_html):
    assert 'data-i18n="qb.stats.history.title"' in frontend_html
    assert 'data-i18n="qb.stats.history.sub"' in frontend_html
    assert "qbCreateStatsSnapshot()" in frontend_html
    assert 'data-i18n="qb.stats.history.snapshot_button"' in frontend_html
    assert "qbLoadStatsHistory()" in frontend_html
    assert 'data-i18n="qb.stats.history.refresh_button"' in frontend_html


def test_history_status_and_body_containers_present(frontend_html):
    assert 'id="qb-stats-history-status"' in frontend_html
    assert 'id="qb-stats-history-body"' in frontend_html


def test_history_card_is_inside_questionbank_page(frontend_html):
    page_start = frontend_html.index('id="page-questionbank"')
    page_end = frontend_html.index('id="page-materialintelligence"')
    between = frontend_html[page_start:page_end]
    assert 'id="qb-stats-history-status"' in between
    assert 'id="qb-stats-history-body"' in between


def test_history_card_appears_after_stats_card(frontend_html):
    """Placement check: the Trend/History card should follow the
    existing Faz 2.9.11 Statistics/Coverage card, not precede or
    interleave with it."""
    stats_idx = frontend_html.index('id="qb-stats-body"')
    history_idx = frontend_html.index('id="qb-stats-history-body"')
    assert history_idx > stats_idx


# ---------------------------------------------------------------------
# 2. qbLoadStatsHistory() / qbCreateStatsSnapshot(): API wiring, reuses
#    the Faz 2.9.12 endpoints verbatim, no client-side re-aggregation
# ---------------------------------------------------------------------


def test_load_stats_history_function_present(qb_js):
    assert "async function qbLoadStatsHistory(" in qb_js


def test_load_stats_history_calls_history_endpoint(qb_js):
    body = _function_body(qb_js, "async function qbLoadStatsHistory(")
    assert "/api/question-bank/stats/history" in body
    assert "apiRequest(" in body


def test_load_stats_history_stores_result_in_module_state(qb_js):
    body = _function_body(qb_js, "async function qbLoadStatsHistory(")
    assert "QB_STATS_HISTORY = await apiRequest" in body


def test_load_stats_history_handles_loading_and_error_states(qb_js):
    body = _function_body(qb_js, "async function qbLoadStatsHistory(")
    assert "qb.stats.history.loading" in body
    assert "qb.stats.history.error_prefix" in body
    assert "qb-stats-history-status" in body


def test_load_stats_history_resets_state_on_error(qb_js):
    """An error must not leave a stale successful QB_STATS_HISTORY
    behind -- a failed refresh should not silently keep showing the
    previous (potentially now-wrong) list without any error
    indication."""
    body = _function_body(qb_js, "async function qbLoadStatsHistory(")
    catch_clause = body[body.index("catch"):]
    assert "QB_STATS_HISTORY = null" in catch_clause


def test_create_snapshot_function_present(qb_js):
    assert "async function qbCreateStatsSnapshot(" in qb_js


def test_create_snapshot_calls_snapshot_endpoint_with_post(qb_js):
    body = _function_body(qb_js, "async function qbCreateStatsSnapshot(")
    assert "/api/question-bank/stats/snapshot" in body
    assert "'POST'" in body or '"POST"' in body


def test_create_snapshot_refreshes_history_afterwards(qb_js):
    body = _function_body(qb_js, "async function qbCreateStatsSnapshot(")
    assert "qbLoadStatsHistory()" in body


def test_create_snapshot_handles_error_state(qb_js):
    body = _function_body(qb_js, "async function qbCreateStatsSnapshot(")
    assert "qb.stats.history.snapshot_error_prefix" in body


# ---------------------------------------------------------------------
# 3. qbRenderStatsHistory(): renders entries verbatim, empty-state
#    handling, no client-side re-aggregation
# ---------------------------------------------------------------------


def test_render_stats_history_function_present(qb_js):
    assert "function qbRenderStatsHistory(" in qb_js


def test_render_stats_history_uses_response_fields_directly(qb_js):
    """Renders each history entry's own created_at/stats.total fields
    -- never recomputes a count from raw question records (that would
    be re-implementing backend.question_bank.stats.compute_stats
    client-side, out of scope for this phase, same as Faz 2.9.11's own
    scope lock for the Statistics/Coverage card)."""
    body = _function_body(qb_js, "function qbRenderStatsHistory(")
    assert "created_at" in body
    assert "stats.total" in body
    assert "QB_LIST" not in body


def test_render_stats_history_handles_empty_state(qb_js):
    body = _function_body(qb_js, "function qbRenderStatsHistory(")
    assert "qb.stats.history.empty" in body


# ---------------------------------------------------------------------
# 4. Lifecycle wiring: qbInit() loads history, qbReapplyLanguage()
#    re-renders it (language switch must not require a re-fetch)
# ---------------------------------------------------------------------


def test_qb_init_loads_stats_history(qb_js):
    body = _function_body(qb_js, "function qbInit(")
    assert "qbLoadStatsHistory()" in body


def test_reapply_language_rerenders_history_without_refetching(qb_js):
    body = _function_body(qb_js, "function qbReapplyLanguage(")
    assert "qbRenderStatsHistory()" in body
    assert "qbLoadStatsHistory()" not in body


# ---------------------------------------------------------------------
# 5. i18n: qb.stats.history.* key parity + no missing referenced keys
# ---------------------------------------------------------------------


def test_qb_stats_history_key_parity_between_tr_and_en(frontend_html):
    script = _extract_script(frontend_html)
    en_all = _keys_in_literal(_extract_lang_dict_literal(script, "en"))
    tr_all = _keys_in_literal(_extract_lang_dict_literal(script, "tr"))
    en_hist = {k for k in en_all if k.startswith("qb.stats.history.")}
    tr_hist = {k for k in tr_all if k.startswith("qb.stats.history.")}
    assert en_hist, "expected at least one qb.stats.history.* EN key"
    assert en_hist == tr_hist, (
        f"qb.stats.history.* key parity broken -- only in en: {sorted(en_hist - tr_hist)}, "
        f"only in tr: {sorted(tr_hist - en_hist)}"
    )


def test_qb_stats_history_values_actually_translated(frontend_html):
    script = _extract_script(frontend_html)
    en_literal = _extract_lang_dict_literal(script, "en")
    tr_literal = _extract_lang_dict_literal(script, "tr")

    def _values(literal):
        pattern = r"'(qb\.stats\.history\.[a-zA-Z0-9_.]+)':\s*'([^']*)'"
        return dict(re.findall(pattern, literal))

    en_values = _values(en_literal)
    tr_values = _values(tr_literal)
    assert en_values, "no qb.stats.history.* key/value pairs extracted"
    assert en_values.keys() == tr_values.keys()
    identical = {k for k in en_values if en_values[k] == tr_values[k]}
    assert not identical, (
        f"untranslated (identical TR/EN) qb.stats.history.* values: {sorted(identical)}"
    )


def test_no_qb_stats_history_t_call_references_a_missing_key(frontend_html):
    """Every t('qb.stats.history....') call anywhere in the QB section
    must resolve to a key that actually exists in both I18N.en and
    I18N.tr."""
    qb_js = _qb_section_text(frontend_html)
    referenced = set(re.findall(r"t\('(qb\.stats\.history\.[a-zA-Z0-9_.]+)'\)", qb_js))
    assert referenced, "expected at least one t('qb.stats.history....') call in the QB section"

    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))

    missing_en = referenced - en_keys
    missing_tr = referenced - tr_keys
    assert not missing_en, f"referenced but missing from EN I18N: {sorted(missing_en)}"
    assert not missing_tr, f"referenced but missing from TR I18N: {sorted(missing_tr)}"


def test_qb_stats_history_required_keys_present(frontend_html):
    required = (
        "qb.stats.history.title",
        "qb.stats.history.sub",
        "qb.stats.history.snapshot_button",
        "qb.stats.history.refresh_button",
        "qb.stats.history.loading",
        "qb.stats.history.empty",
        "qb.stats.history.error_prefix",
        "qb.stats.history.snapshot_error_prefix",
        "qb.stats.history.col_taken_at",
        "qb.stats.history.col_total",
    )
    script = _extract_script(frontend_html)
    en_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "en")))
    tr_keys = set(_keys_in_literal(_extract_lang_dict_literal(script, "tr")))
    for key in required:
        assert key in en_keys, f"missing required EN key: {key}"
        assert key in tr_keys, f"missing required TR key: {key}"


# ---------------------------------------------------------------------
# 6. Faz 2.9.10/2.9.11 regression -- existing Statistics/Coverage card
#    and its i18n keys are untouched by this phase
# ---------------------------------------------------------------------


def test_existing_stats_card_still_present(frontend_html):
    assert 'data-i18n="qb.stats.title"' in frontend_html
    assert 'id="qb-stats-body"' in frontend_html
    assert "qbLoadStats()" in frontend_html


def test_existing_stats_breakdown_definition_unaffected(qb_js):
    assert "QB_STATS_BREAKDOWNS" in qb_js
    start = qb_js.index("QB_STATS_BREAKDOWNS")
    breakdowns_block = qb_js[start:qb_js.index("];", start)]
    for key in ("by_validation_status", "by_category", "by_difficulty", "by_question_type"):
        assert f"'{key}'" in breakdowns_block


# ---------------------------------------------------------------------
# 7. No charting library introduced by this phase
# ---------------------------------------------------------------------


def test_no_charting_library_referenced_anywhere_in_frontend(frontend_html):
    """Faz 2.9.12's Trend/History panel is a plain HTML table, per its
    own explicit scope lock (see the JS section's comment above
    QB_STATS_HISTORY) -- no chart/graphing library script tag or
    import is introduced anywhere in the file."""
    lowered = frontend_html.lower()
    forbidden_markers = (
        "chart.js", "chartjs", "cdn.jsdelivr.net/npm/chart",
        "recharts", "d3.min.js", "d3.v", "plotly", "highcharts",
        "apexcharts", "echarts",
    )
    for marker in forbidden_markers:
        assert marker not in lowered, f"unexpected charting library reference found: {marker}"


# ---------------------------------------------------------------------
# 8. JS syntax validity (whole <script> block)
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
