#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.19 Stage 3 -- Washer Resolution Decision Entry Form
 * regression harness.
 *
 * Same live-extraction technique as
 * tests/js/run_washer_resolution_queue_tests.js: Node's built-in
 * `vm` module runs the *actual* decision-form declarations extracted
 * live from frontend/index.html against a small hand-built DOM stub.
 *
 * Scope: the decision-entry form only (Stage 3). Never extracts or
 * exercises report-specific (Stage 5) or queue-table-specific
 * (Stage 2) rendering beyond what wrrLoadResolutionDetail itself
 * needs to drive the form's show/hide logic -- see
 * run_washer_resolution_report_tests.js and
 * run_washer_resolution_queue_tests.js for that coverage.
 *
 * Invoked via `node tests/js/run_washer_resolution_decision_form_tests.js`
 * from the repo root, or indirectly via
 * tests/test_faz_2_8_19_stage3_washer_resolution_decision_form_frontend.py.
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
  'WRR_QUEUE_REQUIRED_FIELDS', 'WRR_DETAIL_REQUIRED_FIELDS',
  'WRR_LAST_QUEUE', 'WRR_LAST_DETAIL',
  'WRR_DECIDE_IDEMPOTENCY_KEY', 'WRR_DECIDE_KEY_RESOLUTION_ID', 'WRR_DECIDE_IN_FLIGHT',
];
const MUTABLE_STATE_NAMES = [
  'WRR_LAST_QUEUE', 'WRR_LAST_DETAIL',
  'WRR_DECIDE_IDEMPOTENCY_KEY', 'WRR_DECIDE_KEY_RESOLUTION_ID', 'WRR_DECIDE_IN_FLIGHT',
];
const FUNCTION_NAMES = [
  't', 'applyStaticTranslations', 'setLanguage', 'scEsc',
  'wrrStatusLabel', 'wrrBoolLabel',
  'wrrQueueRecordIsWellFormed', 'wrrDetailIsWellFormed',
  'loadWasherResolutionQueue', 'wrrRenderQueueTable',
  'wrrLoadResolutionDetail', 'wrrDetailField', 'wrrRenderDetail',
  'wrrGenerateIdempotencyKey', 'wrrPopulateStatusOptions', 'wrrResetDecisionForm',
  'wrrShowDecisionFormForDetail', 'wrrHideDecisionForm',
  'wrrValidateDecisionForm', 'wrrSubmitDecision',
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
  parts.push('function __getWrrLastDetail() { return WRR_LAST_DETAIL; }');
  parts.push('function __setWrrLastDetail(v) { WRR_LAST_DETAIL = v; }');
  parts.push('function __getDecideKey() { return WRR_DECIDE_IDEMPOTENCY_KEY; }');
  parts.push('function __getDecideKeyResolutionId() { return WRR_DECIDE_KEY_RESOLUTION_ID; }');
  parts.push('function __getDecideInFlight() { return WRR_DECIDE_IN_FLIGHT; }');
  return { source: parts.join('\n\n'), rawHtml: html };
}

function buildDom(rawHtml, byId) {
  return buildDomShared(rawHtml, byId, { includePlaceholders: false });
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
    encodeURIComponent: encodeURIComponent,
    parseInt: parseInt,
    Date: Date,
    Math: Math,
    apiRequest: apiRequestImpl || (() => { throw new Error('apiRequest should not be called by this test'); }),
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'wrr_decide_extracted.js' });
  return { context, byId, documentStub };
}

const FORM_ELEMENT_IDS = [
  'wrr-decision-form-card', 'wrr-decide-blocked-notice', 'wrr-decide-terminal-notice',
  'wrr-decide-new-status', 'wrr-decide-resolution-note', 'wrr-decide-evidence-reference',
  'wrr-decide-resolved-by', 'wrr-decide-confidence-level',
  'wrr-decide-validation-error', 'wrr-decide-status', 'wrr-decide-submit-btn',
];
const DETAIL_ELEMENT_IDS = ['wrr-detail-card', 'wrr-detail-status', 'wrr-detail-content'];
const QUEUE_ELEMENT_IDS = ['wrr-queue-status', 'wrr-queue-content', 'wrr-queue-table'];

function primeAllElements(byId) {
  FORM_ELEMENT_IDS.concat(DETAIL_ELEMENT_IDS, QUEUE_ELEMENT_IDS).forEach((id) => {
    byId[id] = makeElement(id);
  });
}

function fillValidForm(ctx, overrides) {
  const values = Object.assign({
    'wrr-decide-new-status': 'under_review',
    'wrr-decide-resolution-note': 'Escalated for secondary source review.',
    'wrr-decide-evidence-reference': 'internal-review-log#2026-08-03',
    'wrr-decide-resolved-by': 'ilhan',
    'wrr-decide-confidence-level': '',
  }, overrides || {});
  Object.entries(values).forEach(([id, v]) => { ctx.byId[id].value = v; });
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

function blockedDetail(overrides) {
  return fakeDetail(Object.assign({
    resolution_id: 'RES-WASH-ISO7093-M10',
    source_status: 'blocked_authoritative_source',
    effective_status: 'blocked_authoritative_source',
    is_blocked: true,
  }, overrides));
}

function terminalDetail(overrides) {
  return fakeDetail(Object.assign({
    resolution_id: 'RES-WASH-TERMINAL-EXAMPLE',
    effective_status: 'resolved',
    decision_count: 1,
    is_terminal: true,
  }, overrides));
}

async function loadDetail(ctx, detail) {
  await vm.runInContext(`wrrLoadResolutionDetail(${JSON.stringify(detail.resolution_id)})`, ctx.context);
}

// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// Test scenarios.
// ---------------------------------------------------------------

// 1. wrrHideDecisionForm() actually hides the card (the static
// style="display:none" HTML attribute itself is verified by the
// companion Python structural test, not this behavioral harness,
// since the DOM stub does not parse inline style attributes).
async function testHideDecisionFormHidesCard() {
  const ctx = newContext(EXTRACTED, HTML);
  primeAllElements(ctx.byId);
  ctx.byId['wrr-decision-form-card'].style.display = '';
  vm.runInContext('wrrHideDecisionForm()', ctx.context);
  check('wrrHideDecisionForm sets display to none', ctx.byId['wrr-decision-form-card'].style.display === 'none');
}

// 2. Form shown after successful detail load
async function testFormShownAfterSuccessfulDetailLoad() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async () => detail);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('form shown after detail loads', ctx.byId['wrr-decision-form-card'].style.display === '');
}

// 3. Form stays hidden on detail load error
async function testFormHiddenOnDetailError() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('network unreachable'); });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, fakeDetail());
  check('form stays hidden on detail error', ctx.byId['wrr-decision-form-card'].style.display === 'none');
}

// 4. POST called with correct resolution_id URL
async function testSubmitCallsCorrectUrl() {
  let decideCallPath = null;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) { decideCallPath = p; return { decision: {}, created: true }; }
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check(
    'submit called correct URL',
    decideCallPath === '/api/library/washers/resolutions/RES-WASH-DIN127B-M10/decide'
  );
}

// 5. Canonical request body + Content-Type via apiRequest (JSON body)
async function testSubmitSendsCanonicalRequestBody() {
  let calledOptions = null;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => {
    if (p.indexOf('/decide') !== -1) { calledOptions = opts; return { decision: {}, created: true }; }
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx, { 'wrr-decide-confidence-level': '2' });
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('POST method used', calledOptions && calledOptions.method === 'POST');
  const body = JSON.parse(calledOptions.body);
  check('body.new_status correct', body.new_status === 'under_review');
  check('body.resolution_note correct', body.resolution_note === 'Escalated for secondary source review.');
  check('body.evidence_reference correct', body.evidence_reference === 'internal-review-log#2026-08-03');
  check('body.resolved_by correct', body.resolved_by === 'ilhan');
  check('body.confidence_level is a number', body.confidence_level === 2);
  check('body.idempotency_key present', typeof body.idempotency_key === 'string' && body.idempotency_key.length > 0);
  check('no decided_at sent by client', !('decided_at' in body));
}

async function testConfidenceLevelOmittedWhenBlank() {
  let calledOptions = null;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => {
    if (p.indexOf('/decide') !== -1) { calledOptions = opts; return { decision: {}, created: true }; }
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  const body = JSON.parse(calledOptions.body);
  check('confidence_level omitted when left blank', !('confidence_level' in body));
}

// 6. Required-field validation (backend-contract-derived only)
async function testMissingRequiredFieldsBlocksSubmit() {
  let apiWasCalled = false;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => { apiWasCalled = apiWasCalled || p.indexOf('/decide') !== -1; return detail; });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx, { 'wrr-decide-resolution-note': '', 'wrr-decide-evidence-reference': '' });
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('decide not called when required fields are blank', !apiWasCalled);
  const expectedLabel = vm.runInContext("t('wrr.decide.resolution_note_label')", ctx.context);
  checkIncludes(
    'validation error names the missing resolution_note field',
    ctx.byId['wrr-decide-validation-error'].textContent,
    expectedLabel
  );
  check('validation error element made visible', ctx.byId['wrr-decide-validation-error'].style.display === '');
}

async function testBlankNewStatusBlocksSubmit() {
  let apiWasCalled = false;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => { apiWasCalled = apiWasCalled || p.indexOf('/decide') !== -1; return detail; });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx, { 'wrr-decide-new-status': '' });
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('decide not called when new_status is blank', !apiWasCalled);
}

async function testWhitespaceOnlyFieldsTreatedAsBlank() {
  let apiWasCalled = false;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => { apiWasCalled = apiWasCalled || p.indexOf('/decide') !== -1; return detail; });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx, { 'wrr-decide-resolved-by': '   ' });
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('whitespace-only resolved_by rejected client-side (matches backend .strip() check)', !apiWasCalled);
}

// 7. Submit button disabled during in-flight request; double-submit blocked
async function testSubmitButtonDisabledDuringRequest() {
  let resolveApi;
  const detail = fakeDetail();
  const apiPromise = new Promise((resolve) => { resolveApi = resolve; });
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) { await apiPromise; return { decision: {}, created: true }; }
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  const submitPromise = vm.runInContext('wrrSubmitDecision()', ctx.context);
  await new Promise((r) => setTimeout(r, 0));
  check('submit button disabled while request in flight', ctx.byId['wrr-decide-submit-btn'].disabled === true);
  resolveApi();
  await submitPromise;
}

async function testDoubleSubmitDoesNotSendTwoRequests() {
  let calls = 0;
  let resolveApi;
  const detail = fakeDetail();
  const apiPromise = new Promise((resolve) => { resolveApi = resolve; });
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) { calls++; await apiPromise; return { decision: {}, created: true }; }
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  const first = vm.runInContext('wrrSubmitDecision()', ctx.context);
  await new Promise((r) => setTimeout(r, 0));
  const second = vm.runInContext('wrrSubmitDecision()', ctx.context);
  resolveApi();
  await first;
  await second;
  check('only one /decide call made despite a second concurrent submit attempt', calls === 1);
}

// 8. Idempotency key behavior
async function testIdempotencyKeyPersistsAcrossFailedRetry() {
  let seenKeys = [];
  const detail = fakeDetail();
  let shouldFail = true;
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => {
    if (p.indexOf('/decide') !== -1) {
      const body = JSON.parse(opts.body);
      seenKeys.push(body.idempotency_key);
      if (shouldFail) throw new Error('conflict');
      return { decision: {}, created: true };
    }
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context); // fails
  await vm.runInContext('wrrSubmitDecision()', ctx.context); // retry, same key expected
  check('idempotency_key unchanged across a failed-submit retry', seenKeys.length === 2 && seenKeys[0] === seenKeys[1]);
}

async function testNewIdempotencyKeyAfterSuccess() {
  const keysUsed = [];
  const detail = fakeDetail();
  let callCount = 0;
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => {
    if (p.indexOf('/decide') !== -1) {
      callCount++;
      keysUsed.push(JSON.parse(opts.body).idempotency_key);
      return { decision: {}, created: true };
    }
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context); // succeeds
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context); // second, independent submit
  check('two decide calls made', callCount === 2);
  check('a new idempotency_key was used for the post-success submit', keysUsed[0] !== keysUsed[1]);
}

async function testNewRecordGetsFreshIdempotencyKey() {
  const detailA = fakeDetail({ resolution_id: 'RES-A' });
  const detailB = fakeDetail({ resolution_id: 'RES-B' });
  const ctx = newContext(EXTRACTED, HTML, async (p) => (p.indexOf('RES-A') !== -1 ? detailA : detailB));
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detailA);
  const keyA = vm.runInContext('__getDecideKey()', ctx.context);
  await loadDetail(ctx, detailB);
  const keyB = vm.runInContext('__getDecideKey()', ctx.context);
  check('a different record gets a different idempotency_key', keyA !== keyB);
}

// 9. Success behavior: message, queue refresh, detail refresh, form reset
async function testSuccessfulSubmitShowsSuccessMessage() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) return { decision: {}, created: true };
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  checkIncludes('success message shown', ctx.byId['wrr-decide-status'].innerHTML, 'alert-success');
}

async function testSuccessfulSubmitRefreshesQueueAndDetail() {
  let queueCalls = 0;
  let detailCalls = 0;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) return { decision: {}, created: true };
    if (p.indexOf('/queue') !== -1) { queueCalls++; return { records: [] }; }
    detailCalls++;
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail); // detailCalls = 1
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('queue reloaded after successful submit', queueCalls === 1);
  check('detail reloaded after successful submit', detailCalls === 2);
}

async function testFormFieldsResetAfterSuccessfulSubmit() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) return { decision: {}, created: true };
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('resolution_note cleared after success', ctx.byId['wrr-decide-resolution-note'].value === '');
  check('evidence_reference cleared after success', ctx.byId['wrr-decide-evidence-reference'].value === '');
}

// 10. Error handling: 404 / 409 / 422 / network
async function testSubmitErrorShown() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) throw new Error("Resolution 'X' was not found in the ledger.");
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  checkIncludes('404-style error surfaced', ctx.byId['wrr-decide-validation-error'].textContent, 'not found');
}

async function testBlockedConflictErrorShown() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) {
      throw new Error("Resolution 'X' is blocked_authoritative_source; it cannot be decided through this workflow in this phase.");
    }
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  checkIncludes('409 blocked message surfaced verbatim from backend', ctx.byId['wrr-decide-validation-error'].textContent, 'blocked_authoritative_source');
}

async function testValidationErrorFromBackendShown() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) throw new Error('Eksik alanlar: resolution_note');
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  checkIncludes('422-style backend validation message surfaced', ctx.byId['wrr-decide-validation-error'].textContent, 'Eksik alanlar');
}

async function testNetworkErrorShown() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) throw new Error('network unreachable');
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  checkIncludes('network error surfaced', ctx.byId['wrr-decide-validation-error'].textContent, 'network unreachable');
}

// 11. Terminal record behavior
async function testTerminalRecordDisablesForm() {
  const detail = terminalDetail();
  const ctx = newContext(EXTRACTED, HTML, async () => detail);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('submit button disabled for a terminal record', ctx.byId['wrr-decide-submit-btn'].disabled === true);
  check('terminal notice shown', ctx.byId['wrr-decide-terminal-notice'].style.display === '');
}

// 12. Blocked record behavior
async function testBlockedRecordDisablesForm() {
  const detail = blockedDetail();
  const ctx = newContext(EXTRACTED, HTML, async () => detail);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('submit button disabled for a blocked record', ctx.byId['wrr-decide-submit-btn'].disabled === true);
  check('blocked notice shown', ctx.byId['wrr-decide-blocked-notice'].style.display === '');
  check('terminal notice not shown for a blocked (not terminal) record', ctx.byId['wrr-decide-terminal-notice'].style.display === 'none');
}

async function testOpenRecordEnablesForm() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async () => detail);
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('submit button enabled for an open, non-terminal record', ctx.byId['wrr-decide-submit-btn'].disabled === false);
  check('blocked notice not shown', ctx.byId['wrr-decide-blocked-notice'].style.display === 'none');
  check('terminal notice not shown', ctx.byId['wrr-decide-terminal-notice'].style.display === 'none');
}

// 13. GET-only queue/detail behavior preserved (Stage 2 regression, scoped check)
async function testQueueAndDetailLoadsAreGetOnly() {
  const methodsUsed = [];
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => {
    methodsUsed.push((opts && opts.method) || 'GET');
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  await loadDetail(ctx, detail);
  check('queue/detail loads never use POST', methodsUsed.every((m) => m === 'GET'));
}

// 14. Decision history endpoint never called
async function testDecisionHistoryEndpointNeverCalled() {
  const detail = fakeDetail();
  const calledPaths = [];
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    calledPaths.push(p);
    if (p.indexOf('/decide') !== -1) return { decision: {}, created: true };
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('no call to the decisions-history endpoint', calledPaths.every((p) => p.indexOf('/decisions') === -1));
}

// 15. No bulk endpoint call
async function testNoBulkEndpointCalled() {
  const detail = fakeDetail();
  const calledPaths = [];
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    calledPaths.push(p);
    if (p.indexOf('/decide') !== -1) return { decision: {}, created: true };
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  fillValidForm(ctx);
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('no bulk/batch endpoint called', calledPaths.every((p) => p.toLowerCase().indexOf('bulk') === -1));
}

// 16. No form markup outside the decision-form card (no accidental
// duplicate form fields elsewhere on the page).
async function testFormMarkupOnlyInsideDecisionFormCard() {
  const cardStart = HTML.indexOf('id="wrr-decision-form-card"');
  const cardEnd = HTML.indexOf('</div>\n</div>\n\n  <div id="page-governance"');
  check('decision form card markup present', cardStart !== -1);
  const beforeCard = HTML.slice(0, cardStart);
  checkNotIncludes('no id="wrr-decide-" markup appears before the card itself', beforeCard, 'id="wrr-decide-');
}

// 17. TR/EN parity for the new decide.* keys
async function testDecideKeysHaveTrAndEnTranslations() {
  const ctx = newContext(EXTRACTED, HTML);
  const keys = [
    'wrr.decide.title', 'wrr.decide.subtitle', 'wrr.decide.blocked_notice',
    'wrr.decide.terminal_notice', 'wrr.decide.select_placeholder',
    'wrr.decide.new_status_label', 'wrr.decide.resolution_note_label',
    'wrr.decide.evidence_reference_label', 'wrr.decide.resolved_by_label',
    'wrr.decide.confidence_level_label', 'wrr.decide.confidence_none',
    'wrr.decide.submit_button', 'wrr.decide.submitting', 'wrr.decide.success',
    'wrr.decide.validation_error_prefix',
  ];
  for (const key of keys) {
    const trValue = vm.runInContext(`I18N['tr'][${JSON.stringify(key)}]`, ctx.context);
    const enValue = vm.runInContext(`I18N['en'][${JSON.stringify(key)}]`, ctx.context);
    check(`TR value present for ${key}`, typeof trValue === 'string' && trValue.length > 0);
    check(`EN value present for ${key}`, typeof enValue === 'string' && enValue.length > 0);
  }
}

const ALL_TESTS = [
  testHideDecisionFormHidesCard,
  testFormShownAfterSuccessfulDetailLoad,
  testFormHiddenOnDetailError,
  testSubmitCallsCorrectUrl,
  testSubmitSendsCanonicalRequestBody,
  testConfidenceLevelOmittedWhenBlank,
  testMissingRequiredFieldsBlocksSubmit,
  testBlankNewStatusBlocksSubmit,
  testWhitespaceOnlyFieldsTreatedAsBlank,
  testSubmitButtonDisabledDuringRequest,
  testDoubleSubmitDoesNotSendTwoRequests,
  testIdempotencyKeyPersistsAcrossFailedRetry,
  testNewIdempotencyKeyAfterSuccess,
  testNewRecordGetsFreshIdempotencyKey,
  testSuccessfulSubmitShowsSuccessMessage,
  testSuccessfulSubmitRefreshesQueueAndDetail,
  testFormFieldsResetAfterSuccessfulSubmit,
  testSubmitErrorShown,
  testBlockedConflictErrorShown,
  testValidationErrorFromBackendShown,
  testNetworkErrorShown,
  testTerminalRecordDisablesForm,
  testBlockedRecordDisablesForm,
  testOpenRecordEnablesForm,
  testQueueAndDetailLoadsAreGetOnly,
  testDecisionHistoryEndpointNeverCalled,
  testNoBulkEndpointCalled,
  testFormMarkupOnlyInsideDecisionFormCard,
  testDecideKeysHaveTrAndEnTranslations,
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
  process.exitCode = 0;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
