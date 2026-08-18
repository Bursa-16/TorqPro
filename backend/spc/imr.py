"""Individuals / Moving Range (I-MR) control chart engine (Faz 2.5B).

This module is a pure, deterministic SPC mathematical engine. It has
no dependency on ``backend.production_validation`` or any other
domain/persistence module.

Input order is entirely caller-owned: ``compute_imr`` performs no
sorting and has no concept of a sequence number, timestamp, or any
other production-validation ordering semantics. Values are processed
in exactly the order supplied. Attaching validated, ordered
measurement data to this engine (e.g. from
``backend.production_validation.MeasurementRecord``) is explicitly out
of scope for Faz 2.5B and belongs to a future adapter/integration
phase.

Moving-range span is fixed at 2 (consecutive-pair range). This is not
generalized to an arbitrary span in this phase.

Sigma methodology note (future-compatibility boundary): ``sigma_hat``
on the returned result is this module's own within-series estimator,
``MR_bar / d2``. It is specific to the I-MR method. A future capability
phase (Cp/Cpk/Pp/Ppk) must define its own sigma methodology explicitly
rather than implicitly reusing this value - Cp/Cpk may adopt an
approved within-process estimator by deliberate future choice, while
Pp/Ppk require an overall-process variation estimate. No capability
calculation is implemented here, and no future capability module
should assume a dependency on this module's sigma estimate without a
separately justified methodology decision at that time.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional, Sequence

from backend.spc.exceptions import SPCDataError

# Standard SPC bias/control-limit constants for moving-range span 2.
# Standard SPC notation for the bias constant is lowercase "d2"; the
# identifier below is capitalized only because Python module-level
# constants conventionally use upper case - it refers to the same
# standard d2 = 1.128 value tabulated for subgroup/span size 2, not a
# distinct "D2" constant family (D3/D4 below are a different, genuinely
# separate constant family from d2).
D2_BIAS_CONSTANT_MR2: float = 1.128  # standard notation: d2, moving-range span 2
D3_CONSTANT_MR2: float = 0.0
D4_CONSTANT_MR2: float = 3.267
SIGMA_MULTIPLIER: float = 3.0

_MIN_OBSERVATIONS = 2


@dataclass(frozen=True)
class IMRPoint:
    """A single observation's position on the I-MR chart.

    Attributes:
        index: 1-based position in the caller-supplied ordered
            sequence.
        value: The observation's numeric value.
        moving_range: ``abs(value - previous_value)``. ``None`` for
            the first point, which has no prior observation.
        out_of_control: Whether ``value`` falls strictly beyond the
            individuals chart's UCL/LCL. Basic control-limit
            classification only - not a Nelson rule, zone, or pattern
            evaluation.
    """

    index: int
    value: float
    moving_range: Optional[float]
    out_of_control: bool


@dataclass(frozen=True)
class IMRResult:
    """Immutable I-MR control chart result.

    Attributes:
        points: Ordered per-observation results, in the exact order
            supplied to ``compute_imr``.
        center_line: Individuals chart center line (mean of values).
        ucl_individuals: Individuals chart upper control limit.
        lcl_individuals: Individuals chart lower control limit. Not
            clamped to zero - a negative value is a valid,
            methodology-defined result.
        mr_center_line: Moving-range chart center line (MR_bar).
        ucl_mr: Moving-range chart upper control limit.
        lcl_mr: Moving-range chart lower control limit. Zero for
            moving-range span 2 (D3 = 0), by the standard formula
            itself rather than any application-level clamp.
        sigma_hat: Estimated process sigma (MR_bar / d2). Specific to
            this I-MR estimator - see module docstring.
        n: Number of observations in the input sequence.
    """

    points: tuple  # tuple[IMRPoint, ...]
    center_line: float
    ucl_individuals: float
    lcl_individuals: float
    mr_center_line: float
    ucl_mr: float
    lcl_mr: float
    sigma_hat: float
    n: int


def _is_out_of_control(value: float, ucl: float, lcl: float) -> bool:
    """Strict basic control-limit classification.

    A value exactly on UCL or LCL is in control. Only values strictly
    beyond a limit are out of control. No epsilon/tolerance is used -
    this is an exact comparison. This function implements basic
    individuals control-limit classification only; it is not a Nelson
    rule, Western Electric rule, zone, run, trend, or pattern
    evaluation.
    """
    return value > ucl or value < lcl


def _validate_observation(raw_value) -> float:
    """Convert and validate a single observation.

    Fails closed with ``SPCDataError`` for anything that is not
    unambiguously a finite numeric observation: booleans, NaN, +/-Inf,
    ``None``, and values that cannot be converted to ``float`` at all.
    No filtering-and-continuing, no silent coercion of ambiguous
    input.
    """
    # bool is a subtype of int in Python, so it would otherwise pass a
    # naive float() coercion as 1.0/0.0. Reject explicitly.
    if isinstance(raw_value, bool):
        raise SPCDataError(
            f"observation must be numeric, not a boolean: {raw_value!r}"
        )
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise SPCDataError(
            f"observation is not a valid numeric value: {raw_value!r}"
        )
    if not isfinite(value):
        raise SPCDataError(
            f"observation must be finite (NaN/Infinity rejected): {raw_value!r}"
        )
    return value


def _require_finite(value: float, description: str) -> float:
    """Fail closed if a computed intermediate/final value is non-finite.

    Individually finite observations can still combine (via
    subtraction, summation, or division) into a non-finite computed
    quantity - e.g. ``abs(1e308 - (-1e308))`` overflows to ``inf``
    even though both operands are finite. The engine's deterministic
    result is only authoritative if every computed quantity is
    actually finite; a silently returned ``inf``/``nan`` would violate
    the fail-closed contract just as much as an invalid raw input
    would.
    """
    if not isfinite(value):
        raise SPCDataError(
            f"computed {description} is not finite ({value!r}); "
            "input magnitude produced numeric overflow"
        )
    return value


def compute_imr(values: Sequence[float]) -> IMRResult:
    """Compute an Individuals / Moving Range (I-MR) control chart.

    Args:
        values: Ordered observations, in the exact order the caller
            wants them charted. This function performs no sorting and
            has no concept of a sequence number or timestamp - order
            is entirely caller-owned.

    Returns:
        An immutable ``IMRResult``.

    Raises:
        SPCDataError: If fewer than 2 observations are supplied, or
            any observation is not a finite numeric value (NaN, +Inf,
            -Inf, boolean, non-numeric, or otherwise invalid).

    Note:
        ``n == 2`` means the calculation is mathematically defined -
        one moving range is computable. It does NOT mean the sample is
        statistically adequate for establishing a process baseline.
        This function implements no minimum-sample-size policy beyond
        mathematical computability; any stricter adequacy threshold is
        a caller/policy decision outside this phase's scope.
    """
    if values is None:
        raise SPCDataError("values must not be None")

    validated = [_validate_observation(v) for v in values]
    n = len(validated)

    if n < _MIN_OBSERVATIONS:
        raise SPCDataError(
            f"at least {_MIN_OBSERVATIONS} observations are required to "
            f"compute an I-MR chart, got {n}"
        )

    moving_ranges = [
        _require_finite(abs(validated[i] - validated[i - 1]), "moving range")
        for i in range(1, n)
    ]
    mr_bar = _require_finite(
        sum(moving_ranges) / len(moving_ranges), "moving-range average (MR_bar)"
    )
    x_bar = _require_finite(sum(validated) / n, "center line (X_bar)")

    sigma_hat = _require_finite(
        mr_bar / D2_BIAS_CONSTANT_MR2, "estimated sigma (sigma_hat)"
    )

    ucl_individuals = _require_finite(
        x_bar + SIGMA_MULTIPLIER * sigma_hat, "individuals UCL"
    )
    lcl_individuals = _require_finite(
        x_bar - SIGMA_MULTIPLIER * sigma_hat, "individuals LCL"
    )

    ucl_mr = _require_finite(D4_CONSTANT_MR2 * mr_bar, "moving-range UCL")
    lcl_mr = _require_finite(D3_CONSTANT_MR2 * mr_bar, "moving-range LCL")

    points = []
    for i, value in enumerate(validated):
        moving_range = moving_ranges[i - 1] if i > 0 else None
        points.append(
            IMRPoint(
                index=i + 1,
                value=value,
                moving_range=moving_range,
                out_of_control=_is_out_of_control(
                    value, ucl_individuals, lcl_individuals
                ),
            )
        )

    return IMRResult(
        points=tuple(points),
        center_line=x_bar,
        ucl_individuals=ucl_individuals,
        lcl_individuals=lcl_individuals,
        mr_center_line=mr_bar,
        ucl_mr=ucl_mr,
        lcl_mr=lcl_mr,
        sigma_hat=sigma_hat,
        n=n,
    )
