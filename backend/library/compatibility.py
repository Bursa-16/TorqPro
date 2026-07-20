"""TorqPro Engineering Library - compatibility rules (Phase 1.3
infrastructure).

Metadata-only definition for the bolt/nut/washer compatibility rule
set (e.g. minimum nut class per bolt class). This is an engineering
rule-set library, not a calculation module: no compatibility logic is
implemented here. No records are migrated in this phase.

Faz 2.4.1B note: the structured bolt<->nut compatibility *service*
requested by that phase (``CompatibilityResult`` with
warnings/errors/engineering_notes, not a bare boolean) lives in
``backend.library.compatibility_engine`` rather than here, to keep
this module's Phase 1.3 "metadata-only" design unchanged.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

COMPATIBILITY_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Compatibility Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Bolt/nut/washer compatibility rule set, e.g. minimum "
                "nut property class per bolt property class."
            ),
            source_standard="ISO 898-2",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("dimensionless",),
        )
    )
)

# Ready-to-read future migration source (not loaded in Phase 1.3).
COMPATIBILITY_LIBRARY.attach_source("data/Civata_Somun_Uyumluluk.json")
