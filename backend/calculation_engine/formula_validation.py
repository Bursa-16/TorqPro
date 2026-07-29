"""TorqPro Calculation Engine - Engineering Formula Validation (Faz 2.8.8).

Read-only aggregation and reporting over the two formula catalogs that
already exist in this repository:

- ``backend.vdi2230_core.trace`` (populated: 7 entries, kept
  independent by design -- see that module's own docstring).
- ``backend.calculation_engine.formula_registry`` (intentionally
  empty engine-level scaffold; registering concrete formulas into it
  is out of scope for this phase, per
  ``docs/adr/ADR-0012-material-intelligence-formula-validation.md``).

This module never writes to either catalog and never reclassifies a
formula's ``validation_status``. It only reads
``vdi2230_core.trace.all_traces()`` and
``formula_registry.all_formulas()`` (both pre-existing public
accessors) and produces a deterministic coverage/status report, in
TR/EN.

**Read-only boundary (mandatory, product-owner directive
2026-07-28):** this module calls no setter, no ``register_formula``,
no calculation function, and no mutation path on either catalog --
only the two ``all_*`` accessors above. It cannot alter or replace
any engineering formula or coefficient by construction. See
``test_faz_2_8_8_formula_validation.py::TestReadOnlyBoundary``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.calculation_engine import formula_registry
from backend.vdi2230_core import trace as vdi_trace

APPROVED = "APPROVED"
PROVISIONAL = "PROVISIONAL"


_MESSAGES: Dict[str, Dict[str, str]] = {
    "provisional_present": {
        "tr": (
            "Katalogda PROVISIONAL sınıflandırılmış formül(ler) var; bunlar üretim "
            "hesaplaması için onaylı değildir."
        ),
        "en": (
            "The catalog contains PROVISIONAL-classified formula(s); these are not "
            "approved for production calculation."
        ),
    },
    "no_registry_entries": {
        "tr": (
            "Motor seviyesi formül kaydı (formula_registry) boş; bu, iş bu fazda "
            "beklenen bir durumdur ve yeni bir hata değildir."
        ),
        "en": (
            "The engine-level formula registry (formula_registry) is empty; this is "
            "expected in this phase, not a defect."
        ),
    },
    "all_approved": {
        "tr": "Bu kataloğun tüm formülleri APPROVED durumundadır.",
        "en": "Every formula in this catalog is APPROVED.",
    },
}


def _msg(code: str, lang: str) -> str:
    entry = _MESSAGES[code]
    return entry.get(lang, entry["tr"])


def _normalize_lang(lang: Optional[str]) -> str:
    return "en" if (lang or "tr").strip().lower().startswith("en") else "tr"


@dataclass(frozen=True)
class FormulaValidationEntry:
    formula_id: str
    symbol: str
    unit: str
    source: str
    classification: str
    validation_status: str
    catalog: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "formula_id": self.formula_id,
            "symbol": self.symbol,
            "unit": self.unit,
            "source": self.source,
            "classification": self.classification,
            "validation_status": self.validation_status,
            "catalog": self.catalog,
        }


@dataclass(frozen=True)
class FormulaValidationReport:
    entries: List[FormulaValidationEntry]
    total_count: int
    approved_count: int
    provisional_count: int
    other_status_count: int
    catalogs_scanned: List[str]
    notices: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "total_count": self.total_count,
            "approved_count": self.approved_count,
            "provisional_count": self.provisional_count,
            "other_status_count": self.other_status_count,
            "catalogs_scanned": list(self.catalogs_scanned),
            "notices": list(self.notices),
        }


def _vdi2230_entries() -> List[FormulaValidationEntry]:
    entries = []
    for formula_id, formula_trace in vdi_trace.all_traces().items():
        entries.append(
            FormulaValidationEntry(
                formula_id=str(getattr(formula_id, "value", formula_id)),
                symbol=formula_trace.symbol,
                unit=formula_trace.unit,
                source=formula_trace.source,
                classification=formula_trace.classification,
                validation_status=formula_trace.validation_status,
                catalog="vdi2230_core.trace",
            )
        )
    return entries


def _formula_registry_entries() -> List[FormulaValidationEntry]:
    entries = []
    for formula_id, registry_entry in formula_registry.all_formulas().items():
        entries.append(
            FormulaValidationEntry(
                formula_id=str(formula_id),
                symbol=registry_entry.symbol,
                unit=registry_entry.unit,
                source=registry_entry.source,
                classification=registry_entry.classification,
                validation_status=registry_entry.validation_status,
                catalog="calculation_engine.formula_registry",
            )
        )
    return entries


def build_formula_validation_report(lang: Optional[str] = None) -> FormulaValidationReport:
    """Aggregate every known formula catalog into one deterministic,
    read-only report. Raises nothing for an empty catalog -- an empty
    ``formula_registry`` is a documented, expected state, not an
    error.
    """
    lang = _normalize_lang(lang)
    vdi_entries = _vdi2230_entries()
    registry_entries = _formula_registry_entries()
    entries = vdi_entries + registry_entries

    approved = sum(1 for e in entries if e.validation_status == APPROVED)
    provisional = sum(1 for e in entries if e.validation_status == PROVISIONAL)
    other = len(entries) - approved - provisional

    notices: List[str] = []
    if provisional:
        notices.append(_msg("provisional_present", lang))
    if not registry_entries:
        notices.append(_msg("no_registry_entries", lang))
    if entries and provisional == 0 and other == 0:
        notices.append(_msg("all_approved", lang))

    catalogs = sorted({e.catalog for e in entries}) or [
        "vdi2230_core.trace",
        "calculation_engine.formula_registry",
    ]

    return FormulaValidationReport(
        entries=entries,
        total_count=len(entries),
        approved_count=approved,
        provisional_count=provisional,
        other_status_count=other,
        catalogs_scanned=catalogs,
        notices=notices,
    )


__all__ = [
    "APPROVED",
    "PROVISIONAL",
    "FormulaValidationEntry",
    "FormulaValidationReport",
    "build_formula_validation_report",
]
