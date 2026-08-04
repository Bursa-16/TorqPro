#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.19 Stage 4 -- Washer Resolution Decision History regression
 * harness.
 *
 * Same live-extraction technique as
 * tests/js/run_washer_resolution_decision_form_tests.js: Node's
 * built-in `vm` module runs the *actual* history-view declarations
 * extracted live from frontend/index.html against a small
 * hand-built DOM stub.
 *
 * Scope: the read-only decision-history view only (Stage 4). Never
 * extracts or exercises report-specific (Stage 5) rendering beyond
 * what wrrLoadResolutionDetail itself needs to drive the history
 * load -- see run_washer_resolution_report_tests.js,
 * run_washer_resolution_queue_tests.js and
 * run_washer_resolution_decision_form_tests.js for that coverage.
 *
 * Invoked via `node tests/js/run_washer_resolution_decision_history_tests.js`
 * from the repo root, or indirectly via
 * tests/test_faz_2_8_19_stage4_washer_resolution_decision_history.py.
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
  'WRR_HISTORY_REQUIRED_FIELDS',
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
  'wrrHistoryRecordIsWellFormed', 'wrrHistoryResponseIsWellFormed',
  'wrrLoadResolutionHistory', 'wrrHideHistory', 'wrrRenderHistoryTable',
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
  vm.runInContext(extractedSource, context, { filename: 'wrr_history_extracted.js' });
  return { context, byId, documentStub };
}

const HISTORY_ELEMENT_IDS = ['wrr-history-card', 'wrr-history-status', 'wrr-history-content'];
const FORM_ELEMENT_IDS = [
  'wrr-decision-form-card', 'wrr-decide-blocked-notice', 'wrr-decide-terminal-notice',
  'wrr-decide-new-status', 'wrr-decide-resolution-note', 'wrr-decide-evidence-reference',
  'wrr-decide-resolved-by', 'wrr-decide-confidence-level',
  'wrr-decide-validation-error', 'wrr-decide-status', 'wrr-decide-submit-btn',
];
const DETAIL_ELEMENT_IDS = ['wrr-detail-card', 'wrr-detail-status', 'wrr-detail-content'];
const QUEUE_ELEMENT_IDS = ['wrr-queue-status', 'wrr-queue-content', 'wrr-queue-table'];

function primeAllElements(byId) {
  HISTORY_ELEMENT_IDS.concat(FORM_ELEMENT_IDS, DETAIL_ELEMENT_IDS, QUEUE_ELEMENT_IDS).forEach((id) => {
    byId[id] = makeElement(id);
  });
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

function blockedDetail() {
  return fakeDetail({
    resolution_id: 'RES-WASH-ISO7093-M10',
    source_status: 'blocked_authoritative_source',
    effective_status: 'blocked_authoritative_source',
    is_blocked: true,
  });
}

function terminalDetail() {
  return fakeDetail({
    resolution_id: 'RES-WASH-TERMINAL-EXAMPLE',
    effective_status: 'resolved',
    decision_count: 1,
    is_terminal: true,
  });
}

function fakeDecision(overrides) {
  const base = {
    decision_id: 'DEC-0001',
    resolution_id: 'RES-WASH-DIN127B-M10',
    previous_status: 'open',
    new_status: 'under_review',
    resolution_note: 'Escalated for secondary source review.',
    evidence_reference: 'internal-review-log#2026-08-03',
    resolved_by: 'ilhan',
    decided_at: '2026-08-03T12:00:00Z',
    confidence_level: 2,
    integrity_checksum: 'a1b2c3',
    idempotency_key: 'wrr-decide-abc123',
  };
  return Object.assign({}, base, overrides);
}

function defaultApi(detail, decisions) {
  return async (p) => {
    if (p.indexOf('/decisions') !== -1) return { resolution_id: detail.resolution_id, decisions: decisions || [] };
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  };
}

async function loadDetail(ctx, detail) {
  await vm.runInContext(`wrrLoadResolutionDetail(${JSON.stringify(detail.resolution_id)})`, ctx.context);
}

// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// Test scenarios.
// ---------------------------------------------------------------

// 1. History not called before detail loaded
async function testHistoryNotCalledBeforeDetailLoaded() {
  let historyCalled = false;
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decisions') !== -1) historyCalled = true;
    return { records: [] };
  });
  primeAllElements(ctx.byId);
  check('history endpoint not called before any detail load', !historyCalled);
}

// 2. Correct resolution_id used
async function testHistoryCallsCorrectUrl() {
  let calledPath = null;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decisions') !== -1) { calledPath = p; return { resolution_id: detail.resolution_id, decisions: [] }; }
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check(
    'history called with correct URL',
    calledPath === '/api/library/washers/resolutions/RES-WASH-DIN127B-M10/decisions'
  );
}

// 3. Response order preserved (no client-side re-sort)
async function testResponseOrderPreserved() {
  const detail = fakeDetail();
  const decisions = [
    fakeDecision({ decision_id: 'DEC-0003', decided_at: '2026-08-03T09:00:00Z' }),
    fakeDecision({ decision_id: 'DEC-0001', decided_at: '2026-08-03T12:00:00Z' }),
    fakeDecision({ decision_id: 'DEC-0002', decided_at: '2026-08-03T10:00:00Z' }),
  ];
  const ctx = newContext(EXTRACTED, HTML, defaultApi(detail, decisions));
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  const html = ctx.byId['wrr-history-content'].innerHTML;
  const posA = html.indexOf('DEC-0003');
  const posB = html.indexOf('DEC-0001');
  const posC = html.indexOf('DEC-0002');
  check('rendered in exact API response order, not re-sorted', posA < posB && posB < posC);
}

// 4. Decision rows render with the real field names
async function testDecisionRowsRender() {
  const detail = fakeDetail();
  const decisions = [fakeDecision()];
  const ctx = newContext(EXTRACTED, HTML, defaultApi(detail, decisions));
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  const html = ctx.byId['wrr-history-content'].innerHTML;
  checkIncludes('decision_id rendered', html, 'DEC-0001');
  checkIncludes('resolution_note rendered', html, 'Escalated for secondary source review.');
  checkIncludes('evidence_reference rendered', html, 'internal-review-log#2026-08-03');
  checkIncludes('resolved_by rendered', html, 'ilhan');
  checkIncludes('decided_at rendered', html, '2026-08-03T12:00:00Z');
  check('history card shown', ctx.byId['wrr-history-card'].style.display === '');
  check('history content shown, status cleared', ctx.byId['wrr-history-content'].style.display === '');
}

// 5. Empty history state
async function testEmptyHistoryShowsEmptyState() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, defaultApi(detail, []));
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  const expectedMessage = vm.runInContext("t('wrr.history.empty_state')", ctx.context);
  checkIncludes('empty history message shown', ctx.byId['wrr-history-content'].innerHTML, expectedMessage);
  checkNotIncludes('no <table> tag for empty history', ctx.byId['wrr-history-content'].innerHTML, '<table');
}

// 6. 404 error
async function test404HistoryErrorShown() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decisions') !== -1) throw new Error('Bilinmeyen resolution_id: RES-WASH-DIN127B-M10');
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  checkIncludes('404 message surfaced', ctx.byId['wrr-history-status'].innerHTML, 'Bilinmeyen resolution_id');
  checkIncludes('404 error uses alert-danger styling', ctx.byId['wrr-history-status'].innerHTML, 'alert-danger');
}

// 7. Network error
async function testNetworkHistoryErrorShown() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decisions') !== -1) throw new Error('network unreachable');
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  checkIncludes('network error surfaced', ctx.byId['wrr-history-status'].innerHTML, 'network unreachable');
}

// 8. Malformed response
async function testMalformedHistoryResponseRejected() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decisions') !== -1) return { decisions: [{ decision_id: 'X' }] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  checkIncludes('malformed history shows a clear message', ctx.byId['wrr-history-status'].innerHTML, 'alert-danger');
  check('malformed history leaves content hidden', ctx.byId['wrr-history-content'].style.display === 'none');
}

async function testNonArrayDecisionsRejected() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decisions') !== -1) return { decisions: 'not-an-array' };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  checkIncludes('non-array decisions field rejected as malformed', ctx.byId['wrr-history-status'].innerHTML, 'alert-danger');
}

// 9. Blocked record history accessible
async function testBlockedRecordHistoryAccessible() {
  const detail = blockedDetail();
  const decisions = [fakeDecision({ resolution_id: detail.resolution_id })];
  const ctx = newContext(EXTRACTED, HTML, defaultApi(detail, decisions));
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('history card shown for a blocked record', ctx.byId['wrr-history-card'].style.display === '');
  checkIncludes('blocked record history decision rendered', ctx.byId['wrr-history-content'].innerHTML, 'DEC-0001');
}

// 10. Terminal record history accessible
async function testTerminalRecordHistoryAccessible() {
  const detail = terminalDetail();
  const decisions = [fakeDecision({ resolution_id: detail.resolution_id })];
  const ctx = newContext(EXTRACTED, HTML, defaultApi(detail, decisions));
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('history card shown for a terminal record', ctx.byId['wrr-history-card'].style.display === '');
  checkIncludes('terminal record history decision rendered', ctx.byId['wrr-history-content'].innerHTML, 'DEC-0001');
}

// 11. Read-only: no mutation controls anywhere in the rendered markup
async function testHistoryIsReadOnlyNoMutationControls() {
  const detail = fakeDetail();
  const decisions = [fakeDecision()];
  const ctx = newContext(EXTRACTED, HTML, defaultApi(detail, decisions));
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  const html = ctx.byId['wrr-history-content'].innerHTML;
  for (const forbidden of ['<button', '<input', '<select', '<textarea', 'onclick=']) {
    checkNotIncludes(`no ${forbidden} in the history table`, html, forbidden);
  }
}

function testNoEditDeleteRollbackFunctionsExist() {
  const forbiddenNames = [
    'wrrEditDecision', 'wrrDeleteDecision', 'wrrRollbackDecision',
    'wrrReplayDecision', 'wrrDuplicateDecision', 'wrrApproveDecision', 'wrrRejectDecision',
  ];
  for (const name of forbiddenNames) {
    check(`no ${name} function defined in frontend`, HTML.indexOf('function ' + name) === -1);
  }
}

// 12. Successful decide refreshes history
async function testSuccessfulDecideRefreshesHistory() {
  let historyCalls = 0;
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    if (p.indexOf('/decide') !== -1) return { decision: {}, created: true };
    if (p.indexOf('/decisions') !== -1) { historyCalls++; return { resolution_id: detail.resolution_id, decisions: [] }; }
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail); // historyCalls = 1
  const fields = {
    'wrr-decide-new-status': 'under_review',
    'wrr-decide-resolution-note': 'Escalated for secondary source review.',
    'wrr-decide-evidence-reference': 'internal-review-log#2026-08-03',
    'wrr-decide-resolved-by': 'ilhan',
  };
  Object.entries(fields).forEach(([id, v]) => { ctx.byId[id].value = v; });
  await vm.runInContext('wrrSubmitDecision()', ctx.context);
  check('history reloaded after a successful decide submit', historyCalls === 2);
}

// 13. Queue/detail/report regression (scoped smoke check; full
// coverage lives in the Stage 2/report harnesses)
async function testQueueDetailStillWorkAfterHistoryAdditions() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, defaultApi(detail, []));
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  check('queue content still shown (no regression)', ctx.byId['wrr-queue-content'].style.display === '');
  await loadDetail(ctx, detail);
  check('detail content still shown (no regression)', ctx.byId['wrr-detail-content'].style.display === '');
}

// 14. Decision form regression: still shown/enabled correctly
async function testDecisionFormStillWorksAfterHistoryAdditions() {
  const detail = fakeDetail();
  const ctx = newContext(EXTRACTED, HTML, defaultApi(detail, []));
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('decision form still shown (no regression)', ctx.byId['wrr-decision-form-card'].style.display === '');
  check('submit button still enabled for an open record (no regression)', ctx.byId['wrr-decide-submit-btn'].disabled === false);
}

// 15. TR/EN parity for new wrr.history.* keys
async function testHistoryKeysHaveTrAndEnTranslations() {
  const ctx = newContext(EXTRACTED, HTML);
  const keys = [
    'wrr.history.title', 'wrr.history.subtitle', 'wrr.history.empty_state',
    'wrr.history.col.decision_id', 'wrr.history.col.previous_status',
    'wrr.history.col.new_status', 'wrr.history.col.resolution_note',
    'wrr.history.col.evidence_reference', 'wrr.history.col.resolved_by',
    'wrr.history.col.decided_at', 'wrr.history.col.confidence_level',
  ];
  for (const key of keys) {
    const trValue = vm.runInContext(`I18N['tr'][${JSON.stringify(key)}]`, ctx.context);
    const enValue = vm.runInContext(`I18N['en'][${JSON.stringify(key)}]`, ctx.context);
    check(`TR value present for ${key}`, typeof trValue === 'string' && trValue.length > 0);
    check(`EN value present for ${key}`, typeof enValue === 'string' && enValue.length > 0);
  }
}

// 16. No bulk/AI call anywhere in this scope
async function testNoBulkOrAiCall() {
  const detail = fakeDetail();
  const calledPaths = [];
  const ctx = newContext(EXTRACTED, HTML, async (p) => {
    calledPaths.push(p);
    if (p.indexOf('/decisions') !== -1) return { resolution_id: detail.resolution_id, decisions: [fakeDecision()] };
    if (p.indexOf('/queue') !== -1) return { records: [] };
    return detail;
  });
  primeAllElements(ctx.byId);
  await loadDetail(ctx, detail);
  check('no bulk endpoint called', calledPaths.every((p) => p.toLowerCase().indexOf('bulk') === -1));
  check('no ai endpoint called', calledPaths.every((p) => p.toLowerCase().indexOf('/ai/') === -1));
}

const ALL_TESTS = [
  testHistoryNotCalledBeforeDetailLoaded,
  testHistoryCallsCorrectUrl,
  testResponseOrderPreserved,
  testDecisionRowsRender,
  testEmptyHistoryShowsEmptyState,
  test404HistoryErrorShown,
  testNetworkHistoryErrorShown,
  testMalformedHistoryResponseRejected,
  testNonArrayDecisionsRejected,
  testBlockedRecordHistoryAccessible,
  testTerminalRecordHistoryAccessible,
  testHistoryIsReadOnlyNoMutationControls,
  testNoEditDeleteRollbackFunctionsExist,
  testSuccessfulDecideRefreshesHistory,
  testQueueDetailStillWorkAfterHistoryAdditions,
  testDecisionFormStillWorksAfterHistoryAdditions,
  testHistoryKeysHaveTrAndEnTranslations,
  testNoBulkOrAiCall,
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
