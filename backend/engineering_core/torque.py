"""Tightening torque calculation.

Moved unchanged from the ``/api/engineering/check`` handler in
backend/app.py (Phase 1). The expression is identical to the original
inner ``torque(mt,mb)`` closure.
"""

from __future__ import annotations

import math

from . import friction, geometry, units


def tightening_torque_nm(preload_n: float, pitch_diameter_mm: float, pitch_mm: float,
                         mu_thread: float, mu_bearing: float,
                         effective_bearing_diameter_mm: float) -> float:
    """Tightening torque in N*m.

    Original::

        helix=math.atan(p/(math.pi*d2))
        rho=math.atan(mt/math.cos(math.pi/6))
        return F*((d2/2)*math.tan(helix+rho)+mb*(x.effective_bearing_diameter_mm/2))/1000
    """
    helix = geometry.helix_angle_rad(pitch_mm, pitch_diameter_mm)
    rho = friction.thread_friction_angle_rad(mu_thread)
    return units.nmm_to_nm(
        preload_n * ((pitch_diameter_mm / 2) * math.tan(helix + rho)
                     + mu_bearing * (effective_bearing_diameter_mm / 2)))
