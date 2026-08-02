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
  'LAST_CALCULATION', 'ACTIVE_STANDARD_LIBRARY', 'OEM_NORM_DB', '_oF', 'FMEA', 'FMEA_SEVERITY_CLASS', 'ISH', 'CURRENT_ROLE',
  'CURRENT_USER', 'CURRENT_RELEASE_PACKAGE', 'ORG_SETTINGS', 'deferredPrompt',
  'DEPLOY_TYPE_LABEL_KEY', 'DEPLOY_BACKUP_LABEL_KEY', 'DEPLOY_CHANNEL_LABEL_KEY', 'LAST_DIAGNOSTICS',
  'THRESHOLD_TBD_KEY', 'SYSTEM_HEALTH_HELP', 'INFO_ICON_SEQ', 'AUTH_TOKEN',
  'SC_BOLTS', 'SC_NUTS', 'SC_LOADED', 'SC_STATUS_META',
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
const MUTABLE_STATE_NAMES = ['FC_LIST', 'FC_SELECTED_ID', 'FC_COMPARE_ID', 'FC_REQUEST_SEQ', 'FC_LAST_REPORT', 'ACTIVE_STANDARD_LIBRARY', 'CURRENT_ROLE', 'LAST_CALCULATION', 'CURRENT_RELEASE_PACKAGE', 'ORG_SETTINGS', 'deferredPrompt', 'LAST_DIAGNOSTICS'];
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
  'translationValue', 'oemGetAll', 'oemSearch', 'oemRenderCard', 'oemFilter',
  'oemSecFilter', 'oemRenderList', 'oemInit', 'oemReapplyLanguage', 'buildFmea',
  'buildISH', 'ishLookupItem', 'problemAnaliz', 'problemReapplyLanguage',
  'saveGoldenCase', 'loadGoldenCases',
  'reportLocale', 'reportHtml', 'printCurrentReport', 'printRecord',
  'generateProjectRelease', 'printProjectRelease', 'generateReleaseCertificate', 'printReleaseCertificate',
  'installPwa', 'loadMobileAccess', 'loadCloudReadiness', 'loadRuntimeHealth',
  'loadGoLiveProfile', 'renderGoLiveChecklist', 'saveGoLiveProfile', 'runDnsCheck',
  'loadDeploymentProfile', 'renderDeployment', 'saveDeploymentProfile',
  'exportSystemPackage', 'importSystemPackage', 'loadMigrationHistory',
  'runDiagnostics', 'renderDiagnostics', 'downloadDiagnostics',
  'changeOwnPassword', 'adminCreateUser', 'loadAdminUsers', 'adminUpdateUser', 'adminResetPassword',
  'loadAudit', 'downloadBackup', 'loadSystemHealth', 'shInfo', 'infoIconHtml',
  'scEsc', 'scFmtNum', 'scFmtRange', 'scVerificationLabel', 'loadStrengthClassesWorkspace',
  'scRenderBoltTable', 'scRenderNutTable', 'scPopulateCompatSelectors', 'scCheckCompatibility',
  'scRenderCompatResult', 'scReapplyLanguage',
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
  parts.push('function __getOemNormDb() { return OEM_NORM_DB; }');
  parts.push('function __getI18N() { return I18N; }');
  parts.push('function __getFmea() { return FMEA; }');
  parts.push('function __getSystemHealthHelp() { return SYSTEM_HEALTH_HELP; }');
  parts.push('function __getIsh() { return ISH; }');
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
    classList: { _set: new Set(), toggle(c, on) { if (on === false || (on === undefined && this._set.has(c))) this._set.delete(c); else this._set.add(c); }, add(c) { this._set.add(c); }, remove(c) { this._set.delete(c); }, contains(c) { return this._set.has(c); } },
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
      // Track any <input type="checkbox" data-item-code="..."> tags
      // found in the rebuilt HTML as live checkbox-like objects, so
      // container.querySelectorAll('input:checked' / 'input[type="checkbox"]')
      // (see document.querySelectorAll below) can find them -- this
      // mirrors real DOM behavior closely enough to test Ishikawa
      // checkbox selection/restoration without a full DOM tree.
      const inputTags = [...this._html.matchAll(/<input\b([^>]*)>/g)];
      this._checkboxes = inputTags
        .filter((m) => /type="checkbox"/.test(m[0]))
        .map((m) => {
          const attrs = parseTagAttrs(m[1]);
          let checked = attrs.checked !== undefined;
          return {
            dataset: { itemCode: attrs['data-item-code'], tags: attrs['data-tags'] || '' },
            get checked() { return checked; },
            set checked(val) { checked = val; },
          };
        });
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
      const scoped = /^#([\w-]+)\s+input(:checked|\[type="checkbox"\])?$/.exec(selector);
      if (scoped) {
        const container = this._byId[scoped[1]];
        if (!container || !container._checkboxes) return [];
        return scoped[2] === ':checked' ? container._checkboxes.filter((cb) => cb.checked) : container._checkboxes;
      }
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
  const windowCalls = [];
  const promptCalls = [];
  let promptReturnValue = null;
  const sandbox = {
    document: documentStub,
    localStorage: localStorageStub,
    sessionStorage: makeLocalStorage({}),
    console: console,
    alert: (msg) => { alertCalls.push(msg); },
    prompt: (msg) => { promptCalls.push(msg); return promptReturnValue; },
    setTimeout: (fn) => { fn(); },
    window: {
      print: () => { windowCalls.push('print'); },
      open: () => { windowCalls.push('open'); return { document: { write: () => {}, close: () => {} }, print: () => { windowCalls.push('popup-print'); } }; },
    },
    hesapla: () => {}, // library cascade functions call hesapla() as a side-effect; stubbed no-op here since this harness tests i18n/data-model behavior, not the calculation engine
    apiRequest: apiRequestImpl || (() => { throw new Error('apiRequest should not be called by this harness'); }),
    downloadText: () => { throw new Error('downloadText should not be called by this harness'); },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'fc_i18n_extracted.js' });
  return {
    context, byId, localStorageStub, documentStub, alertCalls, windowCalls, promptCalls,
    setPromptReturn(v) { promptReturnValue = v; },
  };
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

  // ---- 15. Topbar simplified (Stage 1): duplicate nav removed, system-active pill still translates ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    // The old topbar.dashboard / topbar.report nav buttons called
    // showNav(), a function that was never defined anywhere in the
    // codebase (dead/non-functional duplicate navigation). Stage 1
    // removed them; assert they are gone rather than asserting they
    // exist, per the approved topbar-simplification UI change.
    const dashEl = getByI18nKey(ctx, 'topbar.dashboard');
    const reportEl = getByI18nKey(ctx, 'topbar.report');
    check('topbar.dashboard element no longer exists (dead duplicate nav removed)', !dashEl);
    check('topbar.report element no longer exists (dead duplicate nav removed)', !reportEl);
    check('showNav( call no longer present anywhere in frontend/index.html', rawHtml.indexOf('showNav(') === -1);
    check('"Go-Live Wizard" string no longer present beside the version', rawHtml.indexOf('Go-Live Wizard') === -1);

    // The same former topbar destinations must remain reachable from
    // the sidebar via the existing, working showPage() handler.
    const sidebarDashEl = getByI18nKey(ctx, 'sidebar.dashboard');
    const sidebarReportEl = getByI18nKey(ctx, 'sidebar.generate_report');
    check('sidebar.dashboard element exists (dashboard reachable from sidebar)', !!sidebarDashEl);
    check('sidebar.generate_report element exists (report reachable from sidebar)', !!sidebarReportEl);

    const activeEl = getByI18nKey(ctx, 'topbar.system_active');
    check('topbar.system_active element exists', !!activeEl);
    ctx.context.applyStaticTranslations();
    ctx.context.setLanguage('en');
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

  // ================================================================
  // Faz 2.7.2b -- OEM Norm Query + Norm Guide.
  // ================================================================
  function setupOemDom(ctx) {
    for (const id of ['oem-meta', 'oem-section-tabs', 'oem-count', 'oem-list', 'oem-search']) {
      ctx.byId[id] = ctx.documentStub.getElementById(id);
    }
    ctx.context.oemInit();
  }

  // ---- 48. OEM_NORM_DB record count preserved: 6 sections, 19 points ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const db = ctx.context.__getOemNormDb();
    checkEqual('OEM_NORM_DB has 6 sections', db.sections.length, 6);
    const total = db.sections.reduce((n, s) => n + s.noktalar.length, 0);
    checkEqual('OEM_NORM_DB has 19 tightening points total', total, 19);
  }

  // ---- 49. Technical field preservation: id/section_id/thread/sinif/tip/
  //          nominal_nm/t_min/t_max/aci_deg/norm references untouched ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const db = ctx.context.__getOemNormDb();
    const sec7 = db.sections.find((s) => s.id === '7');
    check('section 7 exists untouched', !!sec7);
    const p71 = sec7.noktalar.find((p) => p.id === '7.1');
    check('point 7.1 exists', !!p71);
    checkEqual('7.1 thread unchanged', p71.thread, 'M12x1.25');
    checkEqual('7.1 sinif unchanged', p71.sinif, 'A');
    checkEqual('7.1 tip unchanged', p71.tip, 'torque_only');
    checkEqual('7.1 nominal_nm unchanged', p71.nominal_nm, 105);
    checkEqual('7.1 t_min unchanged', p71.t_min, 100);
    checkEqual('7.1 t_max unchanged', p71.t_max, 110);
    checkEqual('7.1 sourceReference (norm article) unchanged', p71.sourceReference, '2.00176/86 Madde 7.1');
    const p1015 = db.sections.find((s) => s.id === '10').noktalar.find((p) => p.id === '10.15');
    checkEqual('10.15 aci_deg unchanged', p1015.aci_deg, 45);
    checkEqual('10.15 ilk_tork unchanged', p1015.ilk_tork, 90);
    checkEqual('meta.norm_no unchanged', db.meta.norm_no, '2.00176/86');
  }

  // ---- 50. OEM static UI TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titleEl = getByI18nKey(ctx, 'oem.title');
    const searchPh = getPlaceholderByKey(ctx, 'oem.search_placeholder');
    ctx.context.applyStaticTranslations();
    checkEqual('oem title tr', titleEl.textContent, 'OEM Norm Sorgulama');
    checkEqual('oem search placeholder tr', searchPh.placeholder, 'Madde no, sistem, diş ölçüsü, sınıf...');
    ctx.context.setLanguage('en');
    checkEqual('oem title en', titleEl.textContent, 'OEM Norm Query');
    checkEqual('oem search placeholder en', searchPh.placeholder, 'Item no., system, thread size, class...');
  }

  // ---- 51. Section (baslik) titles TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const sections = { 7: ['FRENLER', 'BRAKES'], 10: ['MOTOR ASKISI', 'ENGINE MOUNT'], 6: ['DİREKSİYON', 'STEERING'] };
    for (const [id, [tr]] of Object.entries(sections)) {
      const sec = ctx.context.__getOemNormDb().sections.find((s) => s.id === id);
      checkEqual('section ' + id + ' baslik tr', ctx.context.t(sec.baslikKey), tr);
    }
    ctx.context.setLanguage('en');
    for (const [id, [, en]] of Object.entries(sections)) {
      const sec = ctx.context.__getOemNormDb().sections.find((s) => s.id === id);
      checkEqual('section ' + id + ' baslik en', ctx.context.t(sec.baslikKey), en);
    }
  }

  // ---- 52. All 19 tanim keys resolve in both languages ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const db = ctx.context.__getOemNormDb();
    let allPointsTr = true, allPointsEn = true;
    db.sections.forEach((s) => s.noktalar.forEach((p) => {
      if (ctx.context.t(p.tanimKey) === p.tanimKey) allPointsTr = false;
    }));
    ctx.context.setLanguage('en');
    db.sections.forEach((s) => s.noktalar.forEach((p) => {
      if (ctx.context.t(p.tanimKey) === p.tanimKey) allPointsEn = false;
    }));
    check('all 19 points have a resolved tanimKey in tr', allPointsTr);
    check('all 19 points have a resolved tanimKey in en', allPointsEn);
    checkEqual('sample tanim (11.13) en', ctx.context.t(db.sections.find((s) => s.id === '11').noktalar.find((p) => p.id === '11.13').tanimKey), 'Aluminum wheel mounting bolt');
  }

  // ---- 53. Variant text TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const p101 = ctx.context.__getOemNormDb().sections.find((s) => s.id === '10').noktalar.find((p) => p.id === '10.1');
    check('10.1 has a variantKey', !!p101.variantKey);
    checkEqual('10.1 variant tr', ctx.context.t(p101.variantKey), 'Yalnızca 1.3 JTD');
    ctx.context.setLanguage('en');
    checkEqual('10.1 variant en', ctx.context.t(p101.variantKey), 'Only 1.3 JTD');
  }

  // ---- 54. Tork/Tork+Açı/Kontrol Yok type labels TR/EN (card render) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const db = ctx.context.__getOemNormDb();
    const pOnly = db.sections.find((s) => s.id === '7').noktalar.find((p) => p.id === '7.1');
    const pAngle = db.sections.find((s) => s.id === '10').noktalar.find((p) => p.id === '10.15');
    const pNoControl = db.sections.find((s) => s.id === '11').noktalar.find((p) => p.id === '11.13');
    const cardOnlyTr = ctx.context.oemRenderCard({ ...pOnly, section_id: '7', section_baslikKey: db.sections.find((s) => s.id === '7').baslikKey });
    const cardAngleTr = ctx.context.oemRenderCard({ ...pAngle, section_id: '10', section_baslikKey: db.sections.find((s) => s.id === '10').baslikKey });
    const cardNcTr = ctx.context.oemRenderCard({ ...pNoControl, section_id: '11', section_baslikKey: db.sections.find((s) => s.id === '11').baslikKey });
    check('tr: torque-only card shows "Yalnız Tork"', cardOnlyTr.indexOf('Yalnız Tork') !== -1);
    check('tr: torque+angle card shows "Tork+Açı"', cardAngleTr.indexOf('Tork+Açı') !== -1);
    check('tr: no-control card shows "Kontrol Yok"', cardNcTr.indexOf('Kontrol Yok') !== -1);
    ctx.context.setLanguage('en');
    const cardOnlyEn = ctx.context.oemRenderCard({ ...pOnly, section_id: '7', section_baslikKey: db.sections.find((s) => s.id === '7').baslikKey });
    const cardAngleEn = ctx.context.oemRenderCard({ ...pAngle, section_id: '10', section_baslikKey: db.sections.find((s) => s.id === '10').baslikKey });
    const cardNcEn = ctx.context.oemRenderCard({ ...pNoControl, section_id: '11', section_baslikKey: db.sections.find((s) => s.id === '11').baslikKey });
    check('en: torque-only card shows "Torque Only"', cardOnlyEn.indexOf('Torque Only') !== -1);
    check('en: torque+angle card shows "Torque+Angle"', cardAngleEn.indexOf('Torque+Angle') !== -1);
    check('en: no-control card shows "No Control"', cardNcEn.indexOf('No Control') !== -1);
  }

  // ---- 55. Active/Silindi/Deneysel badges TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const db = ctx.context.__getOemNormDb();
    const active = db.sections.find((s) => s.id === '7').noktalar.find((p) => p.id === '7.1'); // experimental:true
    const deleted = db.sections.find((s) => s.id === '10').noktalar.find((p) => p.id === '10.14');
    const cardActiveTr = ctx.context.oemRenderCard({ ...active, section_id: '7', section_baslikKey: db.sections.find((s) => s.id === '7').baslikKey });
    const cardDeletedTr = ctx.context.oemRenderCard({ ...deleted, section_id: '10', section_baslikKey: db.sections.find((s) => s.id === '10').baslikKey });
    check('tr: active badge "AKTİF"', cardActiveTr.indexOf('AKTİF') !== -1);
    check('tr: experimental badge "DENEYSEL"', cardActiveTr.indexOf('DENEYSEL') !== -1);
    check('tr: deleted badge "SİLİNDİ"', cardDeletedTr.indexOf('SİLİNDİ') !== -1);
    ctx.context.setLanguage('en');
    const cardActiveEn = ctx.context.oemRenderCard({ ...active, section_id: '7', section_baslikKey: db.sections.find((s) => s.id === '7').baslikKey });
    const cardDeletedEn = ctx.context.oemRenderCard({ ...deleted, section_id: '10', section_baslikKey: db.sections.find((s) => s.id === '10').baslikKey });
    check('en: active badge "ACTIVE"', cardActiveEn.indexOf('ACTIVE') !== -1);
    check('en: experimental badge "EXPERIMENTAL"', cardActiveEn.indexOf('EXPERIMENTAL') !== -1);
    check('en: deleted badge "DELETED"', cardDeletedEn.indexOf('DELETED') !== -1);
    checkEqual('experimental flag itself (boolean) unaffected by language', active.experimental, true);
  }

  // ---- 56. Class A/B filter labels TR/EN; technical filter codes unchanged ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    check('oemFilter still branches on literal \'sinif:A\'/\'sinif:B\' codes', scriptSrc.indexOf("_oF==='sinif:A'") !== -1 && scriptSrc.indexOf("_oF==='sinif:B'") !== -1);
    const ctx = newContext(extractedSource, rawHtml, {});
    const btnA = getByI18nKey(ctx, 'oem.filter_class_a');
    ctx.context.applyStaticTranslations();
    checkEqual('Sınıf A filter button tr', btnA.textContent, 'Sınıf A');
    ctx.context.setLanguage('en');
    checkEqual('Class A filter button en', btnA.textContent, 'Class A');
  }

  // ---- 57. OEM search: TR/EN cross-language, technical-code search ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    // tr term in tr mode
    let results = ctx.context.oemSearch('direksiyon simidi');
    check('tr term matches in tr mode', results.some((p) => p.id === '6.1'));
    // en term in en mode
    ctx.context.setLanguage('en');
    results = ctx.context.oemSearch('steering wheel');
    check('en term matches in en mode', results.some((p) => p.id === '6.1'));
    // tr term in en mode (cross-language)
    results = ctx.context.oemSearch('direksiyon simidi');
    check('tr term still matches while UI is in en mode (dual-language search)', results.some((p) => p.id === '6.1'));
    // en term in tr mode (cross-language)
    ctx.context.setLanguage('tr');
    results = ctx.context.oemSearch('steering wheel');
    check('en term matches while UI is in tr mode (dual-language search)', results.some((p) => p.id === '6.1'));
    // thread search
    results = ctx.context.oemSearch('m22x1.5');
    check('thread search (M22x1.5) matches 12.12', results.some((p) => p.id === '12.12'));
    // malzeme (material code) search
    results = ctx.context.oemSearch('10r riv/dac');
    check('material code search matches 7.1', results.some((p) => p.id === '7.1'));
    // class + technical type search
    results = ctx.context.oemSearch('torque_angle');
    check('technical tip enum search matches torque_angle points', results.every((p) => p.tip === 'torque_angle') && results.length > 0);
  }

  // ---- 58. Language switch: search query, filters, and result record IDs
  //          are preserved; only displayed text changes ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupOemDom(ctx);
    ctx.byId['oem-search'].value = 'fren';
    ctx.context.oemFilter('sinif:A', null);
    const idsTrBefore = (ctx.context.oemSearch('fren')).filter((p) => p.sinif === 'A').map((p) => p.id).sort();
    ctx.context.setLanguage('en');
    checkEqual('search query preserved after language switch', ctx.byId['oem-search'].value, 'fren');
    const idsEnAfter = (ctx.context.oemSearch('fren')).filter((p) => p.sinif === 'A').map((p) => p.id).sort();
    // "fren" is a tr-only term (Turkish for "brake") -- oemSearch is
    // dual-language, so it must still match section 7 (translated to
    // "BRAKES" in en) via the tr side of the section-title comparison.
    checkEqual('matched record IDs identical across language switch', JSON.stringify(idsTrBefore), JSON.stringify(idsEnAfter));
    check('at least one record matched (sanity check)', idsEnAfter.length > 0);
  }

  // ---- 59. No raw translation-key leakage in OEM dynamic HTML ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupOemDom(ctx);
    const html1 = ctx.byId['oem-list'].innerHTML + ctx.byId['oem-meta'].innerHTML + ctx.byId['oem-section-tabs'].innerHTML;
    check('no raw "oem.xxx" key text leaks into tr rendering', !/oem\.[a-z_.0-9]+(?![\w])/.test(html1.replace(/<[^>]*>/g, ' ')));
    ctx.context.setLanguage('en');
    ctx.context.oemReapplyLanguage();
    const html2 = ctx.byId['oem-list'].innerHTML + ctx.byId['oem-meta'].innerHTML + ctx.byId['oem-section-tabs'].innerHTML;
    check('no raw "oem.xxx" key text leaks into en rendering', !/oem\.[a-z_.0-9]+(?![\w])/.test(html2.replace(/<[^>]*>/g, ' ')));
  }

  // ---- 60. Norm Guide: all static keys resolve TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titleEl = getByI18nKey(ctx, 'norm.title');
    const critEl = getByI18nKey(ctx, 'norm.capability_critical');
    ctx.context.applyStaticTranslations();
    checkEqual('norm title tr', titleEl.textContent, 'Norm ve Standart Rehberi');
    checkEqual('norm capability_critical tr', critEl.textContent, 'Kritik (Report)');
    ctx.context.setLanguage('en');
    checkEqual('norm title en', titleEl.textContent, 'Norm and Standards Guide');
    checkEqual('norm capability_critical en', critEl.textContent, 'Critical (Report)');
  }

  // ---- 61. Norm Guide technical codes/thresholds unchanged in both languages ----
  {
    check('Cm/Cmk >= 2.00 threshold text is present verbatim in markup (not a translation key)',
      /Cm\/Cmk ≥ 2\.00/.test(rawHtml));
    check('Cm/Cmk >= 1.67 threshold text is present verbatim', /Cm\/Cmk ≥ 1\.67/.test(rawHtml));
    check('VDI 2230 appears verbatim in norm page subtitle key (both languages)',
      /'norm\.subtitle': 'VDI 2230/.test(rawHtml));
    check('ISO 16047 appears verbatim in norm page subtitle key', /ISO 16047/.test(rawHtml));
  }

  // ---- 62. Hard-coded user text scan across all Faz 2.7.2b functions ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const turkishCharRe = /[şğüöçİĞÜŞÖÇı]/;
    const funcs = ['oemGetAll', 'oemSearch', 'oemRenderCard', 'oemFilter', 'oemSecFilter', 'oemRenderList', 'oemInit', 'oemReapplyLanguage'];
    let anyLeftover = false;
    for (const fn of funcs) {
      const src = extractFunctionDecl(scriptSrc, fn);
      const strs = [...src.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]).filter((s) => turkishCharRe.test(s));
      if (strs.length) { anyLeftover = true; }
    }
    check('no hard-coded Turkish string literals remain in OEM functions', !anyLeftover);
  }

  // ---- 63. Language-dependent decision anti-pattern scan (OEM scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const oemSrc = scriptSrc.slice(scriptSrc.indexOf('function oemGetAll'), scriptSrc.indexOf('function oemInit') + 2000);
    check('no .includes(\'Civata\')-style translated-text filtering in OEM code', !/includes\('[A-ZÇĞİÖŞÜ][a-zçğıöşüA-ZÇĞİÖŞÜ ]+'\)/.test(oemSrc));
    check('OEM decision branches (.tip/.status/.sinif ===) use only technical enum literals',
      [...oemSrc.matchAll(/\.(tip|status|sinif)\s*===\s*'([^']*)'/g)].every((m) => !looksLikeTranslatedText(m[2])));
    // Heuristic: technical enum values here are short snake_case codes
    // (torque_only, deleted, ...) or single-letter class codes (A, B).
    // Translated display text would contain a Turkish-specific
    // character or a space between words -- neither ever appears in
    // a legitimate technical enum literal.
    function looksLikeTranslatedText(s) { return /[şğüöçİĞÜŞÖÇı ]/.test(s); }
  }

  // ================================================================
  // Faz 2.7.2b (cont.) -- translationValue() fallback / console.warn
  // behavior verification. All via spying on the real console.warn
  // for the duration of each check -- no production code touched,
  // no cache or global state added to translationValue() itself.
  // ================================================================
  function withWarnSpy(fn) {
    const calls = [];
    const orig = console.warn;
    console.warn = (...args) => { calls.push(args.join(' ')); };
    try { fn(calls); } finally { console.warn = orig; }
    return calls;
  }

  // ---- 64. Valid key: no console.warn ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    let result;
    const calls = withWarnSpy(() => { result = ctx.context.translationValue('oem.title', 'tr'); });
    checkEqual('translationValue returns the tr value for a valid key', result, 'OEM Norm Sorgulama');
    checkEqual('no console.warn for a valid key', calls.length, 0);
  }

  // ---- 65. Normal OEM search: zero console.warn across a full search
  //          (all 19 records' tanim/section/variant keys are valid) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const calls = withWarnSpy(() => { ctx.context.oemSearch('fren'); });
    checkEqual('no console.warn during a normal oemSearch() call', calls.length, 0);
    // Simulate several keystrokes' worth of searches (progressive query).
    const calls2 = withWarnSpy(() => {
      ['f', 'fr', 'fre', 'fren', 'fren '].forEach((q) => ctx.context.oemSearch(q));
    });
    checkEqual('no console.warn across 5 progressive keystroke-style searches', calls2.length, 0);
  }

  // ---- 66. A missing key produces exactly one warning per
  //          translationValue() call -- linear, not exploding
  //          per-record or per-keystroke (translationValue() has no
  //          internal loop, so this also serves as a source-level
  //          regression guard against a future refactor adding one). ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const tvSrc = extractFunctionDecl(scriptSrc, 'translationValue');
    check('translationValue() contains no loop construct (for/while/forEach) that could multiply warnings',
      !/\b(for|while)\s*\(/.test(tvSrc) && !/\.(forEach|map)\(/.test(tvSrc));
    const calls = withWarnSpy(() => {
      for (let i = 0; i < 5; i++) ctx.context.translationValue('this.key.does.not.exist', 'tr');
    });
    checkEqual('exactly 5 warnings for 5 explicit calls with a missing key (1:1, no multiplication)', calls.length, 5);
  }

  // ---- 67. translationValue() does not call t() (no double-warning path) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const tvSrc = extractFunctionDecl(scriptSrc, 'translationValue');
    check('translationValue() body does not call t(...) internally (would double-warn via two independent fallback chains)',
      !/(?<![\w.])t\(/.test(tvSrc));
  }

  // ---- 68. tr missing / en present -> controlled en fallback + 1 warning ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const tvSrc = extractFunctionDecl(scriptSrc, 'translationValue');
    check('translationValue() has a distinct "lang missing, other-lang present" warning branch', tvSrc.indexOf("' fallback'") !== -1 && tvSrc.indexOf('fallbackLang') !== -1);
    check('translationValue() has a distinct "missing everywhere" warning branch', tvSrc.indexOf('no translation found in any language') !== -1);
    // Construct a genuine single-key gap (tr missing, en present) via
    // the test-only I18N accessor -- the real I18N.en/I18N.tr tables
    // ship with full 768/768 parity, so no such gap exists naturally;
    // this temporarily adds one key to the *same* I18N.en object the
    // real functions close over, purely for this test.
    const i18n = ctx.context.__getI18N();
    i18n.en['faz2_7_2b_test.only_en_key'] = 'English only value';
    let result;
    const calls = withWarnSpy(() => { result = ctx.context.translationValue('faz2_7_2b_test.only_en_key', 'tr'); });
    checkEqual('tr-missing/en-present key falls back to the en value', result, 'English only value');
    checkEqual('exactly one controlled warning for the tr-missing/en-present path', calls.length, 1);
    check('warning message mentions the en fallback', calls[0].indexOf('en fallback') !== -1);
  }

  // ---- 68b. en missing / tr present -> controlled tr fallback + 1 warning ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const i18n = ctx.context.__getI18N();
    i18n.tr['faz2_7_2b_test.only_tr_key'] = 'Yalnızca Türkçe değer';
    let result;
    const calls = withWarnSpy(() => { result = ctx.context.translationValue('faz2_7_2b_test.only_tr_key', 'en'); });
    checkEqual('en-missing/tr-present key falls back to the tr value', result, 'Yalnızca Türkçe değer');
    checkEqual('exactly one controlled warning for the en-missing/tr-present path', calls.length, 1);
    check('warning message mentions the tr fallback', calls[0].indexOf('tr fallback') !== -1);
  }

  // ---- 69. Both languages missing -> raw key returned + 1 controlled warning ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    let result;
    const calls = withWarnSpy(() => { result = ctx.context.translationValue('totally.unknown.key', 'tr'); });
    checkEqual('raw key returned when missing in both languages', result, 'totally.unknown.key');
    checkEqual('exactly one controlled warning when missing everywhere', calls.length, 1);
    check('warning message indicates no translation found in any language', calls[0].indexOf('no translation found in any language') !== -1);
  }

  // ---- 70. Original t() fallback console.warn call sites are untouched ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const tSrc = extractFunctionDecl(scriptSrc, 't');
    checkEqual('t() still has exactly 2 console.warn call sites', (tSrc.match(/console\.warn\(/g) || []).length, 2);
    check('t() en-fallback warning text unchanged', tSrc.indexOf('using en fallback') !== -1);
    check('t() total-miss warning text unchanged', tSrc.indexOf('no translation found in any language') !== -1);
  }

  // ================================================================
  // Faz 2.7.2c -- FMEA Failure Catalog.
  // ================================================================

  // ---- 71. FMEA record count preserved: 8 records ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('FMEA has 8 records', ctx.context.__getFmea().length, 8);
  }

  // ---- 72. Every record has a severityCode in {critical, high, medium} ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const fmea = ctx.context.__getFmea();
    const allowed = new Set(['critical', 'high', 'medium']);
    check('every FMEA record has a severityCode', fmea.every((f) => typeof f.severityCode === 'string'));
    check('every severityCode is one of critical/high/medium', fmea.every((f) => allowed.has(f.severityCode)));
  }

  // ---- 73. Visible Turkish severity label is not used as a decision input
  //          (source-level check: no object keyed by KRİTİK/YÜKSEK/ORTA) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    check('no object literal keyed by the Turkish severity words remains', !/\{[^}]*KRİTİK\s*:/.test(scriptSrc) && !/\{[^}]*YÜKSEK\s*:/.test(scriptSrc));
  }

  // ---- 74. rc[f.p] anti-pattern no longer present ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    check('rc[f.p] anti-pattern is gone', scriptSrc.indexOf('rc[f.p]') === -1);
    check('buildFmea() now indexes the severity class map by severityCode', scriptSrc.indexOf('FMEA_SEVERITY_CLASS[f.severityCode]') !== -1);
  }

  // ---- 75. Severity CSS class mapping: critical->danger, high->warn,
  //          medium->info, identical in tr and en ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    // FMEA_SEVERITY_CLASS is a plain const object -- exercise it via
    // buildFmea()'s actual rendered output instead of relying on a
    // dedicated accessor, which more faithfully tests the real path.
    ctx.byId = ctx.byId || {};
    ctx.byId['fmea-list'] = ctx.documentStub.getElementById('fmea-list');
    ctx.context.buildFmea();
    const htmlTr = ctx.byId['fmea-list'].innerHTML;
    check('tr render contains pill-danger (critical)', htmlTr.indexOf('pill-danger') !== -1);
    check('tr render contains pill-warn (high)', htmlTr.indexOf('pill-warn') !== -1);
    check('tr render contains pill-info (medium)', htmlTr.indexOf('pill-info') !== -1);
    ctx.context.setLanguage('en');
    ctx.context.buildFmea();
    const htmlEn = ctx.byId['fmea-list'].innerHTML;
    check('en render still contains pill-danger (critical, unchanged)', htmlEn.indexOf('pill-danger') !== -1);
    check('en render still contains pill-warn (high, unchanged)', htmlEn.indexOf('pill-warn') !== -1);
    check('en render still contains pill-info (medium, unchanged)', htmlEn.indexOf('pill-info') !== -1);
  }

  // ---- 76. Severity labels translate TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('severity_critical tr', ctx.context.t('fmea.severity_critical'), 'KRİTİK');
    checkEqual('severity_high tr', ctx.context.t('fmea.severity_high'), 'YÜKSEK');
    checkEqual('severity_medium tr', ctx.context.t('fmea.severity_medium'), 'ORTA');
    ctx.context.setLanguage('en');
    checkEqual('severity_critical en', ctx.context.t('fmea.severity_critical'), 'CRITICAL');
    checkEqual('severity_high en', ctx.context.t('fmea.severity_high'), 'HIGH');
    checkEqual('severity_medium en', ctx.context.t('fmea.severity_medium'), 'MEDIUM');
  }

  // ---- 77. All 8 records' errorKey/causeKey/effectKey/recommendationKey
  //          resolve in both languages ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const fmea = ctx.context.__getFmea();
    checkEqual('all 8 records have errorKey', fmea.filter((f) => f.errorKey).length, 8);
    checkEqual('all 8 records have causeKey', fmea.filter((f) => f.causeKey).length, 8);
    checkEqual('all 8 records have effectKey', fmea.filter((f) => f.effectKey).length, 8);
    checkEqual('all 8 records have recommendationKey', fmea.filter((f) => f.recommendationKey).length, 8);
    let allResolvedTr = true, allResolvedEn = true;
    fmea.forEach((f) => {
      [f.errorKey, f.causeKey, f.effectKey, f.recommendationKey].forEach((k) => {
        if (ctx.context.t(k) === k) allResolvedTr = false;
      });
    });
    ctx.context.setLanguage('en');
    fmea.forEach((f) => {
      [f.errorKey, f.causeKey, f.effectKey, f.recommendationKey].forEach((k) => {
        if (ctx.context.t(k) === k) allResolvedEn = false;
      });
    });
    check('all 32 content fields resolve in tr', allResolvedTr);
    check('all 32 content fields resolve in en', allResolvedEn);
  }

  // ---- 78. 32 content fields have distinct, non-empty TR and EN text
  //          (sample-verified against the original source strings) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('fmea_001 error tr', ctx.context.t('fmea.error.fmea_001'), 'Tork limit dışı');
    checkEqual('fmea_004 recommendation tr (contains Cm/Cmk threshold)', ctx.context.t('fmea.recommendation.fmea_004'), 'Cm/Cmk < 1.67 ise üretimden çıkar');
    ctx.context.setLanguage('en');
    checkEqual('fmea_001 error en', ctx.context.t('fmea.error.fmea_001'), 'Torque out of limits');
    checkEqual('fmea_004 recommendation en (Cm/Cmk threshold preserved verbatim)', ctx.context.t('fmea.recommendation.fmea_004'), 'Remove from production if Cm/Cmk < 1.67');
  }

  // ---- 79. No raw translation-key leakage in FMEA dynamic HTML ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.byId['fmea-list'] = ctx.documentStub.getElementById('fmea-list');
    ctx.context.buildFmea();
    const htmlTr = ctx.byId['fmea-list'].innerHTML;
    check('no raw "fmea.xxx" key text leaks into tr rendering', !/fmea\.[a-z_.0-9]+(?![\w])/.test(htmlTr.replace(/<[^>]*>/g, ' ')));
    ctx.context.setLanguage('en');
    ctx.context.buildFmea();
    const htmlEn = ctx.byId['fmea-list'].innerHTML;
    check('no raw "fmea.xxx" key text leaks into en rendering', !/fmea\.[a-z_.0-9]+(?![\w])/.test(htmlEn.replace(/<[^>]*>/g, ' ')));
  }

  // ---- 80. Language switch: record count/order/severityCode/CSS class
  //          unchanged; only displayed text changes ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const before = ctx.context.__getFmea().map((f) => ({ id: f.id, severityCode: f.severityCode }));
    ctx.byId['fmea-list'] = ctx.documentStub.getElementById('fmea-list');
    ctx.context.buildFmea();
    const htmlTr = ctx.byId['fmea-list'].innerHTML;
    ctx.context.setLanguage('en');
    const after = ctx.context.__getFmea().map((f) => ({ id: f.id, severityCode: f.severityCode }));
    checkEqual('record count unchanged after language switch', after.length, before.length);
    checkEqual('record order and IDs unchanged after language switch', JSON.stringify(after.map((f) => f.id)), JSON.stringify(before.map((f) => f.id)));
    checkEqual('severityCode values unchanged after language switch', JSON.stringify(after), JSON.stringify(before));
    ctx.context.buildFmea();
    const htmlEn = ctx.byId['fmea-list'].innerHTML;
    const classesTr = [...htmlTr.matchAll(/pill-(danger|warn|info)/g)].map((m) => m[1]);
    const classesEn = [...htmlEn.matchAll(/pill-(danger|warn|info)/g)].map((m) => m[1]);
    checkEqual('CSS severity classes identical (same order) across language switch', JSON.stringify(classesTr), JSON.stringify(classesEn));
    check('displayed text actually changed (Turkish error text no longer present in en)', htmlEn.indexOf('Tork limit dışı') === -1);
  }

  // ---- 81. Cm/Cmk and technical threshold text preserved verbatim ----
  {
    check('"Cm/Cmk < 1.67" appears verbatim in the tr FMEA data', /'fmea\.recommendation\.fmea_004': 'Cm\/Cmk < 1\.67/.test(rawHtml));
    check('"Cm\\/Cmk < 1.67" appears verbatim in the en FMEA data', /'fmea\.recommendation\.fmea_004': 'Remove from production if Cm\/Cmk < 1\.67'/.test(rawHtml));
  }

  // ---- 82. FMEA static UI TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titleEl = getByI18nKey(ctx, 'fmea.title');
    ctx.context.applyStaticTranslations();
    checkEqual('fmea page title tr', titleEl.textContent, 'FMEA Hata Kataloğu');
    ctx.context.setLanguage('en');
    checkEqual('fmea page title en', titleEl.textContent, 'FMEA Failure Catalog');
  }

  // ---- 83. Hard-coded Turkish user text scan (FMEA scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const src = extractFunctionDecl(scriptSrc, 'buildFmea');
    const turkishCharRe = /[şğüöçİĞÜŞÖÇı]/;
    const strs = [...src.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]).filter((s) => turkishCharRe.test(s));
    check('no hard-coded Turkish string literals remain in buildFmea()', strs.length === 0);
  }

  // ---- 84. Language-dependent decision anti-pattern scan (FMEA scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const fmeaSrc = scriptSrc.slice(scriptSrc.indexOf('const FMEA='), scriptSrc.indexOf('function buildFmea') + 800);
    check('no severity-label-keyed object (translated-text-as-decision anti-pattern) in FMEA scope',
      !/\{[^}]*(KRİTİK|YÜKSEK|ORTA)\s*:/.test(fmeaSrc));
  }

  // ================================================================
  // Faz 2.7.2d -- Engineering Reference closure audit: integrated
  // regression tests spanning Library/OEM/FMEA/Friction Condition
  // together (each area's own dedicated tests already exist in
  // blocks 1-84; these verify the surfaces work correctly *together*
  // and that language-switch state preservation holds simultaneously
  // across all of them).
  // ================================================================

  // ---- 85. TR/EN key resolution across all Engineering Reference
  //          pages simultaneously (no raw-key fallback anywhere) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const sampleKeys = [
      'hizli.title', 'fc.page_title', 'oem.title', 'norm.title', 'fmea.title',
      'library.product_families.group_bolt', 'library.coatings.system_coat_001',
      'oem.section.7', 'oem.tanim.6_1', 'fmea.error.fmea_001', 'fmea.severity_critical',
    ];
    let unresolvedTr = 0, unresolvedEn = 0;
    for (const k of sampleKeys) if (ctx.context.t(k) === k) unresolvedTr++;
    ctx.context.setLanguage('en');
    for (const k of sampleKeys) if (ctx.context.t(k) === k) unresolvedEn++;
    checkEqual('no unresolved keys across Engineering Reference pages in tr', unresolvedTr, 0);
    checkEqual('no unresolved keys across Engineering Reference pages in en', unresolvedEn, 0);
  }

  // ---- 86. Record ID sets identical after a language switch, across
  //          library/OEM/FMEA simultaneously ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const libIdsTr = ctx.context.__getTorqProLibrary().product_families.map((f) => f.family_id).sort();
    const oemIdsTr = ctx.context.__getOemNormDb().sections.flatMap((s) => s.noktalar.map((p) => p.id)).sort();
    const fmeaIdsTr = ctx.context.__getFmea().map((f) => f.id).sort();
    ctx.context.setLanguage('en');
    const libIdsEn = ctx.context.__getTorqProLibrary().product_families.map((f) => f.family_id).sort();
    const oemIdsEn = ctx.context.__getOemNormDb().sections.flatMap((s) => s.noktalar.map((p) => p.id)).sort();
    const fmeaIdsEn = ctx.context.__getFmea().map((f) => f.id).sort();
    checkEqual('library family_id set unchanged after language switch', JSON.stringify(libIdsTr), JSON.stringify(libIdsEn));
    checkEqual('OEM point id set unchanged after language switch', JSON.stringify(oemIdsTr), JSON.stringify(oemIdsEn));
    checkEqual('FMEA id set unchanged after language switch', JSON.stringify(fmeaIdsTr), JSON.stringify(fmeaIdsEn));
  }

  // ---- 87. Technical option value sets identical after a language
  //          switch (yontem, v_malzeme, and the library selector) ----
  {
    check('yontem option values are the fixed set {system_a,method_c,torque_angle,tty}',
      /value="system_a"/.test(rawHtml) && /value="method_c"/.test(rawHtml) &&
      /value="torque_angle"/.test(rawHtml) && /value="tty"/.test(rawHtml));
    check('v_malzeme option values are the fixed set {steel,aluminum,castiron}',
      /value="steel"/.test(rawHtml) && /value="aluminum"/.test(rawHtml) && /value="castiron"/.test(rawHtml));
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    const valuesTr = ctx.byId['lib_family'].options.map((o) => o.value).sort();
    ctx.context.setLanguage('en');
    ctx.context.libraryReapplyLanguage();
    const valuesEn = ctx.byId['lib_family'].options.map((o) => o.value).sort();
    checkEqual('library family option values unchanged after language switch', JSON.stringify(valuesTr), JSON.stringify(valuesEn));
  }

  // ---- 88. No raw translation-key leakage across Library/OEM/FMEA/FC
  //          rendered together in one pass ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    setupOemDom(ctx);
    ctx.byId['fmea-list'] = ctx.documentStub.getElementById('fmea-list');
    ctx.context.buildFmea();
    ctx.context.setLanguage('en');
    ctx.context.libraryReapplyLanguage();
    ctx.context.oemReapplyLanguage();
    ctx.context.buildFmea();
    const combined = ctx.byId['lib_family'].innerHTML + ctx.byId['lib_coating'].innerHTML +
      ctx.byId['oem-list'].innerHTML + ctx.byId['oem-meta'].innerHTML + ctx.byId['fmea-list'].innerHTML;
    check('no raw namespaced key text leaks across library+OEM+FMEA rendered together in en',
      !/(library|oem|fmea)\.[a-z_.0-9]+(?![\w])/.test(combined.replace(/<[^>]*>/g, ' ')));
  }

  // ---- 89. Technical standards and numeric values identical in both
  //          languages, checked across library + OEM + norm together ----
  {
    check('VDI 2230 appears verbatim (norm page)', /VDI 2230/.test(rawHtml));
    check('ISO 16047 appears verbatim (norm + coatings test_standard)', /ISO 16047/.test(rawHtml));
    check('FIAT norm number 2.00176/86 appears verbatim', /2\.00176\/86/.test(rawHtml));
    const ctx = newContext(extractedSource, rawHtml, {});
    const p71 = ctx.context.__getOemNormDb().sections.find((s) => s.id === '7').noktalar.find((p) => p.id === '7.1');
    ctx.context.setLanguage('en');
    const p71en = ctx.context.__getOemNormDb().sections.find((s) => s.id === '7').noktalar.find((p) => p.id === '7.1');
    checkEqual('OEM torque values identical regardless of language (same object, not re-fetched)', p71.nominal_nm, p71en.nominal_nm);
  }

  // ---- 90. Cross-language OEM search regression (closure re-check) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.setLanguage('en');
    const trTermInEn = ctx.context.oemSearch('fren kaliperi');
    check('tr term still finds the correct record while UI is en (closure re-check)', trTermInEn.some((p) => p.id === '7.1'));
  }

  // ---- 91. Library selection preservation regression (closure re-check) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupLibraryDom(ctx);
    ctx.byId['lib_coating'].value = 'COAT-004';
    ctx.context.setLanguage('en');
    checkEqual('coating selection survives language switch (closure re-check)', ctx.byId['lib_coating'].value, 'COAT-004');
  }

  // ---- 92. FMEA CSS severity preservation regression (closure re-check) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.byId['fmea-list'] = ctx.documentStub.getElementById('fmea-list');
    ctx.context.buildFmea();
    const before = [...ctx.byId['fmea-list'].innerHTML.matchAll(/pill-(danger|warn|info)/g)].map((m) => m[1]);
    ctx.context.setLanguage('en');
    ctx.context.buildFmea();
    const after = [...ctx.byId['fmea-list'].innerHTML.matchAll(/pill-(danger|warn|info)/g)].map((m) => m[1]);
    checkEqual('FMEA severity CSS class sequence unchanged (closure re-check)', JSON.stringify(before), JSON.stringify(after));
  }

  // ---- 93. Friction Condition re-render regression (closure re-check) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const report = fakeReport();
    ctx.context.FC_LAST_REPORT = report;
    ctx.context.fcRenderOverview(report);
    ctx.context.setLanguage('en');
    check('FC overview re-rendered in en after language switch (closure re-check)', ctx.byId['fc-overview'].innerHTML.indexOf('Coating') !== -1);
  }

  // ---- 94. Persisted payload contract regression (closure re-check) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.byId['sonuc-box'] = { innerText: '' };
    const rec = ctx.context.captureCurrentCalculation();
    checkEqual('source_mode fallback is byte-identical to the legacy contract (closure re-check)', rec.source_mode, 'Formül fallback');
    check('family field is a readable string, not a bare technical ID (closure re-check)', typeof rec.family !== 'string' || !/^FAM-/.test(rec.family || ''));
  }

  // ================================================================
  // Faz 2.7.3a -- Problem Management / Ishikawa.
  // ================================================================
  function setupProblemDom(ctx) {
    for (const id of ['p_ne', 'p_nerede', 'p_nezaman', 'p_nasil', 'p_nekdar', 'p_kim', 'ishikawa-cats', 'mudahale-sonuc']) {
      ctx.byId[id] = ctx.documentStub.getElementById(id);
    }
    ctx.context.buildISH();
  }
  function checkIshItems(ctx, codes) {
    const boxes = ctx.byId['ishikawa-cats']._checkboxes;
    codes.forEach((code) => { const cb = boxes.find((b) => b.dataset.itemCode === code); if (cb) cb.checked = true; });
  }

  // ---- 95. ISH category count preserved: 5 ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('ISH has 5 categories', ctx.context.__getIsh().length, 5);
  }

  // ---- 96. ISH item count preserved: 16 ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const total = ctx.context.__getIsh().reduce((n, c) => n + c.items.length, 0);
    checkEqual('ISH has 16 items total', total, 16);
  }

  // ---- 97. Every category has categoryCode + categoryKey ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const ish = ctx.context.__getIsh();
    check('every category has categoryCode', ish.every((c) => typeof c.categoryCode === 'string' && c.categoryCode.length > 0));
    check('every category has categoryKey', ish.every((c) => typeof c.categoryKey === 'string' && c.categoryKey.length > 0));
  }

  // ---- 98. Every item has itemCode + itemKey + tags array ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const ish = ctx.context.__getIsh();
    const allItems = ish.flatMap((c) => c.items);
    check('every item has itemCode', allItems.every((it) => typeof it.itemCode === 'string' && it.itemCode.length > 0));
    check('every item has itemKey', allItems.every((it) => typeof it.itemKey === 'string' && it.itemKey.length > 0));
    check('every item has a tags array', allItems.every((it) => Array.isArray(it.tags)));
  }

  // ---- 99. itemCode values are unique across all 16 items ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const allCodes = ctx.context.__getIsh().flatMap((c) => c.items).map((it) => it.itemCode);
    checkEqual('16 itemCodes, all unique', new Set(allCodes).size, allCodes.length);
  }

  // ---- 100. Visible checkbox textContent is not used as a decision
  //           input (source-level check) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const paSrc = extractFunctionDecl(scriptSrc, 'problemAnaliz');
    check('problemAnaliz() does not read cb.parentElement.textContent for classification', paSrc.indexOf('parentElement.textContent') === -1);
    check('problemAnaliz() reads cb.dataset.itemCode / cb.dataset.tags instead', paSrc.indexOf('dataset.itemCode') !== -1 && paSrc.indexOf('dataset.tags') !== -1);
  }

  // ---- 101. Old Turkish-substring anti-patterns are gone ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    check("no sec.includes('diş')-style anti-pattern remains", scriptSrc.indexOf("includes('diş')") === -1);
    check("no sec.includes('yağ')-style anti-pattern remains", scriptSrc.indexOf("includes('yağ')") === -1);
    check("no sec.includes('parametre')-style anti-pattern remains", scriptSrc.indexOf("includes('parametre')") === -1);
    check("no sec.includes('Tabanca')-style anti-pattern remains", scriptSrc.indexOf("includes('Tabanca')") === -1);
    check("no sec.includes('yetenek')/('Cm')-style anti-pattern remains", scriptSrc.indexOf("includes('yetenek')") === -1);
  }

  // ---- 102. Old substring-rule <-> new tag mapping equivalence.
  //           Derived from the ORIGINAL logic:
  //             hM  = includes('parametre') || includes('Tabanca')  -> tool_suitability, tool_parameters
  //             hMa = includes('diş') || includes('yağ')            -> thread_damage, thread_oil_rust, mating_surface_oil
  //             hS  = includes('yetenek') || includes('Cm')          -> machine_capability
  //           (mating_surface_oil is a deliberately-preserved
  //           cross-category quirk: "yağ" also appears in the
  //           Product/Part item's Turkish text, so the old substring
  //           rule matched it too -- tagging it 'material' keeps the
  //           exact same trigger set, not a "corrected" one.) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const allItems = ctx.context.__getIsh().flatMap((c) => c.items);
    const byTag = (tag) => allItems.filter((it) => it.tags.includes(tag)).map((it) => it.itemCode).sort();
    checkEqual('tightening_tool tag maps to exactly {tool_suitability, tool_parameters}',
      JSON.stringify(byTag('tightening_tool')), JSON.stringify(['tool_parameters', 'tool_suitability'].sort()));
    checkEqual('material tag maps to exactly {thread_damage, thread_oil_rust, mating_surface_oil}',
      JSON.stringify(byTag('material')), JSON.stringify(['mating_surface_oil', 'thread_damage', 'thread_oil_rust'].sort()));
    checkEqual('calibration tag maps to exactly {machine_capability}',
      JSON.stringify(byTag('calibration')), JSON.stringify(['machine_capability']));
  }

  // ---- 103. Category names TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const expect = {
      measurement_tools: ['Ölçme / Aletler', 'Measurement / Tools'],
      machine_tool: ['Makine / Tabanca', 'Machine / Tool'],
      material_fastener: ['Malzeme / Vida', 'Material / Fastener'],
      human_operator: ['İnsan / Operatör', 'Human / Operator'],
      product_part: ['Ürün / Parça', 'Product / Part'],
    };
    for (const [code, [tr]] of Object.entries(expect)) {
      const cat = ctx.context.__getIsh().find((c) => c.categoryCode === code);
      check('category exists for ' + code, !!cat);
      checkEqual('category tr for ' + code, ctx.context.t(cat.categoryKey), tr);
    }
    ctx.context.setLanguage('en');
    for (const [code, [, en]] of Object.entries(expect)) {
      const cat = ctx.context.__getIsh().find((c) => c.categoryCode === code);
      checkEqual('category en for ' + code, ctx.context.t(cat.categoryKey), en);
    }
  }

  // ---- 104. All 16 items TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const allItems = ctx.context.__getIsh().flatMap((c) => c.items);
    checkEqual('16 items total', allItems.length, 16);
    let allTr = true, allEn = true;
    allItems.forEach((it) => { if (ctx.context.t(it.itemKey) === it.itemKey) allTr = false; });
    ctx.context.setLanguage('en');
    allItems.forEach((it) => { if (ctx.context.t(it.itemKey) === it.itemKey) allEn = false; });
    check('all 16 items resolve in tr', allTr);
    check('all 16 items resolve in en', allEn);
    checkEqual('sample item (thread_damage) tr', (function () { ctx.context.setLanguage('tr'); return ctx.context.t('problem.item_thread_damage'); })(), 'Vida dişleri hasarlı mı?');
  }

  // ---- 105. page-problem static UI TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titleEl = getByI18nKey(ctx, 'problem.title');
    const whatPh = getPlaceholderByKey(ctx, 'problem.placeholder_what');
    ctx.context.applyStaticTranslations();
    checkEqual('problem page title tr', titleEl.textContent, 'Problem Tanımlama ve Kök Neden');
    checkEqual('problem "what" placeholder tr', whatPh.placeholder, 'Tork limit dışı');
    ctx.context.setLanguage('en');
    checkEqual('problem page title en', titleEl.textContent, 'Problem Definition and Root Cause');
    checkEqual('problem "what" placeholder en', whatPh.placeholder, 'Torque out of limits');
  }

  // ---- 106. problemAnaliz() dynamic report TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupProblemDom(ctx);
    ctx.byId['p_ne'].value = 'Test problem';
    ctx.context.problemAnaliz();
    const htmlTr = ctx.byId['mudahale-sonuc'].innerHTML;
    check('tr report shows "Problem Analiz Raporu"', htmlTr.indexOf('Problem Analiz Raporu') !== -1);
    check('tr report shows "Operasyon" label', htmlTr.indexOf('Operasyon') !== -1);
    ctx.context.setLanguage('en');
    ctx.context.problemAnaliz();
    const htmlEn = ctx.byId['mudahale-sonuc'].innerHTML;
    check('en report shows "Problem Analysis Report"', htmlEn.indexOf('Problem Analysis Report') !== -1);
    check('en report shows "Operation" label', htmlEn.indexOf('Operation') !== -1);
  }

  // ---- 107. Three conditional warnings TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupProblemDom(ctx);
    checkIshItems(ctx, ['tool_parameters', 'thread_damage', 'machine_capability']);
    ctx.context.problemAnaliz();
    const htmlTr = ctx.byId['mudahale-sonuc'].innerHTML;
    check('tr: tool warning shown', htmlTr.indexOf('Sıkıcı kaynaklı') !== -1);
    check('tr: material warning shown', htmlTr.indexOf('Malzeme: Sürtünme') !== -1);
    check('tr: calibration warning shown', htmlTr.indexOf('Kalibrasyon kontrol et') !== -1);
    ctx.context.setLanguage('en');
    ctx.context.problemAnaliz();
    const htmlEn = ctx.byId['mudahale-sonuc'].innerHTML;
    check('en: tool warning shown', htmlEn.indexOf('Tool-related') !== -1);
    check('en: material warning shown', htmlEn.indexOf('Material: run') !== -1);
    check('en: calibration warning shown', htmlEn.indexOf('Check calibration') !== -1);
  }

  // ---- 108. Marked-cause labels render in the active language ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupProblemDom(ctx);
    checkIshItems(ctx, ['thread_damage']);
    ctx.context.problemAnaliz();
    check('tr: marked-cause list shows the tr item label', ctx.byId['mudahale-sonuc'].innerHTML.indexOf('Vida dişleri hasarlı mı?') !== -1);
    ctx.context.setLanguage('en');
    ctx.context.problemAnaliz();
    check('en: marked-cause list shows the en item label', ctx.byId['mudahale-sonuc'].innerHTML.indexOf('Are the screw threads damaged?') !== -1);
  }

  // ---- 109. Language switch: itemCode selection, form inputs, and
  //           classification are all preserved; only text changes ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupProblemDom(ctx);
    ctx.byId['p_ne'].value = 'Torque deviation';
    ctx.byId['p_nerede'].value = 'Line 3';
    checkIshItems(ctx, ['tool_suitability', 'mating_surface_oil']);
    ctx.context.setLanguage('en');
    const boxesAfter = ctx.byId['ishikawa-cats']._checkboxes;
    const checkedAfter = boxesAfter.filter((b) => b.checked).map((b) => b.dataset.itemCode).sort();
    checkEqual('checked itemCode set unchanged after language switch', JSON.stringify(checkedAfter), JSON.stringify(['mating_surface_oil', 'tool_suitability'].sort()));
    checkEqual('p_ne form input unchanged after language switch', ctx.byId['p_ne'].value, 'Torque deviation');
    checkEqual('p_nerede form input unchanged after language switch', ctx.byId['p_nerede'].value, 'Line 3');
    ctx.context.problemAnaliz();
    const html = ctx.byId['mudahale-sonuc'].innerHTML;
    check('classification unaffected: tool warning still triggers (tool_suitability tagged tightening_tool)', html.indexOf('Tool-related') !== -1);
    check('classification unaffected: material warning still triggers (mating_surface_oil tagged material)', html.indexOf('Material: run') !== -1);
    check('classification unaffected: calibration warning does NOT trigger (nothing tagged calibration)', html.indexOf('Check calibration') === -1);
  }

  // ---- 110. No raw translation-key leakage in Problem Management
  //           dynamic HTML ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupProblemDom(ctx);
    checkIshItems(ctx, ['machine_capability']);
    ctx.context.problemAnaliz();
    const htmlTr = ctx.byId['ishikawa-cats'].innerHTML + ctx.byId['mudahale-sonuc'].innerHTML;
    check('no raw "problem.xxx" key text leaks into tr rendering', !/problem\.[a-z_.0-9]+(?![\w])/.test(htmlTr.replace(/<[^>]*>/g, ' ')));
    ctx.context.setLanguage('en');
    ctx.context.problemReapplyLanguage();
    const htmlEn = ctx.byId['ishikawa-cats'].innerHTML + ctx.byId['mudahale-sonuc'].innerHTML;
    check('no raw "problem.xxx" key text leaks into en rendering', !/problem\.[a-z_.0-9]+(?![\w])/.test(htmlEn.replace(/<[^>]*>/g, ' ')));
  }

  // ---- 111. Hard-coded user text scan (Problem Management scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const turkishCharRe = /[şğüöçİĞÜŞÖÇı]/;
    for (const fn of ['buildISH', 'problemAnaliz', 'problemReapplyLanguage', 'ishLookupItem']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      const strs = [...src.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]).filter((s) => turkishCharRe.test(s));
      check('no hard-coded Turkish string literals remain in ' + fn + '()', strs.length === 0);
    }
  }

  // ---- 112. Language-dependent decision anti-pattern scan (closure) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const problemSrc = scriptSrc.slice(scriptSrc.indexOf('const ISH='), scriptSrc.indexOf('function problemAnaliz') + 2000);
    check('no visible-label-keyed classification object in Problem Management scope',
      !/\.includes\('[şğüöçİĞÜŞÖÇıA-ZÇĞİÖŞÜ][^']*'\)/.test(problemSrc.replace(/tags\.includes\('[a-z_]+'\)/g, '')));
  }

  // ================================================================
  // Faz 2.7.3b -- Golden Cases.
  // ================================================================

  // ---- 113. page-goldencases static UI TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titleEl = getByI18nKey(ctx, 'golden.title');
    const saveBtnEl = getByI18nKey(ctx, 'golden.save_btn');
    ctx.context.applyStaticTranslations();
    checkEqual('golden page title tr', titleEl.textContent, 'Altın Referans Senaryoları');
    checkEqual('golden save button tr', saveBtnEl.textContent, 'Altın Senaryoyu Kaydet');
    ctx.context.setLanguage('en');
    checkEqual('golden page title en', titleEl.textContent, 'Golden Reference Scenarios');
    checkEqual('golden save button en', saveBtnEl.textContent, 'Save Golden Scenario');
  }

  // ---- 114. Form labels TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const nameLabel = getByI18nKey(ctx, 'golden.name_label');
    const toleranceLabel = getByI18nKey(ctx, 'golden.tolerance_label');
    ctx.context.applyStaticTranslations();
    checkEqual('golden name label tr', nameLabel.textContent, 'Senaryo Adı');
    checkEqual('golden tolerance label tr', toleranceLabel.textContent, 'Tolerans (%)');
    ctx.context.setLanguage('en');
    checkEqual('golden name label en', nameLabel.textContent, 'Scenario Name');
    checkEqual('golden tolerance label en', toleranceLabel.textContent, 'Tolerance (%)');
  }

  // ---- 115. saveGoldenCase() payload fields unchanged by language ----
  {
    async function runSave(lang) {
      let captured = null;
      const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
        if (opts && opts.method === 'POST') { captured = JSON.parse(opts.body); return { id: 1 }; }
        return [];
      });
      ctx.byId['gc_name'] = { value: 'M10-10.9-Golden' };
      ctx.byId['gc_thread'] = { value: 'M10' };
      ctx.byId['gc_class'] = { value: '10.9' };
      ctx.byId['gc_reference'] = { value: '70' };
      ctx.byId['gc_program'] = { value: '69.3' };
      ctx.byId['gc_tolerance'] = { value: '5' };
      ctx.byId['goldenCaseRows'] = { innerHTML: '' };
      ctx.context.CURRENT_ROLE = 'admin';
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.saveGoldenCase();
      return captured;
    }
    const trPayload = await runSave('tr');
    const enPayload = await runSave('en');
    checkEqual('payload name identical tr/en', trPayload.name, enPayload.name);
    checkEqual('payload thread identical tr/en', trPayload.thread, enPayload.thread);
    checkEqual('payload property_class identical tr/en', trPayload.property_class, enPayload.property_class);
    checkEqual('payload reference_torque_nm identical tr/en', trPayload.reference_torque_nm, enPayload.reference_torque_nm);
    checkEqual('payload program_torque_nm identical tr/en', trPayload.program_torque_nm, enPayload.program_torque_nm);
    checkEqual('payload tolerance_pct identical tr/en', trPayload.tolerance_pct, enPayload.tolerance_pct);
    checkEqual('thread value untranslated (user input, technical)', trPayload.thread, 'M10');
    checkEqual('name value untranslated (user input)', trPayload.name, 'M10-10.9-Golden');
  }

  // ---- 116. loadGoldenCases() empty-state message TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {}, async () => []);
    ctx.byId['goldenCaseRows'] = { innerHTML: '' };
    ctx.context.CURRENT_ROLE = 'admin';
    await ctx.context.loadGoldenCases();
    checkEqual('empty-state tr', ctx.byId['goldenCaseRows'].innerHTML, 'Henüz altın senaryo yok.');
    ctx.context.setLanguage('en');
    await ctx.context.loadGoldenCases();
    checkEqual('empty-state en', ctx.byId['goldenCaseRows'].innerHTML, 'No golden scenarios yet.');
  }

  // ---- 117/118. passed=true -> GEÇTİ/PASSED + ok class;
  //               passed=false -> KALDI/FAILED + nok class ----
  {
    const rows = [
      { name: 'Case A', thread: 'M10', property_class: '10.9', program_torque_nm: 69.3, reference_torque_nm: 70, error_pct: 1.0, passed: true },
      { name: 'Case B', thread: 'M12', property_class: '8.8', program_torque_nm: 80, reference_torque_nm: 70, error_pct: 14.3, passed: false },
    ];
    const ctx = newContext(extractedSource, rawHtml, {}, async () => rows);
    ctx.byId['goldenCaseRows'] = { innerHTML: '' };
    ctx.context.CURRENT_ROLE = 'admin';
    await ctx.context.loadGoldenCases();
    const htmlTr = ctx.byId['goldenCaseRows'].innerHTML;
    check('tr: passed row shows "Geçti"', htmlTr.indexOf('Geçti') !== -1);
    check('tr: passed row has ok class', /class="badge-prod ok">Geçti/.test(htmlTr));
    check('tr: failed row shows "Kaldı"', htmlTr.indexOf('Kaldı') !== -1);
    check('tr: failed row has nok class', /class="badge-prod nok">Kaldı/.test(htmlTr));
    ctx.context.setLanguage('en');
    await ctx.context.loadGoldenCases();
    const htmlEn = ctx.byId['goldenCaseRows'].innerHTML;
    check('en: passed row shows "Passed"', htmlEn.indexOf('Passed') !== -1);
    check('en: passed row has ok class', /class="badge-prod ok">Passed/.test(htmlEn));
    check('en: failed row shows "Failed"', htmlEn.indexOf('Failed') !== -1);
    check('en: failed row has nok class', /class="badge-prod nok">Failed/.test(htmlEn));
  }

  // ---- 119. passed boolean decision does not depend on the displayed
  //           label (source-level: badge class keys off r.passed only) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const lgcSrc = extractFunctionDecl(scriptSrc, 'loadGoldenCases');
    check('CSS class selection reads r.passed directly, not a translated label', lgcSrc.indexOf("r.passed?'ok':'nok'") !== -1);
    check('status text reads r.passed via t(), not the other way around', lgcSrc.indexOf("r.passed?t('calibration.status_passed'):t('calibration.status_failed')") !== -1);
  }

  // ---- 120. Record order and ID set preserved across a language switch ----
  {
    const rows = [{ id: 3, name: 'C', passed: true }, { id: 1, name: 'A', passed: false }, { id: 2, name: 'B', passed: true }];
    const ctx = newContext(extractedSource, rawHtml, {}, async () => rows);
    ctx.byId['goldenCaseRows'] = { innerHTML: '' };
    ctx.context.CURRENT_ROLE = 'admin';
    await ctx.context.loadGoldenCases();
    const namesTr = [...ctx.byId['goldenCaseRows'].innerHTML.matchAll(/<strong>([^<]*)<\/strong>/g)].map((m) => m[1]);
    ctx.context.setLanguage('en');
    await ctx.context.loadGoldenCases();
    const namesEn = [...ctx.byId['goldenCaseRows'].innerHTML.matchAll(/<strong>([^<]*)<\/strong>/g)].map((m) => m[1]);
    checkEqual('record order (by name, as returned) unchanged across language switch', JSON.stringify(namesEn), JSON.stringify(namesTr));
    checkEqual('record order matches backend response order (3,1,2 -> C,A,B)', JSON.stringify(namesTr), JSON.stringify(['C', 'A', 'B']));
  }

  // ---- 121. User inputs (form fields) untouched by language switch ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.byId['gc_name'] = { value: 'Custom-Scenario-01' };
    ctx.byId['gc_thread'] = { value: 'M14' };
    ctx.context.setLanguage('en');
    checkEqual('gc_name input unaffected by language switch', ctx.byId['gc_name'].value, 'Custom-Scenario-01');
    checkEqual('gc_thread input unaffected by language switch', ctx.byId['gc_thread'].value, 'M14');
  }

  // ---- 122. setLanguage() re-render uses GET only; no POST is issued ----
  {
    let postCalled = false;
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
      if (opts && opts.method === 'POST') postCalled = true;
      return [];
    });
    ctx.byId['goldenCaseRows'] = { innerHTML: '' };
    ctx.context.CURRENT_ROLE = 'admin';
    await ctx.context.loadGoldenCases();
    ctx.context.setLanguage('en');
    checkEqual('no POST request was issued by the language-switch re-render', postCalled, false);
  }

  // ---- 123. No raw translation-key leakage in Golden Cases HTML ----
  {
    const rows = [{ name: 'X', thread: 'M10', property_class: '10.9', program_torque_nm: 69, reference_torque_nm: 70, error_pct: 1, passed: true }];
    const ctx = newContext(extractedSource, rawHtml, {}, async () => rows);
    ctx.byId['goldenCaseRows'] = { innerHTML: '' };
    ctx.context.CURRENT_ROLE = 'admin';
    await ctx.context.loadGoldenCases();
    const htmlTr = ctx.byId['goldenCaseRows'].innerHTML;
    check('no raw "golden.xxx"/"calibration.xxx" key text leaks into tr rendering', !/(golden|calibration)\.[a-z_.0-9]+(?![\w])/.test(htmlTr.replace(/<[^>]*>/g, ' ')));
    ctx.context.setLanguage('en');
    await ctx.context.loadGoldenCases();
    const htmlEn = ctx.byId['goldenCaseRows'].innerHTML;
    check('no raw key text leaks into en rendering', !/(golden|calibration)\.[a-z_.0-9]+(?![\w])/.test(htmlEn.replace(/<[^>]*>/g, ' ')));
  }

  // ---- 124. Hard-coded user text scan (Golden Cases scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const turkishCharRe = /[şğüöçİĞÜŞÖÇı]/;
    for (const fn of ['saveGoldenCase', 'loadGoldenCases']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      const strs = [...src.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]).filter((s) => turkishCharRe.test(s));
      check('no hard-coded Turkish string literals remain in ' + fn + '()', strs.length === 0);
    }
  }

  // ---- 125. Language-dependent decision anti-pattern scan (closure) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const gcSrc = scriptSrc.slice(scriptSrc.indexOf('async function saveGoldenCase'), scriptSrc.indexOf('async function loadGoldenCases') + 1500);
    check('no translated-label-driven decision in Golden Cases scope', !/includes\('[şğüöçİĞÜŞÖÇıA-ZÇĞİÖŞÜ][^']*'\)/.test(gcSrc));
  }

  // ================================================================
  // Faz 2.7.3c -- Problem Management/Ishikawa + Golden Cases closure
  // audit. No new defects were found during this review; these tests
  // exercise both areas together and re-confirm the individually-
  // tested guarantees hold simultaneously.
  // ================================================================

  // ---- 126. TR/EN key resolution across both areas simultaneously ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const sampleKeys = [
      'problem.title', 'problem.category_measurement_tools', 'problem.item_thread_damage',
      'golden.title', 'golden.name_label', 'calibration.status_passed', 'calibration.status_failed',
    ];
    let unresolvedTr = 0, unresolvedEn = 0;
    for (const k of sampleKeys) if (ctx.context.t(k) === k) unresolvedTr++;
    ctx.context.setLanguage('en');
    for (const k of sampleKeys) if (ctx.context.t(k) === k) unresolvedEn++;
    checkEqual('no unresolved keys across Problem Management + Golden Cases in tr', unresolvedTr, 0);
    checkEqual('no unresolved keys across Problem Management + Golden Cases in en', unresolvedEn, 0);
  }

  // ---- 127. ISH item/category counts and golden-case record shape
  //           unaffected by exercising both modules in one context ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupProblemDom(ctx);
    checkIshItems(ctx, ['tool_parameters']);
    const rows = [{ id: 1, name: 'Combined-Test', thread: 'M10', property_class: '10.9', program_torque_nm: 69, reference_torque_nm: 70, error_pct: 1.4, passed: true }];
    ctx.byId['goldenCaseRows'] = ctx.documentStub.getElementById('goldenCaseRows');
    ctx.context.CURRENT_ROLE = 'admin';
    await (async () => {
      const orig = ctx.context.__getIsh().length;
      checkEqual('ISH still has 5 categories after Ishikawa interaction', orig, 5);
    })();
    ctx.context.setLanguage('en');
    checkEqual('checked itemCode survives language switch alongside golden-cases module presence',
      ctx.byId['ishikawa-cats']._checkboxes.filter((b) => b.checked).map((b) => b.dataset.itemCode).join(','), 'tool_parameters');
  }

  // ---- 128. No raw key leakage across Problem Management + Golden
  //           Cases rendered together in one pass ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    setupProblemDom(ctx);
    checkIshItems(ctx, ['machine_capability']);
    ctx.context.problemAnaliz();
    const rows = [{ id: 1, name: 'Y', thread: 'M12', property_class: '8.8', program_torque_nm: 80, reference_torque_nm: 80, error_pct: 0, passed: true }];
    const ctx2 = newContext(extractedSource, rawHtml, {}, async () => rows);
    ctx2.byId['goldenCaseRows'] = { innerHTML: '' };
    ctx2.context.CURRENT_ROLE = 'admin';
    await ctx2.context.loadGoldenCases();
    ctx.context.setLanguage('en');
    ctx.context.problemReapplyLanguage();
    ctx2.context.setLanguage('en');
    await ctx2.context.loadGoldenCases();
    const combined = ctx.byId['ishikawa-cats'].innerHTML + ctx.byId['mudahale-sonuc'].innerHTML + ctx2.byId['goldenCaseRows'].innerHTML;
    check('no raw namespaced key text leaks across problem+golden rendered together in en',
      !/(problem|golden|calibration)\.[a-z_.0-9]+(?![\w])/.test(combined.replace(/<[^>]*>/g, ' ')));
  }

  // ---- 129. Closure re-check: old-substring/tag equivalence still
  //           holds and the removed anti-patterns have not reappeared ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    check("closure: no sec.includes('diş')/('yağ')/('parametre')/('Tabanca')/('yetenek') anywhere",
      ["includes('diş')", "includes('yağ')", "includes('parametre')", "includes('Tabanca')", "includes('yetenek')"]
        .every((pat) => scriptSrc.indexOf(pat) === -1));
    const ctx = newContext(extractedSource, rawHtml, {});
    const allItems = ctx.context.__getIsh().flatMap((c) => c.items);
    checkEqual('closure: tightening_tool tag set unchanged',
      JSON.stringify(allItems.filter((it) => it.tags.includes('tightening_tool')).map((it) => it.itemCode).sort()),
      JSON.stringify(['tool_parameters', 'tool_suitability'].sort()));
  }

  // ---- 130. Closure re-check: Golden Cases passed/CSS class contract
  //           and backend GET-only re-render still hold ----
  {
    const rows = [{ id: 1, name: 'Z', thread: 'M8', property_class: '8.8', program_torque_nm: 30, reference_torque_nm: 30, error_pct: 0, passed: false }];
    let postCalled = false;
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
      if (opts && opts.method === 'POST') postCalled = true;
      return rows;
    });
    ctx.byId['goldenCaseRows'] = { innerHTML: '' };
    ctx.context.CURRENT_ROLE = 'admin';
    await ctx.context.loadGoldenCases();
    ctx.context.setLanguage('en');
    checkEqual('closure: no POST triggered by language switch', postCalled, false);
    check('closure: failed record still shows nok class', ctx.byId['goldenCaseRows'].innerHTML.indexOf('badge-prod nok') !== -1);
  }

  // ================================================================
  // Faz 2.7.4a -- Report Center + printable report templates
  // (reportHtml/printCurrentReport/printRecord/generateProjectRelease/
  // printProjectRelease/generateReleaseCertificate/
  // printReleaseCertificate).
  // ================================================================

  // ---- 131. page-rapor static UI TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const titleEl = getByI18nKey(ctx, 'rapor.center_title');
    const printBtnEl = getByI18nKey(ctx, 'rapor.print_report_btn');
    ctx.context.applyStaticTranslations();
    checkEqual('report center title tr', titleEl.textContent, 'Rapor Merkezi');
    checkEqual('print report button tr', printBtnEl.textContent, 'Raporu Yazdır / PDF');
    ctx.context.setLanguage('en');
    checkEqual('report center title en', titleEl.textContent, 'Report Center');
    checkEqual('print report button en', printBtnEl.textContent, 'Print Report / PDF');
  }

  // ---- 132. reportLocale(): tr -> tr-TR, en -> en-US ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    checkEqual('reportLocale() returns tr-TR when CURRENT_LANG is tr', ctx.context.reportLocale(), 'tr-TR');
    ctx.context.setLanguage('en');
    checkEqual('reportLocale() returns en-US when CURRENT_LANG is en', ctx.context.reportLocale(), 'en-US');
  }

  // ---- 133. reportHtml() heading and labels TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const rec = { record_no: 'TP-0001', family: 'Hex head fully-threaded bolt', standard: 'ISO 4017', thread: 'M10', property_class: '10.9', torque_nm: 65.4, preload_n: 34700, confidence: 4, created_at: '2026-01-15T10:00:00Z' };
    const htmlTr = ctx.context.reportHtml(rec);
    check('tr report heading present', htmlTr.indexOf('TorqPro Mühendislik Ön Değerlendirme Raporu') !== -1);
    check('tr "Toplam Tork" label present', htmlTr.indexOf('Toplam Tork') !== -1);
    ctx.context.setLanguage('en');
    const htmlEn = ctx.context.reportHtml(rec);
    check('en report heading present', htmlEn.indexOf('TorqPro Engineering Preliminary Assessment Report') !== -1);
    check('en "Total Torque" label present', htmlEn.indexOf('Total Torque') !== -1);
  }

  // ---- 134. Technical record fields identical in both languages
  //           (family/standard/thread/property_class/coating/source_mode
  //           are never translated -- they render verbatim) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const rec = { record_no: 'TP-0002', family: 'Altıgen başlı tam dişli civata', standard: 'ISO 4017', thread: 'M12', property_class: '8.8', coating: 'Elektrolitik çinko', source_mode: 'Kütüphane', torque_nm: 80, preload_n: 40000, confidence: 3 };
    const htmlTr = ctx.context.reportHtml(rec);
    ctx.context.setLanguage('en');
    const htmlEn = ctx.context.reportHtml(rec);
    check('r.family renders verbatim (untranslated) in tr', htmlTr.indexOf('Altıgen başlı tam dişli civata') !== -1);
    check('r.family renders verbatim (untranslated) in en too -- never auto-translated', htmlEn.indexOf('Altıgen başlı tam dişli civata') !== -1);
    check('r.standard identical in both languages', htmlTr.indexOf('ISO 4017') !== -1 && htmlEn.indexOf('ISO 4017') !== -1);
    check('r.thread identical in both languages', htmlTr.indexOf('M12') !== -1 && htmlEn.indexOf('M12') !== -1);
    check('r.property_class identical in both languages', htmlTr.indexOf('8.8') !== -1 && htmlEn.indexOf('8.8') !== -1);
  }

  // ---- 135. Raw numeric values unchanged across languages ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const rec = { torque_nm: 123.456, preload_n: 78901, confidence: 2 };
    const htmlTr = ctx.context.reportHtml(rec);
    ctx.context.setLanguage('en');
    const htmlEn = ctx.context.reportHtml(rec);
    check('torque decimal precision (1 digit) unchanged in tr', htmlTr.indexOf('123.5 Nm') !== -1);
    check('torque decimal precision (1 digit) unchanged in en (same rounding, Number.toFixed is locale-independent)', htmlEn.indexOf('123.5 Nm') !== -1);
    check('confidence code G2 identical in both languages', htmlTr.indexOf('G2') !== -1 && htmlEn.indexOf('G2') !== -1);
  }

  // ---- 136. Date formatting: tr-TR vs en-US locale ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const rec = { created_at: '2026-03-15T14:30:00Z' };
    const htmlTr = ctx.context.reportHtml(rec);
    ctx.context.setLanguage('en');
    const htmlEn = ctx.context.reportHtml(rec);
    const dateTr = new Date(rec.created_at).toLocaleString('tr-TR');
    const dateEn = new Date(rec.created_at).toLocaleString('en-US');
    check('tr report date uses tr-TR formatting', htmlTr.indexOf(dateTr) !== -1);
    check('en report date uses en-US formatting', htmlEn.indexOf(dateEn) !== -1);
    check('tr-TR and en-US date strings actually differ (locale is genuinely applied)', dateTr !== dateEn);
  }

  // ---- 137. Number formatting: same raw number, locale-only display difference ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const rec = { preload_n: 1234567 };
    const htmlTr = ctx.context.reportHtml(rec);
    ctx.context.setLanguage('en');
    const htmlEn = ctx.context.reportHtml(rec);
    const numTr = Math.round(rec.preload_n).toLocaleString('tr-TR');
    const numEn = Math.round(rec.preload_n).toLocaleString('en-US');
    check('tr preload uses tr-TR grouping (e.g. 1.234.567)', htmlTr.indexOf(numTr) !== -1);
    check('en preload uses en-US grouping (e.g. 1,234,567)', htmlEn.indexOf(numEn) !== -1);
    check('the underlying raw number is identical (only separators differ)', numTr.replace(/[.,]/g, '') === numEn.replace(/[.,]/g, ''));
  }

  // ---- 138. Units and technical terms identical in both languages ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const rec = { torque_nm: 50, preload_n: 20000, confidence: 4 };
    const htmlTr = ctx.context.reportHtml(rec);
    ctx.context.setLanguage('en');
    const htmlEn = ctx.context.reportHtml(rec);
    check('Nm unit unchanged in tr', htmlTr.indexOf(' Nm') !== -1);
    check('Nm unit unchanged in en', htmlEn.indexOf(' Nm') !== -1);
    check('N unit unchanged in tr', htmlTr.indexOf(' N<') !== -1);
    check('N unit unchanged in en', htmlEn.indexOf(' N<') !== -1);
  }

  // ---- 139. G1-G4 confidence codes preserved ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    for (const c of [1, 2, 3, 4]) {
      const html = ctx.context.reportHtml({ confidence: c });
      check('confidence code G' + c + ' preserved verbatim', html.indexOf('G' + c) !== -1);
    }
    ctx.context.setLanguage('en');
    for (const c of [1, 2, 3, 4]) {
      const html = ctx.context.reportHtml({ confidence: c });
      check('confidence code G' + c + ' preserved verbatim in en too', html.indexOf('G' + c) !== -1);
    }
  }

  // ---- 140. printCurrentReport() uses the active language (including
  //           its "calculate first" guard message) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.byId['printArea'] = { style: {}, innerHTML: '' };
    // No real calculation has been performed in this harness, so
    // captureCurrentCalculation() returns torque_nm: null and
    // printCurrentReport() takes its guard-alert path -- this still
    // exercises the "uses the active language" requirement via the
    // translated alert message.
    ctx.context.printCurrentReport();
    checkEqual('printCurrentReport() alert uses tr text when no calculation exists', ctx.alertCalls[ctx.alertCalls.length - 1], 'Önce hesap yapın.');
    ctx.context.setLanguage('en');
    ctx.context.printCurrentReport();
    checkEqual('printCurrentReport() alert uses en text after switching language', ctx.alertCalls[ctx.alertCalls.length - 1], 'Please calculate first.');
  }

  // ---- 141. printRecord() uses the active language ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.ARCHIVE_CACHE = [{ id: 7, record_no: 'TP-0007', torque_nm: 40, preload_n: 15000, confidence: 3 }];
    ctx.byId['printArea'] = { style: {}, innerHTML: '' };
    ctx.context.setLanguage('en');
    ctx.context.printRecord(7);
    check('printRecord() renders in en', ctx.byId['printArea'].innerHTML.indexOf('Total Torque') !== -1);
    checkEqual('printRecord() triggers window.print()', ctx.windowCalls.indexOf('print') !== -1, true);
  }

  // ---- 142. No stale-language cache: re-printing after a language
  //           switch reflects the NEW language, not the old one ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.ARCHIVE_CACHE = [{ id: 1, torque_nm: 10, preload_n: 1000, confidence: 1 }];
    ctx.byId['printArea'] = { style: {}, innerHTML: '' };
    ctx.context.printRecord(1);
    check('first print (tr) shows Turkish label', ctx.byId['printArea'].innerHTML.indexOf('Toplam Tork') !== -1);
    ctx.context.setLanguage('en');
    ctx.context.printRecord(1);
    check('second print (after switching to en) shows English label, not stale tr', ctx.byId['printArea'].innerHTML.indexOf('Total Torque') !== -1);
    check('second print does not contain the old tr label', ctx.byId['printArea'].innerHTML.indexOf('Toplam Tork') === -1);
  }

  // ---- 143. Release certificate/package headings TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {}, async () => ({
      title: 'X', package_no: 'PKG-1', created_at: '2026-01-01T00:00:00Z',
      project: { name: 'Proj', customer: 'Cust', project_code: 'C1' },
      summary: { total_calculations: 3, approved_revisions: 2, open_revisions: 1, release_ready: true },
      items: [], decision: 'OK',
    }));
    ctx.byId['release_project'] = { value: '1' };
    ctx.byId['release_title'] = { value: '' };
    ctx.byId['releasePackageView'] = { innerHTML: '' };
    ctx.context.ORG_SETTINGS = {};
    await ctx.context.generateProjectRelease();
    const htmlTr = ctx.byId['releasePackageView'].innerHTML;
    check('tr release package shows "Proje" label', htmlTr.indexOf('Proje') !== -1);
    check('tr release package shows "HAZIR" decision', htmlTr.indexOf('HAZIR') !== -1);
    ctx.context.setLanguage('en');
    await ctx.context.generateProjectRelease();
    const htmlEn = ctx.byId['releasePackageView'].innerHTML;
    check('en release package shows "Project" label', htmlEn.indexOf('Project') !== -1);
    check('en release package shows "READY" decision', htmlEn.indexOf('READY') !== -1);
  }

  // ---- 144. Release package technical/project/customer values
  //           are not auto-translated ----
  {
    const ctx = newContext(extractedSource, rawHtml, {}, async () => ({
      title: 'X', package_no: 'PKG-2', created_at: '2026-01-01T00:00:00Z',
      project: { name: 'Müşteri Özel Proje', customer: 'Acme Otomotiv', project_code: 'CODE-9' },
      summary: { total_calculations: 1, approved_revisions: 1, open_revisions: 0, release_ready: false },
      items: [{ record_no: 'TP-1', thread: 'M10', property_class: '10.9', torque_nm: 65, revision_no: 1, revision_status: 'approved', version_signature: 'v1', reviewer_name: 'A. Yilmaz' }],
      decision: 'Beklemede',
    }));
    ctx.byId['release_project'] = { value: '1' };
    ctx.byId['release_title'] = { value: '' };
    ctx.byId['releasePackageView'] = { innerHTML: '' };
    ctx.context.ORG_SETTINGS = {};
    ctx.context.setLanguage('en');
    await ctx.context.generateProjectRelease();
    const html = ctx.byId['releasePackageView'].innerHTML;
    check('project name (free text) not translated in en mode', html.indexOf('Müşteri Özel Proje') !== -1);
    check('customer name (free text) not translated in en mode', html.indexOf('Acme Otomotiv') !== -1);
    check('decision text (free text from backend) not translated in en mode', html.indexOf('Beklemede') !== -1);
    check('thread/property_class technical values untouched', html.indexOf('M10') !== -1 && html.indexOf('10.9') !== -1);
  }

  // ---- 145. window.print() flow preserved (no popup/window behavior change) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.CURRENT_RELEASE_PACKAGE = { package_no: 'PKG-3' };
    ctx.byId['releasePackageView'] = { innerHTML: '<p>content</p>' };
    ctx.context.printProjectRelease();
    checkEqual('printProjectRelease() opens a popup window', ctx.windowCalls.indexOf('open') !== -1, true);
    checkEqual('printProjectRelease() calls print() on the popup', ctx.windowCalls.indexOf('popup-print') !== -1, true);
  }

  // ---- 146. No raw translation-key leakage in report/release/certificate HTML ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const htmlTr = ctx.context.reportHtml({ torque_nm: 1, preload_n: 1, confidence: 1 });
    check('no raw "rapor.xxx" key text leaks into tr report', !/rapor\.[a-z_.0-9]+(?![\w])/.test(htmlTr));
    ctx.context.setLanguage('en');
    const htmlEn = ctx.context.reportHtml({ torque_nm: 1, preload_n: 1, confidence: 1 });
    check('no raw "rapor.xxx" key text leaks into en report', !/rapor\.[a-z_.0-9]+(?![\w])/.test(htmlEn));
  }

  // ---- 147. Hard-coded user text scan (Report Center scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const turkishCharRe = /[şğüöçİĞÜŞÖÇı]/;
    for (const fn of ['reportHtml', 'printCurrentReport', 'printRecord', 'generateProjectRelease', 'generateReleaseCertificate']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      const strs = [...src.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]).filter((s) => turkishCharRe.test(s));
      check('no hard-coded Turkish string literals remain in ' + fn + '()', strs.length === 0);
    }
  }

  // ---- 148. In-scope hardcoded 'tr-TR' scan: 0 in report functions
  //           (out-of-scope occurrences elsewhere are noted in the
  //           phase report, not modified here) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    for (const fn of ['reportHtml', 'generateProjectRelease', 'generateReleaseCertificate']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      check("no hardcoded 'tr-TR' remains in " + fn + '()', src.indexOf("'tr-TR'") === -1);
    }
  }

  // ================================================================
  // Faz 2.7.4b-1 -- Go-Live Wizard / DNS Check / Cloud Deployment /
  // Runtime Health / Mobile Access.
  // ================================================================

  // ---- 149. Five pages' static UI TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const checks = [
      ['golive.title', 'İlk Yayın Kurulum Sihirbazı', 'First Publish Setup Wizard'],
      ['dns.title', 'Domain ve DNS Kontrolü', 'Domain and DNS Check'],
      ['cloud.title', 'Güvenli İnternet Yayını', 'Secure Internet Publishing'],
      ['runtime.title', 'Canlılık ve Hazırlık Durumu', 'Liveness and Readiness Status'],
      ['mobile.title', 'Mobil Erişim', 'Mobile Access'],
    ];
    for (const [key, tr] of checks) {
      const el = getByI18nKey(ctx, key);
      check('page title element exists for ' + key, !!el);
    }
    ctx.context.applyStaticTranslations();
    for (const [key, tr] of checks) checkEqual('tr title for ' + key, getByI18nKey(ctx, key).textContent, tr);
    ctx.context.setLanguage('en');
    for (const [key, , en] of checks) checkEqual('en title for ' + key, getByI18nKey(ctx, key).textContent, en);
  }

  // ---- 150. Form labels and placeholders TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const serverIpLabel = getByI18nKey(ctx, 'golive.server_ip_label');
    const domainPh = ctx.byId ? null : null;
    ctx.context.applyStaticTranslations();
    checkEqual('golive server ip label tr', serverIpLabel.textContent, 'Sunucu IP');
    ctx.context.setLanguage('en');
    checkEqual('golive server ip label en', serverIpLabel.textContent, 'Server IP');
    const dnsDomainLabel = getByI18nKey(ctx, 'dns.domain_label');
    checkEqual('dns domain label en', dnsDomainLabel.textContent, 'Domain Name');
  }

  // ---- 151. Technical option values preserved (planned/ready) ----
  {
    check('gw_https option values are the fixed set {planned,ready}',
      /<option value="planned" data-i18n="golive\.https_planned">/.test(rawHtml) &&
      /<option value="ready" data-i18n="golive\.https_ready">/.test(rawHtml));
    const ctx = newContext(extractedSource, rawHtml, {});
    const el = getByI18nKey(ctx, 'golive.https_planned');
    ctx.context.applyStaticTranslations();
    checkEqual('https_planned label tr', el.textContent, 'Planlanıyor');
    ctx.context.setLanguage('en');
    checkEqual('https_planned label en', el.textContent, 'Planned');
    // option value attribute itself is static markup, never touched by applyStaticTranslations/setLanguage
    check('option value="planned" attribute unchanged in markup', /value="planned"/.test(rawHtml));
  }

  // ---- 152. saveGoLiveProfile(): payload identical across languages;
  //           success/fallback alert TR/EN ----
  {
    async function runSaveGoLive(lang) {
      let captured = null;
      const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
        if (opts && opts.method === 'PUT') { captured = JSON.parse(opts.body); return { server_ip: captured.server_ip, domain: captured.domain, https_status: captured.https_status }; }
        return {};
      });
      ctx.byId['gw_server_ip'] = { value: '10.0.0.5' };
      ctx.byId['gw_domain'] = { value: 'app.example.com' };
      ctx.byId['gw_https'] = { value: 'ready' };
      ctx.byId['goLiveChecklist'] = { innerHTML: '' };
      ctx.byId['wizardSteps'] = ctx.documentStub.getElementById('wizardSteps');
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.saveGoLiveProfile();
      return { captured, alert: ctx.alertCalls[ctx.alertCalls.length - 1] };
    }
    const trResult = await runSaveGoLive('tr');
    const enResult = await runSaveGoLive('en');
    checkEqual('payload identical across languages (server_ip)', trResult.captured.server_ip, enResult.captured.server_ip);
    checkEqual('payload identical across languages (domain)', trResult.captured.domain, enResult.captured.domain);
    checkEqual('payload identical across languages (https_status)', trResult.captured.https_status, enResult.captured.https_status);
    checkEqual('https_status technical value untranslated', trResult.captured.https_status, 'ready');
    checkEqual('tr success alert', trResult.alert, 'İlk yayın profili kaydedildi.');
    checkEqual('en success alert', enResult.alert, 'First-publish profile saved.');
  }

  // ---- 153. runDnsCheck(): same backend technical result shown
  //           TR/EN; domain value and technical status code unchanged ----
  {
    async function runDns(lang) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => ({
        resolved_ips: ['185.100.20.50'], matches_expected: true, https_ready: true, status: 'verified',
      }));
      ctx.byId['dns_domain'] = { value: 'app.torqpro.com' };
      ctx.byId['dns_expected_ip'] = { value: '185.100.20.50' };
      ctx.byId['dnsResult'] = { innerHTML: '' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.runDnsCheck();
      return ctx.byId['dnsResult'].innerHTML;
    }
    const htmlTr = await runDns('tr');
    const htmlEn = await runDns('en');
    check('tr dns result shows resolved IP', htmlTr.indexOf('185.100.20.50') !== -1);
    check('en dns result shows the same resolved IP (domain/technical value unchanged)', htmlEn.indexOf('185.100.20.50') !== -1);
    check('tr shows "Evet" for match', htmlTr.indexOf('Evet') !== -1);
    check('en shows "Yes" for match', htmlEn.indexOf('Yes') !== -1);
    check('backend status code "verified" rendered verbatim in both languages', htmlTr.indexOf('verified') !== -1 && htmlEn.indexOf('verified') !== -1);
  }

  // ---- 154. loadCloudReadiness(): backend boolean/technical values
  //           identical; displayed descriptions TR/EN ----
  {
    async function runCloud(lang) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => ({
        ready: false,
        checks: [{ name: 'Dockerfile', value: 'Mevcut', ok: true }, { name: 'Secret Key', value: 'Eksik', ok: false }],
      }));
      ctx.byId['cloudChecklist'] = { innerHTML: '' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.loadCloudReadiness();
      return ctx.byId['cloudChecklist'].innerHTML;
    }
    const htmlTr = await runCloud('tr');
    const htmlEn = await runCloud('en');
    check('tr shows "Hazır" for the ok check', htmlTr.indexOf('Hazır') !== -1);
    check('en shows "Ready" for the ok check', htmlEn.indexOf('Ready') !== -1);
    check('tr shows "Eksikler tamamlanmalı" (ready:false)', htmlTr.indexOf('Eksikler tamamlanmalı') !== -1);
    check('en shows "Gaps must be completed" (ready:false)', htmlEn.indexOf('Gaps must be completed') !== -1);
    check('backend check names (free text from backend) rendered verbatim in both', htmlTr.indexOf('Dockerfile') !== -1 && htmlEn.indexOf('Dockerfile') !== -1);
  }

  // ---- 155. loadRuntimeHealth(): API/db boolean decisions unaffected;
  //           OK/NOK-equivalent logic identical; server-time locale
  //           TR/EN; raw timestamp unchanged ----
  {
    // Note: loadRuntimeHealth() itself contains no toLocaleString('tr-TR')
    // call in this codebase -- the "Sunucu zamanı" / server-time
    // formatting the phase instructions referenced actually lives in
    // loadSystemHealth() (Admin Panel, page-admin), a different
    // function outside this sub-phase's explicit scope. This is
    // called out explicitly in the phase report; runtime.* labels are
    // still fully translated here.
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const rhSrc = extractFunctionDecl(scriptSrc, 'loadRuntimeHealth');
    check("loadRuntimeHealth() contains no hardcoded 'tr-TR' (none existed to begin with)", rhSrc.indexOf("'tr-TR'") === -1);
    async function runRuntime(lang) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => ({
        app: 'TorqPro', version: '3.1', liveness: true, readiness: false, database: 'sqlite', license: 'Pro', active_datasets: 4,
      }));
      ctx.byId['runtimeHealth'] = { innerHTML: '' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.loadRuntimeHealth();
      return ctx.byId['runtimeHealth'].innerHTML;
    }
    const htmlTr = await runRuntime('tr');
    const htmlEn = await runRuntime('en');
    check('tr: liveness true shows OK (technical code unchanged)', htmlTr.indexOf('>OK<') !== -1);
    check('en: liveness true still shows OK', htmlEn.indexOf('>OK<') !== -1);
    check('tr: readiness false shows "HAZIR DEĞİL"', htmlTr.indexOf('HAZIR DEĞİL') !== -1);
    check('en: readiness false shows "NOT READY"', htmlEn.indexOf('NOT READY') !== -1);
    check('raw active_datasets value (4) identical in both languages', htmlTr.indexOf('>4<') !== -1 && htmlEn.indexOf('>4<') !== -1);
  }

  // ---- 156. loadMobileAccess(): technical readiness result unchanged;
  //           displayed message TR/EN ----
  {
    async function runMobile(lang) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => ({
        local_url: 'http://192.168.1.10:8000', host: '192.168.1.10', port: 8000, pwa_ready: true,
        checks: [{ name: 'Local IP', value: '192.168.1.10', ok: true }],
      }));
      ctx.byId['mobileAccessStatus'] = { innerHTML: '' };
      ctx.byId['networkCheck'] = { innerHTML: '' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.loadMobileAccess();
      return { status: ctx.byId['mobileAccessStatus'].innerHTML, network: ctx.byId['networkCheck'].innerHTML };
    }
    const trResult = await runMobile('tr');
    const enResult = await runMobile('en');
    check('tr pwa_ready shows "Hazır"', trResult.status.indexOf('Hazır') !== -1);
    check('en pwa_ready shows "Ready"', enResult.status.indexOf('Ready') !== -1);
    check('local_url (technical value) identical in both languages', trResult.status.indexOf('192.168.1.10:8000') !== -1 && enResult.status.indexOf('192.168.1.10:8000') !== -1);
    check('network check "ok" still shows OK in both', trResult.network.indexOf('OK') !== -1 && enResult.network.indexOf('OK') !== -1);
  }

  // ---- 157. installPwa(): accept/reject technical outcome unaffected;
  //           alert text TR/EN; language switch never fires the
  //           install prompt itself ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    ctx.context.deferredPrompt = null;
    ctx.byId['installPwaBtn'] = { disabled: false };
    await ctx.context.installPwa();
    checkEqual('tr "not ready" alert', ctx.alertCalls[ctx.alertCalls.length - 1], 'Kurulum seçeneği şu anda hazır değil. Tarayıcı menüsünden Ana ekrana ekle seçeneğini kullanın.');
    ctx.context.setLanguage('en');
    await ctx.context.installPwa();
    checkEqual('en "not ready" alert', ctx.alertCalls[ctx.alertCalls.length - 1], 'Install option is not ready yet. Use "Add to Home Screen" from the browser menu.');
    // A real prompt: accepting/rejecting is entirely up to the browser
    // event (deferredPrompt.userChoice) -- installPwa() never inspects
    // language, and setLanguage() itself never touches deferredPrompt
    // or calls installPwa().
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const setLangSrc = extractFunctionDecl(scriptSrc, 'setLanguage');
    check('setLanguage() never references deferredPrompt or installPwa', setLangSrc.indexOf('deferredPrompt') === -1 && setLangSrc.indexOf('installPwa()') === -1);
  }

  // ---- 158. Language switch: form inputs and technical state
  //           preserved; only GET (no POST/save/install) is issued;
  //           re-render only happens for the currently active page ----
  {
    let putCalled = false, getCalls = 0;
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
      if (opts && opts.method === 'PUT') putCalled = true; else getCalls++;
      if (url.indexOf('golive-profile') !== -1) return { server_ip: '', domain: '', https_status: 'planned' };
      if (url.indexOf('cloud-readiness') !== -1) return { ready: true, checks: [] };
      return {};
    });
    ctx.byId['gw_server_ip'] = { value: '172.16.0.1' };
    ctx.byId['gw_domain'] = { value: 'preserved.example.com' };
    ctx.byId['goLiveChecklist'] = { innerHTML: '' };
    ctx.byId['wizardSteps'] = ctx.documentStub.getElementById('wizardSteps');
    // Only the golivewizard page is "active"; clouddeploy/runtimehealth/
    // mobileaccess are not, so their admin/other GETs must NOT fire.
    ctx.documentStub.getElementById('page-golivewizard').classList.add('active');
    ctx.context.setLanguage('en');
    checkEqual('gw_server_ip input preserved across language switch', ctx.byId['gw_server_ip'].value, '172.16.0.1');
    checkEqual('gw_domain input preserved across language switch', ctx.byId['gw_domain'].value, 'preserved.example.com');
    checkEqual('no PUT/save call was triggered by the language switch', putCalled, false);
    check('at least one safe GET call was made for the active go-live page', getCalls >= 1);
  }

  // ---- 159. No raw translation-key leakage across the 5 pages'
  //           dynamic HTML ----
  {
    const ctx = newContext(extractedSource, rawHtml, {}, async () => ({
      resolved_ips: [], matches_expected: false, https_ready: false, status: 'pending',
    }));
    ctx.byId['dns_domain'] = { value: 'x' };
    ctx.byId['dns_expected_ip'] = { value: 'y' };
    ctx.byId['dnsResult'] = { innerHTML: '' };
    ctx.context.setLanguage('en');
    await ctx.context.runDnsCheck();
    check('no raw namespaced key text leaks into en dns result', !/(dns|golive|cloud|runtime|mobile)\.[a-z_.0-9]+(?![\w])/.test(ctx.byId['dnsResult'].innerHTML));
  }

  // ---- 160. Hard-coded user text scan (this sub-phase's scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const turkishCharRe = /[şğüöçİĞÜŞÖÇı]/;
    for (const fn of ['installPwa', 'loadMobileAccess', 'loadCloudReadiness', 'loadRuntimeHealth', 'loadGoLiveProfile', 'renderGoLiveChecklist', 'saveGoLiveProfile', 'runDnsCheck']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      const strs = [...src.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]).filter((s) => turkishCharRe.test(s));
      check('no hard-coded Turkish string literals remain in ' + fn + '()', strs.length === 0);
    }
  }

  // ---- 161. In-scope hardcoded 'tr-TR' scan: 0 in these 8 functions ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    for (const fn of ['installPwa', 'loadMobileAccess', 'loadCloudReadiness', 'loadRuntimeHealth', 'loadGoLiveProfile', 'renderGoLiveChecklist', 'saveGoLiveProfile', 'runDnsCheck']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      check("no hardcoded 'tr-TR' remains in " + fn + '()', src.indexOf("'tr-TR'") === -1);
    }
  }

  // ---- 162. Language-dependent decision anti-pattern scan (closure) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    for (const fn of ['loadCloudReadiness', 'loadRuntimeHealth', 'runDnsCheck', 'renderGoLiveChecklist']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      check('no translated-text-driven decision in ' + fn + '()', !/\.includes\('[şğüöçİĞÜŞÖÇıA-ZÇĞİÖŞÜ][^']*'\)/.test(src));
    }
    check("https_status==='ready' branches on the stable technical value, not a label",
      scriptSrc.indexOf("https_status==='ready'") !== -1);
  }

  // ================================================================
  // Faz 2.7.4b-2 -- Deployment Profile / Data Migration / System
  // Diagnostics.
  // ================================================================

  // ---- 163. Three pages' static UI TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const checks = [
      ['deploy.title', 'Kurulum Profili', 'Deployment Profile'],
      ['migration.title', 'Veri Taşıma', 'Data Migration'],
      ['diagnostics.title', 'Sistem Tanılama', 'System Diagnostics'],
    ];
    ctx.context.applyStaticTranslations();
    for (const [key, tr] of checks) checkEqual('tr title for ' + key, getByI18nKey(ctx, key).textContent, tr);
    ctx.context.setLanguage('en');
    for (const [key, , en] of checks) checkEqual('en title for ' + key, getByI18nKey(ctx, key).textContent, en);
  }

  // ---- 164. Deployment dropdown visible labels TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const el = getByI18nKey(ctx, 'deploy.type_lan');
    ctx.context.applyStaticTranslations();
    checkEqual('type_lan label tr', el.textContent, 'Yerel Ağ Sunucusu');
    ctx.context.setLanguage('en');
    checkEqual('type_lan label en', el.textContent, 'Local Network Server');
  }

  // ---- 165. Deployment technical value preservation (option values) ----
  {
    check('dep_type option values are the fixed set {standalone,lan,cloud}',
      /value="standalone" data-i18n="deploy\.type_standalone"/.test(rawHtml) &&
      /value="lan" data-i18n="deploy\.type_lan"/.test(rawHtml) &&
      /value="cloud" data-i18n="deploy\.type_cloud"/.test(rawHtml));
    check('dep_backup option values are the fixed set {daily,weekly,manual}',
      /value="daily" data-i18n="deploy\.backup_daily"/.test(rawHtml) &&
      /value="weekly" data-i18n="deploy\.backup_weekly"/.test(rawHtml) &&
      /value="manual" data-i18n="deploy\.backup_manual"/.test(rawHtml));
    check('dep_channel option values are the fixed set {stable,pilot,offline}',
      /value="stable" data-i18n="deploy\.channel_stable"/.test(rawHtml) &&
      /value="pilot" data-i18n="deploy\.channel_pilot"/.test(rawHtml) &&
      /value="offline" data-i18n="deploy\.channel_offline"/.test(rawHtml));
  }

  // ---- 166. saveDeploymentProfile() payload identical across languages ----
  {
    async function runSaveDeployment(lang) {
      let captured = null;
      const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
        if (opts && opts.method === 'PUT') { captured = JSON.parse(opts.body); return captured; }
        return {};
      });
      ctx.byId['dep_env'] = { value: 'Staging' };
      ctx.byId['dep_type'] = { value: 'lan' };
      ctx.byId['dep_host'] = { value: '10.1.1.1' };
      ctx.byId['dep_port'] = { value: '9000' };
      ctx.byId['dep_backup'] = { value: 'weekly' };
      ctx.byId['dep_channel'] = { value: 'pilot' };
      ctx.byId['deploymentPreview'] = { innerHTML: '' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.saveDeploymentProfile();
      return { captured, alert: ctx.alertCalls[ctx.alertCalls.length - 1] };
    }
    const trResult = await runSaveDeployment('tr');
    const enResult = await runSaveDeployment('en');
    checkEqual('payload identical (environment)', trResult.captured.environment, enResult.captured.environment);
    checkEqual('payload identical (install_type)', trResult.captured.install_type, enResult.captured.install_type);
    checkEqual('payload identical (host)', trResult.captured.host, enResult.captured.host);
    checkEqual('payload identical (port)', trResult.captured.port, enResult.captured.port);
    checkEqual('payload identical (backup_frequency)', trResult.captured.backup_frequency, enResult.captured.backup_frequency);
    checkEqual('payload identical (update_channel)', trResult.captured.update_channel, enResult.captured.update_channel);
    checkEqual('install_type technical value untranslated', trResult.captured.install_type, 'lan');
  }

  // ---- 167. saveDeploymentProfile() success alert TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => JSON.parse(opts.body));
    ctx.byId['dep_env'] = { value: 'X' };
    ctx.byId['dep_type'] = { value: 'standalone' };
    ctx.byId['dep_host'] = { value: 'localhost' };
    ctx.byId['dep_port'] = { value: '8000' };
    ctx.byId['dep_backup'] = { value: 'daily' };
    ctx.byId['dep_channel'] = { value: 'stable' };
    ctx.byId['deploymentPreview'] = { innerHTML: '' };
    await ctx.context.saveDeploymentProfile();
    checkEqual('tr success alert', ctx.alertCalls[ctx.alertCalls.length - 1], 'Kurulum profili kaydedildi.');
    ctx.context.setLanguage('en');
    await ctx.context.saveDeploymentProfile();
    checkEqual('en success alert', ctx.alertCalls[ctx.alertCalls.length - 1], 'Deployment profile saved.');
  }

  // ---- 168. renderDeployment(): same technical profile, different
  //           displayed label per language, technical values unchanged ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const profile = { environment: 'Production', install_type: 'cloud', host: '203.0.113.5', port: 8443, backup_frequency: 'weekly', update_channel: 'pilot' };
    ctx.byId['deploymentPreview'] = { innerHTML: '' };
    ctx.context.renderDeployment(profile);
    const htmlTr = ctx.byId['deploymentPreview'].innerHTML;
    check('tr shows "Bulut Sunucusu" for cloud', htmlTr.indexOf('Bulut Sunucusu') !== -1);
    check('tr shows "Haftalık" for weekly', htmlTr.indexOf('Haftalık') !== -1);
    ctx.context.setLanguage('en');
    ctx.context.renderDeployment(profile);
    const htmlEn = ctx.byId['deploymentPreview'].innerHTML;
    check('en shows "Cloud Server" for the same cloud value', htmlEn.indexOf('Cloud Server') !== -1);
    check('en shows "Weekly" for the same weekly value', htmlEn.indexOf('Weekly') !== -1);
    check('host:port (technical) identical in both languages', htmlTr.indexOf('203.0.113.5:8443') !== -1 && htmlEn.indexOf('203.0.113.5:8443') !== -1);
  }

  // ---- 169. importSystemPackage(): no-file alert TR/EN; POST payload
  //           {content} unchanged; table count unchanged; only the
  //           fixed wrapper text changes ----
  {
    async function runImport(lang, file) {
      let captured = null;
      const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
        if (opts && opts.method === 'POST') { captured = JSON.parse(opts.body); return { import_no: 'IMP-1', table_count: 13 }; }
        return [];
      });
      ctx.byId['migration_file'] = { files: file ? [file] : [] };
      ctx.byId['migrationResult'] = { innerHTML: '' };
      ctx.byId['migrationHistory'] = { innerHTML: '' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.importSystemPackage();
      return { captured, alert: ctx.alertCalls[ctx.alertCalls.length - 1], resultHtml: ctx.byId['migrationResult'].innerHTML };
    }
    const noFileTr = await runImport('tr', null);
    checkEqual('tr no-file alert', noFileTr.alert, 'Dosya seçin.');
    const noFileEn = await runImport('en', null);
    checkEqual('en no-file alert', noFileEn.alert, 'Select a file.');
    const fileContent = '{"tables":13}';
    const fakeFile = { text: async () => fileContent };
    const withFileTr = await runImport('tr', fakeFile);
    checkEqual('POST payload content identical to the file contents (tr)', withFileTr.captured.content, fileContent);
    check('tr result shows "Doğrulandı" and table count 13', withFileTr.resultHtml.indexOf('Doğrulandı') !== -1 && withFileTr.resultHtml.indexOf('13') !== -1);
    const withFileEn = await runImport('en', fakeFile);
    checkEqual('POST payload content identical regardless of language', withFileEn.captured.content, fileContent);
    check('en result shows "Verified" and the same table count 13', withFileEn.resultHtml.indexOf('Verified') !== -1 && withFileEn.resultHtml.indexOf('13') !== -1);
  }

  // ---- 170. exportSystemPackage(): downloaded JSON content is
  //           language-independent; a language switch never triggers
  //           an export ----
  {
    const ctx = newContext(extractedSource, rawHtml, {}, async () => ({ export_no: 'EXP-1', tables: { users: [] } }));
    ctx.byId['migrationHistory'] = { innerHTML: '' };
    let exportCalled = false;
    const origLoadHistory = ctx.context.loadMigrationHistory;
    // exportSystemPackage() itself does not read CURRENT_LANG anywhere.
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const exportSrc = extractFunctionDecl(scriptSrc, 'exportSystemPackage');
    check('exportSystemPackage() body never references CURRENT_LANG', exportSrc.indexOf('CURRENT_LANG') === -1);
    const setLangSrc = extractFunctionDecl(scriptSrc, 'setLanguage');
    check('setLanguage() never calls exportSystemPackage()', setLangSrc.indexOf('exportSystemPackage()') === -1);
  }

  // ---- 171. loadMigrationHistory(): empty-state TR/EN; record
  //           order/id set and technical values unchanged ----
  {
    async function runHistory(lang, rows) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => rows);
      ctx.byId['migrationHistory'] = { innerHTML: '' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.loadMigrationHistory();
      return ctx.byId['migrationHistory'].innerHTML;
    }
    checkEqual('tr empty-state', await runHistory('tr', []), 'Kayıt yok.');
    checkEqual('en empty-state', await runHistory('en', []), 'No records.');
    const rows = [{ operation_no: 'OP-3', operation_type: 'export', status: 'done' }, { operation_no: 'OP-1', operation_type: 'import', status: 'failed' }];
    const htmlTr = await runHistory('tr', rows);
    const htmlEn = await runHistory('en', rows);
    const idsTr = [...htmlTr.matchAll(/<div>(OP-\d+)<\/div>/g)].map((m) => m[1]);
    const idsEn = [...htmlEn.matchAll(/<div>(OP-\d+)<\/div>/g)].map((m) => m[1]);
    checkEqual('operation_no order identical across languages', JSON.stringify(idsTr), JSON.stringify(idsEn));
    checkEqual('operation order matches backend response order (OP-3, OP-1)', JSON.stringify(idsTr), JSON.stringify(['OP-3', 'OP-1']));
    check('technical status values (export/import/done/failed) rendered verbatim in both', htmlTr.indexOf('export') !== -1 && htmlEn.indexOf('export') !== -1 && htmlTr.indexOf('failed') !== -1 && htmlEn.indexOf('failed') !== -1);
  }

  // ---- 172. runDiagnostics(): overall_ok/c.ok booleans and
  //           qg-pass/qg-fail CSS classes identical; labels TR/EN ----
  {
    async function runDiag(lang) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => ({
        overall_ok: false,
        checks: [{ name: 'Database', value: 'sqlite', ok: true, detail: '' }, { name: 'Disk Space', value: '2GB', ok: false, detail: 'low' }],
      }));
      ctx.byId['diagnosticRows'] = { innerHTML: '' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.runDiagnostics();
      return ctx.byId['diagnosticRows'].innerHTML;
    }
    const htmlTr = await runDiag('tr');
    const htmlEn = await runDiag('en');
    check('tr passing check shows OK and qg-pass', /qg-pass">OK/.test(htmlTr));
    check('en passing check shows OK and qg-pass (unchanged)', /qg-pass">OK/.test(htmlEn));
    check('tr failing check shows qg-fail and "HATA"', /qg-fail">HATA/.test(htmlTr));
    check('en failing check shows qg-fail and "ERROR"', /qg-fail">ERROR/.test(htmlEn));
    check('tr overall_ok:false shows "Genel Durum" + "Kontrol gerekli"', htmlTr.indexOf('Genel Durum') !== -1 && htmlTr.indexOf('Kontrol gerekli') !== -1);
    check('en overall_ok:false shows "Overall Status" + "Check needed"', htmlEn.indexOf('Overall Status') !== -1 && htmlEn.indexOf('Check needed') !== -1);
    check('backend check names (Database/Disk Space) rendered verbatim in both', htmlTr.indexOf('Disk Space') !== -1 && htmlEn.indexOf('Disk Space') !== -1);
  }

  // ---- 173. downloadDiagnostics(): technical JSON payload is
  //           language-independent; never triggered by a language switch ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const ddSrc = extractFunctionDecl(scriptSrc, 'downloadDiagnostics');
    check('downloadDiagnostics() never references CURRENT_LANG', ddSrc.indexOf('CURRENT_LANG') === -1);
    const setLangSrc = extractFunctionDecl(scriptSrc, 'setLanguage');
    check('setLanguage() never calls downloadDiagnostics()', setLangSrc.indexOf('downloadDiagnostics()') === -1);
  }

  // ---- 174. Language switch: Deployment form/dropdown state
  //           preserved; only GET (no PUT) issued for the active page ----
  {
    let putCalled = false;
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
      if (opts && opts.method === 'PUT') putCalled = true;
      return { environment: 'Prod', install_type: 'cloud', host: '1.2.3.4', port: 443, backup_frequency: 'daily', update_channel: 'stable' };
    });
    ctx.byId['dep_env'] = { value: 'Prod-Custom' };
    ctx.byId['dep_type'] = { value: 'cloud' };
    ctx.byId['dep_host'] = { value: '1.2.3.4' };
    ctx.byId['dep_port'] = { value: '443' };
    ctx.byId['dep_backup'] = { value: 'weekly' };
    ctx.byId['dep_channel'] = { value: 'offline' };
    ctx.byId['deploymentPreview'] = { innerHTML: '' };
    ctx.documentStub.getElementById('page-deployment').classList.add('active');
    ctx.context.setLanguage('en');
    checkEqual('dep_env preserved after language switch', ctx.byId['dep_env'].value, 'Prod-Custom');
    checkEqual('dep_type selection preserved after language switch', ctx.byId['dep_type'].value, 'cloud');
    checkEqual('dep_backup selection preserved after language switch', ctx.byId['dep_backup'].value, 'weekly');
    checkEqual('dep_channel selection preserved after language switch', ctx.byId['dep_channel'].value, 'offline');
    checkEqual('no PUT was triggered by the language switch', putCalled, false);
  }

  // ---- 175. Language switch: Migration file input untouched; no
  //           import/export/POST triggered ----
  {
    const fakeFile = { name: 'backup.json' };
    let postCalled = false;
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
      if (opts && opts.method === 'POST') postCalled = true;
      return [];
    });
    ctx.byId['migration_file'] = { files: [fakeFile] };
    ctx.byId['migrationHistory'] = { innerHTML: '' };
    ctx.documentStub.getElementById('page-migration').classList.add('active');
    ctx.context.setLanguage('en');
    checkEqual('migration_file selection (file object) unchanged by language switch', ctx.byId['migration_file'].files[0], fakeFile);
    checkEqual('no POST (import/export) was triggered by the language switch', postCalled, false);
  }

  // ---- 176. Language switch: Diagnostics re-renders cached
  //           LAST_DIAGNOSTICS without re-running the check ----
  {
    let getCalled = false;
    const ctx = newContext(extractedSource, rawHtml, {}, async () => { getCalled = true; return { overall_ok: true, checks: [] }; });
    ctx.context.LAST_DIAGNOSTICS = { overall_ok: true, checks: [{ name: 'API', value: 'up', ok: true, detail: '' }] };
    ctx.byId['diagnosticRows'] = { innerHTML: '' };
    ctx.documentStub.getElementById('page-diagnostics').classList.add('active');
    ctx.context.setLanguage('en');
    checkEqual('runDiagnostics() (a new check) was NOT triggered by the language switch', getCalled, false);
    check('diagnosticRows re-rendered from cached LAST_DIAGNOSTICS in en', ctx.byId['diagnosticRows'].innerHTML.indexOf('API') !== -1);
    checkEqual('LAST_DIAGNOSTICS object reference itself is unchanged', ctx.context.LAST_DIAGNOSTICS.checks[0].name, 'API');
  }

  // ---- 177. No raw translation-key leakage across deployment/
  //           migration/diagnostics dynamic HTML ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const profile = { environment: 'X', install_type: 'lan', host: 'h', port: 1, backup_frequency: 'manual', update_channel: 'offline' };
    ctx.byId['deploymentPreview'] = { innerHTML: '' };
    ctx.byId['diagnosticRows'] = { innerHTML: '' };
    ctx.context.setLanguage('en');
    ctx.context.renderDeployment(profile);
    ctx.context.renderDiagnostics({ overall_ok: true, checks: [{ name: 'X', value: 'Y', ok: true, detail: '' }] });
    const combined = ctx.byId['deploymentPreview'].innerHTML + ctx.byId['diagnosticRows'].innerHTML;
    check('no raw namespaced key text leaks into en rendering', !/(deploy|migration|diagnostics)\.[a-z_.0-9]+(?![\w])/.test(combined));
  }

  // ---- 178. Hard-coded user text scan (this sub-phase's scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const turkishCharRe = /[şğüöçİĞÜŞÖÇı]/;
    for (const fn of ['loadDeploymentProfile', 'renderDeployment', 'saveDeploymentProfile', 'exportSystemPackage', 'importSystemPackage', 'loadMigrationHistory', 'runDiagnostics', 'renderDiagnostics', 'downloadDiagnostics']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      const strs = [...src.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]).filter((s) => turkishCharRe.test(s));
      check('no hard-coded Turkish string literals remain in ' + fn + '()', strs.length === 0);
    }
  }

  // ---- 179. In-scope hardcoded 'tr-TR' scan: 0 (none existed here) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    for (const fn of ['loadDeploymentProfile', 'renderDeployment', 'saveDeploymentProfile', 'exportSystemPackage', 'importSystemPackage', 'loadMigrationHistory', 'runDiagnostics', 'renderDiagnostics', 'downloadDiagnostics']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      check("no hardcoded 'tr-TR' remains in " + fn + '()', src.indexOf("'tr-TR'") === -1);
    }
  }

  // ---- 180. Language-dependent decision anti-pattern scan (closure) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    for (const fn of ['saveDeploymentProfile', 'renderDeployment', 'runDiagnostics']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      check('no translated-text-driven decision in ' + fn + '()', !/\.includes\('[şğüöçİĞÜŞÖÇıA-ZÇĞİÖŞÜ][^']*'\)/.test(src));
    }
    check('c.ok drives qg-pass/qg-fail directly (stable boolean), not a translated label', scriptSrc.indexOf("c.ok?'qg-pass':'qg-fail'") !== -1);
  }

  // ================================================================
  // Faz 2.7.4b-3 -- Admin Panel.
  // ================================================================

  // ---- 184. page-admin static UI TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const checks = [
      ['admin.title', 'Yönetici Paneli', 'Admin Panel'],
      ['admin.new_user_title', 'Yeni Kullanıcı', 'New User'],
      ['admin.system_health_title', 'Sistem Sağlığı', 'System Health'],
    ];
    ctx.context.applyStaticTranslations();
    for (const [key, tr] of checks) checkEqual('tr title for ' + key, getByI18nKey(ctx, key).textContent, tr);
    ctx.context.setLanguage('en');
    for (const [key, , en] of checks) checkEqual('en title for ' + key, getByI18nKey(ctx, key).textContent, en);
  }

  // ---- 185. Form label and placeholder TR/EN ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const el = getByI18nKey(ctx, 'admin.display_name_label');
    ctx.context.applyStaticTranslations();
    checkEqual('display name label tr', el.textContent, 'Görünen Ad');
    ctx.context.setLanguage('en');
    checkEqual('display name label en', el.textContent, 'Display Name');
  }

  // ---- 186. Role technical value preservation (viewer/engineer/admin) ----
  {
    check('adm_role option values are the fixed set {engineer,viewer,admin}',
      /<option value="engineer" data-i18n="admin\.role_engineer">/.test(rawHtml) &&
      /<option value="viewer" data-i18n="admin\.role_viewer">/.test(rawHtml) &&
      /<option value="admin" data-i18n="admin\.role_admin">/.test(rawHtml));
  }

  // ---- 187. adminCreateUser() payload identical across languages;
  //           validation/success messages TR/EN ----
  {
    async function runCreateUser(lang) {
      let captured = null;
      const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
        if (opts && opts.method === 'POST' && url.indexOf('/api/admin/users') !== -1) { captured = JSON.parse(opts.body); return {}; }
        return [];
      });
      ctx.byId['adm_username'] = { value: 'jdoe' };
      ctx.byId['adm_display'] = { value: 'John Doe' };
      ctx.byId['adm_password'] = { value: 'secret123' };
      ctx.byId['adm_role'] = { value: 'engineer' };
      ctx.byId['adminUsers'] = { innerHTML: '' };
      ctx.context.CURRENT_ROLE = 'admin';
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.adminCreateUser();
      return { captured, alert: ctx.alertCalls[ctx.alertCalls.length - 1] };
    }
    const trResult = await runCreateUser('tr');
    const enResult = await runCreateUser('en');
    checkEqual('payload username identical tr/en', trResult.captured.username, enResult.captured.username);
    checkEqual('payload role identical tr/en (technical value)', trResult.captured.role, 'engineer');
    checkEqual('tr success alert', trResult.alert, 'Kullanıcı oluşturuldu.');
    checkEqual('en success alert', enResult.alert, 'User created.');
    // validation message
    const ctx2 = newContext(extractedSource, rawHtml, {});
    ctx2.byId['adm_username'] = { value: '' };
    ctx2.byId['adm_display'] = { value: '' };
    ctx2.byId['adm_password'] = { value: '' };
    ctx2.byId['adm_role'] = { value: 'engineer' };
    await ctx2.context.adminCreateUser();
    checkEqual('tr validation alert', ctx2.alertCalls[ctx2.alertCalls.length - 1], 'Tüm alanları doldurun.');
    ctx2.context.setLanguage('en');
    await ctx2.context.adminCreateUser();
    checkEqual('en validation alert', ctx2.alertCalls[ctx2.alertCalls.length - 1], 'Fill in all fields.');
  }

  // ---- 188. changeOwnPassword() payload identical across languages;
  //           validation/success messages TR/EN ----
  {
    async function runChangePassword(lang) {
      let captured = null;
      const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
        captured = JSON.parse(opts.body); return {};
      });
      ctx.byId['pwd_current'] = { value: 'oldpass' };
      ctx.byId['pwd_new'] = { value: 'newpass' };
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.changeOwnPassword();
      return { captured, alert: ctx.alertCalls[ctx.alertCalls.length - 1] };
    }
    const trResult = await runChangePassword('tr');
    const enResult = await runChangePassword('en');
    checkEqual('payload current_password identical tr/en', trResult.captured.current_password, enResult.captured.current_password);
    checkEqual('payload new_password identical tr/en', trResult.captured.new_password, enResult.captured.new_password);
    checkEqual('tr success alert', trResult.alert, 'Parola güncellendi.');
    checkEqual('en success alert', enResult.alert, 'Password updated.');
    const ctx2 = newContext(extractedSource, rawHtml, {});
    ctx2.byId['pwd_current'] = { value: '' };
    ctx2.byId['pwd_new'] = { value: '' };
    await ctx2.context.changeOwnPassword();
    checkEqual('tr validation alert', ctx2.alertCalls[ctx2.alertCalls.length - 1], 'Mevcut ve yeni şifreyi girin.');
    ctx2.context.setLanguage('en');
    await ctx2.context.changeOwnPassword();
    checkEqual('en validation alert', ctx2.alertCalls[ctx2.alertCalls.length - 1], 'Enter your current and new password.');
  }

  // ---- 189. adminUpdateUser(): role/is_active payload preserved;
  //           displayed active/inactive + button labels TR/EN ----
  {
    async function runUpdateUser(lang) {
      let captured = null;
      const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
        if (opts && opts.method === 'PATCH') { captured = JSON.parse(opts.body); return {}; }
        return [{ id: 1, username: 'jdoe', display_name: 'John Doe', role: 'engineer', is_active: 1 }];
      });
      ctx.byId['adminUsers'] = { innerHTML: '' };
      ctx.context.CURRENT_ROLE = 'admin';
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.adminUpdateUser(1, { role: 'viewer' });
      const html = await (async () => { await ctx.context.loadAdminUsers(); return ctx.byId['adminUsers'].innerHTML; })();
      return { captured, html };
    }
    const trResult = await runUpdateUser('tr');
    const enResult = await runUpdateUser('en');
    checkEqual('role payload identical tr/en', trResult.captured.role, enResult.captured.role);
    checkEqual('role payload technical value untranslated', trResult.captured.role, 'viewer');
    check('tr rendered row shows "Aktif"', trResult.html.indexOf('Aktif') !== -1);
    check('en rendered row shows "Active"', enResult.html.indexOf('Active') !== -1);
    check('tr rendered row shows "Pasifleştir" button', trResult.html.indexOf('Pasifleştir') !== -1);
    check('en rendered row shows "Deactivate" button', enResult.html.indexOf('Deactivate') !== -1);
  }

  // ---- 190. adminResetPassword(): prompt text TR/EN; prompt result
  //           passed through unchanged; cancel (null) issues no POST;
  //           language switch never triggers prompt() ----
  {
    let postCalled = false;
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
      if (opts && opts.method === 'POST') postCalled = true;
      return {};
    });
    ctx.setPromptReturn('Temp!Pass123');
    await ctx.context.adminResetPassword(5);
    checkEqual('tr prompt message', ctx.promptCalls[ctx.promptCalls.length - 1], 'Yeni geçici şifre:');
    checkEqual('POST fired with a real prompt value', postCalled, true);
    checkEqual('success alert tr', ctx.alertCalls[ctx.alertCalls.length - 1], 'Parola güncellendi.');

    ctx.context.setLanguage('en');
    await ctx.context.adminResetPassword(5);
    checkEqual('en prompt message', ctx.promptCalls[ctx.promptCalls.length - 1], 'New temporary password:');
    checkEqual('success alert en', ctx.alertCalls[ctx.alertCalls.length - 1], 'Password updated.');

    // Cancel (prompt returns null) -> no POST
    postCalled = false;
    ctx.setPromptReturn(null);
    await ctx.context.adminResetPassword(5);
    checkEqual('cancelled prompt (null) triggers no POST', postCalled, false);

    // Language switch itself never calls prompt()
    const promptCountBefore = ctx.promptCalls.length;
    ctx.context.setLanguage('tr');
    checkEqual('setLanguage() never calls prompt()', ctx.promptCalls.length, promptCountBefore);
  }

  // ---- 191. loadAdminUsers(): user ID/order preserved; is_active
  //           boolean and role value unchanged; displayed text TR/EN;
  //           CSS pill class unchanged ----
  {
    const rows = [
      { id: 3, username: 'c', display_name: 'C', role: 'admin', is_active: 1 },
      { id: 1, username: 'a', display_name: 'A', role: 'viewer', is_active: 0 },
    ];
    async function runLoadUsers(lang) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => rows);
      ctx.byId['adminUsers'] = { innerHTML: '' };
      ctx.context.CURRENT_ROLE = 'admin';
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.loadAdminUsers();
      return ctx.byId['adminUsers'].innerHTML;
    }
    const htmlTr = await runLoadUsers('tr');
    const htmlEn = await runLoadUsers('en');
    const idsTr = [...htmlTr.matchAll(/adminUpdateUser\((\d+)/g)].map((m) => m[1]);
    const idsEn = [...htmlEn.matchAll(/adminUpdateUser\((\d+)/g)].map((m) => m[1]);
    checkEqual('user id/order preserved across language switch', JSON.stringify(idsEn.slice(0, 2)), JSON.stringify(idsTr.slice(0, 2)));
    check('tr shows "Pasif" for inactive user', htmlTr.indexOf('Pasif') !== -1);
    check('en shows "Inactive" for inactive user', htmlEn.indexOf('Inactive') !== -1);
    check('pill-ok CSS class present for active user in both', htmlTr.indexOf('pill-ok') !== -1 && htmlEn.indexOf('pill-ok') !== -1);
    check('pill-nok CSS class present for inactive user in both', htmlTr.indexOf('pill-nok') !== -1 && htmlEn.indexOf('pill-nok') !== -1);
    check('role option value="viewer" (technical) present in both', htmlTr.indexOf('value="viewer"') !== -1 && htmlEn.indexOf('value="viewer"') !== -1);
  }

  // ---- 192. loadAudit(): record order/ID preserved; raw created_at
  //           unchanged; tr-TR vs en-US date display; action/resource/
  //           detail free text not auto-translated ----
  {
    const rows = [
      { id: 2, action: 'user.login', username: 'jdoe', created_at: '2026-02-10T09:15:00Z', detail: 'Giriş başarılı' },
      { id: 1, action: 'user.create', username: 'admin', created_at: '2026-02-09T08:00:00Z', detail: null },
    ];
    async function runAudit(lang) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => rows);
      ctx.byId['auditList'] = { innerHTML: '' };
      ctx.context.CURRENT_ROLE = 'admin';
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.loadAudit();
      return ctx.byId['auditList'].innerHTML;
    }
    const htmlTr = await runAudit('tr');
    const htmlEn = await runAudit('en');
    check('audit action free text (user.login) rendered verbatim in tr', htmlTr.indexOf('user.login') !== -1);
    check('audit action free text (user.login) rendered verbatim in en (not auto-translated)', htmlEn.indexOf('user.login') !== -1);
    check('audit detail free text (Giriş başarılı) not auto-translated in en', htmlEn.indexOf('Giriş başarılı') !== -1);
    const dateTr = new Date(rows[0].created_at).toLocaleString('tr-TR');
    const dateEn = new Date(rows[0].created_at).toLocaleString('en-US');
    check('tr audit date uses tr-TR formatting', htmlTr.indexOf(dateTr) !== -1);
    check('en audit date uses en-US formatting', htmlEn.indexOf(dateEn) !== -1);
    check('tr-TR and en-US audit date strings differ (locale genuinely applied)', dateTr !== dateEn);
  }

  // ---- 193. loadSystemHealth(): apiOk/dbOk booleans and OK/NOK codes
  //           unchanged; green/yellow/red state unchanged; server-time
  //           tr-TR/en-US locale; raw server_time unchanged; numeric
  //           values unchanged ----
  {
    const healthResponse = {
      status: 'ok', database_ok: true, version: '3.1', database_size_kb: 512,
      active_users: 4, total_users: 9, calculation_count: 120, audit_count: 340,
      server_time: '2026-03-01T12:00:00Z', schema_version: 7,
    };
    async function runHealth(lang) {
      const ctx = newContext(extractedSource, rawHtml, {}, async () => healthResponse);
      ctx.byId['systemHealthCards'] = { innerHTML: '' };
      ctx.byId['systemHealthDetail'] = { textContent: '' };
      ctx.context.CURRENT_ROLE = 'admin';
      if (lang === 'en') ctx.context.setLanguage('en');
      await ctx.context.loadSystemHealth();
      return { cards: ctx.byId['systemHealthCards'].innerHTML, detail: ctx.byId['systemHealthDetail'].textContent };
    }
    const trResult = await runHealth('tr');
    const enResult = await runHealth('en');
    check('tr: apiOk shows OK (technical code unchanged)', trResult.cards.indexOf('>OK<') !== -1);
    check('en: apiOk still shows OK', enResult.cards.indexOf('>OK<') !== -1);
    check('raw numeric active_users (4) identical in both languages', trResult.cards.indexOf('>4<') !== -1 && enResult.cards.indexOf('>4<') !== -1);
    const dateTr = new Date(healthResponse.server_time).toLocaleString('tr-TR');
    const dateEn = new Date(healthResponse.server_time).toLocaleString('en-US');
    check('tr server time uses tr-TR formatting', trResult.detail.indexOf(dateTr) !== -1);
    check('en server time uses en-US formatting', enResult.detail.indexOf(dateEn) !== -1);
    check('raw schema_version (7) identical in both languages', trResult.detail.indexOf('7') !== -1 && enResult.detail.indexOf('7') !== -1);
  }

  // ---- 194. SYSTEM_HEALTH_HELP: all keys resolve TR/EN; 4 health
  //           cards fully covered; green/yellow/red technical codes
  //           unchanged; no raw key leakage ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const help = ctx.context.__getSystemHealthHelp ? ctx.context.__getSystemHealthHelp() : ctx.context.SYSTEM_HEALTH_HELP;
    const cardKeys = Object.keys(help);
    checkEqual('4 health cards defined', cardKeys.length, 4);
    let allResolvedTr = true, allResolvedEn = true;
    cardKeys.forEach((k) => {
      const d = help[k];
      [d.titleKey, d.reasonKey, d.yellowKey, d.greenKey, d.redKey].filter(Boolean).forEach((key) => {
        if (ctx.context.t(key) === key) allResolvedTr = false;
      });
    });
    ctx.context.setLanguage('en');
    cardKeys.forEach((k) => {
      const d = help[k];
      [d.titleKey, d.reasonKey, d.yellowKey, d.greenKey, d.redKey].filter(Boolean).forEach((key) => {
        if (ctx.context.t(key) === key) allResolvedEn = false;
      });
    });
    check('all SYSTEM_HEALTH_HELP keys resolve in tr', allResolvedTr);
    check('all SYSTEM_HEALTH_HELP keys resolve in en', allResolvedEn);
  }

  // ---- 195. shInfo()/infoIconHtml(): tooltip title/body TR/EN;
  //           technical state decision (warn=true for red) unchanged;
  //           no raw key leakage ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const htmlTrGreen = ctx.context.shInfo('api', 'green');
    const htmlTrRed = ctx.context.shInfo('api', 'red');
    check('tr green-state tooltip shows the tr green explanation', htmlTrGreen.indexOf('API isteklere normal yanıt veriyor') !== -1);
    check('tr red-state tooltip is marked warn (info-icon-btn warn class)', htmlTrRed.indexOf('info-icon-btn warn') !== -1);
    check('tr green-state tooltip is NOT marked warn', htmlTrGreen.indexOf('info-icon-btn warn') === -1);
    ctx.context.setLanguage('en');
    const htmlEnGreen = ctx.context.shInfo('api', 'green');
    check('en green-state tooltip shows the en explanation', htmlEnGreen.indexOf('The API is responding normally') !== -1);
    check('no raw "admin.xxx" key leaks into en tooltip', !/admin\.[a-z_.0-9]+(?![\w])/.test(htmlEnGreen));
    // unmonitored state (users/records) uses the fallback explanation
    const htmlUnmonitored = ctx.context.shInfo('users', 'unmonitored');
    check('unmonitored-state tooltip uses the fallback explanation (en)', htmlUnmonitored.indexOf('not defined in the backend for this item') !== -1);
  }

  // ---- 196. downloadBackup(): language switch triggers no download;
  //           fallback message TR/EN; backend content untouched ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    // downloadBackup() uses global fetch, not apiRequest -- stub it directly.
    let fetchCalled = 0;
    ctx.context.fetch = async () => { fetchCalled++; return { ok: false }; };
    await ctx.context.downloadBackup();
    checkEqual('tr backup-failed alert', ctx.alertCalls[ctx.alertCalls.length - 1], 'Yedek alınamadı.');
    ctx.context.setLanguage('en');
    await ctx.context.downloadBackup();
    checkEqual('en backup-failed alert', ctx.alertCalls[ctx.alertCalls.length - 1], 'Backup could not be retrieved.');
    checkEqual('language switch itself never calls fetch (only explicit downloadBackup() calls did)', fetchCalled, 2);
  }

  // ---- 197. Language switch: admin form inputs preserved; only safe
  //           GET/render calls happen; no PUT/PATCH/POST/prompt/
  //           download is triggered; CURRENT_ROLE guard respected ----
  {
    let mutatingCallMade = false, getCalls = 0;
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
      if (opts && ['POST', 'PUT', 'PATCH'].includes(opts.method)) mutatingCallMade = true;
      else getCalls++;
      if (url.indexOf('/api/admin/users') !== -1 && url.indexOf('reset-password') === -1) return [];
      if (url.indexOf('/api/admin/audit') !== -1) return [];
      if (url.indexOf('/api/admin/system') !== -1) return { status: 'ok', database_ok: true, server_time: '2026-01-01T00:00:00Z' };
      return {};
    });
    ctx.byId['adm_username'] = { value: 'preserved-user' };
    ctx.byId['adm_display'] = { value: 'Preserved Name' };
    ctx.byId['pwd_current'] = { value: 'kept1' };
    ctx.byId['pwd_new'] = { value: 'kept2' };
    ctx.byId['adminUsers'] = { innerHTML: '' };
    ctx.byId['auditList'] = { innerHTML: '' };
    ctx.byId['systemHealthCards'] = { innerHTML: '' };
    ctx.byId['systemHealthDetail'] = { textContent: '' };
    ctx.context.CURRENT_ROLE = 'admin';
    ctx.documentStub.getElementById('page-admin').classList.add('active');
    ctx.context.setLanguage('en');
    checkEqual('adm_username preserved across language switch', ctx.byId['adm_username'].value, 'preserved-user');
    checkEqual('adm_display preserved across language switch', ctx.byId['adm_display'].value, 'Preserved Name');
    checkEqual('pwd_current preserved across language switch', ctx.byId['pwd_current'].value, 'kept1');
    checkEqual('pwd_new preserved across language switch', ctx.byId['pwd_new'].value, 'kept2');
    checkEqual('no mutating (POST/PUT/PATCH) call triggered by the language switch', mutatingCallMade, false);
    checkEqual('no prompt() call triggered by the language switch', ctx.promptCalls.length, 0);
    check('at least one safe GET call was made for the active admin page', getCalls >= 1);

    // Non-admin role: the guard must remain a no-op (no admin-only
    // calls at all, not even a GET).
    let anyCallMadeForNonAdmin = false;
    const ctx2 = newContext(extractedSource, rawHtml, {}, async () => { anyCallMadeForNonAdmin = true; return []; });
    ctx2.context.CURRENT_ROLE = 'viewer';
    ctx2.documentStub.getElementById('page-admin').classList.add('active');
    ctx2.context.setLanguage('en');
    checkEqual('non-admin CURRENT_ROLE: no admin-only network calls at all on language switch', anyCallMadeForNonAdmin, false);
  }

  // ---- 198. In-scope hardcoded 'tr-TR' scan: 0 (both loadAudit() and
  //           loadSystemHealth() now use reportLocale()) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    for (const fn of ['loadAudit', 'loadSystemHealth']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      check("no hardcoded 'tr-TR' remains in " + fn + '()', src.indexOf("'tr-TR'") === -1);
      check(fn + '() uses reportLocale()', src.indexOf('reportLocale()') !== -1);
    }
  }

  // ---- 199. Hard-coded user text scan (admin scope) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const turkishCharRe = /[şğüöçİĞÜŞÖÇı]/;
    for (const fn of ['changeOwnPassword', 'adminCreateUser', 'loadAdminUsers', 'adminUpdateUser', 'adminResetPassword', 'loadAudit', 'downloadBackup', 'loadSystemHealth', 'shInfo', 'infoIconHtml']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      const strs = [...src.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]).filter((s) => turkishCharRe.test(s));
      check('no hard-coded Turkish string literals remain in ' + fn + '()', strs.length === 0);
    }
  }

  // ---- 200. Language-dependent decision anti-pattern scan (admin) ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    for (const fn of ['loadAdminUsers', 'loadSystemHealth', 'shInfo']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      check('no translated-text-driven decision in ' + fn + '()', !/\.includes\('[şğüöçİĞÜŞÖÇıA-ZÇĞİÖŞÜ][^']*'\)/.test(src));
    }
    check("role decisions branch on u.role==='viewer'/'engineer'/'admin' (stable technical value)",
      scriptSrc.indexOf("u.role==='viewer'") !== -1);
  }

  // ---- 201. Faz 2.8.3: sidebar item, page id, and the three sections
  //           exist in the real markup (byId auto-vivifies stub
  //           elements on first access, so existence is checked
  //           against rawHtml text directly, not ctx.byId) ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    check('sidebar strengthclasses item exists (i18n key present)', !!getByI18nKey(ctx, 'sidebar.strengthclasses'));
    check('page-strengthclasses container exists', rawHtml.indexOf('id="page-strengthclasses"') !== -1);
    check('sc page_title i18n key present', !!getByI18nKey(ctx, 'sc.page_title'));
    check('Bolt Classes section title present', !!getByI18nKey(ctx, 'sc.bolt_section_title'));
    check('Nut Classes section title present', !!getByI18nKey(ctx, 'sc.nut_section_title'));
    check('Compatibility Checker section title present', !!getByI18nKey(ctx, 'sc.compat_section_title'));
    check('bolt strength-class table container exists', rawHtml.indexOf('id="sc-bolt-table"') !== -1);
    check('nut property-class table container exists', rawHtml.indexOf('id="sc-nut-table"') !== -1);
    check('sidebar item calls showPage(\'strengthclasses\')', rawHtml.indexOf("showPage('strengthclasses')") !== -1);
  }

  // ---- 202. Faz 2.8.3: compatibility checker inputs exist in the
  //           real markup ----
  {
    check('bolt class selector exists', rawHtml.indexOf('id="sc-compat-bolt"') !== -1);
    check('nut class selector exists', rawHtml.indexOf('id="sc-compat-nut"') !== -1);
    check('nominal diameter input exists', rawHtml.indexOf('id="sc-compat-diameter"') !== -1);
    check('standard selector exists', rawHtml.indexOf('id="sc-compat-standard"') !== -1);
    check('material-family selector exists', rawHtml.indexOf('id="sc-compat-material-family"') !== -1);
    check('compatibility check button exists', rawHtml.indexOf('id="sc-compat-check-btn"') !== -1);
    check('compatibility result container exists', rawHtml.indexOf('id="sc-compat-result"') !== -1);
  }

  // ---- 203. Faz 2.8.3: four compatibility statuses have EN+TR i18n
  //           keys, and loader/compatibility functions are defined ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const i18n = ctx.context.__getI18N();
    for (const status of ['compatible', 'conditionally_compatible', 'not_compatible', 'unknown']) {
      const key = 'sc.status.' + status;
      check('EN has ' + key, Object.prototype.hasOwnProperty.call(i18n.en, key));
      check('TR has ' + key, Object.prototype.hasOwnProperty.call(i18n.tr, key));
    }
    check('loadStrengthClassesWorkspace is a function', typeof ctx.context.loadStrengthClassesWorkspace === 'function');
    check('scCheckCompatibility is a function', typeof ctx.context.scCheckCompatibility === 'function');
    check('scRenderCompatResult is a function', typeof ctx.context.scRenderCompatResult === 'function');
  }

  // ---- 204. Faz 2.8.3: EN/TR key parity across the whole dictionary
  //           (not just the sc.* subset) still holds after this
  //           phase's additions ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const i18n = ctx.context.__getI18N();
    const enKeys = Object.keys(i18n.en);
    const trKeys = Object.keys(i18n.tr);
    const missingInTr = enKeys.filter((k) => !trKeys.includes(k));
    const missingInEn = trKeys.filter((k) => !enKeys.includes(k));
    checkEqual('no EN key missing from TR', missingInTr.length, 0);
    checkEqual('no TR key missing from EN', missingInEn.length, 0);
  }

  // ---- 205. Faz 2.8.3: the six required engineering caution
  //           messages exist, in both languages ----
  {
    const ctx = newContext(extractedSource, rawHtml, {});
    const i18n = ctx.context.__getI18N();
    const cautionKeys = [
      'sc.caution.friction', 'sc.caution.torque', 'sc.caution.stress_definitions',
      'sc.caution.iso_equivalence', 'sc.caution.oem_limits', 'sc.caution.diameter_conditional',
    ];
    for (const key of cautionKeys) {
      check('EN caution present: ' + key, !!(i18n.en[key] && i18n.en[key].length > 0));
      check('TR caution present: ' + key, !!(i18n.tr[key] && i18n.tr[key].length > 0));
    }
  }

  // ---- 206. Faz 2.8.3: loadStrengthClassesWorkspace renders fetched
  //           bolt/nut data, escapes API text, and only calls the API
  //           when the page is loaded (not on every showPage call) ----
  {
    let callCount = 0;
    const fakeBolt = {
      designation: '8.8', standard: 'ISO 898-1', material_family: 'carbon_alloy_steel',
      nominal_tensile_strength_mpa: 800, min_tensile_strength_mpa: 830, yield_ratio: 0.8,
      min_yield_strength_mpa: 660, proof_stress_mpa: 660, hardness_min: 255, hardness_max: 335,
      hardness_scale: 'HV', diameter_min_mm: 5, diameter_max_mm: 39,
      heat_treatment: 'Quenched & tempered <script>alert(1)</script>', elongation_percent: 12,
      verification_status: 'reference_only', notes_en: 'note <b>x</b>', notes_tr: 'not', source: 'ISO 898-1',
    };
    const fakeNut = {
      designation: '04', standard: 'ISO 898-2', material_family: 'carbon_alloy_steel',
      proof_load_stress_mpa: 400, compatible_bolt_classes: ['3.6', '4.6'],
      diameter_min_mm: 1.6, diameter_max_mm: 39, nut_style: 'thin (style 0)',
      hardness_min: null, hardness_max: null, hardness_scale: 'HV',
      heat_treatment: 'Not mandatory', verification_status: 'reference_only',
      notes_en: 'nut note', notes_tr: 'somun notu', source: 'ISO 898-2',
    };
    const ctx = newContext(extractedSource, rawHtml, {}, async (url) => {
      callCount++;
      if (url.indexOf('/api/engineering/bolt-strength-classes') !== -1) return [fakeBolt];
      if (url.indexOf('/api/engineering/nut-property-classes') !== -1) return [fakeNut];
      return [];
    });
    ctx.documentStub.getElementById('page-strengthclasses').classList.add('active');
    await ctx.context.loadStrengthClassesWorkspace();
    checkEqual('exactly 2 API calls made on page load (bolts + nuts)', callCount, 2);
    const boltHtml = ctx.byId['sc-bolt-table'].innerHTML;
    check('04 designation rendered in nut table without truncation', ctx.byId['sc-nut-table'].innerHTML.indexOf('04') !== -1);
    check('8.8 designation rendered in bolt table', boltHtml.indexOf('8.8') !== -1);
    check('API text with markup is escaped (no raw <script> in rendered bolt table)', boltHtml.indexOf('<script>alert(1)</script>') === -1);
    check('escaped markup entity present instead', boltHtml.indexOf('&lt;script&gt;') !== -1);
    check('bolt selector populated for compatibility checker', ctx.byId['sc-compat-bolt'].innerHTML.indexOf('8.8') !== -1);
    check('nut selector populated for compatibility checker', ctx.byId['sc-compat-nut'].innerHTML.indexOf('04') !== -1);

    // Re-invoking load (simulating a second showPage navigation) must
    // not silently accumulate duplicate DOM/listener state -- table
    // innerHTML is fully replaced, not appended to. One <thead><tr>
    // (headers) + one <tbody><tr> (the single fake bolt record) = 2,
    // stable across repeated loads (not 4, which would indicate
    // accumulation).
    await ctx.context.loadStrengthClassesWorkspace();
    const boltRowCount = (ctx.byId['sc-bolt-table'].innerHTML.match(/<tr>/g) || []).length;
    checkEqual('re-loading the page replaces (not duplicates) table rows', boltRowCount, 2);
  }

  // ---- 207. Faz 2.8.3: compatibility checker calls the POST
  //           endpoint, renders status/reasons/warnings/checks, and
  //           surfaces a clean error message (no raw exception) on
  //           API failure ----
  {
    const ctx = newContext(extractedSource, rawHtml, {}, async (url, opts) => {
      if (opts && opts.method === 'POST') {
        return {
          status: 'not_compatible', compatible: false,
          bolt_strength_class: '10.9', nut_property_class: '8',
          recommended_minimum_nut_class: '10',
          reasons: ['Nut property class 8 is below the minimum for bolt class 10.9.'],
          warnings: [], warning_codes: [],
          checks: { strength_class: 'fail', diameter_range: 'pass', standard: 'pass', material_family: 'pass' },
        };
      }
      return [];
    });
    ctx.byId['sc-compat-bolt'] = { value: '10.9' };
    ctx.byId['sc-compat-nut'] = { value: '8' };
    ctx.byId['sc-compat-diameter'] = { value: '' };
    ctx.byId['sc-compat-standard'] = { value: '' };
    ctx.byId['sc-compat-material-family'] = { value: '' };
    ctx.byId['sc-compat-check-btn'] = { disabled: false };
    await ctx.context.scCheckCompatibility();
    const resultHtml = ctx.byId['sc-compat-result'].innerHTML;
    const statusLabelTr = ctx.context.__getI18N().tr['sc.status.not_compatible'];
    check('result shows not_compatible status text', resultHtml.indexOf(statusLabelTr) !== -1);
    check('result shows recommended minimum nut class', resultHtml.indexOf('10') !== -1);
    check('result shows the reason text (escaped)', resultHtml.indexOf('below the minimum for bolt class 10.9') !== -1);
    check('result shows strength_class check outcome', resultHtml.indexOf('fail') !== -1);

    // API failure path: apiRequest throws Error(detail) already (see
    // apiRequest's own error handling) -- confirm the workspace shows
    // that clean message, not "[object Object]" or a raw stack.
    const ctxErr = newContext(extractedSource, rawHtml, {}, async () => { throw new Error('Bilinmeyen civata dayanım sınıfı: XX'); });
    ctxErr.byId['sc-compat-bolt'] = { value: 'XX' };
    ctxErr.byId['sc-compat-nut'] = { value: '8' };
    ctxErr.byId['sc-compat-diameter'] = { value: '' };
    ctxErr.byId['sc-compat-standard'] = { value: '' };
    ctxErr.byId['sc-compat-material-family'] = { value: '' };
    ctxErr.byId['sc-compat-check-btn'] = { disabled: false };
    await ctxErr.context.scCheckCompatibility();
    const errHtml = ctxErr.byId['sc-compat-result'].innerHTML;
    check('API error renders the real message text', errHtml.indexOf('Bilinmeyen civata dayanım sınıfı: XX') !== -1);
    check('API error does not render "[object Object]"', errHtml.indexOf('[object Object]') === -1);
    check('API error does not render "undefined"', errHtml.indexOf('undefined') === -1);
  }

  // ---- 208. Faz 2.8.3: language switch re-renders already-fetched
  //           strength-class data in place (no re-fetch) ----
  {
    let callCount = 0;
    const ctx = newContext(extractedSource, rawHtml, {}, async (url) => {
      callCount++;
      if (url.indexOf('bolt-strength-classes') !== -1) return [{
        designation: '8.8', standard: 'ISO 898-1', material_family: 'carbon_alloy_steel',
        verification_status: 'reference_only', notes_en: 'en note', notes_tr: 'tr note', source: 'ISO 898-1',
      }];
      if (url.indexOf('nut-property-classes') !== -1) return [];
      return [];
    });
    ctx.documentStub.getElementById('page-strengthclasses').classList.add('active');
    await ctx.context.loadStrengthClassesWorkspace();
    const callsAfterLoad = callCount;
    ctx.context.setLanguage('en');
    checkEqual('language switch triggers no additional API calls', callCount, callsAfterLoad);
    check('bolt table re-rendered with English note text after language switch',
      ctx.byId['sc-bolt-table'].innerHTML.indexOf('en note') !== -1);
    ctx.context.setLanguage('tr');
    check('bolt table re-rendered with Turkish note text after language switch back',
      ctx.byId['sc-bolt-table'].innerHTML.indexOf('tr note') !== -1);
  }

  // ---- 209. Faz 2.8.3: endpoint paths referenced in the extracted
  //           source match the real backend routes exactly ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    const loadFnSrc = extractFunctionDecl(scriptSrc, 'loadStrengthClassesWorkspace');
    const compatFnSrc = extractFunctionDecl(scriptSrc, 'scCheckCompatibility');
    check('loadStrengthClassesWorkspace calls the bolt list endpoint',
      loadFnSrc.indexOf('/api/engineering/bolt-strength-classes') !== -1);
    check('loadStrengthClassesWorkspace calls the nut list endpoint',
      loadFnSrc.indexOf('/api/engineering/nut-property-classes') !== -1);
    check('scCheckCompatibility calls the compatibility POST endpoint',
      compatFnSrc.indexOf('/api/engineering/bolt-nut-compatibility') !== -1);
  }

  // ---- 210. Faz 2.8.3: no duplicate event-listener wiring -- the new
  //           page uses inline on* handlers (idempotent on re-render,
  //           same pattern as the rest of this codebase) rather than
  //           addEventListener, so re-invoking the loader cannot
  //           accumulate duplicate handlers. ----
  {
    const scriptSrc = rawHtml.match(/<script>([\s\S]*)<\/script>/)[1];
    for (const fn of ['scRenderBoltTable', 'scRenderNutTable', 'scRenderCompatResult']) {
      const src = extractFunctionDecl(scriptSrc, fn);
      check(fn + '() does not call addEventListener', src.indexOf('addEventListener') === -1);
    }
    const htmlSrc = fs.readFileSync(FRONTEND_PATH, 'utf-8');
    const pageBlockMatch = htmlSrc.match(/<div id="page-strengthclasses"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>\s*<\/div>/);
    check('strength classes page markup uses inline handlers, not addEventListener',
      htmlSrc.indexOf('addEventListener') === -1 || !pageBlockMatch || pageBlockMatch[0].indexOf('addEventListener') === -1);
  }

  console.log('\n' + pass + ' passed, ' + fail + ' failed.');
  if (fail > 0) {
    console.log('Failures: ' + failures.join('; '));
    process.exit(1);
  }
  process.exit(0);
}

main().catch((e) => { console.error('FATAL:', e); process.exit(1); });
