"""TorqPro Engineering Library - thread library (Phase 1.3 infrastructure).

Metadata-only definition for metric screw thread geometry: nominal
diameter, pitch, tolerance class and stress-area source. No records
are migrated from any existing dataset in this phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

THREAD_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Thread Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Master thread geometry definitions: nominal diameter, "
                "pitch, tolerance class and stress-area source."
            ),
            source_standard="ISO 965-1",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("mm",),
        )
    )
)
