"""TorqPro VDI 2230 Core - quick target assembly preload F_M.

PROVISIONAL quick model -- explicitly NOT the validated multi-factor
VDI 2230 assembly-preload / tightening-scatter method (see
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §4 vicinity and §6,
which describes target/min/max distributions and Monte Carlo /
variance propagation as separate, more detailed work).

Formula::

    F_M = Rp0.2 * A_s * utilization_ratio

This is the same model already implemented in
``backend/engineering_core/preload.py:preload_from_yield_n``,
re-implemented independently here so ``backend.vdi2230_core`` stays
free of any import from ``backend.engineering_core``.
"""

from __future__ import annotations

from .exceptions import CalculationInputError
from .units import require_positive


def target_preload_n(
    rp02_mpa: float, stress_area_mm2: float, utilization_ratio: float
) -> float:
    """Quick target assembly preload F_M in N.

    Raises ``CalculationInputError`` if any input is not a finite,
    strictly positive number, or if ``utilization_ratio`` exceeds 1
    (a target above 100% of yield is not a valid quick-model input).
    """
    rp02 = require_positive(rp02_mpa, "rp02_mpa")
    stress_area = require_positive(stress_area_mm2, "stress_area_mm2")
    ratio = require_positive(utilization_ratio, "utilization_ratio")
    if ratio > 1:
        raise CalculationInputError(
            f"utilization_ratio must be <= 1, got {ratio}"
        )
    return rp02 * stress_area * ratio


__all__ = ["target_preload_n"]
