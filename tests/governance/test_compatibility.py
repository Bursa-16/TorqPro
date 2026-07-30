"""Faz 2.8.11 Stage 2/3/4 compatibility guard.

ADR-0014's Stage 2/3 scope was "no existing mechanism imports or
depends on it yet," and Stage 3 added "without connecting it to
existing production workflows or exposing API endpoints." Stage 4
authorizes exactly **one** new coupling point: ``backend/app.py``
additively mounting ``backend.governance.api``'s router (task item 1,
"Mount the governance API additively onto the existing
`backend.app.app`"). This test enforces that everything else stays
exactly as isolated as before -- if a future change wires
``backend.governance`` into ``backend.production_validation``,
``backend.joints``, ``backend.library``, or any part of
``backend/app.py`` beyond that one approved router-mount import,
before an explicit Stage 5 authorizes it, this test fails loudly.
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


#: Existing mechanisms that must not depend on backend.governance,
#: except for the one Stage 4-approved exception handled explicitly
#: in test_no_existing_mechanism_imports_governance_package below
#: (backend/app.py's single router-mount import). Paths are relative
#: to the repo root.
EXISTING_MECHANISM_PATHS = [
    REPO_ROOT / "backend" / "production_validation",
    REPO_ROOT / "backend" / "joints",
    REPO_ROOT / "backend" / "library",
    REPO_ROOT / "backend" / "app.py",
    REPO_ROOT / "backend" / "vdi2230_core",
    REPO_ROOT / "backend" / "calculation_engine",
    REPO_ROOT / "backend" / "engineering_core",
    REPO_ROOT / "backend" / "standards",
    REPO_ROOT / "backend" / "api" / "routes",
]

#: The exact, sole Stage 4-approved import of backend.governance from
#: outside the package -- backend/app.py mounting the governance
#: router. Any other import line containing "backend.governance"
#: anywhere in EXISTING_MECHANISM_PATHS is still a violation.
_APPROVED_APP_PY_IMPORT_SUBSTRING = "from backend.governance.api import router as governance_router"


def _python_files(path: Path):
    if path.is_file() and path.suffix == ".py":
        yield path
    elif path.is_dir():
        yield from path.rglob("*.py")


def test_no_existing_mechanism_imports_governance_package_except_the_one_approved_mount():
    offenders = []
    for mechanism_path in EXISTING_MECHANISM_PATHS:
        if not mechanism_path.exists():
            continue
        for py_file in _python_files(mechanism_path):
            for line in _import_lines(py_file.read_text(encoding="utf-8")):
                if "backend.governance" not in line and "backend import governance" not in line:
                    continue
                is_app_py = py_file == REPO_ROOT / "backend" / "app.py"
                is_the_approved_line = _APPROVED_APP_PY_IMPORT_SUBSTRING in line
                if is_app_py and is_the_approved_line:
                    continue  # the one Stage 4-approved coupling point
                offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, (
        "Only backend/app.py's single governance-router mount import is "
        "approved (Stage 4); the following additional import(s) are not: "
        + ", ".join(offenders)
    )


def test_app_py_mounts_governance_router_exactly_once():
    """The inverse check: the one approved coupling point must exist
    exactly once (not duplicated, not silently dropped)."""
    app_py = REPO_ROOT / "backend" / "app.py"
    text = app_py.read_text(encoding="utf-8")
    assert text.count(_APPROVED_APP_PY_IMPORT_SUBSTRING) == 1
    assert text.count("app.include_router(governance_router)") == 1


def test_governance_package_does_not_import_existing_mechanisms():
    """Symmetric check: backend.governance itself must not reach into
    any of the four existing mechanisms' modules via an actual import
    statement (it may exist alongside them, and its own docstrings
    may *name* them in prose, without depending on their internals).
    ``backend.api.dependencies`` (the shared, mechanism-agnostic auth
    dependency every TorqPro endpoint already uses) is deliberately
    *not* in this forbidden list -- reusing it is Stage 4's approved
    "no new authentication mechanism" requirement, not a coupling to
    any of the four production mechanisms."""
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
        "backend.api.routes",
    ]
    offenders = []
    for py_file in _python_files(governance_path):
        for line in _import_lines(py_file.read_text(encoding="utf-8")):
            for forbidden in forbidden_substrings:
                if forbidden in line:
                    offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, "backend.governance must stay decoupled: " + "; ".join(offenders)


def test_governance_api_only_imports_the_approved_auth_dependency():
    """Even narrower than the general check above: confirm
    backend/governance/api.py's only import reaching outside
    backend.governance is exactly ``backend.api.dependencies``."""
    api_py = REPO_ROOT / "backend" / "governance" / "api.py"
    outside_imports = [
        line.strip()
        for line in _import_lines(api_py.read_text(encoding="utf-8"))
        if "backend" in line and "backend.governance" not in line
    ]
    assert outside_imports == ["from backend.api.dependencies import user"]


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
    (a temp directory), and the Stage 4 API resolves it lazily from
    an environment variable with no fallback path. This guards
    against a future change silently introducing a shipped default
    path/directory under backend/governance/data/."""
    governance_path = REPO_ROOT / "backend" / "governance"
    data_dir = governance_path / "data"
    assert not data_dir.exists(), (
        "backend/governance/data/ must not exist -- the store's storage "
        "path is always caller-supplied, never a shipped default."
    )


def test_governance_api_defines_only_the_nine_approved_write_routes_and_two_read_routes():
    """Stage 4 scope guard: exactly the approved endpoint set exists
    under backend/governance/api.py -- no extra route was added, and
    none of the nine write routes or two read routes is missing."""
    from backend.governance.api import router

    paths = sorted({route.path for route in router.routes})
    expected = sorted(
        {
            "/api/governance/{aggregate_id}/history",
            "/api/governance/{aggregate_id}/status",
            "/api/governance/review/{aggregate_id}/submit",
            "/api/governance/review/{aggregate_id}/approve",
            "/api/governance/review/{aggregate_id}/reject",
            "/api/governance/publication/{aggregate_id}/activate",
            "/api/governance/publication/{aggregate_id}/supersede",
            "/api/governance/publication/{aggregate_id}/archive",
            "/api/governance/resolution/{aggregate_id}/resolve",
            "/api/governance/resolution/{aggregate_id}/reject",
            "/api/governance/resolution/{aggregate_id}/waive",
        }
    )
    assert paths == expected
