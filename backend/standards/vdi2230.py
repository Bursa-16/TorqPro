"""VDI 2230 standard definition (metadata only, Phase 1.2)."""

from .base_standard import BaseStandard
from .registry import register

VDI_2230_1 = register(
    BaseStandard(
        name="VDI 2230-1",
        version="2015",
        organization="VDI",
        status="active",
        description=(
            "Systematic calculation of highly stressed bolted joints - "
            "joints with one cylindrical bolt."
        ),
        supported_calculations=(
            "preload",
            "tightening_torque",
            "joint_analysis",
            "utilization",
        ),
        supported_fasteners=("bolt", "screw", "stud"),
        supported_materials=("carbon_steel", "alloy_steel"),
        reference_documents=("VDI 2230-2", "ISO 898-1", "ISO 965-1"),
    )
)
