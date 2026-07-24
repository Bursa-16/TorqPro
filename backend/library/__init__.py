"""TorqPro Engineering Library (Phase 1.3 + Phase 1.4 infrastructure).

Independent professional engineering data layer, separate from the
calculation engine.

Phase 1.3 introduced the registry and per-domain metadata shells.
Phase 1.4 adds the data layer around them -- lazy loading, source
provenance, a migration engine and validation/search -- without
changing any existing behaviour:

- No engineering formulas were moved or changed
  (``backend.engineering_core`` is untouched).
- No standards metadata was moved or changed
  (``backend.standards`` is untouched).
- No records are migrated automatically from the existing JSON
  reference files under ``data/``; those files remain the current
  source of truth and are never modified. Loading/migrating a
  library's records is only possible via an explicit call.
- No API or frontend behaviour changed.

Modules:
- registry:               LibraryMetadata / BaseLibrary / register /
                           get_library / list_libraries / search / validate
- bolt_library:            bolt/screw/stud master definitions (shell)
- nut_library:             nut master definitions (shell)
- washer_library:          washer master definitions (shell)
- thread_library:          thread geometry definitions (shell)
- material_library:        material property sets (shell)
- coating_library:         surface/coating specifications (shell)
- lubrication_library:     lubricant specs and friction conditions (shell)
- friction_condition_library: combination-dependent friction data
                            (coating+lubricant+condition pairing;
                            Faz 2.6.2A shell, no records yet)
- strength_class_library:  bolt/nut property class reference (shell)
- compatibility:           bolt/nut/washer compatibility rule set (shell)
- oem_library:              adapter-only reference into backend.standards
                            for OEM norms (Faz 2.4.0; carries no data
                            of its own)
- loader:                  lazy, cached JSON source reader
- source_manager:          source/version/SHA-256/revision/load-time tracking
- migration:               JSON -> registry migration engine (infrastructure)
- validator:               duplicate/missing-field/unit/thread/material/
                           compatibility record validation
- search:                  category/keyword/standard search
- facade:                  LibraryRegistry combining register/get/list/
                           search/validate/load/reload/statistics
- population:              Faz 2.4.1 engineering database population
                           (backend/library/data/*.json -> registry)
                           plus the find_bolt/find_nut/find_material/
                           find_thread/find_coating/find_lubrication/
                           list_strength_classes/list_oems search API
"""

from __future__ import annotations

from .registry import (
    BaseLibrary,
    LibraryMetadata,
    get_library,
    list_libraries,
    register,
    search,
    validate,
)
from . import (
    bolt_library,
    coating_library,
    compatibility,
    friction_condition_library,
    joint_hardware_library,
    lubrication_library,
    material_library,
    nut_library,
    oem_library,
    strength_class_library,
    thread_library,
    washer_library,
)
from . import loader, migration, population, source_manager, validator

# Imported via the dotted submodule path (not ``from . import search``):
# the package already re-exports a function named ``search`` (the
# Phase 1.3 keyword search above), so ``from . import search`` would
# just resolve to that existing attribute instead of loading this
# module. The category/keyword/standard search lives at
# ``search_advanced`` / ``search_by_category`` / etc. below instead of
# under the name ``search`` to avoid any ambiguity for callers.
from .search import (
    CATEGORY_LIBRARY_MAP,
    search_by_category,
    search_by_keyword,
    search_by_standard,
)
from .search import search as search_advanced
from .facade import LibraryRegistry, library_registry
from .population import (
    find_bolt,
    find_coating,
    find_joint_hardware_by_standard,
    find_joint_hardware_by_type,
    find_lubrication,
    find_material,
    find_nut,
    find_thread,
    find_washer_by_material,
    find_washer_by_size,
    find_washer_by_standard,
    find_washer_for_bolt,
    find_washer_locking,
    find_washer_temperature,
    list_oems,
    list_strength_classes,
    populate_all,
    populate_library,
)

# Loading the ``search`` submodule just above causes Python to
# automatically rebind the ``backend.library.search`` package
# attribute to that submodule, as a side effect of importing it for
# the first time. Re-bind the Phase 1.3 keyword-search FUNCTION as the
# package-level ``search`` name so existing callers of
# ``backend.library.search(...)`` keep working unchanged.
from .registry import search  # noqa: F811  (intentional re-bind, see above)

__all__ = [
    "LibraryMetadata",
    "BaseLibrary",
    "register",
    "get_library",
    "list_libraries",
    "search",
    "validate",
    "bolt_library",
    "nut_library",
    "washer_library",
    "thread_library",
    "material_library",
    "coating_library",
    "lubrication_library",
    "friction_condition_library",
    "strength_class_library",
    "compatibility",
    "oem_library",
    "joint_hardware_library",
    "loader",
    "source_manager",
    "migration",
    "validator",
    "search_advanced",
    "search_by_category",
    "search_by_keyword",
    "search_by_standard",
    "CATEGORY_LIBRARY_MAP",
    "LibraryRegistry",
    "library_registry",
    "population",
    "populate_all",
    "populate_library",
    "find_bolt",
    "find_nut",
    "find_material",
    "find_thread",
    "find_coating",
    "find_lubrication",
    "find_washer_by_standard",
    "find_washer_by_size",
    "find_washer_by_material",
    "find_washer_for_bolt",
    "find_washer_locking",
    "find_washer_temperature",
    "find_joint_hardware_by_type",
    "find_joint_hardware_by_standard",
    "list_strength_classes",
    "list_oems",
]
