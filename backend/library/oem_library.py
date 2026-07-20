"""TorqPro Engineering Library - OEM library (Faz 2.4.0, adapter-only).

Unlike the other nine domain shells (bolt, nut, washer, thread,
material, coating, lubrication, strength_class, compatibility), this
module owns no engineering data of its own. An OEM-specific norm is
already fully represented as a ``backend.standards.BaseStandard``
entry (see ``backend/standards/oem.py``, Phase 1.2). This shell only
*adapts* that existing standard registry into the library registry's
surface (registration, search, statistics) via read-only lookups.

Hard rule: nothing here copies, caches or duplicates a
``backend.standards`` value. ``resolve_oem_reference`` always resolves
against the live ``backend.standards.registry`` on every call; no OEM
data is stored in this module or in the registered ``OEM_LIBRARY``'s
own record store.
"""

from __future__ import annotations

from typing import List

from backend.standards.base_standard import BaseStandard
from backend.standards.registry import get_standard
from backend.standards.registry import list_standards as _list_standards

from .registry import BaseLibrary, LibraryMetadata, register

OEM_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="OEM Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Adapter-only reference into backend.standards for "
                "OEM-specific (company) norms. Carries no engineering "
                "data of its own -- see backend/standards/oem.py for "
                "the actual standard definitions."
            ),
            source_standard="",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=(),
        )
    )
)


def resolve_oem_reference(name: str) -> BaseStandard:
    """Resolve ``name`` against the live ``backend.standards``
    registry and return that standard's own object, unchanged.

    Read-only: never stores, copies or caches the returned value.
    Raises ``KeyError`` if no such standard is registered (same
    behaviour as ``backend.standards.registry.get_standard``).
    """
    return get_standard(name)


def list_oem_references() -> List[str]:
    """Return the canonical names of every standard currently
    registered in ``backend.standards`` (pass-through, read-only;
    does not filter to OEM-only standards, since
    ``backend.standards.registry`` does not distinguish OEM from
    normative standards at lookup time)."""
    return [standard.name for standard in _list_standards()]


__all__ = ["OEM_LIBRARY", "resolve_oem_reference", "list_oem_references"]
