"""Unit conversion helpers.

Moved from inline expressions in backend/app.py (Phase 1).
Behaviour-preserving: the arithmetic is identical to the original
inline code (division by 1000, multiplication by 100).
"""

from __future__ import annotations


def nmm_to_nm(value_nmm: float) -> float:
    """Convert a moment from N*mm to N*m. (Original inline code: ``x/1000``)."""
    return value_nmm / 1000


def fraction_to_percent(value: float) -> float:
    """Convert a dimensionless ratio to percent. (Original inline code: ``x*100``)."""
    return value * 100
