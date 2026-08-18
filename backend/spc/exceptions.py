"""Exceptions for the SPC engine (Faz 2.5B).

Deliberately separate from ``backend.production_validation.exceptions``:
the SPC engine has no dependency on the production-validation domain,
so it defines its own fail-closed exception type rather than reusing
one from an unrelated module.
"""
from __future__ import annotations


class SPCDataError(Exception):
    """Raised when input to an SPC calculation is invalid.

    Covers: insufficient sample size, non-finite values (NaN/Inf),
    non-numeric values, and any other input that cannot be treated as
    a valid, unambiguous numeric observation. The SPC engine fails
    closed - it never silently filters, skips, or coerces invalid
    observations and continues.
    """
