"""CalculationInputError name-overlap isolation tests.

``backend.calculation_engine.exceptions.CalculationInputError`` and
``backend.vdi2230_core.exceptions.CalculationInputError`` share a
class name but live in separate packages with separate base classes
(see docstrings in both ``exceptions.py`` modules). This module
verifies, at both the class-identity level and the
``VDI2230Provider`` orchestration level, that the two never get
confused with each other: an engine-boundary failure (a required
request field is missing) must surface as the engine's own
exception, and a core-domain failure (a malformed physical value)
must propagate as the core's own exception, unconverted.
"""

from __future__ import annotations

import pytest

from backend.calculation_engine import CalculationRequest
from backend.calculation_engine.exceptions import (
    CalculationEngineError,
    CalculationInputError as EngineCalculationInputError,
)
from backend.calculation_engine.providers.vdi2230_provider import VDI2230Provider
from backend.vdi2230_core.exceptions import (
    CalculationInputError as CoreCalculationInputError,
    Vdi2230CoreError,
)

_BOLT_SEGMENTS = [
    {"length_mm": 20.0, "modulus_mpa": 210000.0, "area_mm2": 78.5},
    {"length_mm": 10.0, "modulus_mpa": 210000.0, "area_mm2": 58.0},
]
_JOINT_SEGMENTS = [
    {"length_mm": 15.0, "modulus_mpa": 210000.0, "area_mm2": 200.0},
]


def _base_inputs(**overrides):
    inputs = {
        "diameter_mm": 10.0,
        "pitch_mm": 1.5,
        "rp02_mpa": 640.0,
        "utilization_ratio": 0.9,
        "bolt_segments": [dict(s) for s in _BOLT_SEGMENTS],
        "joint_segments": [dict(s) for s in _JOINT_SEGMENTS],
        "external_axial_load_n": 5000.0,
    }
    inputs.update(overrides)
    return inputs


@pytest.fixture
def provider() -> VDI2230Provider:
    return VDI2230Provider()


# ---------------------------------------------------------------------------
# Class-identity: the two CalculationInputError classes must be distinct.
# ---------------------------------------------------------------------------


def test_engine_and_core_calculation_input_error_are_distinct_classes():
    assert EngineCalculationInputError is not CoreCalculationInputError


def test_engine_and_core_calculation_input_error_share_no_inheritance():
    assert not issubclass(EngineCalculationInputError, CoreCalculationInputError)
    assert not issubclass(CoreCalculationInputError, EngineCalculationInputError)


def test_engine_calculation_input_error_base_is_calculation_engine_error():
    assert issubclass(EngineCalculationInputError, CalculationEngineError)
    assert not issubclass(EngineCalculationInputError, Vdi2230CoreError)


def test_core_calculation_input_error_base_is_vdi2230_core_error():
    assert issubclass(CoreCalculationInputError, Vdi2230CoreError)
    assert not issubclass(CoreCalculationInputError, CalculationEngineError)


# ---------------------------------------------------------------------------
# Orchestration-level: the provider must raise the correct one of the two,
# never converting one into the other.
# ---------------------------------------------------------------------------


def test_missing_request_key_raises_engine_error_not_core_error(provider):
    """A boundary failure (request malformed before any core call) must
    raise the engine's own CalculationInputError, and specifically must
    NOT be an instance of the core's same-named exception."""
    request = CalculationRequest(standard="VDI2230", inputs={})

    with pytest.raises(EngineCalculationInputError) as excinfo:
        provider.calculate(request)

    assert not isinstance(excinfo.value, CoreCalculationInputError)


def test_malformed_physical_value_raises_core_error_not_engine_error(provider):
    """A domain failure detected inside backend.vdi2230_core (NaN
    diameter) must propagate as the core's own CalculationInputError,
    unconverted -- the provider must NOT re-wrap it as, or mistake it
    for, the engine's boundary exception."""
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(diameter_mm=float("nan")),
    )

    with pytest.raises(CoreCalculationInputError) as excinfo:
        provider.calculate(request)

    assert not isinstance(excinfo.value, EngineCalculationInputError)


def test_negative_rp02_raises_core_error_not_engine_error(provider):
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(rp02_mpa=-640.0),
    )

    with pytest.raises(CoreCalculationInputError) as excinfo:
        provider.calculate(request)

    assert not isinstance(excinfo.value, EngineCalculationInputError)


def test_malformed_segment_type_raises_engine_error_not_core_error(provider):
    """bolt_segments of the wrong shape is caught at the provider's
    own request-mapping boundary (before any vdi2230_core call), so it
    must raise the engine's exception, not the core's."""
    request = CalculationRequest(
        standard="VDI2230",
        inputs=_base_inputs(bolt_segments="not-a-list"),
    )

    with pytest.raises(EngineCalculationInputError) as excinfo:
        provider.calculate(request)

    assert not isinstance(excinfo.value, CoreCalculationInputError)
