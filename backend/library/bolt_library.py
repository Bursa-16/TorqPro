"""TorqPro Engineering Library - bolt library (Phase 1.3 infrastructure).

Metadata-only definition for bolts, screws and studs: designation,
thread, geometry, property class and material specification. No
records are migrated from any existing dataset in this phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

BOLT_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Bolt Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Master definitions for bolts, screws and studs: "
                "designation, thread, geometry, head/bearing geometry, "
                "property class and material specification."
            ),
            source_standard="ISO 898-1",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("mm", "N", "MPa"),
        )
    )
)
