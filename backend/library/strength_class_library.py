"""TorqPro Engineering Library - strength class library (Phase 1.3
infrastructure).

Metadata-only definition for bolt and nut property (strength) class
reference records, e.g. 4.6, 8.8, 10.9, 12.9 for bolts and 4, 8, 10
for nuts. Distinct from raw material identity. No records are
migrated in this phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

STRENGTH_CLASS_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Strength Class Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Bolt and nut property class reference records "
                "(e.g. 4.6, 8.8, 10.9, 12.9), kept distinct from raw "
                "material identity."
            ),
            source_standard="ISO 898-1",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("MPa",),
        )
    )
)
