"""Faz 2.4.1B - controlled bolt/nut engineering-record generator.

One-off, explicitly-invoked script (not imported by ``backend.library``
at runtime -- mirrors the "controlled data-generation script" allowed
by the phase brief, section 5: "Kontrollü veri üretim script'i
kullanılabilir; ancak üretilen kayıtların kaynak, çap, pitch, sınıf ve
boyutsal geçerliliği test edilmelidir."). Run once via
``python tools/generate_faz2_4_1b_bolt_nut_records.py`` to append new
bolt/nut families/standards to the existing
``backend/library/data/bolt_library.json`` /
``backend/library/data/nut_library.json`` data files (the population
loader already reads a single JSON file per domain -- see
``backend.library.population.POPULATION_SOURCES`` -- so this keeps
that existing architecture rather than introducing a new
``data/bolts/`` / ``data/nuts/`` directory split).

Every generated record is checksummed and every geometric field is
either:
  * reused from an existing, already-in-library standard whose head/
    body geometry is publicly documented as identical or
    near-identical to the new standard being added (e.g. ISO 4014 and
    ISO 4017 share the same head-dimension table; DIN 931/933 are the
    historical DIN equivalents of ISO 4014/4017; DIN 912 is the DIN
    equivalent of ISO 4762) -- tagged ``validation_status
    ="reference_only"`` like the pre-existing Faz 2.4.1 records this
    reuses, or
  * a ratio-based engineering estimate (flange diameters, structural/
    stud/set-screw/shoulder/reduced-shank geometry) -- tagged
    ``validation_status="provisional"`` / ``verification_status
    ="unverified"`` / ``record_status="draft"`` per the phase brief's
    explicit instruction not to record estimates as certain data.

No standard's copyrighted dimensional table text is reproduced; only
derived/estimated numeric engineering values are stored, exactly as
the pre-existing Faz 2.4.1 bolt/nut records already do.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "library", "data")
BOLT_PATH = os.path.join(DATA_DIR, "bolt_library.json")
NUT_PATH = os.path.join(DATA_DIR, "nut_library.json")
THREAD_PATH = os.path.join(DATA_DIR, "thread_library.json")

PRIORITY_DIAMETERS = [3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 27, 30, 33, 36]
STRUCTURAL_DIAMETERS = [12, 16, 20, 24, 27, 30, 36]
NICHE_DIAMETERS = [8, 10, 12, 16, 20, 24]

# ISO 898-1 nominal mechanical property values (widely published,
# public-domain numeric reference values -- not standard table text).
BOLT_STRENGTH_DATA = {
    "8.8": {"rm": 800.0, "rp02": 640.0, "proof": 580.0, "elong": 12.0, "hardness": "255-335 HV"},
    "10.9": {"rm": 1040.0, "rp02": 940.0, "proof": 830.0, "elong": 9.0, "hardness": "320-380 HV"},
    "12.9": {"rm": 1220.0, "rp02": 1100.0, "proof": 970.0, "elong": 8.0, "hardness": "385-435 HV"},
}


def _load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _checksum(record: Dict[str, Any]) -> str:
    payload = {k: v for k, v in record.items() if k != "checksum"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _thread_lookup(thread_records: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    lookup = {}
    for rec in thread_records:
        if rec.get("thread_series") != "ISO_METRIC":
            continue
        key = (rec["nominal_diameter_mm"], rec.get("series"))
        lookup[key] = rec
    return lookup


def _existing_by_standard(
    bolt_records: List[Dict[str, Any]], standard: str
) -> Dict[float, Dict[str, Any]]:
    return {
        r["diameter_mm"]: r for r in bolt_records if r.get("source_standard") == standard
    }


def _base_provenance(
    *, source: str, confidence: int, validation_status: str, approval_status: str,
    notes: str, verified_fields: List[str], estimated_fields: List[str],
) -> Dict[str, Any]:
    return {
        "source_standard": source,
        "confidence": confidence,
        "notes": notes,
        "revision": "2026-07-20",
        "source": source,
        "version": "2.4.1B",
        "validation_status": validation_status,
        "approval_status": approval_status,
        "metadata": {
            "verified_fields": verified_fields,
            "estimated_fields": estimated_fields,
            "thread_geometry_source": "ISO 724 (see Thread Library)",
        },
    }


def _bolt_common_thread_fields(thread_rec: Dict[str, Any], fine_rec: Optional[Dict[str, Any]]):
    return {
        "pitch_coarse_mm": thread_rec["pitch_mm"],
        "pitch_fine_mm": fine_rec["pitch_mm"] if fine_rec else None,
        "stress_area_mm2": thread_rec["stress_area_mm2"],
        "minor_diameter_mm": thread_rec["minor_diameter_mm"],
        "pitch_diameter_mm": thread_rec["pitch_diameter_mm"],
    }


def make_reused_geometry_bolt(
    *, rid: str, diameter: int, thread_rec, fine_rec, template: Dict[str, Any],
    standard: str, standard_org: str, family: str, head_type: str, drive_type: str,
    property_class: str, thread_designation: str, confidence: int = 3,
) -> Dict[str, Any]:
    """Build a new bolt record reusing another standard's already-
    in-library head geometry (documented dimensional correspondence,
    e.g. ISO 4014<->ISO 4017 head table, DIN 912<->ISO 4762)."""
    strength = BOLT_STRENGTH_DATA[property_class]
    rec: Dict[str, Any] = _base_provenance(
        source=standard,
        confidence=confidence,
        validation_status="reference_only",
        approval_status="pending",
        notes=(
            f"{family} per {standard}. Head/body geometry reused from the "
            f"already-in-library equivalent standard's dimension table "
            f"(documented {standard} <-> equivalent-standard head-geometry "
            "correspondence) -- treat as reference_only and verify against "
            f"the full {standard} text before production use. Thread "
            "sub-fields are ISO 724, inherited from Thread Library."
        ),
        verified_fields=[],
        estimated_fields=[
            "head_height_mm", "socket_size_mm", "washer_face_diameter_mm",
            "bearing_diameter_mm", "recommended_hole_mm",
            "clearance_hole_medium_mm", "tap_drill_mm", "thread_engagement_mm",
            "weight_kg_per_100",
        ],
    )
    rec.update(
        id=rid,
        designation=thread_designation,
        thread=thread_designation,
        property_class=property_class,
        material=property_class,
        head_type=head_type,
        diameter_mm=diameter,
        head_across_flats_mm=template["head_across_flats_mm"],
        head_across_corners_mm=template["head_across_corners_mm"],
        head_height_mm=template["head_height_mm"],
        socket_size_mm=template.get("socket_size_mm"),
        washer_face_diameter_mm=template["washer_face_diameter_mm"],
        bearing_diameter_mm=template["bearing_diameter_mm"],
        recommended_hole_mm=template["recommended_hole_mm"],
        clearance_hole_medium_mm=template["clearance_hole_medium_mm"],
        tap_drill_mm=template["tap_drill_mm"],
        thread_engagement_mm=template["thread_engagement_mm"],
        weight_kg_per_100=template["weight_kg_per_100"],
        # -- Faz 2.4.1B structured fields --
        bolt_family=family,
        standard_organization=standard_org,
        nominal_diameter_mm=float(diameter),
        pitch_mm=thread_rec["pitch_mm"],
        coarse_or_fine="coarse",
        thread_tolerance_class="6g",
        nominal_length_mm=round(1.5 * diameter + 20, 1),
        threaded_length_mm=round(2.0 * diameter + 6, 1),
        drive_type=drive_type,
        wrench_size_mm=template["head_across_flats_mm"] if head_type != "Socket" else None,
        under_head_bearing_diameter_mm=template["bearing_diameter_mm"],
        reduced_shank_diameter_mm=None,
        heat_treatment="Quenched and tempered",
        coating_compatibility=["Plain", "Zinc flake", "Hot-dip galvanized", "Zinc-nickel"],
        lubrication_state="As supplied (unlubricated)",
        minimum_tensile_strength_mpa=strength["rm"],
        proof_strength_mpa=strength["proof"],
        yield_strength_mpa=strength["rp02"],
        elongation_percent=strength["elong"],
        hardness_range=strength["hardness"],
        operating_temperature_min_c=-50.0,
        operating_temperature_max_c=150.0 if property_class == "8.8" else 200.0,
        dimensional_tolerance_reference=f"{standard} product grade",
        verification_status="unverified",
        record_status="draft",
    )
    rec.update(_bolt_common_thread_fields(thread_rec, fine_rec))
    rec["checksum"] = _checksum(rec)
    return rec


def make_estimated_bolt(
    *, rid: str, diameter: int, thread_rec, fine_rec, standard: str, standard_org: str,
    family: str, head_type: str, drive_type: str, property_class: str,
    thread_designation: str, extra_notes: str = "",
) -> Dict[str, Any]:
    """Build a new bolt record for a family with no already-in-library
    geometry to reuse: dimensions are ratio-based engineering
    estimates, explicitly marked draft/unverified per the phase
    brief's instruction not to record estimates as certain data."""
    strength = BOLT_STRENGTH_DATA[property_class]
    across_flats = round(1.6 * diameter + 1.0, 2) if head_type != "Headless" else None
    across_corners = round(across_flats * 1.1547, 2) if across_flats else None
    head_height = round(0.65 * diameter, 2) if head_type != "Headless" else None
    rec: Dict[str, Any] = _base_provenance(
        source=standard,
        confidence=4,
        validation_status="provisional",
        approval_status="pending",
        notes=(
            f"{family} per {standard} (indicative only). All dimensional "
            "fields are ratio-based engineering estimates, NOT read from a "
            f"{standard} dimension table -- verify against the full "
            f"standard before production use. {extra_notes}"
        ).strip(),
        verified_fields=[],
        estimated_fields=[
            "head_across_flats_mm", "head_height_mm", "washer_face_diameter_mm",
            "bearing_diameter_mm", "tap_drill_mm", "weight_kg_per_100",
        ],
    )
    # Physically-derived estimate: weight_kg_per_100 = 100 x (steel
    # density 7.85 g/cm^3 = 7.85e-6 kg/mm^3) x (pi/4 x d^2 x length),
    # i.e. cylindrical-volume approximation x unit conversion x 100
    # pieces. Previous draft of this formula divided by 100 instead of
    # multiplying, which underflowed to 0.0 at small diameters (see
    # Faz 2.4.1B follow-up fix) -- corrected here and asserted >0
    # below so the same bug cannot silently reappear.
    length_mm = 1.5 * diameter + 20
    weight = round(6.1655e-4 * (diameter ** 2) * length_mm, 4)
    assert weight > 0, f"weight_kg_per_100 underflowed to 0 for diameter={diameter}"
    rec.update(
        id=rid,
        designation=thread_designation,
        thread=thread_designation,
        property_class=property_class,
        material=property_class,
        head_type=head_type,
        diameter_mm=diameter,
        head_across_flats_mm=across_flats,
        head_across_corners_mm=across_corners,
        head_height_mm=head_height,
        socket_size_mm=round(0.5 * diameter, 1) if head_type == "Socket" else None,
        washer_face_diameter_mm=across_flats,
        bearing_diameter_mm=across_flats,
        recommended_hole_mm=round(diameter + 1.0, 1),
        clearance_hole_medium_mm=round(diameter + 1.1, 1),
        tap_drill_mm=round(thread_rec["minor_diameter_mm"], 1),
        thread_engagement_mm=float(diameter),
        weight_kg_per_100=weight,
        bolt_family=family,
        standard_organization=standard_org,
        nominal_diameter_mm=float(diameter),
        pitch_mm=thread_rec["pitch_mm"],
        coarse_or_fine="coarse",
        thread_tolerance_class="6g",
        nominal_length_mm=round(1.5 * diameter + 20, 1),
        threaded_length_mm=round(2.0 * diameter + 6, 1),
        drive_type=drive_type,
        wrench_size_mm=across_flats,
        under_head_bearing_diameter_mm=across_flats,
        reduced_shank_diameter_mm=None,
        heat_treatment="Quenched and tempered",
        coating_compatibility=["Plain", "Zinc flake"],
        lubrication_state="As supplied (unlubricated)",
        minimum_tensile_strength_mpa=strength["rm"],
        proof_strength_mpa=strength["proof"],
        yield_strength_mpa=strength["rp02"],
        elongation_percent=strength["elong"],
        hardness_range=strength["hardness"],
        operating_temperature_min_c=-50.0,
        operating_temperature_max_c=150.0 if property_class == "8.8" else 200.0,
        dimensional_tolerance_reference=f"{standard} (indicative)",
        verification_status="unverified",
        record_status="draft",
    )
    rec.update(_bolt_common_thread_fields(thread_rec, fine_rec))
    rec["checksum"] = _checksum(rec)
    return rec


def _parse_thread_diameter_pitch(thread: str, thread_lookup: Dict[Any, Dict[str, Any]]):
    """Parse a legacy ``thread`` string ("M3" or "M3x0.45") into
    ``(nominal_diameter_mm, pitch_mm, coarse_or_fine)`` using the live
    Thread Library as the source of truth for pitch values."""
    if "x" in thread.lower():
        dia_str, pitch_str = thread.lower().split("x", 1)
        diameter = float(dia_str[1:])
        pitch = float(pitch_str)
        fine_rec = thread_lookup.get((diameter, "Fine"))
        is_fine = fine_rec is not None and fine_rec["pitch_mm"] == pitch
        series = "Fine" if is_fine else "Coarse"
        return diameter, pitch, ("fine" if series == "Fine" else "coarse")
    diameter = float(thread[1:])
    coarse = thread_lookup.get((diameter, "Coarse"))
    pitch = coarse["pitch_mm"] if coarse else None
    return diameter, pitch, "coarse"


def backfill_legacy_bolt_records(
    records: List[Dict[str, Any]], thread_lookup: Dict[Any, Dict[str, Any]],
) -> int:
    """Fill in the Faz 2.4.1B structured fields on every pre-existing
    (``version == "2.4.1"``) bolt record, in place. Purely a function
    of each record's own pre-existing core fields (``diameter_mm``,
    ``property_class``, ``source_standard``, ...), so re-running this
    on an unchanged input always recomputes the same values and the
    same checksum (idempotent). Does not touch ``id``, core Faz 2.4.1
    fields, or any record whose ``version`` isn't exactly "2.4.1"."""
    family_by_standard = {
        "ISO 4017": ("Hexagon head screw", "ISO", "Hex (external)"),
        "ISO 4762": ("Socket head cap screw", "ISO", "Hex socket (internal)"),
    }
    updated = 0
    for record in records:
        is_legacy = record.get("version") == "2.4.1"
        std = record.get("source_standard")
        if not is_legacy or std not in family_by_standard:
            continue
        family, org, drive = family_by_standard[std]
        diameter = record["diameter_mm"]
        strength = BOLT_STRENGTH_DATA.get(record["property_class"], BOLT_STRENGTH_DATA["8.8"])
        record.update(
            bolt_family=family,
            standard_organization=org,
            nominal_diameter_mm=float(diameter),
            pitch_mm=record.get("pitch_coarse_mm"),
            coarse_or_fine="coarse",
            thread_tolerance_class="6g",
            nominal_length_mm=round(1.5 * diameter + 20, 1),
            threaded_length_mm=round(2.0 * diameter + 6, 1),
            drive_type=drive,
            wrench_size_mm=record.get("head_across_flats_mm"),
            under_head_bearing_diameter_mm=record.get("bearing_diameter_mm"),
            reduced_shank_diameter_mm=None,
            heat_treatment="Quenched and tempered",
            coating_compatibility=["Plain", "Zinc flake", "Hot-dip galvanized", "Zinc-nickel"],
            lubrication_state="As supplied (unlubricated)",
            minimum_tensile_strength_mpa=strength["rm"],
            proof_strength_mpa=strength["proof"],
            yield_strength_mpa=strength["rp02"],
            elongation_percent=strength["elong"],
            hardness_range=strength["hardness"],
            operating_temperature_min_c=-50.0,
            operating_temperature_max_c=150.0 if record["property_class"] == "8.8" else 200.0,
            dimensional_tolerance_reference=f"{record['source_standard']} product grade",
            verification_status=(
                "verified" if record.get("validation_status") == "validated" else "unverified"
            ),
            record_status="approved" if record.get("approval_status") == "approved" else "draft",
        )
        record["checksum"] = _checksum(record)
        updated += 1
    return updated


def backfill_legacy_nut_records(
    records: List[Dict[str, Any]], thread_lookup: Dict[Any, Dict[str, Any]],
) -> int:
    """Nut counterpart of :func:`backfill_legacy_bolt_records` -- see
    that function's docstring for the idempotency argument, which
    applies identically here."""
    family_by_standard = {
        "ISO 4032": ("Hexagon nut", "None", None, None),
        "ISO 4033": ("High nut", "None", None, None),
        "ISO 8673": ("Hexagon nut", "None", None, None),
        "ISO 7040": (
            "Nylon insert lock nut", "Nylon insert prevailing torque",
            "Standard type, reusable a limited number of cycles", True,
        ),
        "ISO 10511": (
            "Prevailing torque nut", "Nylon insert prevailing torque",
            "Low type, reusable a limited number of cycles", True,
        ),
    }
    updated = 0
    for record in records:
        is_legacy = record.get("version") == "2.4.1"
        std = record.get("source_standard")
        if not is_legacy or std not in family_by_standard:
            continue
        family, locking_principle, torque_category, reusable = family_by_standard[std]
        diameter, pitch, coarse_or_fine = _parse_thread_diameter_pitch(
            record["thread"], thread_lookup,
        )
        proof_stress = NUT_PROOF_STRESS_MPA.get(record["property_class"], 800.0)
        stress_key = (diameter, "Fine" if coarse_or_fine == "fine" else "Coarse")
        stress_rec = thread_lookup.get(stress_key)
        proof_load = round(proof_stress * stress_rec["stress_area_mm2"], 1) if stress_rec else None
        across_flats = record.get("width_across_flats_mm")
        record.update(
            nut_family=family,
            standard_organization="ISO",
            nominal_diameter_mm=diameter,
            pitch_mm=pitch,
            coarse_or_fine=coarse_or_fine,
            thread_tolerance_class="6H",
            width_across_corners_mm=round(across_flats * 1.1547, 2) if across_flats else None,
            flange_diameter_mm=None,
            bearing_surface_diameter_mm=across_flats,
            proof_load_n=proof_load,
            hardness_range="170-302 HV",
            heat_treatment="As rolled/hardened",
            coating_compatibility=["Plain", "Zinc flake", "Hot-dip galvanized", "Zinc-nickel"],
            lubrication_state="As supplied (unlubricated)",
            prevailing_torque_category=torque_category or "",
            locking_principle=(
                locking_principle
                if locking_principle and record.get("locking_type", "None") != "None"
                else ""
            ),
            reusable=reusable if record.get("locking_type", "None") != "None" else None,
            operating_temperature_min_c=-50.0,
            operating_temperature_max_c=150.0,
            mating_bolt_requirements="Bolt property class <= 8.8 recommended",
            dimensional_tolerance_reference=f"{record['source_standard']} (indicative)",
            verification_status=(
                "verified" if record.get("validation_status") == "validated" else "unverified"
            ),
            record_status="approved" if record.get("approval_status") == "approved" else "draft",
        )
        record["checksum"] = _checksum(record)
        updated += 1
    return updated


def build_bolt_records(
    thread_lookup: Dict[Any, Dict[str, Any]], existing_bolts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    hex_template = _existing_by_standard(existing_bolts, "ISO 4017")
    socket_template = _existing_by_standard(existing_bolts, "ISO 4762")
    new_records: List[Dict[str, Any]] = []

    for d in PRIORITY_DIAMETERS:
        coarse = thread_lookup[(d, "Coarse")]
        fine = thread_lookup.get((d, "Fine"))

        new_records.append(make_reused_geometry_bolt(
            rid=f"BOLT-ISO4014-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            template=hex_template[d], standard="ISO 4014", standard_org="ISO",
            family="Hexagon head bolt", head_type="Hex", drive_type="Hex (external)",
            property_class="8.8", thread_designation=f"M{d:g}",
        ))
        new_records.append(make_reused_geometry_bolt(
            rid=f"BOLT-DIN931-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            template=hex_template[d], standard="DIN 931", standard_org="DIN",
            family="Hexagon head bolt", head_type="Hex", drive_type="Hex (external)",
            property_class="8.8", thread_designation=f"M{d:g}",
        ))
        new_records.append(make_reused_geometry_bolt(
            rid=f"BOLT-DIN933-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            template=hex_template[d], standard="DIN 933", standard_org="DIN",
            family="Hexagon head screw", head_type="Hex", drive_type="Hex (external)",
            property_class="8.8", thread_designation=f"M{d:g}",
        ))
        new_records.append(make_reused_geometry_bolt(
            rid=f"BOLT-DIN912-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            template=socket_template[d], standard="DIN 912", standard_org="DIN",
            family="Socket head cap screw", head_type="Socket",
            drive_type="Hex socket (internal)", property_class="8.8",
            thread_designation=f"M{d:g}",
        ))
        new_records.append(make_estimated_bolt(
            rid=f"BOLT-ISO4162-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            standard="ISO 4162", standard_org="ISO", family="Flange bolt",
            head_type="Flange", drive_type="Hex (external)", property_class="8.8",
            thread_designation=f"M{d:g}",
            extra_notes="Flange diameter estimated as ~1.9x the equivalent hex across-flats.",
        ))

    for d in STRUCTURAL_DIAMETERS:
        coarse = thread_lookup[(d, "Coarse")]
        fine = thread_lookup.get((d, "Fine"))
        new_records.append(make_reused_geometry_bolt(
            rid=f"BOLT-EN14399-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            template=hex_template[d], standard="EN 14399-3", standard_org="EN",
            family="Structural bolt", head_type="Hex", drive_type="Hex (external)",
            property_class="10.9", thread_designation=f"M{d:g}", confidence=3,
        ))

    for d in NICHE_DIAMETERS:
        coarse = thread_lookup[(d, "Coarse")]
        fine = thread_lookup.get((d, "Fine"))
        new_records.append(make_estimated_bolt(
            rid=f"BOLT-STUD-ISO898-1-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            standard="ISO 898-1", standard_org="ISO", family="Stud bolt",
            head_type="Headless", drive_type="", property_class="8.8",
            thread_designation=f"M{d:g}",
            extra_notes="Double-end stud; length pair is representative only.",
        ))
        new_records.append(make_estimated_bolt(
            rid=f"BOLT-SETSCREW-ISO4026-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            standard="ISO 4026", standard_org="ISO", family="Set screw",
            head_type="Headless", drive_type="Hex socket (internal)",
            property_class="8.8", thread_designation=f"M{d:g}",
            extra_notes="Flat-point hex socket set screw; no head geometry (headless).",
        ))
        rec = make_estimated_bolt(
            rid=f"BOLT-SHOULDER-ISO7379-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            standard="ISO 7379", standard_org="ISO", family="Shoulder bolt",
            head_type="Socket", drive_type="Hex socket (internal)",
            property_class="8.8", thread_designation=f"M{d:g}",
            extra_notes=(
                "Shoulder (precision) diameter is larger than the thread "
                "nominal diameter per ISO 7379 -- stored in metadata."
            ),
        )
        rec["metadata"]["shoulder_diameter_mm_estimated"] = round(d + 2.0, 1)
        rec["checksum"] = _checksum({k: v for k, v in rec.items() if k != "checksum"})
        new_records.append(rec)
        new_records.append(make_estimated_bolt(
            rid=f"BOLT-REDUCEDSHANK-M{d:g}", diameter=d, thread_rec=coarse, fine_rec=fine,
            standard="DIN 7968", standard_org="DIN", family="Reduced shank bolt",
            head_type="Hex", drive_type="Hex (external)", property_class="8.8",
            thread_designation=f"M{d:g}",
            extra_notes=(
                "reduced_shank_diameter_mm approximated as the ISO 724 "
                "pitch diameter (fitted-bolt convention)."
            ),
        ))
        new_records[-1]["reduced_shank_diameter_mm"] = coarse["pitch_diameter_mm"]
        new_records[-1]["checksum"] = _checksum(
            {k: v for k, v in new_records[-1].items() if k != "checksum"}
        )
        if fine is not None:
            new_records.append(make_estimated_bolt(
                rid=f"BOLT-FINE-ISO4017-M{d:g}", diameter=d, thread_rec=fine, fine_rec=fine,
                standard="ISO 4017", standard_org="ISO",
                family="Hexagon head screw (fine thread)", head_type="Hex",
                drive_type="Hex (external)", property_class="8.8",
                thread_designation=fine["designation"],
                extra_notes="Fine-pitch variant; head geometry ratio-estimated from hex family.",
            ))
            new_records[-1]["coarse_or_fine"] = "fine"
            new_records[-1]["checksum"] = _checksum(
                {k: v for k, v in new_records[-1].items() if k != "checksum"}
            )

    return new_records


# ---------------------------------------------------------------------
# Nuts
# ---------------------------------------------------------------------

NUT_PROOF_STRESS_MPA = {"8": 800.0, "9": 900.0, "10": 1040.0, "12": 1220.0}


def make_nut_record(
    *, rid: str, diameter: int, thread_rec, standard: str, standard_org: str,
    family: str, property_class: str, height_ratio: float, locking_type: str,
    locking_principle: str, prevailing_torque_category: str, reusable: Optional[bool],
    flange: bool, extra_notes: str = "", confidence: int = 4,
    validation_status: str = "provisional", thread_designation: Optional[str] = None,
) -> Dict[str, Any]:
    across_flats = round(1.6 * diameter + 1.0, 2)
    height = round(height_ratio * diameter, 2)
    proof_stress = NUT_PROOF_STRESS_MPA.get(property_class, 800.0)
    stress_area = thread_rec["stress_area_mm2"]
    rec: Dict[str, Any] = {
        "id": rid,
        "source_standard": standard,
        "confidence": confidence,
        "notes": (
            f"{family} per {standard}. height_mm and flange/bearing "
            "dimensions are ratio-based engineering estimates -- verify "
            f"against the full {standard} table before production use. "
            f"{extra_notes}"
        ).strip(),
        "revision": "2026-07-20",
        "source": standard,
        "version": "2.4.1B",
        "validation_status": validation_status,
        "approval_status": "pending",
        "metadata": {
            "verified_fields": [],
            "estimated_fields": ["height_mm", "width_across_flats_mm"],
        },
        "designation": f"{standard} M{diameter:g}",
        "thread": thread_designation or f"M{diameter:g}",
        "property_class": property_class,
        "height_mm": height,
        "width_across_flats_mm": across_flats,
        "flange": flange,
        "locking_type": locking_type,
        "bearing_face": "Flat, chamfered" if not flange else "Flange bearing surface",
        "strength_compatibility": ["4.6", "4.8", "5.6", "5.8", "6.8", "8.8"],
        # -- Faz 2.4.1B structured fields --
        "nut_family": family,
        "standard_organization": standard_org,
        "nominal_diameter_mm": float(diameter),
        "pitch_mm": thread_rec["pitch_mm"],
        "coarse_or_fine": "coarse",
        "thread_tolerance_class": "6H",
        "width_across_corners_mm": round(across_flats * 1.1547, 2),
        "flange_diameter_mm": round(across_flats * 1.9, 2) if flange else None,
        "bearing_surface_diameter_mm": round(across_flats * 1.9, 2) if flange else across_flats,
        "proof_load_n": round(proof_stress * stress_area, 1),
        "hardness_range": "170-302 HV" if property_class in ("8", "9") else "272-353 HV",
        "heat_treatment": (
            "Quenched and tempered" if property_class in ("10", "12")
            else "As rolled/hardened"
        ),
        "coating_compatibility": ["Plain", "Zinc flake", "Hot-dip galvanized", "Zinc-nickel"],
        "lubrication_state": "As supplied (unlubricated)",
        "prevailing_torque_category": prevailing_torque_category,
        "locking_principle": locking_principle,
        "reusable": reusable,
        "operating_temperature_min_c": -50.0,
        "operating_temperature_max_c": 150.0 if property_class in ("8", "9") else 200.0,
        "mating_bolt_requirements": f"Bolt property class <= {property_class}.8 recommended",
        "dimensional_tolerance_reference": f"{standard} (indicative)",
        "verification_status": "unverified",
        "record_status": "draft",
    }
    rec["checksum"] = _checksum(rec)
    return rec


def build_nut_records(thread_lookup: Dict[Any, Dict[str, Any]]) -> List[Dict[str, Any]]:
    new_records: List[Dict[str, Any]] = []

    for d in PRIORITY_DIAMETERS:
        coarse = thread_lookup[(d, "Coarse")]
        new_records.append(make_nut_record(
            rid=f"NUT-ISO4035-M{d:g}", diameter=d, thread_rec=coarse,
            standard="ISO 4035", standard_org="ISO", family="Thin nut",
            property_class="8", height_ratio=0.5, locking_type="None",
            locking_principle="", prevailing_torque_category="", reusable=None,
            flange=False,
        ))
        new_records.append(make_nut_record(
            rid=f"NUT-ISO4161-M{d:g}", diameter=d, thread_rec=coarse,
            standard="ISO 4161", standard_org="ISO", family="Flange nut",
            property_class="8", height_ratio=0.9, locking_type="None",
            locking_principle="", prevailing_torque_category="", reusable=None,
            flange=True,
        ))
        new_records.append(make_nut_record(
            rid=f"NUT-ISO7042-M{d:g}", diameter=d, thread_rec=coarse,
            standard="ISO 7042", standard_org="ISO", family="All-metal lock nut",
            property_class="8", height_ratio=0.9, locking_type="All-metal (deformed thread)",
            locking_principle="All-metal (deformed thread) prevailing torque",
            prevailing_torque_category="High temperature capable", reusable=False,
            flange=False, confidence=3,
        ))

    for d in STRUCTURAL_DIAMETERS:
        coarse = thread_lookup[(d, "Coarse")]
        new_records.append(make_nut_record(
            rid=f"NUT-EN14399-M{d:g}", diameter=d, thread_rec=coarse,
            standard="EN 14399-4", standard_org="EN", family="Structural nut",
            property_class="10", height_ratio=0.9, locking_type="None",
            locking_principle="", prevailing_torque_category="", reusable=None,
            flange=False, confidence=3,
        ))

    for d in NICHE_DIAMETERS:
        coarse = thread_lookup[(d, "Coarse")]
        new_records.append(make_nut_record(
            rid=f"NUT-WELD-DIN929-M{d:g}", diameter=d, thread_rec=coarse,
            standard="DIN 929", standard_org="DIN", family="Weld nut",
            property_class="8", height_ratio=0.8, locking_type="None",
            locking_principle="", prevailing_torque_category="", reusable=None,
            flange=False,
            extra_notes="Pilot/projection weld nut; welding projections not modelled.",
        ))
        new_records.append(make_nut_record(
            rid=f"NUT-SQUARE-DIN557-M{d:g}", diameter=d, thread_rec=coarse,
            standard="DIN 557", standard_org="DIN", family="Square nut",
            property_class="8", height_ratio=1.0, locking_type="None",
            locking_principle="", prevailing_torque_category="", reusable=None,
            flange=False,
        ))
        new_records.append(make_nut_record(
            rid=f"NUT-CAP-DIN1587-M{d:g}", diameter=d, thread_rec=coarse,
            standard="DIN 1587", standard_org="DIN", family="Cap nut",
            property_class="8", height_ratio=1.6, locking_type="None",
            locking_principle="", prevailing_torque_category="", reusable=None,
            flange=False, extra_notes="Domed cap (acorn) nut; blind-hole depth not modelled.",
        ))

    return new_records


def _strip_previous_generation(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove any record this script generated on a prior run
    (tagged ``version == "2.4.1B"``), leaving every pre-existing
    Faz 2.4.1 record -- including any that a person has since hand-
    edited -- untouched. This is what makes ``main()`` idempotent:
    re-running the script always yields the same appended record set
    (same ids, same field values, same checksums) instead of
    duplicating or double-appending on a second run.
    """
    return [r for r in records if r.get("version") != "2.4.1B"]


def main() -> None:
    thread_payload = _load(THREAD_PATH)
    thread_lookup = _thread_lookup(thread_payload["records"])

    bolt_payload = _load(BOLT_PATH)
    n_backfilled_bolts = backfill_legacy_bolt_records(bolt_payload["records"], thread_lookup)
    bolt_payload["records"] = _strip_previous_generation(bolt_payload["records"])
    existing_bolt_ids = {r["id"] for r in bolt_payload["records"]}
    new_bolts = build_bolt_records(thread_lookup, bolt_payload["records"])
    assert len(new_bolts) == len({r["id"] for r in new_bolts}), "duplicate generated bolt id"
    bolt_collision = existing_bolt_ids & {r["id"] for r in new_bolts}
    assert not bolt_collision, "id collision with existing bolts"
    bolt_payload["records"].extend(new_bolts)
    bolt_payload["metadata"]["version"] = "2.4.1B"
    if "Faz 2.4.1B" not in bolt_payload["metadata"]["description"]:
        bolt_payload["metadata"]["description"] = (
            bolt_payload["metadata"]["description"]
            + " Extended in Faz 2.4.1B with ISO 4014/4162, DIN 931/933/912, "
            "EN 14399-3, and stud/set-screw/shoulder/reduced-shank/fine-thread "
            "families."
        )
    _save(BOLT_PATH, bolt_payload)

    nut_payload = _load(NUT_PATH)
    n_backfilled_nuts = backfill_legacy_nut_records(nut_payload["records"], thread_lookup)
    nut_payload["records"] = _strip_previous_generation(nut_payload["records"])
    existing_nut_ids = {r["id"] for r in nut_payload["records"]}
    new_nuts = build_nut_records(thread_lookup)
    assert len(new_nuts) == len({r["id"] for r in new_nuts}), "duplicate generated nut id"
    assert not (existing_nut_ids & {r["id"] for r in new_nuts}), "id collision with existing nuts"
    nut_payload["records"].extend(new_nuts)
    nut_payload["metadata"]["version"] = "2.4.1B"
    if "Faz 2.4.1B" not in nut_payload["metadata"].get("description", ""):
        nut_payload["metadata"]["description"] = (
            nut_payload["metadata"].get("description", "")
            + " Extended in Faz 2.4.1B with ISO 4035/4161/7042, EN 14399-4, "
            "DIN 929/557/1587 families."
        )
    _save(NUT_PATH, nut_payload)

    bolt_total = len(bolt_payload["records"])
    nut_total = len(nut_payload["records"])
    print(
        f"bolts: backfilled {n_backfilled_bolts} legacy, "
        f"+{len(new_bolts)} new -> {bolt_total} total"
    )
    print(
        f"nuts:  backfilled {n_backfilled_nuts} legacy, "
        f"+{len(new_nuts)} new -> {nut_total} total"
    )


if __name__ == "__main__":
    main()
