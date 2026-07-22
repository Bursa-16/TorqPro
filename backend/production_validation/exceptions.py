"""Domain exceptions for the production validation module."""
from __future__ import annotations


class ProductionValidationError(Exception):
    """Base class for all production-validation domain errors."""


class NotFoundError(ProductionValidationError):
    pass


class ConflictError(ProductionValidationError):
    """Uniqueness or duplicate-import conflict."""


class ValidationDataError(ProductionValidationError):
    """Input fails a data-integrity rule (section 5 of the phase spec)."""


class LockedError(ProductionValidationError):
    """Target is locked/immutable (locked dataset, approved study)."""


class StateTransitionError(ProductionValidationError):
    pass


class AuthorizationError(ProductionValidationError):
    pass


class CsvImportError(ProductionValidationError):
    def __init__(self, message: str, row_errors: list | None = None):
        super().__init__(message)
        self.row_errors = row_errors or []
