#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.9 Stage 5 -- Washer Resolution Report frontend regression
 * harness.
 *
 * Zero external dependencies, same technique as
 * tests/js/run_material_intelligence_tests.js: Node's built-in `vm`
 * module runs the *actual* Washer Resolution Report declarations
 * extracted live from frontend/index.html (never a committed copy)
 * against a small hand-built DOM/localStorage stub.
 *
 * Invoked via `node tests/js/run_washer_resolution_report_tests.js`
 * from the repo root, or indirectly via
 * tests/test_faz_2_8_9_stage5_frontend.py.
 * Exit code 0 = all assertions passed; non-zero = at least one
 * failure.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND_PATH = path.join(REPO_ROOT, 'frontend', 'index.html');

// ---------------------------------------------------------------
// Extraction (same technique as the other harnesses)
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
  let j = i;
  for (; j < script.length; j++) {
    const c = script[j];
    if (c === '{' || c === '[' || c === '(') depth++;
    else if (c === '}' || c === ']' || c === ')') depth--;
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
  let start = m.index;
  const asyncMatch = /async\s+$/.exec(script.slice(Math.max(0, start - 10), start));
  if (asyncMatch) start -= asyncMatch[0].length;
  return script.slice(start, j + 1);
}

function toVarDecl(declText, name) {
  const re = new RegExp('^(const|let)(\\s+' + name + '\\s*=)');
  if (!re.test(declText)) throw new Error('expected declaration of ' + name + ' to rewrite to var, got: ' + declText.slice(0, 60));
  return declText.replace(re, 'var$2');
}

const CONST_NAMES = ['I18N', 'CURRENT_LANG', 'WRR_LAST_REPORT', 'WRR_STATUS_LABEL_KEYS', 'WRR_REQUIRED_FIELDS'];
const MUTABLE_STATE_NAMES = ['WRR_LAST_REPORT'];
const FUNCTION_NAMES = [
  't', 'applyStaticTranslations', 'setLanguage', 'scEsc',
  'wrrStatusLabel', 'wrrIsWellFormed', 'loadWasherResolutionReport',
  'wrrRenderAll', 'wrrSummaryCard', 'wrrRenderSummaryCards', 'wrrRenderDistribution',
  'wrrRenderIssueTypeDistribution', 'wrrRenderLatestDecisions',
  'wrrRenderIntegrity', 'wrrReapplyLanguage',
];

function buildExtractedSource() {
  const html = fs.readFileSync(FRONTEND_PATH, 'utf-8');
  const script = extractScript(html);
  const parts = [];
  for (const n of CONST_NAMES) {
    let decl = extractConstDecl(script, n);
    if (MUTABLE_STATE_NAMES.includes(n)) decl = toVarDecl(decl, n);
    parts.push(decl);
    if (n === 'CURRENT_LANG') {
      const anchor = /let\s+CURRENT_LANG\s*=[^;]*;/.exec(script);
      const rest = script.slice(anchor.index + anchor[0].length);
      const stMatch = /^\s*if\s*\(!I18N\[CURRENT_LANG\]\)\s*CURRENT_LANG\s*=\s*'tr';/.exec(rest);
      parts.push(stMatch[0]);
    }
  }
  for (const n of FUNCTION_NAMES) parts.push(extractFunctionDecl(script, n));
  parts.push('function __getCurrentLang() { return CURRENT_LANG; }');
  parts.push('function __getWrrLastReport() { return WRR_LAST_REPORT; }');
  parts.push('function __setWrrLastReport(v) { WRR_LAST_REPORT = v; }');
  return { source: parts.join('\n\n'), rawScript: script, rawHtml: html };
}

// ---------------------------------------------------------------
// Minimal DOM / localStorage stub (identical shape to the other
// harnesses)
// ---------------------------------------------------------------
function makeElement(id) {
  let _value = '';
  let _classes = new Set();
  return {
    id: id,
    _text: '',
    _html: '',
    disabled: false,
    checked: false,
    style: {},
    classList: {
      add(c) { _classes.add(c); },
      remove(c) { _classes.delete(c); },
      contains(c) { return _classes.has(c); },
    },
    set textContent(v) { this._text = String(v); },
    get textContent() { return this._text; },
    set innerHTML(v) { this._html = String(v); },
    get innerHTML() { return this._html; },
    set value(v) { _value = v; },
    get value() { return _value; },
  };
}

function makeLocalStorage(initial) {
  const store = new Map(Object.entries(initial || {}));
  return {
    getItem(k) { return store.has(k) ? store.get(k) : null; },
    setItem(k, v) { store.set(k, String(v)); },
    removeItem(k) { store.delete(k); },
  };
}

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
    el._attrs = { 'data-i18n': key };
    el.getAttribute = (n) => el._attrs[n] || null;
    return el;
  });
  return {
    _byId: byId,
    getElementById(id) {
      if (!(id in this._byId)) this._byId[id] = makeElement(id);
      return this._byId[id];
    },
    querySelectorAll(selector) {
      if (selector === '[data-i18n]') return dataI18nEls;
      if (selector === '.lang-btn') return [];
      return [];
    },
    querySelector() { return null; },
    addEventListener() {},
  };
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
function checkIncludes(name, haystack, needle) {
  check(name, typeof haystack === 'string' && haystack.indexOf(needle) !== -1);
}
function checkNotIncludes(name, haystack, needle) {
  check(name, typeof haystack === 'string' && haystack.indexOf(needle) === -1);
}

function newContext(extractedSource, rawHtml, apiRequestImpl, activePageId) {
  const byId = {};
  const documentStub = buildDom(rawHtml, byId);
  if (activePageId) {
    documentStub.getElementById('page-' + activePageId).classList.add('active');
  }
  const sandbox = {
    document: documentStub,
    localStorage: makeLocalStorage({}),
    sessionStorage: makeLocalStorage({}),
    console: console,
    apiRequest: apiRequestImpl || (() => { throw new Error('apiRequest should not be called by this test'); }),
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'wrr_extracted.js' });
  return { context, byId, documentStub };
}

function primeWrrElements(byId) {
  [
    'wrr-status', 'wrr-content', 'wrr-summary-cards', 'wrr-source-distribution',
    'wrr-effective-distribution', 'wrr-issue-type-distribution',
    'wrr-latest-decisions', 'wrr-integrity',
  ].forEach((id) => { byId[id] = makeElement(id); });
}

// Response fixture shaped exactly like the Faz 2.8.9 Stage 4 report
// payload (as wrapped by the Stage 5A API endpoint).
function fakeReport(overrides) {
  const base = {
    total_washer_records: 223,
    total_resolution_records: 76,
    source_status_distribution: {
      open: 71, under_review: 0, resolved: 0, accepted_as_is: 0,
      blocked_authoritative_source: 5, rejected: 0,
    },
    effective_status_distribution: {
      open: 70, under_review: 1, resolved: 0, accepted_as_is: 0,
      blocked_authoritative_source: 5, rejected: 0,
    },
    effective_open_count: 70,
    effective_under_review_count: 1,
    effective_terminal_count: 0,
    effective_blocked_count: 5,
    effective_resolved_count: 0,
    total_decision_count: 1,
    issue_type_distribution: {
      source_missing: 34, source_ambiguous: 0, standard_identity_ambiguous: 5,
      dimensional_conflict: 10, duplicate_or_alias: 0, verification_pending: 27, other: 0,
    },
    latest_decision_summary: [
      {
        resolution_id: 'RES-WASH-DIN127B-M10', effective_status: 'under_review',
        decision_count: 1, last_decision_new_status: 'under_review',
        last_decided_at: '2026-07-29T12:00:00Z', last_resolved_by: 'ilhan',
      },
    ],
    data_integrity_warning_count: 0,
    report_checksum: 'a'.repeat(64),
  };
  return Object.assign({}, base, overrides);
}

function fakeApiResponse(reportOverrides) {
  return { format: 'json', lang: 'tr', report: fakeReport(reportOverrides) };
}

// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// Test scenarios.
//
// Every scenario is declared as an `async function`, even the
// synchronous ones -- `await`ing a non-promise value is a no-op, so
// this lets `main()` await every scenario uniformly in one list
// without needing to track which are "really" async. This is the
// fix for the harness's original defect: previously, async
// scenarios returned a promise from a bare `(function(){...})()`
// IIFE that nothing awaited, so the final summary log and the
// unconditional process-exit call at the bottom of the file ran (as
// synchronous top-level code) before any of those promises' `.then()`
// callbacks ever fired -- their `check()` calls never executed, yet
// the harness still reported a misleadingly "clean" 8-assertion,
// 0-failure result every time, with no exit-code signal that
// anything async was silently skipped.
// ---------------------------------------------------------------

// 1. Successful load renders every section
async function testSuccessfulLoadRendersAllSections() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeApiResponse());
  primeWrrElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionReport()', ctx.context);
  checkIncludes('summary cards render total records', ctx.byId['wrr-summary-cards'].innerHTML, '76');
  checkIncludes('summary cards render effective open', ctx.byId['wrr-summary-cards'].innerHTML, '70');
  checkIncludes('source distribution rendered', ctx.byId['wrr-source-distribution'].innerHTML, '71');
  checkIncludes('effective distribution rendered', ctx.byId['wrr-effective-distribution'].innerHTML, '70');
  checkIncludes('issue type distribution rendered', ctx.byId['wrr-issue-type-distribution'].innerHTML, '34');
  checkIncludes('latest decisions table rendered', ctx.byId['wrr-latest-decisions'].innerHTML, 'RES-WASH-DIN127B-M10');
  checkIncludes('integrity checksum rendered', ctx.byId['wrr-integrity'].innerHTML, 'a'.repeat(64));
  check('content shown, status cleared', ctx.byId['wrr-content'].style.display === '');
}

// 2. Empty state: no decisions recorded
async function testNoDecisionsShowsEmptyStateNotEmptyTable() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeApiResponse({
    latest_decision_summary: [], total_decision_count: 0,
  }));
  primeWrrElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionReport()', ctx.context);
  const expectedMessage = vm.runInContext("t('wrr.no_decisions')", ctx.context);
  checkIncludes('empty-state message shown', ctx.byId['wrr-latest-decisions'].innerHTML, expectedMessage);
  checkNotIncludes('no <table> tag when there are no decisions', ctx.byId['wrr-latest-decisions'].innerHTML, '<table');
}

// 3. Integrity warning visible but non-destructive when count > 0
async function testIntegrityWarningShownWhenCountPositive() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeApiResponse({ data_integrity_warning_count: 2 }));
  primeWrrElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionReport()', ctx.context);
  checkIncludes('warning banner present', ctx.byId['wrr-integrity'].innerHTML, 'alert-warning');
  checkIncludes('warning count shown', ctx.byId['wrr-integrity'].innerHTML, '2');
  // Checksum must still render alongside the warning (non-destructive).
  checkIncludes('checksum still rendered with warning present', ctx.byId['wrr-integrity'].innerHTML, 'a'.repeat(64));
}

async function testNoWarningBannerWhenCountIsZero() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeApiResponse({ data_integrity_warning_count: 0 }));
  primeWrrElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionReport()', ctx.context);
  checkNotIncludes('no warning banner when count is 0', ctx.byId['wrr-integrity'].innerHTML, 'alert-warning');
}

// 4. Loading and API-error states
async function testApiErrorShowsSafeMessageNotStackTrace() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('network unreachable'); });
  primeWrrElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionReport()', ctx.context);
  checkIncludes('error message surfaced', ctx.byId['wrr-status'].innerHTML, 'network unreachable');
  checkIncludes('error uses alert-danger styling', ctx.byId['wrr-status'].innerHTML, 'alert-danger');
  check('content stays hidden on error', ctx.byId['wrr-content'].style.display === 'none');
}

// 5. Malformed response protection -- never guesses
async function testMalformedResponseMissingFieldsIsRejected() {
  const ctx = newContext(EXTRACTED, HTML, async () => ({ format: 'json', lang: 'tr', report: { total_resolution_records: 76 } }));
  primeWrrElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionReport()', ctx.context);
  check('malformed response leaves content hidden', ctx.byId['wrr-content'].style.display === 'none');
  checkIncludes('malformed response shows a clear message, not partial data', ctx.byId['wrr-status'].innerHTML, 'alert-danger');
  checkNotIncludes('malformed response does not render summary cards with guessed values', ctx.byId['wrr-summary-cards'].innerHTML, '76');
}

async function testWrrIsWellFormedRejectsNullAndMissingFields() {
  const ctx = newContext(EXTRACTED, HTML);
  const wellFormedResult = vm.runInContext(
    '__setWrrLastReport(null); wrrIsWellFormed(' + JSON.stringify(fakeReport()) + ')', ctx.context
  );
  check('well-formed fixture accepted', wellFormedResult === true);
  const nullResult = vm.runInContext('wrrIsWellFormed(null)', ctx.context);
  check('null report rejected', nullResult === false);
  const partialResult = vm.runInContext('wrrIsWellFormed({total_resolution_records: 1})', ctx.context);
  check('partial report rejected', partialResult === false);
}

// 6. Status labels resolve via t(), not raw codes, in both languages
async function testStatusLabelsAreTranslatedNotRawCodes() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeApiResponse());
  primeWrrElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionReport()', ctx.context);
  const expectedBlockedLabel = vm.runInContext("t('wrr.status.blocked_authoritative_source')", ctx.context);
  checkIncludes(
    'blocked status renders its translated label',
    ctx.byId['wrr-source-distribution'].innerHTML,
    expectedBlockedLabel
  );
  checkNotIncludes(
    'source distribution does not leak the raw status code',
    ctx.byId['wrr-source-distribution'].innerHTML,
    'blocked_authoritative_source'
  );
}

// 7. Language switch re-renders from cache, no extra network call
async function testLanguageSwitchRerendersWithoutRefetch() {
  let apiCallCount = 0;
  const ctx = newContext(EXTRACTED, HTML, async () => { apiCallCount++; return fakeApiResponse(); }, 'washerresolution');
  primeWrrElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionReport()', ctx.context);
  const callsAfterLoad = apiCallCount;
  vm.runInContext("setLanguage('en')", ctx.context);
  check('language switch does not refetch the report', apiCallCount === callsAfterLoad);
  checkIncludes('re-rendered content still present after language switch', ctx.byId['wrr-summary-cards'].innerHTML, '76');
}

async function testReapplyLanguageNoOpWhenPageNotActive() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeApiResponse(), null);
  primeWrrElements(ctx.byId);
  vm.runInContext('__setWrrLastReport(' + JSON.stringify(fakeReport()) + ')', ctx.context);
  vm.runInContext('wrrReapplyLanguage()', ctx.context);
  check('no rendering attempted when washer resolution page is not active', ctx.byId['wrr-summary-cards'].innerHTML === '');
}

// 8. Sidebar / page presence
async function testSidebarAndPageMarkupPresent() {
  check("sidebar item present", HTML.indexOf("showPage('washerresolution')") !== -1);
  check('page container present', HTML.indexOf('id="page-washerresolution"') !== -1);
}

// 9. Static translation coverage
async function testStaticTranslationApplied() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext("applyStaticTranslations()", ctx.context);
  const dataI18nEls = ctx.documentStub.querySelectorAll('[data-i18n]');
  const wrrEls = dataI18nEls.filter((el) => el.getAttribute('data-i18n').indexOf('wrr.') === 0);
  check('at least one wrr.* data-i18n element found', wrrEls.length > 0);
  check('every wrr.* element received non-empty translated text', wrrEls.every((el) => el.textContent && el.textContent.length > 0));
}

const ALL_TESTS = [
  testSuccessfulLoadRendersAllSections,
  testNoDecisionsShowsEmptyStateNotEmptyTable,
  testIntegrityWarningShownWhenCountPositive,
  testNoWarningBannerWhenCountIsZero,
  testApiErrorShowsSafeMessageNotStackTrace,
  testMalformedResponseMissingFieldsIsRejected,
  testWrrIsWellFormedRejectsNullAndMissingFields,
  testStatusLabelsAreTranslatedNotRawCodes,
  testLanguageSwitchRerendersWithoutRefetch,
  testReapplyLanguageNoOpWhenPageNotActive,
  testSidebarAndPageMarkupPresent,
  testStaticTranslationApplied,
];

// =================================================================
async function main() {
  for (const testFn of ALL_TESTS) {
    try {
      await testFn();
    } catch (err) {
      fail++;
      const label = testFn.name + ' (threw)';
      failures.push(label);
      console.log('FAIL: ' + label + ' -- ' + (err && err.stack ? err.stack : String(err)));
    }
  }
  console.log((pass + fail) + ' assertions, ' + pass + ' passed, ' + fail + ' failed');
  if (fail > 0) {
    console.log('Failures:\n  - ' + failures.join('\n  - '));
    process.exitCode = 1;
    return;
  }
  process.exitCode = 0;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
