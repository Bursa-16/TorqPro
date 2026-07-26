"""TorqPro Engineering Library - Faz 2.8.5 washer resolution report.

Additive aggregate report over the washer library's provenance
(Faz 2.8.4) and correction/resolution ledger (Faz 2.8.5) state.
Follows the collector/renderer separation already established by
``backend/calculation_engine/strength_class_report.py`` and
``backend/calculation_engine/friction_report.py`` (Faz 2.8.3 / 2.6.5):
``collect_washer_resolution_report`` reads the domain data exactly
once and returns a frozen, JSON-safe dict; the two ``render_*``
functions only format an already-collected report -- neither
re-derives anything nor mutates ``washer_library.json`` or the
resolution ledger.

Deliberately **not** timestamped (unlike the two calculation-engine
reports above, which do stamp ``generated_at`` with
``datetime.now()``): this report must be byte-for-byte reproducible
across repeated calls against the same inputs, so callers can assert
determinism directly (see ``tests/test_faz_2_8_5_washer_correction_workflow.py``).
A caller that needs a timestamp can attach one outside this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from . import washer_resolution as wr

_DATA_DIR = Path(__file__).resolve().parent / "data"
WASHER_LIBRARY_PATH = _DATA_DIR / "washer_library.json"
_REPO_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE_REPORT_PATH = (
    _REPO_ROOT / "docs" / "phase_2_8" / "phase_2_8_4_washer_provenance_report.json"
)


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def collect_washer_resolution_report() -> Dict[str, Any]:
    """Collect one washer resolution report snapshot. Reads
    ``washer_library.json``, the Faz 2.8.4 provenance report, and the
    Faz 2.8.5 resolution ledger exactly once each; the returned dict
    is a frozen projection, never re-derived by the renderers."""
    library_payload = _load_json(WASHER_LIBRARY_PATH)
    provenance_report = _load_json(PROVENANCE_REPORT_PATH)

    total_washer_records = len(library_payload.get("records", []))
    category_totals = provenance_report.get("summary", {}).get("category_totals", {})

    resolutions = wr.list_washer_resolutions()
    status_counts = wr.count_by_status()
    issue_type_counts = wr.count_by_issue_type()

    confidence_distribution: Dict[str, int] = {}
    for record in resolutions:
        key = str(record.confidence_level.value) if record.confidence_level else "unset"
        confidence_distribution[key] = confidence_distribution.get(key, 0) + 1

    unresolved = sorted(
        (
            {
                "resolution_id": r.resolution_id,
                "washer_record_id": r.washer_record_id,
                "issue_type": r.issue_type.value,
                "resolution_status": r.resolution_status.value,
                "requires_authoritative_source": r.requires_authoritative_source,
            }
            for r in wr.unresolved_washer_resolutions()
        ),
        key=lambda row: row["washer_record_id"],
    )

    return {
        "total_washer_records": total_washer_records,
        "provenance_category_totals": dict(sorted(category_totals.items())),
        "verified_record_count": category_totals.get("standard_verified", 0),
        "action_needed_record_count": category_totals.get("action_needed", 0),
        "resolution_status_counts": status_counts,
        "open_resolution_count": status_counts.get("open", 0),
        "resolved_count": status_counts.get("resolved", 0),
        "blocked_authoritative_source_count": status_counts.get(
            "blocked_authoritative_source", 0
        ),
        "issue_type_distribution": issue_type_counts,
        "confidence_distribution": dict(sorted(confidence_distribution.items())),
        "unresolved_records": unresolved,
        "unresolved_count": len(unresolved),
        "total_resolution_entries": len(resolutions),
    }


def render_washer_resolution_report_json(report: Dict[str, Any]) -> str:
    """Deterministic JSON rendering of an already-collected report
    (stable key order, no timestamps, no absolute paths)."""
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def render_washer_resolution_report_markdown(report: Dict[str, Any]) -> str:
    """Deterministic Markdown rendering of an already-collected
    report."""
    lines: List[str] = []
    a = lines.append

    a("# Faz 2.8.5 - Washer Correction & Resolution Report")
    a("")
    a(
        "Bu rapor `washer_library.json` icindeki hicbir alani "
        "degistirmez; yalnizca Faz 2.8.4 provenance bulgularini ve "
        "Faz 2.8.5 resolution ledger durumunu ozetler."
    )
    a("")

    a("## Genel durum")
    a("")
    a("| Metrik | Deger |")
    a("|---|---:|")
    a(f"| Toplam washer kaydi | {report['total_washer_records']} |")
    a(f"| Verified kayit sayisi | {report['verified_record_count']} |")
    a(f"| Action needed kayit sayisi | {report['action_needed_record_count']} |")
    a(f"| Toplam resolution kaydi | {report['total_resolution_entries']} |")
    a(f"| Open resolution sayisi | {report['open_resolution_count']} |")
    a(f"| Resolved sayisi | {report['resolved_count']} |")
    a(
        "| Blocked (authoritative source) sayisi | "
        f"{report['blocked_authoritative_source_count']} |"
    )
    a(f"| Unresolved (aktif) kayit sayisi | {report['unresolved_count']} |")
    a("")

    a("## Provenance kategori dagilimi (Faz 2.8.4)")
    a("")
    a("| Kategori | Kayit |")
    a("|---|---:|")
    for category, count in report["provenance_category_totals"].items():
        a(f"| `{category}` | {count} |")
    a("")

    a("## Resolution status dagilimi")
    a("")
    a("| Status | Kayit |")
    a("|---|---:|")
    for status, count in report["resolution_status_counts"].items():
        a(f"| `{status}` | {count} |")
    a("")

    a("## Issue type dagilimi")
    a("")
    a("| Issue type | Kayit |")
    a("|---|---:|")
    for issue_type, count in report["issue_type_distribution"].items():
        a(f"| `{issue_type}` | {count} |")
    a("")

    a("## Confidence dagilimi (resolution kayitlari)")
    a("")
    a("| Confidence | Kayit |")
    a("|---|---:|")
    for level, count in report["confidence_distribution"].items():
        a(f"| `{level}` | {count} |")
    a("")

    a("## Unresolved kayit listesi")
    a("")
    a("| Resolution ID | Washer Record ID | Issue Type | Status | Requires Authoritative Source |")
    a("|---|---|---|---|---|")
    for row in report["unresolved_records"]:
        a(
            f"| {row['resolution_id']} | {row['washer_record_id']} | "
            f"`{row['issue_type']}` | `{row['resolution_status']}` | "
            f"{row['requires_authoritative_source']} |"
        )
    a("")

    text = "\n".join(lines)
    return text.rstrip("\n") + "\n"


__all__ = [
    "WASHER_LIBRARY_PATH",
    "PROVENANCE_REPORT_PATH",
    "collect_washer_resolution_report",
    "render_washer_resolution_report_json",
    "render_washer_resolution_report_markdown",
]
