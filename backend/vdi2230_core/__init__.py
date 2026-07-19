"""TorqPro VDI 2230 Core (Phase 2.2).

Independent, pure-Python package implementing a first slice of VDI
2230 bolted-joint calculation building blocks: tensile stress area
(A_s), quick target preload (F_M), generic series-compliance
stiffness (c_b, c_c), the mandatory load-factor / service-force model
(Phi, F_S), and a safety/result evaluation structure.

No calculation in this package is a validated, complete
implementation of VDI 2230 Part 1. Every formula's exact source,
classification and ``PROVISIONAL`` validation status is recorded in
``backend/vdi2230_core/trace.py`` -- see that module and each
calculation module's docstring before relying on any value produced
here.

Explicitly out of scope for this phase (see
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §7, §8, §20):

- bolt substitution-length regions and clamped-part pressure-cone
  effective area (``stiffness.py`` only implements the generic
  series-compliance combinator; callers supply segment geometry);
- detailed tightening-torque decomposition, preload scatter / Monte
  Carlo, settlement, thermal, relaxation, fatigue and torque-angle
  models (§5-§6, §10, §13-§17);
- wiring into
  ``backend.calculation_engine.providers.vdi2230_provider.VDI2230Provider``
  (deferred to a later phase).

This package imports nothing from ``backend.engineering_core``,
``backend.standards``, ``backend.library``, ``backend.calculation_engine``
or ``backend.app`` -- verified by an isolation test in
``tests/test_vdi2230_core.py``, mirroring the same guarantee already
enforced for ``backend.calculation_engine`` in Phase 2.1.
"""

from __future__ import annotations

from .exceptions import (
    CalculationDomainError,
    CalculationInputError,
    MissingFormulaError,
    ValidationError,
    Vdi2230CoreError,
)
from .formula_ids import FormulaId
from .load_factor import load_factor_phi, service_bolt_force_n
from .preload import target_preload_n
from .result import (
    STATUS_CALCULATION_ERROR,
    STATUS_FAIL,
    STATUS_INVALID_INPUT,
    STATUS_MISSING_INPUT,
    STATUS_NOT_EVALUABLE,
    STATUS_PASS,
    STATUS_WARN,
    SafetyResult,
    evaluate_safety,
)
from .stiffness import StiffnessSegment, series_compliance_stiffness_n_per_mm
from .stress_area import tensile_stress_area_mm2
from .trace import FormulaTrace, all_traces, get_trace

__all__ = [
    "Vdi2230CoreError",
    "CalculationInputError",
    "CalculationDomainError",
    "MissingFormulaError",
    "ValidationError",
    "FormulaId",
    "FormulaTrace",
    "get_trace",
    "all_traces",
    "tensile_stress_area_mm2",
    "target_preload_n",
    "StiffnessSegment",
    "series_compliance_stiffness_n_per_mm",
    "load_factor_phi",
    "service_bolt_force_n",
    "SafetyResult",
    "evaluate_safety",
    "STATUS_PASS",
    "STATUS_WARN",
    "STATUS_FAIL",
    "STATUS_NOT_EVALUABLE",
    "STATUS_INVALID_INPUT",
    "STATUS_MISSING_INPUT",
    "STATUS_CALCULATION_ERROR",
]
