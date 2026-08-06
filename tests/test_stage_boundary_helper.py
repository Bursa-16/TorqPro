"""Direct regression tests for tests/_stage_boundary.py.

Covers the acceptance-criteria gap found after the initial
fix/pre-existing-stage-boundary-tests delivery: an invalid (broken,
deleted, or unreachable) commit reference must fail loudly, never be
absorbed by a ``pytest.skip``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests._stage_boundary import stage_range_changed_files

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Two real, valid, evidence-backed commits from the same closed range
#: already used by the historical stage-boundary tests (Faz 2.8.19
#: Stage 2: "feat: add washer resolution queue frontend" as the end
#: commit). Reused here as a known-good baseline.
VALID_START = "58ca1d487c0f4bdfd7ac0937ed260d5ed98f6732"
VALID_END = "2481b21d240b51f49cd0f5b08b2e8ffdde48f29e"

#: Deliberately malformed/unreachable references -- not real commits,
#: not ambiguous prefixes of real commits.
INVALID_COMMIT = "0000000000000000000000000000000000000000"
GARBAGE_REF = "not-a-real-commit-reference"


class TestInvalidCommitFailsLoudly:
    def test_invalid_start_commit_raises_assertion_error(self):
        with pytest.raises(AssertionError) as exc_info:
            stage_range_changed_files(REPO_ROOT, INVALID_COMMIT, VALID_END)
        assert exc_info.type is AssertionError

    def test_invalid_end_commit_raises_assertion_error(self):
        with pytest.raises(AssertionError) as exc_info:
            stage_range_changed_files(REPO_ROOT, VALID_START, INVALID_COMMIT)
        assert exc_info.type is AssertionError

    def test_invalid_commit_is_never_skipped(self):
        # The specific regression this file exists to prevent: an
        # invalid commit must not be silently swallowed as a skip --
        # it must surface as a real, visible test failure.
        with pytest.raises(AssertionError):
            stage_range_changed_files(REPO_ROOT, INVALID_COMMIT, VALID_END)
        # (pytest.raises already fails the test if a Skipped exception
        # -- which subclasses BaseException, not AssertionError -- is
        # raised instead; this second, explicit assertion documents
        # the intent for a human reader rather than relying on that
        # implicitly.)

    def test_garbage_ref_also_raises_assertion_error(self):
        with pytest.raises(AssertionError):
            stage_range_changed_files(REPO_ROOT, GARBAGE_REF, VALID_END)

    def test_error_message_names_the_problematic_start_ref(self):
        with pytest.raises(AssertionError) as exc_info:
            stage_range_changed_files(REPO_ROOT, INVALID_COMMIT, VALID_END)
        message = str(exc_info.value)
        assert INVALID_COMMIT in message
        assert "start_commit" in message
        assert "start" in message

    def test_error_message_names_the_problematic_end_ref(self):
        with pytest.raises(AssertionError) as exc_info:
            stage_range_changed_files(REPO_ROOT, VALID_START, INVALID_COMMIT)
        message = str(exc_info.value)
        assert INVALID_COMMIT in message
        assert "end_commit" in message
        assert "end" in message

    def test_error_message_names_the_full_range_being_checked(self):
        with pytest.raises(AssertionError) as exc_info:
            stage_range_changed_files(REPO_ROOT, VALID_START, INVALID_COMMIT)
        message = str(exc_info.value)
        assert VALID_START in message
        assert INVALID_COMMIT in message


class TestEmptyReversedAndHeadStillGuarded:
    """Unchanged behaviour -- re-asserted here so a future edit to the
    invalid-commit path cannot accidentally weaken these three."""

    def test_identical_commits_raise(self):
        with pytest.raises(AssertionError):
            stage_range_changed_files(REPO_ROOT, VALID_START, VALID_START)

    def test_reversed_range_raises(self):
        with pytest.raises(AssertionError):
            stage_range_changed_files(REPO_ROOT, VALID_END, VALID_START)

    def test_literal_head_end_commit_raises(self):
        with pytest.raises(AssertionError):
            stage_range_changed_files(REPO_ROOT, VALID_START, "HEAD")


class TestValidRangeStillWorks:
    def test_valid_closed_range_returns_a_file_list(self):
        changed = stage_range_changed_files(REPO_ROOT, VALID_START, VALID_END)
        assert isinstance(changed, list)
        assert len(changed) > 0

    def test_valid_closed_range_contains_no_backend_or_release_files(self):
        changed = stage_range_changed_files(REPO_ROOT, VALID_START, VALID_END)
        assert not any(f.startswith("backend/") for f in changed)
        assert "VERSION" not in changed
        assert "README.md" not in changed
        assert "docs/CHANGELOG.md" not in changed

    def test_valid_closed_range_is_deterministic(self):
        first = stage_range_changed_files(REPO_ROOT, VALID_START, VALID_END)
        second = stage_range_changed_files(REPO_ROOT, VALID_START, VALID_END)
        assert first == second
