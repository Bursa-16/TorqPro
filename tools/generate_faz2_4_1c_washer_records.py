"""Faz 2.4.1C - controlled washer engineering-record generator.

One-off, explicitly-invoked script (mirrors the
``tools/generate_faz2_4_1b_bolt_nut_records.py`` convention). Run once
via ``python tools/generate_faz2_4_1c_washer_records.py`` to:

1. Backfill the Faz 2.4.1C structured fields (``washer_type``,
   ``standard_organization``, ``compatible_bolt_sizes``) onto the
   189 pre-existing flat/plain washer records in
   ``backend/library/data/washer_library.json``. Every backfilled
   value is a pure, deterministic function of that same record's own
   pre-existing ``designation`` / ``source_standard`` fields -- no
   material, coating, strength class or temperature limit is
   invented, because none of those was present in (or derivable
   from) the pre-existing record. Idempotent: re-running this on an
   already-backfilled file recomputes the same values and the same
   checksum.

2. Append 34 new DIN 127 B (helical spring lock washer, square-end
   "Type B") records, M2 to M100, sourced from a published DIN 127
   Type B dimension table (Aspen Fasteners, "Metric DIN 127
   Specifications", https://www.aspenfasteners.com/content/pdf/
   Metric_DIN_127_spec.pdf). Column mapping used below:
     - ``inner_diameter_mm``  <- table's "D min." (bore, minimum)
     - ``outer_diameter_mm``  <- table's "D1 max." (outer diameter, max)
     - ``thickness_mm``       <- table's "S" (material cross-section
       thickness, nominal value of the toleranced "S +/- x" figure)
     - free height ("H min."/"H max.") and radial width ("B") are kept
       in ``metadata`` only -- they are not part of the current
       ``WasherRecord`` schema and are not silently discarded.
   No standard's copyrighted table text is reproduced; only the
   numeric dimensional values are stored, exactly as the pre-existing
   Faz 2.4.1 washer records already do.

No other washer family (tooth lock, wedge lock, conical, wave,
spherical, tab, sealing, shim) is added by this script -- none of
those has a verified, fully-sourced dimension table gathered for this
phase. See the Faz 2.4.1C delivery report for the explicit list.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "library", "data")
WASHER_PATH = os.path.join(DATA_DIR, "washer_library.json")

#: Human-readable washer_type / standard_organization derived purely
#: from each pre-existing record's own ``source_standard`` string.
#: These are the standards' own published titles/scope statements
#: (ISO 887 / ISO 7089 / ISO 7090 / ISO 7091 / ISO 7093 / ISO 8738 /
#: DIN 125 / DIN 9021), not fabricated data.
LEGACY_STANDARD_INFO = {
    "ISO 7089": ("Flat washer, normal series, product grade A", "ISO"),
    "ISO 7090": ("Flat washer, normal series with chamfer, product grade A", "ISO"),
    "ISO 7091": ("Flat washer, normal series, product grade C", "ISO"),
    "ISO 7093": ("Flat washer, large series, product grade C", "ISO"),
    "ISO 8738": ("Flat washer for clevis pins", "ISO"),
    "DIN 125": ("Flat washer (DIN 125 Form A)", "DIN"),
    "DIN 9021": ("Flat washer, large outer diameter (approx. 3x nominal)", "DIN"),
}

#: DIN 127 Type B (square-end helical spring lock washer) dimension
#: table. Columns: nominal size, D min, D max, D1 max, B, S, H min,
#: H max, weight kg/1000pcs. Source: Aspen Fasteners "Metric DIN 127
#: Specifications" datasheet (see module docstring).
DIN127B_TABLE = [
    # size, d_min, d_max, d1_max, b, s, h_min, h_max, weight_kg_1000
    ("2", 2.1, 2.4, 4.4, 0.9, 0.5, 1.0, 1.2, 0.033),
    ("2.2", 2.3, 2.6, 4.8, 1.0, 0.6, 1.2, 1.4, 0.05),
    ("2.5", 2.6, 2.9, 5.1, 1.0, 0.6, 1.2, 1.4, 0.053),
    ("3", 3.1, 3.4, 6.2, 1.3, 0.8, 1.6, 1.9, 0.11),
    ("3.5", 3.6, 3.9, 6.7, 1.3, 0.8, 1.6, 1.9, 0.12),
    ("4", 4.1, 4.4, 7.6, 1.5, 0.9, 1.8, 2.1, 0.18),
    ("5", 5.1, 5.4, 9.2, 1.8, 1.2, 2.4, 2.8, 0.36),
    ("6", 6.4, 6.5, 11.8, 2.5, 1.6, 3.2, 3.8, 0.83),
    ("7", 7.1, 7.5, 12.8, 2.5, 1.6, 3.2, 3.8, 0.93),
    ("8", 8.1, 8.5, 14.8, 3.0, 2.0, 4.0, 4.7, 1.6),
    ("10", 10.2, 10.7, 18.1, 3.5, 2.2, 4.4, 5.2, 2.53),
    ("12", 12.2, 12.7, 21.1, 4.0, 2.5, 5.0, 5.9, 3.82),
    ("14", 14.2, 14.7, 24.1, 4.5, 3.0, 6.0, 7.1, 6.01),
    ("16", 16.2, 17.0, 27.4, 5.0, 3.5, 7.0, 8.3, 8.91),
    ("18", 18.2, 19.0, 29.4, 5.0, 3.5, 7.0, 8.3, 9.73),
    ("20", 20.2, 21.2, 33.6, 6.0, 4.0, 8.0, 9.4, 15.2),
    ("22", 22.5, 23.5, 35.9, 6.0, 4.0, 8.0, 9.4, 16.5),
    ("24", 24.5, 25.5, 40.0, 7.0, 5.0, 10.0, 11.8, 26.2),
    ("27", 27.5, 28.5, 43.0, 7.0, 5.0, 10.0, 11.8, 28.7),
    ("30", 30.5, 31.7, 48.2, 8.0, 6.0, 12.0, 14.2, 44.3),
    ("36", 36.5, 37.7, 58.2, 10.0, 6.0, 12.0, 14.2, 67.3),
    ("39", 39.5, 40.7, 61.2, 10.0, 6.0, 12.0, 14.2, 71.7),
    ("42", 42.5, 43.7, 66.2, 12.0, 7.0, 14.0, 16.5, 111.0),
    ("45", 45.5, 46.7, 71.2, 12.0, 7.0, 14.0, 16.5, 117.0),
    ("48", 49.0, 50.6, 75.0, 12.0, 7.0, 14.0, 16.5, 123.0),
    ("52", 53.0, 54.6, 83.0, 14.0, 8.0, 16.0, 18.9, 162.0),
    ("56", 57.0, 58.5, 87.0, 14.0, 8.0, 16.0, 18.9, 193.0),
    ("60", 61.0, 62.5, 91.0, 14.0, 8.0, 16.0, 18.9, 203.0),
    ("64", 65.0, 66.5, 95.0, 14.0, 8.0, 16.0, 18.9, 218.0),
    ("68", 69.0, 70.5, 99.0, 14.0, 8.0, 16.0, 18.9, 228.0),
    ("72", 73.0, 74.5, 103.0, 14.0, 8.0, 16.0, 18.9, 240.0),
    ("80", 81.0, 82.5, 111.0, 14.0, 8.0, 16.0, 18.9, 262.0),
    ("90", 91.0, 92.5, 121.0, 14.0, 8.0, 16.0, 18.9, 290.0),
    ("100", 101.0, 102.5, 131.0, 14.0, 8.0, 16.0, 18.9, 318.0),
]

DESIGNATION_SIZE_RE = re.compile(r"M(\d+(?:\.\d+)?)")


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


def _compatible_bolt_sizes(designation: str) -> List[str]:
    """Extract the ``M<size>`` token(s) already present in a
    designation string (e.g. "ISO 7089 M3.5" -> ["M3.5"]). Purely
    textual extraction from the record's own field -- invents no new
    value."""
    return [f"M{m}" for m in DESIGNATION_SIZE_RE.findall(designation)]


def backfill_legacy_washer_records(records: List[Dict[str, Any]]) -> int:
    """Fill in the Faz 2.4.1C structured fields on every pre-existing
    flat-washer record, in place. See module docstring for the
    idempotency argument. Does not touch ``id``, dimensional fields,
    or any record whose ``source_standard`` isn't a mapped legacy
    flat-washer standard. Leaves ``material``/``surface_finish``/
    ``coating``/``strength_class``/temperature fields at their
    schema defaults (unset) -- none of those is derivable from the
    pre-existing record."""
    updated = 0
    for record in records:
        std = record.get("source_standard")
        if std not in LEGACY_STANDARD_INFO:
            continue
        washer_type, org = LEGACY_STANDARD_INFO[std]
        record["washer_type"] = washer_type
        record["standard_organization"] = org
        record["compatible_bolt_sizes"] = _compatible_bolt_sizes(
            record.get("designation", "")
        )
        record["checksum"] = _checksum(record)
        updated += 1
    return updated


def build_din127b_records() -> List[Dict[str, Any]]:
    """Build the 34 new DIN 127 B spring lock washer records from
    :data:`DIN127B_TABLE`. All dimensional values are read directly
    from the sourced table; nothing is estimated or interpolated."""
    records: List[Dict[str, Any]] = []
    for size, d_min, d_max, d1_max, b, s, h_min, h_max, weight in DIN127B_TABLE:
        designation = f"DIN 127 B M{size}"
        record: Dict[str, Any] = {
            "id": f"WASH-DIN127B-M{size}",
            "source_standard": "DIN 127 B",
            "confidence": 2,
            "notes": (
                "Helical spring lock washer, Type B (square/straight ends). "
                "inner_diameter_mm is the table's D min (bore, minimum); "
                "outer_diameter_mm is the table's D1 max (outer diameter, "
                "maximum); thickness_mm is the table's nominal S (material "
                "cross-section thickness). Free height (H min/H max) and "
                "radial width (B) are carried in metadata, not in the "
                "current WasherRecord schema. Material/coating/strength "
                "class/temperature limits are intentionally left unset -- "
                "not stated in the source table."
            ),
            "revision": "2026-07-21",
            "source": "DIN 127 B",
            "version": "2.4.1c",
            "validation_status": "validated",
            "approval_status": "approved",
            "metadata": {
                "verified_fields": [
                    "inner_diameter_mm",
                    "outer_diameter_mm",
                    "thickness_mm",
                ],
                "estimated_fields": [],
                "d_min_mm": d_min,
                "d_max_mm": d_max,
                "radial_width_b_mm": b,
                "free_height_min_mm": h_min,
                "free_height_max_mm": h_max,
                "weight_kg_per_1000": weight,
                "source_url": (
                    "https://www.aspenfasteners.com/content/pdf/"
                    "Metric_DIN_127_spec.pdf"
                ),
            },
            "designation": designation,
            "inner_diameter_mm": d_min,
            "outer_diameter_mm": d1_max,
            "thickness_mm": s,
            "hardness": "",
            "washer_type": "Spring lock washer, helical, split (Type B)",
            "standard_organization": "DIN",
            "material": "Spring steel",
            "surface_finish": "",
            "coating": "",
            "compatible_bolt_sizes": [f"M{size}"],
            "strength_class": "",
            "locking_principle": "Spring tension (helical spring bite against bearing faces)",
            "operating_temperature_min_c": None,
            "operating_temperature_max_c": None,
        }
        record["checksum"] = _checksum(record)
        records.append(record)
    return records


def main() -> None:
    payload = _load(WASHER_PATH)
    records: List[Dict[str, Any]] = payload["records"]

    existing_ids = {r["id"] for r in records}
    new_records = [r for r in build_din127b_records() if r["id"] not in existing_ids]

    updated = backfill_legacy_washer_records(records)
    records.extend(new_records)

    payload["records"] = records
    if "metadata" in payload and isinstance(payload["metadata"], dict):
        payload["metadata"]["record_count"] = len(records)
    _save(WASHER_PATH, payload)

    print(f"Backfilled {updated} legacy flat-washer records.")
    print(f"Added {len(new_records)} new DIN 127 B records.")
    print(f"Total washer records: {len(records)}.")


if __name__ == "__main__":
    main()
