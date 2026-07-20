"""TorqPro Engineering Library - registry facade (Phase 1.4 infrastructure).

A single object exposing the full registry surface for this phase:
``register``, ``get``, ``list``, ``search``, ``validate`` (the
existing Phase 1.3 operations, delegated unchanged) plus the new
``load``, ``reload`` and ``statistics`` operations.

Composes ``registry.py`` with ``loader.py``, ``migration.py``,
``validator.py`` and ``search.py``. None of those modules import this
one, so there is no circular import: this facade sits on top of them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import loader as loader_module
from . import validator as validator_module
from .migration import MigrationEngine, default_migration_engine
from .registry import BaseLibrary
from .registry import get_library as _get_library
from .registry import list_libraries as _list_libraries
from .registry import register as _register
from .registry import validate as _validate_metadata

# NOTE: imported via the dotted submodule path (not ``from . import
# search``), because the package already re-exports a function named
# ``search`` (the Phase 1.3 keyword search in registry.py). Using
# ``from . import search`` here would resolve to that pre-existing
# package attribute instead of loading this module.
from .search import search as _category_keyword_search


class LibraryRegistry:
    """High-level facade over the Phase 1.3 registry plus the Phase
    1.4 loading/migration/validation/search infrastructure.

    Instantiating this class has no side effects: no library is
    loaded or migrated until ``load``/``reload`` is called explicitly.
    """

    def __init__(self, migration_engine: Optional[MigrationEngine] = None) -> None:
        self._migration_engine = migration_engine or default_migration_engine

    # -- Phase 1.3 surface (unchanged behaviour, delegated) ----------
    def register(self, library: BaseLibrary) -> BaseLibrary:
        """Register a library. Re-registering the same key overwrites it."""
        return _register(library)

    def get(self, name: str) -> BaseLibrary:
        """Return a registered library by name (case-insensitive)."""
        return _get_library(name)

    def list(self) -> List[BaseLibrary]:
        """Return all registered libraries, sorted by name."""
        return _list_libraries()

    def search(
        self,
        keyword: str = "",
        category: Optional[str] = None,
        standard: Optional[str] = None,
    ) -> List[BaseLibrary]:
        """Search by keyword, domain category, and/or standard."""
        return _category_keyword_search(keyword=keyword, category=category, standard=standard)

    def validate(self, library: BaseLibrary) -> List[str]:
        """Validate a library's metadata structure (Phase 1.3 checks)."""
        return _validate_metadata(library)

    # -- Phase 1.4 additions ------------------------------------------
    def load(self, name: str) -> BaseLibrary:
        """Lazily load ``name``'s attached JSON source into memory.

        Uses the cached copy on repeat calls (lazy loading). Must be
        called explicitly; nothing invokes this automatically.
        Raises ``ValueError`` if the library has no attached source.
        """
        library = self.get(name)
        self._migration_engine.apply(library)
        return library

    def reload(self, name: str) -> BaseLibrary:
        """Force a fresh read of ``name``'s JSON source from disk and
        re-apply it, discarding any cached copy."""
        library = self.get(name)
        loader_module.default_loader.reload(library)
        self._migration_engine.apply(library)
        return library

    def statistics(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Per-library record count/revision/duplicates/missing
        fields/source/status.

        Pass ``name`` for a single library's statistics dict, or omit
        it for a dict of every registered library keyed by name.
        """
        libraries = [self.get(name)] if name else self.list()
        stats: Dict[str, Any] = {}
        for library in libraries:
            report = validator_module.validate_library(library)
            counts = report.count_by_code()
            stats[library.metadata.name] = {
                "record_count": len(library.records),
                "revision": library.metadata.last_revision,
                "duplicates": counts.get("duplicate_id", 0),
                "missing_fields": counts.get("missing_field", 0),
                "source": library.source_path,
                "status": library.metadata.status,
            }
        if name:
            return stats[libraries[0].metadata.name]
        return stats

    # -- Faz 2.4.1B additions -----------------------------------------
    def search_bolts(self, **filters: Any) -> List[Dict[str, Any]]:
        """Faz 2.4.1B extended bolt search (see
        ``population.search_bolts`` for the full filter list, e.g.
        ``library_registry.search_bolts(nominal_diameter=10,
        strength_class="10.9", standard="ISO 4017")``)."""
        from . import population as population_module

        return population_module.search_bolts(**filters)

    def search_nuts(self, **filters: Any) -> List[Dict[str, Any]]:
        """Faz 2.4.1B extended nut search (see
        ``population.search_nuts`` for the full filter list)."""
        from . import population as population_module

        return population_module.search_nuts(**filters)


# Shared default facade instance for the package. Named distinctly
# (not ``registry``) so it never shadows the ``backend.library.registry``
# submodule attribute that Python binds automatically on the package.
library_registry = LibraryRegistry()
