"""Faz 2.4.0 tests: oem_library.py (adapter-only, no data of its own)."""

from __future__ import annotations

import pytest

from backend.library import oem_library
from backend.library.oem_library import OEM_LIBRARY
from backend.library.registry import get_library
from backend.library.search import CATEGORY_LIBRARY_MAP, search_by_category
from backend.standards.fiat import FIAT_9_55823
from backend.standards.registry import get_standard


def test_oem_library_registered_with_no_records():
    lib = get_library("OEM Library")
    assert lib is OEM_LIBRARY
    assert lib.records == []
    assert lib.metadata.record_count == 0


def test_oem_library_carries_no_engineering_data():
    # OEM_LIBRARY's own metadata must not embed any standard content
    # (source_standard/description are generic, not copied values).
    assert OEM_LIBRARY.metadata.source_standard == ""


def test_resolve_oem_reference_returns_live_standards_object():
    resolved = oem_library.resolve_oem_reference(FIAT_9_55823.name)
    expected = get_standard(FIAT_9_55823.name)
    assert resolved is expected  # same object -- nothing was copied


def test_resolve_oem_reference_unknown_raises_key_error():
    with pytest.raises(KeyError):
        oem_library.resolve_oem_reference("Not A Real Standard")


def test_list_oem_references_is_read_only_passthrough():
    names = oem_library.list_oem_references()
    assert FIAT_9_55823.name in names


def test_oem_category_registered_in_category_library_map():
    assert CATEGORY_LIBRARY_MAP["oem"] == "oem library"
    assert search_by_category("oem") is OEM_LIBRARY
