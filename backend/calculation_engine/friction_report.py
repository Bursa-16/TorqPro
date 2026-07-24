"""TorqPro Calculation Engine - Friction Condition Reporting (Faz 2.6.5).

Formats the already-computed Faz 2.6.3/2.6.4 domain results
(``assess_friction_readiness``, ``assess_recommendation_readiness``,
``generate_friction_warnings``, ``compare_friction_conditions``) into
a structured, additive, testable report section. Builds NO new
engineering result: every value here traces back to one of those four
functions or to fields already stored on the resolved
``FrictionConditionRecord``.

Investigation finding (see
docs/phases/PHASE_2.6.5_FRICTION_REPORTING_INTEGRATION.md §1): this
codebase has no PDF/HTML report generator today (``docs/310_Reporting.md``
is a one-line placeholder; ``backend.production_validation.service``
handles study/dataset records, not report rendering). The only
existing report-adjacent surface is the ``/api/engineering/check``
JSON response and the audit log (``backend.app.audit``). There is
therefore no existing report request/response model to extend
without inventing one -- this module deliberately produces a
self-contained, additive JSON *report section* (Option B: a
dedicated preview endpoint), not a change to any current report
model, since none renders to PDF/HTML yet. A PDF/HTML renderer can
consume this section's ``to_dict()`` output unchanged whenever one is
built.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .friction_readiness import _resolve_raw_record
from .friction_recommendations import (
    INTENDED_USE_MINIMUM_LEVEL,
    compare_friction_conditions,
)
from .friction_recommendations import assess_recommendation_readiness as _assess_recommendation
from .friction_readiness import assess_friction_readiness as _assess_torque_readiness
from .exceptions import CalculationInputError

# -- Deterministic safety labels (verbatim per directive) --------------
LABEL_REFERENCE_ONLY = "Reference Only"
LABEL_NOT_CERTIFIED = "Not a Certified ISO 16047 Test Result"
LABEL_DECOMPOSITION_UNAVAILABLE = "Torque Decomposition Unavailable"
LABEL_NO_TIGHTENING_RECOMMENDATION = "No Tightening Recommendation Generated"
LABEL_PRODUCTION_APPROVAL_NOT_AVAILABLE = "Production Approval Not Available"

_PRODUCTION_READY_LEVEL = "production_recommendation_ready"


def _friction_condition_library_data_version() -> str:
    """Reuse the existing library metadata version from the data
    file itself (kept current by the Faz 2.6.2B generator script) --
    no parallel versioning mechanism introduced. Deliberately reads
    the JSON payload directly rather than the in-memory registry
    object's ``LibraryMetadata.version``, which is set once at module
    import time and is not re-synced when the data file is
    regenerated."""
    from backend.library import loader as loader_module
    from backend.library.population import _data_path, POPULATION_SOURCES

    payload = loader_module.read_source_payload(
        _data_path(POPULATION_SOURCES["friction condition library"])
    )
    return payload.get("metadata", {}).get("version", "")


@dataclass(frozen=True)
class FrictionConditionSourceSummary:
    source_reference: str
    source_type: str
    source_page_or_table: str
    verification_status: str
    applicability: str
    engineering_notes: str
    record_checksum: str
    data_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_reference": self.source_reference,
            "source_type": self.source_type,
            "source_page_or_table": self.source_page_or_table,
            "verification_status": self.verification_status,
            "applicability": self.applicability,
            "engineering_notes": self.engineering_notes,
            "record_checksum": self.record_checksum,
            "data_version": self.data_version,
        }


@dataclass(frozen=True)
class FrictionConditionReadinessSummary:
    recommendation_level: str
    available_capabilities: List[str]
    blocked_capabilities: List[str]
    blocking_reasons: List[str]
    required_missing_data: List[str]
    torque_calculation_mode: str
    torque_blocking_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_level": self.recommendation_level,
            "available_capabilities": list(self.available_capabilities),
            "blocked_capabilities": list(self.blocked_capabilities),
            "blocking_reasons": list(self.blocking_reasons),
            "required_missing_data": list(self.required_missing_data),
            "torque_calculation_mode": self.torque_calculation_mode,
            "torque_blocking_reasons": list(self.torque_blocking_reasons),
        }


@dataclass(frozen=True)
class FrictionConditionComparisonSummary:
    friction_condition_id_a: str
    friction_condition_id_b: str
    is_self_comparison: bool
    range_relation: str
    width_relation: str
    source_classification_a: str
    source_classification_b: str
    verification_status_a: str
    verification_status_b: str
    source_status_relation: str
    descriptive_statements: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "friction_condition_id_a": self.friction_condition_id_a,
            "friction_condition_id_b": self.friction_condition_id_b,
            "is_self_comparison": self.is_self_comparison,
            "range_relation": self.range_relation,
            "width_relation": self.width_relation,
            "source_classification_a": self.source_classification_a,
            "source_classification_b": self.source_classification_b,
            "verification_status_a": self.verification_status_a,
            "verification_status_b": self.verification_status_b,
            "source_status_relation": self.source_status_relation,
            "descriptive_statements": list(self.descriptive_statements),
        }


@dataclass(frozen=True)
class FrictionConditionReportSection:
    """The full, additive "Friction Condition Assessment" report
    section. Every field traces to a resolved record or to the
    Faz 2.6.3/2.6.4 domain functions -- nothing computed here."""

    friction_condition_id: str
    coating_reference: str
    lubricant_reference: str
    friction_model: str
    overall_friction_coefficient_minimum: Optional[float]
    overall_friction_coefficient_nominal_estimate: Optional[float]
    overall_friction_coefficient_maximum: Optional[float]
    nominal_policy: str
    source: FrictionConditionSourceSummary
    readiness: FrictionConditionReadinessSummary
    engineering_warnings: List[str]
    safety_labels: List[str]
    intended_use: Optional[str]
    comparison: Optional[FrictionConditionComparisonSummary]
    report_generated_at: str
    application_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "friction_condition_id": self.friction_condition_id,
            "coating_reference": self.coating_reference,
            "lubricant_reference": self.lubricant_reference,
            "friction_model": self.friction_model,
            "overall_friction_coefficient_minimum": self.overall_friction_coefficient_minimum,
            "overall_friction_coefficient_nominal_estimate":
                self.overall_friction_coefficient_nominal_estimate,
            "overall_friction_coefficient_maximum": self.overall_friction_coefficient_maximum,
            "nominal_policy": self.nominal_policy,
            "source": self.source.to_dict(),
            "readiness": self.readiness.to_dict(),
            "engineering_warnings": list(self.engineering_warnings),
            "safety_labels": list(self.safety_labels),
            "intended_use": self.intended_use,
            "comparison": self.comparison.to_dict() if self.comparison else None,
            "report_generated_at": self.report_generated_at,
            "application_version": self.application_version,
        }


def _validate_intended_use(intended_use: Optional[str]) -> None:
    if intended_use is not None and intended_use not in INTENDED_USE_MINIMUM_LEVEL:
        allowed = ", ".join(sorted(INTENDED_USE_MINIMUM_LEVEL))
        raise CalculationInputError(
            f"invalid_intended_use: {intended_use!r} is not one of: {allowed}"
        )


def _safety_labels(
    verification_status: str, decomposition_available: bool,
    torque_blocked: bool, recommendation_level: str,
) -> List[str]:
    labels: List[str] = []
    if verification_status == "reference_only":
        labels.append(LABEL_REFERENCE_ONLY)
    if verification_status != "verified" and verification_status != "approved":
        labels.append(LABEL_NOT_CERTIFIED)
    if not decomposition_available:
        labels.append(LABEL_DECOMPOSITION_UNAVAILABLE)
    if torque_blocked:
        labels.append(LABEL_NO_TIGHTENING_RECOMMENDATION)
    if recommendation_level != _PRODUCTION_READY_LEVEL:
        labels.append(LABEL_PRODUCTION_APPROVAL_NOT_AVAILABLE)
    return labels


def build_friction_condition_report_section(
    friction_condition_id: str,
    *,
    compare_with_id: Optional[str] = None,
    intended_use: Optional[str] = None,
) -> FrictionConditionReportSection:
    """Build the additive "Friction Condition Assessment" report
    section for ``friction_condition_id``.

    Raises ``CalculationInputError`` (controlled, deterministic) for:
    unknown friction_condition_id / compare_with_id, broken coating or
    lubricant reference, missing source traceability, invalid
    intended_use. Same-id comparison is not an error -- it is
    explicitly flagged via ``comparison.is_self_comparison``.
    """
    _validate_intended_use(intended_use)

    raw = _resolve_raw_record(friction_condition_id)  # raises on unknown id
    readiness = _assess_recommendation(friction_condition_id, intended_use=intended_use)
    torque_readiness = _assess_torque_readiness(friction_condition_id)

    source = FrictionConditionSourceSummary(
        source_reference=raw.get("source_reference", ""),
        source_type=raw.get("source_type", ""),
        source_page_or_table=raw.get("source_page_or_table", ""),
        verification_status=raw.get("verification_status", ""),
        applicability=raw.get("applicability", ""),
        engineering_notes=raw.get("engineering_notes", ""),
        record_checksum=raw.get("checksum", ""),
        data_version=_friction_condition_library_data_version(),
    )

    readiness_summary = FrictionConditionReadinessSummary(
        recommendation_level=readiness.recommendation_level,
        available_capabilities=readiness.available_capabilities,
        blocked_capabilities=readiness.blocked_capabilities,
        blocking_reasons=readiness.blocking_reasons,
        required_missing_data=readiness.required_missing_data,
        torque_calculation_mode=torque_readiness.calculation_mode,
        torque_blocking_reasons=torque_readiness.blocking_reasons,
    )

    torque_blocked = bool(torque_readiness.blocking_reasons)
    safety_labels = _safety_labels(
        verification_status=raw.get("verification_status", ""),
        decomposition_available=torque_readiness.decomposition_available,
        torque_blocked=torque_blocked,
        recommendation_level=readiness.recommendation_level,
    )

    comparison_summary: Optional[FrictionConditionComparisonSummary] = None
    if compare_with_id is not None:
        is_self = compare_with_id == friction_condition_id
        comparison = compare_friction_conditions(friction_condition_id, compare_with_id)
        comparison_summary = FrictionConditionComparisonSummary(
            friction_condition_id_a=comparison.friction_condition_id_a,
            friction_condition_id_b=comparison.friction_condition_id_b,
            is_self_comparison=is_self,
            range_relation=comparison.range_relation,
            width_relation=comparison.width_relation,
            source_classification_a=comparison.source_classification_a,
            source_classification_b=comparison.source_classification_b,
            verification_status_a=comparison.verification_status_a,
            verification_status_b=comparison.verification_status_b,
            source_status_relation=comparison.source_status_relation,
            descriptive_statements=comparison.descriptive_statements,
        )

    return FrictionConditionReportSection(
        friction_condition_id=friction_condition_id,
        coating_reference=raw.get("coating_id", "") or "",
        lubricant_reference=raw.get("lubricant_id", "") or "",
        friction_model=raw.get("friction_model", "") or "",
        overall_friction_coefficient_minimum=raw.get("overall_friction_coefficient_min"),
        overall_friction_coefficient_nominal_estimate=(
            torque_readiness.combined_friction_scenarios["nominal_estimate"]
            if torque_readiness.combined_friction_scenarios else None
        ),
        overall_friction_coefficient_maximum=raw.get("overall_friction_coefficient_max"),
        nominal_policy=(
            torque_readiness.combined_friction_scenarios["nominal_estimate_policy"]
            if torque_readiness.combined_friction_scenarios
            else "arithmetic midpoint of reference range"
        ),
        source=source,
        readiness=readiness_summary,
        engineering_warnings=readiness.engineering_warnings,
        safety_labels=safety_labels,
        intended_use=intended_use,
        comparison=comparison_summary,
        report_generated_at=datetime.now(timezone.utc).isoformat(),
        application_version=_app_version(),
    )


def _app_version() -> str:
    """Reuse the existing application version constant (no parallel
    versioning mechanism introduced)."""
    try:
        from backend.app import APP_VERSION
    except ImportError:  # pragma: no cover - direct import with backend/ on sys.path
        from app import APP_VERSION  # type: ignore[no-redef]
    return APP_VERSION


__all__ = [
    "LABEL_REFERENCE_ONLY",
    "LABEL_NOT_CERTIFIED",
    "LABEL_DECOMPOSITION_UNAVAILABLE",
    "LABEL_NO_TIGHTENING_RECOMMENDATION",
    "LABEL_PRODUCTION_APPROVAL_NOT_AVAILABLE",
    "FrictionConditionSourceSummary",
    "FrictionConditionReadinessSummary",
    "FrictionConditionComparisonSummary",
    "FrictionConditionReportSection",
    "build_friction_condition_report_section",
]
