"""Faz 2.8.12 Stage 2 tests: backend.governance.ownership."""

from __future__ import annotations

from backend.governance import ownership


def test_washer_resolution_is_externally_owned():
    assert ownership.is_externally_owned("washer_resolution") is True


def test_unregistered_aggregate_types_are_not_owned():
    for aggregate_type in (
        "calc_revision",
        "joint_revision",
        "washer_style_issue",
        "production_validation",
        "",
        "unknown_future_type",
    ):
        assert ownership.is_externally_owned(aggregate_type) is False


def test_registry_is_closed_and_contains_exactly_washer_resolution():
    assert ownership.RESTRICTED_AGGREGATE_TYPES == frozenset({"washer_resolution"})


def test_module_never_imports_backend_library():
    """Structural compatibility check (mirrors
    ``tests/governance/test_compatibility.py``'s pattern): the
    ownership module never binds a ``backend.library`` name into its
    own namespace -- it must stay a pure string registry, never a
    second boundary-crossing import. Checked against the module's
    actual bound names, not its documentation text (the module's
    docstring legitimately *discusses* backend.library without
    importing it)."""
    from backend.governance import ownership as mod

    assert "wr" not in mod.__dict__
    assert "washer_resolution" not in mod.__dict__
    assert not any(
        getattr(value, "__module__", "").startswith("backend.library")
        for value in vars(mod).values()
        if hasattr(value, "__module__")
    )
