"""Tests for backend.spc.imr (Faz 2.5B)."""
from __future__ import annotations

import math

import pytest

from backend.spc.exceptions import SPCDataError
from backend.spc.imr import (
    D2_BIAS_CONSTANT_MR2,
    D3_CONSTANT_MR2,
    D4_CONSTANT_MR2,
    SIGMA_MULTIPLIER,
    _is_out_of_control,
    compute_imr,
)


# ---------------------------------------------------------------- hand-calculated


def test_hand_calculated_case():
    # values: 20, 22, 24, 21, 23
    # moving ranges: |22-20|=2, |24-22|=2, |21-24|=3, |23-21|=2
    result = compute_imr([20, 22, 24, 21, 23])

    assert result.n == 5
    assert result.center_line == pytest.approx(22.0)

    mr_values = [p.moving_range for p in result.points]
    assert mr_values == [None, pytest.approx(2.0), pytest.approx(2.0), pytest.approx(3.0), pytest.approx(2.0)]

    mr_bar = 2.25
    assert result.mr_center_line == pytest.approx(mr_bar)

    sigma_hat = mr_bar / 1.128
    assert result.sigma_hat == pytest.approx(sigma_hat)

    assert result.ucl_individuals == pytest.approx(22.0 + 3 * sigma_hat)
    assert result.lcl_individuals == pytest.approx(22.0 - 3 * sigma_hat)

    assert result.ucl_mr == pytest.approx(3.267 * mr_bar)
    assert result.lcl_mr == pytest.approx(0.0)

    # point structure / ordering preserved exactly
    assert [p.value for p in result.points] == [20, 22, 24, 21, 23]
    assert [p.index for p in result.points] == [1, 2, 3, 4, 5]
    assert all(p.out_of_control is False for p in result.points)


# ---------------------------------------------------------------- minimum sample


def test_minimum_sample_n_equals_2():
    result = compute_imr([5, 8])
    assert result.n == 2
    assert result.points[0].moving_range is None
    assert result.points[1].moving_range == pytest.approx(3.0)


def test_insufficient_sample_n_equals_1():
    with pytest.raises(SPCDataError):
        compute_imr([5])


def test_insufficient_sample_empty():
    with pytest.raises(SPCDataError):
        compute_imr([])


# ---------------------------------------------------------------- constant series


def test_constant_series_is_valid_degenerate_result():
    result = compute_imr([7, 7, 7, 7])

    assert result.center_line == pytest.approx(7.0)
    assert result.mr_center_line == pytest.approx(0.0)
    assert result.sigma_hat == pytest.approx(0.0)
    assert result.ucl_individuals == pytest.approx(7.0)
    assert result.lcl_individuals == pytest.approx(7.0)
    assert result.ucl_mr == pytest.approx(0.0)
    assert result.lcl_mr == pytest.approx(0.0)

    assert all(p.out_of_control is False for p in result.points)
    assert all(
        p.moving_range == pytest.approx(0.0)
        for p in result.points
        if p.moving_range is not None
    )


# ---------------------------------------------------------------- monotonic series


def test_increasing_sequence_moving_ranges():
    result = compute_imr([1, 2, 3, 4, 5])
    mrs = [p.moving_range for p in result.points[1:]]
    assert all(mr == pytest.approx(1.0) for mr in mrs)


def test_decreasing_sequence_moving_ranges_use_absolute_value():
    result = compute_imr([5, 4, 3, 2, 1])
    mrs = [p.moving_range for p in result.points[1:]]
    assert all(mr == pytest.approx(1.0) for mr in mrs)


# ---------------------------------------------------------------- deterministic beyond-limit


def test_deterministic_beyond_limit_case():
    values = [10, 10, 10, 10, 10, 1000]
    result = compute_imr(values)

    # independent hand calculation
    moving_ranges = [0, 0, 0, 0, 990]
    mr_bar = sum(moving_ranges) / len(moving_ranges)  # 198
    x_bar = (10 * 5 + 1000) / 6  # 175
    sigma_hat = mr_bar / 1.128
    ucl = x_bar + 3 * sigma_hat
    lcl = x_bar - 3 * sigma_hat

    assert result.mr_center_line == pytest.approx(mr_bar)
    assert result.center_line == pytest.approx(x_bar)
    assert result.sigma_hat == pytest.approx(sigma_hat)
    assert result.ucl_individuals == pytest.approx(ucl)
    assert result.lcl_individuals == pytest.approx(lcl)

    # independently verify the outlier is actually beyond the computed limit
    assert 1000 > ucl

    for p in result.points[:5]:
        assert p.out_of_control is False
    assert result.points[5].out_of_control is True


# ---------------------------------------------------------------- boundary predicate


def test_boundary_predicate_exact_ucl_is_in_control():
    assert _is_out_of_control(value=100.0, ucl=100.0, lcl=50.0) is False


def test_boundary_predicate_exact_lcl_is_in_control():
    assert _is_out_of_control(value=50.0, ucl=100.0, lcl=50.0) is False


def test_boundary_predicate_above_ucl_is_out_of_control():
    assert _is_out_of_control(value=100.0001, ucl=100.0, lcl=50.0) is True


def test_boundary_predicate_below_lcl_is_out_of_control():
    assert _is_out_of_control(value=49.9999, ucl=100.0, lcl=50.0) is True


# ---------------------------------------------------------------- invalid values


def test_rejects_nan():
    with pytest.raises(SPCDataError):
        compute_imr([1, 2, math.nan])


def test_rejects_positive_infinity():
    with pytest.raises(SPCDataError):
        compute_imr([1, 2, math.inf])


def test_rejects_negative_infinity():
    with pytest.raises(SPCDataError):
        compute_imr([1, 2, -math.inf])


def test_rejects_boolean_observation():
    with pytest.raises(SPCDataError):
        compute_imr([1, 2, True])


def test_rejects_non_numeric_string():
    with pytest.raises(SPCDataError):
        compute_imr([1, 2, "not-a-number"])


def test_rejects_none_observation():
    with pytest.raises(SPCDataError):
        compute_imr([1, 2, None])


def test_rejects_finite_inputs_that_overflow_to_non_finite_moving_range():
    # Both values are individually finite, but abs(1e308 - (-1e308))
    # overflows float range to inf. The engine must fail closed on the
    # non-finite computed moving range rather than silently returning
    # an infinite result.
    with pytest.raises(SPCDataError):
        compute_imr([1e308, -1e308])


# ---------------------------------------------------------------- ordering


def test_input_order_is_preserved_exactly_no_sorting():
    values = [30, 10, 20, 5, 25]
    result = compute_imr(values)
    assert [p.value for p in result.points] == values
    assert [p.index for p in result.points] == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------- constants sanity


def test_constants_match_approved_values():
    assert D2_BIAS_CONSTANT_MR2 == pytest.approx(1.128)
    assert D3_CONSTANT_MR2 == pytest.approx(0.0)
    assert D4_CONSTANT_MR2 == pytest.approx(3.267)
    assert SIGMA_MULTIPLIER == pytest.approx(3.0)
