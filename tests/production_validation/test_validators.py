import math

import pytest

from backend.production_validation.exceptions import ValidationDataError
from backend.production_validation.validators import (
    validate_characteristic_type,
    validate_invalid_reason,
    validate_measured_value,
    validate_spec_limits,
    validate_study_type,
    validate_subgroup_size,
    validate_unit_present,
)


def test_spec_limits_lower_must_be_below_upper():
    validate_spec_limits(40.0, 50.0)
    with pytest.raises(ValidationDataError):
        validate_spec_limits(50.0, 40.0)
    with pytest.raises(ValidationDataError):
        validate_spec_limits(40.0, 40.0)


def test_spec_limits_target_must_be_within_bounds():
    validate_spec_limits(40.0, 50.0, 45.0)
    with pytest.raises(ValidationDataError):
        validate_spec_limits(40.0, 50.0, 60.0)


def test_subgroup_size_must_be_positive():
    validate_subgroup_size(5)
    validate_subgroup_size(None)
    with pytest.raises(ValidationDataError):
        validate_subgroup_size(0)
    with pytest.raises(ValidationDataError):
        validate_subgroup_size(-3)


def test_measured_value_rejects_nan_and_infinity():
    validate_measured_value(45.2)
    with pytest.raises(ValidationDataError):
        validate_measured_value(math.nan)
    with pytest.raises(ValidationDataError):
        validate_measured_value(math.inf)
    with pytest.raises(ValidationDataError):
        validate_measured_value(-math.inf)


def test_measured_value_requires_numeric():
    with pytest.raises(ValidationDataError):
        validate_measured_value(None)
    with pytest.raises(ValidationDataError):
        validate_measured_value("not-a-number")


def test_unit_present_rejects_blank():
    validate_unit_present("Nm")
    with pytest.raises(ValidationDataError):
        validate_unit_present("")
    with pytest.raises(ValidationDataError):
        validate_unit_present("   ")
    with pytest.raises(ValidationDataError):
        validate_unit_present(None)


def test_invalid_reason_required_when_invalid():
    validate_invalid_reason(True, None)
    validate_invalid_reason(False, "kalibrasyon dışı")
    with pytest.raises(ValidationDataError):
        validate_invalid_reason(False, None)
    with pytest.raises(ValidationDataError):
        validate_invalid_reason(False, "   ")


def test_study_type_and_characteristic_type_whitelist():
    validate_study_type("torque_validation")
    with pytest.raises(ValidationDataError):
        validate_study_type("not_a_type")
    validate_characteristic_type("residual_torque")
    with pytest.raises(ValidationDataError):
        validate_characteristic_type("not_a_characteristic")
