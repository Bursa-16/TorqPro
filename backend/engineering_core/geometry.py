"""Metric ISO thread geometry.

Moved unchanged from the ``/api/engineering/check`` handler in
backend/app.py (Phase 1). Coefficients 0.6495 and 1.2269 are the
standard ISO 68-1 metric thread pitch/minor diameter factors already
present in the original code; nothing new was introduced.
"""

from __future__ import annotations

import math

# Factors exactly as used in the original app.py code.
PITCH_DIAMETER_FACTOR = 0.6495
MINOR_DIAMETER_FACTOR = 1.2269


def pitch_diameter_mm(diameter_mm: float, pitch_mm: float) -> float:
    """d2 = d - 0.6495*P (original: ``d2=d-0.6495*p``)."""
    return diameter_mm - 0.6495 * pitch_mm


def minor_diameter_mm(diameter_mm: float, pitch_mm: float) -> float:
    """d3 = d - 1.2269*P (original: ``d3=d-1.2269*p``)."""
    return diameter_mm - 1.2269 * pitch_mm


def helix_angle_rad(pitch_mm: float, pitch_diameter_mm: float) -> float:
    """Thread helix (lead) angle (original: ``math.atan(p/(math.pi*d2))``)."""
    return math.atan(pitch_mm / (math.pi * pitch_diameter_mm))


def thread_shear_area_mm2(diameter_mm: float, engagement_mm: float) -> float:
    """Engaged-thread shear area (original: ``math.pi*d*engagement*.5``)."""
    return math.pi * diameter_mm * engagement_mm * .5
