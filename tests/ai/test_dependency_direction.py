"""ADR-0017 Karar 2 -- static, one-way dependency-direction guard.

``backend.ai_gateway`` may import the existing deterministic/domain
packages (that direction is exercised functionally by the other
``tests/ai/*`` modules). This test proves the converse: none of those
packages, nor ``backend/app.py``, nor any existing ``backend/api``
route/dependency module, import anything from ``backend.ai_gateway`` --
with exactly one sanctioned exception (see ``SANCTIONED_ENTRY_POINTS``
below).

v3.0.0-alpha.4 note: ``backend.ai_gateway.orchestrator.handle_query``'s
own docstring always named a future HTTP route layer as "the *only*
function outside functions in this package that a future HTTP route
layer... is expected to call" -- i.e. exactly one consumer was always
the intended, planned exception to this guard, not a weakening of it.
``backend/api/routes/ai_gateway.py`` (Faz v3.0.0-alpha.4) is that
consumer, and is the only file this test now permits to import
``backend.ai_gateway``. Every other file under every guarded
directory/file below -- including every *other* file in
``backend/api`` -- is still held to the original, unweakened rule.

This phase also fixes a latent substring bug in the matcher below:
``"ai_gateway" in module_name`` would have false-positived on any
future module whose *own* name happens to contain the substring
"ai_gateway" (e.g. ``backend.api.routes.ai_gateway`` itself, or
``backend.app`` importing it) even though such a module does not
import the guarded ``backend.ai_gateway`` package at all. The matcher
now checks an exact dotted-prefix match instead
(``backend.ai_gateway`` or ``backend.ai_gateway.<anything>``), so
``backend/app.py``'s import of ``backend.api.routes.ai_gateway`` (a
different, unrelated module) is correctly never flagged.

Pure ``ast`` source inspection -- no package is actually imported here
beyond what pytest collection already does, so this test cannot be
fooled by import-time side effects and cannot itself introduce a
reverse dependency.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Directories that must never import backend.ai_gateway (ADR-0017
#: Karar 2 and Karar 13's "dokunulmayacak" list), except for the one
#: file named in SANCTIONED_ENTRY_POINTS.
GUARDED_DIRS = [
    "backend/engineering_core",
    "backend/vdi2230_core",
    "backend/calculation_engine",
    "backend/standards",
    "backend/question_bank",
    "backend/governance",
    "backend/production_validation",
    "backend/joints",
    "backend/library",
    "backend/api",
]

#: Individual files that must never import backend.ai_gateway.
GUARDED_FILES = [
    "backend/app.py",
]

#: The one, pre-planned exception (see module docstring): the
#: v3.0.0-alpha.4 HTTP route module, whose entire purpose is to call
#: backend.ai_gateway.orchestrator.handle_query. Nothing else under
#: GUARDED_DIRS/GUARDED_FILES is exempted.
SANCTIONED_ENTRY_POINTS = [
    "backend/api/routes/ai_gateway.py",
]

_GUARDED_PACKAGE = "backend.ai_gateway"


def _is_guarded_package_reference(module_name: str) -> bool:
    return module_name == _GUARDED_PACKAGE or module_name.startswith(_GUARDED_PACKAGE + ".")


def _module_imports_ai_gateway(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_guarded_package_reference(alias.name):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and _is_guarded_package_reference(node.module):
                return True
    return False


def _collect_offenders() -> List[str]:
    offenders: List[str] = []
    sanctioned = set(SANCTIONED_ENTRY_POINTS)

    for rel_dir in GUARDED_DIRS:
        base = REPO_ROOT / rel_dir
        if not base.exists():
            continue
        for py_file in sorted(base.rglob("*.py")):
            rel = str(py_file.relative_to(REPO_ROOT))
            if rel in sanctioned:
                continue
            if _module_imports_ai_gateway(py_file):
                offenders.append(rel)

    for rel_file in GUARDED_FILES:
        if rel_file in sanctioned:
            continue
        path = REPO_ROOT / rel_file
        if path.exists() and _module_imports_ai_gateway(path):
            offenders.append(rel_file)

    return offenders


def test_no_guarded_package_imports_ai_gateway():
    """The one-way dependency direction (ADR-0017 Karar 2): if this
    fails, some existing module has started depending on
    backend.ai_gateway, which breaks the "delete ai_gateway and
    nothing else changes" guarantee (ADR-0017 Karar 10)."""
    offenders = _collect_offenders()
    assert not offenders, (
        "The following files import backend.ai_gateway, violating "
        "ADR-0017 Karar 2's one-way dependency rule: " + ", ".join(offenders)
    )


def test_sanctioned_entry_point_is_the_only_ai_gateway_consumer():
    """The exception carved out above must stay exactly one file. If a
    second file starts importing backend.ai_gateway, it must be
    reviewed and either rejected or explicitly added to
    SANCTIONED_ENTRY_POINTS -- it must never silently pass this test
    as a side effect of the v3.0.0-alpha.4 exception."""
    assert SANCTIONED_ENTRY_POINTS == ["backend/api/routes/ai_gateway.py"]
    path = REPO_ROOT / SANCTIONED_ENTRY_POINTS[0]
    assert path.exists()
    assert _module_imports_ai_gateway(path)


def test_guarded_dirs_and_files_actually_exist():
    """Guards the guard: if the repository layout changes and one of
    these paths silently stops existing, this test fails loudly
    instead of test_no_guarded_package_imports_ai_gateway silently
    checking zero files."""
    missing = [
        rel
        for rel in GUARDED_DIRS + GUARDED_FILES
        if not (REPO_ROOT / rel).exists()
    ]
    assert not missing, f"Expected guarded paths are missing: {missing}"
