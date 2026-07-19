"""TorqPro VDI 2230 Core - load factor Phi and service bolt force F_S.

Mandatory corrected model
(``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §3; also stated as a
non-negotiable project rule in ``docs/12_CLAUDE_CONTEXT.md``)::

    Phi = c_b / (c_b + c_c)
    F_S = F_M + Phi * F_A

The superseded expression ``F_M - Phi * F_A`` for the service bolt
force is explicitly rejected by §3 and is never implemented here --
see the regression test in ``tests/test_vdi2230_core.py`` that proves
this module's result differs from that rejected expression whenever
``F_A != 0``.
"""

from __future__ import annotations

from .exceptions import CalculationDomainError
from .units import require_finite, require_non_negative, require_range


def load_factor_phi(
    bolt_stiffness_n_per_mm: float, clamped_stiffness_n_per_mm: float
) -> float:
    """Load factor Phi = c_b / (c_b + c_c), dimensionless.

    Raises ``CalculationInputError`` if either stiffness is not a
    finite number >= 0. Raises ``CalculationDomainError`` if
    ``c_b + c_c == 0`` (the ratio is mathematically undefined).
    """
    c_b = require_non_negative(bolt_stiffness_n_per_mm, "bolt_stiffness_n_per_mm")
    c_c = require_non_negative(clamped_stiffness_n_per_mm, "clamped_stiffness_n_per_mm")

    total_stiffness = c_b + c_c
    if total_stiffness == 0:
        raise CalculationDomainError(
            "bolt_stiffness_n_per_mm + clamped_stiffness_n_per_mm must "
            "be > 0 to compute Phi"
        )

    phi = c_b / total_stiffness
    # Defensive bound check: mathematically guaranteed by the
    # non-negative inputs validated above, kept explicit so an
    # out-of-range Phi is never silently returned.
    return require_range(phi, "phi", 0.0, 1.0)


def service_bolt_force_n(
    preload_n: float, phi: float, external_axial_load_n: float
) -> float:
    """Service bolt force F_S = F_M + Phi * F_A, in N.

    Raises ``CalculationInputError`` if ``preload_n`` is not a finite
    number >= 0, if ``phi`` is not finite and within ``[0, 1]``, or if
    ``external_axial_load_n`` is not a finite number.
    """
    preload = require_non_negative(preload_n, "preload_n")
    load_factor = require_range(phi, "phi", 0.0, 1.0)
    external_load = require_finite(external_axial_load_n, "external_axial_load_n")
    return preload + load_factor * external_load


__all__ = ["load_factor_phi", "service_bolt_force_n"]
