"""TorqPro Engineering Library - ISO 724 basic-profile thread geometry
helpers (Faz 2.4.1A).

Pure, dependency-free geometry functions used to derive the Faz
2.4.1A ``ThreadRecord`` fields (``major_diameter_mm``,
``minor_diameter_external_mm``, ``minor_diameter_internal_mm``) from
``nominal_diameter_mm`` / ``pitch_mm``, and reused by
``validator.py`` to tolerance-check those fields on existing records.

Scope and package-isolation note
---------------------------------
This module intentionally duplicates the same ISO 68-1 / ISO 724
basic-profile constants already present in
``backend.vdi2230_core.stress_area`` (``PITCH_DIAMETER_FACTOR`` /
``MINOR_DIAMETER_FACTOR``) rather than importing them. That mirrors
the isolation pattern ``vdi2230_core`` itself already uses versus
``engineering_core`` (see the docstring of that module): each package
keeps its own copy of these public-domain constants so that
``backend.library`` stays independent of ``backend.vdi2230_core`` /
``backend.calculation_engine``, per the Faz 2.4 Option C architecture
decision (library is data-only; no VDI 2230 formula changes in this
phase). No VDI 2230 formula is read, imported, or modified here.

Formulas (ISO 68-1 basic triangle, H = sqrt(3)/2 * P; ISO 724 basic
profile, no tolerance allowance applied):

    d2 = D2 = D - 0.75 * H            (pitch diameter, external/internal)
    d3      = D - (17/12) * H          (minor diameter, external/bolt,
                                         rounded root)
    D1      = D - 1.25 * H             (minor diameter, internal/nut,
                                         sharp root)
    d = D   = nominal diameter         (basic major diameter, same
                                         theoretical value for both
                                         external and internal threads)

These are the *basic* (theoretical) values with no tolerance
allowance -- the same convention already used for the pre-existing
``pitch_diameter_mm`` / ``minor_diameter_mm`` fields in
``data/thread_library.json`` (verified against that data below).
"""

from __future__ import annotations

import math

#: sqrt(3)/2, the ISO 68-1 basic triangle height factor (H = FACTOR * P).
BASIC_TRIANGLE_HEIGHT_FACTOR = math.sqrt(3) / 2

#: Pitch-diameter factor: d2 = D2 = D - PITCH_DIAMETER_FACTOR * P.
PITCH_DIAMETER_FACTOR = 0.75 * BASIC_TRIANGLE_HEIGHT_FACTOR

#: External (bolt) minor-diameter factor, rounded root:
#: d3 = D - MINOR_DIAMETER_EXTERNAL_FACTOR * P.
MINOR_DIAMETER_EXTERNAL_FACTOR = (17 / 12) * BASIC_TRIANGLE_HEIGHT_FACTOR

#: Internal (nut) minor-diameter factor, sharp root:
#: D1 = D - MINOR_DIAMETER_INTERNAL_FACTOR * P.
MINOR_DIAMETER_INTERNAL_FACTOR = 1.25 * BASIC_TRIANGLE_HEIGHT_FACTOR


def basic_major_diameter_mm(nominal_diameter_mm: float) -> float:
    """Basic (theoretical, no-tolerance) major diameter.

    Identical for external and internal ISO metric threads in the
    basic profile -- always equal to ``nominal_diameter_mm``. Carried
    as its own function/field for schema completeness, not because
    the value differs.
    """
    return nominal_diameter_mm


def basic_pitch_diameter_mm(nominal_diameter_mm: float, pitch_mm: float) -> float:
    """Basic pitch diameter d2 = D2 (same value, external or internal)."""
    return nominal_diameter_mm - PITCH_DIAMETER_FACTOR * pitch_mm


def basic_minor_diameter_external_mm(nominal_diameter_mm: float, pitch_mm: float) -> float:
    """Basic external (bolt) minor diameter d3, rounded root."""
    return nominal_diameter_mm - MINOR_DIAMETER_EXTERNAL_FACTOR * pitch_mm


def basic_minor_diameter_internal_mm(nominal_diameter_mm: float, pitch_mm: float) -> float:
    """Basic internal (nut) minor diameter D1, sharp root."""
    return nominal_diameter_mm - MINOR_DIAMETER_INTERNAL_FACTOR * pitch_mm
