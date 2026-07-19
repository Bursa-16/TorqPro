"""TorqPro VDI 2230 Core - generic series-compliance stiffness.

Formula (``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §7 for bolt
stiffness c_b, §8 for clamped-part stiffness c_c)::

    1 / c = sum(L_i / (E_i * A_i))

This module implements only the generic series-spring compliance
combinator shared by both c_b and c_c. It does **not** compute or
assume any specific segment geometry:

- bolt substitution-length regions (shank, engaged thread, head/nut
  substitution lengths -- §7), and
- clamped-part effective area / pressure-cone method (§8)

both require the licensed VDI 2230 Part 1 reference and are explicitly
out of scope for this phase. Callers supply already-known
``(length, modulus, area)`` segments; this module only sums their
compliance and inverts it to a stiffness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .exceptions import CalculationDomainError
from .units import require_positive


@dataclass(frozen=True)
class StiffnessSegment:
    """A single series-compliance segment.

    Attributes:
        length_mm: Segment length L_i, in mm.
        modulus_mpa: Segment elastic modulus E_i, in MPa.
        area_mm2: Segment cross-sectional area A_i, in mm^2.
    """

    length_mm: float
    modulus_mpa: float
    area_mm2: float


def series_compliance_stiffness_n_per_mm(
    segments: Sequence[StiffnessSegment],
) -> float:
    """Combine ``segments`` in series and return the resulting
    stiffness in N/mm: ``c = 1 / sum(L_i / (E_i * A_i))``.

    Raises ``CalculationDomainError`` if ``segments`` is empty.
    Raises ``CalculationInputError`` if any segment's length, modulus
    or area is not a finite, strictly positive number.
    """
    if not segments:
        raise CalculationDomainError(
            "At least one stiffness segment is required to compute a "
            "series compliance"
        )

    total_compliance = 0.0
    for index, segment in enumerate(segments):
        length = require_positive(segment.length_mm, f"segments[{index}].length_mm")
        modulus = require_positive(
            segment.modulus_mpa, f"segments[{index}].modulus_mpa"
        )
        area = require_positive(segment.area_mm2, f"segments[{index}].area_mm2")
        total_compliance += length / (modulus * area)

    return 1.0 / total_compliance


__all__ = ["StiffnessSegment", "series_compliance_stiffness_n_per_mm"]
