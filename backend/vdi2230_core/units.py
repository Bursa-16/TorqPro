"""TorqPro VDI 2230 Core - unit labels and shared numeric guards.

Phase 2.2. Unit convention is SI throughout this package: length in
millimetres (mm), force in newtons (N), stress in megapascals
(MPa = N/mm^2), stiffness in newtons per millimetre (N/mm) and moment
in newton-metres (Nm) at any future API boundary. Dimensionless ratios
(``Phi``, utilization) carry an empty unit label.

This module holds only unit labels and shared "is this a well-formed,
in-domain number" guards -- never formula arithmetic. Keeping these
separate means a unit-system change or a stricter numeric guard never
touches the calculation logic in ``stress_area.py``, ``preload.py``,
``stiffness.py``, ``load_factor.py`` or ``result.py``.
"""

from __future__ import annotations

import math
from numbers import Real

from .exceptions import CalculationInputError

NEWTON = "N"
MILLIMETRE = "mm"
MEGAPASCAL = "MPa"
NEWTON_METRE = "Nm"
NEWTON_PER_MILLIMETRE = "N/mm"
DIMENSIONLESS = ""


def require_finite(value: object, name: str) -> float:
    """Return ``value`` as a ``float`` if it is a well-formed, finite
    real number; raise ``CalculationInputError`` otherwise (``None``,
    wrong type, ``NaN`` or infinite)."""
    if value is None:
        raise CalculationInputError(f"{name} must not be None")
    if isinstance(value, bool) or not isinstance(value, Real):
        raise CalculationInputError(
            f"{name} must be a real number, got {type(value).__name__}"
        )
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise CalculationInputError(f"{name} must be a finite number, got {number}")
    return number


def require_positive(value: object, name: str) -> float:
    """Return ``value`` as a finite ``float`` strictly greater than
    zero; raise ``CalculationInputError`` otherwise."""
    number = require_finite(value, name)
    if number <= 0:
        raise CalculationInputError(f"{name} must be > 0, got {number}")
    return number


def require_non_negative(value: object, name: str) -> float:
    """Return ``value`` as a finite ``float`` greater than or equal to
    zero; raise ``CalculationInputError`` otherwise."""
    number = require_finite(value, name)
    if number < 0:
        raise CalculationInputError(f"{name} must be >= 0, got {number}")
    return number


def require_range(value: object, name: str, low: float, high: float) -> float:
    """Return ``value`` as a finite ``float`` within ``[low, high]``
    (inclusive); raise ``CalculationInputError`` otherwise."""
    number = require_finite(value, name)
    if not (low <= number <= high):
        raise CalculationInputError(
            f"{name} must be within [{low}, {high}], got {number}"
        )
    return number


__all__ = [
    "NEWTON",
    "MILLIMETRE",
    "MEGAPASCAL",
    "NEWTON_METRE",
    "NEWTON_PER_MILLIMETRE",
    "DIMENSIONLESS",
    "require_finite",
    "require_positive",
    "require_non_negative",
    "require_range",
]
