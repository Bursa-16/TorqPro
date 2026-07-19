"""Generic OEM standard infrastructure (metadata only, Phase 1.2).

Provides a helper for defining company-specific (OEM) standards so
future OEM norms can be added without new boilerplate.
"""

from typing import Tuple

from .base_standard import BaseStandard
from .registry import register


def define_oem_standard(
    name: str,
    organization: str,
    version: str = "",
    status: str = "active",
    description: str = "",
    supported_calculations: Tuple[str, ...] = (),
    supported_fasteners: Tuple[str, ...] = (),
    supported_materials: Tuple[str, ...] = (),
    reference_documents: Tuple[str, ...] = (),
) -> BaseStandard:
    """Create and register an OEM-specific standard descriptor."""
    return register(
        BaseStandard(
            name=name,
            version=version,
            organization=organization,
            status=status,
            description=description,
            supported_calculations=supported_calculations,
            supported_fasteners=supported_fasteners,
            supported_materials=supported_materials,
            reference_documents=reference_documents,
        )
    )
