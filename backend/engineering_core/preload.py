"""Preload calculations.

Moved unchanged from the ``/api/engineering/check`` handler in
backend/app.py (Phase 1).
"""

from __future__ import annotations

from . import units


def preload_from_yield_n(rp02_mpa: float, stress_area_mm2: float,
                         target_yield_ratio: float) -> float:
    """Target preload F = Rp0.2 * As * yield-utilization ratio.

    Original: ``F=x.rp02_mpa*x.stress_area_mm2*x.target_yield_ratio``.
    """
    return rp02_mpa * stress_area_mm2 * target_yield_ratio


def proof_load_utilization_pct(preload_n: float, proof_stress_mpa: float,
                               stress_area_mm2: float) -> float:
    """Nut proof-load utilization in percent.

    Original: ``F/(x.nut_proof_mpa*x.stress_area_mm2)*100``.
    """
    return units.fraction_to_percent(preload_n / (proof_stress_mpa * stress_area_mm2))
