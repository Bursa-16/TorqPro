"""TorqPro Engineering Library - lazy JSON loader (Phase 1.4 infrastructure).

Reads the existing JSON reference files under ``data/`` on demand and
caches the result per library. Nothing is read automatically: a
library's records are only fetched from disk the first time
``load()`` is called for it, and the cached copy is reused until
``reload()`` (or ``clear_cache()``) is called explicitly.

This module only *reads* records into memory. It never writes back to
a JSON file and never mutates a registered library's state by itself
-- callers decide whether/how to apply what was loaded (see
``backend.library.migration``). Independent from
``backend.engineering_core`` and ``backend.standards``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import models as models_module
from .registry import BaseLibrary

# Different existing JSON files store their payload under different
# top-level keys ("records" for most datasets, "rules" for the
# bolt/nut compatibility rule set). Checked in this order; the first
# list-valued key found is used.
_RECORD_KEYS = ("records", "rules", "entries", "items", "data")


def read_source_payload(path: str) -> Dict[str, Any]:
    """Read a JSON reference file from disk, unmodified."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the first list-valued record collection found in ``payload``.

    Returns an empty list if ``payload`` is not a dict or holds none
    of the recognised record-collection keys.
    """
    if not isinstance(payload, dict):
        return []
    for key in _RECORD_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


class LibraryLoader:
    """Per-library lazy JSON loader with an explicit, opt-in cache.

    Nothing is loaded until ``load()`` is called; after that, repeated
    calls return the cached list until ``reload()`` or
    ``clear_cache()`` is used. A fresh :class:`LibraryLoader` starts
    with an empty cache.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    def is_cached(self, library: BaseLibrary) -> bool:
        """Return True if this library's records are already cached."""
        return library.metadata.key in self._cache

    def load(self, library: BaseLibrary) -> List[Dict[str, Any]]:
        """Return this library's source records, reading the file only
        on the first call for that library (lazy loading).

        Raises ``ValueError`` if no JSON source has been attached to
        ``library`` via ``BaseLibrary.attach_source``.
        """
        key = library.metadata.key
        if key in self._cache:
            return list(self._cache[key])
        if not library.source_path:
            raise ValueError(
                f"No JSON source attached to library: {library.metadata.name}"
            )
        payload = read_source_payload(library.source_path)
        records = extract_records(payload)
        self._cache[key] = records
        return list(records)

    def reload(self, library: BaseLibrary) -> List[Dict[str, Any]]:
        """Discard any cached records for ``library`` and read the
        source file again from disk."""
        self._cache.pop(library.metadata.key, None)
        return self.load(library)

    def clear_cache(self, library: Optional[BaseLibrary] = None) -> None:
        """Drop cached records for one library, or for every library
        if ``library`` is omitted."""
        if library is None:
            self._cache.clear()
        else:
            self._cache.pop(library.metadata.key, None)


# Shared default loader instance for the package. A module-level
# instance is convenient for the registry facade and tests, but
# nothing forces its use -- callers may create their own
# :class:`LibraryLoader` for isolation.
default_loader = LibraryLoader()


def load(library: BaseLibrary) -> List[Dict[str, Any]]:
    """Lazily load and cache ``library``'s source records (shortcut for
    ``default_loader.load``)."""
    return default_loader.load(library)


def reload(library: BaseLibrary) -> List[Dict[str, Any]]:
    """Force-reload ``library``'s source records (shortcut for
    ``default_loader.reload``)."""
    return default_loader.reload(library)


def load_typed(
    library: BaseLibrary, using: Optional["LibraryLoader"] = None
) -> List["models_module.LibraryRecordBase"]:
    """Lazily load ``library``'s source records and validate/parse
    them against its Faz 2.4.0 typed schema (see
    ``backend.library.models``).

    ``using`` selects the :class:`LibraryLoader` instance (defaults to
    ``default_loader``, same lazy-cache-per-key semantics as
    ``load``/``reload`` above -- pass a dedicated instance for cache
    isolation, exactly as existing callers already do for ``load``).

    Raises ``pydantic.ValidationError`` on the first record that does
    not satisfy the schema, and ``ValueError`` if no JSON source is
    attached (same as ``load``). Not called anywhere automatically --
    an explicit, opt-in read, like ``load`` itself.
    """
    active_loader = using or default_loader
    raw_records = active_loader.load(library)
    return models_module.parse_typed_records(library.metadata.key, raw_records)
