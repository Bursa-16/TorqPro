#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.11 Stage 4 -- Engineering Governance Workspace frontend
 * regression harness.
 *
 * Zero external dependencies, same technique as
 * tests/js/run_washer_resolution_report_tests.js: Node's built-in
 * `vm` module runs the *actual* governance workspace declarations
 * extracted live from frontend/index.html (never a committed copy)
 * against a small hand-built DOM stub, with a fake `apiRequest`
 * injected per scenario (this workspace calls `apiRequest` directly,
 * the same shared utility every other page already uses -- no
 * `fetch` stub is needed).
 *
 * Invoked via `node tests/js/run_governance_workspace_tests.js` from
 * the repo root, or indirectly via
 * tests/test_faz_2_8_11_stage4_frontend.py.
 * Exit code 0 = all assertions passed; non-zero = at least one
 * failure.
 */
const path = require('path');
const vm = require('vm');

const {
  extractScript,
  extractConstDecl,
  extractFunctionDecl,
  toVarDecl,
  makeElement,
  buildDom: buildDomShared,
  createChecker,
} = require('./harness_common');
const fs = require('fs');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND_PATH = path.join(REPO_ROOT, 'frontend', 'index.html');

const CONST_NAMES = ['I18N', 'CURRENT_LANG', 'GOV_ACTIONS', 'GOV_LAST_HISTORY', 'GOV_LAST_STATUS', 'GOV_LAST_ERROR'];
const MUTABLE_STATE_NAMES = ['GOV_LAST_HISTORY', 'GOV_LAST_STATUS', 'GOV_LAST_ERROR'];
const FUNCTION_NAMES = [
  't', 'applyStaticTranslations', 'setLanguage',
  'govEsc', 'govGroupLabel', 'govStatusLabel', 'govActionLabel',
  'govPopulateActionSelect', 'govOnActionChange',
  'govIsWellFormedHistory', 'govIsWellFormedStatus',
  'govRenderLoading', 'govRenderEmpty', 'govRenderError',
  'govRenderStatus', 'govRenderHistory',
  'govInit', 'govClassifyError', 'govLoad', 'govSubmitCommand',
  'govReapplyLanguage',
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
  parts.push('function __getGovLastHistory() { return GOV_LAST_HISTORY; }');
  parts.push('function __getGovLastStatus() { return GOV_LAST_STATUS; }');
  return { source: parts.join('\n\n'), rawScript: script, rawHtml: html };
}

const { check, checkIncludes, checkNotIncludes, recordFailure, summary } = createChecker();

function buildDom(rawHtml, byId) {
  return buildDomShared(rawHtml, byId, { includePlaceholders: true });
}

function newContext(extractedSource, rawHtml, apiRequestImpl, activePageId) {
  const byId = {};
  const documentStub = buildDom(rawHtml, byId);
  if (activePageId) {
    documentStub.getElementById('page-' + activePageId).classList.add('active');
  }
  const calls = [];
  const wrappedApiRequest = apiRequestImpl
    ? async (pathArg, options) => { calls.push({ path: pathArg, options: options || {} }); return apiRequestImpl(pathArg, options); }
    : (() => { throw new Error('apiRequest should not be called by this test'); });
  const sandbox = {
    document: documentStub,
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    console: console,
    apiRequest: wrappedApiRequest,
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'gov_extracted.js' });
  return { context, byId, documentStub, calls };
}

function primeGovElements(byId) {
  [
    'gov_aggregate_id', 'gov_aggregate_type', 'gov-status-message', 'gov-content',
    'gov-status-cards', 'gov-history-list', 'gov_action', 'gov_decision_id',
    'gov_idempotency_key', 'gov_occurred_at', 'gov_metadata', 'gov_superseded_by_id',
    'gov-superseded-by-group', 'gov-command-result',
  ].forEach((id) => { byId[id] = makeElement(id); });
}

function fakeEvent(overrides) {
  const base = {
    event_id: 'e1', aggregate_id: 'agg-1', aggregate_type: 'calc_revision',
    lifecycle_group: 'review', previous_status: 'draft', new_status: 'under_review',
    decision_id: 'd1', idempotency_key: 'k1', actor: 'ilhan',
    occurred_at: '2026-07-30T10:00:00Z', review_comment: null, change_reason: null,
    revision_no: null, supersedes_id: null, superseded_by_id: null, metadata: {},
  };
  return Object.assign({}, base, overrides);
}

function fakeHistory(overrides) {
  const base = {
    aggregate_id: 'agg-1', aggregate_type: 'calc_revision',
    events: [fakeEvent()], total_events: 1,
  };
  return Object.assign({}, base, overrides);
}

function fakeStatus(overrides) {
  const base = {
    aggregate_id: 'agg-1', aggregate_type: 'calc_revision',
    status: { review: 'under_review', publication: null, resolution: null },
    latest_events: { review: fakeEvent(), publication: null, resolution: null },
  };
  return Object.assign({}, base, overrides);
}

// =================================================================
const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// ---------------------------------------------------------------
// Test scenarios. Every scenario is an `async function` and every
// call site in ALL_TESTS is `await`-ed inside main()'s loop -- see
// the Faz 2.8.8 defect note in run_washer_resolution_report_tests.js
// for why this matters: an un-awaited async scenario would let the
// final summary print before its check() calls ever ran, silently
// hiding real failures behind a "clean" result.
// ---------------------------------------------------------------

// 1 & 2. Sidebar / page markup presence, correct navigation target
async function testSidebarAndPageMarkupPresent() {
  check('sidebar item present', HTML.indexOf("showPage('governance')") !== -1);
  check('page container present', HTML.indexOf('id="page-governance"') !== -1);
  const pageMatches = HTML.match(/id="page-governance"/g) || [];
  check('page container appears exactly once', pageMatches.length === 1);
}

// 3-6. Required functions exist in the extracted, real source
async function testRequiredFunctionsExist() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  for (const fn of ['govInit', 'govLoad', 'govSubmitCommand', 'govReapplyLanguage', 'govRenderStatus', 'govRenderHistory', 'govRenderError', 'govRenderLoading', 'govRenderEmpty']) {
    check(fn + ' is a function in the extracted source', vm.runInContext('typeof ' + fn, ctx.context) === 'function');
  }
}

// 7 & 8. apiRequest is used; aggregate_id/aggregate_type sent correctly
async function testGovLoadUsesApiRequestWithCorrectParams() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory(), 'governance');
  primeGovElements(ctx.byId);
  ctx.byId['gov_aggregate_id'].value = 'agg-42';
  ctx.byId['gov_aggregate_type'].value = 'joint_revision';
  await vm.runInContext('govLoad()', ctx.context);
  check('exactly two apiRequest calls (history + status)', ctx.calls.length === 2);
  check('history call path includes aggregate_id', ctx.calls[0].path.indexOf('agg-42') !== -1);
  check('history call includes aggregate_type query param', ctx.calls[0].path.indexOf('aggregate_type=joint_revision') !== -1);
  check('status call path includes aggregate_id', ctx.calls[1].path.indexOf('agg-42') !== -1);
}

// 9. Status response renders three lifecycle groups separately
async function testStatusRendersThreeGroupsSeparately() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  primeGovElements(ctx.byId);
  const status = fakeStatus({
    status: { review: 'approved', publication: 'active', resolution: 'waived' },
  });
  vm.runInContext('govRenderStatus(' + JSON.stringify(status) + ')', ctx.context);
  const html = ctx.byId['gov-status-cards'].innerHTML;
  checkIncludes('review status rendered', html, 'approved');
  checkIncludes('publication status rendered', html, 'active');
  checkIncludes('resolution status rendered', html, 'waived');
  const reviewLabel = vm.runInContext("t('gov.group.review')", ctx.context);
  const pubLabel = vm.runInContext("t('gov.group.publication')", ctx.context);
  const resLabel = vm.runInContext("t('gov.group.resolution')", ctx.context);
  checkIncludes('review group label rendered', html, reviewLabel);
  checkIncludes('publication group label rendered', html, pubLabel);
  checkIncludes('resolution group label rendered', html, resLabel);
}

// 10. History response renders events
async function testHistoryRendersEvents() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  primeGovElements(ctx.byId);
  const history = fakeHistory({ events: [fakeEvent({ event_id: 'evt-99', actor: 'ilhan cekic' })], total_events: 1 });
  vm.runInContext('govRenderHistory(' + JSON.stringify(history) + ')', ctx.context);
  checkIncludes('event id rendered', ctx.byId['gov-history-list'].innerHTML, 'evt-99');
  checkIncludes('actor rendered', ctx.byId['gov-history-list'].innerHTML, 'ilhan cekic');
}

// 11. Empty history renders the translated empty state
async function testEmptyHistoryRendersTranslatedEmptyState() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  primeGovElements(ctx.byId);
  const history = fakeHistory({ events: [], total_events: 0 });
  vm.runInContext('govRenderHistory(' + JSON.stringify(history) + ')', ctx.context);
  const expected = vm.runInContext("t('gov.history_empty')", ctx.context);
  checkIncludes('translated empty-history message shown', ctx.byId['gov-history-list'].innerHTML, expected);
  checkNotIncludes('no <table> tag when there are no events', ctx.byId['gov-history-list'].innerHTML, '<table');
}

// 12. Loading state renders
async function testLoadingStateRenders() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  primeGovElements(ctx.byId);
  vm.runInContext('govRenderLoading()', ctx.context);
  const expected = vm.runInContext("t('gov.loading')", ctx.context);
  check('loading message shown', ctx.byId['gov-status-message'].textContent === expected);
  check('content hidden while loading', ctx.byId['gov-content'].style.display === 'none');
}

// 13. Successful command state renders
async function testSuccessfulCommandRenders() {
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => {
    if (p.indexOf('/submit') !== -1) return { result: 'created', idempotent: false, event: fakeEvent() };
    return fakeHistory();
  }, 'governance');
  primeGovElements(ctx.byId);
  ctx.byId['gov_aggregate_id'].value = 'agg-1';
  ctx.byId['gov_aggregate_type'].value = 'calc_revision';
  ctx.byId['gov_action'].value = 'review_submit';
  ctx.byId['gov_decision_id'].value = 'd1';
  ctx.byId['gov_idempotency_key'].value = 'k1';
  ctx.byId['gov_occurred_at'].value = '2026-07-30T10:00:00Z';
  await vm.runInContext('govSubmitCommand()', ctx.context);
  const expected = vm.runInContext("t('gov.result_created')", ctx.context);
  checkIncludes('created result message shown', ctx.byId['gov-command-result'].innerHTML, expected);
}

// 14. Validation error renders safely
async function testValidationErrorRendersSafely() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('Geçersiz istek alanı (ör. occurred_at biçimi).'); }, 'governance');
  primeGovElements(ctx.byId);
  ctx.byId['gov_aggregate_id'].value = 'agg-1';
  ctx.byId['gov_aggregate_type'].value = 'calc_revision';
  await vm.runInContext('govLoad()', ctx.context);
  const prefix = vm.runInContext("t('gov.validation_error_prefix')", ctx.context);
  checkIncludes('validation error prefix shown', ctx.byId['gov-status-message'].textContent, prefix);
  checkNotIncludes('no stack trace leaked', ctx.byId['gov-status-message'].textContent, '\n    at ');
}

// 15. Conflict error renders safely
async function testConflictErrorRendersSafely() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error("idempotency_key 'k1' was already used for a different request."); }, 'governance');
  primeGovElements(ctx.byId);
  ctx.byId['gov_aggregate_id'].value = 'agg-1';
  ctx.byId['gov_aggregate_type'].value = 'calc_revision';
  await vm.runInContext('govLoad()', ctx.context);
  const prefix = vm.runInContext("t('gov.conflict_error_prefix')", ctx.context);
  checkIncludes('conflict error prefix shown', ctx.byId['gov-status-message'].textContent, prefix);
}

// 16. Authentication/API error renders safely
async function testAuthErrorRendersSafely() {
  const ctx = newContext(EXTRACTED, HTML, async () => { throw new Error('Oturum gerekli'); }, 'governance');
  primeGovElements(ctx.byId);
  ctx.byId['gov_aggregate_id'].value = 'agg-1';
  ctx.byId['gov_aggregate_type'].value = 'calc_revision';
  await vm.runInContext('govLoad()', ctx.context);
  const expected = vm.runInContext("t('gov.auth_error')", ctx.context);
  check('auth error message shown', ctx.byId['gov-status-message'].textContent === expected);
}

// 17. Malformed status response is rejected
async function testMalformedStatusRejected() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  primeGovElements(ctx.byId);
  vm.runInContext('govRenderStatus({aggregate_id: "agg-1"})', ctx.context);
  const expected = vm.runInContext("t('gov.malformed_response')", ctx.context);
  check('malformed status message shown', ctx.byId['gov-status-message'].textContent === expected);
  check('GOV_LAST_STATUS not set on malformed response', vm.runInContext('__getGovLastStatus()', ctx.context) === null);
}

// 18. Malformed history response is rejected
async function testMalformedHistoryRejected() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  primeGovElements(ctx.byId);
  vm.runInContext('govRenderHistory({aggregate_id: "agg-1", events: "not-an-array"})', ctx.context);
  const expected = vm.runInContext("t('gov.malformed_response')", ctx.context);
  check('malformed history message shown', ctx.byId['gov-status-message'].textContent === expected);
  check('GOV_LAST_HISTORY not set on malformed response', vm.runInContext('__getGovLastHistory()', ctx.context) === null);
}

// 19. All nine command actions are represented
async function testAllNineActionsRepresented() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  const actions = vm.runInContext('GOV_ACTIONS.map(a => a.value)', ctx.context);
  const expected = [
    'review_submit', 'review_approve', 'review_reject',
    'publication_activate', 'publication_supersede', 'publication_archive',
    'resolution_resolve', 'resolution_reject', 'resolution_waive',
  ];
  check('exactly nine actions defined', actions.length === 9);
  for (const a of expected) {
    check('action present: ' + a, actions.indexOf(a) !== -1);
  }
}

// 20. Supersede lineage field appears only for supersede
async function testSupersedeFieldOnlyForSupersedeAction() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory());
  primeGovElements(ctx.byId);
  ctx.byId['gov_action'].value = 'publication_supersede';
  vm.runInContext('govOnActionChange()', ctx.context);
  check('supersede field shown for supersede action', ctx.byId['gov-superseded-by-group'].style.display === '');
  ctx.byId['gov_action'].value = 'review_submit';
  vm.runInContext('govOnActionChange()', ctx.context);
  check('supersede field hidden for non-supersede action', ctx.byId['gov-superseded-by-group'].style.display === 'none');
}

// 21 & 22. actor and previous_status are never sent
async function testActorAndPreviousStatusNeverSent() {
  const ctx = newContext(EXTRACTED, HTML, async (p, opts) => {
    if (p.indexOf('/submit') !== -1) return { result: 'created', idempotent: false, event: fakeEvent() };
    return fakeHistory();
  }, 'governance');
  primeGovElements(ctx.byId);
  ctx.byId['gov_aggregate_id'].value = 'agg-1';
  ctx.byId['gov_aggregate_type'].value = 'calc_revision';
  ctx.byId['gov_action'].value = 'review_submit';
  ctx.byId['gov_decision_id'].value = 'd1';
  ctx.byId['gov_idempotency_key'].value = 'k1';
  ctx.byId['gov_occurred_at'].value = '2026-07-30T10:00:00Z';
  await vm.runInContext('govSubmitCommand()', ctx.context);
  const submitCall = ctx.calls.find((c) => c.path.indexOf('/submit') !== -1);
  check('a submit call was made', !!submitCall);
  if (submitCall) {
    const body = JSON.parse(submitCall.options.body);
    check('request body does not include actor', !('actor' in body));
    check('request body does not include previous_status', !('previous_status' in body));
  }
  check('extracted source never references a gov_actor element', EXTRACTED.indexOf('gov_actor') === -1);
  check('extracted source never references a gov_previous_status element', EXTRACTED.indexOf('gov_previous_status') === -1);
}

// 23. Language switch reapplies governance labels
async function testLanguageSwitchReappliesGovernanceLabels() {
  const ctx = newContext(EXTRACTED, HTML, async () => fakeHistory(), 'governance');
  primeGovElements(ctx.byId);
  vm.runInContext('govRenderStatus(' + JSON.stringify(fakeStatus()) + ')', ctx.context);
  const trHtml = ctx.byId['gov-status-cards'].innerHTML;
  vm.runInContext("setLanguage('en')", ctx.context);
  const enHtml = ctx.byId['gov-status-cards'].innerHTML;
  const enReviewLabel = vm.runInContext("t('gov.group.review')", ctx.context);
  checkIncludes('status cards re-rendered in the new language', enHtml, enReviewLabel);
  check('re-rendered output actually changed language content', trHtml !== enHtml || enReviewLabel === 'Review');
}

// 24. Async assertions are genuinely awaited (structural self-check --
// every async scenario above is invoked with `await` inside main()'s
// loop; this scenario additionally proves a call count only reflects
// reality *after* awaiting, not before).
async function testAsyncCallsAreGenuinelyAwaited() {
  let resolved = false;
  const ctx = newContext(EXTRACTED, HTML, async () => {
    await new Promise((resolve) => setImmediate(resolve));
    resolved = true;
    return fakeHistory();
  }, 'governance');
  primeGovElements(ctx.byId);
  ctx.byId['gov_aggregate_id'].value = 'agg-1';
  ctx.byId['gov_aggregate_type'].value = 'calc_revision';
  const promise = vm.runInContext('govLoad()', ctx.context);
  check('apiRequest promise not yet resolved synchronously', resolved === false);
  await promise;
  check('apiRequest promise resolved after awaiting govLoad()', resolved === true);
}

const ALL_TESTS = [
  testSidebarAndPageMarkupPresent,
  testRequiredFunctionsExist,
  testGovLoadUsesApiRequestWithCorrectParams,
  testStatusRendersThreeGroupsSeparately,
  testHistoryRendersEvents,
  testEmptyHistoryRendersTranslatedEmptyState,
  testLoadingStateRenders,
  testSuccessfulCommandRenders,
  testValidationErrorRendersSafely,
  testConflictErrorRendersSafely,
  testAuthErrorRendersSafely,
  testMalformedStatusRejected,
  testMalformedHistoryRejected,
  testAllNineActionsRepresented,
  testSupersedeFieldOnlyForSupersedeAction,
  testActorAndPreviousStatusNeverSent,
  testLanguageSwitchReappliesGovernanceLabels,
  testAsyncCallsAreGenuinelyAwaited,
];

// =================================================================
async function main() {
  // setup
  // (EXTRACTED/HTML built at module load above; nothing further to
  // set up before running scenarios)

  // synchronous + asynchronous checks -- every scenario is awaited
  for (const testFn of ALL_TESTS) {
    try {
      await testFn();
    } catch (err) {
      const label = testFn.name + ' (threw)';
      recordFailure(label);
      console.log('FAIL: ' + label + ' -- ' + (err && err.stack ? err.stack : String(err)));
    }
  }

  // print totals only after all promises settle
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
