"""TorqPro Engineering Library - exception hierarchy (Faz 2.4.2A).

Mirrors the isolated-per-package exception convention already
established by ``backend.vdi2230_core.exceptions`` and
``backend.calculation_engine.exceptions`` (see
``tests/test_exception_isolation.py``): each subsystem owns its own
root exception rather than sharing one global hierarchy. No existing
``backend.library`` error class existed before this module, so this
introduces ``LibraryError`` as that root -- not a competing parallel
hierarchy, since none was previously in place for this package.
"""

from __future__ import annotations


class LibraryError(Exception):
    """Base class for all backend.library errors."""


class OEMStandardNotFoundError(LibraryError, KeyError):
    """No standard is registered under the requested OEM reference id.

    Raised by ``backend.library.oem_library.resolve_oem_reference``
    in place of the raw ``KeyError`` that
    ``backend.standards.registry.get_standard`` raises, so callers
    only need to catch ``backend.library`` exceptions at this
    package's boundary. Also inherits from the builtin ``KeyError``
    (multiple inheritance, same pattern as
    ``json.JSONDecodeError(ValueError)``) so any pre-existing
    ``except KeyError`` / ``pytest.raises(KeyError)`` call site keeps
    working unchanged -- this is a strictly more specific exception,
    not a behavioural break.
    """

    def __init__(self, standard_id: str) -> None:
        self.standard_id = standard_id
        super().__init__(f"OEM standard reference not found: {standard_id}")


__all__ = ["LibraryError", "OEMStandardNotFoundError"]
