"""Thread friction relations.

Moved unchanged from the ``/api/engineering/check`` handler in
backend/app.py (Phase 1). ``math.pi/6`` (30 degrees) is the metric
thread half angle already present in the original expression.
"""

from __future__ import annotations

import math

# Metric thread half angle (60 degrees flank angle / 2), as in original code.
THREAD_HALF_ANGLE_RAD = math.pi / 6


def thread_friction_angle_rad(mu_thread: float) -> float:
    """Effective thread friction angle rho'.

    Original: ``rho=math.atan(mt/math.cos(math.pi/6))``.
    """
    return math.atan(mu_thread / math.cos(math.pi / 6))
