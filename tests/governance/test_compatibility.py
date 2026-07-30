"""Faz 2.8.11 Stage 2 compatibility guard.

ADR-0014's Stage 2 scope is explicit: "No existing mechanism imports
or depends on it yet." This test enforces that mechanically rather
than relying on code review alone -- if a future change accidentally
wires ``backend.governance`` into ``backend.production_validation``,
``backend.joints``, ``backend.library``, or ``backend.app`` before an
explicit Stage 3/4/5 authorizes it, this test fails loudly.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Matches actual Python import statements only (``import backend.x``
#: or ``from backend.x import ...`` / ``from backend import x``), not
#: prose mentions inside docstrings or comments -- this package's own
#: docstrings intentionally *name* the four existing mechanisms (to
#: document what it must stay decoupled from), which is not itself a
#: dependency.
_IMPORT_LINE_PATTERN = re.compile(
    r"^\s*(import\s+[\w.]+|from\s+[\w.]+\s+import\s+)", re.MULTILINE
)


def _import_lines(text: str):
    return [
        line
        for line in text.splitlines()
        if _IMPORT_LINE_PATTERN.match(line)
    ]


#: Existing mechanisms that must not depend on backend.governance yet
#: (ADR-0014, "Compatibility strategy"). Paths are relative to the
#: repo root.
EXISTING_MECHANISM_PATHS = [
    REPO_ROOT / "backend" / "production_validation",
    REPO_ROOT / "backend" / "joints",
    REPO_ROOT / "backend" / "library",
    REPO_ROOT / "backend" / "app.py",
    REPO_ROOT / "backend" / "vdi2230_core",
    REPO_ROOT / "backend" / "calculation_engine",
    REPO_ROOT / "backend" / "engineering_core",
    REPO_ROOT / "backend" / "standards",
    REPO_ROOT / "backend" / "api",
]


def _python_files(path: Path):
    if path.is_file() and path.suffix == ".py":
        yield path
    elif path.is_dir():
        yield from path.rglob("*.py")


def test_no_existing_mechanism_imports_governance_package():
    offenders = []
    for mechanism_path in EXISTING_MECHANISM_PATHS:
        if not mechanism_path.exists():
            continue
        for py_file in _python_files(mechanism_path):
            for line in _import_lines(py_file.read_text(encoding="utf-8")):
                if "backend.governance" in line or "backend import governance" in line:
                    offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, (
        "Stage 2 requires backend.governance to be inert: the following "
        "existing files import it and must not: " + ", ".join(offenders)
    )


def test_governance_package_does_not_import_existing_mechanisms():
    """Symmetric check: backend.governance itself must not reach into
    any of the four existing mechanisms' modules via an actual import
    statement (it may exist alongside them, and its own docstrings
    may *name* them in prose, without depending on their internals)."""
    governance_path = REPO_ROOT / "backend" / "governance"
    forbidden_substrings = [
        "backend.production_validation",
        "backend.joints",
        "backend.library",
        "backend.app",
        "backend.vdi2230_core",
        "backend.calculation_engine",
        "backend.engineering_core",
        "backend.standards",
    ]
    offenders = []
    for py_file in _python_files(governance_path):
        for line in _import_lines(py_file.read_text(encoding="utf-8")):
            for forbidden in forbidden_substrings:
                if forbidden in line:
                    offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, "backend.governance must stay decoupled: " + "; ".join(offenders)


def test_governance_package_has_no_persistence_or_api_layer_yet():
    """Stage 2 scope guard: no JSON ledger file, no SQLite schema, and
    no FastAPI route decorator should exist under backend/governance/
    yet -- those are Stage 3 (event store/service) and Stage 4
    (additive API) concerns."""
    governance_path = REPO_ROOT / "backend" / "governance"
    data_dir = governance_path / "data"
    assert not data_dir.exists(), (
        "Stage 2 defines no persistence layer; backend/governance/data/ "
        "must not exist yet."
    )
    for py_file in _python_files(governance_path):
        text = py_file.read_text(encoding="utf-8")
        assert "@app." not in text and "APIRouter" not in text, (
            f"{py_file.relative_to(REPO_ROOT)} appears to define an API "
            "route; Stage 2 is contracts/models only."
        )
