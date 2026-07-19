"""DIN standard definitions (metadata only, Phase 1.2)."""

from .base_standard import BaseStandard
from .registry import register

DIN_13_1 = register(
    BaseStandard(
        name="DIN 13-1",
        version="1999",
        organization="DIN",
        status="active",
        description=(
            "ISO general purpose metric screw threads - nominal sizes for "
            "coarse pitch threads."
        ),
        supported_calculations=("thread_geometry",),
        supported_fasteners=("bolt", "screw", "stud", "nut"),
        supported_materials=(),
        reference_documents=("ISO 261", "ISO 965-1"),
    )
)

DIN_946 = register(
    BaseStandard(
        name="DIN 946",
        version="1991",
        organization="DIN",
        status="active",
        description=(
            "Determination of coefficient of friction of bolt/nut "
            "assemblies under specified conditions."
        ),
        supported_calculations=("friction_coefficient",),
        supported_fasteners=("bolt", "nut"),
        supported_materials=("carbon_steel", "alloy_steel"),
        reference_documents=("ISO 16047",),
    )
)
