"""Shared helper for "stage N touched no backend/VERSION/README/CHANGELOG
files" regression tests.

Root cause this replaces (see docs/phases/... post-mortem / the commit
message of the fix that introduced this module): every one of these
tests originally compared a fixed, historical "stage boundary" commit
to the literal, ever-advancing ``"HEAD"`` ref. That is only valid for
the narrow window between the stage finishing and the *next* commit
landing on ``main`` -- the moment any later, entirely legitimate stage
or phase adds a backend/VERSION/README/CHANGELOG change (as later
stages of the very same phase routinely, correctly do), the old test
starts failing even though nothing about the stage it actually
describes changed at all.

The fix is not a different single pinned commit (that only moves the
same problem to a new fixed point that will itself eventually be
overtaken) -- it is a **closed range**: both the start and the end of
the diff must be fixed, historical commits that both belong to the
stage being described. ``stage_range_changed_files()`` enforces that
shape and fails loudly (never silently) if a caller passes something
that looks like the old open-ended pattern, or a reversed/empty range.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

import pytest


def stage_range_changed_files(
    repo_root: Path, start_commit: str, end_commit: str
) -> List[str]:
    """Return the files changed in the closed range
    ``(start_commit, end_commit]`` -- both endpoints must be fixed,
    historical commit hashes belonging to the same completed stage.

    Never pass the literal string ``"HEAD"`` (or any other symbolic,
    moving ref) as ``end_commit`` -- that reintroduces exactly the
    fragility this helper exists to remove. Passing it raises
    immediately, before any git call, so the mistake is obvious at the
    call site rather than showing up as a mysterious later failure.

    Skips (does not fail) the calling test if either commit is not
    reachable in the current checkout (e.g. a shallow clone without
    full history) -- this matches the pre-existing behaviour of the
    tests this helper replaces, which is the correct behaviour for
    that specific situation (an environment limitation, not a stage
    regression).

    Raises ``AssertionError`` -- not a silent pass -- if the two
    commits are identical, or if ``start_commit`` is not an ancestor
    of ``end_commit`` (an empty or reversed range almost always means
    a bookkeeping mistake in the *test*, not that "nothing changed").
    """
    if end_commit.strip().upper() == "HEAD":
        raise AssertionError(
            "stage_range_changed_files() must be called with a fixed, "
            "historical end_commit -- never the literal 'HEAD' ref. "
            "Using HEAD reintroduces the moving-boundary bug this "
            "helper exists to prevent."
        )
    if start_commit == end_commit:
        raise AssertionError(
            f"stage_range_changed_files(): start_commit and end_commit "
            f"are identical ({start_commit!r}) -- an empty range is not "
            "a valid stage boundary; refusing to silently report zero "
            "changed files."
        )

    for label, commit in (("start_commit", start_commit), ("end_commit", end_commit)):
        reachable = subprocess.run(
            ["git", "cat-file", "-e", commit],
            capture_output=True, text=True, cwd=str(repo_root),
        )
        if reachable.returncode != 0:
            pytest.skip(
                f"{label} {commit!r} is not reachable in this checkout "
                "(e.g. a shallow clone without full history)"
            )

    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", start_commit, end_commit],
        cwd=str(repo_root),
    )
    if ancestor.returncode != 0:
        raise AssertionError(
            f"stage_range_changed_files(): start_commit {start_commit!r} is "
            f"not an ancestor of end_commit {end_commit!r} -- this is a "
            "reversed or unrelated commit range, not a valid stage "
            "boundary; refusing to treat it as an empty/passing diff."
        )

    result = subprocess.run(
        ["git", "diff", "--name-only", start_commit, end_commit],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    assert result.returncode == 0, result.stderr
    return [f for f in result.stdout.splitlines() if f.strip()]


__all__ = ["stage_range_changed_files"]
