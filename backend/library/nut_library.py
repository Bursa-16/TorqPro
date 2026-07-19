"""TorqPro Engineering Library - nut library (Phase 1.3 infrastructure).

Metadata-only definition for nuts: style, height, thread, bearing
geometry and proof class. No records are migrated from the existing
proof-load dataset in this phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

NUT_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Nut Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Master definitions for nuts: style, height, thread, "
                "bearing geometry and proof class."
            ),
            source_standard="ISO 898-2",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("mm", "N", "MPa"),
        )
    )
)

# Ready-to-read future migration source (not loaded in Phase 1.3).
NUT_LIBRARY.attach_source("data/ISO_898_2_Somun_Proof_Load.json")
