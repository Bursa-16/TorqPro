"""TorqPro Calculation Engine - base provider contract.

Prerequisite scaffolding. ``Provider`` is the abstract base every
concrete calculation provider (e.g. ``VDI2230Provider``) implements.
It defines no calculation behaviour itself.
"""

from __future__ import annotations

import abc

from .request import CalculationRequest
from .response import CalculationResponse


class Provider(abc.ABC):
    """Abstract base class for a calculation provider.

    Concrete subclasses declare ``standard`` and ``version`` as
    class attributes and implement ``calculate``.
    """

    standard: str
    version: str

    @abc.abstractmethod
    def calculate(
        self, request: CalculationRequest
    ) -> CalculationResponse:
        """Run this provider's calculation for ``request`` and
        return a ``CalculationResponse``."""
        raise NotImplementedError


__all__ = ["Provider"]
