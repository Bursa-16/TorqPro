"""ISO standard definitions (metadata only, Phase 1.2)."""

from .base_standard import BaseStandard
from .registry import register

ISO_898_1 = register(
    BaseStandard(
        name="ISO 898-1",
        version="2013",
        organization="ISO",
        status="active",
        description=(
            "Mechanical properties of fasteners made of carbon steel and "
            "alloy steel - bolts, screws and studs with specified property "
            "classes."
        ),
        supported_calculations=("proof_load", "tensile_strength"),
        supported_fasteners=("bolt", "screw", "stud"),
        supported_materials=("carbon_steel", "alloy_steel"),
        reference_documents=("ISO 898-2", "ISO 965-1"),
    )
)

ISO_965_1 = register(
    BaseStandard(
        name="ISO 965-1",
        version="2013",
        organization="ISO",
        status="active",
        description=(
            "ISO general purpose metric screw threads - tolerances, "
            "principles and basic data."
        ),
        supported_calculations=("thread_geometry",),
        supported_fasteners=("bolt", "screw", "stud", "nut"),
        supported_materials=(),
        reference_documents=("ISO 68-1", "ISO 261"),
    )
)
