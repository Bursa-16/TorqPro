"""TorqPro Calculation Engine - Engineering Formula Validation (Faz 2.8.8).

Read-only aggregation and reporting over the two formula catalogs that
already exist in this repository:

- ``backend.vdi2230_core.trace`` (populated: 7 entries, kept
  independent by design -- see that module's own docstring).
- ``backend.calculation_engine.formula_registry`` (intentionally
  empty engine-level scaffold; registering concrete formulas into it
  is out of scope for this phase, per
  ``docs/adr/ADR-0012-material-intelligence-formula-validation.md``).

Phase 2.8.21 adds a third source, read the same way: read-only,
additive, no reclassification -- ``backend.engineering_core.trace.
all_traces()``. Its entries carry a richer metadata shape than the
5-field ``FormulaValidationEntry`` below (see
``backend.engineering_core.trace.EngineeringCoreFormulaTrace``); the
extra fields are exposed as additional, backward-compatible keys on
``FormulaValidationEntry.to_dict()`` (``None``/empty for the two
pre-existing catalogs, populated for engineering_core) rather than by
widening the two pre-existing catalogs' own trace shapes.

This module never writes to either catalog and never reclassifies a
formula's ``validation_status``. It only reads
``vdi2230_core.trace.all_traces()``,
``formula_registry.all_formulas()`` and (Phase 2.8.21)
``engineering_core.trace.all_traces()`` (all pre-existing public
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
from backend.engineering_core import trace as engcore_trace
from backend.vdi2230_core import trace as vdi_trace

# Single source of truth for these two values remains
# backend.vdi2230_core.trace (imported, not redefined) -- Phase 2.8.21
# extends the *set* of statuses this report can display, not the
# meaning of the two shared ones.
APPROVED = vdi_trace.APPROVED
PROVISIONAL = vdi_trace.PROVISIONAL


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
    # Phase 2.8.21, additive: richer governance metadata. ``None``/empty
    # for entries from the two pre-existing catalogs (vdi2230_core.trace,
    # formula_registry) -- their own trace shapes are untouched by this
    # phase; populated for engineering_core.trace entries. Existing
    # consumers reading only the seven fields above are unaffected.
    source_level: Optional[str] = None
    confidence: Optional[str] = None
    limitations: Optional[List[str]] = None
    prohibited_claims: Optional[List[str]] = None
    intended_use: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "formula_id": self.formula_id,
            "symbol": self.symbol,
            "unit": self.unit,
            "source": self.source,
            "classification": self.classification,
            "validation_status": self.validation_status,
            "catalog": self.catalog,
            "source_level": self.source_level,
            "confidence": self.confidence,
            "limitations": list(self.limitations) if self.limitations else [],
            "prohibited_claims": list(self.prohibited_claims) if self.prohibited_claims else [],
            "intended_use": self.intended_use,
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


def _engineering_core_entries() -> List[FormulaValidationEntry]:
    """Phase 2.8.21: read-only projection of
    ``backend.engineering_core.trace.all_traces()`` into the same
    ``FormulaValidationEntry`` shape used by the other two catalogs,
    with the additional metadata fields populated. Never reclassifies
    a status -- every ``validation_status`` here is exactly the
    ``status`` already recorded in ``engineering_core.trace``.
    """
    entries = []
    for formula_id, formula_trace in engcore_trace.all_traces().items():
        entries.append(
            FormulaValidationEntry(
                formula_id=str(getattr(formula_id, "value", formula_id)),
                symbol=formula_trace.name,
                unit="",
                source=formula_trace.source_reference,
                classification=formula_trace.domain,
                validation_status=formula_trace.status,
                catalog="engineering_core.trace",
                source_level=formula_trace.source_level,
                confidence=formula_trace.confidence,
                limitations=list(formula_trace.limitations),
                prohibited_claims=list(formula_trace.prohibited_claims),
                intended_use=formula_trace.intended_use,
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
    engcore_entries = _engineering_core_entries()
    entries = vdi_entries + registry_entries + engcore_entries

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
