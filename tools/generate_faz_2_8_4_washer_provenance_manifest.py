"""TorqPro Engineering Library - Faz 2.8.4 washer provenance evidence
manifest generator.

This is a one-time *authoring* script (mirrors the convention already
established by ``tools/generate_faz2_4_1c_washer_records.py`` and
siblings): it writes
``backend/library/data/washer_provenance_evidence.json``, which then
becomes the single source of truth for washer-record provenance
classification. ``tools/washer_provenance_report_faz_2_8_4.py`` never
re-derives categories or reason codes -- it only reads this manifest,
validates it against the live library, and reports.

Scope (Faz 2.8.4 task brief): classify each of the 223
``backend/library/data/washer_library.json`` records into exactly one
of five provenance categories, based on:

  1. A read-only transcription of the ``Pul_Geometri`` sheet (23
     records, ISO 7089 / 7090 / 7093-1 only) from the Google Drive
     file ``Baglanti_Elemanlari_Kutuphanesi_v3_1.xlsx`` (a secondary,
     unverified catalog -- its own ``Kaynaklar`` sheet marks the
     underlying ISO standards as "Satın alınacak" / not yet
     purchased). This transcription is reproduced here as static data
     for auditability; no Google Drive URL, file ID, or account
     information is stored.
  2. The washer records' own internal provenance fields
     (``confidence``, ``validation_status``, ``approval_status``,
     ``metadata.estimated_fields``, ``notes``), which in several
     groups already self-declare "ratio-estimated ... NOT read from
     the [standard] dimensional table" or (for ISO 8738) combine a
     numeric confidence of 4 with ``validation_status="reference_only"``
     / ``approval_status="pending"``.

This script makes **no geometric correctness claims** and changes
**no** field in ``washer_library.json``. It only decides, once, which
of the five provenance categories and (for ``action_needed``) which
of the four reason codes applies to each record, and writes that
decision to the manifest.

Categories (mutually exclusive, cover all 223 records exactly once):
    standard_verified, secondary_source_only,
    generated_from_unverified_source, no_external_evidence,
    action_needed

Reason codes (``action_needed`` only):
    estimated_value_diverges_from_secondary_source,
    standard_identity_requires_review,
    confidence_metadata_contradiction,
    high_internal_confidence_lacks_external_evidence

Usage::

    python tools/generate_faz_2_8_4_washer_provenance_manifest.py

Writes ``backend/library/data/washer_provenance_evidence.json``
unconditionally (this is an authoring tool, not a production code
path; re-run only when the evidence basis itself changes).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_library.json"
MANIFEST_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_provenance_evidence.json"

#: Static, read-only transcription of the Pul_Geometri sheet in
#: Baglanti_Elemanlari_Kutuphanesi_v3_1.xlsx (Google Drive, folder
#: "TorqPro_17", reviewed 2026-07-26). Field names mirror the sheet's
#: own Turkish headers (d1 = İç Çap, d2 = Dış Çap, h = Kalınlık).
#: The sheet's own Kaynaklar entry SRC-005 for these three standards
#: is marked "Satın alınacak" (official standard not yet purchased/
#: accessed) -- this catalog is itself a secondary, unverified source.
XLSX_SOURCE_FILE = "Baglanti_Elemanlari_Kutuphanesi_v3_1.xlsx"
XLSX_SOURCE_SHEET = "Pul_Geometri"

XLSX_WASHER_EVIDENCE: Dict[str, Dict[str, Dict[str, Any]]] = {
    "ISO 7089": {
        "M5":  {"row": "WG-0001", "d1": 5.3,  "d2": 10, "h": 1},
        "M6":  {"row": "WG-0002", "d1": 6.4,  "d2": 12, "h": 1.6},
        "M8":  {"row": "WG-0003", "d1": 8.4,  "d2": 16, "h": 1.6},
        "M10": {"row": "WG-0004", "d1": 10.5, "d2": 20, "h": 2},
        "M12": {"row": "WG-0005", "d1": 13,   "d2": 24, "h": 2.5},
        "M14": {"row": "WG-0006", "d1": 15,   "d2": 28, "h": 2.5},
        "M16": {"row": "WG-0007", "d1": 17,   "d2": 30, "h": 3},
        "M20": {"row": "WG-0008", "d1": 21,   "d2": 37, "h": 3},
        "M24": {"row": "WG-0009", "d1": 25,   "d2": 44, "h": 4},
    },
    "ISO 7090": {
        "M5":  {"row": "WG-0010", "d1": 5.3,  "d2": 10, "h": 1},
        "M6":  {"row": "WG-0011", "d1": 6.4,  "d2": 12, "h": 1.6},
        "M8":  {"row": "WG-0012", "d1": 8.4,  "d2": 16, "h": 1.6},
        "M10": {"row": "WG-0013", "d1": 10.5, "d2": 20, "h": 2},
        "M12": {"row": "WG-0014", "d1": 13,   "d2": 24, "h": 2.5},
        "M14": {"row": "WG-0015", "d1": 15,   "d2": 28, "h": 2.5},
        "M16": {"row": "WG-0016", "d1": 17,   "d2": 30, "h": 3},
        "M20": {"row": "WG-0017", "d1": 21,   "d2": 37, "h": 3},
        "M24": {"row": "WG-0018", "d1": 25,   "d2": 44, "h": 4},
    },
    # Backend groups these under source_standard "ISO 7093" (no
    # suffix); the XLSX sheet labels its column "ISO 7093-1". Whether
    # these denote the same washer family/part is NOT established in
    # this session -- see standard_identity_requires_review below.
    "ISO 7093-1": {
        "M6":  {"row": "WG-0019", "d1": 6.4,  "d2": 18, "h": 1.6},
        "M8":  {"row": "WG-0020", "d1": 8.4,  "d2": 24, "h": 2},
        "M10": {"row": "WG-0021", "d1": 10.5, "d2": 30, "h": 2.5},
        "M12": {"row": "WG-0022", "d1": 13,   "d2": 37, "h": 3},
        "M16": {"row": "WG-0023", "d1": 17,   "d2": 50, "h": 3},
    },
}

CATEGORY_DEFINITIONS = {
    "standard_verified": (
        "Confirmed against a licensed/purchased primary ISO or DIN "
        "standard document accessed during this phase. Not used in "
        "Faz 2.8.4 -- no such access occurred."
    ),
    "secondary_source_only": (
        "Numerically matches a secondary, unverified catalog source "
        "(the reviewed XLSX); the catalog itself is not confirmed "
        "against a purchased primary standard."
    ),
    "generated_from_unverified_source": (
        "Direct data-lineage evidence (e.g. a generation script or "
        "changelog entry) shows this record was produced FROM the "
        "secondary source. Requires proven lineage, not just a "
        "numeric match -- see reason in notes when count is 0."
    ),
    "no_external_evidence": (
        "No comparable data was found in the reviewed Google Drive "
        "materials for this standard/designation. Not a correctness "
        "judgement -- only an evidence-availability statement."
    ),
    "action_needed": (
        "Some aspect of this record's provenance requires human "
        "review before its confidence level is changed. Does not by "
        "itself assert the geometry is wrong."
    ),
}

REASON_CODE_DEFINITIONS = {
    "estimated_value_diverges_from_secondary_source": (
        "Record's own metadata already marks the geometry as "
        "ratio-estimated (not table-read); its values show a "
        "secondary-source divergence from the reviewed XLSX. This is "
        "an expected consequence of the estimate, not a confirmed "
        "error."
    ),
    "standard_identity_requires_review": (
        "The backend standard label and the secondary-source standard "
        "label may not denote the same washer family/part revision; "
        "identity unconfirmed. Comparison result is not used to "
        "assert numeric correctness."
    ),
    "confidence_metadata_contradiction": (
        "The record's numeric confidence level and its own "
        "validation_status/approval_status/notes fields are in "
        "tension (an evidence gap between the confidence label and "
        "the internal metadata)."
    ),
    "high_internal_confidence_lacks_external_evidence": (
        "Internal metadata claims a fully verified/approved status "
        "with no estimated fields, but no external corroborating "
        "source was found in the reviewed materials. A review "
        "priority signal, not a correctness claim."
    ),
}

ALLOWED_CATEGORIES = frozenset(CATEGORY_DEFINITIONS)
ALLOWED_REASON_CODES = frozenset(REASON_CODE_DEFINITIONS)

_DESIGNATION_RE = re.compile(r"(M\d+(?:\.\d+)?)")


def _extract_designation(raw_designation: str) -> str:
    match = _DESIGNATION_RE.search(raw_designation or "")
    if not match:
        raise ValueError(f"Cannot extract designation from {raw_designation!r}")
    return match.group(1)


def _values_match(record: Dict[str, Any], xlsx_row: Dict[str, Any]) -> bool:
    fields = (
        ("inner_diameter_mm", "d1"),
        ("outer_diameter_mm", "d2"),
        ("thickness_mm", "h"),
    )
    for lib_field, xlsx_field in fields:
        lib_val = record.get(lib_field)
        xlsx_val = xlsx_row.get(xlsx_field)
        if lib_val is None or xlsx_val is None:
            return False
        if abs(float(lib_val) - float(xlsx_val)) > 1e-9:
            return False
    return True


def _classify(record: Dict[str, Any]) -> Dict[str, Any]:
    standard = record.get("source_standard", "")
    designation = _extract_designation(record.get("designation", ""))
    record_id = record["id"]

    comparison_fields = ["inner_diameter_mm", "outer_diameter_mm", "thickness_mm"]

    # ISO 7093 (backend) vs ISO 7093-1 (XLSX): identity not established.
    if standard == "ISO 7093":
        xlsx_row = XLSX_WASHER_EVIDENCE["ISO 7093-1"].get(designation)
        if xlsx_row is not None:
            return {
                "category": "action_needed",
                "reason_code": "standard_identity_requires_review",
                "evidence_source": "google_drive_xlsx",
                "evidence_type": "secondary_unverified_catalog",
                "source_file": XLSX_SOURCE_FILE,
                "source_sheet": XLSX_SOURCE_SHEET,
                "source_reference": xlsx_row["row"],
                "comparison_fields": comparison_fields,
                "comparison_result": "identity_unconfirmed",
                "notes": (
                    "Backend standard label 'ISO 7093' vs. catalog label "
                    "'ISO 7093-1'; whether these denote the same washer "
                    "family/part revision was not established in this "
                    "session. Comparison result is not used to assert "
                    "numeric correctness."
                ),
            }
        return _no_external_evidence(comparison_fields)

    # ISO 8738: numeric confidence 4 alongside self-declared
    # reference_only/pending/estimated internal metadata.
    if standard == "ISO 8738":
        return {
            "category": "action_needed",
            "reason_code": "confidence_metadata_contradiction",
            "evidence_source": "backend_internal_metadata",
            "evidence_type": "confidence_status_conflict",
            "source_file": "backend/library/data/washer_library.json",
            "source_sheet": None,
            "source_reference": record_id,
            "comparison_fields": ["confidence", "validation_status", "approval_status"],
            "comparison_result": "not_applicable",
            "notes": (
                "confidence=4 is present alongside validation_status="
                "'reference_only' and approval_status='pending' on this "
                "same record; an evidence gap between the confidence "
                "label and the record's own internal metadata."
            ),
        }

    # DIN 127 B: internally claims validated/approved with no
    # estimated fields, but no external corroboration was found.
    if standard == "DIN 127 B":
        return {
            "category": "action_needed",
            "reason_code": "high_internal_confidence_lacks_external_evidence",
            "evidence_source": "none_found",
            "evidence_type": "no_external_corroboration",
            "source_file": "backend/library/data/washer_library.json",
            "source_sheet": None,
            "source_reference": record_id,
            "comparison_fields": None,
            "comparison_result": "not_applicable",
            "notes": (
                "Internal metadata (validation_status='validated', "
                "approval_status='approved', no estimated fields) "
                "differs from every other washer group reviewed, but no "
                "external corroborating source was found in the "
                "reviewed Google Drive materials. Flagged as a review "
                "priority signal, not a correctness claim."
            ),
        }

    # ISO 7089 / ISO 7090: compare against XLSX where the designation
    # is present; otherwise no comparable evidence exists.
    if standard in ("ISO 7089", "ISO 7090"):
        xlsx_row = XLSX_WASHER_EVIDENCE.get(standard, {}).get(designation)
        if xlsx_row is None:
            return _no_external_evidence(comparison_fields)
        if _values_match(record, xlsx_row):
            return {
                "category": "secondary_source_only",
                "reason_code": None,
                "evidence_source": "google_drive_xlsx",
                "evidence_type": "secondary_unverified_catalog",
                "source_file": XLSX_SOURCE_FILE,
                "source_sheet": XLSX_SOURCE_SHEET,
                "source_reference": xlsx_row["row"],
                "comparison_fields": comparison_fields,
                "comparison_result": "match",
                "notes": (
                    "Matches the secondary catalog value. The catalog's "
                    "own source record (SRC-005) is marked 'Satın "
                    "alınacak' (official standard not yet purchased/"
                    "accessed) -- this is a secondary-source match, not "
                    "a primary-standard verification."
                ),
            }
        return {
            "category": "action_needed",
            "reason_code": "estimated_value_diverges_from_secondary_source",
            "evidence_source": "google_drive_xlsx",
            "evidence_type": "secondary_unverified_catalog",
            "source_file": XLSX_SOURCE_FILE,
            "source_sheet": XLSX_SOURCE_SHEET,
            "source_reference": xlsx_row["row"],
            "comparison_fields": comparison_fields,
            "comparison_result": "mismatch",
            "notes": (
                "Secondary-source divergence from the reviewed catalog "
                "value. This record's own metadata already marks the "
                "geometry as ratio-estimated (not table-read), so a "
                "divergence is an expected consequence of the estimate, "
                "not a confirmed error."
            ),
        }

    # ISO 7091, DIN 125, DIN 9021 and any other group: no XLSX
    # coverage, no other Drive evidence found.
    return _no_external_evidence(comparison_fields)


def _no_external_evidence(comparison_fields: List[str]) -> Dict[str, Any]:
    return {
        "category": "no_external_evidence",
        "reason_code": None,
        "evidence_source": "none_found",
        "evidence_type": "no_evidence_found",
        "source_file": None,
        "source_sheet": None,
        "source_reference": None,
        "comparison_fields": None,
        "comparison_result": "not_applicable",
        "notes": (
            "No comparable data was found in the reviewed Google Drive "
            "materials (Torque folder and TorqPro_17/"
            + XLSX_SOURCE_FILE
            + ") for this standard/designation. This is an "
            "evidence-availability statement, not a correctness "
            "judgement."
        ),
    }


def build_manifest() -> Dict[str, Any]:
    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    records = library["records"]

    entries: List[Dict[str, Any]] = []
    for record in records:
        classification = _classify(record)
        assert classification["category"] in ALLOWED_CATEGORIES
        if classification["reason_code"] is not None:
            assert classification["reason_code"] in ALLOWED_REASON_CODES
        entry = {
            "record_id": record["id"],
            "standard": record.get("source_standard"),
            "designation": _extract_designation(record.get("designation", "")),
            **classification,
            "reviewed_at": None,
        }
        entries.append(entry)

    entries.sort(key=lambda e: e["record_id"])

    return {
        "manifest_version": "1.0",
        "phase": "2.8.4",
        "title": "Washer Library Provenance Evidence Manifest",
        "phase_date": "2026-07-26",
        "generated_at": None,
        "scope_note": (
            "This manifest records the evidence status found for each "
            "washer_library.json record during Faz 2.8.4. It makes no "
            "geometric correctness claims and was not used to change "
            "any field in washer_library.json."
        ),
        "category_definitions": CATEGORY_DEFINITIONS,
        "reason_code_definitions": REASON_CODE_DEFINITIONS,
        "entries": entries,
    }


def main() -> int:
    manifest = build_manifest()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(manifest['entries'])} entries to {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
