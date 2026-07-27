"""TorqPro Calculation Engine - Fastener Assembly Intelligence (Faz 2.8.6).

Aggregates the already-existing, already-tested domain engines
(``backend.library.compatibility_engine``,
``backend.library.strength_compatibility``,
``backend.library.washer_resolution_validator``,
``backend.library.population`` thread/OEM lookups,
``backend.calculation_engine.friction_readiness``) into one
deterministic per-assembly assessment: a per-check compatibility
status, a set of engineering warnings/recommendations sourced only
from those engines, and an Assembly Intelligence Score.

Builds NO new engineering result and invents NO threshold, weight or
value. Every ``compatible``/``incompatible`` outcome traces back to a
field already present on a resolved bolt/nut master record or to a
call into one of the five engines above.

Investigation correction (2026-07-27, before first delivery): initial
scoping treated operating-temperature and coating as unconditionally
``blocked_authoritative_source`` on the assumption that
``coating_library.py``/``material_library.py`` (both Phase 1.3 shells,
``record_count=0``) were the only source for those attributes. Checked
against real records instead: every ``bolt_library``/``nut_library``
record already carries its own verified/estimated
``operating_temperature_min_c``/``max_c`` and ``coating_compatibility``
fields -- independent of the empty coating/material shells. Those two
checks are therefore genuinely assessable and are implemented against
the resolved bolt/nut record, not blocked.

``material`` remains blocked: every bolt/nut record's ``material``
field is a verbatim duplicate of its ``property_class`` (confirmed
across the full population), so it carries no independent
material-identity information; a real material check would need
``backend.library.material_library``, which has zero populated
records. Checks that require that still-missing data return
``STATUS_BLOCKED_AUTHORITATIVE_SOURCE`` rather than a guessed value.

Four-status contract (Faz 2.8.6 brief, İlhan sign-off 2026-07-27):

- ``compatible``: an engine positively confirmed the pairing/attribute.
- ``incompatible``: an engine positively rejected the pairing/attribute.
- ``insufficient_data``: the specific record(s) needed exist but lack
  the field(s) required to decide (e.g. an ``unknown`` strength-class
  designation, a friction condition below decomposition readiness).
- ``blocked_authoritative_source``: the entire domain has no
  populated, sourced library to check against at all (coating,
  material, operating temperature, defence recommendations, intended
  use -- none of these have ANY record in this repository).

Score formula (per brief): only checks that resolved to ``compatible``
or ``incompatible`` count toward the score. ``insufficient_data`` and
``blocked_authoritative_source`` checks are excluded from the
denominator entirely -- never treated as compatible, and never used to
depress the score merely because authoritative data is unavailable.

    score = compatible_assessed_checks / total_assessed_checks * 100

If ``total_assessed_checks == 0`` no numeric score is produced;
``overall_status`` is ``"not_assessable"`` instead.

Any ``incompatible`` finding is additionally surfaced in
``critical_incompatibilities`` -- this list is never emptied or hidden
by an aggregate score, however high.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.calculation_engine.exceptions import CalculationInputError
from backend.calculation_engine.friction_readiness import assess_friction_readiness
from backend.library import population
from backend.library.compatibility_engine import check_bolt_nut_compatibility
from backend.library.exceptions import OEMStandardNotFoundError
from backend.library.oem_library import resolve_oem_reference
from backend.library.strength_compatibility import (
    check_bolt_nut_strength_compatibility,
)

# ---------------------------------------------------------------------
# Status vocabulary (Faz 2.8.6 four-status contract -- exhaustive, do
# not add a fifth status without a corresponding brief amendment).
# ---------------------------------------------------------------------
STATUS_COMPATIBLE = "compatible"
STATUS_INCOMPATIBLE = "incompatible"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_BLOCKED_AUTHORITATIVE_SOURCE = "blocked_authoritative_source"

_ASSESSED_STATUSES = (STATUS_COMPATIBLE, STATUS_INCOMPATIBLE)
_ALL_STATUSES = (
    STATUS_COMPATIBLE,
    STATUS_INCOMPATIBLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_BLOCKED_AUTHORITATIVE_SOURCE,
)

# Domains with zero independent, populated/sourced records in this
# repository today. "intended_use" and "defence_recommendation" have
# no backing field or standard anywhere; "material" exists as a field
# but is a verbatim duplicate of property_class on every record (see
# module docstring) and backend.library.material_library (the module
# that would carry real, independent material data) is a Phase 1.3
# shell with record_count=0. Checks against these domains are
# structurally blocked, not just missing a field on one record -- see
# module docstring for the insufficient_data vs
# blocked_authoritative_source distinction. NOTE: operating_temperature
# and coating were removed from this list after verifying that
# bolt_library/nut_library records carry real per-record data for
# both -- see the two check functions below.
BLOCKED_DOMAINS = (
    "intended_use",
    "material",
    "defence_recommendation",
)


@dataclass(frozen=True)
class CheckResult:
    """One assembly-intelligence check outcome.

    ``status`` is always one of the four Faz 2.8.6 statuses. ``detail``
    is a short deterministic human-readable reason (never a numeric
    judgement). ``warnings``/``recommendations`` are passed through
    verbatim from the underlying engine that produced this result --
    never authored here.
    """

    check_id: str
    status: str
    detail: str
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "detail": self.detail,
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
        }


@dataclass(frozen=True)
class AssemblyIntelligenceResult:
    """Full Faz 2.8.6 assessment for one assembly input."""

    checks: List[CheckResult]
    overall_status: str  # "assessed" | "not_assessable"
    score: Optional[float]
    total_checks: int
    assessed_checks: int
    insufficient_data_checks: int
    blocked_authoritative_source_checks: int
    assessment_coverage_percent: float
    critical_incompatibilities: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "overall_status": self.overall_status,
            "score": self.score,
            "total_checks": self.total_checks,
            "assessed_checks": self.assessed_checks,
            "insufficient_data_checks": self.insufficient_data_checks,
            "blocked_authoritative_source_checks": (
                self.blocked_authoritative_source_checks
            ),
            "assessment_coverage_percent": self.assessment_coverage_percent,
            "critical_incompatibilities": list(self.critical_incompatibilities),
        }


# ---------------------------------------------------------------------
# Individual checks -- each wraps exactly one existing engine call, or
# reads a field already present on a resolved bolt/nut master record.
# ---------------------------------------------------------------------

def _resolve_bolt(
    bolt_designation: Optional[str], nominal_diameter_mm: Optional[float],
) -> Optional[Dict[str, Any]]:
    if not bolt_designation:
        return None
    bolts = population.find_bolt(diameter_mm=nominal_diameter_mm)
    return next(
        (b for b in bolts if b.get("designation") == bolt_designation), None,
    ) or next(
        (b for b in population.find_bolt() if b.get("designation") == bolt_designation),
        None,
    )


def _resolve_nut(
    nut_designation: Optional[str], nominal_diameter_mm: Optional[float],
) -> Optional[Dict[str, Any]]:
    if not nut_designation:
        return None
    nuts = population.find_nut(diameter_mm=nominal_diameter_mm)
    return next(
        (n for n in nuts if n.get("designation") == nut_designation), None,
    ) or next(
        (n for n in population.find_nut() if n.get("designation") == nut_designation),
        None,
    )


def _check_bolt_nut_dimensional(
    bolt: Optional[Dict[str, Any]],
    nut: Optional[Dict[str, Any]],
    bolt_designation: Optional[str],
    nut_designation: Optional[str],
) -> CheckResult:
    """Bolt-Nut uyumu: dimensional/thread/coating/lock-type pairing
    via ``backend.library.compatibility_engine`` (Faz 2.4.1B), the
    engine whose own docstring states it is "not implemented" as
    boolean-only and always returns structured warnings/errors."""
    check_id = "bolt_nut_dimensional"
    if not bolt_designation or not nut_designation:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            "Bolt and/or nut designation not supplied.",
        )
    if bolt is None or nut is None:
        missing = []
        if bolt is None:
            missing.append(f"bolt {bolt_designation!r}")
        if nut is None:
            missing.append(f"nut {nut_designation!r}")
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            f"No master record found for: {', '.join(missing)}.",
        )
    result = check_bolt_nut_compatibility(bolt, nut)
    status = STATUS_COMPATIBLE if result.compatible else STATUS_INCOMPATIBLE
    detail = (
        "Bolt/nut dimensional pairing is compatible."
        if result.compatible
        else "; ".join(result.errors) or "Bolt/nut dimensional pairing rejected."
    )
    return CheckResult(
        check_id, status, detail,
        warnings=result.warnings, recommendations=result.engineering_notes,
    )


def _check_strength_class(
    bolt_strength_class: Optional[str],
    nut_property_class: Optional[str],
    nominal_diameter_mm: Optional[float],
) -> CheckResult:
    """Strength class uyumu via ``backend.library.strength_compatibility``
    (Faz 2.8.3). The engine's own ``unknown`` status maps to
    ``insufficient_data`` here (unrecognised designation, not a
    rejected pairing); ``conditionally_compatible`` maps to
    ``incompatible`` since the brief requires only two assessed
    outcomes -- the conditional detail/warnings are preserved
    verbatim so nothing is lost."""
    check_id = "strength_class"
    if not bolt_strength_class or not nut_property_class:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            "Bolt strength class and/or nut property class not supplied.",
        )
    result = check_bolt_nut_strength_compatibility(
        bolt_strength_class, nut_property_class, nominal_diameter_mm,
    )
    if result.status == "unknown":
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            "; ".join(result.reasons) or "Unrecognised strength class designation.",
        )
    status = STATUS_COMPATIBLE if result.status == "compatible" else STATUS_INCOMPATIBLE
    detail = (
        "Strength class pairing is compatible."
        if status == STATUS_COMPATIBLE
        else ("; ".join(result.reasons) or "Strength class pairing not compatible.")
    )
    return CheckResult(check_id, status, detail, warnings=result.warnings)


def _check_thread(
    thread_designation: Optional[str], nominal_diameter_mm: Optional[float],
) -> CheckResult:
    """Thread uyumu via ``backend.library.population.find_thread``
    (thread geometry master library)."""
    check_id = "thread"
    if not thread_designation:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA, "Thread designation not supplied.",
        )
    matches = population.find_thread(designation=thread_designation)
    if not matches:
        return CheckResult(
            check_id, STATUS_INCOMPATIBLE,
            f"No thread geometry record for designation {thread_designation!r}.",
        )
    if nominal_diameter_mm is not None:
        diameter_matches = [
            m for m in matches
            if m.get("nominal_diameter_mm") == nominal_diameter_mm
        ]
        if not diameter_matches:
            return CheckResult(
                check_id, STATUS_INCOMPATIBLE,
                f"Thread {thread_designation!r} does not match nominal diameter "
                f"{nominal_diameter_mm:g} mm in the thread geometry library.",
            )
    return CheckResult(
        check_id, STATUS_COMPATIBLE,
        f"Thread designation {thread_designation!r} found in the thread geometry library.",
    )


def _check_bolt_washer(bolt_size: Optional[str]) -> CheckResult:
    """Bolt-Washer uyumu via ``backend.library.population.find_washer_for_bolt``."""
    check_id = "bolt_washer"
    if not bolt_size:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA, "Bolt size not supplied.",
        )
    matches = population.find_washer_for_bolt(bolt_size)
    if not matches:
        return CheckResult(
            check_id, STATUS_INCOMPATIBLE,
            f"No washer record lists {bolt_size!r} in compatible_bolt_sizes.",
        )
    return CheckResult(
        check_id, STATUS_COMPATIBLE,
        f"{len(matches)} washer record(s) compatible with bolt size {bolt_size!r}.",
    )


def _check_washer_diameter(
    bolt_size: Optional[str], washer_standard: Optional[str],
) -> CheckResult:
    """Washer çap uyumu: cross the bolt-compatible washer set against
    a specific washer standard, when one was supplied."""
    check_id = "washer_diameter"
    if not bolt_size or not washer_standard:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            "Bolt size and/or washer standard not supplied.",
        )
    bolt_matches = population.find_washer_for_bolt(bolt_size)
    if not bolt_matches:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            f"No washer record for bolt size {bolt_size!r} to cross-check diameter against.",
        )
    standard_matches = [
        m for m in bolt_matches
        if (m.get("standard") or "").strip().upper() == washer_standard.strip().upper()
    ]
    if not standard_matches:
        return CheckResult(
            check_id, STATUS_INCOMPATIBLE,
            f"No {washer_standard!r} washer record compatible with bolt size {bolt_size!r}.",
        )
    return CheckResult(
        check_id, STATUS_COMPATIBLE,
        f"{washer_standard!r} washer diameter range matches bolt size {bolt_size!r}.",
    )


def _check_friction_condition(friction_condition_id: Optional[str]) -> CheckResult:
    """Friction condition uygunluğu via
    ``backend.calculation_engine.friction_readiness`` (Faz 2.6.3)."""
    check_id = "friction_condition"
    if not friction_condition_id:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA, "Friction condition id not supplied.",
        )
    try:
        readiness = assess_friction_readiness(friction_condition_id)
    except CalculationInputError as exc:
        return CheckResult(check_id, STATUS_INCOMPATIBLE, str(exc))
    if readiness.decomposition_available or readiness.combined_friction_scenarios:
        return CheckResult(
            check_id, STATUS_COMPATIBLE,
            f"Friction condition {friction_condition_id!r} has usable data "
            f"(mode={readiness.calculation_mode}).",
            warnings=readiness.engineering_warnings,
        )
    return CheckResult(
        check_id, STATUS_INSUFFICIENT_DATA,
        "; ".join(readiness.blocking_reasons)
        or f"Friction condition {friction_condition_id!r} lacks decomposition-ready data.",
        warnings=readiness.engineering_warnings,
    )


def _check_standard(standard_name: Optional[str]) -> CheckResult:
    """Standard uyumu via ``backend.standards.registry``."""
    from backend.standards.registry import get_standard  # local: avoid import cycle at module load

    check_id = "standard"
    if not standard_name:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA, "Standard reference not supplied.",
        )
    try:
        std = get_standard(standard_name)
    except KeyError:
        return CheckResult(
            check_id, STATUS_INCOMPATIBLE,
            f"{standard_name!r} is not a registered standard in backend.standards.",
        )
    return CheckResult(
        check_id, STATUS_COMPATIBLE, f"{std.name!r} is a registered standard.",
    )


def _check_oem_or_automotive(
    check_id: str, oem_reference: Optional[str],
) -> CheckResult:
    """Shared implementation for the OEM (12) and Automotive (14)
    checks -- both resolve through the same
    ``backend.library.oem_library`` adapter over ``backend.standards``;
    Faz 2.8.6 does not have a separate automotive-only data source, so
    both checks are identical in mechanism and differ only in the
    reference the caller supplies."""
    if not oem_reference:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA, "OEM/automotive reference not supplied.",
        )
    try:
        std = resolve_oem_reference(oem_reference)
    except OEMStandardNotFoundError:
        return CheckResult(
            check_id, STATUS_INCOMPATIBLE,
            f"{oem_reference!r} is not a registered OEM/automotive standard.",
        )
    return CheckResult(
        check_id, STATUS_COMPATIBLE, f"{std.name!r} resolved via the OEM standards adapter.",
    )


def _check_operating_temperature(
    bolt: Optional[Dict[str, Any]],
    nut: Optional[Dict[str, Any]],
    intended_operating_temperature_c: Optional[float],
) -> CheckResult:
    """Operating temperature: cross the intended service temperature
    against ``operating_temperature_min_c``/``max_c`` already present
    on the resolved bolt and nut master records (verified/estimated
    per record, per that record's own ``metadata.verified_fields`` --
    this check reads the value, it does not re-judge its confidence
    level)."""
    check_id = "operating_temperature"
    if intended_operating_temperature_c is None or bolt is None or nut is None:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            "Intended operating temperature and/or resolved bolt/nut record not supplied.",
        )
    out_of_range = []
    for label, record in (("bolt", bolt), ("nut", nut)):
        lo = record.get("operating_temperature_min_c")
        hi = record.get("operating_temperature_max_c")
        if lo is None or hi is None:
            continue
        if not (lo <= intended_operating_temperature_c <= hi):
            out_of_range.append(
                f"{label} {record.get('designation')!r} rated {lo:g}..{hi:g} C"
            )
    if not any(
        record.get("operating_temperature_min_c") is not None
        for record in (bolt, nut)
    ):
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            "Resolved bolt/nut record(s) have no operating_temperature_min_c/max_c field.",
        )
    if out_of_range:
        return CheckResult(
            check_id, STATUS_INCOMPATIBLE,
            f"Intended operating temperature {intended_operating_temperature_c:g} C exceeds: "
            + "; ".join(out_of_range) + ".",
        )
    return CheckResult(
        check_id, STATUS_COMPATIBLE,
        f"Intended operating temperature {intended_operating_temperature_c:g} C is within "
        "the bolt and nut records' rated range.",
    )


def _check_coating(
    bolt: Optional[Dict[str, Any]],
    nut: Optional[Dict[str, Any]],
    intended_coating: Optional[str],
) -> CheckResult:
    """Coating uyumu: cross the intended coating against
    ``coating_compatibility`` already present on the resolved bolt and
    nut master records."""
    check_id = "coating"
    if not intended_coating or bolt is None or nut is None:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            "Intended coating and/or resolved bolt/nut record not supplied.",
        )
    needle = intended_coating.strip().lower()
    bolt_list = bolt.get("coating_compatibility") or []
    nut_list = nut.get("coating_compatibility") or []
    if not bolt_list and not nut_list:
        return CheckResult(
            check_id, STATUS_INSUFFICIENT_DATA,
            "Resolved bolt/nut record(s) have no coating_compatibility field.",
        )
    bolt_ok = any(c.lower() == needle for c in bolt_list) if bolt_list else None
    nut_ok = any(c.lower() == needle for c in nut_list) if nut_list else None
    if bolt_ok is False or nut_ok is False:
        return CheckResult(
            check_id, STATUS_INCOMPATIBLE,
            f"Coating {intended_coating!r} not listed in coating_compatibility for "
            f"bolt {bolt.get('designation')!r} and/or nut {nut.get('designation')!r} "
            f"(bolt options: {bolt_list}; nut options: {nut_list}).",
        )
    return CheckResult(
        check_id, STATUS_COMPATIBLE,
        f"Coating {intended_coating!r} is listed as compatible for the "
        "resolved bolt/nut record(s).",
    )


def _check_blocked_domain(check_id: str) -> CheckResult:
    """Checks 7, 10, 13 (Intended Use, Material, Defence): no
    independent backing library/field exists in this repository (see
    module docstring), so no compatible/incompatible judgement can be
    made without inventing data. Always returns
    ``STATUS_BLOCKED_AUTHORITATIVE_SOURCE`` -- this is a structural,
    repo-wide condition, not something that varies per assembly
    input."""
    return CheckResult(
        check_id, STATUS_BLOCKED_AUTHORITATIVE_SOURCE,
        "No populated, sourced library exists for this domain in the current repository "
        "(Phase 1.3 shell: record_count=0, status=\"draft\").",
    )


# ---------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------

def assess_assembly(
    *,
    bolt_designation: Optional[str] = None,
    nut_designation: Optional[str] = None,
    bolt_strength_class: Optional[str] = None,
    nut_property_class: Optional[str] = None,
    nominal_diameter_mm: Optional[float] = None,
    thread_designation: Optional[str] = None,
    bolt_size: Optional[str] = None,
    washer_standard: Optional[str] = None,
    friction_condition_id: Optional[str] = None,
    standard_name: Optional[str] = None,
    oem_reference: Optional[str] = None,
    automotive_reference: Optional[str] = None,
    intended_operating_temperature_c: Optional[float] = None,
    intended_coating: Optional[str] = None,
) -> AssemblyIntelligenceResult:
    """Run every Faz 2.8.6 check for one assembly input and compute the
    Assembly Intelligence Score per the brief's formula.

    All parameters are optional: a missing input makes the
    corresponding check(s) ``insufficient_data`` rather than raising --
    consistent with every other engine in this package
    (``check_bolt_nut_strength_compatibility``,
    ``assess_friction_readiness``, etc.), which report "not enough
    data" as a normal outcome, never an exception.
    """
    bolt = _resolve_bolt(bolt_designation, nominal_diameter_mm)
    nut = _resolve_nut(nut_designation, nominal_diameter_mm)

    checks: List[CheckResult] = [
        _check_bolt_nut_dimensional(bolt, nut, bolt_designation, nut_designation),
        _check_bolt_washer(bolt_size),
        _check_washer_diameter(bolt_size, washer_standard),
        _check_thread(thread_designation, nominal_diameter_mm),
        _check_strength_class(bolt_strength_class, nut_property_class, nominal_diameter_mm),
        _check_friction_condition(friction_condition_id),
        _check_blocked_domain("intended_use"),
        _check_operating_temperature(bolt, nut, intended_operating_temperature_c),
        _check_coating(bolt, nut, intended_coating),
        _check_blocked_domain("material"),
        _check_standard(standard_name),
        _check_oem_or_automotive("oem_recommendation", oem_reference),
        _check_blocked_domain("defence_recommendation"),
        _check_oem_or_automotive("automotive_recommendation", automotive_reference),
    ]

    assessed = [c for c in checks if c.status in _ASSESSED_STATUSES]
    compatible = [c for c in assessed if c.status == STATUS_COMPATIBLE]
    insufficient = [c for c in checks if c.status == STATUS_INSUFFICIENT_DATA]
    blocked = [c for c in checks if c.status == STATUS_BLOCKED_AUTHORITATIVE_SOURCE]
    critical = [
        f"{c.check_id}: {c.detail}" for c in checks if c.status == STATUS_INCOMPATIBLE
    ]

    total_checks = len(checks)
    assessed_checks = len(assessed)
    coverage = (assessed_checks / total_checks * 100.0) if total_checks else 0.0

    if assessed_checks == 0:
        overall_status = "not_assessable"
        score: Optional[float] = None
    else:
        overall_status = "assessed"
        score = round(len(compatible) / assessed_checks * 100.0, 2)

    return AssemblyIntelligenceResult(
        checks=checks,
        overall_status=overall_status,
        score=score,
        total_checks=total_checks,
        assessed_checks=assessed_checks,
        insufficient_data_checks=len(insufficient),
        blocked_authoritative_source_checks=len(blocked),
        assessment_coverage_percent=round(coverage, 2),
        critical_incompatibilities=critical,
    )


__all__ = [
    "STATUS_COMPATIBLE",
    "STATUS_INCOMPATIBLE",
    "STATUS_INSUFFICIENT_DATA",
    "STATUS_BLOCKED_AUTHORITATIVE_SOURCE",
    "BLOCKED_DOMAINS",
    "CheckResult",
    "AssemblyIntelligenceResult",
    "assess_assembly",
]
