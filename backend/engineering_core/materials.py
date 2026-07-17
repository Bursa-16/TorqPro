"""Material-derived strength values.

Moved unchanged from the ``/api/engineering/check`` handler in
backend/app.py (Phase 1). The 0.58 shear-strength factor is the value
already used by the original code; nothing new was introduced.
"""

from __future__ import annotations

# Shear strength factor exactly as used in the original app.py code.
SHEAR_STRENGTH_FACTOR = .58


def shear_strength_mpa(rm_mpa: float) -> float:
    """Shear strength from tensile strength Rm (original: ``.58*rm``)."""
    return .58 * rm_mpa
