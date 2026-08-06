#!/usr/bin/env node
'use strict';
/*
 * Faz 2.8.22 -- "Örnek Tork Çalışması" / Sample Torque Study screen
 * UI/UX messaging regression harness.
 *
 * Zero external dependencies, same technique as
 * tests/js/run_i18n_tests.js and tests/js/run_material_intelligence_tests.js:
 * Node's built-in `vm` module runs the *actual* declarations extracted
 * live from frontend/index.html (never a committed copy) against a
 * small hand-built DOM/localStorage stub.
 *
 * Covers PDF review items 1-6 (attached PDF review, 2026-08-06):
 *   1. Title renders with no raw HTML markup leaking into the text.
 *   2/3. Icon-triggered popovers (Kapsam ve Öncelik / Referans Kaynak /
 *        class-matching rule) carry the full previous message text,
 *        localized per language, instead of always-visible TR-only text.
 *   4. Reference-source icon uses the dedicated "ref" (open-book) variant
 *      with a clear, localized aria-label/title (not just an emoji).
 *   5. "Örnek OEM genel öngörüsü" / "sample general OEM forecast" wording
 *      shortened to "Örnek öngörü" / "sample estimate".
 *   6. Class-mismatch blocking error keeps a short visible summary AND
 *      gets a red ("error") icon that opens the full explanation.
 *   7 (regression guard only, not reopened): the underlying torque/
 *      tensile-force numbers for known selections are unchanged.
 *
 * Invoked via `node tests/js/run_torque_study_ui_messaging_tests.js`
 * from the repo root, or indirectly via
 * tests/test_faz_2_8_22_torque_study_ui_messaging.py.
 * Exit code 0 = all assertions passed; non-zero = at least one failure.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const {
  extractScript,
  extractConstDecl,
  extractFunctionDecl,
  toVarDecl,
  makeLocalStorage,
  buildDom,
  createChecker,
} = require('./harness_common');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const FRONTEND_PATH = path.join(REPO_ROOT, 'frontend', 'index.html');

const CONST_NAMES = ['I18N', 'CURRENT_LANG', 'N01391', 'INFO_ICON_SEQ', 'INFO_ICON_VARIANTS'];
const MUTABLE_STATE_NAMES = ['CURRENT_LANG', 'INFO_ICON_SEQ'];
const FUNCTION_NAMES = [
  't', 'applyStaticTranslations', 'setLanguage',
  'infoIconHtml', 'initInfoIcons', 'n01391Hesapla',
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
      if (stMatch) parts.push(stMatch[0]);
    }
  }
  for (const n of FUNCTION_NAMES) parts.push(extractFunctionDecl(script, n));
  parts.push('function __getCurrentLang() { return CURRENT_LANG; }');
  return { source: parts.join('\n\n'), rawHtml: html };
}

const { check, checkIncludes, checkNotIncludes, summary } = createChecker();

function newContext(extractedSource, rawHtml) {
  const byId = {};
  const documentStub = buildDom(rawHtml, byId);
  const sandbox = {
    document: documentStub,
    localStorage: makeLocalStorage({}),
    sessionStorage: makeLocalStorage({}),
    console: console,
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(extractedSource, context, { filename: 'torque_study_ui_extracted.js' });
  return { context, byId, documentStub };
}

function setN01391Selection(documentStub, { dis, flans, civata, somun }) {
  documentStub.getElementById('n_dis').value = dis;
  documentStub.getElementById('n_flans').value = flans ? 'yes' : 'no';
  documentStub.getElementById('n_civata').value = civata;
  documentStub.getElementById('n_somun').value = somun;
}

async function main() {
  const { source, rawHtml } = buildExtractedSource();

  // ---------------------------------------------------------------
  // Item 1: title has no raw HTML leaking into the translated string.
  // ---------------------------------------------------------------
  {
    const { context } = newContext(source, rawHtml);
    const trTitle = context.t('n01391.title');
    const enContext = context; // same context, just call t after switching lang
    check('n01391.title (tr) contains no HTML tag characters', !/[<>]/.test(trTitle));
    check('n01391.title (tr) is the clean Turkish label', trTitle === 'Örnek Tork Çalışması');
    context.setLanguage('en');
    const enTitle = enContext.t('n01391.title');
    check('n01391.title (en) contains no HTML tag characters', !/[<>]/.test(enTitle));
    check('n01391.title (en) is the clean English label', enTitle === 'Sample Torque Study');
  }

  // The static markup itself (the fallback text before JS runs, and
  // the div's data-i18n host) must also be free of the leaked <span>
  // -- guards against the bug being reintroduced directly in the HTML.
  {
    const titleMarkupMatch = /data-i18n="n01391\.title">([^<]*(?:<(?!\/div)[^>]*>[^<]*)*)<\/div>/.exec(rawHtml);
    check('static n01391.title markup exists', !!titleMarkupMatch);
    if (titleMarkupMatch) {
      check('static n01391.title markup has no embedded <span> style leak', !/<span/.test(titleMarkupMatch[1]));
    }
  }

  // ---------------------------------------------------------------
  // Items 2-4: icon-triggered popovers carry the full previous
  // message, localized, with clear (non-emoji-only) aria-labels.
  // ---------------------------------------------------------------
  {
    const { context, documentStub } = newContext(source, rawHtml);
    context.initInfoIcons();

    const scopeHtml = documentStub.getElementById('n01391-scope-info').innerHTML;
    checkIncludes('scope-info popover (tr) keeps full scope/priority text', scopeHtml, context.t('n01391.scope_priority_text'));
    checkIncludes('scope-info icon (tr) is a warn-styled button', scopeHtml, 'info-icon-btn warn');
    checkIncludes('scope-info icon has aria-haspopup=dialog', scopeHtml, 'aria-haspopup="dialog"');
    checkIncludes('scope-info icon has aria-expanded=false initially', scopeHtml, 'aria-expanded="false"');
    check('scope-info icon aria-label is non-empty and TR-localized', scopeHtml.includes('aria-label="Kapsam ve öncelik ayrıntılarını görüntüle"'));

    const refHtml = documentStub.getElementById('n01391-ref-info').innerHTML;
    checkIncludes('ref-info popover (tr) keeps full reference-source text', refHtml, context.t('n01391.ref_source_text'));
    checkIncludes('ref-info icon uses the dedicated open-book "ref" variant', refHtml, 'info-icon-btn ref');
    check('ref-info icon aria-label is clear (not emoji-only), TR', refHtml.includes('aria-label="Referans kaynağını görüntüle"'));

    const matchHtml = documentStub.getElementById('n01391-matching-info').innerHTML;
    checkIncludes('matching-info popover (tr) keeps full class-matching-rule text', matchHtml, context.t('n01391.matching_rule'));
    checkIncludes('matching-info icon is an info-styled button', matchHtml, 'info-icon-btn"');

    // Switch to English and re-render: same three icons must now
    // carry the English text, not stay frozen in Turkish (this used
    // to be hardcoded TR-only before Faz 2.8.22).
    context.setLanguage('en');
    const scopeHtmlEn = documentStub.getElementById('n01391-scope-info').innerHTML;
    checkIncludes('scope-info popover (en) shows English scope/priority text', scopeHtmlEn, context.t('n01391.scope_priority_text'));
    check('scope-info popover (en) no longer contains the Turkish text', !scopeHtmlEn.includes('Teknik resim veya proje şartnamesi'));

    const refHtmlEn = documentStub.getElementById('n01391-ref-info').innerHTML;
    check('ref-info icon aria-label is clear, EN', refHtmlEn.includes('aria-label="View reference source"'));
  }

  // ---------------------------------------------------------------
  // Item 5: "Örnek OEM genel öngörüsü" / "sample general OEM
  // forecast" wording shortened, without touching the OEM/general-
  // estimate calculation logic (no calculation function touched by
  // this harness at all).
  // ---------------------------------------------------------------
  {
    const { context } = newContext(source, rawHtml);
    const trDisclaimer = context.t('n01391.disclaimer_line1');
    check('TR disclaimer uses the shortened "örnek öngörü" wording', trDisclaimer.includes('örnek öngörüdür'));
    check('TR disclaimer no longer says "genel öngörüsü"', !trDisclaimer.includes('genel öngörüsü'));
    context.setLanguage('en');
    const enDisclaimer = context.t('n01391.disclaimer_line1');
    check('EN disclaimer uses the shortened "sample estimate" wording', enDisclaimer.includes('sample estimate'));
    check('EN disclaimer no longer says "sample general OEM forecast"', !enDisclaimer.includes('sample general OEM forecast'));
  }

  // ---------------------------------------------------------------
  // Item 6 + Item 7 (regression guard): mismatched bolt/nut class
  // keeps a short visible summary AND a red error icon with the full
  // explanation; matched combinations render no mismatch banner at
  // all. Nominal torque / tensile force numbers for both scenarios
  // are asserted unchanged (M5 flanged 10.9/8 and M12x1.25 flanged
  // 10.9/10, cross-checked against the values shown in the reviewed
  // PDF screenshots).
  // ---------------------------------------------------------------
  {
    const { context, documentStub } = newContext(source, rawHtml);

    // Mismatched: M5, Flanged, Bolt 10.9 / Nut 8 (uses the lower class).
    setN01391Selection(documentStub, { dis: 'M5', flans: true, civata: '10.9', somun: '8' });
    context.n01391Hesapla();
    const mismatchedHtml = documentStub.getElementById('n01391-sonuc').innerHTML;
    checkIncludes('mismatch case: short visible summary text is present', mismatchedHtml, context.t('n01391.mismatch_warning'));
    checkIncludes('mismatch case: uses alert-danger (red), not alert-warn', mismatchedHtml, 'alert-danger');
    checkNotIncludes('mismatch case: does not additionally render a redundant alert-warn banner for the mismatch', mismatchedHtml.split('n01391-warn')[0], 'alert-warn');
    checkIncludes('mismatch case: red error icon variant is present', mismatchedHtml, 'info-icon-btn err');
    checkIncludes('mismatch case: error icon popover carries the full class-matching-rule explanation', mismatchedHtml, context.t('n01391.matching_rule'));
    check('mismatch case: nominal torque unchanged at 5 Nm (matches reviewed PDF)', /5\s*<span[^>]*>\s*Nm/.test(mismatchedHtml) || mismatchedHtml.includes('>5 <span'));
    checkIncludes('mismatch case: tensile force unchanged at 5.100 N (matches reviewed PDF)', mismatchedHtml, '5.100');
    checkIncludes('mismatch case: short disclaimer summary still visible outside the popover', mismatchedHtml, context.t('n01391.disclaimer_line1'));
    checkIncludes('mismatch case: full disclaimer detail lines preserved inside the info icon popover', mismatchedHtml, context.t('n01391.disclaimer_line4'));

    // Matched: M12x1.25, Flanged, Bolt 10.9 / Nut 10 -- no mismatch banner.
    setN01391Selection(documentStub, { dis: 'M12x1.25', flans: true, civata: '10.9', somun: '10' });
    context.n01391Hesapla();
    const matchedHtml = documentStub.getElementById('n01391-sonuc').innerHTML;
    checkNotIncludes('matched case: no mismatch banner rendered', matchedHtml, context.t('n01391.mismatch_warning'));
    checkNotIncludes('matched case: no red error icon rendered', matchedHtml, 'info-icon-btn err');
    check('matched case: nominal torque unchanged at 120 Nm (matches reviewed PDF)', matchedHtml.includes('>120 <span'));
    checkIncludes('matched case: tensile force unchanged at 53.700 N (matches reviewed PDF)', matchedHtml, '53.700');
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
