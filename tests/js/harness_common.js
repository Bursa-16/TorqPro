'use strict';
/*
 * Faz 2.8.10 Stage 3 -- shared JS regression-harness helpers.
 *
 * Extracted from tests/js/run_assembly_intelligence_tests.js (Faz
 * 2.8.6), tests/js/run_joint_analysis_tests.js (Faz 2.8.7),
 * tests/js/run_material_intelligence_tests.js (Faz 2.8.8), and
 * tests/js/run_washer_resolution_report_tests.js (Faz 2.8.9), which
 * independently re-implemented the same extraction/DOM-stub/assertion
 * infrastructure four times over. Every function below was verified
 * byte-identical (or, for `makeElement`/`buildDom`, a strict superset
 * of the narrower variant -- see the per-function notes) across those
 * four files before being lifted out here; nothing here changes any
 * of their existing assertions or output.
 *
 * tests/js/run_i18n_tests.js (Faz 2.6.8, the original/oldest harness
 * that the later four followed the "same technique" of) is
 * deliberately NOT migrated to this module in Stage 3: several of its
 * equivalent internal helpers (extractConstDecl, extractFunctionDecl,
 * makeElement, makeLocalStorage, buildDom) have diverged in their
 * exact implementation from the four newer harnesses, so unifying
 * them would be a behavioral change to a large (4174-line),
 * already-passing harness rather than a pure extraction -- out of
 * scope for "genuinely duplicated, stable" helpers.
 *
 * `buildExtractedSource()` and `newContext()` in each harness are also
 * NOT part of this module: they are inherently feature-specific (each
 * harness extracts a different set of const/function declarations
 * from frontend/index.html and builds a different sandbox), so there
 * is nothing stable to share there.
 */

// ---------------------------------------------------------------
// Extraction helpers (verified byte-identical across all four
// migrated harnesses; extractScript and toVarDecl are additionally
// byte-identical in run_i18n_tests.js too, though that harness is not
// migrated to use this module in this stage).
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

// ---------------------------------------------------------------
// Minimal DOM / localStorage stub.
//
// makeElement: the run_material_intelligence_tests.js /
// run_washer_resolution_report_tests.js variant (with `classList`) is
// used here -- it is a strict superset of the
// run_assembly_intelligence_tests.js / run_joint_analysis_tests.js
// variant (without `classList`). Verified none of the four harnesses'
// extracted frontend functions call `.classList` on an element that
// only the narrower variant would have provided, so adding it changes
// nothing observable for any of the four.
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

// buildDom: the run_assembly_intelligence_tests.js /
// run_joint_analysis_tests.js / run_material_intelligence_tests.js
// variant also scrapes `[data-i18n-placeholder]` elements;
// run_washer_resolution_report_tests.js's variant does not (it never
// needed placeholder handling and its querySelectorAll for that
// selector fell through to `[]`). To preserve that harness's exact
// original behavior while sharing the implementation, this takes an
// `options.includePlaceholders` flag -- default `true` matches the
// three-harness majority behavior unchanged; the washer-report
// harness passes `{ includePlaceholders: false }` to keep its
// original `[]` result for that selector.
function buildDom(rawHtml, byId, options) {
  const includePlaceholders = !options || options.includePlaceholders !== false;
  const dataI18nEls = scrapeDataI18nKeys(rawHtml, 'data-i18n').map((key) => {
    const el = makeElement(null);
    el._attrs = { 'data-i18n': key };
    el.getAttribute = (n) => el._attrs[n] || null;
    return el;
  });
  const placeholderEls = includePlaceholders
    ? scrapeDataI18nKeys(rawHtml, 'data-i18n-placeholder').map((key) => {
      const el = makeElement(null);
      el._attrs = { 'data-i18n-placeholder': key };
      el.getAttribute = (n) => el._attrs[n] || null;
      el.set = (v) => { el.placeholder = v; };
      return el;
    })
    : [];
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
// Assertion bookkeeping -- factory, not module-level state, so each
// harness gets its own independent pass/fail/failures counters (and
// output stays interleaved with that harness's own console.log calls
// exactly as before: `check()` still logs each failure immediately,
// only the running totals move behind `summary()`).
// ---------------------------------------------------------------

function createChecker() {
  let pass = 0;
  let fail = 0;
  const failures = [];

  function recordFailure(name) {
    fail++;
    failures.push(name);
  }

  function check(name, cond) {
    if (cond) { pass++; }
    else { recordFailure(name); console.log('FAIL: ' + name); }
  }
  function checkIncludes(name, haystack, needle) {
    check(name, typeof haystack === 'string' && haystack.indexOf(needle) !== -1);
  }
  function checkNotIncludes(name, haystack, needle) {
    check(name, typeof haystack === 'string' && haystack.indexOf(needle) === -1);
  }
  function summary() {
    return { pass, fail, failures };
  }

  return { check, checkIncludes, checkNotIncludes, recordFailure, summary };
}

module.exports = {
  extractScript,
  extractConstDecl,
  extractFunctionDecl,
  extractStatementAfter,
  toVarDecl,
  makeElement,
  makeLocalStorage,
  scrapeDataI18nKeys,
  buildDom,
  createChecker,
};
