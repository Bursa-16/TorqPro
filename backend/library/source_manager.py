"""TorqPro Engineering Library - source manager (Phase 1.4 infrastructure).

Tracks, per library, where its data comes from and what state that
source was in the last time it was inspected: source path, version,
SHA-256 checksum, revision tag and load timestamp.

Infrastructure only: this module never reads engineering records and
never mutates a registered library. It has no dependency on
``backend.library.registry`` (or any other module in this package),
so nothing else in the library package needs to import it to avoid a
circular import.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Dict, Optional


@dataclass(frozen=True)
class SourceRecord:
    """Immutable provenance snapshot for one library's data source.

    Attributes:
        library_key: Registry key of the library this source belongs to.
        source: Path (or identifier) of the underlying JSON file.
        version: Declared version/edition of the source content.
        sha256: Hex digest of the source file's content at track time.
        revision: Free-form revision tag (e.g. dataset status/date).
        loaded_at: ISO-8601 UTC timestamp of the last successful load,
            or ``None`` if the source has been tracked but not loaded.
    """

    library_key: str
    source: str
    version: str = ""
    sha256: str = ""
    revision: str = ""
    loaded_at: Optional[str] = None


def compute_sha256(path: str) -> str:
    """Return the hex SHA-256 digest of the file at ``path``."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SourceManager:
    """In-memory registry of per-library source provenance.

    A fresh :class:`SourceManager` tracks nothing until ``track`` is
    called explicitly.
    """

    def __init__(self) -> None:
        self._sources: Dict[str, SourceRecord] = {}

    def track(
        self,
        library_key: str,
        source: str,
        version: str = "",
        revision: str = "",
    ) -> SourceRecord:
        """Record (or refresh) provenance for a library's source file.

        Computes the source file's SHA-256 checksum at call time.
        Does not mark the source as loaded; call ``mark_loaded`` once
        the records have actually been read into memory.
        """
        key = library_key.strip().lower()
        record = SourceRecord(
            library_key=key,
            source=source,
            version=version,
            sha256=compute_sha256(source),
            revision=revision,
        )
        self._sources[key] = record
        return record

    def mark_loaded(self, library_key: str) -> SourceRecord:
        """Stamp the tracked source for ``library_key`` with the
        current UTC time as its load timestamp.

        Raises ``KeyError`` if the library's source was never tracked.
        """
        key = library_key.strip().lower()
        if key not in self._sources:
            raise KeyError(f"No source tracked for library: {library_key}")
        updated = replace(
            self._sources[key],
            loaded_at=datetime.now(timezone.utc).isoformat(),
        )
        self._sources[key] = updated
        return updated

    def get(self, library_key: str) -> Optional[SourceRecord]:
        """Return the tracked source for ``library_key``, or ``None``."""
        return self._sources.get(library_key.strip().lower())

    def all(self) -> Dict[str, SourceRecord]:
        """Return a copy of every tracked source, keyed by library key."""
        return dict(self._sources)

    def clear(self) -> None:
        """Forget all tracked sources."""
        self._sources.clear()


# Shared default instance for the package (mirrors ``loader.default_loader``).
default_source_manager = SourceManager()
