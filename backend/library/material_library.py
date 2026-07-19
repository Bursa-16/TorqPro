"""TorqPro Engineering Library - material library (Phase 1.3 infrastructure).

Metadata-only definition for material property sets: proof/yield/
tensile strength, modulus, Poisson ratio, CTE, hardness and source,
per temperature/condition. Independent of the calculation values in
``backend.engineering_core.materials``; no calculation behaviour
changes. No records are migrated in this phase.
"""

from __future__ import annotations

from .registry import BaseLibrary, LibraryMetadata, register

MATERIAL_LIBRARY = register(
    BaseLibrary(
        metadata=LibraryMetadata(
            name="Material Library",
            version="0.1",
            organization="TorqPro",
            description=(
                "Temperature/condition-specific material property sets: "
                "proof/yield/tensile strength, modulus, Poisson ratio, "
                "CTE, hardness and source."
            ),
            source_standard="ISO 898-1",
            status="draft",
            record_count=0,
            last_revision="",
            supported_units=("MPa", "GPa", "1/K"),
        )
    )
)
