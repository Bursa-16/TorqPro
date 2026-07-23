"""Faz 2.6.0 one-off generator: Tablo 9.4 surface/lubrication-state records.

Produces the 15 (5 surface conditions x 3 lubrication states) records
derived from "Tablo 9.4 Surtunme Katsayilari icin Yaklasik Degerler"
(Makine Elemanlari textbook, Sekil 9.23 "Somun Dayanma Yuzeyi" context,
page 211 -- source image supplied by user). Values are the table's
overall (combined, not thread/bearing-split) friction coefficient
ranges, transcribed verbatim -- no derivation, split or K-factor
conversion is performed (Faz 2.6.0 scope: architecture, not
coefficient population beyond this one cited table).

Run once to (re)generate the ``LUBE-SURF-*`` block appended to
``backend/library/data/lubrication_library.json``. Idempotent: re-run
after any edit to TABLE_9_4 to keep stored checksums correct.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "backend" / "library" / "data" / "lubrication_library.json"
)

SOURCE_REFERENCE = (
    "Makine Elemanlari (ders kitabi), Tablo 9.4 - "
    "Surtunme Katsayilari icin Yaklasik Degerler"
)
SOURCE_PAGE = "s. 211, Tablo 9.4 (bkz. Sekil 9.23 Somun Dayanma Yuzeyi baglami)"
GENERATED_DATE = "2026-07-23"

NO_LUBRICANT = "No lubricant (as-coated/as-plated surface)"
OILED_GENERIC = "Generic oil film (unspecified oil type)"
MOS2_WITH_OIL = "Molybdenum disulfide with oil film"

# (surface_condition_tr, surface_slug, lubricant_type_enum_value, state_slug, mu_min, mu_max)
TABLE_9_4 = [
    ("Kaplanmamis", "UNCOATED", NO_LUBRICANT, "DRY", 0.20, 0.35),
    ("Kaplanmamis", "UNCOATED", OILED_GENERIC, "OILED", 0.16, 0.23),
    ("Kaplanmamis", "UNCOATED", MOS2_WITH_OIL, "MOS2-OILED", 0.13, 0.19),

    ("Fosfatlanmis", "PHOSPHATED", NO_LUBRICANT, "DRY", 0.28, 0.40),
    ("Fosfatlanmis", "PHOSPHATED", OILED_GENERIC, "OILED", 0.16, 0.33),
    ("Fosfatlanmis", "PHOSPHATED", MOS2_WITH_OIL, "MOS2-OILED", 0.13, 0.19),

    ("Fosfat+Karartma", "PHOSPHATE-BLACKENED", NO_LUBRICANT, "DRY", 0.26, 0.37),
    ("Fosfat+Karartma", "PHOSPHATE-BLACKENED", OILED_GENERIC, "OILED", 0.24, 0.27),
    ("Fosfat+Karartma", "PHOSPHATE-BLACKENED", MOS2_WITH_OIL, "MOS2-OILED", 0.14, 0.21),

    ("Galvanize", "GALVANIZED", "No lubricant (as-coated/as-plated surface)", "DRY", 0.14, 0.20),
    ("Galvanize", "GALVANIZED", "Generic oil film (unspecified oil type)", "OILED", 0.14, 0.19),
    ("Galvanize", "GALVANIZED", "Molybdenum disulfide with oil film", "MOS2-OILED", 0.10, 0.17),

    ("Kadmiyum Kapli", "CADMIUM", "No lubricant (as-coated/as-plated surface)", "DRY", 0.10, 0.19),
    ("Kadmiyum Kapli", "CADMIUM", "Generic oil film (unspecified oil type)", "OILED", 0.10, 0.17),
    ("Kadmiyum Kapli", "CADMIUM", "Molybdenum disulfide with oil film", "MOS2-OILED", 0.13, 0.17),
]

CADMIUM_REGULATORY_WARNING = (
    "Kadmiyum kaplama modern seri uretim otomotiv uygulamalarinda RoHS/ELV "
    "ve benzeri mevzuat ile musteri OEM sartlarina bagli olarak kisitli veya "
    "yasaklidir. Bu kayit yalnizca tarihsel/referans muhendislik degeri "
    "tasir; yeni bir tasarimda kullanilmadan once mevzuat ve musteri "
    "onayi ayrica dogrulanmalidir. Kesin mevzuat hukmu bu fazda "
    "belirtilmemistir (bkz. Faz 2.6.2 veri dogrulama fazi)."
)


def build_record(
    surface_tr: str, surface_slug: str, lubricant_type: str,
    state_slug: str, mu_min: float, mu_max: float,
) -> dict:
    is_cadmium = surface_slug == "CADMIUM"
    record = {
        "id": f"LUBE-SURF-{surface_slug}-{state_slug}",
        "source_standard": "",
        "confidence": 3,
        "notes": (
            "Faz 2.6.0: Tablo 9.4 kaynakli, tek toplam surtunme katsayisi "
            "araligi (thread/bearing ayrimi yok). Uretimde kullanilmadan "
            "once ISO 16047 tork-on yuk testi ile dogrulanmalidir."
        ),
        "revision": GENERATED_DATE,
        "source": SOURCE_REFERENCE,
        "version": "2.6.0",
        "validation_status": "provisional",
        "approval_status": "pending",
        "metadata": {},
        "designation": f"{surface_tr} - {state_slug.replace('-', ' ').title()}",
        "lubricant_type": lubricant_type,
        "friction_coefficient_min": None,
        "friction_coefficient_max": None,
        "application": "Somun dayanma yuzeyi surtunme katsayisi referansi (Tablo 9.4)",
        "oem_compatibility": [],
        "overall_friction_coefficient_min": mu_min,
        "overall_friction_coefficient_max": mu_max,
        "friction_model": "combined_or_unspecified",
        "mu_thread_min": None,
        "mu_thread_max": None,
        "mu_bearing_min": None,
        "mu_bearing_max": None,
        "k_factor_min": None,
        "k_factor_max": None,
        "scatter_percent": None,
        "max_temperature_c": None,
        "corrosion_resistance": "",
        "reusability": "",
        "recommended_standards": [],
        "source_status": "textbook_reference",
        "source_reference": SOURCE_REFERENCE,
        "source_type": "textbook",
        "source_page_or_table": SOURCE_PAGE,
        "verification_status": "reference_only",
        "applicability": (
            "Somun dayanma yuzeyi (bearing surface) sürtünmesi baglaminda "
            "verilmis genel civata/somun yuzey durumu referans degeri; "
            "belirli bir civata capi, siniflandirma veya yag markasina "
            "ozel degildir."
        ),
        "engineering_notes": "",
        "regulatory_warning": CADMIUM_REGULATORY_WARNING if is_cadmium else "",
        "surface_condition": surface_tr,
        "name": "",
        "standard": "",
        "description": "",
        "aliases": [],
        "created_at": None,
        "updated_at": None,
        "record_version": "1.0",
        "status": "restricted_legacy" if is_cadmium else "provisional",
        "unit_system": "metric",
        "country": "",
        "manufacturer": "",
        "tags": ["faz-2.6.0", "table-9.4", surface_slug.lower(), state_slug.lower()],
    }
    payload = {k: v for k, v in record.items() if k != "checksum"}
    checksum = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    record["checksum"] = checksum
    return record


def main() -> None:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    existing_ids = {r["id"] for r in data["records"]}
    new_records = []
    for surface_tr, surface_slug, lubricant_type, state_slug, mu_min, mu_max in TABLE_9_4:
        rec = build_record(surface_tr, surface_slug, lubricant_type, state_slug, mu_min, mu_max)
        if rec["id"] in existing_ids:
            data["records"] = [r for r in data["records"] if r["id"] != rec["id"]]
        new_records.append(rec)

    data["records"].extend(new_records)
    data["metadata"]["version"] = "2.6.0"
    data["metadata"]["description"] = (
        "Typical friction ranges, usage notes and OEM compatibility for "
        "eight lubrication conditions (Faz 2.4.1), plus 15 Tablo 9.4 "
        "surface/lubrication-state combined-friction reference records "
        "(Faz 2.6.0, textbook_reference/reference_only)."
    )
    data["metadata"]["generated"] = GENERATED_DATE

    DATA_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(new_records)} Faz 2.6.0 records to {DATA_FILE}")


if __name__ == "__main__":
    main()
