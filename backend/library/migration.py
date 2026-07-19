"""TorqPro Engineering Library - migration engine (Phase 1.4 infrastructure).

Provides the machinery to move records from the existing JSON
reference files into the registry's in-memory library objects.

This phase ships the *engine* only: nothing here runs automatically.
Importing this module (or the ``backend.library`` package) does not
populate any library, does not change any existing JSON file, and
does not alter engineering, API or frontend behaviour. Running an
actual migration for a given library is a deliberate, explicit call
to ``MigrationEngine.apply``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import loader as loader_module
from .registry import BaseLibrary
from .source_manager import SourceManager, SourceRecord, default_source_manager


@dataclass
class MigrationPlan:
    """Describes what migrating one library would involve, without
    doing it.

    ``status`` is one of:
        - "planned": a source is attached and ready to migrate.
        - "no_source": nothing is attached; there is nothing to plan.
    """

    library_key: str
    library_name: str
    source_path: Optional[str]
    record_count: int
    already_populated: bool
    status: str = "planned"


@dataclass
class MigrationResult:
    """Outcome of an applied migration."""

    plan: MigrationPlan
    records_migrated: int
    source_record: Optional[SourceRecord]
    status: str = "applied"


class MigrationEngine:
    """Plans and (only when explicitly asked) applies JSON -> registry
    migrations for a single library at a time.

    Infrastructure only: nothing in this class is invoked by package
    import, application start-up, or any other module in
    ``backend.library``.
    """

    def __init__(
        self,
        loader: Optional[loader_module.LibraryLoader] = None,
        source_manager: Optional[SourceManager] = None,
    ) -> None:
        self._loader = loader or loader_module.default_loader
        self._source_manager = source_manager or default_source_manager

    def plan(self, library: BaseLibrary) -> MigrationPlan:
        """Compute what migrating ``library`` from its attached JSON
        source would involve. Reads the source file to count records
        but never changes ``library``'s own state."""
        if not library.source_path:
            return MigrationPlan(
                library_key=library.metadata.key,
                library_name=library.metadata.name,
                source_path=None,
                record_count=0,
                already_populated=bool(library.records),
                status="no_source",
            )
        records = self._loader.load(library)
        return MigrationPlan(
            library_key=library.metadata.key,
            library_name=library.metadata.name,
            source_path=library.source_path,
            record_count=len(records),
            already_populated=bool(library.records),
            status="planned",
        )

    def apply(
        self, library: BaseLibrary, plan: Optional[MigrationPlan] = None
    ) -> MigrationResult:
        """Copy the attached JSON source's records into ``library``
        and record provenance via the :class:`SourceManager`.

        Ready-to-use infrastructure for a future migration rollout.
        Raises ``ValueError`` if ``library`` has no attached source.
        Must be invoked explicitly -- it is never called automatically
        anywhere in this package.
        """
        active_plan = plan or self.plan(library)
        if active_plan.source_path is None:
            raise ValueError(
                "Cannot migrate a library without an attached source: "
                f"{library.metadata.name}"
            )
        records = self._loader.load(library)
        library.replace_records(records)
        self._source_manager.track(
            library_key=library.metadata.key,
            source=library.source_path,
            version=library.metadata.version,
            revision=library.metadata.last_revision,
        )
        source_record = self._source_manager.mark_loaded(library.metadata.key)
        return MigrationResult(
            plan=active_plan,
            records_migrated=len(records),
            source_record=source_record,
            status="applied",
        )


# Shared default engine for the package (mirrors ``loader.default_loader``).
default_migration_engine = MigrationEngine()
