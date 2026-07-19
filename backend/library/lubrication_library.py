"""TorqPro Engineering Library - lubrication library (Phase 1.3 infrastructure).

Metadata-only definition for lubricant specifications and validated
friction conditions (thread/bearing distributions, counter-surface,
speed, temperature and reuse context). No records are migrated in
this phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

LUBRICATION_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Lubrication Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Lubricant specifications and validated friction "
                "conditions: thread/bearing friction distributions, "
                "counter-surface, speed, temperature and reuse context."
            ),
            source_standard="ISO 16047",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("dimensionless",),
        )
    )
)

# Ready-to-read future migration source (not loaded in Phase 1.3).
LUBRICATION_LIBRARY.attach_source("data/Surtunme_Veritabani.json")
