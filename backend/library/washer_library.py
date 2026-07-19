"""TorqPro Engineering Library - washer library (Phase 1.3 infrastructure).

Metadata-only definition for washers: inner/outer diameter, thickness,
hardness and type. No records are migrated from the existing washer
hardness/bearing-pressure dataset in this phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

WASHER_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Washer Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Master definitions for washers: inner/outer diameter, "
                "thickness, hardness, type and bearing pressure limits."
            ),
            source_standard="ISO 887",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("mm", "MPa", "HV"),
        )
    )
)

# Ready-to-read future migration source (not loaded in Phase 1.3).
WASHER_LIBRARY.attach_source("data/Pul_Sertlik_Yuzey_Basinci.json")
