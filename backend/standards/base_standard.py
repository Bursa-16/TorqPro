"""TorqPro Standards Engine - base standard definition.

Phase 1.2 infrastructure only. This module defines the metadata
container every standard module exposes. No engineering formulas
live here; calculation behaviour is unchanged.
"""

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class BaseStandard:
    """Immutable metadata descriptor for a fastening standard.

    Attributes:
        name: Canonical standard identifier (e.g. "ISO 898-1").
        version: Edition or revision year of the standard.
        organization: Issuing body (e.g. "ISO", "DIN", "VDI").
        status: Lifecycle status (e.g. "active", "withdrawn", "draft").
        description: Short human-readable summary.
        supported_calculations: Calculation types the standard covers.
        supported_fasteners: Fastener families in scope.
        supported_materials: Material classes in scope.
        reference_documents: Related normative documents.
    """

    name: str
    version: str = ""
    organization: str = ""
    status: str = "active"
    description: str = ""
    supported_calculations: Tuple[str, ...] = field(default_factory=tuple)
    supported_fasteners: Tuple[str, ...] = field(default_factory=tuple)
    supported_materials: Tuple[str, ...] = field(default_factory=tuple)
    reference_documents: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        """Normalized registry key for this standard."""
        return self.name.strip().lower()
