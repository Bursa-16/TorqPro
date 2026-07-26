"""TorqPro Engineering Library - Faz 2.8.3 bolt/nut STRENGTH-CLASS
compatibility engine.

Deliberately separate from ``backend.library.compatibility_engine``
(Faz 2.4.1B): that module checks dimensional/thread/coating/lock-type
compatibility between concrete bolt and nut *records*. This module
checks strength-CLASS pairing only (bolt property class vs nut
property class vs an optional nominal diameter), independent of any
specific bolt/nut record, and always returns one of exactly four
statuses (``compatible`` / ``conditionally_compatible`` /
``not_compatible`` / ``unknown``) with deterministic reason/warning
ordering, per the Faz 2.8.3 brief.
"""

from __future__ import annotations

from typing import List, Optional

from .strength_classes import (
    BoltNutCompatibilityResult,
    BoltStrengthClassRecord,
    NutPropertyClassRecord,
    get_bolt_strength_class,
    get_nut_property_class,
)

#: Nut property class numeral required, at minimum, to safely mate a
#: given ISO 898-1 bolt strength class -- ISO 898-2's own pairing
#: convention (nut class numeral >= bolt class integer part). "04"
#: sorts below "4" numerically (both proof stress 400 MPa; 04 is the
#: thin-nut style) so the comparison below is done on the *numeric*
#: value of the nut designation, not its string form -- 3.6 has no
#: entry in the Faz 2.8.3 bolt data (2.8.3 covers 4.6 upward) and is
#: intentionally omitted here.
_MINIMUM_NUT_NUMERAL_FOR_BOLT_CLASS = {
    "4.6": 4.0, "4.8": 4.0,
    "5.6": 5.0, "5.8": 5.0,
    "6.8": 6.0,
    "8.8": 8.0,
    "9.8": 9.0,
    "10.9": 10.0,
    "12.9": 12.0,
}

_CARBON_STEEL_STANDARDS = {"ISO 898", "ISO 898-1", "ISO 898-2"}
_STAINLESS_STANDARDS = {"ISO 3506", "ISO 3506-1", "ISO 3506-2"}


def _standard_family(standard: str) -> str:
    """Collapse a standard string to a coarse family bucket so "ISO
    898" and "ISO 898-1" compare equal (same family), while "ISO 898"
    and "ISO 3506" do not (per the Faz 2.8.3 rule list)."""
    if standard in _CARBON_STEEL_STANDARDS:
        return "iso_898"
    if standard in _STAINLESS_STANDARDS:
        return "iso_3506"
    return standard


def _nut_numeral(designation: str) -> Optional[float]:
    try:
        return float(designation)
    except ValueError:
        return None


def check_bolt_nut_strength_compatibility(
    bolt_strength_class: Optional[str],
    nut_property_class: Optional[str],
    nominal_diameter_mm: Optional[float] = None,
    standard: Optional[str] = None,
    material_family: Optional[str] = None,
) -> BoltNutCompatibilityResult:
    """Check whether ``bolt_strength_class`` and ``nut_property_class``
    are a safe strength pairing.

    ``standard`` / ``material_family`` are optional caller-supplied
    context (e.g. "the user selected ISO 3506" in a UI); when
    provided they're cross-checked against the resolved records'
    own ``standard``/``material_family`` rather than trusted blindly.
    Reason/warning/warning_code ordering is deterministic: findings
    are always appended in the same fixed check order (see ``checks``
    keys below), never via set iteration.
    """
    reasons: List[str] = []
    warnings: List[str] = []
    warning_codes: List[str] = []
    checks: dict = {}

    bolt: Optional[BoltStrengthClassRecord] = (
        get_bolt_strength_class(bolt_strength_class) if bolt_strength_class else None
    )
    nut: Optional[NutPropertyClassRecord] = (
        get_nut_property_class(nut_property_class) if nut_property_class else None
    )

    if bolt is None or nut is None:
        missing = []
        if bolt is None:
            missing.append(f"bolt strength class {bolt_strength_class!r}")
        if nut is None:
            missing.append(f"nut property class {nut_property_class!r}")
        reasons.append(f"Unknown or unrecognised: {', '.join(missing)}.")
        checks["strength_class"] = "unknown"
        return BoltNutCompatibilityResult(
            status="unknown",
            compatible=False,
            bolt_strength_class=bolt_strength_class,
            nut_property_class=nut_property_class,
            recommended_minimum_nut_class=None,
            reasons=reasons,
            warnings=warnings,
            warning_codes=warning_codes,
            checks=checks,
        )

    conditional = False

    # -- Check 1: strength class pairing -----------------------------
    minimum_numeral = _MINIMUM_NUT_NUMERAL_FOR_BOLT_CLASS.get(bolt.designation)
    nut_numeral = _nut_numeral(nut.designation)
    recommended_minimum_nut_class = None
    if minimum_numeral is not None:
        # Find the smallest known nut numeral >= minimum_numeral as the
        # recommendation (deterministic: sorted ascending).
        candidates = sorted(
            {
                v for v in (
                    4.0, 4.0, 5.0, 6.0, 8.0, 9.0, 10.0, 12.0,
                ) if v >= minimum_numeral
            }
        )
        if candidates:
            recommended_minimum_nut_class = (
                "04" if candidates[0] == 4.0 and minimum_numeral <= 4.0
                else str(int(candidates[0]))
            )
    if minimum_numeral is None or nut_numeral is None:
        warnings.append(
            f"Could not numerically evaluate strength pairing for bolt "
            f"{bolt.designation!r} / nut {nut.designation!r}."
        )
        warning_codes.append("strength_pairing_unevaluated")
        checks["strength_class"] = "unevaluated"
    elif nut_numeral < minimum_numeral:
        reasons.append(
            f"Nut property class {nut.designation} (proof "
            f"{nut.proof_load_stress_mpa} MPa) is below the ISO 898-2 "
            f"minimum required for bolt class {bolt.designation} "
            f"(minimum nut numeral {minimum_numeral:g})."
        )
        checks["strength_class"] = "fail"
    else:
        checks["strength_class"] = "pass"

    # -- Check 2: material family / stainless cross-pairing ----------
    if bolt.material_family != material_family and material_family is not None:
        warnings.append(
            f"Requested material_family {material_family!r} does not "
            f"match the resolved bolt record's material_family "
            f"{bolt.material_family.value!r}."
        )
        warning_codes.append("material_family_mismatch_input")

    bolt_is_stainless = bolt.material_family.value.startswith("stainless")
    nut_is_stainless = nut.material_family.value.startswith("stainless")
    if bolt_is_stainless != nut_is_stainless:
        reasons.append(
            "Stainless/carbon-steel material mismatch: bolt material "
            f"family is {bolt.material_family.value!r}, nut material "
            f"family is {nut.material_family.value!r} -- a stainless "
            "bolt paired with a carbon-steel nut (or vice versa) is "
            "not treated as a straightforward compatible pairing "
            "(galvanic/thermal-expansion and strength-table mismatch "
            "concerns)."
        )
        checks["material_family"] = "fail"
    else:
        checks["material_family"] = "pass"

    # -- Check 3: standard family --------------------------------
    bolt_family = _standard_family(bolt.standard)
    nut_family = _standard_family(nut.standard)
    if standard is not None and _standard_family(standard) != bolt_family:
        warnings.append(
            f"Requested standard {standard!r} does not match the "
            f"resolved bolt record's standard {bolt.standard!r}."
        )
        warning_codes.append("standard_mismatch_input")
    if bolt_family != nut_family:
        # ISO 898 vs ISO 898-2 (nut) collapse to the same family and
        # never land here; only a genuine cross-standard pairing
        # (e.g. ISO 898-1 bolt with an ISO 3506-2 nut) does.
        reasons.append(
            f"Cross-standard-family pairing: bolt standard "
            f"{bolt.standard!r}, nut standard {nut.standard!r} are not "
            "the same standard family (ISO 898 vs ISO 3506 are never "
            "treated as fully interchangeable)."
        )
        checks["standard"] = "fail"
    else:
        checks["standard"] = "pass"

    # -- Check 4: diameter range overlap ------------------------------
    diameter_status = "pass"
    if nominal_diameter_mm is not None:
        bolt_ok = (
            (bolt.diameter_min_mm is None or nominal_diameter_mm >= bolt.diameter_min_mm)
            and (bolt.diameter_max_mm is None or nominal_diameter_mm <= bolt.diameter_max_mm)
        )
        nut_ok = (
            (nut.diameter_min_mm is None or nominal_diameter_mm >= nut.diameter_min_mm)
            and (nut.diameter_max_mm is None or nominal_diameter_mm <= nut.diameter_max_mm)
        )
        if not (bolt_ok and nut_ok):
            warnings.append(
                f"Nominal diameter {nominal_diameter_mm:g} mm is outside "
                f"the applicable range for bolt class {bolt.designation} "
                f"(M{bolt.diameter_min_mm:g}-M{bolt.diameter_max_mm:g}) "
                f"and/or nut class {nut.designation} "
                f"(M{nut.diameter_min_mm:g}-M{nut.diameter_max_mm:g})."
            )
            warning_codes.append("diameter_out_of_range")
            diameter_status = "fail"
            conditional = True
    checks["diameter_range"] = diameter_status

    # -- Engineering-warning passthrough (e.g. ISO 3506 scope note) --
    if bolt.engineering_warning:
        warnings.append(bolt.engineering_warning)
        warning_codes.append("bolt_class_engineering_warning")

    if reasons:
        status = "not_compatible"
        compatible = False
    elif conditional:
        status = "conditionally_compatible"
        compatible = False
    else:
        status = "compatible"
        compatible = True

    return BoltNutCompatibilityResult(
        status=status,
        compatible=compatible,
        bolt_strength_class=bolt.designation,
        nut_property_class=nut.designation,
        recommended_minimum_nut_class=recommended_minimum_nut_class,
        reasons=reasons,
        warnings=warnings,
        warning_codes=warning_codes,
        checks=checks,
    )


__all__ = ["check_bolt_nut_strength_compatibility"]
