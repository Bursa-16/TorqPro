"""Phase 1.4 Library Migration infrastructure tests.

Verifies the loader, source manager, migration engine, validator,
search engine and the extended registry facade introduced in this
phase. No engineering_core, standards, API or frontend behaviour is
touched by these tests, and no existing JSON reference file is
modified.

Tests that must mutate a *shared, registered* library (to prove the
end-to-end facade wiring works against the real registry) always
restore that library's original empty state in a ``finally`` block,
so this file's own tests -- and the Phase 1.3 regression tests in
``test_engineering_library.py`` -- stay green regardless of collection
order.
"""

import hashlib

import pytest

# Dual import path: repo root (backend.library) or backend/ on sys.path
# (CI import check), mirroring the engineering_core / standards / Phase
# 1.3 engineering_library test convention.
try:
    from backend.library import (
        BaseLibrary,
        LibraryMetadata,
        get_library,
        library_registry,
        list_libraries,
    )
    from backend.library import loader as loader_module
    from backend.library import migration as migration_module
    from backend.library import source_manager as source_manager_module
    from backend.library import validator as validator_module
    # NOTE: imported via the dotted submodule path, not
    # ``from backend.library import search`` -- the package already
    # re-exports a function named ``search`` (Phase 1.3 keyword
    # search), so a bare ``from backend.library import search``-style
    # reference resolves to that function rather than this module.
    from backend.library.search import (
        CATEGORY_LIBRARY_MAP,
        search_by_category,
        search_by_keyword,
        search_by_standard,
    )
    from backend.library.search import search as combined_search
    from backend import library
except ImportError:
    from library import (
        BaseLibrary,
        LibraryMetadata,
        get_library,
        library_registry,
        list_libraries,
    )
    from library import loader as loader_module
    from library import migration as migration_module
    from library import source_manager as source_manager_module
    from library import validator as validator_module
    from library.search import (
        CATEGORY_LIBRARY_MAP,
        search_by_category,
        search_by_keyword,
        search_by_standard,
    )
    from library.search import search as combined_search
    import library


LibraryLoader = loader_module.LibraryLoader
MigrationEngine = migration_module.MigrationEngine
SourceManager = source_manager_module.SourceManager
compute_sha256 = source_manager_module.compute_sha256


# ---------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------


def test_loader_is_lazy_until_first_load():
    loader = LibraryLoader()
    lib = get_library("Coating Library")
    assert not loader.is_cached(lib)


def test_loader_reads_and_caches_records():
    loader = LibraryLoader()
    lib = get_library("Coating Library")
    records = loader.load(lib)
    assert isinstance(records, list)
    assert len(records) == 1
    assert loader.is_cached(lib)
    # Reading the source must not mutate the registered library itself.
    assert lib.records == []
    assert lib.metadata.record_count == 0


def test_loader_cache_is_isolated_between_loader_instances():
    lib = get_library("Coating Library")
    first_loader = LibraryLoader()
    first_loader.load(lib)
    second_loader = LibraryLoader()
    assert not second_loader.is_cached(lib)


def test_loader_reload_forces_fresh_read():
    loader = LibraryLoader()
    lib = get_library("Lubrication Library")
    first = loader.load(lib)
    second = loader.reload(lib)
    assert first == second
    assert loader.is_cached(lib)


def test_loader_clear_cache_single_and_all():
    loader = LibraryLoader()
    coating = get_library("Coating Library")
    lubrication = get_library("Lubrication Library")
    loader.load(coating)
    loader.load(lubrication)
    loader.clear_cache(coating)
    assert not loader.is_cached(coating)
    assert loader.is_cached(lubrication)
    loader.clear_cache()
    assert not loader.is_cached(lubrication)


def test_loader_raises_without_attached_source():
    loader = LibraryLoader()
    lib = get_library("Bolt Library")
    with pytest.raises(ValueError):
        loader.load(lib)


def test_extract_records_checks_records_then_rules_key():
    assert loader_module.extract_records({"records": [1, 2]}) == [1, 2]
    assert loader_module.extract_records({"rules": [3]}) == [3]
    assert loader_module.extract_records({"records": [], "rules": [9]}) == []
    assert loader_module.extract_records({"other": "x"}) == []
    assert loader_module.extract_records("not-a-dict") == []


def test_extract_records_reads_real_compatibility_rules():
    payload = loader_module.read_source_payload("data/Civata_Somun_Uyumluluk.json")
    rules = loader_module.extract_records(payload)
    assert len(rules) == 5
    assert rules[0]["bolt_class"] == "4.6"


# ---------------------------------------------------------------------
# Source manager
# ---------------------------------------------------------------------


def test_compute_sha256_matches_hashlib():
    path = "data/Surtunme_Veritabani.json"
    expected = hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert compute_sha256(path) == expected


def test_source_manager_track_and_mark_loaded():
    manager = SourceManager()
    tracked = manager.track(
        "Coating Library", "data/Surtunme_Veritabani.json", version="0.1", revision="draft"
    )
    assert tracked.library_key == "coating library"
    assert tracked.sha256 == compute_sha256("data/Surtunme_Veritabani.json")
    assert tracked.loaded_at is None

    loaded = manager.mark_loaded("Coating Library")
    assert loaded.loaded_at is not None
    assert manager.get("coating library") is loaded


def test_source_manager_mark_loaded_without_track_raises():
    manager = SourceManager()
    with pytest.raises(KeyError):
        manager.mark_loaded("Nonexistent Library")


def test_source_manager_all_and_clear():
    manager = SourceManager()
    manager.track("A", "data/Surtunme_Veritabani.json")
    manager.track("B", "data/Teknik_Kaynak_Kayitlari.json")
    assert set(manager.all().keys()) == {"a", "b"}
    manager.clear()
    assert manager.all() == {}


# ---------------------------------------------------------------------
# Migration engine
# ---------------------------------------------------------------------


def _fresh_engine():
    return MigrationEngine(loader=LibraryLoader(), source_manager=SourceManager())


def test_migration_plan_reports_no_source_for_unattached_library():
    lib = get_library("Bolt Library")
    plan = _fresh_engine().plan(lib)
    assert plan.status == "no_source"
    assert plan.source_path is None
    assert plan.record_count == 0


def test_migration_plan_does_not_mutate_registered_library():
    lib = get_library("Lubrication Library")
    plan = _fresh_engine().plan(lib)
    assert plan.status == "planned"
    assert plan.record_count == 1
    assert lib.records == []
    assert lib.metadata.record_count == 0


def test_migration_apply_populates_a_fresh_library_instance():
    fresh = BaseLibrary(
        metadata=LibraryMetadata(
            name="Migration Test Library",
            organization="TorqPro",
            status="draft",
            supported_units=("dimensionless",),
        )
    )
    fresh.attach_source("data/Surtunme_Veritabani.json")
    result = _fresh_engine().apply(fresh)
    assert result.records_migrated == 1
    assert fresh.records != []
    assert fresh.metadata.record_count == 1
    assert result.source_record is not None
    assert result.source_record.loaded_at is not None
    assert result.source_record.sha256 == compute_sha256("data/Surtunme_Veritabani.json")


def test_migration_apply_without_source_raises():
    fresh = BaseLibrary(
        metadata=LibraryMetadata(name="No Source Library", organization="TorqPro", status="draft")
    )
    with pytest.raises(ValueError):
        _fresh_engine().apply(fresh)


def test_migration_never_runs_automatically():
    # Importing loader/source_manager/migration/validator/search does not
    # populate any registered library by itself (mirrors the Phase 1.3
    # "libraries start empty" guarantee for this phase's new modules).
    for lib in list_libraries():
        assert lib.records == []
        assert lib.metadata.record_count == 0


# ---------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------


def test_find_duplicate_ids():
    records = [{"id": "A"}, {"id": "B"}, {"id": "A"}]
    issues = validator_module.find_duplicate_ids(records)
    assert len(issues) == 1
    assert issues[0].code == "duplicate_id"
    assert issues[0].record_index == 2


def test_find_duplicate_ids_skips_records_without_id_field():
    records = [{"name": "no id here"}]
    assert validator_module.find_duplicate_ids(records) == []


def test_find_missing_fields():
    records = [{"id": 1, "name": "x"}, {"id": 2, "name": ""}, {"id": 3}]
    issues = validator_module.find_missing_fields(records, required_fields=("id", "name"))
    assert len(issues) == 2
    assert {issue.record_index for issue in issues} == {1, 2}
    assert all(issue.code == "missing_field" for issue in issues)


def test_find_unit_mismatches():
    records = [{"id": 1, "unit": "mm"}, {"id": 2, "unit": "lbf"}]
    issues = validator_module.find_unit_mismatches(records, "unit", ("mm", "N", "MPa"))
    assert len(issues) == 1
    assert issues[0].code == "unit_mismatch"
    assert issues[0].record_index == 1


def test_find_unit_mismatches_noop_without_supported_units():
    records = [{"id": 1, "unit": "anything"}]
    assert validator_module.find_unit_mismatches(records, "unit", ()) == []


def test_is_valid_thread_designation():
    assert validator_module.is_valid_thread_designation("M8")
    assert validator_module.is_valid_thread_designation("M10x1.5")
    assert not validator_module.is_valid_thread_designation("not-a-thread")
    assert not validator_module.is_valid_thread_designation("")


def test_find_invalid_threads():
    records = [
        {"id": 1, "designation": "M8"},
        {"id": 2, "designation": "M10x1.5"},
        {"id": 3, "designation": "banana"},
    ]
    issues = validator_module.find_invalid_threads(records, thread_field="designation")
    assert len(issues) == 1
    assert issues[0].record_index == 2
    assert issues[0].code == "invalid_thread"


def test_find_invalid_materials():
    records = [{"id": 1, "material": "8.8"}, {"id": 2, "material": "unobtainium"}]
    issues = validator_module.find_invalid_materials(records, material_field="material")
    assert len(issues) == 1
    assert issues[0].record_index == 1
    assert issues[0].code == "invalid_material"


def test_find_broken_compatibility_on_real_production_rules():
    payload = loader_module.read_source_payload("data/Civata_Somun_Uyumluluk.json")
    rules = loader_module.extract_records(payload)
    # The shipped compatibility dataset must reference only recognised
    # bolt/nut property classes.
    assert validator_module.find_broken_compatibility(rules) == []


def test_find_broken_compatibility_flags_unknown_classes():
    rules = [{"bolt_class": "99.9", "minimum_nut_class": "99"}]
    issues = validator_module.find_broken_compatibility(rules)
    assert len(issues) == 2
    assert all(issue.code == "broken_compatibility" for issue in issues)


def test_validate_records_report_helpers():
    records = [{"id": "A"}, {"id": "A"}]
    report = validator_module.validate_records(records, id_field="id", subject="demo")
    assert report.subject == "demo"
    assert not report.is_valid
    assert report.count_by_code() == {"duplicate_id": 1}


def test_validate_records_with_no_applicable_checks_is_valid():
    report = validator_module.validate_records([{"id": 1}, {"id": 2}])
    assert report.is_valid


def test_validate_library_on_empty_registered_library_has_no_issues():
    lib = get_library("Nut Library")
    report = validator_module.validate_library(lib)
    assert report.is_valid


# ---------------------------------------------------------------------
# Search engine
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "category,expected_name",
    [
        ("bolt", "Bolt Library"),
        ("nut", "Nut Library"),
        ("washer", "Washer Library"),
        ("material", "Material Library"),
        ("thread", "Thread Library"),
        ("coating", "Coating Library"),
        ("strength_class", "Strength Class Library"),
        ("strength class", "Strength Class Library"),
    ],
)
def test_search_by_category(category, expected_name):
    found = search_by_category(category)
    assert found is not None
    assert found.metadata.name == expected_name


def test_search_by_category_unknown_returns_none():
    assert search_by_category("gizmo") is None


def test_search_by_keyword_matches_registry_search():
    assert search_by_keyword("torqpro") == library.search("torqpro")


def test_search_by_standard():
    results = search_by_standard("ISO 898-1")
    names = {lib.metadata.name for lib in results}
    assert "Bolt Library" in names
    assert "Material Library" in names


def test_search_by_standard_empty_term_returns_empty_list():
    assert search_by_standard("") == []


def test_search_combined_filters_intersect():
    results = combined_search(keyword="torqpro", category="bolt")
    assert len(results) == 1
    assert results[0].metadata.name == "Bolt Library"


def test_search_with_no_filters_returns_everything():
    assert combined_search() == list_libraries()


def test_search_package_level_names_match_search_module():
    assert library.search_by_category("bolt") is search_by_category("bolt")
    assert library.CATEGORY_LIBRARY_MAP == CATEGORY_LIBRARY_MAP
    assert library.search_advanced is combined_search


# ---------------------------------------------------------------------
# Registry facade (register / get / list / search / validate / load /
# reload / statistics)
# ---------------------------------------------------------------------


def test_facade_register_get_list_search_validate_delegate_correctly():
    assert library_registry.get("bolt library").metadata.name == "Bolt Library"
    assert library_registry.list() == list_libraries()
    assert library_registry.search(keyword="torqpro") == library.search("torqpro")
    assert library_registry.validate(get_library("Washer Library")) == []


def test_facade_statistics_shape_for_single_library():
    stats = library_registry.statistics("Bolt Library")
    assert set(stats.keys()) == {
        "record_count",
        "revision",
        "duplicates",
        "missing_fields",
        "source",
        "status",
    }
    assert stats["record_count"] == 0
    assert stats["status"] == "draft"


def test_facade_statistics_for_all_libraries():
    stats = library_registry.statistics()
    names = {lib.metadata.name for lib in list_libraries()}
    assert names.issubset(stats.keys())


def test_facade_load_and_reload_round_trip_and_restore_state():
    lib = get_library("Lubrication Library")
    assert lib.records == []
    try:
        loaded = library_registry.load("Lubrication Library")
        assert loaded.records != []
        assert loaded.metadata.record_count == len(loaded.records)

        stats = library_registry.statistics("Lubrication Library")
        assert stats["record_count"] == len(loaded.records)

        reloaded = library_registry.reload("Lubrication Library")
        assert reloaded.records == loaded.records
    finally:
        lib.replace_records([])
        loader_module.default_loader.clear_cache(lib)
        source_manager_module.default_source_manager.clear()

    assert lib.records == []
    assert lib.metadata.record_count == 0


def test_facade_load_without_source_raises_and_leaves_library_untouched():
    lib = get_library("Bolt Library")
    with pytest.raises(ValueError):
        library_registry.load("Bolt Library")
    assert lib.records == []
    assert lib.metadata.record_count == 0


# ---------------------------------------------------------------------
# Package-level hygiene: no coupling to engineering_core/standards,
# no circular imports, Phase 1.3 behaviour preserved.
# ---------------------------------------------------------------------


def test_new_modules_do_not_touch_engineering_core_or_standards():
    import ast
    import pathlib

    library_dir = pathlib.Path(library.__file__).resolve().parent
    new_modules = {
        "loader.py",
        "source_manager.py",
        "migration.py",
        "validator.py",
        "search.py",
        "facade.py",
    }
    for path in library_dir.glob("*.py"):
        if path.name not in new_modules:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "engineering_core" not in imported, f"{path.name} imports engineering_core"
        assert "standards" not in imported, f"{path.name} imports standards"


def test_package_still_exposes_phase_1_3_search_function_unshadowed():
    # Loading the new search.py submodule must not silently replace the
    # Phase 1.3 keyword-search function re-exported as `library.search`.
    assert callable(library.search)
    assert library.search("torqpro") == search_by_keyword("torqpro")


def test_json_reference_files_are_never_written_by_this_phase():
    import os

    paths = (
        "data/Civata_Somun_Uyumluluk.json",
        "data/ISO_898_2_Somun_Proof_Load.json",
        "data/Pul_Sertlik_Yuzey_Basinci.json",
        "data/Surtunme_Veritabani.json",
    )
    before = {path: os.path.getmtime(path) for path in paths}

    # Read every attached source through a fresh loader (and via a
    # fresh migration engine, which also computes SHA-256 checksums).
    LibraryLoader().load(get_library("Coating Library"))
    _fresh_engine().plan(get_library("Nut Library"))
    loader_module.read_source_payload("data/Civata_Somun_Uyumluluk.json")

    after = {path: os.path.getmtime(path) for path in paths}
    assert before == after
