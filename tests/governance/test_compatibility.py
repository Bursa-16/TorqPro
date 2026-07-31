"""Faz 2.8.11 Stage 2/3/4/5 + Faz 2.8.12 Stage 2 compatibility guard.

Stage 2/3 scope was "no existing mechanism imports or depends on it
yet," and Stage 3 added "without connecting it to existing production
workflows or exposing API endpoints." Stage 4 authorized exactly
**one** new coupling point: ``backend/app.py`` additively mounting
``backend.governance.api``'s router. Stage 5 authorized exactly
**one more**, in the opposite direction: ``backend/governance/
adapters/washer_resolution.py`` reading from
``backend.library.washer_resolution*`` (read-only, no governance
event is ever written by it -- see that module's own docstring).

Faz 2.8.12 Stage 2 (ADR-0015, "Compatibility boundary update")
explicitly widened that opposite-direction exception to **two more**
files: ``backend/governance/adapters/washer_resolution_sync.py`` and
``backend/governance/adapters/washer_resolution_reconciliation.py``.
Unlike the Stage 5 adapter, these two *do* write governance events --
but only via the existing, unmodified
``backend.governance.service`` command functions (never by inventing
a second persistence path); see
``test_write_adapters_never_bypass_the_governance_service_layer``
below.

No existing mechanism module may import ``backend.governance`` beyond
the Stage 4 exception, and no governance module besides these three
approved adapter files may import an existing mechanism -- this test
enforces both boundaries mechanically.
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
#: router. Kept under its own name (rather than folded into the set
#: below) because ``test_app_py_mounts_governance_router_exactly_once``
#: checks this one, specific line's count independently of the Stage
#: 3 additions.
_APPROVED_APP_PY_ROUTER_IMPORT_SUBSTRING = (
    "from backend.governance.api import router as governance_router"
)

#: Faz 2.8.12 Stage 3 (ADR-0015 "Compatibility boundary update,
#: Stage 3 addendum"): the washer resolution decide endpoint's
#: best-effort governance synchronization call site. Exactly two new
#: import lines, both inside that one endpoint function (local
#: imports, matching this endpoint's existing style for every other
#: washer-module import) -- no other governance import may appear
#: anywhere else in backend/app.py.
_APPROVED_APP_PY_STAGE3_IMPORT_SUBSTRINGS = frozenset(
    {
        "from backend.governance.adapters.washer_resolution_sync import (",
        "from backend.governance.api import resolve_governance_store",
    }
)

#: The full, closed set of governance-import lines approved anywhere
#: in backend/app.py, across both Stage 4 (router mount) and Stage 3
#: (washer sync call site).
_APPROVED_APP_PY_IMPORT_SUBSTRINGS = frozenset(
    {_APPROVED_APP_PY_ROUTER_IMPORT_SUBSTRING} | _APPROVED_APP_PY_STAGE3_IMPORT_SUBSTRINGS
)

#: The one Stage 5-approved, read-only adapter file allowed to import
#: FROM an existing mechanism (the opposite direction from the rule
#: above). Kept as its own name (rather than folded into the plural
#: set below) because several narrower tests below apply to this
#: specific file only (its read-only guarantee, its governance.store/
#: service isolation) and must not be loosened by the Stage 2
#: write-path files' addition.
_APPROVED_ADAPTER_PATH = (
    REPO_ROOT / "backend" / "governance" / "adapters" / "washer_resolution.py"
)

#: The two Faz 2.8.12 Stage 2-approved write-path files (ADR-0015),
#: allowed to import FROM an existing mechanism alongside the Stage 5
#: adapter above. Every other file under backend/governance/
#: (including any future file under backend/governance/adapters/ not
#: listed here) must still have zero such imports.
_APPROVED_WRITE_ADAPTER_PATHS = frozenset(
    {
        REPO_ROOT / "backend" / "governance" / "adapters" / "washer_resolution_sync.py",
        REPO_ROOT
        / "backend"
        / "governance"
        / "adapters"
        / "washer_resolution_reconciliation.py",
    }
)

#: The Faz 2.8.12 Stage 4.2-approved read-only joint revision adapter
#: (module-level imports limited to the two backend.joints submodules
#: with no backend.app dependency -- exceptions.py/schema.py;
#: backend.joints.service is imported only inside a function body,
#: checked separately below).
_APPROVED_JOINT_REVISION_ADAPTER_PATH = (
    REPO_ROOT / "backend" / "governance" / "adapters" / "joint_revision.py"
)

#: All files approved to import an existing mechanism, across every
#: direction/stage established so far (read-only Stage 5 + write-path
#: Stage 2 + read-only Stage 4.2).
_APPROVED_MECHANISM_IMPORTING_PATHS = frozenset(
    {_APPROVED_ADAPTER_PATH, _APPROVED_JOINT_REVISION_ADAPTER_PATH}
    | _APPROVED_WRITE_ADAPTER_PATHS
)


def _python_files(path: Path):
    if path.is_file() and path.suffix == ".py":
        yield path
    elif path.is_dir():
        yield from path.rglob("*.py")


def test_no_existing_mechanism_imports_governance_package_except_the_approved_lines():
    offenders = []
    for mechanism_path in EXISTING_MECHANISM_PATHS:
        if not mechanism_path.exists():
            continue
        for py_file in _python_files(mechanism_path):
            for line in _import_lines(py_file.read_text(encoding="utf-8")):
                if "backend.governance" not in line and "backend import governance" not in line:
                    continue
                is_app_py = py_file == REPO_ROOT / "backend" / "app.py"
                is_an_approved_line = any(
                    approved in line for approved in _APPROVED_APP_PY_IMPORT_SUBSTRINGS
                )
                if is_app_py and is_an_approved_line:
                    continue  # Stage 4 router mount or Stage 3 washer sync call site
                offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, (
        "Only backend/app.py's approved governance import lines "
        f"({sorted(_APPROVED_APP_PY_IMPORT_SUBSTRINGS)}) are approved; the following "
        "additional import(s) are not: " + ", ".join(offenders)
    )


def test_app_py_mounts_governance_router_exactly_once():
    """The inverse check: the Stage 4 router-mount coupling point must
    exist exactly once (not duplicated, not silently dropped)."""
    app_py = REPO_ROOT / "backend" / "app.py"
    text = app_py.read_text(encoding="utf-8")
    assert text.count(_APPROVED_APP_PY_ROUTER_IMPORT_SUBSTRING) == 1
    assert text.count("app.include_router(governance_router)") == 1


def test_app_py_calls_the_washer_sync_call_site_exactly_once():
    """Faz 2.8.12 Stage 3 inverse check: the washer decide endpoint's
    governance synchronization call site must exist exactly once."""
    app_py = REPO_ROOT / "backend" / "app.py"
    text = app_py.read_text(encoding="utf-8")
    assert text.count("sync_washer_decision_and_log(decision, resolve_governance_store())") == 1
    for substring in _APPROVED_APP_PY_STAGE3_IMPORT_SUBSTRINGS:
        assert text.count(substring) == 1


def test_governance_package_does_not_import_existing_mechanisms():
    """Symmetric check: backend.governance itself must not reach into
    any of the four existing mechanisms' modules via an actual import
    statement (it may exist alongside them, and its own docstrings
    may *name* them in prose, without depending on their internals).
    ``backend.api.dependencies`` (the shared, mechanism-agnostic auth
    dependency every TorqPro endpoint already uses) is deliberately
    *not* in this forbidden list -- reusing it is Stage 4's approved
    "no new authentication mechanism" requirement, not a coupling to
    any of the four production mechanisms. The three ADR-0015/Stage
    5-approved adapter files
    (:data:`_APPROVED_MECHANISM_IMPORTING_PATHS`) are excluded from
    this scan and checked by their own, narrower tests below
    instead."""
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
        if py_file in _APPROVED_MECHANISM_IMPORTING_PATHS:
            continue
        for line in _import_lines(py_file.read_text(encoding="utf-8")):
            for forbidden in forbidden_substrings:
                if forbidden in line:
                    offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, "backend.governance must stay decoupled: " + "; ".join(offenders)


def test_only_the_approved_adapters_import_an_existing_mechanism():
    """The Stage 5 + Stage 2 (ADR-0015) adapter exception is exactly
    three files. No other file under backend/governance/adapters/ (or
    anywhere else in the package) may import from an existing
    mechanism."""
    adapters_path = REPO_ROOT / "backend" / "governance" / "adapters"
    forbidden_substrings = [
        "backend.production_validation",
        "backend.joints",
        "backend.app",
        "backend.vdi2230_core",
        "backend.calculation_engine",
        "backend.engineering_core",
        "backend.standards",
        "backend.api.routes",
    ]
    offenders = []
    for py_file in _python_files(adapters_path):
        if py_file in _APPROVED_MECHANISM_IMPORTING_PATHS:
            continue
        for line in _import_lines(py_file.read_text(encoding="utf-8")):
            for forbidden in forbidden_substrings:
                if forbidden in line:
                    offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {line.strip()}")
            if "backend.library" in line:
                offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {line.strip()}")
    assert not offenders, (
        "only the three ADR-0015-approved adapter files may import an "
        "existing mechanism: " + "; ".join(offenders)
    )


def test_exactly_four_files_are_approved_to_import_an_existing_mechanism():
    """Inverse guard: the approved-file allowlist itself must name
    exactly four real, existing files -- catches an allowlist entry
    silently going stale (e.g. a rename) as loudly as a new,
    unapproved import would be caught above."""
    assert len(_APPROVED_MECHANISM_IMPORTING_PATHS) == 4
    for path in _APPROVED_MECHANISM_IMPORTING_PATHS:
        assert path.is_file(), f"approved adapter path does not exist: {path}"


def test_approved_adapter_only_imports_washer_resolution_modules():
    """Narrower still: the one approved adapter file may only reach
    into ``backend.library.washer_resolution*`` -- not production
    validation, joints, app.py, or any other washer library module it
    doesn't need."""
    text = _APPROVED_ADAPTER_PATH.read_text(encoding="utf-8")
    outside_imports = [
        line.strip()
        for line in _import_lines(text)
        if "backend" in line and "backend.governance" not in line
    ]
    for line in outside_imports:
        assert "washer_resolution" in line, f"unexpected external import: {line}"
    assert any("backend.library" in line for line in outside_imports)


def test_approved_adapter_never_imports_governance_store_or_service():
    """The adapter must be read-only with respect to the governance
    event store too -- it has no way to append a governance event."""
    text = _APPROVED_ADAPTER_PATH.read_text(encoding="utf-8")
    for line in _import_lines(text):
        assert "governance.store" not in line
        assert "governance.service" not in line
    assert "store.append(" not in text
    assert "FileGovernanceEventStore(" not in text


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


def test_read_only_adapter_exposes_no_mutation_or_persistence_methods():
    """Stage 5 rule: 'Do not expose mutation, transition or
    persistence methods through adapters.' Applies to the original
    read-only adapter only -- the two Faz 2.8.12 Stage 2 write-path
    files (ADR-0015) are, by design, not read-only, and are covered
    instead by the AST-based boundary tests below (which verify they
    write *exclusively* through the existing, unmodified
    ``backend.governance.service`` command functions, never through a
    second, self-invented persistence path)."""
    text = _APPROVED_ADAPTER_PATH.read_text(encoding="utf-8")
    forbidden_defs = (
        "def submit_", "def approve_", "def reject_", "def activate_",
        "def supersede_", "def archive_", "def resolve_", "def waive_",
        "def append(", "def write(", "def save(", "def delete(", "def update(",
    )
    offenders = [forbidden for forbidden in forbidden_defs if forbidden in text]
    assert not offenders, "read-only adapter must not define: " + ", ".join(offenders)


def test_governance_api_defines_only_the_nine_approved_write_routes_and_four_read_routes():
    """Stage 4 scope guard, extended by Faz 2.8.13 Stage 2 and Faz
    2.8.14 Stage 3: exactly the approved endpoint set exists under
    backend/governance/api.py -- no extra route was added, and none
    of the nine write routes or four read routes (two generic + the
    single-record joint-revision projection route + the new bulk
    joint-revisions projection route) is missing."""
    from backend.governance.api import router

    paths = sorted({route.path for route in router.routes})
    expected = sorted(
        {
            "/api/governance/{aggregate_id}/history",
            "/api/governance/{aggregate_id}/status",
            "/api/governance/joint-revision/{revision_id}",
            "/api/governance/joint-revisions",
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


def test_joint_revision_route_is_get_only():
    """Faz 2.8.13 Stage 2 scope guard: the new joint-revision
    projection route accepts exactly ``GET`` -- no ``POST``,
    ``PUT``, ``PATCH``, or ``DELETE`` method was introduced for it,
    matching the approved Stage 1 contract's "no write route" rule."""
    from backend.governance.api import router

    joint_revision_routes = [
        route
        for route in router.routes
        if route.path == "/api/governance/joint-revision/{revision_id}"
    ]
    assert len(joint_revision_routes) == 1
    assert joint_revision_routes[0].methods == {"GET"}


def test_no_write_route_exists_for_joint_revision():
    """Inverse guard, restated at the whole-router level: no route
    path under ``/api/governance/`` contains ``joint-revision`` and
    accepts a mutating HTTP method."""
    from backend.governance.api import router

    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}
    offenders = [
        (route.path, route.methods)
        for route in router.routes
        if "joint-revision" in route.path and (route.methods & mutating_methods)
    ]
    assert not offenders, f"unexpected mutating method(s) on a joint-revision route: {offenders}"


def test_governance_api_may_import_the_approved_joint_revision_adapter():
    """Positive check, mirroring the existing approved-import tests
    for the write-path adapters: ``backend/governance/api.py`` is
    expected to import ``backend.governance.adapters.joint_revision``
    at module level -- this is an intra-package import (never a
    direct import of ``backend.joints`` itself), and is exactly the
    one new coupling point Faz 2.8.13 Stage 2 approved."""
    api_path = REPO_ROOT / "backend" / "governance" / "api.py"
    text = api_path.read_text(encoding="utf-8")
    assert any(
        "backend.governance.adapters.joint_revision" in line for line in _import_lines(text)
    ), "expected backend/governance/api.py to import the approved joint_revision adapter"


def test_joint_revision_route_handler_calls_no_governance_write_or_persistence_function():
    """AST-based guard: the new route handler's own function body
    must not reference any governance write/persistence surface --
    no ``svc.<transition function>`` call, no ``store.append``, no
    ``FileGovernanceEventStore(`` construction, no
    ``get_governance_store``/``resolve_governance_store`` dependency.
    This is a narrower, route-specific restatement of the adapter's
    own "never writes anywhere" guarantee, verifying the handler
    wrapped around it doesn't add a write path the adapter itself
    doesn't have."""
    api_path = REPO_ROOT / "backend" / "governance" / "api.py"
    tree = _parse(api_path)

    handler = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "governance_joint_revision":
            handler = node
            break
    assert handler is not None, "governance_joint_revision handler not found"

    source = ast.get_source_segment(api_path.read_text(encoding="utf-8"), handler) or ""
    forbidden_substrings = (
        "svc.",
        "store.append",
        "FileGovernanceEventStore(",
        "get_governance_store",
        "resolve_governance_store",
        "GovernanceEvent(",
    )
    offenders = [forbidden for forbidden in forbidden_substrings if forbidden in source]
    assert not offenders, (
        "joint-revision route handler references a governance write/persistence "
        f"surface: {offenders}"
    )


# ---------------------------------------------------------------------
# Faz 2.8.14 Stage 3 -- joint revisions bulk route (additive, read-only)
# ---------------------------------------------------------------------


def test_joint_revisions_bulk_route_is_get_only():
    """The new bulk route accepts exactly ``GET`` -- no ``POST``,
    ``PUT``, ``PATCH``, or ``DELETE`` was introduced for it, matching
    the approved Stage 1 contract's "no mutation" rule."""
    from backend.governance.api import router

    bulk_routes = [
        route for route in router.routes if route.path == "/api/governance/joint-revisions"
    ]
    assert len(bulk_routes) == 1
    assert bulk_routes[0].methods == {"GET"}


def test_no_write_route_exists_for_joint_revisions_bulk():
    """Restated, route-specific guard (the whole-router substring
    check above already covers this by construction, since
    'joint-revision' is a substring of 'joint-revisions', but this
    test proves it directly against the exact bulk path rather than
    relying on that substring relationship)."""
    from backend.governance.api import router

    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}
    bulk_routes = [
        route for route in router.routes if route.path == "/api/governance/joint-revisions"
    ]
    assert bulk_routes and not (bulk_routes[0].methods & mutating_methods)


def test_joint_revisions_bulk_route_handler_calls_the_bulk_adapter():
    """AST-level proof that the handler calls
    ``project_joint_revisions_bulk`` -- the one approved adapter
    function for this route -- rather than reimplementing bulk
    projection logic inline."""
    api_path = REPO_ROOT / "backend" / "governance" / "api.py"
    tree = _parse(api_path)

    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "governance_joint_revisions_bulk"
    )
    called_names = {
        inner.func.id
        for inner in ast.walk(handler)
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
    }
    assert "project_joint_revisions_bulk" in called_names


def test_joint_revisions_bulk_route_handler_never_references_joints_service_directly():
    """AST-based guard: the handler must not import or reference
    ``backend.joints`` / ``joints_svc`` / ``joint_service`` directly --
    it may only reach the source through the approved
    ``project_joint_revisions_bulk`` adapter function, never bypass it
    to call the source service module itself."""
    api_path = REPO_ROOT / "backend" / "governance" / "api.py"
    tree = _parse(api_path)

    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "governance_joint_revisions_bulk"
    )
    source = ast.get_source_segment(api_path.read_text(encoding="utf-8"), handler) or ""
    for forbidden in ("joints_svc", "joint_service", "backend.joints", "list_joint_revisions("):
        assert forbidden not in source, (
            f"bulk route handler references forbidden name: {forbidden!r}"
        )


def test_joint_revisions_bulk_route_handler_calls_no_governance_write_or_persistence_function():
    """Same write/persistence-surface guard as the single-record route
    handler test above, applied to the new bulk route handler."""
    api_path = REPO_ROOT / "backend" / "governance" / "api.py"
    tree = _parse(api_path)

    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "governance_joint_revisions_bulk"
    )
    source = ast.get_source_segment(api_path.read_text(encoding="utf-8"), handler) or ""
    forbidden_substrings = (
        "svc.",
        "store.append",
        "FileGovernanceEventStore(",
        "get_governance_store",
        "resolve_governance_store",
        "GovernanceEvent(",
    )
    offenders = [forbidden for forbidden in forbidden_substrings if forbidden in source]
    assert not offenders, (
        "joint-revisions bulk route handler references a governance write/persistence "
        f"surface: {offenders}"
    )


def test_api_module_defines_no_second_outcome_status_mapping():
    """Only one outcome->HTTP-status mapping dictionary
    (`_JOINT_REVISION_OUTCOME_STATUS`) may exist in this file -- the
    new bulk route must not define a second one, since it always
    returns 200 for a well-formed request and therefore needs none."""
    api_path = REPO_ROOT / "backend" / "governance" / "api.py"
    tree = _parse(api_path)
    dict_assignments = [
        node.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.value, ast.Dict)
        and isinstance(node.target, ast.Name)
    ]
    assert dict_assignments == ["_JOINT_REVISION_OUTCOME_STATUS"], (
        f"expected exactly one outcome-status mapping, found: {dict_assignments}"
    )


# ---------------------------------------------------------------------
# Faz 2.8.12 Stage 2 -- AST-based boundary tests for the two
# ADR-0015-approved write-path files. These deliberately do not reuse
# the Stage 5 "adapters must be read-only" assumption (they are not
# read-only by design); instead they verify the *shape* of the write
# path itself: writes happen exclusively through the existing,
# unmodified backend.governance.service command functions, never
# through a self-invented persistence path, and reconciliation never
# duplicates sync_washer_decision's own classification/mapping logic.
# ---------------------------------------------------------------------

import ast  # noqa: E402

_SYNC_ADAPTER_PATH = (
    REPO_ROOT / "backend" / "governance" / "adapters" / "washer_resolution_sync.py"
)
_RECONCILIATION_ADAPTER_PATH = (
    REPO_ROOT / "backend" / "governance" / "adapters" / "washer_resolution_reconciliation.py"
)

#: The exact, closed set of backend.governance.service command
#: functions the sync adapter may import and call. Any other name
#: imported from that module (e.g. submit_review, approve_review --
#: functions belonging to lifecycle groups washer resolution has no
#: business touching) is a violation.
_APPROVED_SERVICE_COMMAND_NAMES = frozenset(
    {"resolve_resolution", "reject_resolution", "waive_resolution"}
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _importfrom_nodes(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield node


def _call_nodes(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _attribute_nodes(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            yield node


def test_sync_adapter_imports_only_the_three_approved_service_commands():
    """The sync adapter may import from ``backend.governance.service``
    (relative ``..service``) -- but only the exact three resolution
    commands washer resolution needs, never any review/publication
    command. It may also import the *type*
    ``GovernanceEventStore`` from ``backend.governance.store`` (for
    its own parameter annotation) but must never import
    ``FileGovernanceEventStore`` (the concrete, writable
    implementation) -- it only ever receives an already-constructed
    store from its caller, never builds one itself."""
    tree = _parse(_SYNC_ADAPTER_PATH)
    imported_from_service = set()
    for node in _importfrom_nodes(tree):
        module = node.module or ""
        is_governance_store_module = module == "store" and node.level == 2
        if module.endswith("service") or module == "backend.governance.service":
            imported_from_service.update(alias.name for alias in node.names)
        if is_governance_store_module:
            names = {alias.name for alias in node.names}
            assert names == {"GovernanceEventStore"}, (
                "sync adapter may only import the GovernanceEventStore type from "
                f"backend.governance.store, got {names}"
            )
    assert imported_from_service == _APPROVED_SERVICE_COMMAND_NAMES, (
        f"sync adapter must import exactly {_APPROVED_SERVICE_COMMAND_NAMES} from "
        f"backend.governance.service, got {imported_from_service}"
    )


def test_reconciliation_never_imports_governance_service_directly():
    """Delegation guard (ADR-0015, 'Preserve the Closed Allowlist'):
    reconciliation must never import
    ``backend.governance.service`` itself -- every governance write
    must flow through ``sync_washer_decision``, never a second,
    independently-written transition call. It may import the
    ``GovernanceEventStore`` *type* from ``backend.governance.store``
    (its own parameter annotation, mirroring the sync adapter) but
    never ``FileGovernanceEventStore``. Matched against the exact
    module string (``store``/``backend.governance.store``), not a
    suffix match, since ``backend.library.washer_resolution_decisions_
    store`` also happens to end in the substring ``store`` and is an
    unrelated, approved read-only import."""
    tree = _parse(_RECONCILIATION_ADAPTER_PATH)
    for node in _importfrom_nodes(tree):
        module = node.module or ""
        is_governance_service_module = module == "service" and node.level == 2
        is_governance_store_module = module == "store" and node.level == 2
        assert not is_governance_service_module, (
            f"reconciliation must not import backend.governance.service directly: "
            f"{ast.dump(node)}"
        )
        if is_governance_store_module:
            names = {alias.name for alias in node.names}
            assert names == {"GovernanceEventStore"}, (
                "reconciliation may only import the GovernanceEventStore type from "
                f"backend.governance.store, got {names}"
            )


def test_reconciliation_calls_sync_washer_decision_and_nothing_else_for_transitions():
    """AST-level delegation check: the only governance-transition-
    shaped call reconciliation ever makes is
    ``sync_washer_decision(...)`` -- it never calls
    ``resolve_resolution``/``reject_resolution``/``waive_resolution``/
    ``GovernanceEvent(...)`` itself, which would mean it duplicated
    the sync adapter's own transition logic instead of delegating to
    it."""
    tree = _parse(_RECONCILIATION_ADAPTER_PATH)
    called_names = set()
    for node in _call_nodes(tree):
        if isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called_names.add(node.func.attr)
    assert "sync_washer_decision" in called_names
    forbidden_direct_calls = _APPROVED_SERVICE_COMMAND_NAMES | {"GovernanceEvent"}
    overlap = called_names & forbidden_direct_calls
    assert not overlap, (
        "reconciliation must delegate to sync_washer_decision, not call these "
        f"directly: {overlap}"
    )


def test_write_adapters_never_call_store_append_directly():
    """Neither write-path file may call ``store.append(...)`` --
    persistence always happens inside
    ``backend.governance.service``'s own command functions, which the
    sync adapter calls instead. The parameter/local variable holding
    the governance store is named ``store`` in both files (checked
    directly, not inferred by type, so this is a precise AST check
    rather than a generic substring scan)."""
    for path in (_SYNC_ADAPTER_PATH, _RECONCILIATION_ADAPTER_PATH):
        tree = _parse(path)
        for node in _call_nodes(tree):
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "append":
                continue
            target = node.func.value
            target_name = target.id if isinstance(target, ast.Name) else None
            assert target_name != "store", (
                f"{path.relative_to(REPO_ROOT)} calls store.append() directly, "
                "bypassing backend.governance.service"
            )


def test_write_adapters_never_reference_store_private_helpers():
    """Neither write-path file may reach into
    ``FileGovernanceEventStore``'s private I/O internals
    (``_read_raw``, ``_write_raw_atomic``, ``_locked``,
    ``_process_lock``, ``_lock_path``) -- all store interaction must
    go through its public contract, exercised only indirectly via
    ``backend.governance.service``'s command functions."""
    forbidden_attrs = {"_read_raw", "_write_raw_atomic", "_locked", "_process_lock", "_lock_path"}
    for path in (_SYNC_ADAPTER_PATH, _RECONCILIATION_ADAPTER_PATH):
        tree = _parse(path)
        offenders = {
            node.attr for node in _attribute_nodes(tree) if node.attr in forbidden_attrs
        }
        assert not offenders, f"{path.relative_to(REPO_ROOT)} references: {offenders}"


def test_write_adapters_never_import_washer_write_functions():
    """Neither write-path file may import a washer *write* function
    (``append_decision``, ``record_decision`` from
    ``washer_resolution_decisions_store``, or anything from
    ``washer_resolution_service`` -- the module that actually
    orchestrates recording a new washer decision). Only read
    accessors (e.g. ``list_decisions``) may be imported."""
    forbidden_names = {"append_decision", "record_decision", "decide_resolution"}
    for path in (_SYNC_ADAPTER_PATH, _RECONCILIATION_ADAPTER_PATH):
        tree = _parse(path)
        for node in _importfrom_nodes(tree):
            module = node.module or ""
            assert "washer_resolution_service" not in module, (
                f"{path.relative_to(REPO_ROOT)} must not import from "
                f"washer_resolution_service (the washer write orchestration module): "
                f"{ast.dump(node)}"
            )
            imported = {alias.name for alias in node.names}
            overlap = imported & forbidden_names
            assert not overlap, (
                f"{path.relative_to(REPO_ROOT)} imports washer write function(s): {overlap}"
            )


def test_sync_adapter_never_defines_its_own_status_mapping_table():
    """ADR-0015, 'Preserve the Closed Allowlist': the approved
    washer-status -> governance-status mapping must come from exactly
    one canonical source
    (``backend.governance.adapters.washer_resolution._STATUS_MAP``).
    The sync adapter's own ``_SYNCABLE_STATUS_MAP`` must be built by
    filtering/deriving from that one table, not by independently
    listing washer statuses -> governance statuses a second time."""
    tree = _parse(_SYNC_ADAPTER_PATH)
    found_canonical_import = False
    for node in _importfrom_nodes(tree):
        module = node.module or ""
        if module.endswith("washer_resolution") and not module.endswith(
            "washer_resolution_sync"
        ) and not module.endswith("washer_resolution_reconciliation"):
            names = {alias.name for alias in node.names}
            if "_STATUS_MAP" in names:
                found_canonical_import = True
    assert found_canonical_import, (
        "sync adapter must import _STATUS_MAP from the Stage 5 read-only adapter "
        "(the single canonical mapping source) rather than defining its own table"
    )

    # Cross-check: every entry actually used at runtime is a subset of
    # the canonical table's EXACT-quality entries -- not a coincidence
    # of independently-chosen literal values.
    from backend.governance.adapters.washer_resolution import (
        MappingQuality,
        _STATUS_MAP as canonical_map,
    )
    from backend.governance.adapters.washer_resolution_sync import _SYNCABLE_STATUS_MAP

    expected = {
        status: canonical
        for status, (canonical, quality) in canonical_map.items()
        if quality == MappingQuality.EXACT and canonical is not None
    }
    assert _SYNCABLE_STATUS_MAP == expected


def test_no_fourth_file_imports_the_washer_mechanism():
    """Closed-allowlist guard, restated at the whole-package level:
    scanning every file under backend/governance/ (not just
    adapters/) for a ``backend.library`` import must find exactly the
    three washer-approved files -- proving that allowlist is
    exhaustive, not merely non-empty. The Stage 4.2 joint revision
    adapter is deliberately excluded from this expectation: it
    imports ``backend.joints``, never ``backend.library``."""
    governance_path = REPO_ROOT / "backend" / "governance"
    offenders = set()
    for py_file in _python_files(governance_path):
        for line in _import_lines(py_file.read_text(encoding="utf-8")):
            if "backend.library" in line:
                offenders.add(py_file)
    expected = frozenset({_APPROVED_ADAPTER_PATH}) | _APPROVED_WRITE_ADAPTER_PATHS
    assert offenders == expected, f"expected exactly {expected}, found {offenders}"


# ---------------------------------------------------------------------
# Faz 2.8.12 Stage 4.2 -- joint revision read-only adapter.
#
# Distinct from the washer write-path AST checks above: this adapter
# is read-only (like the Stage 5 washer adapter) but has its own,
# more delicate import-safety requirement -- the Stage 4.1 spike
# proved a real, deterministic circular import if
# backend.joints.service is ever imported at module level from any
# governance file. These tests enforce the mitigation mechanically,
# not just by docstring convention.
# ---------------------------------------------------------------------

_JOINT_REVISION_ADAPTER_PATH = (
    REPO_ROOT / "backend" / "governance" / "adapters" / "joint_revision.py"
)

#: Module-level imports from backend.joints this adapter is allowed
#: to have -- both have zero backend.app dependency (verified: no
#: import beyond `from __future__ import annotations` in either
#: file), so neither poses any circular-import risk.
_SAFE_JOINTS_MODULE_LEVEL_IMPORTS = frozenset(
    {"backend.joints.exceptions", "backend.joints.schema"}
)


def test_joint_revision_adapter_module_level_imports_are_safe_only():
    """No module-level import in this file may reference
    ``backend.joints.service`` or bare ``backend.joints`` (which would
    execute ``backend/joints/__init__.py`` then whatever the importer
    asks for next) -- only the two zero-dependency submodules
    (``exceptions``, ``schema``) are allowed at module level."""
    tree = _parse(_JOINT_REVISION_ADAPTER_PATH)
    for node in tree.body:  # module-level statements only, not nested in any function
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            full_module = ("." * node.level) + module
            if "joints" not in full_module and "backend.joints" not in full_module:
                continue
            assert full_module in _SAFE_JOINTS_MODULE_LEVEL_IMPORTS, (
                f"unsafe module-level joints import: {full_module} "
                f"(only {_SAFE_JOINTS_MODULE_LEVEL_IMPORTS} are allowed at module level)"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "joints" not in alias.name or alias.name in (
                    "backend.joints.exceptions",
                    "backend.joints.schema",
                ), f"unsafe module-level joints import: {alias.name}"


def test_joint_revision_service_is_imported_only_inside_a_function_body():
    """The one place ``backend.joints.service`` may be imported is
    inside a function body (deferred/lazy import) -- never at module
    level. Checked by confirming every AST node that imports
    ``backend.joints`` (specifically the ``service`` submodule) has a
    function definition as an ancestor, and that zero such imports
    exist directly in ``tree.body`` (module level)."""
    tree = _parse(_JOINT_REVISION_ADAPTER_PATH)

    # Module level: no `service` import anywhere.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "backend.joints":
            names = {alias.name for alias in node.names}
            assert "service" not in names, "backend.joints.service imported at module level"

    # At least one deferred (function-body) import of it exists.
    found_deferred_service_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.ImportFrom) and inner.module == "backend.joints":
                    if "service" in {alias.name for alias in inner.names}:
                        found_deferred_service_import = True
    assert found_deferred_service_import, (
        "expected a deferred (function-body) import of backend.joints.service"
    )


def test_joint_revision_adapter_exposes_no_mutation_or_persistence_methods():
    """Same read-only guarantee as the Stage 5 washer adapter, applied
    to the joint revision adapter."""
    text = _JOINT_REVISION_ADAPTER_PATH.read_text(encoding="utf-8")
    forbidden_defs = (
        "def submit_", "def approve_", "def reject_", "def activate_",
        "def supersede_", "def archive_", "def resolve_", "def waive_",
        "def create_", "def append(", "def write(", "def save(",
        "def delete(", "def update(",
    )
    offenders = [forbidden for forbidden in forbidden_defs if forbidden in text]
    assert not offenders, "joint revision adapter must not define: " + ", ".join(offenders)


def test_joint_revision_adapter_never_imports_governance_store_or_service():
    """Read-only with respect to the governance side too -- it has no
    way to append a governance event or call a transition command."""
    text = _JOINT_REVISION_ADAPTER_PATH.read_text(encoding="utf-8")
    for line in _import_lines(text):
        assert "governance.store" not in line
        assert "governance.service" not in line
        assert "resolve_resolution" not in line
        assert "reject_resolution" not in line
        assert "waive_resolution" not in line
        assert "submit_review" not in line
        assert "approve_review" not in line
        assert "reject_review" not in line
    assert "store.append(" not in text
    assert "FileGovernanceEventStore(" not in text


def test_joint_revision_adapter_has_no_raw_sql():
    """No direct SQL exists in the adapter -- every read goes through
    ``backend.joints.service.get_joint_revision``, never a
    hand-written query."""
    text = _JOINT_REVISION_ADAPTER_PATH.read_text(encoding="utf-8")
    for forbidden in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "conn()"):
        assert forbidden not in text, f"unexpected raw-SQL-shaped text: {forbidden!r}"


# ---------------------------------------------------------------------
# Faz 2.8.14 Stage 2 -- joint revision bulk projection (additive).
#
# The bulk function shares the same file (and therefore the same
# module-level-import, mutation-method, and no-raw-SQL guards above,
# which already scan the whole file), but it has its own, narrower
# guarantee worth checking explicitly: it must define no new status
# mapping of its own and must route every item through the existing
# canonical `project_joint_revision` call, never reimplement its
# logic.
# ---------------------------------------------------------------------


def test_joint_revision_bulk_function_defines_no_second_status_mapping():
    """Only one status-mapping dictionary (`_STATUS_MAP`) may exist in
    this file -- the bulk function must not define a second one under
    any name."""
    tree = _parse(_JOINT_REVISION_ADAPTER_PATH)
    dict_assignments = [
        node.targets[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Dict)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ] + [
        node.target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.value, ast.Dict)
        and isinstance(node.target, ast.Name)
    ]
    assert dict_assignments == ["_STATUS_MAP"], (
        f"expected exactly one module-level dict assignment (_STATUS_MAP), "
        f"found: {dict_assignments}"
    )


def test_joint_revision_bulk_function_calls_the_canonical_single_projection():
    """AST-level proof that `project_joint_revisions_bulk` routes each
    item through the existing `project_joint_revision` call rather
    than reimplementing status-mapping logic inline."""
    tree = _parse(_JOINT_REVISION_ADAPTER_PATH)
    bulk_func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "project_joint_revisions_bulk"
    )
    called_names = {
        inner.func.id
        for inner in ast.walk(bulk_func)
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
    }
    assert "project_joint_revision" in called_names


def test_joint_revision_bulk_function_calls_list_joint_revisions_not_get_joint_revision_only():
    """The bulk function must source its ids from the new
    `list_joint_revisions` accessor (via the shared `_joints_service()`
    helper) -- not invent its own per-joint iteration or reach for a
    different, unapproved source accessor."""
    text = _JOINT_REVISION_ADAPTER_PATH.read_text(encoding="utf-8")
    bulk_start = text.index("def project_joint_revisions_bulk")
    bulk_body = text[bulk_start:]
    assert "list_joint_revisions(" in bulk_body
    assert "_joints_service()" in bulk_body


def test_joint_revision_bulk_function_exposes_no_mutation_or_persistence_call():
    """Same read-only guarantee as the single-record adapter function,
    checked directly against the bulk function's own body via AST
    (not a whole-file substring scan) -- it must not call any store/
    governance-write function."""
    tree = _parse(_JOINT_REVISION_ADAPTER_PATH)
    bulk_func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "project_joint_revisions_bulk"
    )
    forbidden_calls = {"append", "save", "delete", "update", "commit"}
    called_names = {
        inner.func.attr
        for inner in ast.walk(bulk_func)
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
    }
    offenders = called_names & forbidden_calls
    assert not offenders, f"bulk function calls forbidden methods: {offenders}"


def test_joint_revision_bulk_function_importable_and_callable_in_a_clean_process(tmp_path):
    """Same clean-process regression guard as the single-record
    function (Faz 2.8.12 Stage 4.1), extended to the new bulk
    function -- the deferred-import mitigation must hold for it too."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(tmp_path / "clean_process_bulk.db")
    script = (
        "import sys; assert 'backend.app' not in sys.modules; "
        "from backend.governance.adapters.joint_revision import project_joint_revisions_bulk; "
        "result = project_joint_revisions_bulk(); "
        "print('OK', isinstance(result, list))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK True" in result.stdout


def test_governance_api_importable_in_a_clean_process():
    """Faz 2.8.12 Stage 4.1's proven risk, re-verified as a
    regression guard: importing ``backend.governance.api`` directly,
    in a brand-new Python process that has never imported
    ``backend.app``, must succeed. Run via subprocess (not the
    current pytest module cache, which already has ``backend.app``
    loaded via conftest.py and would hide this exact failure mode)."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; assert 'backend.app' not in sys.modules; "
            "from backend.governance.api import router; "
            "print('OK', router is not None)",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK True" in result.stdout


def test_joint_revision_adapter_importable_and_callable_in_a_clean_process(tmp_path):
    """The adapter module itself must be importable, and its
    projection function callable, in a brand-new process that has
    never imported ``backend.app`` -- proving the deferred-import
    mitigation actually works end to end, not just at the import
    statement level.

    Isolated ``TORQPRO_DB_PATH``/secret file (never the real repo's
    ``torqpro.db``); no explicit ``migrate()`` call is made on
    purpose -- doing so would itself require importing
    ``backend.app`` first, defeating the point of this exact test.
    Consequently the projection legitimately reports
    ``source_unavailable`` (no such table) rather than ``not_found``
    on this fresh, unmigrated database -- both are non-crash, safely
    classified outcomes; a properly migrated round trip is covered
    separately by this file's runtime unit tests."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(tmp_path / "clean_process.db")
    script = (
        "import sys; assert 'backend.app' not in sys.modules; "
        "from backend.governance.adapters.joint_revision import project_joint_revision; "
        "result = project_joint_revision(999999999); "
        "print('OK', result.outcome)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK not_found" in result.stdout or "OK source_unavailable" in result.stdout


def test_joint_revision_adapter_safe_after_normal_app_initialization(tmp_path):
    """The opposite, expected-safe order: ``backend.app`` fully
    initialized (and migrated) first, then the adapter -- must also
    succeed, and must correctly report ``not_found`` for a genuinely
    nonexistent id once the schema actually exists."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(tmp_path / "initialized.db")
    script = (
        "from backend.app import app, migrate; migrate(); "
        "from backend.governance.adapters.joint_revision import project_joint_revision; "
        "result = project_joint_revision(999999999); "
        "print('OK', result.outcome)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK not_found" in result.stdout


def test_joint_revision_adapter_reload_is_safe(tmp_path):
    """``importlib.reload`` of the adapter module must not break the
    deferred-import pattern (each call re-imports
    ``backend.joints.service`` fresh; reload just re-executes the
    module body, which defines the function again -- no cached,
    stale, module-level state to go wrong)."""
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["TORQPRO_SECRET_KEY"] = "x" * 64
    env["TORQPRO_DB_PATH"] = str(tmp_path / "reload.db")
    script = (
        "import importlib; "
        "from backend.governance.adapters import joint_revision as jr; "
        "jr.project_joint_revision(1); "
        "importlib.reload(jr); "
        "result = jr.project_joint_revision(1); "
        "print('OK', result.outcome)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
