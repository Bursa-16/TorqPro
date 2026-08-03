#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.19 Stage 2 -- Washer Resolution Queue / Detail frontend
 * regression harness.
 *
 * Zero external dependencies, same technique as
 * tests/js/run_washer_resolution_report_tests.js: Node's built-in
 * `vm` module runs the *actual* Resolution Queue / Detail
 * declarations extracted live from frontend/index.html (never a
 * committed copy) against a small hand-built DOM stub.
 *
 * Scope: read-only queue list + read-only detail lookup only. No
 * scenario here ever calls POST /decide -- one scenario explicitly
 * asserts that no such call is made. Never extracts or exercises
 * wrrReapplyLanguage() (that function also touches the separate
 * Faz 2.8.9 report state/functions, which are this harness's
 * intentional non-goal -- see run_washer_resolution_report_tests.js
 * for report-specific coverage, including its own language-switch
 * test).
 *
 * Invoked via `node tests/js/run_washer_resolution_queue_tests.js`
 * from the repo root, or indirectly via
 * tests/test_faz_2_8_19_stage2_washer_resolution_queue_frontend.py.
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
];
const MUTABLE_STATE_NAMES = ['WRR_LAST_QUEUE', 'WRR_LAST_DETAIL'];
const FUNCTION_NAMES = [
  't', 'applyStaticTranslations', 'setLanguage', 'scEsc',
  'wrrStatusLabel', 'wrrBoolLabel',
  'wrrQueueRecordIsWellFormed', 'wrrDetailIsWellFormed',
  'loadWasherResolutionQueue', 'wrrRenderQueueTable',
  'wrrLoadResolutionDetail', 'wrrDetailField', 'wrrRenderDetail',
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
  parts.push('function __getWrrLastQueue() { return WRR_LAST_QUEUE; }');
  parts.push('function __getWrrLastDetail() { return WRR_LAST_DETAIL; }');
  return { source: parts.join('\n\n'), rawScript: script, rawHtml: html };
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
    apiRequest: apiRequestImpl || (() => { throw new Error('apiRequest should not be called by this test'); }),
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'wrr_queue_extracted.js' });
  return { context, byId, documentStub };
}

function primeQueueElements(byId) {
  ['wrr-queue-status', 'wrr-queue-content', 'wrr-queue-table'].forEach((id) => {
    byId[id] = makeElement(id);
  });
}

function primeDetailElements(byId) {
  ['wrr-detail-card', 'wrr-detail-status', 'wrr-detail-content'].forEach((id) => {
    byId[id] = makeElement(id);
  });
}

function primeAllElements(byId) {
  primeQueueElements(byId);
  primeDetailElements(byId);
}

// Response fixtures shaped exactly like the Faz 2.8.19 Stage 1
// resolution_queue() / resolution_detail() response shapes.
function fakeQueueRecord(overrides) {
  const base = {
    resolution_id: 'RES-WASH-DIN127B-M10',
    washer_record_id: 'WASH-DIN127B-M10',
    issue_type: 'source_missing',
    source_status: 'open',
    effective_status: 'open',
    decision_count: 0,
    is_blocked: false,
    is_terminal: false,
    requires_authoritative_source: false,
  };
  return Object.assign({}, base, overrides);
}

function fakeBlockedQueueRecord(overrides) {
  return fakeQueueRecord(Object.assign({
    resolution_id: 'RES-WASH-ISO7093-M10',
    washer_record_id: 'WASH-ISO7093-M10',
    issue_type: 'standard_identity_ambiguous',
    source_status: 'blocked_authoritative_source',
    effective_status: 'blocked_authoritative_source',
    is_blocked: true,
  }, overrides));
}

function fakeTerminalQueueRecord(overrides) {
  return fakeQueueRecord(Object.assign({
    resolution_id: 'RES-WASH-TERMINAL-EXAMPLE',
    source_status: 'open',
    effective_status: 'resolved',
    decision_count: 1,
    is_terminal: true,
  }, overrides));
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
    resolution_note: 'Flagged as a review priority signal, not a correctness claim.',
    evidence_reference: 'docs/phase_2_8/phase_2_8_4_washer_provenance_report.json#action_needed_records[record_id=WASH-DIN127B-M10]',
    resolved_standard: null,
    resolved_by: '',
    resolved_at: '',
    confidence_level: 2,
    requires_authoritative_source: false,
  };
  return Object.assign({}, base, overrides);
}

// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// Test scenarios.
// ---------------------------------------------------------------

// 1. Queue endpoint is called with the correct URL
async function testQueueCallsCorrectUrl() {
  let calledPath = null;
  const ctx = newContext(EXTRACTED, HTML, async (p) => { calledPath = p; return { records: [] }; });
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  check('queue called correct URL', calledPath === '/api/library/washers/resolutions/queue');
}

// 2. Queue records render with the real field names, no guessing
async function testQueueRecordsRender() {
  const records = [fakeQueueRecord(), fakeBlockedQueueRecord()];
  const ctx = newContext(EXTRACTED, HTML, async () => ({ records }));
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  const html = ctx.byId['wrr-queue-table'].innerHTML;
  checkIncludes('open record resolution_id rendered', html, 'RES-WASH-DIN127B-M10');
  checkIncludes('open record washer_record_id rendered', html, 'WASH-DIN127B-M10');
  checkIncludes('blocked record resolution_id rendered', html, 'RES-WASH-ISO7093-M10');
  check('queue content shown, status cleared', ctx.byId['wrr-queue-content'].style.display === '');
}

// 3. Empty queue
async function testEmptyQueueShowsEmptyState() {
  const ctx = newContext(EXTRACTED, HTML, async () => ({ records: [] }));
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  const expectedMessage = vm.runInContext("t('wrr.empty_state')", ctx.context);
  checkIncludes('empty queue message shown', ctx.byId['wrr-queue-table'].innerHTML, expectedMessage);
  checkNotIncludes('no <table> tag for an empty queue', ctx.byId['wrr-queue-table'].innerHTML, '<table');
}

// 4. API error on queue load
async function testQueueApiErrorShowsSafeMessage() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('network unreachable'); });
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  checkIncludes('queue error message surfaced', ctx.byId['wrr-queue-status'].innerHTML, 'network unreachable');
  checkIncludes('queue error uses alert-danger styling', ctx.byId['wrr-queue-status'].innerHTML, 'alert-danger');
  check('queue content stays hidden on error', ctx.byId['wrr-queue-content'].style.display === 'none');
}

// 5. Malformed queue record is rejected, never partially rendered
async function testMalformedQueueRecordRejected() {
  const ctx = newContext(EXTRACTED, HTML, async () => ({ records: [{ resolution_id: 'X' }] }));
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  checkIncludes('malformed queue shows a clear message', ctx.byId['wrr-queue-status'].innerHTML, 'alert-danger');
  check('malformed queue leaves content hidden', ctx.byId['wrr-queue-content'].style.display === 'none');
}

// 6. Detail endpoint is called with the correct resolution_id
async function testDetailCallsCorrectUrl() {
  let calledPath = null;
  const ctx = newContext(EXTRACTED, HTML, async (p) => { calledPath = p; return fakeDetail(); });
  primeAllElements(ctx.byId);
  await vm.runInContext("wrrLoadResolutionDetail('RES-WASH-DIN127B-M10')", ctx.context);
  check(
    'detail called correct URL',
    calledPath === '/api/library/washers/resolutions/RES-WASH-DIN127B-M10'
  );
}

async function testDetailUrlEncodesResolutionId() {
  let calledPath = null;
  const ctx = newContext(EXTRACTED, HTML, async (p) => { calledPath = p; return fakeDetail(); });
  primeAllElements(ctx.byId);
  await vm.runInContext("wrrLoadResolutionDetail('RES WITH SPACE')", ctx.context);
  check('detail URL encodes the resolution_id', calledPath === '/api/library/washers/resolutions/RES%20WITH%20SPACE');
}

// 7. Detail response renders, only fields present in the response
async function testDetailResponseRenders() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeDetail());
  primeAllElements(ctx.byId);
  await vm.runInContext("wrrLoadResolutionDetail('RES-WASH-DIN127B-M10')", ctx.context);
  const html = ctx.byId['wrr-detail-content'].innerHTML;
  checkIncludes('detail resolution_id rendered', html, 'RES-WASH-DIN127B-M10');
  checkIncludes('detail reason_code rendered', html, 'high_internal_confidence_lacks_external_evidence');
  checkIncludes('detail evidence_reference rendered', html, 'WASH-DIN127B-M10');
  check('detail card shown', ctx.byId['wrr-detail-card'].style.display === '');
  check('detail content shown, status cleared', ctx.byId['wrr-detail-content'].style.display === '');
}

async function testDetailNullFieldsRenderPlaceholderNotBlank() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeDetail({ resolved_standard: null, resolved_by: '', resolved_at: '' }));
  primeAllElements(ctx.byId);
  await vm.runInContext("wrrLoadResolutionDetail('RES-WASH-DIN127B-M10')", ctx.context);
  checkIncludes('null/empty fields render a placeholder, not a guessed value', ctx.byId['wrr-detail-content'].innerHTML, '—');
}

// 8. 404 detail error
async function test404DetailErrorShowsSafeMessage() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('Bilinmeyen resolution_id: RES-DOES-NOT-EXIST'); });
  primeAllElements(ctx.byId);
  await vm.runInContext("wrrLoadResolutionDetail('RES-DOES-NOT-EXIST')", ctx.context);
  checkIncludes('404 message surfaced', ctx.byId['wrr-detail-status'].innerHTML, 'Bilinmeyen resolution_id');
  checkIncludes('404 error uses alert-danger styling', ctx.byId['wrr-detail-status'].innerHTML, 'alert-danger');
  check('detail content stays hidden on 404', ctx.byId['wrr-detail-content'].style.display === 'none');
}

// 9. Blocked record label
async function testBlockedRecordLabeledFromSourceStatus() {
  const records = [fakeBlockedQueueRecord()];
  const ctx = newContext(EXTRACTED, HTML, async () => ({ records }));
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  const expectedYes = vm.runInContext("t('wrr.bool.yes')", ctx.context);
  checkIncludes('blocked record shows the blocked-yes label', ctx.byId['wrr-queue-table'].innerHTML, expectedYes);
  checkIncludes('blocked record uses the badge-prod styling', ctx.byId['wrr-queue-table'].innerHTML, 'badge-prod');
}

// 10. Terminal record label
async function testTerminalRecordLabeledFromEffectiveStatus() {
  const records = [fakeTerminalQueueRecord()];
  const ctx = newContext(EXTRACTED, HTML, async () => ({ records }));
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  const expectedYes = vm.runInContext("t('wrr.bool.yes')", ctx.context);
  checkIncludes('terminal record row includes the terminal-yes label', ctx.byId['wrr-queue-table'].innerHTML, expectedYes);
}

// 11. No decision form, no POST /decide anywhere in this scope
async function testNoDecideCallEverMade() {
  const calledPaths = [];
  const calledMethods = [];
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => {
    calledPaths.push(p);
    calledMethods.push((opts && opts.method) || 'GET');
    if (p.indexOf('/decide') !== -1) throw new Error('POST /decide must never be called by Stage 2');
    if (p.indexOf('/queue') !== -1) return { records: [fakeQueueRecord(), fakeBlockedQueueRecord()] };
    return fakeDetail();
  });
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  await vm.runInContext("wrrLoadResolutionDetail('RES-WASH-DIN127B-M10')", ctx.context);
  check('no call path contains /decide', calledPaths.every((p) => p.indexOf('/decide') === -1));
  check('no POST method used anywhere in this scope', calledMethods.every((m) => m === 'GET'));
  checkNotIncludes(
    'no decision-entry form markup (button/input for new_status) rendered by the queue table',
    ctx.byId['wrr-queue-table'].innerHTML,
    'new_status'
  );
  checkNotIncludes(
    'no decision-entry form markup rendered by the detail view',
    ctx.byId['wrr-detail-content'].innerHTML,
    'new_status'
  );
}

// 12. Detail button present per row, using the real resolution_id
async function testDetailButtonPresentPerRow() {
  const records = [fakeQueueRecord(), fakeBlockedQueueRecord()];
  const ctx = newContext(EXTRACTED, HTML, async () => ({ records }));
  primeAllElements(ctx.byId);
  await vm.runInContext('loadWasherResolutionQueue()', ctx.context);
  const html = ctx.byId['wrr-queue-table'].innerHTML;
  checkIncludes('detail action wired to the open record id', html, "wrrLoadResolutionDetail('RES-WASH-DIN127B-M10')");
  checkIncludes('detail action wired to the blocked record id', html, "wrrLoadResolutionDetail('RES-WASH-ISO7093-M10')");
}

// 13. Report screen sidebar/page markup still present (structural
// smoke check -- full report-behavior regression lives in
// run_washer_resolution_report_tests.js, not duplicated here).
async function testReportPageMarkupStillPresent() {
  check('report page container still present', HTML.indexOf('id="page-washerresolution"') !== -1);
  check('report summary cards container still present', HTML.indexOf('id="wrr-summary-cards"') !== -1);
  check('new queue section container present', HTML.indexOf('id="wrr-queue-table"') !== -1);
  check('new detail section container present', HTML.indexOf('id="wrr-detail-content"') !== -1);
}

// 14. TR/EN parity for the new keys specifically (global parity is
// also covered by tests/test_i18n_key_parity.py; this is a scoped,
// fast sanity check for this stage's own additions).
async function testNewKeysHaveTrAndEnTranslations() {
  const ctx = newContext(EXTRACTED, HTML);
  const newKeys = [
    'wrr.queue.title', 'wrr.queue.subtitle', 'wrr.queue.detail_button',
    'wrr.queue.col.washer_record_id', 'wrr.queue.col.issue_type',
    'wrr.queue.col.source_status', 'wrr.queue.col.is_blocked', 'wrr.queue.col.is_terminal',
    'wrr.detail.title', 'wrr.detail.subtitle', 'wrr.detail.reason_code',
    'wrr.detail.resolution_note', 'wrr.detail.evidence_reference',
    'wrr.detail.resolved_standard', 'wrr.detail.resolved_by', 'wrr.detail.resolved_at',
    'wrr.detail.confidence_level', 'wrr.detail.requires_authoritative_source',
    'wrr.bool.yes', 'wrr.bool.no',
  ];
  for (const key of newKeys) {
    const trValue = vm.runInContext(`I18N['tr'][${JSON.stringify(key)}]`, ctx.context);
    const enValue = vm.runInContext(`I18N['en'][${JSON.stringify(key)}]`, ctx.context);
    check(`TR value present for ${key}`, typeof trValue === 'string' && trValue.length > 0);
    check(`EN value present for ${key}`, typeof enValue === 'string' && enValue.length > 0);
  }
}

const ALL_TESTS = [
  testQueueCallsCorrectUrl,
  testQueueRecordsRender,
  testEmptyQueueShowsEmptyState,
  testQueueApiErrorShowsSafeMessage,
  testMalformedQueueRecordRejected,
  testDetailCallsCorrectUrl,
  testDetailUrlEncodesResolutionId,
  testDetailResponseRenders,
  testDetailNullFieldsRenderPlaceholderNotBlank,
  test404DetailErrorShowsSafeMessage,
  testBlockedRecordLabeledFromSourceStatus,
  testTerminalRecordLabeledFromEffectiveStatus,
  testNoDecideCallEverMade,
  testDetailButtonPresentPerRow,
  testReportPageMarkupStillPresent,
  testNewKeysHaveTrAndEnTranslations,
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
