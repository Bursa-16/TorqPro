"""FIAT OEM standard definitions (metadata only, Phase 1.2)."""

from .base_standard import BaseStandard
from .registry import register

FIAT_9_55823 = register(
    BaseStandard(
        name="FIAT 9.55823",
        version="",
        organization="FIAT",
        status="active",
        description=(
            "FIAT group norm for threaded fastener tightening; OEM-specific "
            "torque and friction requirements."
        ),
        supported_calculations=("tightening_torque",),
        supported_fasteners=("bolt", "screw", "nut"),
        supported_materials=("carbon_steel", "alloy_steel"),
        reference_documents=("VDI 2230-1", "ISO 16047"),
    )
)
