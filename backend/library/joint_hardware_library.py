"""TorqPro Engineering Library - joint hardware library (Faz 2.4.1C shell).

Metadata-only definition for non-washer joint hardware: spacers,
sleeves, bushings, dowel pins, thread inserts and retaining rings.

No records are populated in this phase. A verified, fully-sourced
dimension table (per family, per standard body) was not gathered for
any of these families in Faz 2.4.1C -- see the phase delivery report.
This module only establishes the registry shell, mirroring how
``bolt_library.py`` / ``washer_library.py`` started in Phase 1.3
before their own population phases. Populating real records is a
follow-up, separately-approved atomic phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

#: Sub-categories this shell covers (Faz 2.4.1C brief, section 2).
#: Advisory vocabulary only -- not enforced at the Pydantic layer
#: (``hardware_type`` stays free-text on ``JointHardwareRecord``).
KNOWN_HARDWARE_TYPES = (
    "Spacer",
    "Sleeve",
    "Bushing",
    "Dowel pin",
    "Thread insert",
    "Retaining ring",
)

JOINT_HARDWARE_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Joint Hardware Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Master definitions for non-washer joint hardware: "
                "spacers, sleeves, bushings, dowel pins, thread "
                "inserts and retaining rings."
            ),
            source_standard="",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("mm", "N"),
        )
    )
)

# Ready-to-read future population source (empty in Faz 2.4.1C -- see
# module docstring). Mirrors the "explicit, opt-in" convention already
# established by every other domain shell in this package.
JOINT_HARDWARE_LIBRARY.attach_source("data/joint_hardware_library.json")
