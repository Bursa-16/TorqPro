"""Phase 1.2 Standards Engine infrastructure tests.

Verifies registry behaviour and standard metadata only.
No calculation behaviour is touched.
"""

import pytest

# Dual import path: repo root (backend.standards) or backend/ on sys.path
# (CI import check), mirroring the engineering_core test convention.
try:
    from backend.standards import (
        BaseStandard,
        get_standard,
        list_standards,
        register,
        supported_methods,
    )
    from backend.standards.oem import define_oem_standard
    from backend import engineering_core
    from backend import standards
except ImportError:
    from standards import (
        BaseStandard,
        get_standard,
        list_standards,
        register,
        supported_methods,
    )
    from standards.oem import define_oem_standard
    import engineering_core
    import standards


def test_package_imports_without_side_effects():
    assert hasattr(standards, "registry")
    assert hasattr(standards, "base_standard")


def test_all_expected_standards_registered():
    names = {s.name for s in list_standards()}
    expected = {
        "ISO 898-1",
        "ISO 965-1",
        "DIN 13-1",
        "DIN 946",
        "EN 1090-2",
        "EN 14399",
        "VDI 2230-1",
        "FIAT 9.55823",
    }
    assert expected.issubset(names)


def test_get_standard_is_case_insensitive():
    std = get_standard("vdi 2230-1")
    assert std.name == "VDI 2230-1"
    assert std.organization == "VDI"


def test_get_standard_unknown_raises_key_error():
    with pytest.raises(KeyError):
        get_standard("NOPE 0000")


def test_supported_methods_returns_list():
    methods = supported_methods("VDI 2230-1")
    assert isinstance(methods, list)
    assert "tightening_torque" in methods


def test_register_rejects_non_standard():
    with pytest.raises(TypeError):
        register("not-a-standard")


def test_metadata_fields_present():
    std = get_standard("ISO 898-1")
    assert isinstance(std, BaseStandard)
    assert std.version
    assert std.status == "active"
    assert std.description
    assert std.supported_fasteners
    assert std.reference_documents


def test_define_oem_standard_helper():
    std = define_oem_standard(
        name="TEST-OEM-1",
        organization="TestCo",
        supported_calculations=("tightening_torque",),
    )
    assert get_standard("test-oem-1") is std


def test_standards_engine_does_not_touch_engineering_core():
    core_modules = set(engineering_core.__all__)
    assert not core_modules & set(standards.__all__)
