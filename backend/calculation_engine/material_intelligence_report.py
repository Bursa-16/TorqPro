"""TorqPro Calculation Engine - Material Intelligence / Formula
Validation Professional Report integration (Faz 2.8.8).

Follows the collector/renderer pattern already established by
``strength_class_report.py`` / ``friction_report.py`` /
``assembly_intelligence_report.py``: a pure ``collect_*`` function
calls Faz 2.8.8 domain logic exactly once and freezes the result; a
pure ``render_*`` function only formats an already-collected snapshot
(JSON native, Markdown text) -- it never re-invokes any domain
calculation and never reads the wall clock, so two calls with
identical inputs produce byte-identical output (determinism
requirement carried from every prior report module).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .formula_validation import build_formula_validation_report
from .material_intelligence import MaterialRequirement, recommend_materials

_SECTION_TITLES = {
    "material_intelligence": {
        "tr": "Malzeme Zekası Değerlendirmesi",
        "en": "Material Intelligence Assessment",
    },
    "formula_validation": {
        "tr": "Mühendislik Formülü Doğrulama Kapsamı",
        "en": "Engineering Formula Validation Coverage",
    },
    "candidates": {"tr": "Adaylar", "en": "Candidates"},
    "warnings": {"tr": "Mühendislik Uyarıları", "en": "Engineering Warnings"},
    "readiness": {"tr": "Hazırlık Seviyesi", "en": "Readiness Level"},
    "sign_off": {"tr": "Onay Notu", "en": "Sign-off Notice"},
    "notices": {"tr": "Notlar", "en": "Notices"},
}


def _t(key: str, lang: str) -> str:
    entry = _SECTION_TITLES[key]
    return entry.get(lang, entry["tr"])


def _normalize_lang(lang: Optional[str]) -> str:
    return "en" if (lang or "tr").strip().lower().startswith("en") else "tr"


@dataclass
class MaterialIntelligenceReportSnapshot:
    """One collected, immutable Faz 2.8.8 report snapshot."""

    lang: str
    material_recommendation: Dict[str, Any] = field(default_factory=dict)
    formula_validation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lang": self.lang,
            "material_recommendation": dict(self.material_recommendation),
            "formula_validation": dict(self.formula_validation),
        }


def collect_material_intelligence_report(
    requirement: Optional[MaterialRequirement] = None, lang: Optional[str] = None
) -> MaterialIntelligenceReportSnapshot:
    """Collect one Faz 2.8.8 report snapshot. Calls
    ``recommend_materials`` and ``build_formula_validation_report``
    exactly once each; the returned snapshot is a frozen projection,
    never re-derived by the renderer."""
    lang = _normalize_lang(lang)
    recommendation = recommend_materials(requirement, lang=lang)
    formula_report = build_formula_validation_report(lang=lang)
    return MaterialIntelligenceReportSnapshot(
        lang=lang,
        material_recommendation=recommendation.to_dict(),
        formula_validation=formula_report.to_dict(),
    )


def render_material_intelligence_report_markdown(
    snapshot: MaterialIntelligenceReportSnapshot,
) -> str:
    """Render an already-collected snapshot to Markdown. Never
    re-invokes domain logic; a legacy/partial snapshot dict-like
    object renders without raising by falling back to empty
    collections for any missing field."""
    lang = snapshot.lang
    rec = snapshot.material_recommendation or {}
    fv = snapshot.formula_validation or {}

    lines: List[str] = []
    lines.append(f"# {_t('material_intelligence', lang)}")
    lines.append("")
    lines.append(f"**{_t('readiness', lang)}:** {rec.get('readiness_level', '')}")
    lines.append("")

    candidates = rec.get("candidates") or []
    if candidates:
        lines.append(f"## {_t('candidates', lang)}")
        lines.append("")
        lines.append("| ID | Material | Grade | Rp0.2 (MPa) | Rm (MPa) | E (MPa) |")
        lines.append("|---|---|---|---|---|---|")
        for c in candidates:
            lines.append(
                "| {material_id} | {material} | {grade} | {rp02_mpa} | {rm_mpa} | "
                "{elastic_modulus_mpa} |".format(**c)
            )
        lines.append("")

    warnings = rec.get("engineering_warnings") or []
    if warnings:
        lines.append(f"## {_t('warnings', lang)}")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append(f"**{_t('sign_off', lang)}:** {rec.get('sign_off_notice', '')}")
    lines.append("")

    lines.append(f"## {_t('formula_validation', lang)}")
    lines.append("")
    lines.append(
        "{approved}/{total} APPROVED, {provisional}/{total} PROVISIONAL".format(
            approved=fv.get("approved_count", 0),
            provisional=fv.get("provisional_count", 0),
            total=fv.get("total_count", 0),
        )
    )
    lines.append("")
    notices = fv.get("notices") or []
    if notices:
        lines.append(f"### {_t('notices', lang)}")
        lines.append("")
        for n in notices:
            lines.append(f"- {n}")
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "MaterialIntelligenceReportSnapshot",
    "collect_material_intelligence_report",
    "render_material_intelligence_report_markdown",
]
