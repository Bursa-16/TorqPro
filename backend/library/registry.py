"""TorqPro Engineering Library - central registry.

Infrastructure only. Central bookkeeping for professional engineering
reference libraries (bolts, nuts, washers, threads, materials,
coatings, lubrication, strength classes, compatibility rules).

No engineering formulas, no calculation logic, no API coupling.
Independent from ``backend.engineering_core`` and ``backend.standards``.

Faz 2.4.0: ``LibraryMetadata`` migrated from a frozen ``dataclass`` to
a frozen Pydantic model (Option C: in-place migration, unchanged
field names/defaults/``key`` property, unchanged construction
signature -- every existing ``LibraryMetadata(...)`` call site in the
nine domain shells and in tests keeps working unmodified). Immutable
"copy with change" now uses ``model_copy(update=...)`` in place of
``dataclasses.replace`` (see ``BaseLibrary.replace_records`` below).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from . import models as models_module


class LibraryMetadata(BaseModel):
    """Immutable metadata descriptor for an engineering library.

    Attributes:
        name: Canonical library identifier (e.g. "Bolt Library").
        version: Edition or revision of the library content.
        organization: Owning or issuing body.
        description: Short human-readable summary.
        source_standard: Related normative standard(s), if any.
        status: Lifecycle status (e.g. "draft", "schema_ready", "active").
        record_count: Number of records currently held by the library.
        last_revision: Date or tag of the last content revision.
        supported_units: Unit systems the library data supports.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    version: str = ""
    organization: str = ""
    description: str = ""
    source_standard: str = ""
    status: str = "draft"
    record_count: int = 0
    last_revision: str = ""
    supported_units: Tuple[str, ...] = Field(default_factory=tuple)

    @property
    def key(self) -> str:
        """Normalized registry key for this library."""
        return self.name.strip().lower()


class BaseLibrary:
    """Base container every engineering library module builds on.

    Holds metadata and an in-memory record store. Phase 1.3 only
    provides the shell: libraries start empty and no data is migrated
    from the existing JSON reference files.
    """

    def __init__(
        self,
        metadata: LibraryMetadata,
        records: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.metadata = metadata
        self._records: List[Dict[str, Any]] = list(records) if records else []
        self._source_path: Optional[str] = None

    @property
    def records(self) -> List[Dict[str, Any]]:
        """Return a copy of the records currently held in memory."""
        return list(self._records)

    def attach_source(self, source_path: str) -> None:
        """Record which JSON file this library will migrate from later.

        Infrastructure only: stores the path for a future migration
        phase. Does not read, parse or validate the file.
        """
        self._source_path = source_path

    @property
    def source_path(self) -> Optional[str]:
        """Return the JSON source path attached via ``attach_source``."""
        return self._source_path

    def load_from_source(self) -> List[Dict[str, Any]]:
        """Read raw records from the attached JSON source.

        This is a ready-to-use hook for a future migration phase and
        is not invoked anywhere in Phase 1.3. It does not mutate this
        library's in-memory state.
        """
        if not self._source_path:
            raise ValueError("No JSON source attached to this library")
        payload = load_json_source(self._source_path)
        records = payload.get("records", [])
        if not isinstance(records, list):
            raise ValueError(
                f"Expected a 'records' list in {self._source_path}"
            )
        return records

    def replace_records(self, records: List[Dict[str, Any]]) -> None:
        """Replace this library's in-memory records and keep
        ``metadata.record_count`` in sync.

        Phase 1.4 infrastructure hook for the migration engine. Not
        called anywhere during package import; a library only gains
        records when something explicitly calls this method.
        """
        self._records = list(records)
        self.metadata = self.metadata.model_copy(
            update={"record_count": len(self._records)}
        )

    def typed_records(self) -> List["models_module.LibraryRecordBase"]:
        """Validate and parse this library's current in-memory raw
        records against its Faz 2.4.0 typed schema (see
        ``backend.library.models``).

        Raises ``pydantic.ValidationError`` on the first invalid
        record. Does not mutate ``self._records`` -- the typed
        instances are a validated view, not a replacement for the raw
        dict storage.
        """
        return models_module.parse_typed_records(self.metadata.key, self._records)

    def find_schema_violations(self) -> List[str]:
        """Validate this library's current in-memory raw records
        against its typed schema and return violation messages
        instead of raising. Empty list means every record is
        schema-valid."""
        return models_module.find_schema_violations(self.metadata.key, self._records)


def load_json_source(path: str) -> Dict[str, Any]:
    """Read a JSON reference file from disk without altering any state.

    Infrastructure for a future migration step: this function knows
    how to read the existing JSON library files, but Phase 1.3 never
    calls it to populate a library, and no existing JSON file is
    modified or removed.
    """
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


_REGISTRY: Dict[str, BaseLibrary] = {}


def register(library: BaseLibrary) -> BaseLibrary:
    """Register a library. Re-registering the same key overwrites it."""
    if not isinstance(library, BaseLibrary):
        raise TypeError("register() expects a BaseLibrary instance")
    _REGISTRY[library.metadata.key] = library
    return library


def get_library(name: str) -> BaseLibrary:
    """Return a registered library by name (case-insensitive)."""
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise KeyError(f"Library not registered: {name}")
    return _REGISTRY[key]


def list_libraries() -> List[BaseLibrary]:
    """Return all registered libraries, sorted by name."""
    return sorted(_REGISTRY.values(), key=lambda lib: lib.metadata.key)


def search(term: str) -> List[BaseLibrary]:
    """Return libraries whose name, organization, description or
    source standard contains ``term`` (case-insensitive)."""
    needle = term.strip().lower()
    if not needle:
        return []
    matches: List[BaseLibrary] = []
    for library in _REGISTRY.values():
        meta = library.metadata
        haystack = " ".join(
            [meta.name, meta.organization, meta.description, meta.source_standard]
        ).lower()
        if needle in haystack:
            matches.append(library)
    return sorted(matches, key=lambda lib: lib.metadata.key)


def validate(library: BaseLibrary) -> List[str]:
    """Validate a library's metadata structure.

    Returns a list of problem messages; an empty list means the
    library satisfies the minimum required metadata structure. This
    checks structure only, not the content of individual records.
    """
    if not isinstance(library, BaseLibrary):
        raise TypeError("validate() expects a BaseLibrary instance")

    problems: List[str] = []
    meta = library.metadata

    if not meta.name:
        problems.append("name is required")
    if not meta.organization:
        problems.append("organization is required")
    if not meta.status:
        problems.append("status is required")
    if meta.record_count < 0:
        problems.append("record_count cannot be negative")
    if meta.record_count != len(library.records):
        problems.append("record_count does not match number of loaded records")

    return problems
