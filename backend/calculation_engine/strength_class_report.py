"""TorqPro Calculation Engine - Bolt/Nut Strength Class Reporting
(Faz 2.8.3).

Investigation finding: this base commit (19bbe5c) has no
``backend/reports`` package and no PDF/HTML report generator (see
``friction_report.py``'s own docstring, which documents the same
finding for Faz 2.6.5). There is therefore no existing "Faz 2.7
collector/snapshot architecture" to integrate with in this checkout.
This module follows the same pattern ``friction_report.py`` already
established instead: a self-contained, additive JSON snapshot
(collector) plus a separate renderer, so a future PDF/HTML report
builder can consume ``to_dict()`` output unchanged whenever one
exists.

Collector and renderer are kept separate on purpose (task requirement,
section 13): ``collect_strength_class_snapshot`` calls the domain
logic (``strength_classes`` / ``strength_compatibility``) exactly
once and freezes the result; ``render_strength_class_snapshot`` only
formats an already-collected (or legacy/partial) snapshot dict -- it
never re-invokes any domain calculation. A legacy or incomplete
snapshot (missing any of the Faz 2.8.3 fields) renders without
raising; every new field defaults to ``None`` rather than causing an
exception, so existing/older reports keep working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.library.strength_classes import (
    get_bolt_strength_class,
    get_nut_property_class,
)
from backend.library.strength_compatibility import check_bolt_nut_strength_compatibility

#: New, additive snapshot fields this phase introduces (task section
#: 13's exact list) -- every one of these is optional/``None``-safe on
#: both collection and rendering.
STRENGTH_SNAPSHOT_FIELDS = (
    "bolt_strength_class",
    "nut_property_class",
    "strength_standard",
    "mechanical_properties",
    "compatibility_status",
    "compatibility_warnings",
    "strength_class_verification_status",
    "strength_class_source",
    "strength_value_source",
    "manual_override",
)


@dataclass
class StrengthClassSnapshot:
    """One collected, immutable strength-class report snapshot."""

    bolt_strength_class: Optional[str] = None
    nut_property_class: Optional[str] = None
    strength_standard: Optional[str] = None
    mechanical_properties: Dict[str, Any] = field(default_factory=dict)
    compatibility_status: Optional[str] = None
    compatibility_warnings: List[str] = field(default_factory=list)
    strength_class_verification_status: Optional[str] = None
    strength_class_source: Optional[str] = None
    strength_value_source: Dict[str, Optional[str]] = field(default_factory=dict)
    manual_override: bool = False
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable projection -- plain dict/list/str/bool/
        None only, safe for ``json.dumps`` with no custom encoder."""
        return {
            "bolt_strength_class": self.bolt_strength_class,
            "nut_property_class": self.nut_property_class,
            "strength_standard": self.strength_standard,
            "mechanical_properties": dict(self.mechanical_properties),
            "compatibility_status": self.compatibility_status,
            "compatibility_warnings": list(self.compatibility_warnings),
            "strength_class_verification_status": self.strength_class_verification_status,
            "strength_class_source": self.strength_class_source,
            "strength_value_source": dict(self.strength_value_source),
            "manual_override": self.manual_override,
            "generated_at": self.generated_at,
        }


def collect_strength_class_snapshot(
    bolt_strength_class: Optional[str] = None,
    nut_property_class: Optional[str] = None,
    nominal_diameter_mm: Optional[float] = None,
    manual_values: Optional[Dict[str, float]] = None,
) -> StrengthClassSnapshot:
    """Collect one strength-class report snapshot. Calls the Faz 2.8.3
    domain logic exactly once; the returned snapshot is a frozen
    projection of that call's results, never re-derived later by the
    renderer."""
    manual_values = manual_values or {}
    bolt = get_bolt_strength_class(bolt_strength_class) if bolt_strength_class else None
    nut = get_nut_property_class(nut_property_class) if nut_property_class else None

    mechanical_properties: Dict[str, Any] = {}
    strength_value_source: Dict[str, Optional[str]] = {}
    if bolt is not None:
        from backend.library.strength_classes import resolve_strength_properties
        resolved = resolve_strength_properties(bolt.designation, manual_values=manual_values)
        mechanical_properties = {
            k: v for k, v in resolved.items()
            if k not in ("designation", "sources", "has_library_record")
        }
        strength_value_source = dict(resolved["sources"])

    compatibility_status = None
    compatibility_warnings: List[str] = []
    if bolt_strength_class and nut_property_class:
        result = check_bolt_nut_strength_compatibility(
            bolt_strength_class, nut_property_class,
            nominal_diameter_mm=nominal_diameter_mm,
        )
        compatibility_status = result.status
        compatibility_warnings = list(result.warnings)

    return StrengthClassSnapshot(
        bolt_strength_class=bolt.designation if bolt else bolt_strength_class,
        nut_property_class=nut.designation if nut else nut_property_class,
        strength_standard=bolt.standard if bolt else None,
        mechanical_properties=mechanical_properties,
        compatibility_status=compatibility_status,
        compatibility_warnings=compatibility_warnings,
        strength_class_verification_status=(
            bolt.verification_status.value if bolt else None
        ),
        strength_class_source=bolt.source if bolt else None,
        strength_value_source=strength_value_source,
        manual_override=bool(manual_values),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def render_strength_class_snapshot(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Render an already-collected snapshot dict for display.

    Never calls into ``strength_classes`` / ``strength_compatibility``
    -- purely formats what it is given. Accepts ``None`` or a legacy/
    partial dict missing any of ``STRENGTH_SNAPSHOT_FIELDS`` without
    raising: every missing field renders as an explicit ``None`` /
    empty value rather than an exception, so an older report (from
    before this phase, or any report that never touched strength
    classes) keeps rendering unchanged.
    """
    snapshot = snapshot or {}
    rendered: Dict[str, Any] = {}
    for name in STRENGTH_SNAPSHOT_FIELDS:
        value = snapshot.get(name)
        if name == "compatibility_warnings" and value is None:
            value = []
        if name == "mechanical_properties" and value is None:
            value = {}
        if name == "strength_value_source" and value is None:
            value = {}
        if name == "manual_override" and value is None:
            value = False
        rendered[name] = value
    rendered["has_strength_class_data"] = bool(
        snapshot.get("bolt_strength_class") or snapshot.get("nut_property_class")
    )
    return rendered


__all__ = [
    "StrengthClassSnapshot",
    "STRENGTH_SNAPSHOT_FIELDS",
    "collect_strength_class_snapshot",
    "render_strength_class_snapshot",
]
