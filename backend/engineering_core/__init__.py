"""TorqPro Engineering Core.

Deterministic bolted-joint calculation layer, fully decoupled from
UI, API (FastAPI) and persistence code. All functions here were moved
unchanged from backend/app.py during Phase 1 (behaviour-preserving
refactor). No formula, coefficient or rounding behaviour was altered.

Modules:
- geometry:   thread geometry (pitch/minor diameter, helix angle, shear areas)
- friction:   thread friction angle
- materials:  material-derived strengths (shear strength from Rm)
- preload:    preload and proof-load utilization
- torque:     tightening torque
- joint:      joint-level evaluation (composition of the above)
- units:      unit conversions
- validation: reference-data record validation and deviation checks
"""

from . import friction, geometry, joint, materials, preload, torque, units, validation

__all__ = [
    "friction",
    "geometry",
    "joint",
    "materials",
    "preload",
    "torque",
    "units",
    "validation",
]
