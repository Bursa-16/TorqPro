#!/usr/bin/env node
'use strict';
/*
 * Faz 2.6.8 -- TR/EN i18n foundation regression harness.
 *
 * Zero external dependencies (no npm packages, no jsdom, no browser)
 * -- matches this repo's existing "no framework" constraint for the
 * frontend and keeps this test infrastructure trivially reviewable.
 * Node's built-in `vm` module runs the *actual* i18n/Friction
 * Condition declarations extracted live from frontend/index.html
 * (never a committed copy, so this can't silently drift from the
 * real source) against a small hand-built DOM/localStorage stub.
 *
 * Invoked via `node tests/js/run_i18n_tests.js` from the repo root,
 * or indirectly via tests/test_faz2_6_8_friction_condition_i18n.py.
 * Exit code 0 = all assertions passed; non-zero = at least one
 * failure (details printed to stdout).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND_PATH = path.join(REPO_ROOT, 'frontend', 'index.html');

// ---------------------------------------------------------------
// Extraction: pull only the named top-level declarations out of the
// single <script> block by brace/paren counting. This intentionally
// avoids executing unrelated legacy app code (login, showPage, the
// version-fetch IIFE, etc.) that would need a much larger DOM stub
// to run safely.
// ---------------------------------------------------------------
function extractScript(html) {
  const m = /<script>([\s\S]*?)<\/script>/.exec(html);
  if (!m) throw new Error('no <script> block found in frontend/index.html');
  return m[1];
}

function extractConstDecl(script, name) {
  const re = new RegExp('\\b(?:const|let)\\s+' + name + '\\s*=');
  const m = re.exec(script);
  if (!m) throw new Error('declaration not found: ' + name);
  let i = script.indexOf('=', m.index);
  let depth = 0;
  let started = false;
  let j = i;
  for (; j < script.length; j++) {
    const c = script[j];
    if (c === '{' || c === '[' || c === '(') { depth++; started = true; }
    else if (c === '}' || c === ']' || c === ')') { depth--; }
    else if (c === ';' && depth === 0) break;
  }
  return script.slice(m.index, j + 1);
}

function extractFunctionDecl(script, name) {
  const re = new RegExp('\\bfunction\\s+' + name + '\\s*\\(');
  const m = re.exec(script);
  if (!m) throw new Error('function not found: ' + name);
  const braceStart = script.indexOf('{', m.index);
  let depth = 0;
  let j = braceStart;
  for (; j < script.length; j++) {
    const c = script[j];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) break; }
  }
  return script.slice(m.index, j + 1);
}

const CONST_NAMES = [
  'I18N', 'FC_ENUM_LABELS', 'CURRENT_LANG',
  'FC_LIST', 'FC_SELECTED_ID', 'FC_COMPARE_ID', 'FC_REQUEST_SEQ', 'FC_LAST_REPORT',
  'N01391',
];
// These are mutable workspace state in the real frontend (declared
// with `let` there -- and stay `let` in frontend/index.html; this
// list only controls how the *in-memory test copy* is rewritten,
// see buildExtractedSource). vm.createContext does not expose
// top-level let/const bindings as context properties, so external
// test code assigning e.g. ctx.context.FC_LAST_REPORT = report would
// silently create an unrelated property instead of reaching the
// binding setLanguage()/fcRender*() actually close over. Rewriting
// just these five to `var` for the test harness's own copy makes
// external assignment and internal closures observe the same
// binding, which is required to test "language switch re-renders
// already-loaded content" realistically.
const MUTABLE_STATE_NAMES = ['FC_LIST', 'FC_SELECTED_ID', 'FC_COMPARE_ID', 'FC_REQUEST_SEQ', 'FC_LAST_REPORT'];
const FUNCTION_NAMES = [
  't', 'fcLabel', 'applyStaticTranslations', 'setLanguage',
  'fcEsc', 'fcEscRaw', 'fcFmtNum', 'fcFmtLabel', 'fcCountLabel',
  'fcPopulateFilters', 'fcGroupOf', 'fcRenderList', 'fcRenderCompareOptions',
  'fcRenderOverview', 'fcRenderRangeViz', 'fcRenderReadiness',
  'fcWarningSeverity', 'fcRenderWarnings', 'fcRenderComparison', 'fcRenderReport',
  'n01391Hesapla',
];

function extractStatementAfter(script, anchorRegex, statementRegex) {
  const anchor = anchorRegex.exec(script);
  if (!anchor) throw new Error('anchor not found: ' + anchorRegex);
  const rest = script.slice(anchor.index + anchor[0].length);
  const m = statementRegex.exec(rest);
  if (!m) throw new Error('statement not found after anchor: ' + statementRegex);
  return m[0];
}

// Rewrites only a *leading* `let NAME =` / `const NAME =` to
// `var NAME =` -- test-copy-only, see MUTABLE_STATE_NAMES above.
// frontend/index.html itself is never touched by this function; it
// is read-only input here.
function toVarDecl(declText, name) {
  const re = new RegExp('^(const|let)(\\s+' + name + '\\s*=)');
  if (!re.test(declText)) throw new Error('expected declaration of ' + name + ' to rewrite to var, got: ' + declText.slice(0, 60));
  return declText.replace(re, 'var$2');
}

function buildExtractedSource() {
  const html = fs.readFileSync(FRONTEND_PATH, 'utf-8');
  const script = extractScript(html);
  const parts = [];
  for (const n of CONST_NAMES) {
    let decl = extractConstDecl(script, n);
    if (MUTABLE_STATE_NAMES.includes(n)) decl = toVarDecl(decl, n);
    parts.push(decl);
    if (n === 'CURRENT_LANG') {
      // `let CURRENT_LANG = ...;` is immediately followed by a
      // guard resetting unknown/garbage persisted values to 'tr' --
      // both statements must travel together.
      parts.push(extractStatementAfter(
        script,
        /let\s+CURRENT_LANG\s*=[^;]*;/,
        /^\s*if\s*\(!I18N\[CURRENT_LANG\]\)\s*CURRENT_LANG\s*=\s*'tr';/
      ));
    }
  }
  for (const n of FUNCTION_NAMES) parts.push(extractFunctionDecl(script, n));
  // Node's vm module does not expose top-level `let`/`const` bindings
  // as properties of the context object (only `function`/`var`
  // declarations are). This accessor is test-only scaffolding -- it
  // is appended here, never part of the real frontend/index.html --
  // so assertions can read the live CURRENT_LANG value; the extracted
  // production functions (t/fcLabel/setLanguage/...) already close
  // over the real binding correctly regardless of this.
  parts.push('function __getCurrentLang() { return CURRENT_LANG; }');
  return { source: parts.join('\n\n'), rawHtml: html };
}

// ---------------------------------------------------------------
// Minimal DOM / localStorage stubs -- only what the extracted code
// actually touches (see the getElementById/querySelectorAll id and
// selector list this harness was built against).
// ---------------------------------------------------------------
function makeElement(id) {
  return {
    id: id,
    _text: '',
    _placeholder: '',
    _html: '',
    _attrs: {},
    style: {},
    classList: { toggle() {}, add() {}, remove() {} },
    set textContent(v) { this._text = String(v); },
    get textContent() { return this._text; },
    set innerHTML(v) { this._html = String(v); },
    get innerHTML() { return this._html; },
    set placeholder(v) { this._placeholder = String(v); },
    get placeholder() { return this._placeholder; },
    value: '',
    getAttribute(name) { return this._attrs[name] || null; },
    setAttribute(name, v) { this._attrs[name] = v; },
  };
}

function makeLocalStorage(initial) {
  const store = new Map(Object.entries(initial || {}));
  return {
    getItem(k) { return store.has(k) ? store.get(k) : null; },
    setItem(k, v) { store.set(k, String(v)); },
    removeItem(k) { store.delete(k); },
    _dump() { return Object.fromEntries(store); },
  };
}

// data-i18n / data-i18n-placeholder / .lang-btn stub registries are
// built from small synthetic elements carrying the *real* keys
// scraped out of the actual page markup, so the harness stays
// truthful to what's really in frontend/index.html rather than a
// hand-duplicated guess.
function scrapeDataI18nKeys(rawHtml, attr) {
  const re = new RegExp(attr + '="([a-zA-Z0-9_.]+)"', 'g');
  const keys = [];
  let m;
  while ((m = re.exec(rawHtml))) keys.push(m[1]);
  return keys;
}

function buildDom(rawHtml, byId) {
  const dataI18nEls = scrapeDataI18nKeys(rawHtml, 'data-i18n').map((key) => {
    const el = makeElement(null);
    el.setAttribute('data-i18n', key);
    return el;
  });
  const placeholderEls = scrapeDataI18nKeys(rawHtml, 'data-i18n-placeholder').map((key) => {
    const el = makeElement(null);
    el.setAttribute('data-i18n-placeholder', key);
    return el;
  });
  const langBtnTr = makeElement('lang-btn-tr');
  langBtnTr.setAttribute('data-lang', 'tr');
  const langBtnEn = makeElement('lang-btn-en');
  langBtnEn.setAttribute('data-lang', 'en');
  const langBtns = [langBtnTr, langBtnEn];

  const document_ = {
    _byId: byId,
    _dataI18nEls: dataI18nEls,
    _placeholderEls: placeholderEls,
    _langBtns: langBtns,
    getElementById(id) {
      if (!(id in this._byId)) this._byId[id] = makeElement(id);
      return this._byId[id];
    },
    querySelectorAll(selector) {
      if (selector === '[data-i18n]') return dataI18nEls;
      if (selector === '[data-i18n-placeholder]') return placeholderEls;
      if (selector === '.lang-btn') return langBtns;
      return [];
    },
    addEventListener() { /* no-op: DOMContentLoaded is never fired by this harness */ },
  };
  return document_;
}

// ---------------------------------------------------------------
// Assertion bookkeeping
// ---------------------------------------------------------------
let pass = 0;
let fail = 0;
const failures = [];
function check(name, cond) {
  if (cond) { pass++; }
  else { fail++; failures.push(name); console.log('FAIL: ' + name); }
}
function checkEqual(name, actual, expected) {
  check(name + ' (got ' + JSON.stringify(actual) + ', want ' + JSON.stringify(expected) + ')', actual === expected);
}

// ---------------------------------------------------------------
// Build a context: evaluates the extracted declarations fresh in an
// isolated vm context with its own document/localStorage, so each
// scenario starts from a clean slate (mirrors a fresh page load).
// ---------------------------------------------------------------
function newContext(extractedSource, rawHtml, localStorageSeed) {
  const byId = {};
  const localStorageStub = makeLocalStorage(localStorageSeed);
  const documentStub = buildDom(rawHtml, byId);
  const sandbox = {
    document: documentStub,
    localStorage: localStorageStub,
    console: console,
    apiRequest: () => { throw new Error('apiRequest should not be called by this harness'); },
    downloadText: () => { throw new Error('downloadText should not be called by this harness'); },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'fc_i18n_extracted.js' });
  return { context, byId, localStorageStub, documentStub };
}

function getByI18nKey(ctx, key) {
  return ctx.documentStub._dataI18nEls.find((el) => el.getAttribute('data-i18n') === key);
}
function getPlaceholderByKey(ctx, key) {
  return ctx.documentStub._placeholderEls.find((el) => el.getAttribute('data-i18n-placeholder') === key);
}

// A report object shaped exactly like
// FrictionConditionReportSection.to_dict() in
// backend/calculation_engine/friction_report.py, used to exercise
// the dynamic-content render functions without a live backend.
function fakeReport() {
  return {
    friction_condition_id: 'FC-TEST-001',
    coating_reference: 'COAT-TEST',
    lubricant_reference: '',
    friction_model: 'combined_or_unspecified',
    overall_friction_coefficient_minimum: 0.10,
    overall_friction_coefficient_nominal_estimate: 0.15,
    overall_friction_coefficient_maximum: 0.20,
    nominal_policy: 'arithmetic midpoint of reference range',
    source: {
      source_reference: 'Test Table 1',
      source_type: 'standard',
      source_page_or_table: 'Table 1',
      verification_status: 'reference_only',
      applicability: 'general',
      engineering_notes: '',
      record_checksum: 'abc123',
      data_version: '1.0.0',
    },
    readiness: {
      recommendation_level: 'comparison_only',
      available_capabilities: ['reference_comparison'],
      blocked_capabilities: ['torque_recommendation', 'production_approval'],
      blocking_reasons: [],
      required_missing_data: ['verified_mu_thread'],
      torque_calculation_mode: 'mode_a_combined_estimate',
      torque_blocking_reasons: [],
    },
    engineering_warnings: ['Thread and bearing friction are not separately verified.'],
    safety_labels: ['Reference Only'],
    intended_use: null,
    comparison: null,
    report_generated_at: '2026-07-24T00:00:00Z',
    application_version: '2.6.8',
  };
}

// =================================================================
function main() {
  const { source: extractedSource, rawHtml } = buildExtractedSource();

  // ---- 1. Default language is Turkish (fresh load, empty storage) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('default language is tr', ctx.context.__getCurrentLang(), 'tr');
  }

  // ---- 2. localStorage persistence on initial load (key torqpro_lang) ----
  {
    const ctx = newContext(extractedSource, rawHtml, { torqpro_lang: 'en' });
    checkEqual('CURRENT_LANG initializes from persisted torqpro_lang=en', ctx.context.__getCurrentLang(), 'en');
  }
  {
    const ctx = newContext(extractedSource, rawHtml, { torqpro_lang: 'tr' });
    checkEqual('CURRENT_LANG initializes from persisted torqpro_lang=tr', ctx.context.__getCurrentLang(), 'tr');
  }
  {
    // Unknown/garbage persisted value must fall back to tr, not crash.
    const ctx = newContext(extractedSource, rawHtml, { torqpro_lang: 'xx-not-a-real-lang' });
    checkEqual('unknown persisted language falls back to tr', ctx.context.__getCurrentLang(), 'tr');
  }

  // ---- 3. TR -> EN runtime switch (no reload, in the same context) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('starts tr', ctx.context.__getCurrentLang(), 'tr');
    const titleEl = getByI18nKey(ctx, 'fc.page_title');
    check('fc.page_title element exists in scraped markup', !!titleEl);
    ctx.context.setLanguage('en');
    checkEqual('CURRENT_LANG is en after setLanguage(en)', ctx.context.__getCurrentLang(), 'en');
    checkEqual('localStorage updated to en', ctx.localStorageStub.getItem('torqpro_lang'), 'en');
    checkEqual('fc.page_title text switched to English', titleEl.textContent, 'Friction Condition');
    const searchPh = getPlaceholderByKey(ctx, 'fc.search_placeholder');
    check('fc.search_placeholder element exists', !!searchPh);
    checkEqual('search placeholder switched to English', searchPh.placeholder, 'Search by ID, coating or lubricant reference...');
  }

  // ---- 4. EN -> TR runtime switch, same context (round trip) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.setLanguage('en');
    const titleEl = getByI18nKey(ctx, 'fc.page_title');
    checkEqual('title is English after switching to en', titleEl.textContent, 'Friction Condition');
    ctx.context.setLanguage('tr');
    checkEqual('CURRENT_LANG back to tr', ctx.context.__getCurrentLang(), 'tr');
    checkEqual('localStorage updated back to tr', ctx.localStorageStub.getItem('torqpro_lang'), 'tr');
    checkEqual('title switched back to Turkish', titleEl.textContent, 'Yüzey Sürtünme Koşulu');
    const searchPh = getPlaceholderByKey(ctx, 'fc.search_placeholder');
    checkEqual('search placeholder switched back to Turkish', searchPh.placeholder, 'Kimlik, kaplama veya yağlayıcı referansına göre ara...');
  }

  // ---- 5. Sidebar label + subtitle + banner translate correctly ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const sidebarEl = getByI18nKey(ctx, 'sidebar.frictioncondition');
    const subtitleEl = getByI18nKey(ctx, 'fc.page_subtitle');
    check('sidebar element exists', !!sidebarEl);
    check('subtitle element exists', !!subtitleEl);
    ctx.context.applyStaticTranslations();
    checkEqual('sidebar label is tr by default', sidebarEl.textContent, 'Yüzey Sürtünme Koşulu');
    checkEqual('subtitle is the required tr string', subtitleEl.textContent,
      'Kaplama, yağlama ve temas yüzeylerine bağlı sürtünme referans verileri');
    ctx.context.setLanguage('en');
    checkEqual('sidebar label switches to en', sidebarEl.textContent, 'Friction Condition');
  }

  // ---- 6. Language-switch buttons reflect active language ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.applyStaticTranslations();
    // classList.toggle is a no-op stub (we don't track calls), but we
    // can still confirm applyStaticTranslations runs over both
    // buttons without throwing, and that the active language is
    // correctly tracked in CURRENT_LANG (checked above). Presence of
    // both buttons in the scrape is the structural guarantee.
    checkEqual('exactly two lang buttons (tr, en)', ctx.documentStub._langBtns.length, 2);
  }

  // ---- 7. Dynamic Friction Condition content translates on switch ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const report = fakeReport();
    ctx.context.FC_LAST_REPORT = report;
    ctx.context.fcRenderOverview(report);
    const overviewEl = ctx.byId['fc-overview'];
    check('overview shows Turkish field label by default', overviewEl.innerHTML.indexOf('Kaplama') !== -1);
    ctx.context.setLanguage('en');
    // setLanguage re-renders FC_LAST_REPORT automatically.
    check('overview shows English field label after switch', overviewEl.innerHTML.indexOf('>Coating<') !== -1);
    check('overview no longer shows Turkish field label', overviewEl.innerHTML.indexOf('>Kaplama<') === -1);
  }

  // ---- 8. Enum display labels are translated (verification_status) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('reference_only label in tr', ctx.context.fcLabel('reference_only'), 'Yalnızca Referans');
    ctx.context.setLanguage('en');
    checkEqual('reference_only label in en', ctx.context.fcLabel('reference_only'), 'Reference Only');
  }

  // ---- 9. Recommendation level / capability / calc-mode / comparison
  //         relation / classification enum coverage ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.setLanguage('en');
    const enPairs = [
      ['warnings_only', 'Warnings only'], ['comparison_only', 'Comparison only'],
      ['engineering_recommendation_ready', 'Engineering recommendation ready'],
      ['production_recommendation_ready', 'Production recommendation ready'],
      ['reference_comparison', 'Reference comparison'], ['torque_sensitivity', 'Torque sensitivity'],
      ['torque_recommendation', 'Torque recommendation'], ['lubricant_recommendation', 'Lubricant recommendation'],
      ['coating_recommendation', 'Coating recommendation'], ['production_approval', 'Production approval'],
      ['coating_based', 'Coating-based'], ['lubricant_based', 'Lubricant-based'],
      ['coating_and_lubricant_based', 'Coating and lubricant-based'], ['unclassified', 'Unclassified'],
      ['mode_a_combined_estimate', 'Mode A — combined estimate'], ['mode_b_separated_model', 'Mode B — separated model'],
      ['blocked', 'Blocked'],
      ['not_comparable', 'Not comparable'], ['identical', 'Identical'], ['a_lower', 'A lower'],
      ['b_lower', 'B lower'], ['overlapping', 'Overlapping'], ['equal_width', 'Equal width'],
      ['a_narrower', 'A narrower'], ['b_narrower', 'B narrower'],
      ['standard', 'Standard'], ['textbook', 'Textbook'], ['verified', 'Verified'],
      ['unverified', 'Unverified'], ['restricted_legacy', 'Restricted / Legacy'],
      ['combined_or_unspecified', 'Combined or unspecified'],
    ];
    for (const [key, expected] of enPairs) {
      checkEqual('en enum label: ' + key, ctx.context.fcLabel(key), expected);
    }
    ctx.context.setLanguage('tr');
    // Spot-check a handful in tr too (not exhaustive re-list).
    checkEqual('tr enum label: coating_based', ctx.context.fcLabel('coating_based'), 'Kaplama tabanlı');
    checkEqual('tr enum label: blocked', ctx.context.fcLabel('blocked'), 'Engellendi');
    checkEqual('tr enum label: not_comparable', ctx.context.fcLabel('not_comparable'), 'Karşılaştırılamaz');
  }

  // ---- 10. Unknown enum value falls back safely, both languages ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('unknown enum value falls back (tr)', ctx.context.fcLabel('totally_unknown_value'), 'totally unknown value');
    ctx.context.setLanguage('en');
    checkEqual('unknown enum value falls back (en)', ctx.context.fcLabel('totally_unknown_value'), 'totally unknown value');
    checkEqual('empty value renders em dash', ctx.context.fcLabel(''), '—');
    checkEqual('null value renders em dash', ctx.context.fcLabel(null), '—');
  }

  // ---- 11. Language switching does not refetch the workspace ----
  {
    // setLanguage's own source must never call apiRequest -- it only
    // ever calls fcRenderList()/fcRender*(FC_LAST_REPORT) against
    // state already held in memory. apiRequest is stubbed to throw,
    // so if setLanguage ever called it this would fail immediately.
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.FC_LIST = [];
    ctx.context.FC_LAST_REPORT = fakeReport();
    let threw = false;
    try { ctx.context.setLanguage('en'); } catch (e) { threw = true; }
    check('setLanguage never calls apiRequest (no refetch)', !threw);
    // Static source-level guard too, in case FC_LIST/FC_LAST_REPORT
    // state happened not to exercise every branch above.
    const setLanguageSrc = extractFunctionDecl(extractedSource, 'setLanguage');
    check('setLanguage source contains no apiRequest call', setLanguageSrc.indexOf('apiRequest(') === -1);
    check('setLanguage source contains no location.reload', setLanguageSrc.indexOf('location.reload') === -1);
  }

  // ---- 12. API routes / JSON keys / enum values unchanged ----
  {
    // The frontend must still call the exact same endpoints with the
    // exact same JSON field names as before i18n was introduced --
    // i18n must only ever touch *display* text.
    check('list endpoint path unchanged', rawHtml.indexOf("apiRequest('/api/friction-condition')") !== -1);
    check('report-preview endpoint path unchanged', rawHtml.indexOf("'/api/friction-condition/report-preview'") !== -1);
    check('friction_intended_use JSON key unchanged', rawHtml.indexOf('payload.friction_intended_use') !== -1);
    check('friction_condition_id JSON key unchanged', rawHtml.indexOf('friction_condition_id: FC_SELECTED_ID') !== -1);
    check('compare_with_friction_condition_id JSON key unchanged',
      rawHtml.indexOf('payload.compare_with_friction_condition_id') !== -1);
    // Option *values* (sent to the API) must remain the raw enum
    // keys -- only the visible option *text* may be translated.
    check('intended-use option values are raw enum keys, unchanged',
      /<option value="reference_comparison" data-i18n="fc\.intended_use_reference_comparison">/.test(rawHtml) &&
      /<option value="engineering_calculation" data-i18n="fc\.intended_use_engineering_calculation">/.test(rawHtml) &&
      /<option value="production_release" data-i18n="fc\.intended_use_production_release">/.test(rawHtml));
  }

  // ---- 13. Backend free-text warnings remain untranslated (documented limitation) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const report = fakeReport();
    ctx.context.FC_LAST_REPORT = report;
    ctx.context.fcRenderWarnings(report);
    const warnEl = ctx.byId['fc-warnings'];
    ctx.context.setLanguage('en');
    ctx.context.fcRenderWarnings(report);
    const enHtml = warnEl.innerHTML;
    ctx.context.setLanguage('tr');
    ctx.context.fcRenderWarnings(report);
    const trHtml = warnEl.innerHTML;
    check('backend free-text warning sentence is identical regardless of language',
      enHtml.indexOf('Thread and bearing friction are not separately verified.') !== -1 &&
      trHtml.indexOf('Thread and bearing friction are not separately verified.') !== -1);
  }

  // ================================================================
  // Faz 2.7.0 -- global i18n foundation (login / topbar / sidebar /
  // dashboard). Friction Condition module coverage above (tests
  // 1-13) is left untouched; these tests extend the same harness to
  // the first batch of app-wide surfaces migrated in this phase.
  // ================================================================

  // ---- 14. Login overlay: TR default + EN switch (static markup) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const subtitleEl = getByI18nKey(ctx, 'login.subtitle');
    const userLabelEl = getByI18nKey(ctx, 'login.username_label');
    const submitEl = getByI18nKey(ctx, 'login.submit');
    const userPh = getPlaceholderByKey(ctx, 'login.username_placeholder');
    check('login.subtitle element exists', !!subtitleEl);
    check('login.username_label element exists', !!userLabelEl);
    check('login.submit element exists', !!submitEl);
    ctx.context.applyStaticTranslations();
    checkEqual('login subtitle is tr by default', subtitleEl.textContent, 'Bağlantı Elemanları Analiz Yazılımı');
    checkEqual('login submit button is tr by default', submitEl.textContent, 'Giriş Yap');
    ctx.context.setLanguage('en');
    checkEqual('login subtitle switches to en', subtitleEl.textContent, 'Fastener Analysis Software');
    checkEqual('login username label switches to en', userLabelEl.textContent, 'Username');
    checkEqual('login submit button switches to en', submitEl.textContent, 'Sign In');
    checkEqual('login username placeholder switches to en', userPh.placeholder, 'Your username');
  }

  // ---- 15. Topbar nav items + system-active pill translate ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const dashEl = getByI18nKey(ctx, 'topbar.dashboard');
    const reportEl = getByI18nKey(ctx, 'topbar.report');
    const activeEl = getByI18nKey(ctx, 'topbar.system_active');
    check('topbar.dashboard element exists', !!dashEl);
    check('topbar.report element exists', !!reportEl);
    check('topbar.system_active element exists', !!activeEl);
    ctx.context.applyStaticTranslations();
    checkEqual('topbar report label tr by default', reportEl.textContent, 'Rapor');
    ctx.context.setLanguage('en');
    checkEqual('topbar report label switches to en', reportEl.textContent, 'Report');
    checkEqual('topbar system-active pill switches to en', activeEl.textContent, '● System Active');
  }

  // ---- 16. Every sidebar menu item translates TR <-> EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    // key -> [expected tr text, expected en text]
    const sidebarExpected = {
      'sidebar.dashboard': ['Dashboard', 'Dashboard'],
      'sidebar.sample_torque_study': ['Örnek Tork Çalışması', 'Sample Torque Study'],
      'sidebar.torque_calc': ['Tork Hesap', 'Torque Calc'],
      'sidebar.advanced_analysis': ['Gelişmiş Analiz', 'Advanced Analysis'],
      'sidebar.checklist': ['Check-List', 'Check-List'],
      'sidebar.capability': ['Cm/Cmk Yetenek', 'Cp/Cpk Capability'],
      'sidebar.tool_tracking': ['Sıkıcı Takip', 'Tool Tracking'],
      'sidebar.problem_management': ['Problem Yönetimi', 'Problem Management'],
      'sidebar.oem_norm_query': ['OEM Norm Sorgu', 'OEM Norm Query'],
      'sidebar.norm_guide': ['Norm Rehberi', 'Norm Guide'],
      'sidebar.fmea_catalog': ['FMEA Kataloğu', 'FMEA Catalog'],
      'sidebar.admin_panel': ['Yönetici Paneli', 'Admin Panel'],
      'sidebar.setup_wizard': ['Kurulum Sihirbazı', 'Setup Wizard'],
      'sidebar.dns_check': ['Domain & DNS Kontrolü', 'Domain & DNS Check'],
      'sidebar.secure_deploy': ['Güvenli Yayın', 'Secure Deploy'],
      'sidebar.runtime_health': ['Canlılık Durumu', 'Runtime Health'],
      'sidebar.mobile_access': ['Mobil Erişim', 'Mobile Access'],
      'sidebar.deployment_profile': ['Kurulum Profili', 'Deployment Profile'],
      'sidebar.data_migration': ['Veri Taşıma', 'Data Migration'],
      'sidebar.system_diagnostics': ['Sistem Tanılama', 'System Diagnostics'],
      'sidebar.org_settings': ['Kurum Ayarları', 'Organization Settings'],
      'sidebar.license_mgmt': ['Lisans Yönetimi', 'License Management'],
      'sidebar.usage_summary': ['Kullanım Özeti', 'Usage Summary'],
      'sidebar.release_package': ['Proje Release Paketi', 'Project Release Package'],
      'sidebar.traceability_matrix': ['İzlenebilirlik Matrisi', 'Traceability Matrix'],
      'sidebar.projects': ['Projeler', 'Projects'],
      'sidebar.revisions': ['Hesap Revizyonları', 'Calculation Revisions'],
      'sidebar.approvals_pending': ['Onay Bekleyenler', 'Pending Approvals'],
      'sidebar.data_quality_gate': ['Veri Kalite Kapısı', 'Data Quality Gate'],
      'sidebar.golden_cases': ['Altın Senaryolar', 'Golden Cases'],
      'sidebar.release_cert': ['Sürüm Sertifikası', 'Release Certificate'],
      'sidebar.active_data_versions': ['Aktif Veri Sürümleri', 'Active Data Versions'],
      'sidebar.data_upload_approval': ['Veri Yükleme & Onay', 'Data Upload & Approval'],
      'sidebar.calibration': ['Kalibrasyon', 'Calibration'],
      'sidebar.technical_validation': ['Teknik Doğrulama', 'Technical Validation'],
      'sidebar.generate_report': ['Rapor Üret', 'Generate Report'],
      'sidebar.archive': ['Arşiv', 'Archive'],
      'sidebar.secure_logout': ['Güvenli Çıkış', 'Secure Logout'],
    };
    ctx.context.applyStaticTranslations();
    for (const [key, [trText]] of Object.entries(sidebarExpected)) {
      const el = getByI18nKey(ctx, key);
      check('sidebar element exists for ' + key, !!el);
      if (el) checkEqual('sidebar tr text for ' + key, el.textContent, trText);
    }
    ctx.context.setLanguage('en');
    for (const [key, [, enText]] of Object.entries(sidebarExpected)) {
      const el = getByI18nKey(ctx, key);
      if (el) checkEqual('sidebar en text for ' + key, el.textContent, enText);
    }
  }

  // ---- 17. Dashboard: title, stat labels, table headers, statuses ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titleEl = getByI18nKey(ctx, 'dashboard.title');
    const thOpEl = getByI18nKey(ctx, 'dashboard.th_operation');
    const statusNokEl = getByI18nKey(ctx, 'dashboard.status_nok');
    const statusBorderlineEl = getByI18nKey(ctx, 'dashboard.status_borderline');
    check('dashboard.title element exists', !!titleEl);
    check('dashboard.th_operation element exists', !!thOpEl);
    ctx.context.applyStaticTranslations();
    checkEqual('dashboard title is tr by default', titleEl.textContent, 'Üretim Tork Kontrol Paneli');
    checkEqual('dashboard borderline status is tr by default', statusBorderlineEl.textContent, 'SINIRDA');
    ctx.context.setLanguage('en');
    checkEqual('dashboard title switches to en', titleEl.textContent, 'Production Torque Control Panel');
    checkEqual('dashboard operation header switches to en', thOpEl.textContent, 'Operation');
    checkEqual('dashboard NOK status stays "NOK" in en (technical status code)', statusNokEl.textContent, 'NOK');
    checkEqual('dashboard borderline status switches to en', statusBorderlineEl.textContent, 'BORDERLINE');
  }

  // ---- 18. localStorage persistence covers the whole app (not just FC) ----
  {
    const ctx = newContext(extractedSource, rawHtml, { torqpro_lang: 'en' });
    const titleEl = getByI18nKey(ctx, 'dashboard.title');
    const submitEl = getByI18nKey(ctx, 'login.submit');
    ctx.context.applyStaticTranslations();
    checkEqual('dashboard renders in en on load when torqpro_lang=en persisted', titleEl.textContent, 'Production Torque Control Panel');
    checkEqual('login renders in en on load when torqpro_lang=en persisted', submitEl.textContent, 'Sign In');
  }

  // ---- 19. Missing translation key: controlled fallback + warning ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const warnings = [];
    const origWarn = console.warn;
    console.warn = (...args) => { warnings.push(args.join(' ')); };
    let result;
    try {
      result = ctx.context.t('this.key.does.not.exist.anywhere');
    } finally {
      console.warn = origWarn;
    }
    checkEqual('unknown key falls back to the raw key string', result, 'this.key.does.not.exist.anywhere');
    check('a console warning was emitted for the missing key', warnings.length > 0);
  }

  // ---- 20. Technical standard codes are never altered by translation ----
  {
    // ISO 16047, VDI 2230, APQP, PPAP, Cp/Cpk, Pp/Ppk and OEM norm
    // codes must appear byte-identical regardless of active language.
    // Cm/Cmk (tr) / Cp/Cpk (en) is the one intentional locale-specific
    // exception (verified separately below) -- the raw statistical
    // notation itself is never mistranslated into prose.
    const ctx = newContext(extractedSource, rawHtml, {});
    const capEl = getByI18nKey(ctx, 'sidebar.capability');
    ctx.context.applyStaticTranslations();
    check('tr sidebar capability label contains "Cm/Cmk"', capEl.textContent.indexOf('Cm/Cmk') !== -1);
    ctx.context.setLanguage('en');
    check('en sidebar capability label contains "Cp/Cpk"', capEl.textContent.indexOf('Cp/Cpk') !== -1);
  }

  // ================================================================
  // Faz 2.7.1 -- Calculations & Production Validation pages
  // (n01391 / hizli / vdi / checklist / yetenek / calibration /
  // validation). Same harness pattern as Faz 2.7.0.
  // ================================================================

  // ---- 21. Page titles + subtitles: TR default, EN switch ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titles = {
      'n01391.title': ['Örnek Tork Çalışması', 'Sample Torque Study'], // startsWith check below
      'hizli.title': ['Teorik Tork Hesaplama', 'Theoretical Torque Calculation'],
      'vdi.title': ['Gelişmiş Bağlantı Analizi', 'Advanced Joint Analysis'],
      'checklist.title': ['Torklama Proses Check-List', 'Torque Process Check-List'],
      'yetenek.title': ['Cm / Cmk Makine Yetenek Analizi', 'Cm / Cmk Machine Capability Analysis'],
      'calibration.title': ['Kalibrasyon ve Referans Karşılaştırma', 'Calibration & Reference Comparison'],
      'validation.title': ['Teknik Doğrulama Paneli', 'Technical Validation Panel'],
    };
    ctx.context.applyStaticTranslations();
    for (const [key, [trText]] of Object.entries(titles)) {
      const el = getByI18nKey(ctx, key);
      check('page title element exists for ' + key, !!el);
      if (el) check('page title tr text starts correctly for ' + key, el.textContent.indexOf(trText) === 0);
    }
    ctx.context.setLanguage('en');
    for (const [key, [, enText]] of Object.entries(titles)) {
      const el = getByI18nKey(ctx, key);
      if (el) check('page title en text starts correctly for ' + key, el.textContent.indexOf(enText) === 0);
    }
  }

  // ---- 22. Form labels, buttons, table headers translate (sample across all 7 pages) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const fields = {
      'n01391.thread_size': ['Diş Ölçüsü', 'Thread Size'],
      'hizli.bolt_diameter': ['Cıvata Çapı', 'Bolt Diameter'],
      'hizli.calculate_btn': ['🔧 Hesapla', '🔧 Calculate'],
      'vdi.run_button': ['VDI 2230 Çalıştır', 'Run VDI 2230'],
      'checklist.evaluate_btn': ['📊 Değerlendir', '📊 Evaluate'],
      'checklist.chassis_part_no': ['Şase / Parça No', 'Chassis / Part No.'],
      'yetenek.nominal_torque': ['Nominal Tork (Nm)', 'Nominal Torque (Nm)'],
      'yetenek.calculate_btn': ['📈 Yetenek Hesapla', '📈 Calculate Capability'],
      'calibration.th_decision': ['Karar', 'Decision'],
      'calibration.save_btn': ['Kalibrasyon Kaydet', 'Save Calibration'],
      'validation.th_status': ['Durum', 'Status'],
      'validation.nut_proof_load': ['Somun Proof-Load', 'Nut Proof Load'],
    };
    ctx.context.applyStaticTranslations();
    for (const [key, [trText]] of Object.entries(fields)) {
      const el = getByI18nKey(ctx, key);
      check('field element exists for ' + key, !!el);
      if (el) checkEqual('field tr text for ' + key, el.textContent, trText);
    }
    ctx.context.setLanguage('en');
    for (const [key, [, enText]] of Object.entries(fields)) {
      const el = getByI18nKey(ctx, key);
      if (el) checkEqual('field en text for ' + key, el.textContent, enText);
    }
  }

  // ---- 23. Dropdown option text translates (technical values e.g. M6/M10/8.8/10.9 untouched) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const options = {
      'hizli.class_a_opt': ['A — ±%5 (Kritik güvenlik)', 'A — ±5% (Safety critical)'],
      'hizli.hole_type_blind': ['Kör delik', 'Blind hole'],
      'hizli.material_aluminum': ['Alüminyum', 'Aluminum'],
      'yetenek.manual_lsl_usl': ['Manuel LSL/USL', 'Manual LSL/USL'],
      'yetenek.analysis_cm': ['Cm / Cmk — Makine yeteneği', 'Cm / Cmk — Machine capability'],
    };
    ctx.context.applyStaticTranslations();
    for (const [key, [trText]] of Object.entries(options)) {
      const el = getByI18nKey(ctx, key);
      check('option element exists for ' + key, !!el);
      if (el) checkEqual('option tr text for ' + key, el.textContent, trText);
    }
    ctx.context.setLanguage('en');
    for (const [key, [, enText]] of Object.entries(options)) {
      const el = getByI18nKey(ctx, key);
      if (el) checkEqual('option en text for ' + key, el.textContent, enText);
    }
    // Technical values (thread sizes, strength classes) are raw <option> text
    // with NO data-i18n attribute -- confirming they are untouched by design.
    check('M10 bolt diameter option is untouched by i18n (no data-i18n)',
      /<option selected>M10<\/option>/.test(rawHtml));
    check('10.9 quality class option is untouched by i18n (no data-i18n)',
      /<option selected>10\.9<\/option>/.test(rawHtml));
  }

  // ---- 24. Placeholders translate (checklist operation/inspector, OEM limit fields) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const opPh = getPlaceholderByKey(ctx, 'checklist.operation_placeholder');
    const namePh = getPlaceholderByKey(ctx, 'checklist.name_placeholder');
    check('checklist operation placeholder element exists', !!opPh);
    check('checklist inspector name placeholder element exists', !!namePh);
    ctx.context.applyStaticTranslations();
    checkEqual('operation placeholder tr', opPh.placeholder, 'Ön süspansiyon travers');
    ctx.context.setLanguage('en');
    checkEqual('operation placeholder en', opPh.placeholder, 'Front suspension crossmember');
    checkEqual('inspector name placeholder en', namePh.placeholder, 'Full name');
  }

  // ---- 25. Empty-state / "enter parameters" messages translate on every calc page ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const emptyStates = {
      'n01391.select_parameters': ['Parametreleri seçin', 'Select parameters'],
      'hizli.enter_parameters': ['Parametreleri girin', 'Enter parameters'],
      'vdi.enter_parameters': ['Parametreleri girin', 'Enter parameters'],
      'yetenek.enter_measurements': ['Ölçümleri girin', 'Enter measurements'],
    };
    ctx.context.applyStaticTranslations();
    for (const [key, [trText]] of Object.entries(emptyStates)) {
      const el = getByI18nKey(ctx, key);
      check('empty-state element exists for ' + key, !!el);
      if (el) checkEqual('empty-state tr text for ' + key, el.textContent, trText);
    }
    ctx.context.setLanguage('en');
    for (const [key, [, enText]] of Object.entries(emptyStates)) {
      const el = getByI18nKey(ctx, key);
      if (el) checkEqual('empty-state en text for ' + key, el.textContent, enText);
    }
  }

  // ---- 26. Warning / info banners translate (mode notes, footer warnings) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const banners = {
      'hizli.mode_note': ['Bu mod diş ve yatak sürtünmesini ayrı hesaplayan mühendislik ön değerlendirmesidir. OEM seri üretim değeri için "OEM Norm Sorgu" veya "Örnek Tork Çalışması" modülünü kullanın.',
        'This mode is an engineering pre-assessment that calculates thread and bearing friction separately. Use "OEM Norm Query" or "Sample Torque Study" for an OEM production value.'],
      'validation.footer_warning': ['Doğrulanmış standart veya test raporu olmadan taslak veri seri üretim torku olarak kullanılmamalıdır.',
        'Draft data must not be used as a production torque value without a verified standard or test report.'],
    };
    ctx.context.applyStaticTranslations();
    for (const [key, [trText]] of Object.entries(banners)) {
      const el = getByI18nKey(ctx, key);
      check('banner element exists for ' + key, !!el);
      if (el) checkEqual('banner tr text for ' + key, el.textContent, trText);
    }
    ctx.context.setLanguage('en');
    for (const [key, [, enText]] of Object.entries(banners)) {
      const el = getByI18nKey(ctx, key);
      if (el) checkEqual('banner en text for ' + key, el.textContent, enText);
    }
  }

  // ---- 27. No stray English text visible in TR mode / Turkish text in EN mode
  //          for every scraped data-i18n[-placeholder] key in the Faz 2.7.1
  //          namespaces (n01391/hizli/vdi/checklist/yetenek/calibration/validation).
  //          A key "leaking" means t() returned the raw key itself (unresolved). ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const prefixes = ['n01391.', 'hizli.', 'vdi.', 'checklist.', 'yetenek.', 'calibration.', 'validation.'];
    const allI18nKeys = scrapeDataI18nKeys(rawHtml, 'data-i18n')
      .concat(scrapeDataI18nKeys(rawHtml, 'data-i18n-placeholder'));
    const scoped = [...new Set(allI18nKeys)].filter((k) => prefixes.some((p) => k.startsWith(p)));
    check('at least 150 Faz 2.7.1 keys were scraped from markup', scoped.length >= 150);
    let unresolvedTr = 0;
    let unresolvedEn = 0;
    for (const key of scoped) {
      if (ctx.context.t(key) === key) unresolvedTr++;
    }
    ctx.context.setLanguage('en');
    for (const key of scoped) {
      if (ctx.context.t(key) === key) unresolvedEn++;
    }
    checkEqual('no unresolved (raw-key-fallback) Faz 2.7.1 keys in tr', unresolvedTr, 0);
    checkEqual('no unresolved (raw-key-fallback) Faz 2.7.1 keys in en', unresolvedEn, 0);
  }

  // ---- 28. Language persists across page navigation (showPage does not reset it) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.setLanguage('en');
    // showPage() is not part of the extracted source (it manipulates
    // .page/.sidebar-item classList, orthogonal to i18n and outside
    // this harness's DOM stub) -- what matters for i18n is that
    // CURRENT_LANG / localStorage are untouched by navigation, which
    // showPage() never writes to (verified statically below) and
    // that re-running applyStaticTranslations after a page swap
    // still renders in the active language.
    check('showPage() function does not reference torqpro_lang or CURRENT_LANG',
      (function () {
        const m = /function showPage\([^)]*\)\s*\{[\s\S]*?\n\}/.exec(rawHtml.match(/<script>([\s\S]*)<\/script>/)[1]);
        return !!m && m[0].indexOf('torqpro_lang') === -1 && m[0].indexOf('CURRENT_LANG') === -1;
      })());
    ctx.context.applyStaticTranslations();
    const hizliTitleEl = getByI18nKey(ctx, 'hizli.title');
    checkEqual('language still en after simulated navigation', hizliTitleEl.textContent, 'Theoretical Torque Calculation');
    checkEqual('localStorage still en after simulated navigation', ctx.localStorageStub.getItem('torqpro_lang'), 'en');
  }

  console.log('\n' + pass + ' passed, ' + fail + ' failed.');
  if (fail > 0) {
    console.log('Failures: ' + failures.join('; '));
    process.exit(1);
  }
  process.exit(0);
}

main();
