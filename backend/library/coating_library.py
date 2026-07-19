"""TorqPro Engineering Library - coating library (Phase 1.3 infrastructure).

Metadata-only definition for surface/coating specifications
(descriptive records: coating type, thickness range, counter-surface
context). Friction values remain part of the friction/lubrication
data, not this module. No records are migrated in this phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

COATING_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Coating Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Descriptive surface/coating specifications: coating "
                "type, process, thickness range and counter-surface "
                "context."
            ),
            source_standard="ISO 16047",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("micrometer",),
        )
    )
)

# Ready-to-read future migration source (not loaded in Phase 1.3).
COATING_LIBRARY.attach_source("data/Surtunme_Veritabani.json")
