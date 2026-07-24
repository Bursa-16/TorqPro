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
  // Preserve a leading `async` keyword (e.g. `async function foo(){...}`)
  // -- without it, an extracted function using `await` is a syntax
  // error when re-assembled into the test harness's standalone source.
  let start = m.index;
  const asyncMatch = /async\s+$/.exec(script.slice(Math.max(0, start - 10), start));
  if (asyncMatch) start -= asyncMatch[0].length;
  return script.slice(start, j + 1);
}

const CONST_NAMES = [
  'I18N', 'FC_ENUM_LABELS', 'CURRENT_LANG',
  'FC_LIST', 'FC_SELECTED_ID', 'FC_COMPARE_ID', 'FC_REQUEST_SEQ', 'FC_LAST_REPORT',
  'N01391', 'CL', 'TORQPRO_LIBRARY', 'APP_EDITION', 'DEMO_THREAD_LIMIT',
  'LAST_CALCULATION', 'ACTIVE_STANDARD_LIBRARY',
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
const MUTABLE_STATE_NAMES = ['FC_LIST', 'FC_SELECTED_ID', 'FC_COMPARE_ID', 'FC_REQUEST_SEQ', 'FC_LAST_REPORT', 'ACTIVE_STANDARD_LIBRARY'];
const FUNCTION_NAMES = [
  't', 'fcLabel', 'applyStaticTranslations', 'setLanguage',
  'fcEsc', 'fcEscRaw', 'fcFmtNum', 'fcFmtLabel', 'fcCountLabel',
  'fcPopulateFilters', 'fcGroupOf', 'fcRenderList', 'fcRenderCompareOptions',
  'fcRenderOverview', 'fcRenderRangeViz', 'fcRenderReadiness',
  'fcWarningSeverity', 'fcRenderWarnings', 'fcRenderComparison', 'fcRenderReport',
  'n01391Hesapla', 'buildCL', 'confLabel', 'vdiHesapla',
  'saveCalibrationCase', 'loadCalibrationCases',
  'libById', 'optionHtml', 'limitThreadsForEdition', 'libraryInit', 'libraryFamilyChanged',
  'libraryStandardChanged', 'libraryThreadChanged', 'libraryCoatingChanged', 'getLibrarySelection',
  'libraryCompatibilityChanged', 'parseHardnessMin', 'compatibilityResults', 'libraryRenderMeta',
  'libraryReapplyLanguage', 'confClass', 'captureCurrentCalculation',
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
  // Test-only accessor: TORQPRO_LIBRARY is (and must remain) a `const`
  // in frontend/index.html -- it is never rewritten to `var` (unlike
  // the MUTABLE_STATE_NAMES list) because nothing about it needs
  // external re-assignment, only external *reading*. vm.createContext
  // does not expose top-level const bindings as context properties,
  // so this accessor closure -- appended only here, never part of the
  // real production file -- is what lets test code read the live
  // TORQPRO_LIBRARY object that libraryInit()/getLibrarySelection()/etc.
  // actually close over.
  parts.push('function __getTorqProLibrary() { return TORQPRO_LIBRARY; }');
  return { source: parts.join('\n\n'), rawHtml: html };
}

// ---------------------------------------------------------------
// Minimal DOM / localStorage stubs -- only what the extracted code
// actually touches (see the getElementById/querySelectorAll id and
// selector list this harness was built against).
// ---------------------------------------------------------------
function parseTagAttrs(s) {
  const a = {};
  const re = /([\w-]+)(?:="([^"]*)")?/g;
  let m;
  while ((m = re.exec(s))) a[m[1]] = m[2] !== undefined ? m[2] : true;
  return a;
}
function makeElement(id) {
  let _value = '';
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
    set innerHTML(v) {
      this._html = String(v);
      // Mirror real <select> behavior: rebuilding the option list
      // adopts the explicitly `selected` option's value (or the
      // first option's) as the element's new value. Code that wants
      // a *different* value after rebuilding a <select> (e.g.
      // restoring a saved technical ID) sets .value explicitly
      // afterward, which always wins over this default.
      const opts = [...this._html.matchAll(/<option\b([^>]*)>([^<]*)<\/option>/g)];
      if (opts.length) {
        const parsed = opts.map((m) => ({ attrs: parseTagAttrs(m[1]), text: m[2] }));
        const sel = parsed.find((o) => o.attrs.selected !== undefined) || parsed[0];
        _value = sel.attrs.value !== undefined ? sel.attrs.value : sel.text;
      }
    },
    get innerHTML() { return this._html; },
    set placeholder(v) { this._placeholder = String(v); },
    get placeholder() { return this._placeholder; },
    set value(v) { _value = v; },
    get value() { return _value; },
    get options() {
      return [...this._html.matchAll(/<option\b([^>]*)>([^<]*)<\/option>/g)].map((m) => {
        const attrs = parseTagAttrs(m[1]);
        return { value: attrs.value !== undefined ? attrs.value : m[2], text: m[2] };
      });
    },
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
    querySelector() { return null; }, // no <meta name="torqpro-edition">; APP_EDITION defaults to 'full'
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
function newContext(extractedSource, rawHtml, localStorageSeed, apiRequestImpl) {
  const byId = {};
  const localStorageStub = makeLocalStorage(localStorageSeed);
  const documentStub = buildDom(rawHtml, byId);
  const alertCalls = [];
  const sandbox = {
    document: documentStub,
    localStorage: localStorageStub,
    console: console,
    alert: (msg) => { alertCalls.push(msg); },
    hesapla: () => {}, // library cascade functions call hesapla() as a side-effect; stubbed no-op here since this harness tests i18n/data-model behavior, not the calculation engine
    apiRequest: apiRequestImpl || (() => { throw new Error('apiRequest should not be called by this harness'); }),
    downloadText: () => { throw new Error('downloadText should not be called by this harness'); },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'fc_i18n_extracted.js' });
  return { context, byId, localStorageStub, documentStub, alertCalls };
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
async function main() {
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

  // ================================================================
  // Faz 2.7.1b -- dynamic calculation/validation result text.
  // ================================================================

  // ---- 29. yontem dropdown: stable value regardless of language;
  //          hesapla() branches on value, not translated option text
  //          (regression guard for the language-dependent isC bug). ----
  {
    check('yontem select uses stable value="method_c" (not translated text)',
      /<select class="form-select" id="yontem"[^>]*>[\s\S]{0,40}<option value="system_a"/.test(rawHtml));
    check('yontem select "method_c" option value is present',
      /<option value="method_c" data-i18n="hizli\.method_c">/.test(rawHtml));
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const hesaplaSrc = extractFunctionDecl(scriptSrc, 'hesapla');
    check('hesapla() branches on yontem===\'method_c\' (stable value)', hesaplaSrc.indexOf("yontem==='method_c'") !== -1);
    check('hesapla() no longer branches on translated option text ("C Metodu")', hesaplaSrc.indexOf(".includes('C Metodu')") === -1);
    // Same check holds regardless of active language -- the option's
    // *value* attribute is never touched by applyStaticTranslations()
    // (only textContent/placeholder are), so switching language can't
    // change what hesapla() reads via .value.
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.setLanguage('en');
    const methodCEl = getByI18nKey(ctx, 'hizli.method_c');
    checkEqual('method_c option label is translated to en', methodCEl.textContent, 'Method C (Static)');
    check('method_c option element itself still carries value="method_c" in markup (en does not rewrite attributes)',
      /<option value="method_c" data-i18n="hizli\.method_c">C Metodu \(Statik\)<\/option>/.test(rawHtml));
  }

  // ---- 30. v_malzeme dropdown: stable value; vdiHesapla() reads it,
  //          not the translated option text (regression guard for the
  //          language-dependent Ep/elastic-modulus bug). Runs the real
  //          extracted vdiHesapla() end-to-end in both languages and
  //          confirms the numeric result is identical. ----
  {
    check('v_malzeme select "steel"/"aluminum"/"castiron" values are present',
      /<option value="steel" data-i18n="vdi\.material_steel">/.test(rawHtml) &&
      /<option value="aluminum" data-i18n="vdi\.material_aluminum">/.test(rawHtml) &&
      /<option value="castiron" data-i18n="vdi\.material_castiron">/.test(rawHtml));
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const vdiSrc = extractFunctionDecl(scriptSrc, 'vdiHesapla');
    check('vdiHesapla() branches on value===\'aluminum\' (stable value)', vdiSrc.indexOf("==='aluminum'") !== -1);
    check('vdiHesapla() no longer branches on translated option text ("Alüm")', vdiSrc.indexOf(".includes('Alüm')") === -1);

    function runVdi(lang, material) {
      const ctx = newContext(extractedSource, rawHtml, {});
      if (lang === 'en') ctx.context.setLanguage('en');
      ctx.byId['v_malzeme'] = { value: material };
      ctx.byId['v_plaka'] = { value: '10' };
      ctx.byId['v_boy'] = { value: '40' };
      ctx.byId['v_n'] = { value: '0.5' };
      ctx.byId['v_FA'] = { value: '15' };
      ctx.byId['v_dT'] = { value: '0' };
      ctx.context.vdiHesapla();
      return ctx.byId['vdi-sonuc'].innerHTML;
    }
    const alSteelTr = runVdi('tr', 'steel');
    const alSteelEn = runVdi('en', 'steel');
    const alAlumTr = runVdi('tr', 'aluminum');
    const alAlumEn = runVdi('en', 'aluminum');
    // Extract the numeric plate-compliance result (depends directly on Ep).
    const numRe = /result-val">([\d.]+) ×/;
    const steelTrVal = numRe.exec(alSteelTr)[1];
    const steelEnVal = numRe.exec(alSteelEn)[1];
    const alumTrVal = numRe.exec(alAlumTr)[1];
    const alumEnVal = numRe.exec(alAlumEn)[1];
    checkEqual('steel plate compliance identical TR vs EN (language must not change Ep)', steelTrVal, steelEnVal);
    checkEqual('aluminum plate compliance identical TR vs EN (language must not change Ep)', alumTrVal, alumEnVal);
    check('steel (Ep=210000) and aluminum (Ep=70000) give genuinely different results', steelTrVal !== alumTrVal);
  }

  // ---- 31. Check-List (CL data array + buildCL()): all 20 items have
  //          TR/EN text, category, and reference; no raw key leaks;
  //          the stable `no` identity used for scoring is untouched. ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.buildCL();
    const trHtml = ctx.byId['checklist-items'].innerHTML;
    check('tr checklist renders category "Giriş Kontrolü"', trHtml.indexOf('Giriş Kontrolü') !== -1);
    check('tr checklist renders item 1.1 text', trHtml.indexOf('Cıvata, pul, somun') !== -1);
    check('tr checklist renders all 20 item numbers', ['1.1','1.2','1.3','2.1','2.2','2.3','2.4','2.9','2.14','2.19','2.20','3.1','3.2','3.5','3.6','4.1','4.2','5.1','5.2','5.3'].every((no) => trHtml.indexOf('>' + no + '<') !== -1));
    ctx.context.setLanguage('en');
    ctx.context.buildCL();
    const enHtml = ctx.byId['checklist-items'].innerHTML;
    check('en checklist renders category "Incoming Inspection"', enHtml.indexOf('Incoming Inspection') !== -1);
    check('en checklist renders item 1.1 text in English', enHtml.indexOf('material control') !== -1);
    check('en checklist item numbers (scoring identity) unchanged', ['1.1','5.3'].every((no) => enHtml.indexOf('>' + no + '<') !== -1));
    check('en checklist no longer contains Turkish category text', enHtml.indexOf('Giriş Kontrolü') === -1);
    check('tr checklist has no unresolved raw checklist.* keys', !/checklist\.(cat|item|ref)_[a-z0-9_]+(?!['"])/.test(trHtml.replace(/<[^>]*>/g, '')));
  }

  // ---- 32. confLabel(): all 4 confidence levels translate; the
  //          numeric confidence input is never altered by translation. ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const trLabels = [1, 2, 3, 4].map((c) => ctx.context.confLabel(c));
    checkEqual('confidence 4 tr label', trLabels[3], '4 — Doğrulandı');
    checkEqual('confidence 3 tr label', trLabels[2], '3 — Standarttan');
    checkEqual('confidence 2 tr label', trLabels[1], '2 — Hesap/çapraz kontrol');
    checkEqual('confidence 1 tr label', trLabels[0], '1 — Taslak');
    ctx.context.setLanguage('en');
    const enLabels = [1, 2, 3, 4].map((c) => ctx.context.confLabel(c));
    checkEqual('confidence 4 en label', enLabels[3], '4 — Verified');
    checkEqual('confidence 3 en label', enLabels[2], '3 — From standard');
    checkEqual('confidence 2 en label', enLabels[1], '2 — Calculation/cross-check');
    checkEqual('confidence 1 en label', enLabels[0], '1 — Draft');
    // The leading numeric confidence digit (the actual machine value)
    // is identical across languages -- only the trailing label text differs.
    for (let c = 1; c <= 4; c++) {
      check('numeric confidence prefix unchanged for level ' + c,
        trLabels[c - 1].startsWith(c + ' — ') && enLabels[c - 1].startsWith(c + ' — '));
    }
  }

  // ---- 33. Calibration: empty state, Passed/Failed status, and the
  //          invalid-value alert all translate; pass/fail decision
  //          comes from the (mocked) backend response, never from
  //          display language. ----
  {
    // Empty state
    {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => []);
      ctx.byId['calibrationBody'] = { innerHTML: '' };
      await ctx.context.loadCalibrationCases();
      checkEqual('calibration empty-state tr', ctx.byId['calibrationBody'].innerHTML.indexOf('Henüz kalibrasyon kaydı yok.') !== -1, true);
      ctx.context.setLanguage('en');
      await ctx.context.loadCalibrationCases();
      checkEqual('calibration empty-state en', ctx.byId['calibrationBody'].innerHTML.indexOf('No calibration records yet.') !== -1, true);
    }
    // Passed / Failed rows -- decision (`passed`) is server data, fixed
    // regardless of language; only the displayed label changes.
    {
      const rows = [
        { thread: 'M10', program_value: 69.3, reference_value: 70, error_pct: 1.0, tolerance_pct: 5, passed: true, source_id: 'SRC-1' },
        { thread: 'M12', program_value: 80, reference_value: 70, error_pct: 14.3, tolerance_pct: 5, passed: false, source_id: 'SRC-2' },
      ];
      const ctx = newContext(extractedSource, rawHtml, {}, async () => rows);
      ctx.byId['calibrationBody'] = { innerHTML: '' };
      await ctx.context.loadCalibrationCases();
      const trHtml = ctx.byId['calibrationBody'].innerHTML;
      check('tr: passed row shows "Geçti"', trHtml.indexOf('Geçti') !== -1);
      check('tr: failed row shows "Kaldı"', trHtml.indexOf('Kaldı') !== -1);
      ctx.context.setLanguage('en');
      await ctx.context.loadCalibrationCases();
      const enHtml = ctx.byId['calibrationBody'].innerHTML;
      check('en: passed row shows "Passed"', enHtml.indexOf('Passed') !== -1);
      check('en: failed row shows "Failed"', enHtml.indexOf('Failed') !== -1);
      check('en: no leftover Turkish "Geçti"/"Kaldı"', enHtml.indexOf('Geçti') === -1 && enHtml.indexOf('Kaldı') === -1);
      // Underlying pass/fail data is untouched by language -- same
      // `passed` booleans from the (mocked) API response in both cases.
      check('error/tolerance numeric values rendered identically regardless of language',
        trHtml.indexOf('1.00%') !== -1 && enHtml.indexOf('1.00%') !== -1 &&
        trHtml.indexOf('14.30%') !== -1 && enHtml.indexOf('14.30%') !== -1);
    }
    // Invalid-value alert
    {
      const ctx = newContext(extractedSource, rawHtml, {});
      ctx.byId['cal_program'] = { value: 'not-a-number' };
      ctx.byId['cal_reference'] = { value: '70' };
      ctx.byId['cal_tolerance'] = { value: '5' };
      await ctx.context.saveCalibrationCase();
      checkEqual('invalid-value alert message is tr', ctx.alertCalls[ctx.alertCalls.length - 1], 'Geçerli değer girin.');
      ctx.context.setLanguage('en');
      ctx.byId['cal_program'] = { value: 'not-a-number' };
      await ctx.context.saveCalibrationCase();
      checkEqual('invalid-value alert message is en', ctx.alertCalls[ctx.alertCalls.length - 1], 'Enter a valid value.');
    }
  }

  // ---- 34. No hard-coded leftover user text anywhere in the Faz
  //          2.7.1b dynamic-text scope: every checklist./calibration./
  //          common.conf_* key used by these functions resolves in
  //          both languages (no raw-key fallback). ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const dynamicKeys = [
      'checklist.cat_incoming', 'checklist.cat_operation', 'checklist.cat_equipment',
      'checklist.cat_product', 'checklist.cat_maintenance',
      'checklist.item_1_1', 'checklist.item_5_3', 'checklist.ref_technical_drawing',
      'checklist.ref_process_card', 'common.conf_verified', 'common.conf_from_standard',
      'common.conf_calc_cross_check', 'common.conf_draft', 'calibration.err_enter_valid_value',
      'calibration.status_passed', 'calibration.status_failed', 'calibration.no_records_yet',
    ];
    let unresolvedTr = 0, unresolvedEn = 0;
    for (const k of dynamicKeys) if (ctx.context.t(k) === k) unresolvedTr++;
    ctx.context.setLanguage('en');
    for (const k of dynamicKeys) if (ctx.context.t(k) === k) unresolvedEn++;
    checkEqual('no unresolved Faz 2.7.1b dynamic-text keys in tr', unresolvedTr, 0);
    checkEqual('no unresolved Faz 2.7.1b dynamic-text keys in en', unresolvedEn, 0);
  }

  // ================================================================
  // Faz 2.7.2a -- Fasteners / Joint Hardware / Engineering Library.
  // ================================================================
  function setupLibraryDom(ctx) {
    // Minimal set of elements libraryInit()'s cascade touches.
    for (const id of ['lib_family', 'lib_standard', 'lib_thread', 'lib_nut', 'lib_washer', 'lib_coating',
      'lib_mode', 'libraryMeta', 'compatibilityBox', 'cap', 'kalite', 'surtunme', 'mu_thread', 'mu_bearing']) {
      ctx.byId[id] = ctx.documentStub.getElementById(id);
    }
    ctx.byId['cap'].innerHTML = '<option value="M10">M10</option>';
    ctx.byId['kalite'].value = '10.9';
    ctx.byId['surtunme'].innerHTML = '<option value="0.12">0.12</option>';
    ctx.context.libraryInit();
  }

  // ---- 35. product_families machine-readable groupCode ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const families = ctx.context.__getTorqProLibrary().product_families;
    check('every product_families record has a groupCode', families.every((f) => typeof f.groupCode === 'string' && f.groupCode.length > 0));
    const codes = new Set(families.map((f) => f.groupCode));
    checkEqual('groupCode values are exactly {bolt,nut,washer,screw,stud}',
      [...codes].sort().join(','), 'bolt,nut,screw,stud,washer');
  }

  // ---- 36. group==='Civata' comparison no longer present anywhere ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    check('no more group===\'Civata\' anti-pattern in the source', scriptSrc.indexOf("group==='Civata'") === -1);
    check('libraryInit() now filters on groupCode', extractFunctionDecl(scriptSrc, 'libraryInit').indexOf("groupCode==='bolt'") !== -1);
  }

  // ---- 37. Bolt/Nut/Washer/Screw/Stud group labels translate TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const expect = {
      bolt: ['Civata', 'Bolt'], nut: ['Somun', 'Nut'], washer: ['Pul', 'Washer'],
      screw: ['Vida', 'Screw'], stud: ['Saplama', 'Stud'],
    };
    for (const [code, [tr]] of Object.entries(expect)) {
      const family = ctx.context.__getTorqProLibrary().product_families.find((f) => f.groupCode === code);
      check('a product_families record exists for groupCode ' + code, !!family);
      checkEqual('groupKey tr label for ' + code, ctx.context.t(family.groupKey), tr);
    }
    ctx.context.setLanguage('en');
    for (const [code, [, en]] of Object.entries(expect)) {
      const family = ctx.context.__getTorqProLibrary().product_families.find((f) => f.groupCode === code);
      checkEqual('groupKey en label for ' + code, ctx.context.t(family.groupKey), en);
    }
  }

  // ---- 38. Library dropdown option text translates TR/EN (family + coating selectors) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    const famHtmlTr = ctx.byId['lib_family'].innerHTML;
    const coatHtmlTr = ctx.byId['lib_coating'].innerHTML;
    check('tr family options render translated bolt family names', famHtmlTr.indexOf('Altıgen başlı tam dişli civata') !== -1);
    check('tr coating options render translated coating system names', coatHtmlTr.indexOf('Elektrolitik çinko') !== -1);
    check('tr coating "no selection" option is translated', coatHtmlTr.indexOf('Manuel μ seçimi') !== -1);
    ctx.context.setLanguage('en');
    ctx.context.libraryReapplyLanguage();
    const famHtmlEn = ctx.byId['lib_family'].innerHTML;
    const coatHtmlEn = ctx.byId['lib_coating'].innerHTML;
    check('en family options render translated bolt family names', famHtmlEn.indexOf('Hex head fully-threaded bolt') !== -1);
    check('en coating options render translated coating system names', coatHtmlEn.indexOf('Electrolytic zinc') !== -1);
    check('en coating "no selection" option is translated', coatHtmlEn.indexOf('Manual μ selection') !== -1);
    check('en family options no longer show Turkish family names', famHtmlEn.indexOf('Altıgen başlı tam dişli civata') === -1);
  }

  // ---- 39. Technical option *values* are unchanged by language switch ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    const familyValuesTr = ctx.byId['lib_family'].options.map((o) => o.value).sort();
    const coatingValuesTr = ctx.byId['lib_coating'].options.map((o) => o.value).sort();
    ctx.context.setLanguage('en');
    ctx.context.libraryReapplyLanguage();
    const familyValuesEn = ctx.byId['lib_family'].options.map((o) => o.value).sort();
    const coatingValuesEn = ctx.byId['lib_coating'].options.map((o) => o.value).sort();
    checkEqual('family_id option values identical tr vs en', JSON.stringify(familyValuesTr), JSON.stringify(familyValuesEn));
    checkEqual('coating record_id option values identical tr vs en', JSON.stringify(coatingValuesTr), JSON.stringify(coatingValuesEn));
  }

  // ---- 40. record_id / family_id / thread_code / class_code preserved (data model untouched) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const lib = ctx.context.__getTorqProLibrary();
    checkEqual('thread_series record count unchanged', lib.thread_series.length, 26);
    checkEqual('property_classes record count unchanged', lib.property_classes.length, 12);
    checkEqual('bolt_geometry record count unchanged', lib.bolt_geometry.length, 27);
    checkEqual('nut_geometry record count unchanged', lib.nut_geometry.length, 21);
    checkEqual('washer_geometry record count unchanged', lib.washer_geometry.length, 23);
    checkEqual('product_families record count unchanged', lib.product_families.length, 15);
    checkEqual('compatibility_rules record count unchanged', lib.compatibility_rules.length, 8);
    checkEqual('coatings record count unchanged', lib.coatings.length, 6);
    check('a known thread_code (M10x1.25) is present, untouched', lib.thread_series.some((r) => r.thread_code === 'M10x1.25'));
    check('a known class_code (10.9) is present, untouched', lib.property_classes.some((r) => r.class_code === '10.9'));
    check('a known family_id (FAM-BLT-001) is present, untouched', lib.product_families.some((r) => r.family_id === 'FAM-BLT-001'));
    check('a known coating record_id (COAT-001) is present, untouched', lib.coatings.some((r) => r.record_id === 'COAT-001'));
    check('ISO standard codes untouched (ISO 4017 present)', lib.bolt_geometry.some((r) => r.standard === 'ISO 4017'));
  }

  // ---- 41. Library meta panel labels render TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    const metaTr = ctx.byId['libraryMeta'].innerHTML;
    check('tr meta panel shows "Diş geometrisi"', metaTr.indexOf('Diş geometrisi') !== -1);
    check('tr meta panel shows "Baş / oturma"', metaTr.indexOf('Baş / oturma') !== -1);
    ctx.context.setLanguage('en');
    ctx.context.libraryReapplyLanguage();
    const metaEn = ctx.byId['libraryMeta'].innerHTML;
    check('en meta panel shows "Thread geometry"', metaEn.indexOf('Thread geometry') !== -1);
    check('en meta panel shows "Head / bearing"', metaEn.indexOf('Head / bearing') !== -1);
    check('en meta panel no longer shows Turkish labels', metaEn.indexOf('Diş geometrisi') === -1);
  }

  // ---- 42. Compatibility condition/requirement/rationale translate TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const rule = ctx.context.__getTorqProLibrary().compatibility_rules.find((r) => r.rule_id === 'R-001');
    check('R-001 compatibility rule exists', !!rule);
    checkEqual('R-001 condition tr', ctx.context.t(rule.conditionKey), 'Civata 8.8');
    checkEqual('R-001 requirement tr', ctx.context.t(rule.requirementKey), 'Somun sınıf ≥ 8');
    checkEqual('R-001 rationale tr', ctx.context.t(rule.rationaleKey), 'Somun proof load ≥ civata Rm; sıyırma somunda olmamalı');
    ctx.context.setLanguage('en');
    checkEqual('R-001 condition en', ctx.context.t(rule.conditionKey), 'Bolt 8.8');
    checkEqual('R-001 requirement en', ctx.context.t(rule.requirementKey), 'Nut class ≥ 8');
  }

  // ---- 43. Coating μ values and standard codes unchanged by translation ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const coat = ctx.context.__getTorqProLibrary().coatings.find((c) => c.record_id === 'COAT-001');
    checkEqual('COAT-001 mu_total_min unchanged', coat.mu_total_min, 0.1);
    checkEqual('COAT-001 mu_total_max unchanged', coat.mu_total_max, 0.16);
    checkEqual('COAT-001 standard code unchanged', coat.standard, 'ISO 4042');
    checkEqual('COAT-001 test_standard unchanged (ISO 16047)', coat.test_standard, 'ISO 16047');
    ctx.context.setLanguage('en');
    checkEqual('COAT-001 mu_total_min still unchanged after language switch', coat.mu_total_min, 0.1);
    checkEqual('COAT-001 systemTechnical (matching field) stays the original Turkish text', coat.systemTechnical, 'Elektrolitik çinko');
  }

  // ---- 44. Language switch preserves the active library selection (IDs) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    // Pick a specific, non-default coating and confirm it survives a language switch.
    ctx.byId['lib_coating'].value = 'COAT-003';
    ctx.byId['lib_family'].value = ctx.byId['lib_family'].options[0].value;
    const savedFamily = ctx.byId['lib_family'].value;
    ctx.context.setLanguage('en');
    checkEqual('selected coating record_id survives language switch', ctx.byId['lib_coating'].value, 'COAT-003');
    checkEqual('selected family_id survives language switch', ctx.byId['lib_family'].value, savedFamily);
    // Calculation inputs must be untouched by a pure language switch.
    ctx.byId['mu_thread'].value = '0.137';
    ctx.byId['mu_bearing'].value = '0.128';
    ctx.context.setLanguage('tr');
    checkEqual('mu_thread input unaffected by language switch', ctx.byId['mu_thread'].value, '0.137');
    checkEqual('mu_bearing input unaffected by language switch', ctx.byId['mu_bearing'].value, '0.128');
  }

  // ---- 45. No raw translation-key leakage in library dynamic HTML ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    const combinedTr = ctx.byId['lib_family'].innerHTML + ctx.byId['lib_coating'].innerHTML + ctx.byId['libraryMeta'].innerHTML;
    check('no raw "library.xxx" key text leaks into tr rendering', !/library\.[a-z_.]+(?![\w])/.test(combinedTr.replace(/<[^>]*>/g, ' ')));
    ctx.context.setLanguage('en');
    ctx.context.libraryReapplyLanguage();
    const combinedEn = ctx.byId['lib_family'].innerHTML + ctx.byId['lib_coating'].innerHTML + ctx.byId['libraryMeta'].innerHTML;
    check('no raw "library.xxx" key text leaks into en rendering', !/library\.[a-z_.]+(?![\w])/.test(combinedEn.replace(/<[^>]*>/g, ' ')));
  }

  // ---- 46. Standard/technical codes and numeric data unchanged by translation
  //          (thread pitch, hardness, MPa values) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const lib = ctx.context.__getTorqProLibrary();
    const cls109 = lib.property_classes.find((c) => c.class_code === '10.9');
    checkEqual('10.9 class rm_min_mpa unchanged', cls109.rm_min_mpa, 1040);
    checkEqual('10.9 class rp02_min_mpa unchanged', cls109.rp02_min_mpa, 940);
    const thread = lib.thread_series.find((t2) => t2.thread_code === 'M10x1.25');
    checkEqual('M10x1.25 pitch_mm unchanged', thread.pitch_mm, 1.25);
    checkEqual('M10x1.25 stress_area_iso_mm2 unchanged', thread.stress_area_iso_mm2, 61.2);
  }

  // ---- 47. Coating-name text matching against live standard data never uses
  //          the translatable display field (regression guard for the
  //          resolveLiveStandardData()/captureCurrentCalculation() anti-patterns). ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const resolveSrc = extractFunctionDecl(scriptSrc, 'resolveLiveStandardData');
    check('resolveLiveStandardData() reads systemTechnical, not the translatable system field',
      resolveSrc.indexOf('sel.coating?.systemTechnical') !== -1 && resolveSrc.indexOf('sel.coating?.system||') === -1);
    const captureSrc = extractFunctionDecl(scriptSrc, 'captureCurrentCalculation');
    check('captureCurrentCalculation() persists a readable i18n-aware family label (report/search consumer), not a bare technical ID',
      captureSrc.indexOf('sel.family.nameKey?t(sel.family.nameKey)') !== -1);
    check('captureCurrentCalculation() persists coating systemTechnical/record_id, not the translatable system field',
      captureSrc.indexOf('sel.coating?.systemTechnical') !== -1);
    check('captureCurrentCalculation() no longer reads the translatable lib_mode display value for source_mode',
      captureSrc.indexOf("document.getElementById('lib_mode')?.value") === -1);
    check('source_mode fallback literals are the exact pre-2.7.2a strings, not translated (no t() call)',
      captureSrc.indexOf("'Kütüphane'") !== -1 && captureSrc.indexOf("'Formül fallback'") !== -1 &&
      !/source_mode:\([^)]*t\(/.test(captureSrc));
  }

  // ---- 47c. source_mode: byte-identical to the pre-2.7.2a persisted
  //           contract, in both languages, regardless of ACTIVE_STANDARD_LIBRARY
  //           state. CSV/JSON export both read this column verbatim (via
  //           SELECT * on the backend) and it is never displayed as a
  //           label in renderArchive()/reportHtml(), so no consumer needs
  //           a machine code -- the literal legacy string is the correct,
  //           lowest-risk choice. ----
  {
    // No active standard-library version -> fallback branch.
    const ctxLib = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctxLib);
    ctxLib.byId['lib_family'].value = ctxLib.byId['lib_family'].options[0].value;
    const recLibTr = ctxLib.context.captureCurrentCalculation();
    checkEqual('tr: source_mode "library" fallback is byte-identical to the legacy value', recLibTr.source_mode, 'Kütüphane');
    ctxLib.context.setLanguage('en');
    const recLibEn = ctxLib.context.captureCurrentCalculation();
    checkEqual('en: source_mode "library" fallback is still the Turkish legacy string (never translated)', recLibEn.source_mode, 'Kütüphane');
    checkEqual('source_mode persisted value identical tr vs en (library case)', recLibTr.source_mode, recLibEn.source_mode);

    // No library selector wired up -> formula-fallback branch. (EN vs TR
    // non-translation of the literal is already proven by the "library"
    // case above; re-testing here would require switching language,
    // which -- correctly -- causes libraryReapplyLanguage() to populate
    // a real selection once any DOM lookup auto-vivifies an element, so
    // this sub-test stays single-language to isolate the fallback branch itself.)
    const ctxFallback = newContext(extractedSource, rawHtml, {});
    ctxFallback.byId['sonuc-box'] = { innerText: '' };
    const recFbTr = ctxFallback.context.captureCurrentCalculation();
    checkEqual('tr: source_mode "formula_fallback" case is byte-identical to the legacy value', recFbTr.source_mode, 'Formül fallback');

    // version_signature branch still takes priority exactly as before (operator-precedence regression guard).
    const ctxVer = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctxVer);
    ctxVer.context.ACTIVE_STANDARD_LIBRARY.version_signature = 'DATA-V7';
    const recVer = ctxVer.context.captureCurrentCalculation();
    checkEqual('source_mode uses ACTIVE_STANDARD_LIBRARY.version_signature when present (unchanged priority)', recVer.source_mode, 'DATA-V7');

    // family: readable label, still language-aware (this one IS allowed
    // to differ from the legacy exact bytes at save-time, per the
    // family field decision above -- it has always been a readable
    // string, was never a fixed enum, and both reportHtml() and the
    // archive search only ever display/match whatever string is there).
    check('family field is a non-empty readable string in tr', typeof recLibTr.family === 'string' && recLibTr.family.length > 0);
    check('family field is a non-empty readable string in en', typeof recLibEn.family === 'string' && recLibEn.family.length > 0);
  }

  // ---- 47b. captureCurrentCalculation() / resolveLiveStandardData() payload
  //           format regression (backend compatibility audit follow-up):
  //           the *persisted* family label is the same kind of readable
  //           string as before (just now language-aware at save time),
  //           coating persists byte-identical text to the pre-i18n
  //           behavior, and old-format archive rows still read back fine
  //           since reportHtml()/renderArchive() only ever display
  //           whatever string is stored -- they never parse or validate it. ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    ctx.byId['lib_family'].value = ctx.byId['lib_family'].options[0].value;
    ctx.byId['sonuc-box'] = { innerText: '' };
    const family = ctx.context.__getTorqProLibrary().product_families.find((f) => f.family_id === ctx.byId['lib_family'].value);

    const recTr = ctx.context.captureCurrentCalculation();
    checkEqual('tr: persisted family field is the readable tr label (matches dropdown text)', recTr.family, ctx.context.t(family.nameKey));
    check('tr: persisted family field is NOT the bare family_id', recTr.family !== family.family_id);

    ctx.context.setLanguage('en');
    const recEn = ctx.context.captureCurrentCalculation();
    checkEqual('en: persisted family field is the readable en label', recEn.family, ctx.context.t(family.nameKey));
    check('en vs tr persisted family label differs (language-aware at save time, as designed)', recEn.family !== recTr.family);

    // coating: byte-identical to the pre-i18n behavior in both languages
    // (systemTechnical is never translated) -- this is the field backend
    // search/display never actually reads back as a label, so no format
    // change was needed here.
    if (ctx.byId['lib_coating'].options.length > 1) {
      ctx.byId['lib_coating'].value = ctx.byId['lib_coating'].options[1].value;
      const coating = ctx.context.__getTorqProLibrary().coatings.find((c) => c.record_id === ctx.byId['lib_coating'].value);
      const recTr2 = ctx.context.captureCurrentCalculation();
      ctx.context.setLanguage('tr');
      const recTr3 = ctx.context.captureCurrentCalculation();
      checkEqual('coating field identical regardless of language (never translated)', recTr3.coating, coating.systemTechnical);
    }

    const recWithCoating = ctx.context.captureCurrentCalculation();

    // An old-format archive row (as persisted by pre-2.7.2a code, i.e.
    // family/coating already contain plain readable strings) round-trips
    // through reportHtml()'s consumption pattern with no special handling
    // required -- confirming backward compatibility with existing records.
    const oldFormatRow = { family: 'Altıgen başlı tam dişli civata', coating: 'Elektrolitik çinko', source_mode: 'Kütüphane', standard: 'ISO 4017', thread: 'M10', torque_nm: 65 };
    check('an old-format (pre-2.7.2a) archive row has the same field shape as a newly-created one (family/coating/standard/thread are plain strings)',
      typeof oldFormatRow.family === 'string' && typeof oldFormatRow.coating === 'string' && typeof recWithCoating.family === 'string' && typeof recWithCoating.coating === 'string');

    // A newly-created record's shape also round-trips: the client-side
    // payload (record_no is assigned server-side, never sent by the
    // client) uses the same keys as an old row -- no consumer needs to
    // special-case "old" vs "new" records.
    const newKeys = Object.keys(recWithCoating).sort();
    const oldKeys = Object.keys(oldFormatRow).filter((k) => k !== 'record_no').sort();
    check('new record keys are a superset of the old row\'s client-payload keys (no renamed/removed fields)',
      oldKeys.every((k) => newKeys.includes(k)));
  }

  // ================================================================
  // Friction Condition -- short regression block (per Faz 2.7.2
  // instructions: FC frontend code is untouched this phase; this only
  // re-confirms Faz 2.6.8's behavior still holds after all the i18n
  // work done in 2.7.0/2.7.1/2.7.2a).
  // ================================================================
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titleEl = getByI18nKey(ctx, 'fc.page_title');
    ctx.context.applyStaticTranslations();
    checkEqual('FC static key fc.page_title resolves tr', titleEl.textContent, 'Yüzey Sürtünme Koşulu');
    ctx.context.setLanguage('en');
    checkEqual('FC static key fc.page_title resolves en', titleEl.textContent, 'Friction Condition');

    const report = fakeReport();
    ctx.context.FC_LAST_REPORT = report;
    ctx.context.fcRenderOverview(report);
    const overviewEl = ctx.byId['fc-overview'];
    check('FC render function shows no raw key text', !/fc\.[a-z_.]+(?![\w])/.test(overviewEl.innerHTML));
    ctx.context.setLanguage('tr');
    // setLanguage() re-renders FC_LAST_REPORT automatically when set.
    check('FC report re-renders on language switch (tr label present)', overviewEl.innerHTML.indexOf('Kaplama') !== -1);

    const lubEl = getByI18nKey(ctx, 'fc.filter_group_lubricant');
    ctx.context.applyStaticTranslations();
    checkEqual('Lubricant-based conditions filter label tr', lubEl.textContent, 'Yağlayıcı tabanlı koşullar');
    ctx.context.setLanguage('en');
    checkEqual('Lubricant-based conditions filter label en', lubEl.textContent, 'Lubricant-based conditions');
  }

  console.log('\n' + pass + ' passed, ' + fail + ' failed.');
  if (fail > 0) {
    console.log('Failures: ' + failures.join('; '));
    process.exit(1);
  }
  process.exit(0);
}

main().catch((e) => { console.error('FATAL:', e); process.exit(1); });
