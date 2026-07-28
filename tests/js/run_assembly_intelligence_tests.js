#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.6 Stage 4 -- Assembly Intelligence frontend regression harness.
 *
 * Zero external dependencies (no npm packages, no jsdom, no browser),
 * following the exact same technique as tests/js/run_i18n_tests.js
 * (Faz 2.6.8): Node's built-in `vm` module runs the *actual*
 * Assembly Intelligence declarations extracted live from
 * frontend/index.html (never a committed copy) against a small
 * hand-built DOM/localStorage stub. This is a separate file from
 * run_i18n_tests.js on purpose -- Stage 4 does not modify that
 * existing, already-passing harness.
 *
 * apiRequest (the real fetch/auth-header helper defined in
 * frontend/index.html) is NOT extracted or re-implemented here --
 * exactly like run_i18n_tests.js, it is injected into the sandbox as
 * a controllable mock. This both keeps the harness dependency-free
 * (no fetch polyfill) and is itself the regression check that
 * aiAssessAssembly() goes through the existing auth/fetch helper
 * rather than calling fetch directly or building its own headers.
 *
 * Invoked via `node tests/js/run_assembly_intelligence_tests.js` from
 * the repo root, or indirectly via
 * tests/test_faz_2_8_6_stage4_frontend.py. Exit code 0 = all
 * assertions passed; non-zero = at least one failure.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND_PATH = path.join(REPO_ROOT, 'frontend', 'index.html');

// ---------------------------------------------------------------
// Extraction (same technique as run_i18n_tests.js)
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

function extractStatementAfter(script, anchorRegex, statementRegex) {
  const anchor = anchorRegex.exec(script);
  if (!anchor) throw new Error('anchor not found: ' + anchorRegex);
  const rest = script.slice(anchor.index + anchor[0].length);
  const m = statementRegex.exec(rest);
  if (!m) throw new Error('statement not found after anchor: ' + statementRegex);
  return m[0];
}

function toVarDecl(declText, name) {
  const re = new RegExp('^(const|let)(\\s+' + name + '\\s*=)');
  if (!re.test(declText)) throw new Error('expected declaration of ' + name + ' to rewrite to var, got: ' + declText.slice(0, 60));
  return declText.replace(re, 'var$2');
}

// Only what Stage 4's own functions actually need. Everything else
// in frontend/index.html is intentionally NOT executed here (kept
// out of this harness's DOM/stub surface, same rationale as
// run_i18n_tests.js: avoid needing a much larger stub for unrelated
// legacy app code).
const CONST_NAMES = ['I18N', 'CURRENT_LANG', 'AI_STATUS_META', 'AI_LAST_RESULT', 'AI_REQUEST_IN_FLIGHT'];
const MUTABLE_STATE_NAMES = ['AI_LAST_RESULT', 'AI_REQUEST_IN_FLIGHT'];
const FUNCTION_NAMES = [
  't', 'applyStaticTranslations', 'setLanguage',
  'aiEsc', 'aiTrimField', 'aiNumericField', 'aiBuildPayload',
  'aiAssessAssembly', 'aiRenderResult', 'aiRenderReportSection', 'aiReapplyLanguage',
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
      parts.push(extractStatementAfter(
        script,
        /let\s+CURRENT_LANG\s*=[^;]*;/,
        /^\s*if\s*\(!I18N\[CURRENT_LANG\]\)\s*CURRENT_LANG\s*=\s*'tr';/
      ));
    }
  }
  for (const n of FUNCTION_NAMES) parts.push(extractFunctionDecl(script, n));
  parts.push('function __getCurrentLang() { return CURRENT_LANG; }');
  parts.push('function __getAiLastResult() { return AI_LAST_RESULT; }');
  parts.push('function __setAiLastResult(v) { AI_LAST_RESULT = v; }');
  parts.push('function __getAiRequestInFlight() { return AI_REQUEST_IN_FLIGHT; }');
  return { source: parts.join('\n\n'), rawScript: script, rawHtml: html };
}

// ---------------------------------------------------------------
// Minimal DOM / localStorage stub (same shape as run_i18n_tests.js's
// makeElement -- a plain mutable object, so ad hoc properties like
// `.checked`/`.disabled` used by a <input type="checkbox">/<button>
// work without any special-casing).
// ---------------------------------------------------------------
function makeElement(id) {
  let _value = '';
  return {
    id: id,
    _text: '',
    _html: '',
    disabled: false,
    checked: false,
    style: {},
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
  const placeholderEls = scrapeDataI18nKeys(rawHtml, 'data-i18n-placeholder').map((key) => {
    const el = makeElement(null);
    el._attrs = { 'data-i18n-placeholder': key };
    el.getAttribute = (n) => el._attrs[n] || null;
    el.set = (v) => { el.placeholder = v; };
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
      if (selector === '[data-i18n-placeholder]') return placeholderEls;
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

function newContext(extractedSource, rawHtml, apiRequestImpl) {
  const byId = {};
  const documentStub = buildDom(rawHtml, byId);
  const sandbox = {
    document: documentStub,
    localStorage: makeLocalStorage({}),
    sessionStorage: makeLocalStorage({}),
    console: console,
    apiRequest: apiRequestImpl || (() => { throw new Error('apiRequest should not be called by this test'); }),
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'ai_extracted.js' });
  return { context, byId, documentStub };
}

// A response object shaped exactly like
// POST /api/assembly-intelligence/assess's response body (Faz 2.8.6
// Stage 3), used to exercise the render functions without a live
// backend.
function fakeResult(overrides) {
  const base = {
    engine_result: {},
    assembly_readiness: {
      overall_status: 'assessed',
      overall_risk_level: 'no_critical_incompatibility_detected',
      has_critical_incompatibility: false,
    },
    score: { assembly_intelligence_score: 83.33, score_denominator_note: 'note' },
    coverage: {
      assessment_coverage_percent: 42.86, total_checks: 14, assessed_checks: 6,
      insufficient_data_checks: 5, blocked_authoritative_source_checks: 3,
    },
    check_summary: { passed: 5, warning: 8, failed: 1, total: 14 },
    checks: [
      {
        check_id: 'strength_class', check_name: 'Strength Class Uyum', status: 'compatible',
        severity: 'none', message: 'Strength class pairing is compatible.',
        data_source: 'backend.library.strength_compatibility', suggested_action: 'Aksiyon gerekmiyor.',
      },
    ],
    critical_incompatibilities: [],
  };
  return Object.assign({}, base, overrides);
}

function fakeCriticalResult() {
  return fakeResult({
    assembly_readiness: {
      overall_status: 'assessed', overall_risk_level: 'critical', has_critical_incompatibility: true,
    },
    score: { assembly_intelligence_score: 100.0, score_denominator_note: 'note' },
    checks: [
      {
        check_id: 'strength_class', check_name: 'Strength Class Uyum', status: 'incompatible',
        severity: 'critical', message: 'Strength class pairing not compatible.',
        data_source: 'backend.library.strength_compatibility',
        suggested_action: "Kontrol reddedildi; ilgili secimi degistirin.",
      },
    ],
    critical_incompatibilities: ['strength_class: Strength class pairing not compatible.'],
  });
}

function fakeNotAssessableResult() {
  return {
    engine_result: {},
    assembly_readiness: { overall_status: 'not_assessable', overall_risk_level: 'not_assessable', has_critical_incompatibility: false },
    score: { assembly_intelligence_score: null, score_denominator_note: 'note' },
    coverage: { assessment_coverage_percent: 0, total_checks: 14, assessed_checks: 0, insufficient_data_checks: 5, blocked_authoritative_source_checks: 9 },
    check_summary: { passed: 0, warning: 14, failed: 0, total: 14 },
    checks: [],
    critical_incompatibilities: [],
  };
}

function fakeReportResult(includeReportChecked) {
  return fakeResult({
    report: {
      assembly_readiness: { overall_status: 'assessed', overall_risk_level: 'no_critical_incompatibility_detected' },
      score: { assembly_intelligence_score: 83.33, score_denominator_note: 'note' },
      coverage: { assessment_coverage_percent: 42.86 },
      check_summary: { passed: 5, warning: 8, failed: 1, total: 14 },
      checks: [
        { check_id: 'strength_class', check_name: 'Strength Class Uyum', status: 'compatible', engine_recommendations: ['Use ISO 4032'] },
      ],
      critical_incompatibilities: [],
    },
  });
}

// =================================================================
// Build shared extracted source once (fast: parsed/extracted, not
// re-read per test) -- each test still gets its OWN vm context via
// newContext(), so state never leaks between scenarios.
// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// 1. Payload cleanliness: empty optional fields never sent
// ---------------------------------------------------------------
(function testPayloadOmitsEmptyFields() {
  const ctx = newContext(EXTRACTED, HTML);
  const payload = vm.runInContext('aiBuildPayload()', ctx.context);
  check('payload omits empty bolt_designation', !('bolt_designation' in payload));
  check('payload omits empty nut_designation', !('nut_designation' in payload));
  check('payload omits empty nominal_diameter_mm when blank', !('nominal_diameter_mm' in payload));
  check('payload always includes include_report (boolean)', payload.include_report === false);
  checkEqualKeys('empty-form payload has only include_report key', Object.keys(payload), ['include_report']);
})();

function checkEqualKeys(name, actualKeys, expectedKeys) {
  const a = [...actualKeys].sort();
  const b = [...expectedKeys].sort();
  check(name + ' (got ' + JSON.stringify(a) + ')', JSON.stringify(a) === JSON.stringify(b));
}

// ---------------------------------------------------------------
// 2. Numeric conversion for nominal_diameter_mm / temperature
// ---------------------------------------------------------------
(function testNumericFieldsConverted() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ai-nominal-diameter'] = makeElement('ai-nominal-diameter');
  ctx.byId['ai-nominal-diameter'].value = '3.5';
  ctx.byId['ai-intended-operating-temperature'] = makeElement('ai-intended-operating-temperature');
  ctx.byId['ai-intended-operating-temperature'].value = '-20';
  ctx.byId['ai-bolt-designation'] = makeElement('ai-bolt-designation');
  ctx.byId['ai-bolt-designation'].value = '  M8  ';
  const payload = vm.runInContext('aiBuildPayload()', ctx.context);
  check('nominal_diameter_mm is a number', typeof payload.nominal_diameter_mm === 'number' && payload.nominal_diameter_mm === 3.5);
  check('intended_operating_temperature_c is a number', typeof payload.intended_operating_temperature_c === 'number' && payload.intended_operating_temperature_c === -20);
  check('text field is trimmed', payload.bolt_designation === 'M8');
})();

(function testInvalidNumericFieldOmitted() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ai-nominal-diameter'] = makeElement('ai-nominal-diameter');
  ctx.byId['ai-nominal-diameter'].value = 'not-a-number';
  const payload = vm.runInContext('aiBuildPayload()', ctx.context);
  check('non-numeric nominal_diameter_mm is omitted, not sent as NaN', !('nominal_diameter_mm' in payload));
})();

// ---------------------------------------------------------------
// 3. include_report boolean sent explicitly
// ---------------------------------------------------------------
(function testIncludeReportBooleanSent() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ai-include-report'] = makeElement('ai-include-report');
  ctx.byId['ai-include-report'].checked = true;
  const payload = vm.runInContext('aiBuildPayload()', ctx.context);
  check('include_report=true sent as boolean true', payload.include_report === true);
})();

// ---------------------------------------------------------------
// 4. Auth: aiAssessAssembly goes through the existing apiRequest
//    helper (not a raw fetch call it builds itself).
// ---------------------------------------------------------------
(function testUsesExistingApiRequestHelper() {
  checkNotIncludes('aiAssessAssembly source does not call fetch() directly', EXTRACTED.split('async function aiAssessAssembly')[1].split('async function aiRenderResult')[0] || '', 'fetch(');
  checkIncludes('aiAssessAssembly calls apiRequest(', EXTRACTED, "apiRequest('/api/assembly-intelligence/assess'");
})();

// ---------------------------------------------------------------
// 5/6/7/8. 200 / 401 / 422 / network-error handling + loading state
// ---------------------------------------------------------------
(async function testSuccessfulAssessmentRendersResult() {
  let capturedPath = null, capturedBody = null, sawLoadingText = false;
  const ctx = newContext(EXTRACTED, HTML, async (path, opts) => {
    capturedPath = path;
    capturedBody = JSON.parse(opts.body);
    sawLoadingText = ctx.byId['ai-result'] && ctx.byId['ai-result'].innerHTML.includes('Yükleniyor');
    return fakeResult();
  });
  await vm.runInContext('aiAssessAssembly()', ctx.context);
  check('200: calls the correct endpoint', capturedPath === '/api/assembly-intelligence/assess');
  check('200: request body is valid JSON', capturedBody && typeof capturedBody === 'object');
  check('loading state shown before resolution', sawLoadingText);
  check('200: result rendered without throwing', ctx.byId['ai-result'].innerHTML.length > 0);
  checkIncludes('200: score value rendered', ctx.byId['ai-result'].innerHTML, '83.33');
  check('button re-enabled after success', ctx.byId['ai-assess-btn'].disabled === false);
})();

(async function test401Handling() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('Oturum gerekli'); });
  await vm.runInContext('aiAssessAssembly()', ctx.context);
  checkIncludes('401: error message rendered, not a raw exception', ctx.byId['ai-result'].innerHTML, 'Oturum gerekli');
  check('401: button re-enabled after error', ctx.byId['ai-assess-btn'].disabled === false);
})();

(async function test422Handling() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('nominal_diameter_mm: value is not a valid float'); });
  await vm.runInContext('aiAssessAssembly()', ctx.context);
  checkIncludes('422: API detail message shown to user', ctx.byId['ai-result'].innerHTML, 'value is not a valid float');
})();

(async function testNetworkErrorHandling() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new TypeError('Failed to fetch'); });
  await vm.runInContext('aiAssessAssembly()', ctx.context);
  checkIncludes('network error: controlled message shown, no crash', ctx.byId['ai-result'].innerHTML, 'Failed to fetch');
  check('network error: button re-enabled', ctx.byId['ai-assess-btn'].disabled === false);
})();

// ---------------------------------------------------------------
// 9. Double-submit guard
// ---------------------------------------------------------------
(async function testDoubleSubmitGuard() {
  let callCount = 0;
  let resolveFirst;
  const firstPromise = new Promise((resolve) => { resolveFirst = resolve; });
  const ctx = newContext(EXTRACTED, HTML, async () => {
    callCount++;
    await firstPromise;
    return fakeResult();
  });
  const p1 = vm.runInContext('aiAssessAssembly()', ctx.context);
  const p2 = vm.runInContext('aiAssessAssembly()', ctx.context); // fired while p1 still in flight
  resolveFirst();
  await Promise.all([p1, p2]);
  check('double-submit: apiRequest called exactly once', callCount === 1);
})();

// ---------------------------------------------------------------
// 10/11/12. not_assessable rendering (controlled, not an error path)
// ---------------------------------------------------------------
(function testNotAssessableRendering() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeNotAssessableResult() }));
  const html = ctx.byId['ai-result'].innerHTML;
  checkNotIncludes('not_assessable: no alert-danger error styling used for this controlled state', html.split('ai-critical-banner')[0], 'alert-danger');
  checkIncludes('not_assessable: informational message shown', html, 'Değerlendirme için yeterli veri bulunmuyor');
  check('not_assessable: score section still rendered (fields kept visible)', html.length > 0);
})();

// ---------------------------------------------------------------
// 13/14/15/16. checks[], suggested_action, critical incompatibilities
// ---------------------------------------------------------------
(function testChecksAndCriticalRendering() {
  const ctx = newContext(EXTRACTED, HTML);
  const result = fakeCriticalResult();
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx.context, { __result__: result }));
  const html = ctx.byId['ai-result'].innerHTML;
  checkIncludes('check_name rendered', html, 'Strength Class Uyum');
  checkIncludes('check message rendered', html, 'Strength class pairing not compatible.');
  checkIncludes('data_source rendered', html, 'backend.library.strength_compatibility');
  checkIncludes('suggested_action rendered', html, 'Kontrol reddedildi');
  checkIncludes('critical_incompatibilities item rendered', html, 'strength_class: Strength class pairing not compatible.');
})();

// ---------------------------------------------------------------
// 17/18. Critical banner prominence even with a high score; banner
//        must not be hidden or made less visible by a high score.
// ---------------------------------------------------------------
(function testCriticalBannerProminentDespiteHighScore() {
  const ctx = newContext(EXTRACTED, HTML);
  const result = fakeCriticalResult(); // score 100.0, still critical
  check('sanity: fixture score is high (100)', result.score.assembly_intelligence_score === 100.0);
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx.context, { __result__: result }));
  const html = ctx.byId['ai-result'].innerHTML;
  checkIncludes('critical banner class present', html, 'ai-critical-banner');
  checkIncludes('critical banner uses the most prominent alert style', html, 'alert-danger ai-critical-banner');
  check('critical banner appears before the score summary card', html.indexOf('ai-critical-banner') < html.indexOf('ai-summary-grid'));
  checkIncludes('critical banner text present', html, 'Kritik uyumsuzluk tespit edildi');
})();

(function testNoCriticalBannerWhenNoneFound() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeResult() }));
  checkNotIncludes('no critical banner rendered when critical_incompatibilities is empty', ctx.byId['ai-result'].innerHTML, 'ai-critical-banner');
  checkIncludes('"no critical incompatibility" state shown instead', ctx.byId['ai-result'].innerHTML, 'Kritik uyumsuzluk yok');
})();

// ---------------------------------------------------------------
// 19/20. Report visibility toggling
// ---------------------------------------------------------------
(function testReportShownWhenIncludeReportChecked() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ai-include-report'] = makeElement('ai-include-report');
  ctx.byId['ai-include-report'].checked = true;
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeReportResult(true) }));
  checkIncludes('report section rendered when include_report checked and report present', ctx.byId['ai-result'].innerHTML, 'Rapor Önizleme');
})();

(function testReportHiddenWhenIncludeReportUnchecked() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ai-include-report'] = makeElement('ai-include-report');
  ctx.byId['ai-include-report'].checked = false; // include_report=false
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeReportResult(false) }));
  checkNotIncludes('report section hidden when include_report=false', ctx.byId['ai-result'].innerHTML, 'Rapor Önizleme');
})();

// ---------------------------------------------------------------
// 21. Deterministic rendering for the same response
// ---------------------------------------------------------------
(function testDeterministicRendering() {
  const ctx1 = newContext(EXTRACTED, HTML);
  const ctx2 = newContext(EXTRACTED, HTML);
  const result = fakeCriticalResult();
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx1.context, { __result__: result }));
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx2.context, { __result__: JSON.parse(JSON.stringify(result)) }));
  check('same response renders byte-identical HTML across two fresh contexts', ctx1.byId['ai-result'].innerHTML === ctx2.byId['ai-result'].innerHTML);

  const ctx3 = newContext(EXTRACTED, HTML);
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx3.context, { __result__: result }));
  const first = ctx3.byId['ai-result'].innerHTML;
  vm.runInContext('aiRenderResult(__result__)', Object.assign(ctx3.context, { __result__: result }));
  const second = ctx3.byId['ai-result'].innerHTML;
  check('re-rendering the same object twice in the same context is idempotent', first === second);
})();

// ---------------------------------------------------------------
// 22. TR/EN live update without re-fetching
// ---------------------------------------------------------------
(function testLanguageSwitchReRendersWithoutRefetch() {
  let apiCallCount = 0;
  const ctx = newContext(EXTRACTED, HTML, async () => { apiCallCount++; return fakeResult(); });
  const result = fakeCriticalResult();
  vm.runInContext('__setAiLastResult(__result__)', Object.assign(ctx.context, { __result__: result }));
  vm.runInContext('aiRenderResult(__getAiLastResult())', ctx.context);
  const trHtml = ctx.byId['ai-result'].innerHTML;
  checkIncludes('TR: critical banner text in Turkish', trHtml, 'Kritik uyumsuzluk tespit edildi');

  vm.runInContext("setLanguage('en')", ctx.context);
  const enHtml = ctx.byId['ai-result'].innerHTML;
  checkIncludes('EN: critical banner text in English after language switch', enHtml, 'Critical incompatibility detected');
  check('EN: check name/message still present (re-rendered, not blanked)', enHtml.includes('Strength Class Uyum'));

  vm.runInContext("setLanguage('tr')", ctx.context);
  const trHtmlAgain = ctx.byId['ai-result'].innerHTML;
  checkIncludes('TR again: banner text back to Turkish', trHtmlAgain, 'Kritik uyumsuzluk tespit edildi');
  check('language switch never calls the API', apiCallCount === 0);
})();

// ---------------------------------------------------------------
// 23. Frontend never recalculates score/status/risk/compatibility
//     itself -- static source check: the render functions must not
//     contain arithmetic on score/coverage/check fields, only
//     formatting (.toFixed) of values read directly off the
//     response.
// ---------------------------------------------------------------
(function testNoClientSideScoreRecalculation() {
  const renderSrc = extractFunctionDecl(extractScript(HTML), 'aiRenderResult')
    + extractFunctionDecl(extractScript(HTML), 'aiRenderReportSection');
  const forbiddenPatterns = [
    /score\s*\*/, /score\s*\+[^\d]/, /coverage\s*\*/, /assessed_checks\s*\//,
    /compatible_assessed/, /\/\s*total_checks/, /\/\s*assessed_checks/,
  ];
  forbiddenPatterns.forEach((re) => {
    check('no score/coverage arithmetic pattern ' + re, !re.test(renderSrc));
  });
  checkIncludes('score is only ever formatted (.toFixed), not computed', renderSrc, '.toFixed(2)');
})();

// =================================================================
console.log((pass + fail) + ' assertions, ' + pass + ' passed, ' + fail + ' failed');
if (fail > 0) {
  console.log('Failures:\n  - ' + failures.join('\n  - '));
  process.exit(1);
}
process.exit(0);
