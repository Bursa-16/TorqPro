"""Phase 1.3 Engineering Library infrastructure tests.

Verifies registry behaviour and library metadata shells only. No
engineering_core, standards, API or frontend behaviour is touched by
these tests.
"""

import pytest

# Dual import path: repo root (backend.library) or backend/ on sys.path
# (CI import check), mirroring the engineering_core / standards test
# convention.
try:
    from backend.library import (
        BaseLibrary,
        LibraryMetadata,
        get_library,
        list_libraries,
        register,
        search,
        validate,
    )
    from backend.library import compatibility as compatibility_module
    from backend import engineering_core
    from backend import standards
    from backend import library
except ImportError:
    from library import (
        BaseLibrary,
        LibraryMetadata,
        get_library,
        list_libraries,
        register,
        search,
        validate,
    )
    from library import compatibility as compatibility_module
    import engineering_core
    import standards
    import library


def test_package_imports_without_side_effects():
    assert hasattr(library, "registry")
    assert hasattr(library, "bolt_library")


def test_all_expected_libraries_registered():
    names = {lib.metadata.name for lib in list_libraries()}
    expected = {
        "Bolt Library",
        "Nut Library",
        "Washer Library",
        "Thread Library",
        "Material Library",
        "Coating Library",
        "Lubrication Library",
        "Strength Class Library",
        "Compatibility Library",
    }
    assert expected.issubset(names)


def test_get_library_is_case_insensitive():
    lib = get_library("bolt library")
    assert lib.metadata.name == "Bolt Library"
    assert lib.metadata.organization == "TorqPro"


def test_get_library_unknown_raises_key_error():
    with pytest.raises(KeyError):
        get_library("NOPE LIBRARY")


def test_register_rejects_non_library():
    with pytest.raises(TypeError):
        register("not-a-library")


def test_list_libraries_returns_sorted_list():
    libs = list_libraries()
    keys = [lib.metadata.key for lib in libs]
    assert keys == sorted(keys)


def test_search_finds_by_organization():
    results = search("torqpro")
    assert len(results) >= 9
    assert all(isinstance(lib, BaseLibrary) for lib in results)


def test_search_empty_term_returns_empty_list():
    assert search("") == []
    assert search("   ") == []


def test_metadata_fields_present():
    lib = get_library("Nut Library")
    meta = lib.metadata
    assert isinstance(meta, LibraryMetadata)
    assert meta.name
    assert meta.version
    assert meta.organization
    assert meta.description
    assert meta.source_standard
    assert meta.status
    assert meta.record_count == 0
    assert meta.last_revision == ""
    assert isinstance(meta.supported_units, tuple)


def test_validate_well_formed_library_has_no_problems():
    lib = get_library("Washer Library")
    assert validate(lib) == []


def test_validate_flags_missing_fields():
    bad = BaseLibrary(metadata=LibraryMetadata(name="", organization="", status=""))
    problems = validate(bad)
    assert "name is required" in problems
    assert "organization is required" in problems
    assert "status is required" in problems


def test_validate_rejects_non_library():
    with pytest.raises(TypeError):
        validate("not-a-library")


def test_libraries_start_empty_no_migration_performed():
    for lib in list_libraries():
        assert lib.records == []
        assert lib.metadata.record_count == 0


def test_attach_source_is_ready_but_not_loaded_at_import():
    nut_lib = get_library("Nut Library")
    assert nut_lib.source_path == "data/ISO_898_2_Somun_Proof_Load.json"
    # Ready-to-read, but Phase 1.3 never calls this automatically.
    assert nut_lib.records == []


def test_load_from_source_reads_json_without_mutating_library():
    compat_lib = compatibility_module.COMPATIBILITY_LIBRARY
    records = compat_lib.load_from_source()
    assert isinstance(records, list)
    # Reading the source must not mutate the registered library state.
    assert compat_lib.records == []
    assert compat_lib.metadata.record_count == 0


def test_load_from_source_without_attached_path_raises():
    lib = BaseLibrary(metadata=LibraryMetadata(name="Unattached", organization="x", status="draft"))
    with pytest.raises(ValueError):
        lib.load_from_source()


def test_engineering_library_does_not_touch_engineering_core_or_standards():
    # Compare submodule names only: generic registry-style helper names
    # (register/get_*/list_*/search/validate) are intentionally shared
    # vocabulary across independent registries and are not a coupling.
    core_modules = {name for name in engineering_core.__all__ if name.islower()}
    standards_modules = {
        name for name in standards.__all__ if name.islower() and name != "register"
    }
    library_modules = {
        name for name in library.__all__ if name.islower() and name != "register"
    }
    assert not core_modules & library_modules
    assert not standards_modules & library_modules


def test_engineering_library_has_no_cross_package_imports():
    import ast
    import pathlib

    library_dir = pathlib.Path(library.__file__).resolve().parent
    for path in library_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "engineering_core" not in imported, f"{path.name} imports engineering_core"
        assert "standards" not in imported, f"{path.name} imports standards"
