"""TorqPro VDI 2230 Core - formula trace metadata.

Phase 2.2. Every formula in this package has an accompanying,
immutable ``FormulaTrace`` describing its id, symbol, unit, source
(exact reference into
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` / the cross-referenced
existing code), classification and validation status -- the same
fields used by ``backend.calculation_engine.formula_registry`` in
Phase 2.1.

All seven entries are ``PROVISIONAL``: none of them has completed the
independent hand-calculation, golden-case and reviewer sign-off
process required by
``docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`` §20. ``Phi`` and
``F_S`` are the "mandatory corrected model" per §3 (i.e. the
architecturally required, non-negotiable formulas), but that mandate
is a project rule, not a completed governance sign-off, so their
status stays PROVISIONAL like the rest until that process runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .exceptions import MissingFormulaError
from .formula_ids import FormulaId

PROVISIONAL = "PROVISIONAL"


@dataclass(frozen=True)
class FormulaTrace:
    """Immutable traceability record for a single formula."""

    formula_id: FormulaId
    symbol: str
    unit: str
    source: str
    classification: str
    validation_status: str


_CATALOG: Dict[FormulaId, FormulaTrace] = {
    FormulaId.VDI2230_AS: FormulaTrace(
        formula_id=FormulaId.VDI2230_AS,
        symbol="A_s",
        unit="mm^2",
        source=(
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §2, §9 "
            "(symbol only, formula not stated); d2/d3 factors reuse the "
            "already-approved ISO 68-1 constants from "
            "backend/engineering_core/geometry.py (duplicated, not "
            "imported, to keep this package independent)"
        ),
        classification="QUICK",
        validation_status=PROVISIONAL,
    ),
    FormulaId.VDI2230_PRELOAD: FormulaTrace(
        formula_id=FormulaId.VDI2230_PRELOAD,
        symbol="F_M",
        unit="N",
        source=(
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §4 vicinity "
            "(quick yield-utilization target); same model as "
            "backend/engineering_core/preload.py:preload_from_yield_n"
        ),
        classification="QUICK",
        validation_status=PROVISIONAL,
    ),
    FormulaId.VDI2230_CB: FormulaTrace(
        formula_id=FormulaId.VDI2230_CB,
        symbol="c_b",
        unit="N/mm",
        source=(
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §7 "
            "(generic series-compliance sum only; bolt substitution-"
            "length region geometry is NOT implemented)"
        ),
        classification="CORE_ARCHITECTURE",
        validation_status=PROVISIONAL,
    ),
    FormulaId.VDI2230_CC: FormulaTrace(
        formula_id=FormulaId.VDI2230_CC,
        symbol="c_c",
        unit="N/mm",
        source=(
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §8 "
            "(generic series-compliance sum only; pressure-cone "
            "effective-area method is NOT implemented)"
        ),
        classification="CORE_ARCHITECTURE",
        validation_status=PROVISIONAL,
    ),
    FormulaId.VDI2230_PHI: FormulaTrace(
        formula_id=FormulaId.VDI2230_PHI,
        symbol="Phi",
        unit="",
        source=(
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §3 "
            "(mandatory corrected model)"
        ),
        classification="MANDATORY_CORRECTED_MODEL",
        validation_status=PROVISIONAL,
    ),
    FormulaId.VDI2230_FS: FormulaTrace(
        formula_id=FormulaId.VDI2230_FS,
        symbol="F_S",
        unit="N",
        source=(
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §3 "
            "(mandatory corrected model)"
        ),
        classification="MANDATORY_CORRECTED_MODEL",
        validation_status=PROVISIONAL,
    ),
    FormulaId.VDI2230_RESULT: FormulaTrace(
        formula_id=FormulaId.VDI2230_RESULT,
        symbol="eta",
        unit="",
        source=(
            "docs/05_ENGINEERING_FORMULA_SPECIFICATION.md §9 "
            "(assembly/service stress ratio) + "
            "docs/08_RULE_ENGINE.md §4 (pass/warn/fail/not_evaluable "
            "result status model)"
        ),
        classification="QUICK",
        validation_status=PROVISIONAL,
    ),
}


def get_trace(formula_id: FormulaId) -> FormulaTrace:
    """Return the registered ``FormulaTrace`` for ``formula_id``.

    Raises ``MissingFormulaError`` if no trace is registered -- this
    is a defensive guard: every ``FormulaId`` member is populated
    above, so this should not trigger via normal enum usage.
    """
    try:
        return _CATALOG[formula_id]
    except KeyError as exc:
        raise MissingFormulaError(
            f"No trace registered for formula id: {formula_id!r}"
        ) from exc


def all_traces() -> Dict[FormulaId, FormulaTrace]:
    """Return a shallow copy of the full trace catalog."""
    return dict(_CATALOG)


__all__ = ["FormulaTrace", "get_trace", "all_traces", "PROVISIONAL"]
