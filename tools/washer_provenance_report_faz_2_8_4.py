"""TorqPro Engineering Library - Faz 2.8.4 washer provenance report.

Reads ``backend/library/data/washer_provenance_evidence.json`` (the
single source of truth for provenance categories and reason codes --
see ``tools/generate_faz_2_8_4_washer_provenance_manifest.py``) and
``backend/library/data/washer_library.json``, joins them, validates
consistency, and reports category/reason-code totals.

This tool does **not** re-derive any classification. It only:
  - validates the manifest against the live library (every library
    record present exactly once in the manifest and vice versa, no
    duplicates, every entry has an allowed category and, for
    ``action_needed``, an allowed reason code),
  - joins the two for reporting,
  - renders a deterministic Markdown + JSON report.

Default mode (no arguments): prints a summary to stdout only. No file
under the repository is written.

``--output-dir <path>``: writes ``phase_2_8_4_washer_provenance_report.md``
and ``.json`` to the given directory, deterministically (byte-identical
across repeated runs with the same inputs -- no timestamps, no
absolute paths, no working-directory-dependent content).

There is no ``--apply`` flag. ``washer_library.json`` is never written
by this tool.

Exit codes:
  0  manifest/library consistent, report generated (or summary printed)
  1  manifest/library inconsistency detected (counts, duplicates,
     missing/extra records, invalid category or reason code)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_library.json"
MANIFEST_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_provenance_evidence.json"

ALLOWED_CATEGORIES = (
    "standard_verified",
    "secondary_source_only",
    "generated_from_unverified_source",
    "no_external_evidence",
    "action_needed",
)

ALLOWED_REASON_CODES = (
    "estimated_value_diverges_from_secondary_source",
    "standard_identity_requires_review",
    "confidence_metadata_contradiction",
    "high_internal_confidence_lacks_external_evidence",
)


class ProvenanceConsistencyError(Exception):
    """Raised when the manifest and the live library disagree."""


def load_inputs(
    library_path: Path = LIBRARY_PATH, manifest_path: Path = MANIFEST_PATH
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    library = json.loads(library_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return library, manifest


def validate_and_join(
    library: Dict[str, Any], manifest: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Validate manifest/library consistency and return the joined rows.

    Raises ProvenanceConsistencyError (never silently continues) on
    any mismatch.
    """
    lib_records = library["records"]
    lib_ids = [r["id"] for r in lib_records]
    if len(lib_ids) != len(set(lib_ids)):
        raise ProvenanceConsistencyError("Duplicate record id(s) found in washer_library.json")

    entries = manifest["entries"]
    entry_ids = [e["record_id"] for e in entries]
    if len(entry_ids) != len(set(entry_ids)):
        raise ProvenanceConsistencyError("Duplicate record_id(s) found in manifest")

    std_des_keys = [(e["standard"], e["designation"]) for e in entries]
    if len(std_des_keys) != len(set(std_des_keys)):
        raise ProvenanceConsistencyError(
            "Duplicate (standard, designation) combination(s) found in manifest"
        )

    lib_id_set = set(lib_ids)
    entry_id_set = set(entry_ids)

    missing_in_manifest = lib_id_set - entry_id_set
    if missing_in_manifest:
        raise ProvenanceConsistencyError(
            f"{len(missing_in_manifest)} library record(s) missing from manifest: "
            f"{sorted(missing_in_manifest)[:5]}..."
        )

    extra_in_manifest = entry_id_set - lib_id_set
    if extra_in_manifest:
        noun = "entry" if len(extra_in_manifest) == 1 else "entries"
        raise ProvenanceConsistencyError(
            f"{len(extra_in_manifest)} manifest {noun} "
            f"reference non-existent library record(s): {sorted(extra_in_manifest)[:5]}..."
        )

    entries_by_id = {e["record_id"]: e for e in entries}

    joined: List[Dict[str, Any]] = []
    for record in lib_records:
        entry = entries_by_id[record["id"]]

        category = entry.get("category")
        if category not in ALLOWED_CATEGORIES:
            raise ProvenanceConsistencyError(
                f"Record {record['id']!r} has disallowed category {category!r}"
            )

        reason_code = entry.get("reason_code")
        if category == "action_needed":
            if not reason_code:
                raise ProvenanceConsistencyError(
                    f"Record {record['id']!r} is action_needed but has no reason_code"
                )
            if reason_code not in ALLOWED_REASON_CODES:
                raise ProvenanceConsistencyError(
                    f"Record {record['id']!r} has disallowed reason_code {reason_code!r}"
                )
        elif reason_code is not None:
            raise ProvenanceConsistencyError(
                f"Record {record['id']!r} has category {category!r} but a non-null "
                f"reason_code {reason_code!r} (reason codes are action_needed-only)"
            )

        joined.append(
            {
                "record_id": record["id"],
                "standard": record.get("source_standard"),
                "designation": entry["designation"],
                "confidence": record.get("confidence"),
                "category": category,
                "reason_code": reason_code,
                "evidence_source": entry.get("evidence_source"),
                "evidence_type": entry.get("evidence_type"),
                "source_file": entry.get("source_file"),
                "source_sheet": entry.get("source_sheet"),
                "source_reference": entry.get("source_reference"),
                "comparison_result": entry.get("comparison_result"),
                "notes": entry.get("notes"),
            }
        )

    joined.sort(key=lambda r: r["record_id"])
    return joined


def summarize(joined: List[Dict[str, Any]]) -> Dict[str, Any]:
    category_totals: Dict[str, int] = {c: 0 for c in ALLOWED_CATEGORIES}
    reason_totals: Dict[str, int] = {r: 0 for r in ALLOWED_REASON_CODES}
    standard_totals: Dict[str, Dict[str, int]] = {}

    for row in joined:
        category_totals[row["category"]] += 1
        if row["reason_code"]:
            reason_totals[row["reason_code"]] += 1
        std = row["standard"]
        bucket = standard_totals.setdefault(std, {c: 0 for c in ALLOWED_CATEGORIES})
        bucket[row["category"]] += 1

    return {
        "total_records": len(joined),
        "category_totals": category_totals,
        "reason_totals": reason_totals,
        "standard_totals": dict(sorted(standard_totals.items())),
    }


def render_json_report(joined: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    action_needed_rows = [r for r in joined if r["category"] == "action_needed"]
    report = {
        "phase": "2.8.4",
        "title": "Washer Library Provenance & Verification Readiness",
        "scope_note": (
            "This report records the evidence status found for each "
            "washer_library.json record. It makes no geometric "
            "correctness claims; no field in washer_library.json was "
            "changed to produce it."
        ),
        "xlsx_source_status": {
            "source_file": "Baglanti_Elemanlari_Kutuphanesi_v3_1.xlsx",
            "note": (
                "This secondary catalog's own SRC-005 entry marks the "
                "underlying ISO 7089/7090/7093-1 standards as 'Satın "
                "alınacak' (not yet purchased/accessed); a numeric "
                "match against it is a secondary-source match, not a "
                "primary-standard verification."
            ),
        },
        "identity_review_note": {
            "topic": "ISO 7093 (backend) vs ISO 7093-1 (secondary catalog)",
            "status": "identity_unconfirmed",
        },
        "confidence_metadata_note": {
            "topic": "ISO 8738",
            "status": (
                "confidence=4 present alongside internal "
                "validation_status='reference_only' and "
                "approval_status='pending' -- evidence gap, not a "
                "geometry judgement."
            ),
        },
        "din127b_note": {
            "topic": "DIN 127 B",
            "status": (
                "Internal metadata claims validated/approved with no "
                "estimated fields, but no external corroborating "
                "source was found in the reviewed materials -- a "
                "review-priority signal, not a correctness claim."
            ),
        },
        "summary": summary,
        "action_needed_records": action_needed_rows,
        "all_records": joined,
    }
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def render_markdown_report(joined: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append

    a("# Faz 2.8.4 - Washer Library Provenance & Verification Readiness")
    a("")
    a(
        "Bu rapor 223 `washer_library.json` kaydinin kanit durumunu "
        "izlenebilir bicimde kaydeder. Hicbir geometrik dogruluk "
        "iddiasi tasimaz ve bu raporu uretmek icin `washer_library.json` "
        "icindeki hicbir alan degistirilmedi."
    )
    a("")
    a("## Kapsam ve sinirlamalar")
    a("")
    a(
        "- Bu faz, birincil ISO/DIN standardina dogrudan erisim "
        "icermiyor; yalnizca Google Drive'da incelenen ikincil, "
        "dogrulanmamis bir katalog (XLSX) ve kayitlarin kendi ic "
        "provenance alanlariyla (`confidence`, `validation_status`, "
        "`approval_status`, `metadata.estimated_fields`, `notes`) "
        "karsilastirma yapildi."
    )
    a(
        "- `action_needed` kategorisi kesin bir geometrik hata "
        "iddiasi degildir; yalnizca inceleme onceligini isaret eder."
    )
    a("")

    a("## Kategori toplamlari")
    a("")
    a("| Kategori | Kayit |")
    a("|---|---:|")
    for cat in ALLOWED_CATEGORIES:
        a(f"| `{cat}` | {summary['category_totals'][cat]} |")
    a(f"| **Toplam** | **{summary['total_records']}** |")
    a("")

    a("## Reason-code dagilimi (yalnizca action_needed)")
    a("")
    a("| Reason code | Kayit |")
    a("|---|---:|")
    for reason in ALLOWED_REASON_CODES:
        a(f"| `{reason}` | {summary['reason_totals'][reason]} |")
    a("")

    a("## Standart bazli dagilim")
    a("")
    header_cats = ALLOWED_CATEGORIES
    a("| Standart | " + " | ".join(f"`{c}`" for c in header_cats) + " | Toplam |")
    a("|---" * (len(header_cats) + 2) + "|")
    for std, bucket in summary["standard_totals"].items():
        row_total = sum(bucket.values())
        a(
            f"| {std} | "
            + " | ".join(str(bucket[c]) for c in header_cats)
            + f" | {row_total} |"
        )
    a("")

    a("## XLSX kaynagi durumu")
    a("")
    a(
        "`Baglanti_Elemanlari_Kutuphanesi_v3_1.xlsx` (Google Drive, "
        "`TorqPro_17` klasoru), `Pul_Geometri` sayfasi -- yalnizca ISO "
        "7089/7090/7093-1 icin 23 kayit. Bu dosyanin kendi `Kaynaklar` "
        "sayfasindaki SRC-005 girisi, ilgili ISO standartlarini "
        "**'Satin alinacak'** (henuz satin alinmamis/erisilmemis) "
        "olarak isaretliyor. Bu nedenle bu kaynakla eslesme "
        "`secondary_source_only` kategorisine girer, `standard_verified` "
        "olusturmaz."
    )
    a("")

    a("## ISO 7093 / ISO 7093-1 kimlik belirsizligi")
    a("")
    a(
        "Backend `source_standard` alani \"ISO 7093\" (ek yok); XLSX "
        "sayfasi \"ISO 7093-1\" olarak etiketliyor. Bu iki etiketin "
        "ayni washer ailesini/parca revizyonunu temsil edip etmedigi "
        "bu oturumda dogrulanamadi. Ilgili 5 kayit "
        "`standard_identity_requires_review` gerekcesiyle "
        "`action_needed` olarak isaretlendi; karsilastirma sonucu "
        "sayisal dogruluk iddiasi olarak kullanilmadi."
    )
    a("")

    a("## ISO 8738 confidence/metadata celiskisi")
    a("")
    a(
        "27 ISO 8738 kaydinin tamami `confidence=4` tasiyor, ancak ayni "
        "kayitlarin `validation_status=\"reference_only\"`, "
        "`approval_status=\"pending\"` ve `notes` alani ratio-estimate "
        "oldugunu beyan ediyor. Bu, confidence etiketiyle ic metadata "
        "arasinda bir kanit bosluğu -- geometri hatasi iddiasi degil."
    )
    a("")

    a("## DIN 127 B harici kanit bosluğu")
    a("")
    a(
        "34 DIN 127 B kaydi diger tum gruplardan farkli olarak "
        "`validation_status=\"validated\"`, `approval_status=\"approved\"` "
        "ve bos `estimated_fields` tasiyor -- ama incelenen Drive "
        "materyallerinde bu iddiayi dogrulayacak hicbir harici kaynak "
        "bulunamadi. `high_internal_confidence_lacks_external_evidence` "
        "gerekcesiyle `action_needed` isaretlendi; ne geometri hatasi "
        "ne de confidence dusurulmesi iddia edilmiyor."
    )
    a("")

    a("## Designation bazli action_needed tablosu")
    a("")
    a("| Kayit | Standart | Designation | Reason code |")
    a("|---|---|---|---|")
    for row in joined:
        if row["category"] == "action_needed":
            a(
                f"| {row['record_id']} | {row['standard']} | "
                f"{row['designation']} | `{row['reason_code']}` |"
            )
    a("")

    a("## Degismeyen davranis")
    a("")
    a(
        "Bu raporu uretmek icin `washer_library.json` icindeki hicbir "
        "geometrik deger, confidence, validation_status veya baska bir "
        "alan degistirilmedi. Bu arac `--apply` parametresi icermiyor."
    )
    a("")

    a("## Gelecekteki dogrulama mimarisi onerisi (future architecture)")
    a("")
    a(
        "Ileride lisansli/satin alinmis birincil ISO/DIN standardi "
        "saglandiginda, mevcut checksum/population mimarisine "
        "dokunmadan eklenebilecek, salt-okunur bir karsilastirma "
        "katmani onerilir. Bu faz kapsaminda **kod olarak "
        "eklenmemistir** -- yalnizca tasarim burada belgelenmektedir:"
    )
    a("")
    a(
        "- Girdi: birincil standarttan elle/OCR ile girilen "
        "`ExternalSourceRecord` listesi (standart no, designation, "
        "alan adi, dogrulanmis deger, kaynak dokuman, sayfa/madde, "
        "erisim tarihi)."
    )
    a(
        "- Islev: `washer_library.json` ile alan bazli karsilastirma; "
        "standart bazinda parametrik tolerans (2.8.2'deki sabit "
        "±0.0005 mm kuralinin bu fazda reddedildigi ilkesiyle tutarli)."
    )
    a(
        "- Cikti: salt-okunur bir fark raporu; hicbir kosulda "
        "`washer_library.json` yazmaz."
    )
    a(
        "- Bu mimari, saglandiginda ayri bir fazda, tam test "
        "kapsamiyla birlikte gercek bir modul olarak eklenmelidir -- "
        "bu fazda olu kod/iskelet birakilmadi."
    )
    text = "\n".join(lines)
    return text.rstrip("\n") + "\n"


def run(output_dir: Path | None) -> int:
    try:
        library, manifest = load_inputs()
        joined = validate_and_join(library, manifest)
    except ProvenanceConsistencyError as exc:
        print(f"FAIL: provenance manifest/library inconsistency: {exc}", file=sys.stderr)
        return 1

    summary = summarize(joined)

    print("Faz 2.8.4 - Washer Library Provenance Summary")
    print(f"  Total records: {summary['total_records']}")
    for cat in ALLOWED_CATEGORIES:
        print(f"  {cat}: {summary['category_totals'][cat]}")
    print("  Reason codes:")
    for reason in ALLOWED_REASON_CODES:
        print(f"    {reason}: {summary['reason_totals'][reason]}")

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "phase_2_8_4_washer_provenance_report.md"
        json_path = output_dir / "phase_2_8_4_washer_provenance_report.json"
        md_path.write_text(render_markdown_report(joined, summary), encoding="utf-8")
        json_path.write_text(render_json_report(joined, summary), encoding="utf-8")
        print(f"Wrote {md_path}")
        print(f"Wrote {json_path}")

    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="If given, write deterministic MD+JSON reports to this directory. "
        "Default: print summary to stdout only, write nothing.",
    )
    args = parser.parse_args(argv)
    return run(args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
