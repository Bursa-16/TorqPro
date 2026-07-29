"""Faz 2.8.10 Stage 3 -- global TR/EN translation key-parity guard.

Every existing frontend regression harness (tests/js/run_i18n_tests.js
and the four Faz 2.8.6-2.8.9 harnesses it inspired) only spot-checks a
handful of ``I18N`` keys relevant to its own feature. None of them
walks the *entire* ``I18N.en`` / ``I18N.tr`` key sets in
frontend/index.html and asserts they are identical -- the Stage 1
Quality Gap Report (Sec. 2.3) identified this as a real gap: a future
phase could add an ``en`` key without its ``tr`` counterpart (or vice
versa) and every existing test would still pass.

This module closes that gap with one dedicated, permanent check. It is
deliberately pure Python (regex/brace-counting over the raw HTML text,
the same technique the JS harnesses already use to extract
declarations) rather than a Node subprocess: the check only needs to
read `I18N`'s literal key text, never execute any frontend JavaScript,
so there is nothing here for Node's `vm` module to add. This also
means the test can never be silently skipped for a Node-provisioning
reason -- it has no Node dependency to be absent in the first place,
which is the simplest possible way to guarantee this quality gate
always actually runs when the person runs `pytest -q`.

Expected key counts/sets are discovered from frontend/index.html
itself every run -- nothing here is a hardcoded number. The two sides
are compared against each other, not against a fixed target, so this
test tracks whatever the real file contains today and will correctly
fail the moment the two sides diverge in the future, in either
direction.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_PATH = REPO_ROOT / "frontend" / "index.html"

_KEY_RE = re.compile(r"'([a-zA-Z0-9_.]+)':")


def _match_balanced_braces(text: str, open_brace_index: int) -> int:
    """Return the index of the ``}`` that closes the ``{`` at
    ``open_brace_index``, honoring nested braces. Mirrors the
    brace-counting technique already used by every JS harness's
    ``extractConstDecl``/``extractFunctionDecl`` (just ported to
    Python, since this check never needs to execute the extracted
    JavaScript -- only locate its text boundaries)."""
    assert text[open_brace_index] == "{", "expected '{' at the given index"
    depth = 0
    i = open_brace_index
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise AssertionError("unbalanced braces: no matching '}' found for I18N object")


def _extract_object_block(text: str, start_search_at: int) -> tuple[str, int]:
    """Return (block_text_including_braces, index_just_after_block)
    for the next top-level ``{ ... }`` object starting at or after
    ``start_search_at``."""
    open_idx = text.index("{", start_search_at)
    close_idx = _match_balanced_braces(text, open_idx)
    return text[open_idx:close_idx + 1], close_idx + 1


def _load_i18n_en_tr_blocks() -> tuple[str, str]:
    """Locate ``const I18N = { en: {...}, tr: {...} }`` in
    frontend/index.html and return the raw text of the ``en`` and
    ``tr`` sub-objects, regardless of which one is declared first."""
    assert FRONTEND_PATH.exists(), f"frontend file missing: {FRONTEND_PATH}"
    html = FRONTEND_PATH.read_text(encoding="utf-8")

    decl_match = re.search(r"\bconst\s+I18N\s*=", html)
    assert decl_match, "const I18N = {...} declaration not found in frontend/index.html"

    i18n_block, _ = _extract_object_block(html, decl_match.end())

    en_match = re.search(r"\ben\s*:\s*\{", i18n_block)
    tr_match = re.search(r"\btr\s*:\s*\{", i18n_block)
    assert en_match, "I18N.en sub-object not found"
    assert tr_match, "I18N.tr sub-object not found"

    en_block, _ = _extract_object_block(i18n_block, en_match.end() - 1)
    tr_block, _ = _extract_object_block(i18n_block, tr_match.end() - 1)
    return en_block, tr_block


def _keys_in_block(block: str) -> list[str]:
    """All single-quoted translation-key occurrences in a block, in
    source order, with duplicates preserved (duplicate detection needs
    the raw occurrence list, not a de-duplicated set)."""
    return _KEY_RE.findall(block)


# Faz 2.8.10 Stage 3's duplicate-key check (below) found two
# pre-existing duplicate keys already present in frontend/index.html,
# in both I18N.en and I18N.tr: 'hizli.enter_parameters' (identical
# value both times) and 'yetenek.oem_tmin_tmax' (the two declarations
# differ slightly: "OEM t_min / t_max" vs "OEM t_min/t_max"). A
# duplicate object-literal key is harmless at runtime -- JavaScript
# silently keeps only the later declaration -- but it is still real,
# pre-existing frontend content debt.
#
# Fixing it means removing lines from frontend/index.html, which is a
# frontend production-code change; Stage 3's scope is explicitly
# backend-test-only ("no frontend production changes unless a
# testability defect makes it absolutely unavoidable" -- this is a
# real content defect, not a defect in the *test's* ability to detect
# it, so it is reported rather than fixed here). This explicit,
# reviewed baseline lets the duplicate-key tests below still catch any
# *new* duplicate a future change might introduce, without failing on
# this already-known, separately-reported issue.
_KNOWN_PRE_EXISTING_DUPLICATE_KEYS = frozenset({
    "hizli.enter_parameters",
    "yetenek.oem_tmin_tmax",
})


def test_i18n_en_and_tr_blocks_are_present_and_non_empty():
    """Sanity precondition for every other test in this module: if a
    future frontend refactor ever changes the I18N declaration shape
    enough that extraction itself fails, that must show up as a clear,
    named assertion failure here -- not as a confusing KeyError/
    AssertionError deep inside one of the parity checks below."""
    en_block, tr_block = _load_i18n_en_tr_blocks()
    assert len(en_block) > 0
    assert len(tr_block) > 0
    assert len(_keys_in_block(en_block)) > 0, "I18N.en contains no translation keys"
    assert len(_keys_in_block(tr_block)) > 0, "I18N.tr contains no translation keys"


def test_i18n_en_and_tr_key_counts_are_identical():
    """Total key-occurrence counts (including any duplicates) must
    match between EN and TR. This is a coarser, cheaper check than the
    full key-set comparison below, kept separate so a count mismatch
    reports as its own clearly-labeled failure rather than only
    surfacing indirectly via the set-difference messages."""
    en_block, tr_block = _load_i18n_en_tr_blocks()
    en_keys = _keys_in_block(en_block)
    tr_keys = _keys_in_block(tr_block)
    assert len(en_keys) == len(tr_keys), (
        f"I18N.en has {len(en_keys)} key occurrences but I18N.tr has "
        f"{len(tr_keys)} -- translation key counts must match exactly."
    )


def test_i18n_en_and_tr_key_sets_are_identical():
    """The core parity guard: every key present in one language must
    be present in the other, with no extras on either side. On
    failure, the affected keys are listed explicitly (sorted, for a
    deterministic/reproducible failure message) so the person can go
    straight to the missing translation(s) instead of re-deriving the
    diff themselves.
    """
    en_block, tr_block = _load_i18n_en_tr_blocks()
    en_keys = set(_keys_in_block(en_block))
    tr_keys = set(_keys_in_block(tr_block))

    missing_in_tr = sorted(en_keys - tr_keys)
    missing_in_en = sorted(tr_keys - en_keys)

    assert not missing_in_tr, (
        f"{len(missing_in_tr)} key(s) present in I18N.en but missing from "
        f"I18N.tr: {missing_in_tr}"
    )
    assert not missing_in_en, (
        f"{len(missing_in_en)} key(s) present in I18N.tr but missing from "
        f"I18N.en: {missing_in_en}"
    )
    assert en_keys == tr_keys


def test_i18n_en_block_has_no_duplicate_keys():
    """A duplicate key within a single JS object literal silently
    overwrites the earlier value at runtime (no error, no warning) --
    exactly the kind of defect that is invisible to every existing
    feature-scoped JS harness (they only check that *a* translation
    for their keys exists, not that each key was declared exactly
    once). Detected here by comparing the raw occurrence list against
    its de-duplicated set; failure lists the duplicated key(s) sorted
    for a deterministic message.

    Excludes the Stage 3 known-pre-existing-duplicates baseline (see
    ``_KNOWN_PRE_EXISTING_DUPLICATE_KEYS``) so this test guards against
    *new* duplicates without failing on the two already-known,
    separately-reported ones.
    """
    en_block, _ = _load_i18n_en_tr_blocks()
    en_keys = _keys_in_block(en_block)
    seen = set()
    duplicates = sorted(
        {k for k in en_keys if k in seen or seen.add(k)} - _KNOWN_PRE_EXISTING_DUPLICATE_KEYS
    )
    assert not duplicates, f"I18N.en contains new duplicate key(s): {duplicates}"


def test_i18n_tr_block_has_no_duplicate_keys():
    """TR-side counterpart of test_i18n_en_block_has_no_duplicate_keys
    -- see that test's docstring for the rationale and the baseline
    exclusion."""
    _, tr_block = _load_i18n_en_tr_blocks()
    tr_keys = _keys_in_block(tr_block)
    seen = set()
    duplicates = sorted(
        {k for k in tr_keys if k in seen or seen.add(k)} - _KNOWN_PRE_EXISTING_DUPLICATE_KEYS
    )
    assert not duplicates, f"I18N.tr contains new duplicate key(s): {duplicates}"


def test_i18n_key_parity_module_has_no_node_dependency():
    """Faz 2.8.10 Stage 3 requirement: Node absence must cause an
    explicit test failure, not a silent skip. This module satisfies
    that by construction -- it never shells out to `node` and carries
    no ``pytest.mark.skipif(not NODE_AVAILABLE, ...)`` guard like the
    existing JS-harness wrapper tests do, so there is no Node
    dependency for its absence to silently skip in the first place.
    This test verifies that stays true by inspecting the actual
    runtime module (imported names and pytest markers), not by
    searching this file's own text -- a text search here would be
    self-referential, since the assertion strings themselves would
    always contain the substrings they're checking for.
    """
    this_module = sys.modules[__name__]
    assert not hasattr(this_module, "subprocess"), (
        "this module must not import subprocess -- it must never shell out to node"
    )
    for name in dir(this_module):
        if not name.startswith("test_"):
            continue
        obj = getattr(this_module, name)
        marks = getattr(obj, "pytestmark", [])
        assert not marks, (
            f"{name} carries pytest marker(s) {marks} -- this module's tests "
            "must always run unconditionally, never be conditionally skipped "
            "(e.g. for Node availability)"
        )
    """Guards the exclusion list itself (``_KNOWN_PRE_EXISTING_DUPLICATE_KEYS``).

    If a future change removes one of these two known duplicates
    (fixing the underlying frontend defect), this test fails with a
    clear "stale baseline" message so the exclusion list gets updated
    to reflect the fix, rather than silently keeping a now-unnecessary
    exclusion. If a *new* duplicate is ever added alongside these two,
    the two tests above already catch that independently regardless of
    what happens here.
    """
    en_block, tr_block = _load_i18n_en_tr_blocks()
    for label, block in (("en", en_block), ("tr", tr_block)):
        keys = _keys_in_block(block)
        seen: set[str] = set()
        actual_duplicates = {k for k in keys if k in seen or seen.add(k)}
        assert actual_duplicates == set(_KNOWN_PRE_EXISTING_DUPLICATE_KEYS), (
            f"I18N.{label} duplicate-key set changed from the Stage 3 baseline "
            f"{sorted(_KNOWN_PRE_EXISTING_DUPLICATE_KEYS)} to {sorted(actual_duplicates)} "
            "-- if the duplicates were fixed, update "
            "_KNOWN_PRE_EXISTING_DUPLICATE_KEYS in this file; if new ones "
            "appeared, that is a real regression."
        )
