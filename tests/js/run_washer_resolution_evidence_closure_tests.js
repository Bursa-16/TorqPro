#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.20 Stage 5 -- Washer Resolution Evidence & Controlled
 * Closure frontend regression harness.
 *
 * Same live-extraction technique as
 * tests/js/run_washer_resolution_decision_form_tests.js: Node's
 * built-in `vm` module runs the *actual* evidence/closure
 * declarations extracted live from frontend/index.html against a
 * small hand-built DOM stub.
 *
 * Scope: the Stage 5 evidence list/form, closure readiness view, and
 * close form/result only. Never extracts or exercises decision-form-
 * specific (Stage 3) or queue/history-specific rendering beyond what
 * wrrLoadResolutionDetail itself needs to drive this workspace's
 * show/hide logic.
 *
 * Invoked via `node tests/js/run_washer_resolution_evidence_closure_tests.js`
 * from the repo root, or indirectly via
 * tests/test_faz_2_8_20_stage5_washer_resolution_evidence_closure_frontend.py.
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
  makeElement,
  makeLocalStorage,
  buildDom: buildDomShared,
  createChecker,
} = require('./harness_common');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND_PATH = path.join(REPO_ROOT, 'frontend', 'index.html');

const { check, checkIncludes, checkNotIncludes, recordFailure, summary } = createChecker();

const CONST_NAMES = [
  'I18N', 'CURRENT_LANG', 'WRR_STATUS_LABEL_KEYS',
  'WRR_DETAIL_REQUIRED_FIELDS', 'WRR_LAST_DETAIL',
  'WRR_DECIDE_IDEMPOTENCY_KEY', 'WRR_DECIDE_KEY_RESOLUTION_ID', 'WRR_DECIDE_IN_FLIGHT',
  'WRR_HISTORY_REQUIRED_FIELDS',
  'WRR_EVIDENCE_TYPE_LABEL_KEYS', 'WRR_VERIFICATION_STATUS_LABEL_KEYS',
  'WRR_EVIDENCE_IN_FLIGHT', 'WRR_CLOSE_IN_FLIGHT',
  'WRR_LAST_READINESS', 'WRR_LAST_CLOSURE',
];
const MUTABLE_STATE_NAMES = [
  'WRR_LAST_DETAIL',
  'WRR_DECIDE_IDEMPOTENCY_KEY', 'WRR_DECIDE_KEY_RESOLUTION_ID', 'WRR_DECIDE_IN_FLIGHT',
  'WRR_EVIDENCE_IN_FLIGHT', 'WRR_CLOSE_IN_FLIGHT',
  'WRR_LAST_READINESS', 'WRR_LAST_CLOSURE',
];
const FUNCTION_NAMES = [
  't', 'scEsc', 'wrrStatusLabel', 'wrrBoolLabel', 'wrrDetailField',
  'wrrDetailIsWellFormed', 'wrrRenderDetail',
  'wrrGenerateIdempotencyKey', 'wrrPopulateStatusOptions', 'wrrResetDecisionForm',
  'wrrShowDecisionFormForDetail', 'wrrHideDecisionForm',
  'wrrHistoryRecordIsWellFormed', 'wrrHistoryResponseIsWellFormed',
  'wrrLoadResolutionHistory', 'wrrHideHistory', 'wrrRenderHistoryTable',
  'wrrLoadResolutionDetail',
  'wrrEvidenceTypeLabel', 'wrrVerificationStatusLabel',
  'wrrResetEvidenceClosureState',
  'wrrLoadEvidence', 'wrrRenderEvidenceTable', 'wrrShowEvidenceFormForDetail',
  'wrrResetEvidenceForm', 'wrrValidateEvidenceForm', 'wrrSubmitEvidence',
  'wrrLoadClosureReadiness', 'wrrRenderClosureReadiness', 'wrrShowCloseFormForReadiness',
  'wrrLoadClosure', 'wrrRenderClosure', 'wrrValidateCloseForm', 'wrrSubmitClosure',
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
  parts.push('function __getWrrLastReadiness() { return WRR_LAST_READINESS; }');
  parts.push('function __getWrrLastClosure() { return WRR_LAST_CLOSURE; }');
  parts.push('function __getEvidenceInFlight() { return WRR_EVIDENCE_IN_FLIGHT; }');
  parts.push('function __getCloseInFlight() { return WRR_CLOSE_IN_FLIGHT; }');
  return { source: parts.join('\n\n'), rawHtml: html };
}

function buildDom(rawHtml, byId) {
  return buildDomShared(rawHtml, byId, { includePlaceholders: false });
}

function newContext(extractedSource, rawHtml, apiRequestImpl) {
  const byId = {};
  const documentStub = buildDom(rawHtml, byId);
  const sandbox = {
    document: documentStub,
    localStorage: makeLocalStorage({}),
    sessionStorage: makeLocalStorage({}),
    console: console,
    encodeURIComponent: encodeURIComponent,
    parseInt: parseInt,
    Date: Date,
    Math: Math,
    Array: Array,
    apiRequest: apiRequestImpl || (() => { throw new Error('apiRequest should not be called by this test'); }),
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'wrr_evidence_closure_extracted.js' });
  return { context, byId, documentStub };
}

const EVIDENCE_ELEMENT_IDS = [
  'wrr-evidence-card', 'wrr-evidence-status', 'wrr-evidence-content', 'wrr-evidence-table',
  'wrr-evidence-form-card', 'wrr-evidence-type', 'wrr-evidence-title', 'wrr-evidence-description',
  'wrr-evidence-source-reference', 'wrr-evidence-source-locator', 'wrr-evidence-source-url',
  'wrr-evidence-source-standard', 'wrr-evidence-created-by', 'wrr-evidence-submit-btn',
  'wrr-evidence-validation-error', 'wrr-evidence-status-msg',
];
const CLOSURE_ELEMENT_IDS = [
  'wrr-closure-readiness-card', 'wrr-closure-readiness-status', 'wrr-closure-readiness-content',
  'wrr-close-form-card', 'wrr-close-rationale', 'wrr-close-closed-by', 'wrr-close-submit-btn',
  'wrr-close-validation-error', 'wrr-close-status-msg',
  'wrr-closure-result-card', 'wrr-closure-result-content',
];
const DETAIL_ELEMENT_IDS = ['wrr-detail-card', 'wrr-detail-status', 'wrr-detail-content'];
const HISTORY_ELEMENT_IDS = ['wrr-history-card', 'wrr-history-status', 'wrr-history-content'];
const DECISION_FORM_ELEMENT_IDS = [
  'wrr-decision-form-card', 'wrr-decide-blocked-notice', 'wrr-decide-terminal-notice',
  'wrr-decide-new-status', 'wrr-decide-resolution-note', 'wrr-decide-evidence-reference',
  'wrr-decide-resolved-by', 'wrr-decide-confidence-level',
  'wrr-decide-validation-error', 'wrr-decide-status', 'wrr-decide-submit-btn',
];

function primeAllElements(byId) {
  EVIDENCE_ELEMENT_IDS.concat(CLOSURE_ELEMENT_IDS, DETAIL_ELEMENT_IDS, HISTORY_ELEMENT_IDS, DECISION_FORM_ELEMENT_IDS)
    .forEach((id) => { byId[id] = makeElement(id); });
}

function fakeDetail(overrides) {
  const base = {
    resolution_id: 'RES-WASH-DIN127B-M10',
    washer_record_id: 'WASH-DIN127B-M10',
    issue_type: 'source_missing',
    reason_code: 'high_internal_confidence_lacks_external_evidence',
    source_status: 'open',
    effective_status: 'open',
    decision_count: 0,
    is_blocked: false,
    is_terminal: false,
    resolution_note: '',
    evidence_reference: '',
    resolved_standard: null,
    resolved_by: '',
    resolved_at: '',
    confidence_level: null,
    requires_authoritative_source: false,
  };
  return Object.assign({}, base, overrides);
}

function fakeEvidenceRecord(overrides) {
  const base = {
    evidence_id: 'WRE-11111111-1111-1111-1111-111111111111',
    resolution_id: 'RES-WASH-DIN127B-M10',
    evidence_type: 'manufacturer_document',
    title: 'Test evidence',
    description: 'Test evidence description.',
    source_reference: 'Test Catalog 2026, p. 1',
    source_locator: null,
    source_url: null,
    source_standard: null,
    verification_status: 'unverified',
    verified_by: null,
    verified_at: null,
    created_by: 'ilhan',
    created_at: '2026-01-15T10:00:00.000000Z',
    integrity_checksum: 'a'.repeat(64),
  };
  return Object.assign({}, base, overrides);
}

function fakeReadiness(overrides) {
  const base = {
    resolution_id: 'RES-WASH-DIN127B-M10',
    effective_status: 'open',
    is_ready: false,
    decision_id: null,
    verified_evidence_ids: [],
    unverified_evidence_ids: [],
    rejected_evidence_ids: [],
    corrupted_evidence_ids: [],
    blocking_reasons: ['no verified evidence exists for this resolution'],
  };
  return Object.assign({}, base, overrides);
}

function fakeClosure(overrides) {
  const base = {
    closure_id: 'CLR-22222222-2222-2222-2222-222222222222',
    resolution_id: 'RES-WASH-DIN127B-M10',
    closure_status: 'closed',
    closure_rationale: 'All evidence verified; closing.',
    closed_by: 'ilhan',
    closed_at: '2026-01-20T10:00:00.000000Z',
    evidence_ids: ['WRE-11111111-1111-1111-1111-111111111111'],
    decision_id: 'DEC-33333333-3333-3333-3333-333333333333',
    integrity_checksum: 'b'.repeat(64),
  };
  return Object.assign({}, base, overrides);
}

function fillValidEvidenceForm(ctx, overrides) {
  const values = Object.assign({
    'wrr-evidence-type': 'manufacturer_document',
    'wrr-evidence-title': 'Test evidence',
    'wrr-evidence-description': 'Test evidence description.',
    'wrr-evidence-source-reference': 'Test Catalog 2026, p. 1',
    'wrr-evidence-source-locator': '',
    'wrr-evidence-source-url': '',
    'wrr-evidence-source-standard': '',
    'wrr-evidence-created-by': 'ilhan',
  }, overrides || {});
  Object.entries(values).forEach(([id, v]) => { ctx.byId[id].value = v; });
}

function fillValidCloseForm(ctx, overrides) {
  const values = Object.assign({
    'wrr-close-rationale': 'Closing for test.',
    'wrr-close-closed-by': 'ilhan',
  }, overrides || {});
  Object.entries(values).forEach(([id, v]) => { ctx.byId[id].value = v; });
}

async function loadDetail(ctx, detail, extraRouter) {
  await vm.runInContext(`wrrLoadResolutionDetail(${JSON.stringify(detail.resolution_id)})`, ctx.context);
}

function makeRouter({ detail, evidenceRecords, readiness, closure, onEvidencePost, onClosePost } = {}) {
  return async (p, opts) => {
    if (opts && opts.method === 'POST' && p.indexOf('/evidence') !== -1) {
      if (onEvidencePost) onEvidencePost(p, opts);
      return { evidence: fakeEvidenceRecord() };
    }
    if (opts && opts.method === 'POST' && p.indexOf('/close') !== -1) {
      if (onClosePost) onClosePost(p, opts);
      return { closure: closure || fakeClosure() };
    }
    if (p.indexOf('/closure-readiness') !== -1) return readiness || fakeReadiness();
    if (p.indexOf('/closure') !== -1) return { closure: closure !== undefined ? closure : null };
    if (p.indexOf('/evidence') !== -1) return { records: evidenceRecords || [] };
    if (p.indexOf('/decisions') !== -1) return { decisions: [] };
    return detail || fakeDetail();
  };
}

// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// 1. New DOM ids present in the real page.
// ---------------------------------------------------------------
async function testNewDomIdsPresentInRealHtml() {
  EVIDENCE_ELEMENT_IDS.concat(CLOSURE_ELEMENT_IDS).forEach((id) => {
    checkIncludes('real HTML contains id="' + id + '"', HTML, 'id="' + id + '"');
  });
}

// ---------------------------------------------------------------
// 2. evidence_type has exactly 7 options.
// ---------------------------------------------------------------
async function testEvidenceTypeHasSevenOptions() {
  const m = /<select class="form-select" id="wrr-evidence-type">([\s\S]*?)<\/select>/.exec(HTML);
  check('evidence-type select found', !!m);
  const optionValues = (m ? m[1] : '').match(/<option value="[^"]*"/g) || [];
  // -1 for the "-- select --" placeholder option.
  check('evidence_type has exactly 7 real options', optionValues.length - 1 === 7);
  const expected = [
    'authoritative_standard', 'manufacturer_document', 'approved_engineering_source',
    'internal_measurement', 'comparison_analysis', 'legacy_provenance_reference', 'other',
  ];
  expected.forEach((v) => checkIncludes('evidence_type includes ' + v, HTML, 'value="' + v + '"'));
}

// ---------------------------------------------------------------
// 3. Backend-generated fields absent from evidence form markup.
// ---------------------------------------------------------------
async function testBackendGeneratedFieldsAbsentFromEvidenceForm() {
  const m = /<div class="card" id="wrr-evidence-form-card"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>/.exec(HTML);
  const formHtml = m ? m[0] : '';
  check('evidence form markup found', formHtml.length > 0);
  ['id="wrr-evidence-id"', 'id="wrr-evidence-created-at"', 'id="wrr-evidence-checksum"',
    'id="wrr-evidence-verification-status"', 'idempotency_key'].forEach((needle) => {
    checkNotIncludes('evidence form markup omits ' + needle, formHtml, needle);
  });
}

// ---------------------------------------------------------------
// 4. Backend-generated fields absent from close form markup.
// ---------------------------------------------------------------
async function testBackendGeneratedFieldsAbsentFromCloseForm() {
  const m = /<div class="card" id="wrr-close-form-card"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>/.exec(HTML);
  const formHtml = m ? m[0] : '';
  check('close form markup found', formHtml.length > 0);
  ['id="wrr-close-id"', 'id="wrr-closed-at"', 'id="wrr-close-checksum"',
    'evidence_ids', 'decision_id', 'idempotency_key'].forEach((needle) => {
    checkNotIncludes('close form markup omits ' + needle, formHtml, needle);
  });
}

// ---------------------------------------------------------------
// 5. No reopen button/UI anywhere in the new section.
// ---------------------------------------------------------------
async function testNoReopenUi() {
  const startIdx = HTML.indexOf('id="wrr-evidence-card"');
  const endIdx = HTML.indexOf('id="page-governance"');
  const section = HTML.slice(startIdx, endIdx);
  check('new section located', startIdx !== -1 && endIdx !== -1 && endIdx > startIdx);
  checkNotIncludes('no reopen onclick handler in new section', section, 'onclick="wrrReopen');
  checkNotIncludes('no reopen button id in new section', section, 'id="wrr-reopen');
}

// ---------------------------------------------------------------
// 6. wrrLoadResolutionDetail calls the three new loaders.
// ---------------------------------------------------------------
async function testDetailLoadCallsThreeNewLoaders() {
  let evidenceCalled = false;
  let readinessCalled = false;
  let closureCalled = false;
  const detail = fakeDetail();
  const router = async (p) => {
    if (p.indexOf('/closure-readiness') !== -1) { readinessCalled = true; return fakeReadiness(); }
    if (p.indexOf('/closure') !== -1) { closureCalled = true; return { closure: null }; }
    if (p.indexOf('/evidence') !== -1) { evidenceCalled = true; return { records: [] }; }
    if (p.indexOf('/decisions') !== -1) return { decisions: [] };
    return detail;
  };
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('wrrLoadEvidence called', evidenceCalled);
  check('wrrLoadClosureReadiness called', readinessCalled);
  check('wrrLoadClosure called', closureCalled);
}

// ---------------------------------------------------------------
// 7. Evidence GET uses correct endpoint.
// ---------------------------------------------------------------
async function testEvidenceGetUsesCorrectEndpoint() {
  let evidenceGetPath = null;
  const detail = fakeDetail();
  const router = async (p, opts) => {
    if ((!opts || !opts.method) && p.indexOf('/evidence') !== -1) evidenceGetPath = p;
    if (p.indexOf('/closure-readiness') !== -1) return fakeReadiness();
    if (p.indexOf('/closure') !== -1) return { closure: null };
    if (p.indexOf('/evidence') !== -1) return { records: [] };
    if (p.indexOf('/decisions') !== -1) return { decisions: [] };
    return detail;
  };
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check(
    'evidence GET called correct URL',
    evidenceGetPath === '/api/library/washers/resolutions/RES-WASH-DIN127B-M10/evidence'
  );
}

// ---------------------------------------------------------------
// 8. Evidence POST uses correct endpoint and payload.
// ---------------------------------------------------------------
async function testEvidencePostUsesCorrectEndpointAndPayload() {
  let postedPath = null;
  let postedOptions = null;
  const detail = fakeDetail();
  const router = makeRouter({
    detail,
    onEvidencePost: (p, opts) => { postedPath = p; postedOptions = opts; },
  });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidEvidenceForm(ctx);
  await vm.runInContext('wrrSubmitEvidence()', ctx.context);
  check(
    'evidence POST called correct URL',
    postedPath === '/api/library/washers/resolutions/RES-WASH-DIN127B-M10/evidence'
  );
  check('evidence POST used POST method', postedOptions && postedOptions.method === 'POST');
  const body = JSON.parse(postedOptions.body);
  check('body.evidence_type correct', body.evidence_type === 'manufacturer_document');
  check('body.title correct', body.title === 'Test evidence');
  check('body.description correct', body.description === 'Test evidence description.');
  check('body.source_reference correct', body.source_reference === 'Test Catalog 2026, p. 1');
  check('body.created_by correct', body.created_by === 'ilhan');
}

// ---------------------------------------------------------------
// 9. Optional blank fields omitted from the payload.
// ---------------------------------------------------------------
async function testOptionalBlankFieldsOmitted() {
  let postedOptions = null;
  const detail = fakeDetail();
  const router = makeRouter({ detail, onEvidencePost: (p, opts) => { postedOptions = opts; } });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidEvidenceForm(ctx);
  await vm.runInContext('wrrSubmitEvidence()', ctx.context);
  const body = JSON.parse(postedOptions.body);
  check('source_locator omitted when blank', !('source_locator' in body));
  check('source_url omitted when blank', !('source_url' in body));
  check('source_standard omitted when blank', !('source_standard' in body));
}

// ---------------------------------------------------------------
// 10. authoritative_standard without source_standard fails client validation.
// ---------------------------------------------------------------
async function testAuthoritativeStandardRequiresSourceStandard() {
  let posted = false;
  const detail = fakeDetail();
  const router = makeRouter({ detail, onEvidencePost: () => { posted = true; } });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidEvidenceForm(ctx, { 'wrr-evidence-type': 'authoritative_standard', 'wrr-evidence-source-standard': '' });
  await vm.runInContext('wrrSubmitEvidence()', ctx.context);
  check('submit blocked without source_standard', !posted);
  check(
    'validation error shown',
    ctx.byId['wrr-evidence-validation-error'].style.display === ''
    && ctx.byId['wrr-evidence-validation-error']._text.length > 0
  );
}

// ---------------------------------------------------------------
// 11. Evidence submit double-click protection.
// ---------------------------------------------------------------
async function testEvidenceDoubleSubmitProtected() {
  let postCount = 0;
  const detail = fakeDetail();
  const router = makeRouter({ detail, onEvidencePost: () => { postCount++; } });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidEvidenceForm(ctx);
  await Promise.all([
    vm.runInContext('wrrSubmitEvidence()', ctx.context),
    vm.runInContext('wrrSubmitEvidence()', ctx.context),
  ]);
  check('only one evidence POST sent despite double-click', postCount === 1);
}

// ---------------------------------------------------------------
// 12. Success refreshes evidence/readiness/closure.
// ---------------------------------------------------------------
async function testSuccessRefreshesEvidenceReadinessClosure() {
  let evidenceGetCount = 0;
  let readinessGetCount = 0;
  let closureGetCount = 0;
  const detail = fakeDetail();
  const router = async (p, opts) => {
    if (opts && opts.method === 'POST' && p.indexOf('/evidence') !== -1) return { evidence: fakeEvidenceRecord() };
    if (p.indexOf('/closure-readiness') !== -1) { readinessGetCount++; return fakeReadiness(); }
    if (p.indexOf('/closure') !== -1) { closureGetCount++; return { closure: null }; }
    if (p.indexOf('/evidence') !== -1) { evidenceGetCount++; return { records: [] }; }
    if (p.indexOf('/decisions') !== -1) return { decisions: [] };
    return detail;
  };
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  const evidenceBefore = evidenceGetCount, readinessBefore = readinessGetCount, closureBefore = closureGetCount;
  fillValidEvidenceForm(ctx);
  await vm.runInContext('wrrSubmitEvidence()', ctx.context);
  check('evidence reloaded after submit', evidenceGetCount > evidenceBefore);
  check('readiness reloaded after submit', readinessGetCount > readinessBefore);
  check('closure reloaded after submit', closureGetCount > closureBefore);
}

// ---------------------------------------------------------------
// 13. Evidence list empty state.
// ---------------------------------------------------------------
async function testEvidenceListEmptyState() {
  const detail = fakeDetail();
  const router = makeRouter({ detail, evidenceRecords: [] });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  checkIncludes(
    'empty evidence table shows empty state text',
    ctx.byId['wrr-evidence-table']._html,
    'fc-muted'
  );
}

// ---------------------------------------------------------------
// 14. verification_status is only displayed, never a verify/reject button.
// ---------------------------------------------------------------
async function testVerificationStatusOnlyDisplayed() {
  const detail = fakeDetail();
  const record = fakeEvidenceRecord({ verification_status: 'verified' });
  const router = makeRouter({ detail, evidenceRecords: [record] });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  const tableHtml = ctx.byId['wrr-evidence-table']._html;
  checkNotIncludes('no verify button in evidence table', tableHtml.toLowerCase(), 'verify(');
  checkNotIncludes('no reject button in evidence table', tableHtml.toLowerCase(), 'reject(');
  checkNotIncludes('no onclick in evidence table', tableHtml, 'onclick');
}

// ---------------------------------------------------------------
// 15. Readiness endpoint called correctly.
// ---------------------------------------------------------------
async function testReadinessEndpointCalledCorrectly() {
  let readinessPath = null;
  const detail = fakeDetail();
  const router = async (p) => {
    if (p.indexOf('/closure-readiness') !== -1) { readinessPath = p; return fakeReadiness(); }
    if (p.indexOf('/closure') !== -1) return { closure: null };
    if (p.indexOf('/evidence') !== -1) return { records: [] };
    if (p.indexOf('/decisions') !== -1) return { decisions: [] };
    return detail;
  };
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check(
    'readiness GET called correct URL',
    readinessPath === '/api/library/washers/resolutions/RES-WASH-DIN127B-M10/closure-readiness'
  );
}

// ---------------------------------------------------------------
// 16. effective_status shown in readiness content.
// ---------------------------------------------------------------
async function testEffectiveStatusShownInReadiness() {
  const detail = fakeDetail();
  const readiness = fakeReadiness({ effective_status: 'resolved' });
  const router = makeRouter({ detail, readiness });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  // Language-agnostic: ask the extracted wrrStatusLabel() itself for
  // the expected label (CURRENT_LANG defaults to 'tr' in this
  // harness, same as every other run_washer_resolution_* harness),
  // rather than hardcoding the English string.
  const expectedLabel = await vm.runInContext("wrrStatusLabel('resolved')", ctx.context);
  checkIncludes(
    'effective_status rendered',
    ctx.byId['wrr-closure-readiness-content']._html,
    expectedLabel
  );
}

// ---------------------------------------------------------------
// 17. blocking_reasons rendered verbatim.
// ---------------------------------------------------------------
async function testBlockingReasonsRendered() {
  const detail = fakeDetail();
  const readiness = fakeReadiness({ blocking_reasons: ['a specific backend reason here'] });
  const router = makeRouter({ detail, readiness });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  checkIncludes(
    'blocking reason text rendered verbatim',
    ctx.byId['wrr-closure-readiness-content']._html,
    'a specific backend reason here'
  );
}

// ---------------------------------------------------------------
// 18. Close button disabled when readiness.is_ready is false.
// ---------------------------------------------------------------
async function testCloseButtonDisabledWhenNotReady() {
  const detail = fakeDetail();
  const readiness = fakeReadiness({ is_ready: false });
  const router = makeRouter({ detail, readiness });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('close button disabled when not ready', ctx.byId['wrr-close-submit-btn'].disabled === true);
}

// ---------------------------------------------------------------
// 19. Close button enabled when readiness.is_ready is true and no closure.
// ---------------------------------------------------------------
async function testCloseButtonEnabledWhenReady() {
  const detail = fakeDetail();
  const readiness = fakeReadiness({ is_ready: true, decision_id: 'DEC-abc', verified_evidence_ids: ['WRE-x'] });
  const router = makeRouter({ detail, readiness, closure: null });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('close button enabled when ready and unclosed', ctx.byId['wrr-close-submit-btn'].disabled === false);
}

// ---------------------------------------------------------------
// 20. Close form hidden when closure already exists.
// ---------------------------------------------------------------
async function testCloseFormHiddenWhenClosureExists() {
  const detail = fakeDetail();
  const readiness = fakeReadiness({ is_ready: true });
  const closure = fakeClosure();
  const router = makeRouter({ detail, readiness, closure });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('close form hidden once closure exists', ctx.byId['wrr-close-form-card'].style.display === 'none');
}

// ---------------------------------------------------------------
// 21. GET closure null handled correctly (not an error).
// ---------------------------------------------------------------
async function testGetClosureNullHandledCorrectly() {
  const detail = fakeDetail();
  const router = makeRouter({ detail, closure: null });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('closure result card hidden when closure is null', ctx.byId['wrr-closure-result-card'].style.display === 'none');
}

// ---------------------------------------------------------------
// 22. Closure result fields rendered.
// ---------------------------------------------------------------
async function testClosureResultFieldsRendered() {
  const detail = fakeDetail();
  const closure = fakeClosure();
  const router = makeRouter({ detail, closure });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  const html = ctx.byId['wrr-closure-result-content']._html;
  check('closure result card shown', ctx.byId['wrr-closure-result-card'].style.display === '');
  checkIncludes('closure_id rendered', html, closure.closure_id);
  checkIncludes('closure_status rendered', html, closure.closure_status);
  checkIncludes('closure_rationale rendered', html, closure.closure_rationale);
  checkIncludes('closed_by rendered', html, closure.closed_by);
  checkIncludes('closed_at rendered', html, closure.closed_at);
  checkIncludes('decision_id rendered', html, closure.decision_id);
}

// ---------------------------------------------------------------
// 23. Close POST sends correct payload.
// ---------------------------------------------------------------
async function testClosePostSendsCorrectPayload() {
  let postedPath = null;
  let postedOptions = null;
  const detail = fakeDetail();
  const readiness = fakeReadiness({ is_ready: true });
  const router = makeRouter({
    detail, readiness, closure: null,
    onClosePost: (p, opts) => { postedPath = p; postedOptions = opts; },
  });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidCloseForm(ctx);
  await vm.runInContext('wrrSubmitClosure()', ctx.context);
  check(
    'close POST called correct URL',
    postedPath === '/api/library/washers/resolutions/RES-WASH-DIN127B-M10/close'
  );
  check('close POST used POST method', postedOptions && postedOptions.method === 'POST');
  const body = JSON.parse(postedOptions.body);
  check('body.closure_rationale correct', body.closure_rationale === 'Closing for test.');
  check('body.closed_by correct', body.closed_by === 'ilhan');
  check('body has no extra fields', Object.keys(body).length === 2);
}

// ---------------------------------------------------------------
// 24. Close submit double-click protection.
// ---------------------------------------------------------------
async function testCloseDoubleSubmitProtected() {
  let postCount = 0;
  const detail = fakeDetail();
  const readiness = fakeReadiness({ is_ready: true });
  const router = makeRouter({ detail, readiness, closure: null, onClosePost: () => { postCount++; } });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidCloseForm(ctx);
  await Promise.all([
    vm.runInContext('wrrSubmitClosure()', ctx.context),
    vm.runInContext('wrrSubmitClosure()', ctx.context),
  ]);
  check('only one close POST sent despite double-click', postCount === 1);
}

// ---------------------------------------------------------------
// 25. No client-side reopen function exists anywhere in extracted source.
// ---------------------------------------------------------------
async function testNoReopenFunctionExists() {
  // Word-boundary, identifier/call-shaped match only -- not a raw
  // substring search. The extracted source legitimately contains the
  // English and Turkish confirmation sentences ("there is no reopen
  // action" / "yeniden açma işlemi yoktur") inside I18N.wrr.closure.
  // result_subtitle, which a plain substring check would (and did)
  // incorrectly flag. This checks for an actual reopen-named
  // function/identifier being declared or invoked instead.
  const reopenIdentifierPattern = /\breopen\w*\s*[(=]/i;
  check(
    'extracted source has no "reopen" identifier',
    !reopenIdentifierPattern.test(EXTRACTED)
  );
}

// ---------------------------------------------------------------
// 26. New i18n keys present in both EN and TR.
// ---------------------------------------------------------------
async function testNewI18nKeysPresentInBothLanguages() {
  const sampleKeys = [
    'wrr.evidence.list_title', 'wrr.evidence.add_title', 'wrr.evidence.type_label',
    'wrr.evidence.submit_button', 'wrr.evidence.empty_state',
    'wrr.closure.readiness_title', 'wrr.closure.close_title', 'wrr.closure.ready',
    'wrr.closure.not_ready', 'wrr.closure.result_title',
  ];
  const ctx = newContext(EXTRACTED, HTML, async () => fakeDetail());
  vm.runInContext("setLanguageForTest = function(l){ CURRENT_LANG = l; }", ctx.context);
  sampleKeys.forEach((key) => {
    const enVal = vm.runInContext(`I18N.en[${JSON.stringify(key)}]`, ctx.context);
    const trVal = vm.runInContext(`I18N.tr[${JSON.stringify(key)}]`, ctx.context);
    check('EN has key ' + key, typeof enVal === 'string' && enVal.length > 0);
    check('TR has key ' + key, typeof trVal === 'string' && trVal.length > 0);
  });
}

// ---------------------------------------------------------------
// 27. Existing queue/detail/decision/history functions preserved.
// ---------------------------------------------------------------
async function testExistingFunctionsPreserved() {
  const script = extractScript(HTML);
  ['loadWasherResolutionQueue', 'wrrRenderQueueTable', 'wrrLoadResolutionDetail',
    'wrrRenderDetail', 'wrrShowDecisionFormForDetail', 'wrrSubmitDecision',
    'wrrLoadResolutionHistory', 'wrrRenderHistoryTable'].forEach((name) => {
    check('existing function still defined: ' + name, new RegExp('\\bfunction\\s+' + name + '\\s*\\(').test(script));
  });
}

// ---------------------------------------------------------------
// 28. apiRequest is not redefined by the new code.
// ---------------------------------------------------------------
async function testApiRequestNotRedefined() {
  const script = extractScript(HTML);
  const matches = script.match(/\basync function apiRequest\s*\(/g) || [];
  check('apiRequest defined exactly once', matches.length === 1);
}

// ---------------------------------------------------------------
// 29. XSS: backend strings are escaped, not injected raw.
// ---------------------------------------------------------------
async function testXssStringsEscaped() {
  const detail = fakeDetail();
  const record = fakeEvidenceRecord({ title: '<img src=x onerror=alert(1)>' });
  const router = makeRouter({ detail, evidenceRecords: [record] });
  const ctx = newContext(EXTRACTED, HTML, router);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  const tableHtml = ctx.byId['wrr-evidence-table']._html;
  checkNotIncludes('raw <img onerror not present in evidence table', tableHtml, '<img src=x onerror=alert(1)>');

  const readiness = fakeReadiness({ blocking_reasons: ['<script>alert(2)</script>'] });
  const router2 = makeRouter({ detail, readiness });
  const ctx2 = newContext(EXTRACTED, HTML, router2);
  primeAllElements(ctx2.byId);
  await loadDetail(ctx2, detail);
  const readinessHtml = ctx2.byId['wrr-closure-readiness-content']._html;
  checkNotIncludes('raw <script> not present in blocking_reasons render', readinessHtml, '<script>alert(2)</script>');
}

// ---------------------------------------------------------------
// 30. Harness itself produces a success marker at the end.
// ---------------------------------------------------------------
// (handled by main(); see bottom of file)

const ALL_TESTS = [
  testNewDomIdsPresentInRealHtml,
  testEvidenceTypeHasSevenOptions,
  testBackendGeneratedFieldsAbsentFromEvidenceForm,
  testBackendGeneratedFieldsAbsentFromCloseForm,
  testNoReopenUi,
  testDetailLoadCallsThreeNewLoaders,
  testEvidenceGetUsesCorrectEndpoint,
  testEvidencePostUsesCorrectEndpointAndPayload,
  testOptionalBlankFieldsOmitted,
  testAuthoritativeStandardRequiresSourceStandard,
  testEvidenceDoubleSubmitProtected,
  testSuccessRefreshesEvidenceReadinessClosure,
  testEvidenceListEmptyState,
  testVerificationStatusOnlyDisplayed,
  testReadinessEndpointCalledCorrectly,
  testEffectiveStatusShownInReadiness,
  testBlockingReasonsRendered,
  testCloseButtonDisabledWhenNotReady,
  testCloseButtonEnabledWhenReady,
  testCloseFormHiddenWhenClosureExists,
  testGetClosureNullHandledCorrectly,
  testClosureResultFieldsRendered,
  testClosePostSendsCorrectPayload,
  testCloseDoubleSubmitProtected,
  testNoReopenFunctionExists,
  testNewI18nKeysPresentInBothLanguages,
  testExistingFunctionsPreserved,
  testApiRequestNotRedefined,
  testXssStringsEscaped,
];

// =================================================================
async function main() {
  for (const testFn of ALL_TESTS) {
    try {
      await testFn();
    } catch (err) {
      const label = testFn.name + ' (threw)';
      recordFailure(label);
      console.log('FAIL: ' + label + ' -- ' + (err && err.stack ? err.stack : String(err)));
    }
  }
  const { pass, fail, failures } = summary();
  console.log((pass + fail) + ' assertions, ' + pass + ' passed, ' + fail + ' failed');
  if (fail > 0) {
    console.log('Failures:\n  - ' + failures.join('\n  - '));
    process.exitCode = 1;
    return;
  }
  console.log('SUCCESS: run_washer_resolution_evidence_closure_tests.js');
  process.exitCode = 0;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
