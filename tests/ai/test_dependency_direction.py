"""ADR-0017 Karar 2 -- static, one-way dependency-direction guard.

``backend.ai_gateway`` may import the existing deterministic/domain
packages (that direction is exercised functionally by the other
``tests/ai/*`` modules). This test proves the converse: none of those
packages, nor ``backend/app.py`` nor the existing ``backend/api``
route/dependency modules, import anything from ``backend.ai_gateway``.

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
#: Karar 2 and Karar 13's "dokunulmayacak" list).
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


def _module_imports_ai_gateway(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "ai_gateway" in alias.name:
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and "ai_gateway" in node.module:
                return True
    return False


def _collect_offenders() -> List[str]:
    offenders: List[str] = []

    for rel_dir in GUARDED_DIRS:
        base = REPO_ROOT / rel_dir
        if not base.exists():
            continue
        for py_file in sorted(base.rglob("*.py")):
            if _module_imports_ai_gateway(py_file):
                offenders.append(str(py_file.relative_to(REPO_ROOT)))

    for rel_file in GUARDED_FILES:
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
