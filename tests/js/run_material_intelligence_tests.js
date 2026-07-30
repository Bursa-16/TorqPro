#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.8 -- Material Intelligence / Formula Validation frontend
 * regression harness.
 *
 * Zero external dependencies, same technique as
 * tests/js/run_i18n_tests.js and tests/js/run_joint_analysis_tests.js:
 * Node's built-in `vm` module runs the *actual* Material Intelligence
 * declarations extracted live from frontend/index.html (never a
 * committed copy) against a small hand-built DOM/localStorage stub.
 * Separate file on purpose -- does not modify any existing, already-
 * passing harness.
 *
 * Invoked via `node tests/js/run_material_intelligence_tests.js` from
 * the repo root, or indirectly via tests/test_faz_2_8_8_frontend.py.
 * Exit code 0 = all assertions passed; non-zero = at least one
 * failure.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const {
  extractScript,
  extractConstDecl,
  extractFunctionDecl,
  toVarDecl,
} = require('./harness_common');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND_PATH = path.join(REPO_ROOT, 'frontend', 'index.html');

// ---------------------------------------------------------------
// Extraction helpers now come from tests/js/harness_common.js (Faz
// 2.8.10 Stage 3) -- same technique as the other harnesses, verified
// byte-identical before being shared.
// ---------------------------------------------------------------

// Only what Material Intelligence's own functions actually need --
// same rationale as the other harnesses: avoid a much larger stub for
// unrelated legacy app code.
const CONST_NAMES = ['I18N', 'CURRENT_LANG', 'MI_MATERIALS', 'MI_LAST_REQUIREMENT_PAYLOAD'];
const MUTABLE_STATE_NAMES = ['MI_MATERIALS', 'MI_LAST_REQUIREMENT_PAYLOAD'];
const FUNCTION_NAMES = [
  't', 'applyStaticTranslations', 'setLanguage',
  'scEsc', 'scFmtNum',
  'loadMaterialIntelligenceWorkspace', 'miRenderMaterialsTable',
  'miBuildRequirementPayload', 'miRecommend', 'miRenderRecommendation',
  'miLoadFormulaValidation', 'miReapplyLanguage',
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
  parts.push('function __getMiMaterials() { return MI_MATERIALS; }');
  parts.push('function __setMiMaterials(v) { MI_MATERIALS = v; }');
  parts.push('function __getMiLastRequirementPayload() { return MI_LAST_REQUIREMENT_PAYLOAD; }');
  return { source: parts.join('\n\n'), rawScript: script, rawHtml: html };
}

// ---------------------------------------------------------------
// Minimal DOM / localStorage stub and assertion bookkeeping now come
// from tests/js/harness_common.js (Faz 2.8.10 Stage 3).
// ---------------------------------------------------------------
const { makeElement, makeLocalStorage, buildDom, createChecker } = require('./harness_common');
const { check, checkIncludes, checkNotIncludes, summary } = createChecker();

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
  vm.runInContext(extractedSource, context, { filename: 'mi_extracted.js' });
  return { context, byId, documentStub };
}

// Response fixtures shaped exactly like the Faz 2.8.8 API responses,
// used to exercise the render functions without a live backend.
function fakeMaterialsList() {
  return {
    materials: [
      {
        id: 'MAT-STEEL', material: 'Steel', grade: 'C1022 (carbon steel)',
        rp02_mpa: 350, rm_mpa: 500, elastic_modulus_mpa: 210000,
        validation_status: 'reference_only', approval_status: 'pending',
      },
      {
        id: 'MAT-TITANIUM', material: 'Titanium', grade: 'Ti-6Al-4V (Grade 5)',
        rp02_mpa: 830, rm_mpa: 900, elastic_modulus_mpa: 114000,
        validation_status: 'reference_only', approval_status: 'pending',
      },
    ],
  };
}

function fakeRecommendationResult(overrides) {
  const base = {
    recommendation_available: true,
    readiness_level: 'comparison_only',
    available_capabilities: ['requirement_filter', 'descriptive_comparison', 'quantitative_ranking'],
    blocked_capabilities: ['engineering_recommendation', 'production_approval'],
    blocking_reasons: ["Kayıt onay durumu \u201cbeklemede\u201d; üretim onayı için mühendislik incelemesi gereklidir."],
    engineering_warnings: [
      'Malzeme verisi referans amaçlıdır; parti/sertifika bazlı doğrulanmış veri değildir.',
      'Bu değerler bir malzeme sertifikasının yerini tutmaz; tedarikçiye, döküme ve ısıl işleme göre değişebilir.',
    ],
    required_missing_data: ['approval_status=approved', 'lot_specific_certified_test_data'],
    candidates: [
      { material_id: 'MAT-TITANIUM', material: 'Titanium', grade: 'Ti-6Al-4V (Grade 5)', rp02_mpa: 830, rm_mpa: 900, elastic_modulus_mpa: 114000, requirement_margin_ratio: 2.075 },
    ],
    sign_off_notice: 'Üretimde kullanılmadan önce mühendislik onayı zorunludur.',
  };
  return Object.assign({}, base, overrides);
}

function fakeRecommendationResultEn(overrides) {
  return Object.assign({}, fakeRecommendationResult(), {
    blocking_reasons: ["The record's approval status is \u201cpending\u201d; engineering review is required for production approval."],
    engineering_warnings: [
      'The material data is reference-only; it is not lot/certificate-verified data.',
      'These values are not a substitute for a material certificate; they vary by supplier, heat and treatment condition.',
    ],
    sign_off_notice: 'Engineering sign-off is required before production use.',
  }, overrides);
}

function fakeInsufficientResult() {
  return {
    recommendation_available: false,
    readiness_level: 'data_insufficient',
    available_capabilities: [],
    blocked_capabilities: ['requirement_filter', 'descriptive_comparison', 'quantitative_ranking', 'engineering_recommendation', 'production_approval'],
    blocking_reasons: ['Belirtilen gereksinimi karşılayan malzeme kaydı bulunamadı.'],
    engineering_warnings: ['Malzeme verisi referans amaçlıdır; parti/sertifika bazlı doğrulanmış veri değildir.'],
    required_missing_data: [],
    candidates: [],
    sign_off_notice: 'Üretimde kullanılmadan önce mühendislik onayı zorunludur.',
  };
}

function fakeFormulaValidationReport() {
  return {
    entries: [
      { formula_id: 'VDI2230_PHI', symbol: 'Phi', unit: '', source: 'docs/05...', classification: 'MANDATORY_CORRECTED_MODEL', validation_status: 'APPROVED', catalog: 'vdi2230_core.trace' },
      { formula_id: 'VDI2230_AS', symbol: 'A_s', unit: 'mm^2', source: 'docs/05...', classification: 'QUICK', validation_status: 'PROVISIONAL', catalog: 'vdi2230_core.trace' },
    ],
    total_count: 7, approved_count: 2, provisional_count: 5, other_status_count: 0,
    catalogs_scanned: ['vdi2230_core.trace'],
    notices: ['Katalogda PROVISIONAL sınıflandırılmış formül(ler) var; bunlar üretim hesaplaması için onaylı değildir.'],
  };
}

// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// 1. Materials table rendering (no calculation, display-only)
// ---------------------------------------------------------------
(function testMaterialsTableRendersAllRecords() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['mi-materials-table'] = makeElement('mi-materials-table');
  vm.runInContext('__setMiMaterials(' + JSON.stringify(fakeMaterialsList().materials) + ')', ctx.context);
  vm.runInContext('miRenderMaterialsTable()', ctx.context);
  const html = ctx.byId['mi-materials-table'].innerHTML;
  checkIncludes('materials table includes Steel id', html, 'MAT-STEEL');
  checkIncludes('materials table includes Titanium id', html, 'MAT-TITANIUM');
  checkIncludes('materials table includes validation_status value', html, 'reference_only');
})();

(function testMaterialsTableEmptyIsSafe() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['mi-materials-table'] = makeElement('mi-materials-table');
  vm.runInContext('miRenderMaterialsTable()', ctx.context);
  check('empty materials list renders nothing rather than throwing', ctx.byId['mi-materials-table'].innerHTML === '');
})();

// ---------------------------------------------------------------
// 2. Requirement payload construction: empty fields omit no filter,
//    non-empty fields produce correctly-typed values
// ---------------------------------------------------------------
(function testRequirementPayloadAllEmpty() {
  const ctx = newContext(EXTRACTED, HTML);
  ['mi-min-rp02', 'mi-min-rm', 'mi-min-e', 'mi-material-family'].forEach((id) => { ctx.byId[id] = makeElement(id); });
  const payload = vm.runInContext('miBuildRequirementPayload()', ctx.context);
  check('empty min_rp02_mpa is null, not 0 or NaN', payload.min_rp02_mpa === null);
  check('empty min_rm_mpa is null', payload.min_rm_mpa === null);
  check('empty min_elastic_modulus_mpa is null', payload.min_elastic_modulus_mpa === null);
  check('empty material_family is null, not empty string', payload.material_family === null);
})();

(function testRequirementPayloadNumericConversion() {
  const ctx = newContext(EXTRACTED, HTML);
  ['mi-min-rp02', 'mi-min-rm', 'mi-min-e', 'mi-material-family'].forEach((id) => { ctx.byId[id] = makeElement(id); });
  ctx.byId['mi-min-rp02'].value = '400';
  ctx.byId['mi-material-family'].value = '  Titanium  ';
  const payload = vm.runInContext('miBuildRequirementPayload()', ctx.context);
  check('min_rp02_mpa converted to a number', typeof payload.min_rp02_mpa === 'number' && payload.min_rp02_mpa === 400);
  check('material_family is trimmed', payload.material_family === 'Titanium');
})();

(function testRequirementPayloadIncludesCurrentLang() {
  const ctx = newContext(EXTRACTED, HTML);
  ['mi-min-rp02', 'mi-min-rm', 'mi-min-e', 'mi-material-family'].forEach((id) => { ctx.byId[id] = makeElement(id); });
  const payload = vm.runInContext('miBuildRequirementPayload()', ctx.context);
  check('payload lang defaults to tr', payload.lang === 'tr');
})();

// ---------------------------------------------------------------
// 3. Recommendation flow: loading state, success rendering, error
//    handling, no client-side ranking/guessing
// ---------------------------------------------------------------
(function testRecommendCallsCorrectEndpointAndMethod() {
  const calls = [];
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => { calls.push({ path: p, opts }); return fakeRecommendationResult(); });
  ['mi-min-rp02', 'mi-min-rm', 'mi-min-e', 'mi-material-family', 'mi-recommend-btn'].forEach((id) => { ctx.byId[id] = makeElement(id); });
  ctx.byId['mi-recommendation-result'] = makeElement('mi-recommendation-result');
  return vm.runInContext('miRecommend()', ctx.context).then(() => {
    check('exactly one API call made', calls.length === 1);
    check('called the material-recommendation endpoint', calls[0].path === '/api/engineering/material-recommendation');
    check('used POST', calls[0].opts.method === 'POST');
    check('button re-enabled after completion', ctx.byId['mi-recommend-btn'].disabled === false);
  });
})();

(function testRecommendRendersReadinessAndSignOff() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeRecommendationResult());
  ctx.byId['mi-recommendation-result'] = makeElement('mi-recommendation-result');
  vm.runInContext('miRenderRecommendation(' + JSON.stringify(fakeRecommendationResult()) + ')', ctx.context);
  const html = ctx.byId['mi-recommendation-result'].innerHTML;
  checkIncludes('readiness level rendered', html, 'comparison_only');
  checkIncludes('sign-off notice always rendered', html, 'Üretimde kullanılmadan önce mühendislik onayı zorunludur.');
  checkIncludes('blocking reason rendered (explains, does not guess)', html, 'beklemede');
})();

(function testRecommendNeverRendersEngineeringOrProductionReady() {
  // Structural guard mirroring the backend invariant: the render
  // function itself does not special-case or upgrade a level -- it
  // only displays what the backend sent, and the fixture proves the
  // UI has no code path that fabricates a higher readiness claim.
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['mi-recommendation-result'] = makeElement('mi-recommendation-result');
  vm.runInContext('miRenderRecommendation(' + JSON.stringify(fakeInsufficientResult()) + ')', ctx.context);
  const html = ctx.byId['mi-recommendation-result'].innerHTML;
  checkNotIncludes('never claims engineering_recommendation_ready', html, 'engineering_recommendation_ready');
  checkNotIncludes('never claims production_recommendation_ready', html, 'production_recommendation_ready');
  checkIncludes('states data_insufficient plainly', html, 'data_insufficient');
})();

(function testRecommendNoCandidatesShowsExplanationNotBlank() {
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['mi-recommendation-result'] = makeElement('mi-recommendation-result');
  vm.runInContext('miRenderRecommendation(' + JSON.stringify(fakeInsufficientResult()) + ')', ctx.context);
  const html = ctx.byId['mi-recommendation-result'].innerHTML;
  check('no-candidates case is not a blank panel', html.length > 0);
  checkIncludes('explains why no candidates (TR)', html, 'bulunamadı');
})();

(function testRecommendApiErrorHandledGracefully() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('network down'); });
  ['mi-min-rp02', 'mi-min-rm', 'mi-min-e', 'mi-material-family', 'mi-recommend-btn'].forEach((id) => { ctx.byId[id] = makeElement(id); });
  ctx.byId['mi-recommendation-result'] = makeElement('mi-recommendation-result');
  return vm.runInContext('miRecommend()', ctx.context).then(() => {
    checkIncludes('error message surfaced to user', ctx.byId['mi-recommendation-result'].innerHTML, 'network down');
    check('button re-enabled after error', ctx.byId['mi-recommend-btn'].disabled === false);
  });
})();

(function testRecommendationRenderingComputesNoNewNumber() {
  // The frontend must never compute its own margin/ranking value --
  // every numeric field displayed must come verbatim from the fixture
  // response, not be derived client-side.
  const fixture = fakeRecommendationResult();
  const ctx = newContext(EXTRACTED, HTML);
  ctx.byId['mi-recommendation-result'] = makeElement('mi-recommendation-result');
  vm.runInContext('miRenderRecommendation(' + JSON.stringify(fixture) + ')', ctx.context);
  const html = ctx.byId['mi-recommendation-result'].innerHTML;
  checkIncludes('server-supplied margin ratio rendered verbatim', html, String(fixture.candidates[0].requirement_margin_ratio));
})();

// ---------------------------------------------------------------
// 4. Formula validation panel: read-only display
// ---------------------------------------------------------------
(function testFormulaValidationCallsCorrectEndpoint() {
  const calls = [];
  const ctx = newContext(EXTRACTED, HTML, async (p) => { calls.push(p); return fakeFormulaValidationReport(); });
  ctx.byId['mi-formula-validation-result'] = makeElement('mi-formula-validation-result');
  return vm.runInContext('miLoadFormulaValidation()', ctx.context).then(() => {
    check('exactly one API call made', calls.length === 1);
    check('called the formula-validation endpoint with lang', calls[0].indexOf('/api/engineering/formula-validation?lang=') === 0);
  });
})();

(function testFormulaValidationRendersApprovedCount() {
  const calls = [];
  const ctx = newContext(EXTRACTED, HTML, async () => fakeFormulaValidationReport());
  ctx.byId['mi-formula-validation-result'] = makeElement('mi-formula-validation-result');
  return vm.runInContext('miLoadFormulaValidation()', ctx.context).then(() => {
    const html = ctx.byId['mi-formula-validation-result'].innerHTML;
    checkIncludes('approved/total counts rendered', html, '2/7');
    checkIncludes('PROVISIONAL entry rendered', html, 'PROVISIONAL');
    checkIncludes('APPROVED entry rendered', html, 'APPROVED');
  });
})();

(function testFormulaValidationApiErrorHandledGracefully() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('formula service down'); });
  ctx.byId['mi-formula-validation-result'] = makeElement('mi-formula-validation-result');
  return vm.runInContext('miLoadFormulaValidation()', ctx.context).then(() => {
    checkIncludes('formula validation error surfaced', ctx.byId['mi-formula-validation-result'].innerHTML, 'formula service down');
  });
})();

// ---------------------------------------------------------------
// 5. TR/EN live re-render without refetch of static labels
// ---------------------------------------------------------------
(function testLanguageSwitchRerendersMaterialsTableWithoutRefetch() {
  let apiCallCount = 0;
  const ctx = newContext(EXTRACTED, HTML, async () => { apiCallCount++; return fakeMaterialsList(); }, null);
  ctx.byId['mi-materials-table'] = makeElement('mi-materials-table');
  vm.runInContext('__setMiMaterials(' + JSON.stringify(fakeMaterialsList().materials) + ')', ctx.context);
  vm.runInContext('miRenderMaterialsTable()', ctx.context);
  vm.runInContext("setLanguage('en')", ctx.context);
  check('materials table re-render does not call the API', apiCallCount === 0);
  check('language switch keeps material data intact', ctx.byId['mi-materials-table'].innerHTML.indexOf('MAT-STEEL') !== -1);
})();

(function testLanguageSwitchRefetchesFormulaValidationOnActivePage() {
  const calls = [];
  const ctx = newContext(EXTRACTED, HTML, async (p) => { calls.push(p); return fakeFormulaValidationReport(); }, 'materialintelligence');
  ctx.byId['mi-formula-validation-result'] = makeElement('mi-formula-validation-result');
  vm.runInContext("setLanguage('en')", ctx.context);
  check('setLanguage triggers a re-fetch of language-dependent formula validation notices', calls.length >= 1);
})();

(function testLanguageSwitchDoesNotRefetchWhenPageNotActive() {
  const calls = [];
  const ctx = newContext(EXTRACTED, HTML, async (p) => { calls.push(p); return fakeFormulaValidationReport(); }, null);
  vm.runInContext("setLanguage('en')", ctx.context);
  check('no refetch when Material Intelligence page is not active', calls.length === 0);
})();

// ---------------------------------------------------------------
// 6. Sidebar / page presence and static translation coverage
// ---------------------------------------------------------------
(function testSidebarAndPageMarkupPresent() {
  check("sidebar item present", HTML.indexOf("showPage('materialintelligence')") !== -1);
  check('page container present', HTML.indexOf('id="page-materialintelligence"') !== -1);
})();

(function testStaticTranslationApplied() {
  const ctx = newContext(EXTRACTED, HTML);
  vm.runInContext("applyStaticTranslations()", ctx.context);
  const dataI18nEls = ctx.documentStub.querySelectorAll('[data-i18n]');
  const miEls = dataI18nEls.filter((el) => el.getAttribute('data-i18n').indexOf('mi.') === 0);
  check('at least one mi.* data-i18n element found', miEls.length > 0);
  check('every mi.* element received non-empty translated text', miEls.every((el) => el.textContent && el.textContent.length > 0));
})();

// =================================================================
{
  const { pass, fail, failures } = summary();
  console.log((pass + fail) + ' assertions, ' + pass + ' passed, ' + fail + ' failed');
  if (fail > 0) {
    console.log('Failures:\n  - ' + failures.join('\n  - '));
    process.exit(1);
  }
  process.exit(0);
}
