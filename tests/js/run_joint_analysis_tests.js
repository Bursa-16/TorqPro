#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.7 -- Joint Analysis & Torque Optimization frontend
 * regression harness.
 *
 * Zero external dependencies, same technique as
 * tests/js/run_i18n_tests.js and
 * tests/js/run_assembly_intelligence_tests.js: Node's built-in `vm`
 * module runs the *actual* Joint Analysis declarations extracted live
 * from frontend/index.html (never a committed copy) against a small
 * hand-built DOM/localStorage stub. Separate file on purpose -- does
 * not modify either existing, already-passing harness.
 *
 * Invoked via `node tests/js/run_joint_analysis_tests.js` from the
 * repo root, or indirectly via tests/test_faz_2_8_7_frontend.py.
 * Exit code 0 = all assertions passed; non-zero = at least one
 * failure.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND_PATH = path.join(REPO_ROOT, 'frontend', 'index.html');

// ---------------------------------------------------------------
// Extraction (same technique as the other two harnesses)
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

// Only what Joint Analysis's own functions actually need -- same
// rationale as the other two harnesses: avoid needing a much larger
// stub for unrelated legacy app code.
const CONST_NAMES = [
  'I18N', 'CURRENT_LANG',
  'JA_LAST_RESULT', 'JA_REQUEST_IN_FLIGHT',
  'JA_READINESS_KEY', 'JA_SAFETY_STATUS_KEY', 'JA_SAFETY_STATUS_CLASS', 'JA_UNSUPPORTED_KEY',
];
const MUTABLE_STATE_NAMES = ['JA_LAST_RESULT', 'JA_REQUEST_IN_FLIGHT'];
const FUNCTION_NAMES = [
  't', 'applyStaticTranslations', 'setLanguage',
  'jaEsc', 'jaNumericField', 'jaFmtNum', 'jaBuildPayload',
  'jaCalculate', 'jaReset', 'jaRenderResult', 'jaReapplyLanguage',
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
  parts.push('function __getJaLastResult() { return JA_LAST_RESULT; }');
  parts.push('function __setJaLastResult(v) { JA_LAST_RESULT = v; }');
  parts.push('function __getJaRequestInFlight() { return JA_REQUEST_IN_FLIGHT; }');
  return { source: parts.join('\n\n'), rawScript: script, rawHtml: html };
}

// ---------------------------------------------------------------
// Minimal DOM / localStorage stub (identical shape to the other two
// harnesses).
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
  vm.runInContext(extractedSource, context, { filename: 'ja_extracted.js' });
  return { context, byId, documentStub };
}

// Response shaped exactly like POST /api/engineering/joint-analysis's
// response body (Faz 2.8.7), used to exercise the render functions
// without a live backend.
function fakeResult(overrides) {
  const base = {
    calculated_values: {
      stress_area_mm2: 57.99, target_preload_n: 41752.42,
      bolt_stiffness_n_per_mm: 406000.0, joint_stiffness_n_per_mm: 1575000.0,
      phi: 0.2049, bolt_load_increase_n: 1024.73, residual_clamp_load_n: 37777.16,
      recommended_torque_nm: 71.41, preload_from_applied_torque_n: 26309.10,
      torque_window_min_nm: 20.48, torque_window_max_nm: 80.34,
      yield_utilization: 0.8196, safety_factor: 1.2201,
    },
    torque_window: { min_nm: 20.48, max_nm: 80.34, recommended_nm: 71.41, min_not_evaluable_reason: null, max_not_evaluable_reason: null },
    safety: { status: 'pass', message: 'Utilization within limits', utilization: 0.8196, safety_factor: 1.2201 },
    coverage: { evaluated: {}, evaluated_count: 13, total_count: 13, coverage_percent: 100.0, missing_inputs_for: {} },
    readiness: 'full',
    warnings: ['VDI2230_AS (A_s) is PROVISIONAL: independent validation not yet complete.'],
    critical_findings: [],
    formula_trace: [
      { formula_id: 'VDI2230_AS', symbol: 'A_s', unit: 'mm^2', source: 'docs/05...', classification: 'QUICK', validation_status: 'PROVISIONAL' },
    ],
    unsupported_effects: [
      'settlement_embedment', 'thermal_preload_change', 'relaxation_creep',
      'torque_angle_tightening', 'multi_step_tightening', 'sequence_optimization',
      'full_vdi2230_compliance', 'fea', 'ai_ml_torque_prediction',
    ],
    inputs: { applied_torque_nm: 45.0 },
  };
  return Object.assign({}, base, overrides);
}

function fakeInsufficientDataResult() {
  return {
    calculated_values: {
      stress_area_mm2: null, target_preload_n: null, bolt_stiffness_n_per_mm: null,
      joint_stiffness_n_per_mm: null, phi: null, bolt_load_increase_n: null,
      residual_clamp_load_n: null, recommended_torque_nm: null,
      preload_from_applied_torque_n: null, torque_window_min_nm: null,
      torque_window_max_nm: null, yield_utilization: null, safety_factor: null,
    },
    torque_window: { min_nm: null, max_nm: null, recommended_nm: null, min_not_evaluable_reason: 'x', max_not_evaluable_reason: 'y' },
    safety: { status: 'missing_input', message: 'stress_mpa/limit_mpa not supplied', utilization: null, safety_factor: null },
    coverage: { evaluated: {}, evaluated_count: 0, total_count: 13, coverage_percent: 0.0, missing_inputs_for: { stress_area_mm2: ['diameter_mm', 'pitch_mm'] } },
    readiness: 'insufficient_data',
    warnings: [],
    critical_findings: [],
    formula_trace: [],
    unsupported_effects: ['settlement_embedment'],
    inputs: {},
  };
}

function fakeCriticalResult() {
  return fakeResult({
    calculated_values: Object.assign({}, fakeResult().calculated_values, { residual_clamp_load_n: -24095.49 }),
    safety: { status: 'fail', message: 'Utilization exceeds fail threshold', utilization: 1.35, safety_factor: 0.74 },
    critical_findings: [
      'residual_clamp_load_negative: computed residual clamp load is -24095.5 N (< 0) -- the joint is predicted to separate under the supplied external axial load.',
      'yield_utilization_fail: Utilization exceeds fail threshold (utilization=1.35)',
    ],
  });
}

// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// 1. Payload cleanliness: empty optional fields never sent
// ---------------------------------------------------------------
(function testPayloadOmitsEmptyFields() {
  const ctx = newContext(EXTRACTED, HTML);
  const payload = vm.runInContext('jaBuildPayload()', ctx.context);
  check('empty-form payload has no keys at all', Object.keys(payload).length === 0);
})();

// ---------------------------------------------------------------
// 2. Numeric conversion, trimming, invalid-number omission
// ---------------------------------------------------------------
(function testNumericFieldsConverted() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ja-diameter-mm'] = makeElement('ja-diameter-mm');
  ctx.byId['ja-diameter-mm'].value = '10';
  ctx.byId['ja-pitch-mm'] = makeElement('ja-pitch-mm');
  ctx.byId['ja-pitch-mm'].value = '  1.5  ';
  const payload = vm.runInContext('jaBuildPayload()', ctx.context);
  check('diameter_mm is a number', typeof payload.diameter_mm === 'number' && payload.diameter_mm === 10);
  check('pitch_mm parsed despite surrounding whitespace', payload.pitch_mm === 1.5);
})();

(function testInvalidNumericFieldOmitted() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ja-diameter-mm'] = makeElement('ja-diameter-mm');
  ctx.byId['ja-diameter-mm'].value = 'not-a-number';
  const payload = vm.runInContext('jaBuildPayload()', ctx.context);
  check('non-numeric diameter_mm is omitted, not sent as NaN', !('diameter_mm' in payload));
  check('payload never contains NaN', !Object.values(payload).some((v) => typeof v === 'number' && Number.isNaN(v)));
})();

// ---------------------------------------------------------------
// 3. Segment payload: only sent when fully filled in
// ---------------------------------------------------------------
(function testPartialSegmentOmitted() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ja-bolt-seg-length'] = makeElement('ja-bolt-seg-length');
  ctx.byId['ja-bolt-seg-length'].value = '30';
  // modulus/area left blank -- segment must not be sent partially.
  const payload = vm.runInContext('jaBuildPayload()', ctx.context);
  check('partially filled bolt segment is omitted entirely', !('bolt_segments' in payload));
})();

(function testFullSegmentIncluded() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ja-bolt-seg-length'] = makeElement('ja-bolt-seg-length');
  ctx.byId['ja-bolt-seg-length'].value = '30';
  ctx.byId['ja-bolt-seg-modulus'] = makeElement('ja-bolt-seg-modulus');
  ctx.byId['ja-bolt-seg-modulus'].value = '210000';
  ctx.byId['ja-bolt-seg-area'] = makeElement('ja-bolt-seg-area');
  ctx.byId['ja-bolt-seg-area'].value = '58';
  const payload = vm.runInContext('jaBuildPayload()', ctx.context);
  check('fully filled bolt segment is included', Array.isArray(payload.bolt_segments) && payload.bolt_segments.length === 1);
  check('segment values are numbers', payload.bolt_segments[0].length_mm === 30 && payload.bolt_segments[0].modulus_mpa === 210000 && payload.bolt_segments[0].area_mm2 === 58);
})();

// ---------------------------------------------------------------
// 4. Uses the existing apiRequest/auth helper, not a bespoke fetch
// ---------------------------------------------------------------
(function testUsesExistingApiRequestHelper() {
  checkNotIncludes('jaCalculate source does not call fetch() directly', EXTRACTED.split('async function jaCalculate')[1].split('function jaReset')[0] || '', 'fetch(');
  checkIncludes('jaCalculate calls apiRequest(', EXTRACTED, "apiRequest('/api/engineering/joint-analysis'");
})();

// ---------------------------------------------------------------
// 5. Successful response render + loading state + button re-enable
// ---------------------------------------------------------------
(async function testSuccessfulCalculationRendersResult() {
  let capturedPath = null, capturedBody = null, sawLoadingText = false;
  const ctx = newContext(EXTRACTED, HTML, async (path, opts) => {
    capturedPath = path;
    capturedBody = JSON.parse(opts.body);
    sawLoadingText = ctx.byId['ja-result'] && ctx.byId['ja-result'].innerHTML.includes('Hesaplanıyor');
    return fakeResult();
  });
  await vm.runInContext('jaCalculate()', ctx.context);
  check('200: calls the correct endpoint', capturedPath === '/api/engineering/joint-analysis');
  check('200: request body is valid JSON', capturedBody && typeof capturedBody === 'object');
  check('loading state shown before resolution', sawLoadingText);
  check('200: result rendered without throwing', ctx.byId['ja-result'].innerHTML.length > 0);
  checkIncludes('200: recommended torque value rendered', ctx.byId['ja-result'].innerHTML, '71.410');
  check('button re-enabled after success', ctx.byId['ja-calculate-btn'].disabled === false);
})();

// ---------------------------------------------------------------
// 6. Error handling (auth / validation / network) -- controlled
//    message, no crash, button re-enabled
// ---------------------------------------------------------------
(async function test401Handling() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('Oturum gerekli'); });
  await vm.runInContext('jaCalculate()', ctx.context);
  checkIncludes('401: error message rendered, not a raw exception', ctx.byId['ja-result'].innerHTML, 'Oturum gerekli');
  check('401: button re-enabled after error', ctx.byId['ja-calculate-btn'].disabled === false);
})();

(async function test422Handling() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('target_yield_ratio: ensure this value is less than or equal to 1'); });
  await vm.runInContext('jaCalculate()', ctx.context);
  checkIncludes('422: API detail message shown to user', ctx.byId['ja-result'].innerHTML, 'target_yield_ratio');
})();

(async function testNetworkErrorHandling() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new TypeError('Failed to fetch'); });
  await vm.runInContext('jaCalculate()', ctx.context);
  checkIncludes('network error: controlled message shown, no crash', ctx.byId['ja-result'].innerHTML, 'Failed to fetch');
  check('network error: button re-enabled', ctx.byId['ja-calculate-btn'].disabled === false);
})();

// ---------------------------------------------------------------
// 7. Double-submit guard
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
  const p1 = vm.runInContext('jaCalculate()', ctx.context);
  const p2 = vm.runInContext('jaCalculate()', ctx.context); // fired while p1 still in flight
  resolveFirst();
  await Promise.all([p1, p2]);
  check('double-submit: apiRequest called exactly once', callCount === 1);
})();

// ---------------------------------------------------------------
// 8. insufficient_data rendering (controlled, not an error path;
//    no recommended torque shown, missing inputs surfaced)
// ---------------------------------------------------------------
(function testInsufficientDataRendering() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext('jaRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeInsufficientDataResult() }));
  const html = ctx.byId['ja-result'].innerHTML;
  checkIncludes('insufficient_data: readiness label rendered', html, 'Yetersiz veri');
  checkNotIncludes('insufficient_data: no numeric recommended torque fabricated', html, 'NaN');
})();

// ---------------------------------------------------------------
// 9. Critical findings: banner shown, never a plain success card
//    for negative clamp load / yield fail
// ---------------------------------------------------------------
(function testCriticalFindingsRendering() {
  const ctx = newContext(EXTRACTED, HTML);
  const result = fakeCriticalResult();
  vm.runInContext('jaRenderResult(__result__)', Object.assign(ctx.context, { __result__: result }));
  const html = ctx.byId['ja-result'].innerHTML;
  checkIncludes('critical banner class present', html, 'ai-critical-banner');
  checkIncludes('critical banner uses the most prominent alert style', html, 'alert-danger ai-critical-banner');
  check('critical banner appears before the summary card', html.indexOf('ai-critical-banner') < html.indexOf('ai-summary-grid'));
  checkIncludes('negative residual clamp load finding text rendered', html, 'residual_clamp_load_negative');
  checkIncludes('yield fail finding text rendered', html, 'yield_utilization_fail');
  checkIncludes('safety status styled as failure', html, 'alert-danger');
  checkNotIncludes('critical result: no bare alert-ok success styling used', html.split('ai-critical-banner')[1] || html, 'alert-ok');
})();

(function testNoCriticalBannerWhenNoneFound() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext('jaRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeResult() }));
  checkNotIncludes('no critical banner rendered when critical_findings is empty', ctx.byId['ja-result'].innerHTML, 'ai-critical-banner');
  checkIncludes('"no critical finding" state shown instead', ctx.byId['ja-result'].innerHTML, 'Kritik bulgu yok');
})();

// ---------------------------------------------------------------
// 10. Distinct fields never conflated: applied torque, target
//     preload, preload-from-applied-torque and recommended torque
//     each render as their own labelled value.
// ---------------------------------------------------------------
(function testDistinctTorquePreloadFieldsRendered() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext('jaRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeResult() }));
  const html = ctx.byId['ja-result'].innerHTML;
  checkIncludes('applied torque label rendered', html, 'Uygulanan Tork');
  checkIncludes('target/calculated preload label rendered', html, 'Hedef / Hesaplanan Ön Yük');
  checkIncludes('preload-from-applied-torque label rendered', html, 'Uygulanan Torktan Ön Yük');
  checkIncludes('recommended/required torque label rendered', html, 'Önerilen / Gerekli Tork');
  checkIncludes('minimum torque window label rendered', html, 'Minimum Tork');
  checkIncludes('maximum torque window label rendered', html, 'Maksimum Tork');
  // The four numeric values must not collapse to the same string.
  const appliedTorqueValue = '45.000';
  const targetPreloadValue = '41752.420';
  checkIncludes('applied torque value (45 Nm) rendered', html, appliedTorqueValue);
  checkIncludes('target preload value rendered', html, targetPreloadValue);
})();

// ---------------------------------------------------------------
// 11. Formula trace and unsupported effects rendered
// ---------------------------------------------------------------
(function testFormulaTraceAndUnsupportedEffectsRendered() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext('jaRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeResult() }));
  const html = ctx.byId['ja-result'].innerHTML;
  checkIncludes('formula trace formula_id rendered', html, 'VDI2230_AS');
  checkIncludes('formula trace validation_status rendered', html, 'PROVISIONAL');
  checkIncludes('unsupported effect (settlement) label rendered', html, 'Yerleşme / gömülme kaybı');
  checkIncludes('unsupported effect (torque-angle) label rendered', html, 'Tork-açı sıkma simülasyonu');
})();

// ---------------------------------------------------------------
// 12. Coverage / readiness rendered
// ---------------------------------------------------------------
(function testCoverageAndReadinessRendered() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext('jaRenderResult(__result__)', Object.assign(ctx.context, { __result__: fakeResult() }));
  const html = ctx.byId['ja-result'].innerHTML;
  checkIncludes('coverage percent rendered', html, '100.0%');
  checkIncludes('readiness "full" label rendered', html, 'Tam');
})();

// ---------------------------------------------------------------
// 13. Reset behavior: clears fields and last result
// ---------------------------------------------------------------
(function testResetClearsFieldsAndResult() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['ja-diameter-mm'] = makeElement('ja-diameter-mm');
  ctx.byId['ja-diameter-mm'].value = '10';
  ctx.byId['ja-result'] = makeElement('ja-result');
  ctx.byId['ja-result'].innerHTML = '<div>stale</div>';
  vm.runInContext('__setJaLastResult(__result__)', Object.assign(ctx.context, { __result__: fakeResult() }));
  vm.runInContext('jaReset()', ctx.context);
  check('reset clears numeric field', ctx.byId['ja-diameter-mm'].value === '');
  check('reset clears result panel', ctx.byId['ja-result'].innerHTML === '');
  check('reset clears last-result memory', vm.runInContext('__getJaLastResult()', ctx.context) === null);
})();

// ---------------------------------------------------------------
// 14. Deterministic rendering for the same response
// ---------------------------------------------------------------
(function testDeterministicRendering() {
  const ctx1 = newContext(EXTRACTED, HTML);
  const ctx2 = newContext(EXTRACTED, HTML);
  const result = fakeCriticalResult();
  vm.runInContext('jaRenderResult(__result__)', Object.assign(ctx1.context, { __result__: result }));
  vm.runInContext('jaRenderResult(__result__)', Object.assign(ctx2.context, { __result__: JSON.parse(JSON.stringify(result)) }));
  check('same response renders byte-identical HTML across two fresh contexts', ctx1.byId['ja-result'].innerHTML === ctx2.byId['ja-result'].innerHTML);
})();

// ---------------------------------------------------------------
// 15. TR/EN live update without re-fetching
// ---------------------------------------------------------------
(function testLanguageSwitchReRendersWithoutRefetch() {
  let apiCallCount = 0;
  const ctx = newContext(EXTRACTED, HTML, async () => { apiCallCount++; return fakeResult(); });
  const result = fakeCriticalResult();
  vm.runInContext('__setJaLastResult(__result__)', Object.assign(ctx.context, { __result__: result }));
  vm.runInContext('jaRenderResult(__getJaLastResult())', ctx.context);
  const trHtml = ctx.byId['ja-result'].innerHTML;
  checkIncludes('TR: readiness label in Turkish', trHtml, 'Tam');
  checkIncludes('TR: safety status in Turkish', trHtml, 'Kritik başarısızlık');

  vm.runInContext("setLanguage('en')", ctx.context);
  const enHtml = ctx.byId['ja-result'].innerHTML;
  checkIncludes('EN: readiness label in English after language switch', enHtml, 'Full');
  checkIncludes('EN: safety status in English after language switch', enHtml, 'Critical failure');

  vm.runInContext("setLanguage('tr')", ctx.context);
  const trHtmlAgain = ctx.byId['ja-result'].innerHTML;
  checkIncludes('TR again: readiness label back to Turkish', trHtmlAgain, 'Tam');
  check('language switch never calls the API', apiCallCount === 0);
})();

// =================================================================
console.log((pass + fail) + ' assertions, ' + pass + ' passed, ' + fail + ' failed');
if (fail > 0) {
  console.log('Failures:\n  - ' + failures.join('\n  - '));
  process.exit(1);
}
process.exit(0);
