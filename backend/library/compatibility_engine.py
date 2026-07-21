"""TorqPro Engineering Library - bolt/nut compatibility service (Faz
2.4.1B).

Kept as its own module rather than added directly to
``compatibility.py``: that module is deliberately metadata-only (see
its docstring -- "no compatibility logic is implemented here", a
Phase 1.3 design decision this phase does not reverse). This module
sits alongside it and consumes the same ``bolt library`` / ``nut
library`` record shape; nothing here mutates ``COMPATIBILITY_LIBRARY``
or any other registered library.

``check_bolt_nut_compatibility`` is a structured, non-boolean
compatibility check over one bolt record and one nut record (the
per-record dicts already returned by ``population.find_bolt`` /
``population.search_bolts`` / ``population.find_nut`` /
``population.search_nuts``). It never returns a bare ``True``/``False``
-- always a :class:`CompatibilityResult` carrying warnings, hard
errors and informational engineering notes, per the Faz 2.4.1B brief
(section 9): "Çıktı yalnızca True/False olması" (the output must not
be boolean-only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: ISO 898-1/898-2 minimum nut property class required to safely mate
#: a given bolt property class (ISO 898-2 Table 1 minimum nut/bolt
#: pairing convention: nut class numeral must be >= the bolt's
#: strength-class integer part). Used for the strength cross-check
#: below; independent from (does not import) ``validator.py``'s
#: ``KNOWN_BOLT_CLASSES`` / ``KNOWN_NUT_CLASSES`` allow-lists, which
#: only check format/membership, not the pairing rule itself.
MINIMUM_NUT_CLASS_FOR_BOLT_CLASS: Dict[str, str] = {
    "3.6": "04", "4.6": "4", "4.8": "4", "5.6": "5", "5.8": "5",
    "6.8": "6", "6.9": "6", "8.8": "8", "9.8": "9", "10.9": "10", "12.9": "12",
}


@dataclass
class CompatibilityResult:
    """Structured bolt/nut compatibility outcome.

    ``compatible`` is the overall pass/fail summary, but the point of
    this type is that a caller always also gets ``warnings`` (things
    worth a human's attention that don't block the pairing),
    ``errors`` (things that make the pairing unsafe or invalid -- any
    non-empty ``errors`` forces ``compatible = False``), and
    ``engineering_notes`` (informational context, e.g. what standard
    families are involved, with no bearing on pass/fail).
    """

    compatible: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    engineering_notes: List[str] = field(default_factory=list)


def _diameter(record: Dict[str, Any]) -> Optional[float]:
    return record.get("nominal_diameter_mm", record.get("diameter_mm"))


def _pitch(record: Dict[str, Any]) -> Optional[float]:
    return record.get("pitch_mm", record.get("pitch_coarse_mm"))


def check_bolt_nut_compatibility(
    bolt: Dict[str, Any], nut: Dict[str, Any],
) -> CompatibilityResult:
    """Check whether ``bolt`` and ``nut`` (raw record dicts from the
    bolt/nut population data) can be safely paired.

    Runs every check the Faz 2.4.1B brief lists (section 9): nominal
    diameter match, pitch match, thread tolerance-class compatibility,
    coarse/fine agreement, bolt strength class <-> nut property class,
    operating-temperature range overlap, coating compatibility,
    lock-nut reuse warning, cross-standard-family warning, and a
    lubrication/coating friction-mismatch warning. Any ``errors`` (a
    diameter/pitch/coarse-fine mismatch, or an under-strength nut)
    forces ``compatible = False``; everything else that's merely
    worth flagging goes into ``warnings`` without blocking the pair.
    """
    warnings: List[str] = []
    errors: List[str] = []
    notes: List[str] = []

    bolt_dia = _diameter(bolt)
    nut_dia = _diameter(nut)
    if bolt_dia is None or nut_dia is None:
        errors.append("Bolt or nut record is missing a nominal diameter.")
    elif bolt_dia != nut_dia:
        errors.append(
            f"Nominal diameter mismatch: bolt={bolt_dia} mm, nut={nut_dia} mm."
        )

    bolt_pitch = _pitch(bolt)
    nut_pitch = _pitch(nut)
    if bolt_pitch is not None and nut_pitch is not None and bolt_pitch != nut_pitch:
        errors.append(
            f"Pitch mismatch: bolt={bolt_pitch} mm, nut={nut_pitch} mm."
        )

    bolt_cf = (bolt.get("coarse_or_fine") or "").lower()
    nut_cf = (nut.get("coarse_or_fine") or "").lower()
    if bolt_cf and nut_cf and bolt_cf != nut_cf:
        errors.append(
            f"Coarse/fine mismatch: bolt is {bolt_cf!r}, nut is {nut_cf!r}."
        )

    bolt_tol = bolt.get("thread_tolerance_class", "")
    nut_tol = nut.get("thread_tolerance_class", "")
    if bolt_tol and nut_tol:
        # ISO 965 convention: external (bolt) tolerance classes are
        # lower-case ("6g"), internal (nut) tolerance classes are
        # upper-case ("6H") -- flag anything that doesn't look like
        # that pairing shape as worth a second look, not a hard error
        # (unusual but not inherently invalid pairings exist).
        if not (bolt_tol[-1].islower() and nut_tol[-1].isupper()):
            warnings.append(
                f"Unusual thread tolerance-class pairing: bolt={bolt_tol!r}, "
                f"nut={nut_tol!r} (expected lower-case external / "
                "upper-case internal per ISO 965)."
            )

    bolt_class = bolt.get("property_class", "")
    nut_class = nut.get("property_class", "")
    minimum_nut = MINIMUM_NUT_CLASS_FOR_BOLT_CLASS.get(bolt_class)
    if minimum_nut is not None and nut_class:
        try:
            if float(nut_class) < float(minimum_nut):
                errors.append(
                    f"Nut property class {nut_class!r} is below the ISO "
                    f"898-2 minimum ({minimum_nut!r}) for bolt class "
                    f"{bolt_class!r}."
                )
        except ValueError:
            warnings.append(
                f"Could not numerically compare bolt class {bolt_class!r} "
                f"and nut class {nut_class!r}."
            )
    elif bolt_class and not minimum_nut:
        warnings.append(f"Unrecognised bolt strength class {bolt_class!r}.")

    bolt_tmin = bolt.get("operating_temperature_min_c")
    bolt_tmax = bolt.get("operating_temperature_max_c")
    nut_tmin = nut.get("operating_temperature_min_c")
    nut_tmax = nut.get("operating_temperature_max_c")
    if (
        bolt_tmin is not None
        and bolt_tmax is not None
        and nut_tmin is not None
        and nut_tmax is not None
    ):
        overlap_low = max(bolt_tmin, nut_tmin)
        overlap_high = min(bolt_tmax, nut_tmax)
        if overlap_low > overlap_high:
            warnings.append(
                f"No overlapping operating temperature range: bolt "
                f"[{bolt_tmin}, {bolt_tmax}] C, nut [{nut_tmin}, {nut_tmax}] C."
            )

    bolt_coatings = set(c.lower() for c in bolt.get("coating_compatibility", []))
    nut_coatings = set(c.lower() for c in nut.get("coating_compatibility", []))
    if bolt_coatings and nut_coatings and not (bolt_coatings & nut_coatings):
        warnings.append(
            "No shared coating option between bolt "
            f"({sorted(bolt.get('coating_compatibility', []))}) and nut "
            f"({sorted(nut.get('coating_compatibility', []))})."
        )

    locking_type = nut.get("locking_type", "None")
    if locking_type and locking_type != "None":
        if nut.get("reusable") is False:
            warnings.append(
                f"{nut.get('nut_family', 'Lock nut')} ({locking_type}) is "
                "not rated for reuse -- replace after removal, do not "
                "reinstall the same nut."
            )
        elif nut.get("reusable") is True:
            notes.append(
                f"{nut.get('nut_family', 'Lock nut')} ({locking_type}) is "
                "reusable a limited number of cycles per the standard's "
                "guidance -- inspect before reuse."
            )

    bolt_standard = bolt.get("source_standard", "")
    nut_standard = nut.get("source_standard", "")
    bolt_family = (bolt_standard.split()[0] if bolt_standard else "")
    nut_family = (nut_standard.split()[0] if nut_standard else "")
    if bolt_family and nut_family and bolt_family != nut_family:
        warnings.append(
            f"Cross-standard-family pairing: bolt is {bolt_standard!r} "
            f"({bolt_family}), nut is {nut_standard!r} ({nut_family}) -- "
            "dimensionally compatible ISO metric threads, but mixing "
            "standard families is worth a second look for structural "
            "(EN 14399 / HR-HV system) applications."
        )

    bolt_lube = (bolt.get("lubrication_state") or "").lower()
    nut_lube = (nut.get("lubrication_state") or "").lower()
    if bolt_lube and nut_lube and bolt_lube != nut_lube:
        warnings.append(
            f"Lubrication-state mismatch may change assembly friction: "
            f"bolt is {bolt.get('lubrication_state')!r}, nut is "
            f"{nut.get('lubrication_state')!r}."
        )

    if bolt_dia is not None:
        notes.append(f"Nominal thread size: M{bolt_dia:g}.")
    if bolt_class and nut_class:
        notes.append(f"Bolt class {bolt_class} paired with nut class {nut_class}.")

    return CompatibilityResult(
        compatible=not errors,
        warnings=warnings,
        errors=errors,
        engineering_notes=notes,
    )


__all__ = [
    "CompatibilityResult",
    "MINIMUM_NUT_CLASS_FOR_BOLT_CLASS",
    "check_bolt_nut_compatibility",
]
