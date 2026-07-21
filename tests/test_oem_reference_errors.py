"""Faz 2.4.2A tests: OEM reference error isolation.

Covers ``backend.library.exceptions.OEMStandardNotFoundError`` and its
use in ``backend.library.oem_library.resolve_oem_reference``. Does not
touch or duplicate ``tests/test_library_oem_adapter.py`` (Faz 2.4.0),
which already covers the successful-resolution and read-only-pass-
through behaviour; this file adds only what that file did not cover:
the new exception's type, attributes, chaining, and the guarantee
that pre-existing ``except KeyError`` call sites keep working.
"""

from __future__ import annotations

import pytest

from backend.library import oem_library
from backend.library.exceptions import LibraryError, OEMStandardNotFoundError
from backend.standards.fiat import FIAT_9_55823
from backend.standards.registry import get_standard


def test_existing_oem_reference_still_resolves_correctly():
    resolved = oem_library.resolve_oem_reference(FIAT_9_55823.name)
    expected = get_standard(FIAT_9_55823.name)
    assert resolved is expected


def test_missing_oem_reference_raises_oem_standard_not_found_error():
    with pytest.raises(OEMStandardNotFoundError):
        oem_library.resolve_oem_reference("Not A Real Standard")


def test_missing_oem_reference_still_raises_key_error_for_backward_compatibility():
    # OEMStandardNotFoundError also subclasses KeyError (multiple
    # inheritance), so pre-existing ``except KeyError`` / ``pytest.
    # raises(KeyError)`` call sites keep working unchanged.
    with pytest.raises(KeyError):
        oem_library.resolve_oem_reference("Not A Real Standard")


def test_oem_standard_not_found_error_is_a_library_error():
    with pytest.raises(LibraryError):
        oem_library.resolve_oem_reference("Not A Real Standard")


def test_oem_standard_not_found_error_carries_requested_standard_id():
    with pytest.raises(OEMStandardNotFoundError) as excinfo:
        oem_library.resolve_oem_reference("Not A Real Standard")
    assert excinfo.value.standard_id == "Not A Real Standard"
    assert "Not A Real Standard" in str(excinfo.value)


def test_oem_standard_not_found_error_chains_original_key_error():
    try:
        oem_library.resolve_oem_reference("Not A Real Standard")
    except OEMStandardNotFoundError as exc:
        assert isinstance(exc.__cause__, KeyError)
        assert not isinstance(exc.__cause__, OEMStandardNotFoundError)
    else:
        pytest.fail("expected OEMStandardNotFoundError to be raised")


def test_raw_builtin_key_error_does_not_leak_as_plain_keyerror_instance():
    # The raised exception must be our richer subclass, not a bare
    # builtin KeyError instance -- type(...) is stricter than
    # isinstance(...) and confirms nothing re-raises the original.
    try:
        oem_library.resolve_oem_reference("Not A Real Standard")
    except KeyError as exc:
        assert type(exc) is OEMStandardNotFoundError
    else:
        pytest.fail("expected an exception to be raised")
