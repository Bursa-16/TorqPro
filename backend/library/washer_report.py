"""TorqPro Engineering Library - Faz 2.8.5 washer resolution report,
extended in Faz 2.8.9 Stage 4 with effective-status reporting.

Additive aggregate report over the washer library's provenance
(Faz 2.8.4) and correction/resolution ledger (Faz 2.8.5) state.
Follows the collector/renderer separation already established by
``backend/calculation_engine/strength_class_report.py`` and
``backend/calculation_engine/friction_report.py`` (Faz 2.8.3 / 2.6.5):
``collect_washer_resolution_report`` reads the domain data exactly
once and returns a frozen, JSON-safe dict; the render functions only
format an already-collected report -- neither re-derives anything nor
mutates ``washer_library.json`` or the resolution ledger.

Deliberately **not** timestamped (unlike the two calculation-engine
reports above, which do stamp ``generated_at`` with
``datetime.now()``): this report must be byte-for-byte reproducible
across repeated calls against the same inputs, so callers can assert
determinism directly (see ``tests/test_faz_2_8_5_washer_correction_workflow.py``
and, for the Stage 4 additions, ``tests/test_faz_2_8_9_stage4_report.py``).
A caller that needs a timestamp can attach one outside this module.

Faz 2.8.9 Stage 4 additions (additive only -- no existing key removed
or renamed): open/under_review/terminal/blocked counts and a
``resolved`` count computed from **effective status** -- the Faz
2.8.9 decision ledger's overlay on top of the Faz 2.8.5 source
ledger, never a mutation of it. This module never invents its own
status vocabulary or transition rules: every status value and the
terminal/blocked classification come from
``backend.library.washer_resolution.WasherResolutionStatus`` /
``TERMINAL_STATUSES``, and every effective-status computation is
delegated to ``backend.library.washer_resolution_service`` (Stage 3)
-- this module aggregates and formats, it never recomputes state-
machine logic itself. ``resolved_count`` here can only be non-zero if
a real terminal decision (``new_status == "resolved"``) was actually
recorded in the Faz 2.8.9 decision ledger; it is never inferred,
estimated, or defaulted from the source ledger's static status.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from . import washer_resolution as wr
from . import washer_resolution_service as workflow_service
from .washer_resolution_decisions_store import decisions_for_resolution

_DATA_DIR = Path(__file__).resolve().parent / "data"
WASHER_LIBRARY_PATH = _DATA_DIR / "washer_library.json"
_REPO_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE_REPORT_PATH = (
    _REPO_ROOT / "docs" / "phase_2_8" / "phase_2_8_4_washer_provenance_report.json"
)


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class WasherReportDataError(Exception):
    """Raised when the Faz 2.8.9 decision ledger cannot be read or
    parsed (e.g. corrupted JSON, a record failing schema validation).
    Deliberately carries a fixed, generic message -- never the
    original exception's text, which could contain a file path --
    so a caller (a future API layer) can surface this safely without
    risking a path/traceback leak. The original exception is still
    available server-side via ``__cause__``/``__context__`` for
    logging."""


def _report_checksum(report_without_checksum: Dict[str, Any]) -> str:
    """Canonical project checksum (sha256 over
    ``json.dumps(..., sort_keys=True, ensure_ascii=False)``) -- the
    same algorithm used by
    ``backend.library.washer_resolution_decisions_store.compute_integrity_checksum``
    and ``backend.library.population.find_checksum_mismatches``, so a
    reader familiar with either already knows how to verify this
    report's ``report_checksum`` field independently."""
    canonical = json.dumps(report_without_checksum, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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

    # --- Faz 2.8.9 Stage 4: effective-status aggregation ---------------
    # Delegates entirely to washer_resolution_service.resolution_queue()
    # (Stage 3, already-tested public accessor) -- this module never
    # recomputes effective status or state-machine legality itself, and
    # never reads washer_resolution_ledger.json's resolution_status as
    # if it could have changed (it cannot: see that module's docstring).
    try:
        queue_rows = workflow_service.resolution_queue()
    except Exception:
        raise WasherReportDataError(
            "Washer resolution decision data could not be read; "
            "report cannot be generated."
        ) from None

    effective_status_distribution: Dict[str, int] = {
        status.value: 0 for status in wr.WasherResolutionStatus
    }
    under_review_count = 0
    terminal_count = 0
    resolved_count_effective = 0
    blocked_count_effective = 0
    open_count_effective = 0
    total_decision_count = 0
    latest_decision_summary: List[Dict[str, Any]] = []
    data_integrity_warning_count = 0

    for row in sorted(queue_rows, key=lambda r: r["resolution_id"]):
        effective_status_distribution[row["effective_status"]] += 1
        total_decision_count += row["decision_count"]

        if row["is_blocked"]:
            blocked_count_effective += 1
        elif row["is_terminal"]:
            terminal_count += 1
            if row["effective_status"] == wr.WasherResolutionStatus.RESOLVED.value:
                resolved_count_effective += 1
        elif row["effective_status"] == wr.WasherResolutionStatus.UNDER_REVIEW.value:
            under_review_count += 1
        elif row["effective_status"] == wr.WasherResolutionStatus.OPEN.value:
            open_count_effective += 1

        if row["decision_count"] > 0:
            try:
                history = decisions_for_resolution(row["resolution_id"])
            except Exception:
                data_integrity_warning_count += 1
                continue
            if not history:
                continue
            last = history[-1]
            latest_decision_summary.append(
                {
                    "resolution_id": row["resolution_id"],
                    "effective_status": row["effective_status"],
                    "decision_count": row["decision_count"],
                    "last_decision_new_status": last.new_status.value,
                    "last_decided_at": last.decided_at,
                    "last_resolved_by": last.resolved_by,
                }
            )

    latest_decision_summary.sort(key=lambda row: row["resolution_id"])

    report: Dict[str, Any] = {
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
        # --- Faz 2.8.9 Stage 4: effective-status fields (additive) ---
        "total_resolution_records": len(queue_rows),
        "source_status_distribution": dict(sorted(status_counts.items())),
        "effective_status_distribution": dict(sorted(effective_status_distribution.items())),
        "effective_open_count": open_count_effective,
        "effective_under_review_count": under_review_count,
        "effective_terminal_count": terminal_count,
        "effective_blocked_count": blocked_count_effective,
        "effective_resolved_count": resolved_count_effective,
        "total_decision_count": total_decision_count,
        "latest_decision_summary": latest_decision_summary,
        "data_integrity_warning_count": data_integrity_warning_count,
    }
    report["report_checksum"] = _report_checksum(report)
    return report


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
    a(f"| Rapor checksum (sha256) | `{report['report_checksum']}` |")
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

    a("## Efektif durum dagilimi (Faz 2.8.9 karar ledger'i uzerinden)")
    a("")
    a(
        "`washer_resolution_ledger.json` (kaynak) hicbir zaman "
        "degistirilmez. Asagidaki efektif durum, o kaynagin uzerine "
        "Faz 2.8.9 karar ledger'inin (append-only) en son kaydinin "
        "bindirilmesiyle hesaplanir; karar yoksa kaynak durum aynen "
        "kullanilir."
    )
    a("")
    a("| Metrik | Deger |")
    a("|---|---:|")
    a(f"| Toplam resolution kaydi | {report['total_resolution_records']} |")
    a(f"| Open (efektif) | {report['effective_open_count']} |")
    a(f"| Under review (efektif) | {report['effective_under_review_count']} |")
    a(f"| Terminal (efektif) | {report['effective_terminal_count']} |")
    a(f"| Blocked (efektif) | {report['effective_blocked_count']} |")
    a(
        "| Resolved (yalnizca gercek terminal kararlardan) | "
        f"{report['effective_resolved_count']} |"
    )
    a(f"| Toplam karar (decision) sayisi | {report['total_decision_count']} |")
    a("")
    a(
        "*Not:* \"Resolved (yalnizca gercek terminal kararlardan)\" "
        "sayisi, Faz 2.8.9 karar ledger'inde `new_status=resolved` "
        "olarak gercekten kaydedilmis kararlarin sayisidir; hicbir "
        "kayit tahmin veya varsayimla \"resolved\" sayilmaz."
    )
    a("")

    a("### Efektif durum dagilim tablosu (tum degerler)")
    a("")
    a("| Efektif status | Kayit |")
    a("|---|---:|")
    for status, count in report["effective_status_distribution"].items():
        a(f"| `{status}` | {count} |")
    a("")

    if report["latest_decision_summary"]:
        a("### Son karar ozeti (karari olan kayitlar)")
        a("")
        a(
            "| Resolution ID | Efektif Status | Karar Sayisi | Son Karar | "
            "Karar Zamani (UTC) | Karari Veren |"
        )
        a("|---|---|---:|---|---|---|")
        for row in report["latest_decision_summary"]:
            a(
                f"| {row['resolution_id']} | `{row['effective_status']}` | "
                f"{row['decision_count']} | `{row['last_decision_new_status']}` | "
                f"{row['last_decided_at']} | {row['last_resolved_by']} |"
            )
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


def render_washer_resolution_report_markdown_en(report: Dict[str, Any]) -> str:
    """English-language counterpart of
    :func:`render_washer_resolution_report_markdown`, covering the
    exact same sections in the same order (TR/EN parity) -- added in
    Faz 2.8.9 Stage 4, since all new report content in this project
    must ship bilingual from the start (the rule established in Faz
    2.8.8; the pre-existing Faz 2.8.5 Turkish-only sections are
    reproduced here in English rather than left out, so a reader
    switching language does not lose any section)."""
    lines: List[str] = []
    a = lines.append

    a("# Faz 2.8.5 - Washer Correction & Resolution Report")
    a("")
    a(
        "This report never modifies any field inside "
        "`washer_library.json`; it only summarizes the Faz 2.8.4 "
        "provenance findings and the Faz 2.8.5/2.8.9 resolution "
        "ledger state."
    )
    a("")

    a("## Overview")
    a("")
    a("| Metric | Value |")
    a("|---|---:|")
    a(f"| Total washer records | {report['total_washer_records']} |")
    a(f"| Verified record count | {report['verified_record_count']} |")
    a(f"| Action-needed record count | {report['action_needed_record_count']} |")
    a(f"| Total resolution records | {report['total_resolution_entries']} |")
    a(f"| Open resolution count (source) | {report['open_resolution_count']} |")
    a(f"| Resolved count (source) | {report['resolved_count']} |")
    a(
        "| Blocked (authoritative source) count | "
        f"{report['blocked_authoritative_source_count']} |"
    )
    a(f"| Unresolved (active) record count | {report['unresolved_count']} |")
    a(f"| Report checksum (sha256) | `{report['report_checksum']}` |")
    a("")

    a("## Provenance category distribution (Faz 2.8.4)")
    a("")
    a("| Category | Records |")
    a("|---|---:|")
    for category, count in report["provenance_category_totals"].items():
        a(f"| `{category}` | {count} |")
    a("")

    a("## Resolution status distribution (source)")
    a("")
    a("| Status | Records |")
    a("|---|---:|")
    for status, count in report["resolution_status_counts"].items():
        a(f"| `{status}` | {count} |")
    a("")

    a("## Issue type distribution")
    a("")
    a("| Issue type | Records |")
    a("|---|---:|")
    for issue_type, count in report["issue_type_distribution"].items():
        a(f"| `{issue_type}` | {count} |")
    a("")

    a("## Confidence distribution (resolution records)")
    a("")
    a("| Confidence | Records |")
    a("|---|---:|")
    for level, count in report["confidence_distribution"].items():
        a(f"| `{level}` | {count} |")
    a("")

    a("## Effective status distribution (via the Faz 2.8.9 decision ledger)")
    a("")
    a(
        "`washer_resolution_ledger.json` (the source ledger) is never "
        "modified. The effective status below is computed by "
        "overlaying the most recent entry of the Faz 2.8.9 append-only "
        "decision ledger on top of that source; if no decision exists "
        "for a record, its source status is used as-is."
    )
    a("")
    a("| Metric | Value |")
    a("|---|---:|")
    a(f"| Total resolution records | {report['total_resolution_records']} |")
    a(f"| Open (effective) | {report['effective_open_count']} |")
    a(f"| Under review (effective) | {report['effective_under_review_count']} |")
    a(f"| Terminal (effective) | {report['effective_terminal_count']} |")
    a(f"| Blocked (effective) | {report['effective_blocked_count']} |")
    a(
        "| Resolved (from real terminal decisions only) | "
        f"{report['effective_resolved_count']} |"
    )
    a(f"| Total decision count | {report['total_decision_count']} |")
    a("")
    a(
        "*Note:* the \"Resolved (from real terminal decisions only)\" "
        "count is the number of records with an actually recorded "
        "`new_status=resolved` decision in the Faz 2.8.9 decision "
        "ledger; no record is ever counted as resolved by inference "
        "or assumption."
    )
    a("")

    a("### Effective status distribution table (all values)")
    a("")
    a("| Effective status | Records |")
    a("|---|---:|")
    for status, count in report["effective_status_distribution"].items():
        a(f"| `{status}` | {count} |")
    a("")

    if report["latest_decision_summary"]:
        a("### Latest decision summary (records with at least one decision)")
        a("")
        a(
            "| Resolution ID | Effective Status | Decision Count | "
            "Last Decision | Decided At (UTC) | Decided By |"
        )
        a("|---|---|---:|---|---|---|")
        for row in report["latest_decision_summary"]:
            a(
                f"| {row['resolution_id']} | `{row['effective_status']}` | "
                f"{row['decision_count']} | `{row['last_decision_new_status']}` | "
                f"{row['last_decided_at']} | {row['last_resolved_by']} |"
            )
        a("")

    a("## Unresolved record list")
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
    "WasherReportDataError",
    "collect_washer_resolution_report",
    "render_washer_resolution_report_json",
    "render_washer_resolution_report_markdown",
    "render_washer_resolution_report_markdown_en",
]
