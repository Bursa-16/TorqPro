"""Faz 2.8.11 Stage 2/3 compatibility guard.

ADR-0014's Stage 2/3 scope is explicit: "No existing mechanism
imports or depends on it yet," and Stage 3 adds "without connecting
it to existing production workflows or exposing API endpoints." This
test enforces both mechanically rather than relying on code review
alone -- if a future change accidentally wires ``backend.governance``
into ``backend.production_validation``, ``backend.joints``,
``backend.library``, or ``backend.app``, or adds an API route, before
an explicit Stage 4/5 authorizes it, this test fails loudly.
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


def _strip_triple_quoted_strings(text: str) -> str:
    """Remove ``\"\"\"...\"\"\"``/``'''...'''`` blocks (module, class and
    function docstrings) so prose mentions inside them don't trigger
    a false positive in code-content scans below. Not a full Python
    parser -- good enough for this repository's consistent docstring
    style (triple-double-quoted, never containing an escaped triple
    quote)."""
    return re.sub(r'"""[\s\S]*?"""', "", text)


def test_governance_package_never_references_washer_ledger_paths():
    """Explicit Stage 3 requirement: 'Existing washer resolution
    ledger must not be read, modified, migrated or reused.' Checked
    directly by scanning for the two washer ledger filenames anywhere
    in backend/governance/ source *outside* of docstrings (this
    package's own docstrings intentionally name them, in prose, to
    document what must stay untouched -- a hard-coded path string
    used in actual code would be the real violation)."""
    governance_path = REPO_ROOT / "backend" / "governance"
    forbidden_filenames = [
        "washer_resolution_ledger.json",
        "washer_resolution_decisions.json",
    ]
    offenders = []
    for py_file in _python_files(governance_path):
        code_only = _strip_triple_quoted_strings(py_file.read_text(encoding="utf-8"))
        for forbidden in forbidden_filenames:
            if forbidden in code_only:
                offenders.append(f"{py_file.relative_to(REPO_ROOT)} references {forbidden}")
    assert not offenders, "backend.governance must not reference washer ledgers: " + "; ".join(
        offenders
    )


def test_governance_package_has_no_default_data_directory():
    """Stage 3 defines a file-backed store class
    (``FileGovernanceEventStore``), but no default, hard-coded
    production data path -- every store instance in this package's
    own tests is constructed with an explicit, caller-supplied path
    (a temp directory). This guards against a future change silently
    introducing a shipped default path/directory under
    backend/governance/data/."""
    governance_path = REPO_ROOT / "backend" / "governance"
    data_dir = governance_path / "data"
    assert not data_dir.exists(), (
        "backend/governance/data/ must not exist -- the store's storage "
        "path is always caller-supplied, never a shipped default."
    )


def test_governance_package_has_no_api_layer_yet():
    """Stage 3 scope guard: no FastAPI route decorator or router
    should exist under backend/governance/ yet -- additive API
    endpoints are Stage 4 scope, not Stage 3."""
    governance_path = REPO_ROOT / "backend" / "governance"
    for py_file in _python_files(governance_path):
        text = py_file.read_text(encoding="utf-8")
        assert "@app." not in text and "APIRouter" not in text, (
            f"{py_file.relative_to(REPO_ROOT)} appears to define an API "
            "route; Stage 3 is event store/service layer only, no API."
        )
