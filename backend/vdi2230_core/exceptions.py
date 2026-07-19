"""TorqPro VDI 2230 Core - exception hierarchy.

Phase 2.2. Four expected, distinct failure modes for a pure
calculation package:

- ``CalculationInputError``: a value was supplied but is malformed
  (not a real number, NaN/infinite, or outside its physically valid
  domain such as a negative length).
- ``CalculationDomainError``: individually well-formed inputs combine
  into a mathematically undefined operation for the requested
  calculation (e.g. an empty stiffness-segment list, or
  ``c_b + c_c == 0`` in the load-factor ratio).
- ``MissingFormulaError``: no ``FormulaTrace`` is registered for a
  requested ``FormulaId``.
- ``ValidationError``: a required parameter for a result/threshold
  evaluation was not supplied at all (``None``) -- distinct from
  ``CalculationInputError``, where a value is present but malformed.
"""

from __future__ import annotations


class Vdi2230CoreError(Exception):
    """Base class for all backend.vdi2230_core errors."""


class CalculationInputError(Vdi2230CoreError):
    """A supplied value is not a well-formed, in-domain real number."""


class CalculationDomainError(Vdi2230CoreError):
    """Inputs are individually valid but their combination is
    mathematically undefined for the requested calculation."""


class MissingFormulaError(Vdi2230CoreError):
    """No ``FormulaTrace`` is registered for the requested
    ``FormulaId``."""


class ValidationError(Vdi2230CoreError):
    """A required parameter was not supplied (``None``)."""


__all__ = [
    "Vdi2230CoreError",
    "CalculationInputError",
    "CalculationDomainError",
    "MissingFormulaError",
    "ValidationError",
]
