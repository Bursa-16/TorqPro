"""Domain exceptions for the joint foundation layer."""
from __future__ import annotations


class JointError(Exception):
    """Base class for joint-domain errors."""


class JointNotFoundError(JointError):
    pass


class JointCodeConflictError(JointError):
    pass


class JointArchivedError(JointError):
    pass


class JointRevisionNotFoundError(JointError):
    pass


class JointRevisionConflictError(JointError):
    pass


class JointRevisionImmutableError(JointError):
    pass


class JointRevisionStateError(JointError):
    pass
