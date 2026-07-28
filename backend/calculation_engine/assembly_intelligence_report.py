"""TorqPro Calculation Engine - Assembly Intelligence Report Section
(Faz 2.8.6, Stage 2).

Formats the already-computed Stage 1 result
(``backend.calculation_engine.assembly_intelligence.assess_assembly``)
into a structured, additive, testable report section. Follows the
collector/renderer separation already established by
``backend/calculation_engine/strength_class_report.py``,
``backend/calculation_engine/friction_report.py`` (Faz 2.6.5/2.8.3)
and ``backend/library/washer_report.py`` (Faz 2.8.5):
``collect_assembly_intelligence_report`` calls the Stage 1 engine
exactly once and returns a frozen, JSON-safe dict; the two
``render_*`` functions only format an already-collected report --
neither re-derives a score, re-classifies a check, nor mutates any
library data.

Builds NO new engineering result, changes NO Stage 1 scoring rule and
NO Stage 1 status mapping (per the Stage 2 brief). Every score,
coverage percentage, check status and count in this report is read
directly off the ``AssemblyIntelligenceResult`` Stage 1 already
computed -- this module only adds presentation-layer metadata:

- ``severity``: a fixed, deterministic function of a check's Stage 1
  ``status`` (see ``_SEVERITY_BY_STATUS`` below) -- not a new
  judgement about the check's engineering meaning.
- ``check_name`` / ``data_source``: a static, factual description of
  which check this is and which existing engine/library backs it
  (see ``_CHECK_METADATA`` below) -- documents what Stage 1 already
  does, invents nothing.
- ``suggested_action``: a fixed, generic, per-status procedural
  string (e.g. "provide the missing input", "no populated source
  exists for this domain yet") plus, verbatim, any
  ``recommendations`` the underlying Stage 1 engine itself already
  produced (e.g. ``compatibility_engine``'s ``engineering_notes``).
  Never a fabricated engineering recommendation (no invented coating/
  material/torque suggestion) -- see the Faz 2.8.6 brief's explicit
  prohibition on inventing recommendations.

Deliberately **not** timestamped (like ``washer_report.py``, unlike
the two older calculation-engine reports above which stamp
``generated_at`` with ``datetime.now()``): this report must be
byte-for-byte reproducible across repeated calls against the same
input, per the Stage 2 brief's determinism/testability requirement. A
caller that needs a timestamp can attach one outside this module.

Overall risk level: Stage 1 deliberately does not define a numeric
score-band system (no "Excellent/Good/Warning/High Risk/Unsafe"
thresholds were agreed -- İlhan's Stage-1 sign-off rejected inventing
score weights/thresholds). This module therefore does NOT invent a
new banded risk scale either. ``overall_risk_level`` is a minimal,
three-value classification computed directly from fields Stage 1
already exposes, with no new numeric threshold:

- ``"critical"`` if ``critical_incompatibilities`` is non-empty.
- ``"not_assessable"`` if ``overall_status == "not_assessable"``.
- ``"no_critical_incompatibility_detected"`` otherwise -- explicitly
  not phrased as "safe"/"low risk": coverage, insufficient_data and
  blocked_authoritative_source counts remain visible separately (per
  the brief's requirement that coverage never be conflated with
  score) precisely because a high score with low coverage is not the
  same as a fully-assessed low-risk assembly.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .assembly_intelligence import (
    STATUS_BLOCKED_AUTHORITATIVE_SOURCE,
    STATUS_COMPATIBLE,
    STATUS_INCOMPATIBLE,
    STATUS_INSUFFICIENT_DATA,
    AssemblyIntelligenceResult,
    CheckResult,
    assess_assembly,
)

# ---------------------------------------------------------------------
# Presentation-layer constants (report metadata only -- see module
# docstring; none of this changes a Stage 1 status or score).
# ---------------------------------------------------------------------

_SEVERITY_BY_STATUS: Dict[str, str] = {
    STATUS_COMPATIBLE: "none",
    STATUS_INCOMPATIBLE: "critical",
    STATUS_INSUFFICIENT_DATA: "info",
    STATUS_BLOCKED_AUTHORITATIVE_SOURCE: "warning",
}

#: (display name (TR), data source description) per Stage 1 check_id.
#: Factual description of the existing engine/library each check
#: already wraps -- see assembly_intelligence.py docstrings for the
#: authoritative source of these mappings.
_CHECK_METADATA: Dict[str, "tuple[str, str]"] = {
    "bolt_nut_dimensional": (
        "Bolt-Nut Boyutsal Uyum",
        "backend.library.compatibility_engine.check_bolt_nut_compatibility "
        "(bolt/nut master kayıtları)",
    ),
    "bolt_washer": (
        "Bolt-Washer Uyum",
        "backend.library.population.find_washer_for_bolt (washer library)",
    ),
    "washer_diameter": (
        "Washer Çap Uyum",
        "backend.library.population.find_washer_for_bolt (washer library, standard alanı)",
    ),
    "thread": (
        "Thread Uyum",
        "backend.library.population.find_thread (thread geometry library)",
    ),
    "strength_class": (
        "Strength Class Uyum",
        "backend.library.strength_compatibility.check_bolt_nut_strength_compatibility "
        "(strength class library)",
    ),
    "friction_condition": (
        "Friction Condition Uygunluğu",
        "backend.calculation_engine.friction_readiness.assess_friction_readiness "
        "(friction condition library)",
    ),
    "intended_use": (
        "Intended Use Uygunluğu",
        "Yok - repoda bağımsız intended-use alanı/kütüphanesi yok "
        "(blocked_authoritative_source).",
    ),
    "operating_temperature": (
        "Operating Temperature Uyum",
        "bolt/nut master kayıtlarının operating_temperature_min_c/max_c alanları",
    ),
    "coating": (
        "Coating Uyum",
        "bolt/nut master kayıtlarının coating_compatibility alanları",
    ),
    "material": (
        "Material Uyum",
        "Yok - bolt/nut kayıtlarındaki material alanı property_class ile birebir aynı, "
        "backend.library.material_library kayıtsız (blocked_authoritative_source).",
    ),
    "standard": (
        "Standard Uyum",
        "backend.standards.registry.get_standard (standards registry)",
    ),
    "oem_recommendation": (
        "OEM Önerisi",
        "backend.library.oem_library.resolve_oem_reference (OEM adapter -> standards registry)",
    ),
    "defence_recommendation": (
        "Defence Önerisi",
        "Yok - repoda kayıtlı bir defence standardı yok (blocked_authoritative_source).",
    ),
    "automotive_recommendation": (
        "Automotive Önerisi",
        "backend.library.oem_library.resolve_oem_reference (OEM adapter -> standards registry, "
        "ör. FIAT standartları)",
    ),
}

_SUGGESTED_ACTION_BY_STATUS: Dict[str, str] = {
    STATUS_COMPATIBLE: "Aksiyon gerekmiyor.",
    STATUS_INCOMPATIBLE: (
        "Kontrol reddedildi; ilgili bolt/nut/washer/thread/standard seçimini "
        "değiştirin veya kaydı düzeltin. Ayrıntı için 'detail' alanına bakın."
    ),
    STATUS_INSUFFICIENT_DATA: (
        "Bu kontrol için gerekli girdi veya kayıt sağlanmadı; eksik alanı "
        "sağlayarak yeniden değerlendirin."
    ),
    STATUS_BLOCKED_AUTHORITATIVE_SOURCE: (
        "Bu alan için repoda doğrulanmış/kaynaklı kayıt bulunmuyor; "
        "ilgili kütüphaneye gerçek, kaynaklı veri eklenmeden bu kontrol "
        "değerlendirilemez."
    ),
}


def _check_row(check: CheckResult) -> Dict[str, Any]:
    name, data_source = _CHECK_METADATA.get(
        check.check_id, (check.check_id, "")
    )
    action = _SUGGESTED_ACTION_BY_STATUS[check.status]
    return {
        "check_id": check.check_id,
        "check_name": name,
        "status": check.status,
        "severity": _SEVERITY_BY_STATUS[check.status],
        "detail": check.detail,
        "data_source": data_source,
        "suggested_action": action,
        "engine_warnings": list(check.warnings),
        "engine_recommendations": list(check.recommendations),
    }


def _overall_risk_level(result: AssemblyIntelligenceResult) -> str:
    if result.critical_incompatibilities:
        return "critical"
    if result.overall_status == "not_assessable":
        return "not_assessable"
    return "no_critical_incompatibility_detected"


def collect_assembly_intelligence_report(
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
) -> Dict[str, Any]:
    """Run Stage 1's ``assess_assembly`` exactly once for the given
    input and collect an additive, frozen, JSON-safe "Assembly
    Intelligence" report snapshot. Accepts the identical parameter set
    as ``assess_assembly`` -- this function does not add, remove or
    reinterpret any input.
    """
    result = assess_assembly(
        bolt_designation=bolt_designation,
        nut_designation=nut_designation,
        bolt_strength_class=bolt_strength_class,
        nut_property_class=nut_property_class,
        nominal_diameter_mm=nominal_diameter_mm,
        thread_designation=thread_designation,
        bolt_size=bolt_size,
        washer_standard=washer_standard,
        friction_condition_id=friction_condition_id,
        standard_name=standard_name,
        oem_reference=oem_reference,
        automotive_reference=automotive_reference,
        intended_operating_temperature_c=intended_operating_temperature_c,
        intended_coating=intended_coating,
    )
    return _collect_from_result(result)


def _collect_from_result(result: AssemblyIntelligenceResult) -> Dict[str, Any]:
    """Build the report dict from an already-computed Stage 1 result.
    Split out from ``collect_assembly_intelligence_report`` so tests
    (and future report-only callers, e.g. an API layer that already
    has a Stage 1 result in hand) can build a report without paying
    for a second ``assess_assembly`` call."""
    checks = [_check_row(c) for c in result.checks]

    passed = sum(1 for c in result.checks if c.status == STATUS_COMPATIBLE)
    failed = sum(1 for c in result.checks if c.status == STATUS_INCOMPATIBLE)
    warning = sum(
        1 for c in result.checks
        if c.status in (STATUS_INSUFFICIENT_DATA, STATUS_BLOCKED_AUTHORITATIVE_SOURCE)
    )

    return {
        "assembly_readiness": {
            "overall_status": result.overall_status,
            "overall_risk_level": _overall_risk_level(result),
            "has_critical_incompatibility": bool(result.critical_incompatibilities),
        },
        "score": {
            "assembly_intelligence_score": result.score,
            "score_denominator_note": (
                "Yalnızca compatible/incompatible sonucu üreten kontroller "
                "denominator'a dahildir; insufficient_data ve "
                "blocked_authoritative_source kontroller skora dahil değildir."
            ),
        },
        "coverage": {
            "assessment_coverage_percent": result.assessment_coverage_percent,
            "total_checks": result.total_checks,
            "assessed_checks": result.assessed_checks,
            "insufficient_data_checks": result.insufficient_data_checks,
            "blocked_authoritative_source_checks": result.blocked_authoritative_source_checks,
            "coverage_vs_score_note": (
                "Coverage, kaç kontrolün degerlendirilebildigini gosterir; "
                "score ile karistirilmamalidir -- yuksek score, dusuk "
                "coverage ile birlikte var olabilir."
            ),
        },
        "check_summary": {
            "passed": passed,
            "warning": warning,
            "failed": failed,
            "total": result.total_checks,
        },
        "checks": checks,
        "critical_incompatibilities": list(result.critical_incompatibilities),
    }


def render_assembly_intelligence_report_json(report: Dict[str, Any]) -> str:
    """Deterministic JSON rendering of an already-collected report
    (stable key order, no timestamps, no absolute paths)."""
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def render_assembly_intelligence_report_markdown(report: Dict[str, Any]) -> str:
    """Deterministic Markdown rendering of an already-collected
    report."""
    lines: List[str] = []
    a = lines.append

    a("# Faz 2.8.6 - Fastener Assembly Intelligence Raporu")
    a("")
    a(
        "Bu rapor Faz 2.8.6 Stage 1 motorunun (`assembly_intelligence.py`) "
        "sonucunu bicimlendirir; hicbir muhendislik kuralini, skoru veya "
        "durum eslemesini yeniden hesaplamaz."
    )
    a("")

    readiness = report["assembly_readiness"]
    a("## Assembly Readiness")
    a("")
    a("| Metrik | Deger |")
    a("|---|---:|")
    a(f"| Overall status | `{readiness['overall_status']}` |")
    a(f"| Overall risk level | `{readiness['overall_risk_level']}` |")
    a(
        "| Kritik uyumsuzluk var mi | "
        f"{'EVET' if readiness['has_critical_incompatibility'] else 'Hayir'} |"
    )
    a("")

    if report["critical_incompatibilities"]:
        a("## ⚠ Kritik Uyumsuzluklar (Critical Incompatibilities)")
        a("")
        a(
            "Asagidaki bulgular, toplam skor ne olursa olsun raporda ayrica "
            "ve acikca gosterilir; skor tarafindan gizlenmez."
        )
        a("")
        for item in report["critical_incompatibilities"]:
            a(f"- **{item}**")
        a("")

    score = report["score"]
    a("## Assessment Score")
    a("")
    a("| Metrik | Deger |")
    a("|---|---:|")
    score_value = score["assembly_intelligence_score"]
    score_display = "not_assessable" if score_value is None else f"{score_value:g}"
    a(f"| Assembly Intelligence Score | {score_display} |")
    a(f"| Not | {score['score_denominator_note']} |")
    a("")

    coverage = report["coverage"]
    a("## Coverage")
    a("")
    a("| Metrik | Deger |")
    a("|---|---:|")
    a(f"| Assessment coverage (%) | {coverage['assessment_coverage_percent']:g} |")
    a(f"| Toplam kontrol sayisi | {coverage['total_checks']} |")
    a(f"| Degerlendirilen kontrol sayisi | {coverage['assessed_checks']} |")
    a(f"| insufficient_data kontrol sayisi | {coverage['insufficient_data_checks']} |")
    a(
        "| blocked_authoritative_source kontrol sayisi | "
        f"{coverage['blocked_authoritative_source_checks']} |"
    )
    a("")
    a(f"> {coverage['coverage_vs_score_note']}")
    a("")

    summary = report["check_summary"]
    a("## Kontrol Ozeti (Passed / Warning / Failed)")
    a("")
    a("| Durum | Sayi |")
    a("|---|---:|")
    a(f"| Passed | {summary['passed']} |")
    a(f"| Warning | {summary['warning']} |")
    a(f"| Failed | {summary['failed']} |")
    a(f"| Toplam | {summary['total']} |")
    a("")

    a("## Kontrol Detaylari")
    a("")
    a(
        "| Check ID | Kontrol Adi | Status | Severity | Aciklama | "
        "Kaynak/Veri | Onerilen Aksiyon |"
    )
    a("|---|---|---|---|---|---|---|")
    for row in report["checks"]:
        a(
            f"| `{row['check_id']}` | {row['check_name']} | `{row['status']}` | "
            f"`{row['severity']}` | {row['detail']} | {row['data_source']} | "
            f"{row['suggested_action']} |"
        )
    a("")

    text = "\n".join(lines)
    return text.rstrip("\n") + "\n"


__all__ = [
    "collect_assembly_intelligence_report",
    "collect_assembly_intelligence_report_from_result",
    "render_assembly_intelligence_report_json",
    "render_assembly_intelligence_report_markdown",
]

# Public alias for _collect_from_result (Stage 3 addition): the API
# layer (backend/app.py) already has a Stage 1 AssemblyIntelligenceResult
# in hand and must not call assess_assembly() a second time just to
# build the report -- exactly the reuse case _collect_from_result's own
# docstring anticipated. No engineering logic changed; this is a pure
# visibility alias, the underscore-prefixed name is untouched and still
# used internally/by Stage 2 tests.
collect_assembly_intelligence_report_from_result = _collect_from_result
