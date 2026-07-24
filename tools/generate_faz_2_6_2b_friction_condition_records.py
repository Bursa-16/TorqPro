"""Faz 2.6.2B generator: verified Friction Condition data population.

Populates ``friction_condition_library.json`` using ONLY data that is
already sourced and approved elsewhere in the repository:

- The 10 live ``CoatingRecord``s' ``friction_coefficient_range``
  (Faz 2.4.1/2.4.2B, source "ISO 16047 / ISO 4042", typical range).
- The 8 original (non-Tablo-9.4) live ``LubricationRecord``s'
  ``friction_coefficient_min/max`` (Faz 2.4.0, source "ISO 16047",
  typical range).

No new coefficient is invented, derived, split or estimated. Each
output record is a deterministic 1:1 re-homing of an already-approved
value into its ADR-0010 combination-owner location
(``FrictionConditionRecord``), carrying the exact same numeric bounds
and source citation as the origin record.

Explicitly NOT migrated in this phase (see
docs/adr/ADR-0010-coating-lubrication-friction-data-ownership.md and
docs/phases/PHASE_2.6.2B_VERIFIED_FRICTION_DATA_POPULATION.md
"Blocked/deferred"):

- The 15 Tablo 9.4 (``LUBE-SURF-*``) records: no deterministic,
  unambiguous ``lubricant_id`` mapping exists (a "Dry"/"Oiled"/
  "MoS2-with-oil" *state* is not the same thing as a specific
  lubricant *product* id, and the Faz 2.6.2B directive explicitly
  defaults to NOT mapping when this distinction is uncertain).
- Any of the 19 originally-requested lubricants with no cited source
  at all (Geomet/Dacromet/PTFE/etc. beyond what already exists on
  ``CoatingRecord``, and any independent mu_thread/mu_bearing/K/
  scatter/max-temperature/corrosion/reusability value for any
  product) -- see the phase document's source coverage matrix.

Idempotent: re-running replaces any previously-generated
``FC-COAT-*``/``FC-LUBE-*`` records with freshly recomputed ones
(same deterministic inputs -> byte-identical output), never
duplicates them, and never touches any other record in the file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COATING_PATH = REPO_ROOT / "backend" / "library" / "data" / "coating_library.json"
LUBRICATION_PATH = REPO_ROOT / "backend" / "library" / "data" / "lubrication_library.json"
FRICTION_CONDITION_PATH = (
    REPO_ROOT / "backend" / "library" / "data" / "friction_condition_library.json"
)

GENERATED_DATE = "2026-07-23"


def _parse_range(range_str: str) -> tuple[float, float]:
    """Parse a "<min>-<max>" range string (as used verbatim by
    ``CoatingRecord.friction_coefficient_range``) into a
    ``(min, max)`` float tuple. Raises ``ValueError`` on anything that
    doesn't match -- deliberately strict: an unparseable range must
    stop generation, not silently produce a wrong/guessed value."""
    parts = range_str.split("-")
    if len(parts) != 2:
        raise ValueError(f"unparseable friction_coefficient_range: {range_str!r}")
    return float(parts[0]), float(parts[1])


def _build_record(
    *, record_id: str, coating_id: str, lubricant_id: str,
    overall_min: float, overall_max: float,
    source_reference: str, engineering_notes: str,
) -> dict:
    record = {
        "id": record_id,
        "source_standard": "",
        "confidence": 3,
        "notes": (
            "Faz 2.6.2B: deterministic re-homing of an already-"
            "approved value from CoatingRecord/LubricationRecord "
            "(ADR-0010) -- not a new measurement, not derived, not "
            "split. reference_only."
        ),
        "revision": GENERATED_DATE,
        "source": source_reference,
        "version": "2.6.2b",
        "validation_status": "provisional",
        "approval_status": "pending",
        "metadata": {},
        "coating_id": coating_id,
        "lubricant_id": lubricant_id,
        "surface_condition": "",
        "thread_condition": "",
        "bearing_condition": "",
        "friction_model": "combined_or_unspecified",
        "overall_friction_coefficient_min": overall_min,
        "overall_friction_coefficient_max": overall_max,
        "mu_thread_min": None,
        "mu_thread_max": None,
        "mu_bearing_min": None,
        "mu_bearing_max": None,
        "k_factor_min": None,
        "k_factor_max": None,
        "scatter_percent": None,
        "max_temperature_c": None,
        "applicability": (
            "As-received/as-coated or as-supplied condition; no "
            "specific paired product beyond the referenced "
            "coating/lubricant record. A combination-specific "
            "ISO 16047 test report must govern production "
            "torque-tension calculations; this record is not that "
            "report."
        ),
        "source_reference": source_reference,
        "source_type": "standard",
        "source_page_or_table": "",
        "verification_status": "reference_only",
        "engineering_notes": engineering_notes,
        "name": "",
        "standard": "",
        "description": "",
        "aliases": [],
        "created_at": None,
        "updated_at": None,
        "record_version": "1.0",
        "status": "provisional",
        "unit_system": "metric",
        "country": "",
        "manufacturer": "",
        "tags": ["faz-2.6.2b", "coating-migration" if coating_id else "lubrication-migration"],
    }
    payload = {k: v for k, v in record.items() if k != "checksum"}
    record["checksum"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return record


def generate_from_coatings() -> list[dict]:
    data = json.loads(COATING_PATH.read_text(encoding="utf-8"))
    out = []
    for r in data["records"]:
        range_str = r.get("friction_coefficient_range") or ""
        if not range_str:
            continue
        overall_min, overall_max = _parse_range(range_str)
        out.append(_build_record(
            record_id=f"FC-{r['id']}",
            coating_id=r["id"],
            lubricant_id="",
            overall_min=overall_min,
            overall_max=overall_max,
            source_reference=r.get("source", r.get("source_standard", "")),
            engineering_notes=(
                f"Migrated from CoatingRecord {r['id']!r} "
                f"friction_coefficient_range={range_str!r}."
            ),
        ))
    return out


def generate_from_lubrication() -> list[dict]:
    data = json.loads(LUBRICATION_PATH.read_text(encoding="utf-8"))
    out = []
    for r in data["records"]:
        if r["id"].startswith("LUBE-SURF-"):
            continue  # Tablo 9.4 -- explicitly not migrated this phase.
        fmin, fmax = r.get("friction_coefficient_min"), r.get("friction_coefficient_max")
        if fmin is None or fmax is None:
            continue
        out.append(_build_record(
            record_id=f"FC-{r['id']}",
            coating_id="",
            lubricant_id=r["id"],
            overall_min=float(fmin),
            overall_max=float(fmax),
            source_reference=r.get("source", r.get("source_standard", "")),
            engineering_notes=(
                f"Migrated from LubricationRecord {r['id']!r} "
                f"friction_coefficient_min/max=({fmin}, {fmax})."
            ),
        ))
    return out


def main() -> None:
    new_records = generate_from_coatings() + generate_from_lubrication()
    new_ids = {r["id"] for r in new_records}

    data = json.loads(FRICTION_CONDITION_PATH.read_text(encoding="utf-8"))
    # Idempotent: drop any prior generated record with a colliding id,
    # keep everything else (there is nothing else yet, but this keeps
    # the script safe if hand-authored records are added later).
    kept = [r for r in data["records"] if r["id"] not in new_ids]
    data["records"] = kept + new_records
    data["metadata"]["version"] = "2.6.2b"
    data["metadata"]["description"] = (
        "Combination-dependent friction data (coating + lubricant + "
        "assembly-condition pairing). Faz 2.6.2B: 18 records "
        "deterministically re-homed from already-approved "
        "CoatingRecord/LubricationRecord friction ranges (ISO 16047 / "
        "ISO 4042 typical ranges). The 15 Tablo 9.4 records and any "
        "independent mu_thread/mu_bearing/K/scatter/temperature value "
        "remain unmigrated/unsourced -- see "
        "docs/phases/PHASE_2.6.2B_VERIFIED_FRICTION_DATA_POPULATION.md."
    )
    data["metadata"]["generated"] = GENERATED_DATE
    data["metadata"]["primary_source"] = "ISO 16047 / ISO 4042 (typical range, not a test report)"

    FRICTION_CONDITION_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(new_records)} Faz 2.6.2B records to {FRICTION_CONDITION_PATH}")


if __name__ == "__main__":
    main()
