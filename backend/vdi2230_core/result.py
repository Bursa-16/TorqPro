"""TorqPro VDI 2230 Core - safety / result evaluation structure.

PROVISIONAL result framework (utilization ratio per
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §9; status vocabulary
per ``docs/08_RULE_ENGINE.md`` §4: pass, warn, fail, not_evaluable,
plus the input-quality statuses invalid_input, missing_input and
calculation_error).

No default engineering limit or empirical safety coefficient is
defined anywhere in this module: ``limit_mpa``, ``fail_threshold`` and
``warn_threshold`` must always be supplied by the caller from a
validated source. Missing them yields ``missing_input``, never a
silently assumed default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .exceptions import CalculationDomainError, CalculationInputError, ValidationError
from .formula_ids import FormulaId
from .trace import FormulaTrace, get_trace
from .units import require_finite

STATUS_PASS = "pass"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_NOT_EVALUABLE = "not_evaluable"
STATUS_INVALID_INPUT = "invalid_input"
STATUS_MISSING_INPUT = "missing_input"
STATUS_CALCULATION_ERROR = "calculation_error"


@dataclass(frozen=True)
class SafetyResult:
    """Structured outcome of a safety/result evaluation.

    ``utilization`` is populated only when ``status`` is one of
    ``pass``/``warn``/``fail``; it is ``None`` for every other status
    so a caller can never mistake an unevaluated result for a
    computed one.
    """

    status: str
    utilization: Optional[float]
    message: str
    trace: FormulaTrace


def _require_present(value: Optional[float], name: str) -> None:
    if value is None:
        raise ValidationError(f"{name} is required and was not provided")


def evaluate_safety(
    *,
    stress_mpa: Optional[float],
    limit_mpa: Optional[float],
    fail_threshold: Optional[float],
    warn_threshold: Optional[float] = None,
    evidence_complete: bool = True,
) -> SafetyResult:
    """Evaluate ``stress_mpa`` against ``limit_mpa`` using
    caller-supplied thresholds and return a structured
    ``SafetyResult``.

    ``utilization = stress_mpa / limit_mpa``. Status is ``fail`` if
    ``utilization > fail_threshold``; ``warn`` if ``warn_threshold``
    is given and ``utilization > warn_threshold``; otherwise ``pass``.

    ``evidence_complete=False`` forces ``not_evaluable`` regardless of
    the numeric values, per the "evidence missing, not convertible to
    pass" rule in ``docs/08_RULE_ENGINE.md`` §4.

    This function never raises: every expected failure mode is caught
    and returned as a structured, non-``pass`` status.
    """
    trace = get_trace(FormulaId.VDI2230_RESULT)

    try:
        _require_present(stress_mpa, "stress_mpa")
        _require_present(limit_mpa, "limit_mpa")
        _require_present(fail_threshold, "fail_threshold")

        stress = require_finite(stress_mpa, "stress_mpa")
        if stress < 0:
            raise CalculationInputError(f"stress_mpa must be >= 0, got {stress}")

        limit = require_finite(limit_mpa, "limit_mpa")
        if limit <= 0:
            raise CalculationInputError(f"limit_mpa must be > 0, got {limit}")

        fail_t = require_finite(fail_threshold, "fail_threshold")
        if fail_t <= 0:
            raise CalculationInputError(
                f"fail_threshold must be > 0, got {fail_t}"
            )

        warn_t: Optional[float] = None
        if warn_threshold is not None:
            warn_t = require_finite(warn_threshold, "warn_threshold")
            if warn_t <= 0:
                raise CalculationInputError(
                    f"warn_threshold must be > 0, got {warn_t}"
                )
            if warn_t >= fail_t:
                raise CalculationInputError(
                    "warn_threshold must be < fail_threshold, got "
                    f"warn_threshold={warn_t}, fail_threshold={fail_t}"
                )
    except ValidationError as exc:
        return SafetyResult(
            status=STATUS_MISSING_INPUT, utilization=None, message=str(exc), trace=trace
        )
    except CalculationInputError as exc:
        return SafetyResult(
            status=STATUS_INVALID_INPUT, utilization=None, message=str(exc), trace=trace
        )

    if not evidence_complete:
        return SafetyResult(
            status=STATUS_NOT_EVALUABLE,
            utilization=None,
            message="Supporting engineering evidence is incomplete",
            trace=trace,
        )

    try:
        utilization = stress / limit
    except (ZeroDivisionError, CalculationDomainError) as exc:  # pragma: no cover
        # Defensive: limit > 0 is already guaranteed above, so this
        # branch is not reachable through the public contract.
        return SafetyResult(
            status=STATUS_CALCULATION_ERROR, utilization=None, message=str(exc), trace=trace
        )

    if utilization > fail_t:
        return SafetyResult(
            status=STATUS_FAIL,
            utilization=utilization,
            message="Utilization exceeds fail threshold",
            trace=trace,
        )
    if warn_t is not None and utilization > warn_t:
        return SafetyResult(
            status=STATUS_WARN,
            utilization=utilization,
            message="Utilization exceeds warn threshold",
            trace=trace,
        )
    return SafetyResult(
        status=STATUS_PASS,
        utilization=utilization,
        message="Utilization within limits",
        trace=trace,
    )


__all__ = [
    "SafetyResult",
    "evaluate_safety",
    "STATUS_PASS",
    "STATUS_WARN",
    "STATUS_FAIL",
    "STATUS_NOT_EVALUABLE",
    "STATUS_INVALID_INPUT",
    "STATUS_MISSING_INPUT",
    "STATUS_CALCULATION_ERROR",
]
