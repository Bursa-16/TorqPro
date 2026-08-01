#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.16 Stage 4 -- Joint Revision List search/sort/pagination/
 * CSV-export frontend regression harness.
 *
 * Same technique as tests/js/run_governance_workspace_tests.js and
 * the other harnesses built on tests/js/harness_common.js: Node's
 * built-in `vm` module runs the *actual* Stage 4 declarations
 * extracted live from frontend/index.html (never a committed copy)
 * against a small hand-built DOM/fetch/URL stub. Kept as its own,
 * dedicated file (rather than added to
 * run_governance_workspace_tests.js) so Stage 4's search/sort/
 * pagination/export behaviour stays isolated and readable, per the
 * Stage 4 scope decision -- that existing harness was only touched
 * to let its own already-tracked govReapplyLanguage()/govInit()
 * extraction succeed (see its CONST_NAMES/FUNCTION_NAMES additions),
 * not to grow its own scenario list.
 *
 * No real network call, no real browser, no external test framework
 * -- pure Node + `vm`. Exit code 0 = all assertions passed; non-zero
 * = at least one failure.
 *
 * Invoked via `node tests/js/run_joint_revision_list_ux_tests.js`
 * from the repo root.
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

const CONST_NAMES = [
  'I18N', 'CURRENT_LANG', 'GOV_JR_OUTCOMES',
  'GOV_JRLIST_QUERY_SORT_FIELDS', 'GOV_JRLIST_QUERY_SORT_ORDERS',
  'govJointRevisionListState', 'GOV_JRLIST_QUERY_REQUEST_ID',
];
const MUTABLE_STATE_NAMES = ['GOV_JRLIST_QUERY_REQUEST_ID'];
const FUNCTION_NAMES = [
  't',
  'govEsc', 'govGroupLabel', 'govStatusLabel', 'govJrOutcomeLabel',
  'govIsWellFormedJointRevisionListItem',
  'govJointRevisionQueryJointId',
  'govJointRevisionListBuildQueryUrl', 'govJointRevisionListBuildExportUrl',
  'govIsWellFormedJointRevisionQueryEnvelope',
  'govJointRevisionQueryPageLabel',
  'govRenderJointRevisionQueryControlsState', 'govRenderJointRevisionQueryResult',
  'govLoadJointRevisionsQuery',
  'govJointRevisionQuerySearch', 'govJointRevisionQueryClearSearch',
  'govJointRevisionQuerySortChange', 'govJointRevisionQueryOrderChange',
  'govJointRevisionQueryPageSizeChange',
  'govJointRevisionQueryPrevPage', 'govJointRevisionQueryNextPage',
  'govJointRevisionQueryExportCsv',
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
  parts.push('function __getState() { return govJointRevisionListState; }');
  return { source: parts.join('\n\n'), rawScript: script, rawHtml: html };
}

const { check, checkIncludes, checkNotIncludes, recordFailure, summary } = createChecker();

const JRLIST_IDS = [
  'gov_jrlist_joint_id', 'gov_jrlist_query_search',
  'gov_jrlist_query_sort_by', 'gov_jrlist_query_sort_order', 'gov_jrlist_query_page_size',
  'gov_jrlist_query_search_btn', 'gov_jrlist_query_clear_btn', 'gov_jrlist_query_export_btn',
  'gov-jrlist-query-result',
];

function buildDom(rawHtml, byId) {
  const stub = buildDomShared(rawHtml, byId, { includePlaceholders: true });
  const appended = [];
  const created = [];
  stub.body = {
    appendChild(el) { appended.push(el); },
  };
  stub.createElement = () => {
    const calls = { clicked: false, removed: false };
    const anchor = {
      href: '', download: '',
      click() { calls.clicked = true; },
      remove() { calls.removed = true; },
      _calls: calls,
    };
    created.push(anchor);
    return anchor;
  };
  stub.__appended = appended;
  stub.__created = created;
  return stub;
}

function newContext(extractedSource, rawHtml, opts) {
  opts = opts || {};
  const byId = {};
  JRLIST_IDS.forEach((id) => { byId[id] = makeElement(id); });
  const documentStub = buildDom(rawHtml, byId);

  const apiCalls = [];
  const wrappedApiRequest = async (pathArg, options) => {
    apiCalls.push({ path: pathArg, options: options || {} });
    if (opts.apiRequestImpl) return opts.apiRequestImpl(pathArg, options);
    throw new Error('apiRequest should not be called by this test');
  };

  const fetchCalls = [];
  const wrappedFetch = async (url, options) => {
    fetchCalls.push({ url, options: options || {} });
    if (opts.fetchImpl) return opts.fetchImpl(url, options);
    throw new Error('fetch should not be called by this test');
  };

  const urlCalls = { created: [], revoked: [] };
  const URLMock = {
    createObjectURL(blob) {
      const u = 'blob:mock-' + urlCalls.created.length;
      urlCalls.created.push({ blob, url: u });
      return u;
    },
    revokeObjectURL(u) { urlCalls.revoked.push(u); },
  };

  const sandbox = {
    document: documentStub,
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    console: console,
    apiRequest: wrappedApiRequest,
    fetch: wrappedFetch,
    URL: URLMock,
    URLSearchParams: URLSearchParams,
    AUTH_TOKEN: 'fake-token-abc',
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'jrlist_ux_extracted.js' });
  return { context, byId, documentStub, apiCalls, fetchCalls, urlCalls };
}

function resetState(ctx) {
  vm.runInContext(
    "govJointRevisionListState.search=''; govJointRevisionListState.sortBy='joint_revision_id';"
    + "govJointRevisionListState.sortOrder='asc'; govJointRevisionListState.page=1;"
    + "govJointRevisionListState.pageSize=25; govJointRevisionListState.total=0;"
    + "govJointRevisionListState.totalPages=0; govJointRevisionListState.items=[];"
    + "govJointRevisionListState.loading=false; govJointRevisionListState.error=null;",
    ctx.context,
  );
}

function fakeItem(overrides) {
  const base = {
    source_system: 'joint_revision', joint_revision_id: 1, source_status: 'draft',
    lifecycle_group: 'review', canonical_status: 'draft', outcome: 'supported',
    safe_reason: null,
  };
  return Object.assign({}, base, overrides);
}

function fakeEnvelope(overrides) {
  const base = { items: [fakeItem()], total: 1, page: 1, page_size: 25, total_pages: 1 };
  return Object.assign({}, base, overrides);
}

const { source: EXTRACTED, rawHtml: HTML } = buildExtractedSource();

// =================================================================
// State defaults
// =================================================================

async function testStateDefaults() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('default search is empty string', state.search === '');
  check('default sortBy is joint_revision_id', state.sortBy === 'joint_revision_id');
  check('default sortOrder is asc', state.sortOrder === 'asc');
  check('default page is 1', state.page === 1);
  check('default pageSize is 25', state.pageSize === 25);
  check('default total is 0', state.total === 0);
  check('default totalPages is 0', state.totalPages === 0);
  check('default loading is false', state.loading === false);
  check('default error is null', state.error === null);
  check('default items is an empty array', Array.isArray(state.items) && state.items.length === 0);
}

// =================================================================
// Query URL builder
// =================================================================

async function testQueryUrlBuilderDefault() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  const url = vm.runInContext('govJointRevisionListBuildQueryUrl()', ctx.context);
  check('default query URL uses the query endpoint', url.indexOf('/api/governance/joint-revisions/query?') === 0);
  check('default query URL has sort_by=joint_revision_id', url.indexOf('sort_by=joint_revision_id') !== -1);
  check('default query URL has sort_order=asc', url.indexOf('sort_order=asc') !== -1);
  check('default query URL has page=1', url.indexOf('page=1') !== -1);
  check('default query URL has page_size=25', url.indexOf('page_size=25') !== -1);
  check('default query URL has no search param', url.indexOf('search=') === -1);
  check('default query URL has no joint_id param', url.indexOf('joint_id=') === -1);
}

async function testQueryUrlBuilderSearchAndEncoding() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext("govJointRevisionListState.search = 'approved status';", ctx.context);
  const url = vm.runInContext('govJointRevisionListBuildQueryUrl()', ctx.context);
  check('search parameter present', url.indexOf('search=') !== -1);
  check('search is URL-encoded (space becomes +)', url.indexOf('search=approved+status') !== -1);
}

async function testQueryUrlBuilderSortAndOrder() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext("govJointRevisionListState.sortBy = 'outcome'; govJointRevisionListState.sortOrder = 'desc';", ctx.context);
  const url = vm.runInContext('govJointRevisionListBuildQueryUrl()', ctx.context);
  check('sort_by reflects state', url.indexOf('sort_by=outcome') !== -1);
  check('sort_order reflects state', url.indexOf('sort_order=desc') !== -1);
}

async function testQueryUrlBuilderJointId() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  ctx.byId['gov_jrlist_joint_id'].value = '42';
  const url = vm.runInContext('govJointRevisionListBuildQueryUrl()', ctx.context);
  check('joint_id parameter added when input has a value', url.indexOf('joint_id=42') !== -1);
}

async function testQueryUrlBuilderNoJointIdWhenEmpty() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  ctx.byId['gov_jrlist_joint_id'].value = '';
  const url = vm.runInContext('govJointRevisionListBuildQueryUrl()', ctx.context);
  check('joint_id omitted (not sent as empty string) when input is empty', url.indexOf('joint_id=') === -1);
}

async function testQueryUrlBuilderWhitespaceSearchTrimmedAtSearchTime() {
  // Whitespace-only search is trimmed to '' by govJointRevisionQuerySearch()
  // *before* it reaches state.search -- the builder itself only ever
  // sees an already-trimmed value, matching backend semantics (empty
  // means "no filter").
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  ctx.byId['gov_jrlist_query_search'].value = '   ';
  vm.runInContext('govJointRevisionQuerySearch()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('whitespace-only search is trimmed to empty string in state', state.search === '');
}

async function testQueryUrlBuilderPageAndPageSizeAreNumeric() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext("govJointRevisionListState.page = 3; govJointRevisionListState.pageSize = 50;", ctx.context);
  const url = vm.runInContext('govJointRevisionListBuildQueryUrl()', ctx.context);
  check('page=3 present as plain number text', url.indexOf('page=3') !== -1);
  check('page_size=50 present as plain number text', url.indexOf('page_size=50') !== -1);
}

// =================================================================
// Export URL builder
// =================================================================

async function testExportUrlBuilderDefault() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  const url = vm.runInContext('govJointRevisionListBuildExportUrl()', ctx.context);
  check('export URL uses the export endpoint', url.indexOf('/api/governance/joint-revisions/export.csv?') === 0);
  check('export URL has sort_by', url.indexOf('sort_by=joint_revision_id') !== -1);
  check('export URL has sort_order', url.indexOf('sort_order=asc') !== -1);
  check('export URL has no page param', /(^|[?&])page=/.test(url) === false);
  check('export URL has no page_size param', url.indexOf('page_size=') === -1);
}

async function testExportUrlBuilderSearchSortJointId() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext("govJointRevisionListState.search = 'my term'; govJointRevisionListState.sortBy = 'canonical_status'; govJointRevisionListState.sortOrder = 'desc';", ctx.context);
  ctx.byId['gov_jrlist_joint_id'].value = '7';
  const url = vm.runInContext('govJointRevisionListBuildExportUrl()', ctx.context);
  check('export URL includes search', url.indexOf('search=my+term') !== -1);
  check('export URL includes sort_by', url.indexOf('sort_by=canonical_status') !== -1);
  check('export URL includes sort_order', url.indexOf('sort_order=desc') !== -1);
  check('export URL includes joint_id', url.indexOf('joint_id=7') !== -1);
}

// =================================================================
// State transitions
// =================================================================

async function testSearchResetsPageTo1() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 4;', ctx.context);
  ctx.byId['gov_jrlist_query_search'].value = 'approved';
  await vm.runInContext('govJointRevisionQuerySearch()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('search sets state.search from input', state.search === 'approved');
  check('search resets page to 1', state.page === 1);
}

async function testClearResetsSearchAndPage() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  vm.runInContext("govJointRevisionListState.search = 'old'; govJointRevisionListState.page = 3;", ctx.context);
  ctx.byId['gov_jrlist_query_search'].value = 'old';
  await vm.runInContext('govJointRevisionQueryClearSearch()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('clear empties state.search', state.search === '');
  check('clear resets page to 1', state.page === 1);
  check('clear empties the search input element', ctx.byId['gov_jrlist_query_search'].value === '');
}

async function testSortFieldChangeResetsPage() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 2;', ctx.context);
  ctx.byId['gov_jrlist_query_sort_by'].value = 'outcome';
  await vm.runInContext('govJointRevisionQuerySortChange()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('sort field change updates sortBy', state.sortBy === 'outcome');
  check('sort field change resets page to 1', state.page === 1);
}

async function testSortOrderChangeResetsPage() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 2;', ctx.context);
  ctx.byId['gov_jrlist_query_sort_order'].value = 'desc';
  await vm.runInContext('govJointRevisionQueryOrderChange()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('sort order change updates sortOrder', state.sortOrder === 'desc');
  check('sort order change resets page to 1', state.page === 1);
}

async function testPageSizeChangeResetsPage() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 2;', ctx.context);
  ctx.byId['gov_jrlist_query_page_size'].value = '100';
  await vm.runInContext('govJointRevisionQueryPageSizeChange()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('page size change updates pageSize', state.pageSize === 100);
  check('page size change resets page to 1', state.page === 1);
}

async function testNextPageIncrements() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope({ page: 2, total_pages: 5 }) });
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 1; govJointRevisionListState.totalPages = 5;', ctx.context);
  await vm.runInContext('govJointRevisionQueryNextPage()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('next page increments page', state.page === 2);
}

async function testPrevPageDecrements() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope({ page: 1, total_pages: 5 }) });
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 2; govJointRevisionListState.totalPages = 5;', ctx.context);
  await vm.runInContext('govJointRevisionQueryPrevPage()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('previous page decrements page', state.page === 1);
}

async function testPrevPageNoOpAtPage1() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 1; govJointRevisionListState.totalPages = 5;', ctx.context);
  await vm.runInContext('govJointRevisionQueryPrevPage()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('previous page is a no-op at page 1 (no apiRequest call)', ctx.apiCalls.length === 0 && state.page === 1);
}

async function testNextPageNoOpAtLastPage() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 5; govJointRevisionListState.totalPages = 5;', ctx.context);
  await vm.runInContext('govJointRevisionQueryNextPage()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('next page is a no-op at the last page (no apiRequest call)', ctx.apiCalls.length === 0 && state.page === 5);
}

async function testPrevAndNextNoOpWhenTotalPagesZero() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.page = 1; govJointRevisionListState.totalPages = 0;', ctx.context);
  await vm.runInContext('govJointRevisionQueryNextPage()', ctx.context);
  await vm.runInContext('govJointRevisionQueryPrevPage()', ctx.context);
  check('neither prev nor next call apiRequest when total_pages is 0', ctx.apiCalls.length === 0);
}

// =================================================================
// Response validation
// =================================================================

async function testValidEnvelopeAccepted() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const ok = vm.runInContext(
    'govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(fakeEnvelope()) + ')',
    ctx.context,
  );
  check('a well-formed envelope is accepted', ok === true);
}

async function testMissingItemsRejected() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const body = fakeEnvelope(); delete body.items;
  const ok = vm.runInContext('govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(body) + ')', ctx.context);
  check('missing items is rejected', ok === false);
}

async function testItemsNotArrayRejected() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const body = fakeEnvelope({ items: 'not-an-array' });
  const ok = vm.runInContext('govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(body) + ')', ctx.context);
  check('non-array items is rejected', ok === false);
}

async function testMissingTotalRejected() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const body = fakeEnvelope(); delete body.total;
  const ok = vm.runInContext('govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(body) + ')', ctx.context);
  check('missing total is rejected', ok === false);
}

async function testMissingPageRejected() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const body = fakeEnvelope(); delete body.page;
  const ok = vm.runInContext('govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(body) + ')', ctx.context);
  check('missing page is rejected', ok === false);
}

async function testMissingPageSizeRejected() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const body = fakeEnvelope(); delete body.page_size;
  const ok = vm.runInContext('govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(body) + ')', ctx.context);
  check('missing page_size is rejected', ok === false);
}

async function testMissingTotalPagesRejected() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const body = fakeEnvelope(); delete body.total_pages;
  const ok = vm.runInContext('govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(body) + ')', ctx.context);
  check('missing total_pages is rejected', ok === false);
}

async function testNonIntegerMetadataRejected() {
  const ctx = newContext(EXTRACTED, HTML, {});
  const body = fakeEnvelope({ total: 1.5 });
  const ok = vm.runInContext('govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(body) + ')', ctx.context);
  check('non-integer total is rejected', ok === false);
}

async function testNegativeMetadataBehaviourMatchesImplementation() {
  // Number.isInteger(-1) === true -- the shape guard only checks
  // "is this an integer", not "is it non-negative" (the backend is
  // the source of truth for range validation, matching the Stage 4
  // "no second independent business rule" contract). Documented here
  // so the guard's exact, implemented behaviour is pinned by a test.
  const ctx = newContext(EXTRACTED, HTML, {});
  const body = fakeEnvelope({ total: -1 });
  const ok = vm.runInContext('govIsWellFormedJointRevisionQueryEnvelope(' + JSON.stringify(body) + ')', ctx.context);
  check('negative integer metadata is accepted by the shape guard (range checking is the backend\'s job)', ok === true);
}

async function testInvalidResponseProducesSafeErrorState() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => ({ items: 'nope' }) });
  resetState(ctx);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('invalid envelope shape produces a non-null error', state.error !== null);
  check('invalid envelope shape leaves loading false', state.loading === false);
}

// =================================================================
// Query lifecycle
// =================================================================

async function testLoadCallsCorrectEndpoint() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  check('exactly one apiRequest call', ctx.apiCalls.length === 1);
  check('called endpoint is the query endpoint', ctx.apiCalls[0].path.indexOf('/api/governance/joint-revisions/query') === 0);
}

async function testLoadingTrueBeforeRequestResolvesThenFalseAfter() {
  let sawLoadingDuringCall = false;
  const ctx = newContext(EXTRACTED, HTML, {
    apiRequestImpl: async () => {
      sawLoadingDuringCall = vm.runInContext('govJointRevisionListState.loading', ctx.context);
      return fakeEnvelope();
    },
  });
  resetState(ctx);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  check('loading is true while the request is in flight', sawLoadingDuringCall === true);
  check('loading is false after a successful response', vm.runInContext('govJointRevisionListState.loading', ctx.context) === false);
}

async function testSuccessfulResponseWritesItemsAndMetadataToState() {
  const items = [fakeItem({ joint_revision_id: 5 }), fakeItem({ joint_revision_id: 9 })];
  const ctx = newContext(EXTRACTED, HTML, {
    apiRequestImpl: async () => fakeEnvelope({ items, total: 2, page: 1, page_size: 25, total_pages: 1 }),
  });
  resetState(ctx);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('items written to state', state.items.length === 2 && state.items[0].joint_revision_id === 5);
  check('total written to state', state.total === 2);
  check('page written to state', state.page === 1);
  check('total_pages written to state (as totalPages)', state.totalPages === 1);
}

async function testStateReflectsInRequestParameters() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  vm.runInContext("govJointRevisionListState.search = 'xyz'; govJointRevisionListState.sortBy = 'outcome'; govJointRevisionListState.page = 3;", ctx.context);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  const calledPath = ctx.apiCalls[0].path;
  check('request reflects current search', calledPath.indexOf('search=xyz') !== -1);
  check('request reflects current sortBy', calledPath.indexOf('sort_by=outcome') !== -1);
  check('request reflects current page', calledPath.indexOf('page=3') !== -1);
}

async function testHttpErrorHandledSafely() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => { throw new Error('Sunucu hatası (422)'); } });
  resetState(ctx);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('HTTP error sets a non-null error', state.error !== null);
  check('HTTP error leaves loading false', state.loading === false);
}

async function testNetworkErrorHandledSafely() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => { throw new TypeError('Failed to fetch'); } });
  resetState(ctx);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('network error sets a non-null error', state.error !== null);
  check('network error leaves loading false', state.loading === false);
}

async function testErrorMessageNeverLeaksRawServerText() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => { throw new Error('/secret/internal/path leaked'); } });
  resetState(ctx);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('the raw thrown message is never copied verbatim into state.error', state.error.indexOf('/secret/internal/path') === -1);
}

async function testSingleRequestProducesConsistentFinalRenderNoStaleLoading() {
  const ctx = newContext(EXTRACTED, HTML, { apiRequestImpl: async () => fakeEnvelope() });
  resetState(ctx);
  await vm.runInContext('govLoadJointRevisionsQuery()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('final render shows no loading text', html.indexOf(HTML.match(/'gov\.jrlist\.loading':\s*'([^']*)'/)[1]) === -1);
  check('final render is not empty', html.length > 0);
}

// =================================================================
// Rendering
// =================================================================

async function testLoadingStateRenders() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext('govJointRevisionListState.loading = true;', ctx.context);
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  check('loading state renders fc-muted container', ctx.byId['gov-jrlist-query-result'].innerHTML.indexOf('fc-muted') !== -1);
}

async function testEmptyStateRenders() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('empty state does not render a table', html.indexOf('<table') === -1);
}

async function testErrorStateRenders() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext("govJointRevisionListState.error = 'boom';", ctx.context);
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('error state uses the existing alert alert-danger class', html.indexOf('alert alert-danger') !== -1);
  check('error text is present', html.indexOf('boom') !== -1);
}

async function testTableRendersForNonEmptyResult() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = ' + JSON.stringify([fakeItem({ joint_revision_id: 11 })])
    + '; govJointRevisionListState.total = 1; govJointRevisionListState.totalPages = 1;',
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('non-empty result renders a table', html.indexOf('<table') !== -1);
  check('rendered row includes the revision id', html.indexOf('>11<') !== -1);
}

async function testResultCountVisible() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = ' + JSON.stringify([fakeItem()])
    + '; govJointRevisionListState.total = 42; govJointRevisionListState.totalPages = 2;',
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('total result count (42) is visible', html.indexOf('42') !== -1);
}

async function testPageAndTotalPagesVisible() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = ' + JSON.stringify([fakeItem()])
    + '; govJointRevisionListState.total = 1; govJointRevisionListState.page = 2; govJointRevisionListState.totalPages = 4;',
    ctx.context,
  );
  const label = vm.runInContext('govJointRevisionQueryPageLabel()', ctx.context);
  check('page label includes current page (2)', label.indexOf('2') !== -1);
  check('page label includes total pages (4)', label.indexOf('4') !== -1);
}

async function testNullFieldsRenderAsEmDash() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = '
    + JSON.stringify([fakeItem({ safe_reason: null, canonical_status: null, lifecycle_group: null })])
    + '; govJointRevisionListState.total = 1; govJointRevisionListState.totalPages = 1;',
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('null fields render the em dash placeholder', html.indexOf('\u2014') !== -1);
}

async function testDynamicHtmlIsEscaped() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = '
    + JSON.stringify([fakeItem({ safe_reason: '<img src=x onerror=alert(1)>' })])
    + '; govJointRevisionListState.total = 1; govJointRevisionListState.totalPages = 1;',
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('a raw <img> tag from safe_reason is never rendered unescaped', html.indexOf('<img src=x') === -1);
  check('the escaped form is present instead', html.indexOf('&lt;img') !== -1);
}

async function testApiItemOrderIsPreservedNotReSorted() {
  const items = [fakeItem({ joint_revision_id: 30 }), fakeItem({ joint_revision_id: 10 }), fakeItem({ joint_revision_id: 20 })];
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = ' + JSON.stringify(items)
    + '; govJointRevisionListState.total = 3; govJointRevisionListState.totalPages = 1;',
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  const pos30 = html.indexOf('>30<');
  const pos10 = html.indexOf('>10<');
  const pos20 = html.indexOf('>20<');
  check('rendered row order matches API item order (30, 10, 20), never re-sorted client-side', pos30 < pos10 && pos10 < pos20);
}

async function testPreviousDisabledAtPage1() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = ' + JSON.stringify([fakeItem()])
    + '; govJointRevisionListState.total = 1; govJointRevisionListState.page = 1; govJointRevisionListState.totalPages = 3;',
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const prevDisabled = ctx.byId['gov-jrlist-query-result'].innerHTML.indexOf('id="gov_jrlist_query_prev_btn"');
  check('previous button is rendered', prevDisabled !== -1);
  check('previous is disabled at page 1', vm.runInContext("document.getElementById('gov_jrlist_query_prev_btn').disabled", ctx.context) === true);
}

async function testNextDisabledAtLastPage() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = ' + JSON.stringify([fakeItem()])
    + '; govJointRevisionListState.total = 1; govJointRevisionListState.page = 3; govJointRevisionListState.totalPages = 3;',
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  check('next is disabled at the last page', vm.runInContext("document.getElementById('gov_jrlist_query_next_btn').disabled", ctx.context) === true);
}

async function testPaginationControlsAbsentWhenEmpty() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('no pagination buttons rendered for an empty result', html.indexOf('gov_jrlist_query_prev_btn') === -1);
}

async function testExportControlExistsInMarkup() {
  checkIncludes('export button exists in the real HTML markup', HTML, 'gov_jrlist_query_export_btn');
  checkIncludes('export button is wired to the export handler', HTML, 'govJointRevisionQueryExportCsv()');
}

// =================================================================
// Export lifecycle
// =================================================================

async function testExportCallsCorrectEndpoint() {
  const ctx = newContext(EXTRACTED, HTML, {
    fetchImpl: async () => ({ ok: true, blob: async () => ({ __mockBlob: true }) }),
  });
  resetState(ctx);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  check('exactly one fetch call', ctx.fetchCalls.length === 1);
  check('fetch called the export endpoint', ctx.fetchCalls[0].url.indexOf('/api/governance/joint-revisions/export.csv') === 0);
}

async function testExportReflectsSearchAndSortNotPage() {
  const ctx = newContext(EXTRACTED, HTML, {
    fetchImpl: async () => ({ ok: true, blob: async () => ({ __mockBlob: true }) }),
  });
  resetState(ctx);
  vm.runInContext("govJointRevisionListState.search = 'foo'; govJointRevisionListState.sortBy = 'outcome'; govJointRevisionListState.sortOrder = 'desc'; govJointRevisionListState.page = 4;", ctx.context);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  const url = ctx.fetchCalls[0].url;
  check('export reflects search', url.indexOf('search=foo') !== -1);
  check('export reflects sort_by', url.indexOf('sort_by=outcome') !== -1);
  check('export reflects sort_order', url.indexOf('sort_order=desc') !== -1);
  check('export never sends page', /(^|[?&])page=/.test(url) === false);
}

async function testExportUsesAuthorizationHeader() {
  const ctx = newContext(EXTRACTED, HTML, {
    fetchImpl: async () => ({ ok: true, blob: async () => ({ __mockBlob: true }) }),
  });
  resetState(ctx);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  const headers = ctx.fetchCalls[0].options.headers || {};
  check('export request carries a bearer Authorization header', headers.Authorization === 'Bearer fake-token-abc');
}

async function testExportNon200ProducesError() {
  const ctx = newContext(EXTRACTED, HTML, { fetchImpl: async () => ({ ok: false }) });
  resetState(ctx);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  const state = vm.runInContext('govJointRevisionListState', ctx.context);
  check('a non-200 export response sets a non-null error', state.error !== null);
}

async function testExportCreatesObjectUrlFromBlob() {
  const ctx = newContext(EXTRACTED, HTML, {
    fetchImpl: async () => ({ ok: true, blob: async () => ({ __mockBlob: true }) }),
  });
  resetState(ctx);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  check('URL.createObjectURL was called exactly once', ctx.urlCalls.created.length === 1);
}

async function testExportAnchorFilenameIsCorrect() {
  const ctx = newContext(EXTRACTED, HTML, {
    fetchImpl: async () => ({ ok: true, blob: async () => ({ __mockBlob: true }) }),
  });
  resetState(ctx);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  check('exactly one anchor element was created', ctx.documentStub.__created.length === 1);
  check('anchor download filename is exactly joint-revisions-export.csv', ctx.documentStub.__created[0].download === 'joint-revisions-export.csv');
}

async function testExportAnchorIsClickedAndRemoved() {
  const ctx = newContext(EXTRACTED, HTML, {
    fetchImpl: async () => ({ ok: true, blob: async () => ({ __mockBlob: true }) }),
  });
  resetState(ctx);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  const anchor = ctx.documentStub.__created[0];
  check('the temporary anchor was clicked', anchor._calls.clicked === true);
  check('the temporary anchor was appended to the DOM before clicking', ctx.documentStub.__appended.indexOf(anchor) !== -1);
  check('the temporary anchor was removed after clicking', anchor._calls.removed === true);
}

async function testExportObjectUrlIsRevoked() {
  const ctx = newContext(EXTRACTED, HTML, {
    fetchImpl: async () => ({ ok: true, blob: async () => ({ __mockBlob: true }) }),
  });
  resetState(ctx);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  check('the created object URL was revoked', ctx.urlCalls.revoked.length === 1 && ctx.urlCalls.revoked[0] === ctx.urlCalls.created[0].url);
}

async function testExportBlobIsNeverReadOrRewritten() {
  // The handler must pass the fetched Blob straight to
  // URL.createObjectURL() -- never call .text()/.arrayBuffer() on it
  // (which would be the first step toward re-encoding/mutating the
  // CSV bytes, losing the BOM the backend already added).
  checkNotIncludes(
    'export handler never reads the blob body (no .text()/.arrayBuffer() call on it)',
    HTML.slice(HTML.indexOf('async function govJointRevisionQueryExportCsv'), HTML.indexOf('async function govJointRevisionQueryExportCsv') + 1200),
    '.arrayBuffer()',
  );
}

async function testExportErrorShownSafely() {
  const ctx = newContext(EXTRACTED, HTML, { fetchImpl: async () => ({ ok: false }) });
  resetState(ctx);
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  check('export failure is rendered via the existing alert-danger convention', html.indexOf('alert alert-danger') !== -1);
}

async function testExportButtonReturnsToNormalAfterCompletion() {
  const ctx = newContext(EXTRACTED, HTML, {
    fetchImpl: async () => ({ ok: true, blob: async () => ({ __mockBlob: true }) }),
  });
  resetState(ctx);
  const btn = ctx.byId['gov_jrlist_query_export_btn'];
  btn.textContent = 'Export CSV';
  await vm.runInContext('govJointRevisionQueryExportCsv()', ctx.context);
  check('export button is re-enabled after completion', btn.disabled === false);
  check('export button label is restored after completion', btn.textContent === 'Export CSV');
}

// =================================================================
// Event binding (static markup checks -- this file's whole
// convention is inline onclick/onchange/onkeydown attributes, bound
// exactly once as static HTML, never re-attached via
// addEventListener on re-render -- see module docstring).
// =================================================================

async function testEventBindingsPresentInMarkup() {
  checkIncludes('search button bound', HTML, 'onclick="govJointRevisionQuerySearch()"');
  checkIncludes('search input Enter-key bound', HTML, "govJointRevisionQuerySearch();");
  checkIncludes('clear button bound', HTML, 'onclick="govJointRevisionQueryClearSearch()"');
  checkIncludes('sort field change bound', HTML, 'onchange="govJointRevisionQuerySortChange()"');
  checkIncludes('sort order change bound', HTML, 'onchange="govJointRevisionQueryOrderChange()"');
  checkIncludes('page size change bound', HTML, 'onchange="govJointRevisionQueryPageSizeChange()"');
  checkIncludes('export button bound', HTML, 'onclick="govJointRevisionQueryExportCsv()"');
}

async function testNoDuplicateEventBindingAttributesForEachControl() {
  const controlsAndHandlers = [
    ['gov_jrlist_query_search_btn', 'govJointRevisionQuerySearch()'],
    ['gov_jrlist_query_clear_btn', 'govJointRevisionQueryClearSearch()'],
    ['gov_jrlist_query_sort_by', 'govJointRevisionQuerySortChange()'],
    ['gov_jrlist_query_sort_order', 'govJointRevisionQueryOrderChange()'],
    ['gov_jrlist_query_page_size', 'govJointRevisionQueryPageSizeChange()'],
    ['gov_jrlist_query_export_btn', 'govJointRevisionQueryExportCsv()'],
  ];
  controlsAndHandlers.forEach(([id, handlerCall]) => {
    const idOccurrences = (HTML.match(new RegExp('id="' + id + '"', 'g')) || []).length;
    check(id + ' element id appears exactly once in the static markup (no duplicate control)', idOccurrences === 1);
  });
  // Previous/Next are rendered dynamically (inside innerHTML) rather
  // than static markup -- each render replaces the whole container's
  // innerHTML wholesale, so a fresh render can never accumulate a
  // second listener alongside an old one (there is no persistent DOM
  // node for old inline-onclick handlers to remain attached to).
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = ' + JSON.stringify([fakeItem()])
    + '; govJointRevisionListState.total = 1; govJointRevisionListState.totalPages = 2;',
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const html = ctx.byId['gov-jrlist-query-result'].innerHTML;
  const prevCount = (html.match(/gov_jrlist_query_prev_btn/g) || []).length;
  check('re-rendering twice does not accumulate duplicate Previous buttons', prevCount === 1);
}

// =================================================================
// i18n
// =================================================================

async function testAllUsedGovJrlistKeysExistInEnglish() {
  const script = extractScript(HTML);
  const usedInCalls = new Set((script.match(/t\('(gov\.jrlist\.[\w.]+)'\)/g) || []).map((m) => m.match(/'(gov\.jrlist\.[\w.]+)'/)[1]));
  const usedInAttrs = new Set((HTML.match(/data-i18n(?:-placeholder)?="(gov\.jrlist\.[\w.]+)"/g) || []).map((m) => m.match(/"(gov\.jrlist\.[\w.]+)"/)[1]));
  const used = new Set([...usedInCalls, ...usedInAttrs]);
  const enBlockMatch = /en:\s*\{([\s\S]*?)\n  \},\n  tr:/.exec(script);
  const enKeys = new Set((enBlockMatch[1].match(/'(gov\.jrlist\.[\w.]+)':/g) || []).map((m) => m.match(/'(gov\.jrlist\.[\w.]+)':/)[1]));
  const missing = [...used].filter((k) => !enKeys.has(k));
  check('every used gov.jrlist.* key exists in the EN dictionary', missing.length === 0);
}

async function testAllUsedGovJrlistKeysExistInTurkish() {
  const script = extractScript(HTML);
  const usedInCalls = new Set((script.match(/t\('(gov\.jrlist\.[\w.]+)'\)/g) || []).map((m) => m.match(/'(gov\.jrlist\.[\w.]+)'/)[1]));
  const usedInAttrs = new Set((HTML.match(/data-i18n(?:-placeholder)?="(gov\.jrlist\.[\w.]+)"/g) || []).map((m) => m.match(/"(gov\.jrlist\.[\w.]+)"/)[1]));
  const used = new Set([...usedInCalls, ...usedInAttrs]);
  const trBlockMatch = /tr:\s*\{([\s\S]*?)\n  \},\n\};/.exec(script);
  const trKeys = new Set((trBlockMatch[1].match(/'(gov\.jrlist\.[\w.]+)':/g) || []).map((m) => m.match(/'(gov\.jrlist\.[\w.]+)':/)[1]));
  const missing = [...used].filter((k) => !trKeys.has(k));
  check('every used gov.jrlist.* key exists in the TR dictionary', missing.length === 0);
}

async function testEnAndTrGovJrlistKeySetsMatchExactly() {
  const script = extractScript(HTML);
  const enBlockMatch = /en:\s*\{([\s\S]*?)\n  \},\n  tr:/.exec(script);
  const trBlockMatch = /tr:\s*\{([\s\S]*?)\n  \},\n\};/.exec(script);
  const enKeys = new Set((enBlockMatch[1].match(/'(gov\.jrlist\.[\w.]+)':/g) || []).map((m) => m.match(/'(gov\.jrlist\.[\w.]+)':/)[1]));
  const trKeys = new Set((trBlockMatch[1].match(/'(gov\.jrlist\.[\w.]+)':/g) || []).map((m) => m.match(/'(gov\.jrlist\.[\w.]+)':/)[1]));
  const enOnly = [...enKeys].filter((k) => !trKeys.has(k));
  const trOnly = [...trKeys].filter((k) => !enKeys.has(k));
  check('EN and TR gov.jrlist.* key sets are identical (full parity)', enOnly.length === 0 && trOnly.length === 0);
}

async function testLanguageReRenderPreservesState() {
  const ctx = newContext(EXTRACTED, HTML, {});
  resetState(ctx);
  vm.runInContext(
    'govJointRevisionListState.items = ' + JSON.stringify([fakeItem({ joint_revision_id: 77 })])
    + "; govJointRevisionListState.total = 1; govJointRevisionListState.totalPages = 1; govJointRevisionListState.search = 'kept';",
    ctx.context,
  );
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const before = vm.runInContext('govJointRevisionListState.search', ctx.context);
  vm.runInContext('govRenderJointRevisionQueryResult()', ctx.context);
  const after = vm.runInContext('govJointRevisionListState.search', ctx.context);
  check('re-rendering (as a language switch would trigger) never refetches or clears existing state', before === after && after === 'kept');
}

// =================================================================
// Main
// =================================================================

const ALL_TESTS = [
  testStateDefaults,
  testQueryUrlBuilderDefault, testQueryUrlBuilderSearchAndEncoding, testQueryUrlBuilderSortAndOrder,
  testQueryUrlBuilderJointId, testQueryUrlBuilderNoJointIdWhenEmpty,
  testQueryUrlBuilderWhitespaceSearchTrimmedAtSearchTime, testQueryUrlBuilderPageAndPageSizeAreNumeric,
  testExportUrlBuilderDefault, testExportUrlBuilderSearchSortJointId,
  testSearchResetsPageTo1, testClearResetsSearchAndPage, testSortFieldChangeResetsPage,
  testSortOrderChangeResetsPage, testPageSizeChangeResetsPage,
  testNextPageIncrements, testPrevPageDecrements, testPrevPageNoOpAtPage1, testNextPageNoOpAtLastPage,
  testPrevAndNextNoOpWhenTotalPagesZero,
  testValidEnvelopeAccepted, testMissingItemsRejected, testItemsNotArrayRejected, testMissingTotalRejected,
  testMissingPageRejected, testMissingPageSizeRejected, testMissingTotalPagesRejected,
  testNonIntegerMetadataRejected, testNegativeMetadataBehaviourMatchesImplementation,
  testInvalidResponseProducesSafeErrorState,
  testLoadCallsCorrectEndpoint, testLoadingTrueBeforeRequestResolvesThenFalseAfter,
  testSuccessfulResponseWritesItemsAndMetadataToState, testStateReflectsInRequestParameters,
  testHttpErrorHandledSafely, testNetworkErrorHandledSafely, testErrorMessageNeverLeaksRawServerText,
  testSingleRequestProducesConsistentFinalRenderNoStaleLoading,
  testLoadingStateRenders, testEmptyStateRenders, testErrorStateRenders, testTableRendersForNonEmptyResult,
  testResultCountVisible, testPageAndTotalPagesVisible, testNullFieldsRenderAsEmDash,
  testDynamicHtmlIsEscaped, testApiItemOrderIsPreservedNotReSorted,
  testPreviousDisabledAtPage1, testNextDisabledAtLastPage, testPaginationControlsAbsentWhenEmpty,
  testExportControlExistsInMarkup,
  testExportCallsCorrectEndpoint, testExportReflectsSearchAndSortNotPage, testExportUsesAuthorizationHeader,
  testExportNon200ProducesError, testExportCreatesObjectUrlFromBlob, testExportAnchorFilenameIsCorrect,
  testExportAnchorIsClickedAndRemoved, testExportObjectUrlIsRevoked, testExportBlobIsNeverReadOrRewritten,
  testExportErrorShownSafely, testExportButtonReturnsToNormalAfterCompletion,
  testEventBindingsPresentInMarkup, testNoDuplicateEventBindingAttributesForEachControl,
  testAllUsedGovJrlistKeysExistInEnglish, testAllUsedGovJrlistKeysExistInTurkish,
  testEnAndTrGovJrlistKeySetsMatchExactly, testLanguageReRenderPreservesState,
];

async function main() {
  for (const testFn of ALL_TESTS) {
    try {
      await testFn();
    } catch (e) {
      recordFailure(testFn.name + ' (threw)');
      console.log('FAIL: ' + testFn.name + ' (threw) -- ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join('\n') : e));
    }
  }
  const { pass, fail, failures } = summary();
  console.log(`${pass + fail} assertions, ${pass} passed, ${fail} failed`);
  if (fail > 0) {
    console.log('Failures:');
    failures.forEach((f) => console.log('  - ' + f));
    process.exit(1);
  }
}

main();
