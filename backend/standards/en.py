"""EN standard definitions (metadata only, Phase 1.2)."""

from .base_standard import BaseStandard
from .registry import register

EN_1090_2 = register(
    BaseStandard(
        name="EN 1090-2",
        version="2018",
        organization="CEN",
        status="active",
        description=(
            "Execution of steel structures and aluminium structures - "
            "technical requirements for steel structures, including "
            "preloaded bolted connections."
        ),
        supported_calculations=("preload", "tightening_torque"),
        supported_fasteners=("bolt", "nut", "washer"),
        supported_materials=("carbon_steel", "alloy_steel", "stainless_steel"),
        reference_documents=("EN 14399", "EN 15048"),
    )
)

EN_14399 = register(
    BaseStandard(
        name="EN 14399",
        version="2015",
        organization="CEN",
        status="active",
        description=(
            "High-strength structural bolting assemblies for preloading."
        ),
        supported_calculations=("preload",),
        supported_fasteners=("bolt", "nut", "washer"),
        supported_materials=("carbon_steel", "alloy_steel"),
        reference_documents=("EN 1090-2",),
    )
)
