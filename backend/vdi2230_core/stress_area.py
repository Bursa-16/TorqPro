"""TorqPro VDI 2230 Core - tensile stress area A_s.

PROVISIONAL (see ``backend/vdi2230_core/trace.py`` /
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §20): requires
independent source sign-off before production use.

Formula::

    d2 = d - 0.6495 * P
    d3 = d - 1.2269 * P
    A_s = pi/4 * ((d2 + d3) / 2)^2

``d`` is the nominal thread diameter, ``P`` the pitch, ``d2`` the
pitch diameter and ``d3`` the minor diameter. The 0.6495 / 1.2269
factors are the same ISO 68-1 metric-thread constants already
approved in ``backend/engineering_core/geometry.py``. They are
duplicated here (not imported) so ``backend.vdi2230_core`` stays free
of any import from ``backend.engineering_core``, matching the
package-isolation pattern already enforced for
``backend.calculation_engine`` in Phase 2.1.
"""

from __future__ import annotations

import math

from .exceptions import CalculationDomainError
from .units import require_positive

#: ISO 68-1 metric-thread pitch-diameter factor (d2 = d - FACTOR * P).
PITCH_DIAMETER_FACTOR = 0.6495

#: ISO 68-1 metric-thread minor-diameter factor (d3 = d - FACTOR * P).
MINOR_DIAMETER_FACTOR = 1.2269


def tensile_stress_area_mm2(diameter_mm: float, pitch_mm: float) -> float:
    """Tensile stress area A_s in mm^2.

    Raises ``CalculationInputError`` if ``diameter_mm`` or
    ``pitch_mm`` is not a finite, strictly positive number.
    Raises ``CalculationDomainError`` if the resulting minor diameter
    is not positive (pitch too large relative to diameter for a valid
    metric thread).
    """
    diameter = require_positive(diameter_mm, "diameter_mm")
    pitch = require_positive(pitch_mm, "pitch_mm")

    pitch_diameter = diameter - PITCH_DIAMETER_FACTOR * pitch
    minor_diameter = diameter - MINOR_DIAMETER_FACTOR * pitch
    if minor_diameter <= 0:
        raise CalculationDomainError(
            "pitch_mm is too large relative to diameter_mm: minor "
            f"diameter would be {minor_diameter} mm (must be > 0)"
        )

    mean_diameter = (pitch_diameter + minor_diameter) / 2
    return math.pi / 4 * mean_diameter**2


__all__ = ["tensile_stress_area_mm2", "PITCH_DIAMETER_FACTOR", "MINOR_DIAMETER_FACTOR"]
