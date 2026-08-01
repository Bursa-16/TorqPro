# Phase 2.8.16 Stage 5 — Joint Revision List UX Improvements: Frontend Quality Integration

- Status: **Stage 5 complete** (quality-gate integration + i18n
  hardening only). Phase 2.8.16 as a whole is **not** complete —
  Stage 6 remains (full validation and completion documentation). Do
  not read this document as a phase completion report.
- Depends on:
  `docs/phases/PHASE_2.8.16_STAGE4_FRONTEND_UX.md`.
- Baseline: branch `feature/faz-2.8.16-joint-revision-list-ux`, HEAD
  `93fdd48` (Stage 4 commit) at the time Stage 5 work began. Working
  tree clean. Full suite 2144/2144, quality gate 6/6 (5 JS harnesses),
  dedicated UX harness 136/136, governance workspace harness 160/160
  — all reconfirmed before Stage 5 work began.

## 1. Stage 5 Objective

Wire `tests/js/run_joint_revision_list_ux_tests.js` into
`tools/run_quality_gate.py`'s canonical JS harness list with proof
that a failure there genuinely fails the gate; replace the brittle
exact-count `gov.*` key-parity test with a parity + minimum-floor +
explicit-required-set contract; deepen the dedicated harness's i18n
coverage. No frontend behavior change, no backend change.

## 2. Existing Quality Gate Architecture

`tools/run_quality_gate.py` runs a fixed, ordered sequence of 6
`Gate` objects (`default_gates()`), stopping at the first failure.
Step 5 ("JavaScript harnesses") iterates a **hardcoded tuple**,
`JS_HARNESS_FILENAMES` — not a glob or directory scan — running each
via `node <path>` (through an injectable `runner`, defaulting to
`subprocess.run`) and stopping at the first non-zero exit. Node
absence is itself a hard failure (`NODE_MISSING_MESSAGE`), never a
skip. Existing focused tests for this module already live in
`tests/test_run_quality_gate.py`, using an
`importlib.util.spec_from_file_location`-loaded copy of the module
plus a `_RecordingRunner`/`_FakeCompletedProcess` fake to exercise
`_run_js_harnesses()` without any real subprocess or Node
installation.

**Notable pre-existing gap, unchanged by this Stage**:
`tests/js/run_governance_workspace_tests.js` was **never** in
`JS_HARNESS_FILENAMES` — it has been run manually alongside the gate
since it was written (documented in this phase's own Stage 0 report).
Fixing that gap is unrelated to Joint Revision List UX and is
explicitly out of this Stage's scope ("Faz dışı harness refactor
yapma") — it is not touched here.

## 3. New Harness Integration

One line added to `JS_HARNESS_FILENAMES`:

```python
JS_HARNESS_FILENAMES: tuple[str, ...] = (
    "run_assembly_intelligence_tests.js",
    "run_i18n_tests.js",
    "run_joint_analysis_tests.js",
    "run_material_intelligence_tests.js",
    "run_washer_resolution_report_tests.js",
    "run_joint_revision_list_ux_tests.js",
)
```

No other line in `tools/run_quality_gate.py` was touched — gate
order, timeouts, pytest invocation, JSON/i18n checks, and
Node-requirement behavior are all byte-identical to before.

## 4. Harness Execution Order

Appended **last** (position 6 of 6) — since
`run_governance_workspace_tests.js` is not itself in the list (see
Section 2), there was no adjacent "governance workspace" entry to
position next to; appending at the end was the only well-defined
choice that doesn't reorder the five pre-existing, already-verified
entries. Confirmed via a runner-injection test
(`test_new_harness_runs_after_all_five_pre_existing_harnesses`) that
the five pre-existing harnesses still run first, in their original
order, followed by the new one.

## 5. Harness Failure Behaviour

**Proof method: Option B (runner-injection/monkeypatch)**, reusing
the exact `_RecordingRunner`/`_FakeCompletedProcess` pattern
`tests/test_run_quality_gate.py` already established for this same
purpose — no real file was ever temporarily broken on disk. A
scripted result sequence (five passes, one failure at the new
harness's position) proves: `_run_js_harnesses()` returns
`GateOutcome(passed=False, ...)`, the failure output names
`run_joint_revision_list_ux_tests.js` explicitly, and a full
`run_gates()` invocation with that outcome wired into a 3-gate list
stops at gate 2/3 with exit code `1`, never reaching gate 3. A mirror
test with an all-passing scripted sequence confirms the step reports
"All 6 JavaScript harnesses passed." This is safer than Option A
(temporarily corrupting a real file) and requires no before/after
hash comparison or cleanup step, since no real file was ever changed
for the proof.

## 6. Joint Revision UX Harness Scope

136 (Stage 4) -> **152** assertions. 16 new assertions added, purely
additive (none of the original 136 were modified or removed),
covering the i18n gaps identified in Section 8:

- Re-render never calls `apiRequest`/`fetch` (2 assertions).
- Page/sort-by/sort-order/total-pages state survives a re-render (4).
- The result table is rebuilt (not stale) and is byte-identical
  across two re-renders of the same state (2).
- `gov.jrlist.pageOf`'s rendered text actually changes when
  `CURRENT_LANG` changes — proving it is looked up fresh via `t()`
  on every call, never cached from the first render (2).
- Previous/Next button labels are re-translated across a TR->EN
  re-render (2).
- No raw `gov.jrlist.` key-name literal ever leaks into rendered
  output, checked across the table/empty/loading/error states (4).

## 7. Existing Governance Harness Compatibility

`tests/js/run_governance_workspace_tests.js` was **not modified in
this Stage** — its Stage 4 extraction-list addition
(`govJointRevisionListState`,
`govJointRevisionQueryPageLabel`,
`govRenderJointRevisionQueryControlsState`,
`govRenderJointRevisionQueryResult`) was re-verified as still minimal
and necessary: every one of those four symbols is referenced,
directly or transitively, by `govReapplyLanguage()`, which
`testLanguageSwitchReappliesGovernanceLabels` actually invokes; none
is unused. 160/160 re-confirmed passing, unchanged.

## 8. i18n Parity Strategy — Exact Count Compatibility Decision

**Decision: Option B (from the Stage 5 scope prompt) — parity +
minimum floor + explicit required-key set**, not Option A (keep exact
count) or a full rewrite (Option D). Evidence for the change: the
former `test_gov_key_parity_exact_count`'s literal `==` count had
already been bumped at every phase that added an approved `gov.*` key
(Faz 2.8.9, 2.8.11, 2.8.13, 2.8.14, and this phase's own Stage 4 — 5
times total), while never actually distinguishing "a key was
legitimately added" from "a key was silently deleted while another
was added, netting the same count." The exact total was never the
real invariant.

Replaced with `test_gov_key_parity_and_minimum_count` (renamed):

- EN/TR key-set parity — unchanged, still exact (`set(en_gov) ==
  set(tr_gov)`).
- No duplicate key within either language block — unchanged.
- **Floor, not exact match**: `len(en_gov) >= 104` — catches a bulk
  deletion regression without breaking on the next phase's legitimate
  additive keys. Only ever needs raising, never lowering.

A **new**, separate test,
`test_faz_2_8_16_required_gov_jrlist_keys_present`, pins the specific
24 Faz 2.8.16 keys as a named, explicit `frozenset` — catching the
deletion of any *one specific* key directly, which the aggregate
floor alone cannot do. It also re-verifies the 11 pre-existing
`gov.jrlist.*` keys (Faz 2.8.14) remain present alongside the 24 new
ones — **correcting a count claim** in the Stage 4 final report,
which said 14; the real, programmatically-verified number is 11
(this document and the test itself are the source of truth going
forward).

## 9. Required gov.jrlist Key Contract

`FAZ_2_8_16_REQUIRED_GOV_JRLIST_KEYS` (24 keys, defined in
`tests/test_faz_2_8_11_stage4_frontend.py`): `query_section_sub`,
`searchLabel`, `searchPlaceholder`, `searchButton`, `clearButton`,
`sortBy`, `sortOrder`, `ascending`, `descending`, `pageSize`,
`previous`, `next`, `results`, `pageOf`, `exportCsv`, `exporting`,
`loading`, `empty`, `error`, `export_error`, `sortJointRevisionId`,
`sortSourceStatus`, `sortCanonicalStatus`, `sortOutcome` (all under
the `gov.jrlist.` prefix). A new test,
`test_faz_2_8_16_required_gov_jrlist_key_values_are_real_translations`,
additionally verifies for every one of these 24 keys: present with a
non-`None` value in both EN and TR, neither value is empty/
whitespace-only, neither value equals the literal key name (no
placeholder-as-value mistake), and — since none of these 24 keys is a
short shared technical term/acronym — the EN and TR values are never
identical (verified against the real, current translations; no
allowlist was needed).

## 10. Used-vs-Defined Key Validation

Already covered, both before and after this Stage, by the dedicated
UX harness's `testAllUsedGovJrlistKeysExistInEnglish`/
`testAllUsedGovJrlistKeysExistInTurkish`/
`testEnAndTrGovJrlistKeySetsMatchExactly` (Stage 4) and by this
Stage's new `test_faz_2_8_16_required_gov_jrlist_key_values_are_real_translations`
(Python side). No orphaned/typo'd duplicate key was found in either
layer.

## 11. Backward Compatibility

Existing 5 pre-existing JS harnesses: unchanged, still run first, in
original order. `run_governance_workspace_tests.js`: untouched,
160/160. `test_translation_key_parity_between_tr_and_en` (whole-file
parity, not just `gov.*`): unchanged. `tests/test_run_quality_gate.py`
(21 tests): unchanged, all still passing — confirms the gate-order/
failure-propagation/JSON/Node-absence behavior this Stage's new tests
build on top of is itself untouched.

## 12. Source and Read-Only Safety

No backend file touched (`backend/governance/` diff is empty). No
`tests/governance/` file touched. No frontend behavior file touched
(`frontend/index.html` diff is empty — this Stage needed no frontend
fix). `tools/run_quality_gate.py` received exactly one additive line;
every other gate's logic, order, and reporting format is unchanged.

## 13. Out of Scope

New frontend UX features (none added). Backend/API/CSV contract
changes (none). VERSION/README/CHANGELOG (Stage 6). Adding
`run_governance_workspace_tests.js` to the gate (pre-existing,
unrelated gap — see Section 2).

## 14. Stage 6 Boundary

Stage 6 is expected to run the full validation/completion pass
(final full-suite + quality-gate re-verification, completion report,
product-backlog update, and the VERSION/README/CHANGELOG timing
decision recorded back in the Stage 0 report Section 13).

## 15. Test Strategy

`tests/test_quality_gate_joint_revision_ux.py` (new, 13 tests):
canonical-list membership/uniqueness/order, subprocess invocation
proof, and the negative-path failure proof (Section 5). 16 new
assertions added to the dedicated JS harness (Section 6, purely
additive). 3 tests changed/added in
`tests/test_faz_2_8_11_stage4_frontend.py` (one renamed with revised
semantics, two new) — see Section 8/9.

## 16. Acceptance Criteria

- New harness genuinely wired into the canonical gate (list
  membership + real subprocess invocation + failure/success proof, no
  real file ever broken for the proof).
- Gate step count remains 6/6; JS harness count within step 5 is now
  6, reported correctly in the gate's own output.
- All five pre-existing harnesses unchanged and still run.
- Dedicated harness 152/152 (136 original + 16 new, all additive).
- Governance harness 160/160, unchanged.
- Exact-count brittleness replaced with parity + floor + explicit
  required-set, with an evidence-based rationale recorded.
- 24/24 Faz 2.8.16 required keys verified present, non-empty,
  genuinely translated, in both EN and TR.
- No backend, no `tests/governance/`, no `frontend/index.html`, no
  VERSION/README/CHANGELOG change.
- Governance suite 517/517; full suite passing; quality gate 6/6.
