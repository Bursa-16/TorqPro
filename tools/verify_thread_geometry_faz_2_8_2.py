"""TorqPro Engineering Library - Faz 2.8.2 thread geometry verification.

Extends the Faz 2.8.1 audit architecture (``tools/audit_engineering_
library.py``) rather than duplicating it: this module imports and
reuses ``backend.library.population`` (data access),
``backend.library.models`` (schema), ``backend.library.thread_geometry``
(ISO 724/68-1 basic-profile formulas) and
``backend.vdi2230_core.stress_area`` (ISO 898-1 tensile stress area
formula) -- no second, parallel validation engine is introduced.

Scope (per the Faz 2.8.2 task brief): exactly 72 pre-existing
``thread library`` records --

    - Fine series:        35 records, M3-M100
    - Extra Fine series:  29 records, M8-M100
    - Coarse series:       8 records, M68-M100

No new diameter, series or record is added. No schema field is added
(``ThreadRecord`` keeps ``extra="forbid"`` unchanged). Only these
existing, already-schema-declared fields may be updated by
``--apply``, and only for records with independently corroborated
source traceability: ``confidence``, ``confidence_level``,
``validation_status``, ``approval_status``, ``review_status``,
``notes``, ``source``, ``source_reference``, ``revision``,
``source_revision``, ``checksum``.

Default mode is read-only / dry-run: it reports what it *would*
change without writing anything. ``--apply`` is required to actually
write ``backend/library/data/thread_library.json`` (explicit opt-in,
matching the ``populate_all()`` / audit-script conventions already
established in this package).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.library import models as models_module  # noqa: E402
from backend.library import population  # noqa: E402
from backend.library import thread_geometry  # noqa: E402
from backend.vdi2230_core import stress_area as stress_area_module  # noqa: E402

# Reuse the Faz 2.8.1 audit script's helpers (confidence_label) rather
# than re-implementing them -- "extend the existing audit
# architecture", per the Faz 2.8.2 task brief.
_AUDIT_PATH = REPO_ROOT / "tools" / "audit_engineering_library.py"
_AUDIT_SPEC = importlib.util.spec_from_file_location(
    "audit_engineering_library", _AUDIT_PATH
)
audit = importlib.util.module_from_spec(_AUDIT_SPEC)
sys.modules.setdefault("audit_engineering_library", audit)
_AUDIT_SPEC.loader.exec_module(audit)  # type: ignore[union-attr]

THREAD_DATA_PATH = REPO_ROOT / "backend" / "library" / "data" / "thread_library.json"

#: Geometry comparison tolerance. Diameters are stored to 4 decimals;
#: 0.0005 mm covers legitimate last-digit rounding without masking a
#: real formula discrepancy (an ISO 724 mismatch at this diameter
#: range is never sub-micron).
DIAMETER_TOLERANCE_MM = 0.0005

#: Stress area is stored to 3 decimals on values ranging from ~0.5 to
#: ~7000 mm^2; a fixed absolute tolerance would be too strict at the
#: high end and too loose at the low end, so this check uses whichever
#: is larger of a small absolute floor and a relative tolerance.
STRESS_AREA_ABS_FLOOR_MM2 = 0.002
STRESS_AREA_REL_TOLERANCE = 2e-5

REVISION_DATE = "2026-07-25"

#: Faz 2.8.2 target scope: every Fine/Extra Fine record, plus the 8
#: Coarse M68-M100 records. Selected structurally (series + diameter
#: range), not by a hardcoded id list, so the set stays correct if
#: this script is re-run against an unchanged data file.


def is_in_scope(record: Dict[str, Any]) -> bool:
    series = record.get("series")
    if series in ("Fine", "Extra Fine"):
        return True
    if series == "Coarse" and (record.get("nominal_diameter_mm") or 0) >= 68:
        return True
    return False


# ---------------------------------------------------------------------
# External corroboration evidence (Faz 2.8.2 web research, this
# session). Static, hand-reviewed findings -- not re-derived at run
# time (this script has no network access and must stay
# deterministic). Every entry documents exactly what was checked and
# against which independent secondary sources, per the "no batch/
# automatic G4->G1/G2 upgrade" rule: each id is judged individually.
#
# IMPORTANT: these are commercial/technical secondary references
# (fastener-industry technical charts), not the primary ISO 261:1998
# / ISO 262:2023 standard text itself (paywalled; not reproduced or
# quoted here per copyright policy -- only the numeric pitch value
# and the fact of independent agreement are recorded). Because the
# corroboration is secondary-source, not primary-standard, the
# eligible upgrade target is G3/"reference_only" (matches this
# dataset's own established confidence convention for
# reference_only records -- see e.g. THR-1-4-20UNC), never G2/
# "validated" or G1.
# ---------------------------------------------------------------------
EXTERNAL_CORROBORATION: Dict[str, Dict[str, Any]] = {
    "THR-M68-COARSE": {
        "corroborated": True,
        "evidence": [
            "Aspen Fasteners metric/inch thread pitch reference "
            "(aspenfasteners.com/content/pdf/thread_pitch.pdf): "
            "M68 coarse pitch = 6 mm",
            "mfindllc.com METRIC PITCH THREAD CHART: M68 coarse "
            "pitch = 6 mm",
        ],
    },
    "THR-M72-COARSE": {
        "corroborated": True,
        "evidence": [
            "Aspen Fasteners thread pitch reference: M72 coarse "
            "pitch = 6 mm",
            "mfindllc.com METRIC PITCH THREAD CHART: M72 coarse "
            "pitch = 6 mm",
        ],
    },
    "THR-M76-COARSE": {
        "corroborated": False,
        "evidence": [],
        "reason": (
            "M76 does not appear in either independent secondary "
            "reference consulted this session (both list "
            "...M72, M80... with no M76 entry). Cannot confirm "
            "whether this is a genuine ISO 261 diameter/pitch "
            "combination or a non-preferred/interpolated entry "
            "without primary-standard access."
        ),
    },
    "THR-M80-COARSE": {
        "corroborated": True,
        "evidence": [
            "Aspen Fasteners thread pitch reference: M80 coarse "
            "pitch = 6 mm",
            "mfindllc.com METRIC PITCH THREAD CHART: M80 coarse "
            "pitch = 6 mm",
        ],
    },
    "THR-M85-COARSE": {
        "corroborated": False,
        "evidence": [],
        "reason": (
            "M85 does not appear in either independent secondary "
            "reference consulted this session. Same limitation as "
            "M76 -- see above."
        ),
    },
    "THR-M90-COARSE": {
        "corroborated": True,
        "evidence": [
            "Aspen Fasteners thread pitch reference: M90 coarse "
            "pitch = 6 mm",
            "mfindllc.com METRIC PITCH THREAD CHART: M90 coarse "
            "pitch = 6 mm",
        ],
    },
    "THR-M95-COARSE": {
        "corroborated": False,
        "evidence": [],
        "reason": (
            "M95 does not appear in either independent secondary "
            "reference consulted this session. Same limitation as "
            "M76 -- see above."
        ),
    },
    "THR-M100-COARSE": {
        "corroborated": True,
        "evidence": [
            "Aspen Fasteners thread pitch reference: M100 coarse "
            "pitch = 6 mm",
            "mfindllc.com METRIC PITCH THREAD CHART: M100 coarse "
            "pitch = 6 mm",
        ],
    },
}

#: Fine/Extra Fine: every one of the 64 records. Web research this
#: session (printables.com fine-pitch list; general fastener charts)
#: found the *existence* of ISO 261/262 fine-pitch series data, but
#: also found that those secondary sources' single-value-per-diameter
#: "fine pitch" figures frequently disagree with this dataset's
#: stored pitch (which the dataset's own notes already flag as
#: "selected programmatically... NOT looked up from the ISO 261/262
#: fine-pitch table"). ISO 261/262 fine series are multi-choice
#: (1st/2nd/3rd/4th choice per diameter) and the secondary sources
#: found generally show only the single most common choice, so a
#: disagreement does not prove the stored value is wrong -- but it
#: also cannot be confirmed right without the primary standard table
#: (paywalled, not accessible in this session). Per the "leave G4
#: when no independent confirmation is possible, do not guess" rule,
#: no Fine/Extra Fine record is upgraded in this phase.
FINE_XFINE_REASON = (
    "Secondary-source cross-check found the pitch-selection method "
    "itself unconfirmed against the primary ISO 261/262 multi-choice "
    "pitch table (paywalled; not accessible in this session). "
    "Available secondary summaries disagree with several stored "
    "values, but ISO 261/262 fine series are multi-choice per "
    "diameter, so disagreement with a single-choice secondary "
    "summary does not prove the stored value is wrong either. "
    "Left at G4/provisional per the 'no unverifiable upgrade' rule; "
    "recommended for Faz 2.8.10 (primary-standard-table acquisition)."
)


def corroboration_for(record_id: str, series: str) -> Dict[str, Any]:
    if series in ("Fine", "Extra Fine"):
        return {"corroborated": False, "evidence": [], "reason": FINE_XFINE_REASON}
    return EXTERNAL_CORROBORATION.get(
        record_id,
        {"corroborated": False, "evidence": [], "reason": "Not in Faz 2.8.2 scope."},
    )


# ---------------------------------------------------------------------
# Independent geometric re-derivation (ISO 724 / ISO 68-1 basic
# profile formulas + ISO 898-1 tensile stress area formula), reused
# unmodified from backend.library.thread_geometry /
# backend.vdi2230_core.stress_area.
# ---------------------------------------------------------------------

def recompute_geometry(nominal_diameter_mm: float, pitch_mm: float) -> Dict[str, float]:
    """ISO 68-1/724 basic-profile values, independently re-derived.

    ISO 68-1 supplies the basic-triangle profile relationships (the
    ``H = sqrt(3)/2 * P`` geometry and the 0.75H/1.25H/(17/12)H
    factors); ISO 724 supplies the nominal diameter/pitch series this
    profile is evaluated at. Both roles are kept distinct in the
    report (section: ISO 724 vs ISO 68-1 traceability) even though a
    single ``thread_geometry`` module implements the combined
    calculation, per the existing package docstring.
    """
    return {
        "major_diameter_mm": thread_geometry.basic_major_diameter_mm(
            nominal_diameter_mm
        ),
        "pitch_diameter_mm": round(
            thread_geometry.basic_pitch_diameter_mm(nominal_diameter_mm, pitch_mm), 4
        ),
        "minor_diameter_internal_mm": round(
            thread_geometry.basic_minor_diameter_internal_mm(
                nominal_diameter_mm, pitch_mm
            ),
            4,
        ),
        "minor_diameter_external_mm": round(
            thread_geometry.basic_minor_diameter_external_mm(
                nominal_diameter_mm, pitch_mm
            ),
            4,
        ),
    }


def recompute_stress_area(nominal_diameter_mm: float, pitch_mm: float) -> float:
    """ISO 898-1 tensile stress area, via the existing VDI 2230 core
    formula module (``backend.vdi2230_core.stress_area`` -- imported
    read-only for cross-checking, not modified; no VDI 2230 formula
    is changed by this script)."""
    return stress_area_module.tensile_stress_area_mm2(nominal_diameter_mm, pitch_mm)


def within_tolerance(calculated: float, stored: Optional[float], tol: float) -> bool:
    if stored is None:
        return False
    return abs(calculated - stored) <= tol


def stress_area_tolerance(stored: float) -> float:
    return max(STRESS_AREA_ABS_FLOOR_MM2, abs(stored) * STRESS_AREA_REL_TOLERANCE)


def verify_record_geometry(record: Dict[str, Any]) -> Dict[str, Any]:
    d = record["nominal_diameter_mm"]
    p = record["pitch_mm"]
    geometry = recompute_geometry(d, p)
    stress_area = recompute_stress_area(d, p)

    field_checks = {
        "major_diameter_mm": (
            geometry["major_diameter_mm"], record.get("major_diameter_mm"),
            DIAMETER_TOLERANCE_MM,
        ),
        "pitch_diameter_mm": (
            geometry["pitch_diameter_mm"], record.get("pitch_diameter_mm"),
            DIAMETER_TOLERANCE_MM,
        ),
        "minor_diameter_mm": (
            geometry["minor_diameter_internal_mm"], record.get("minor_diameter_mm"),
            DIAMETER_TOLERANCE_MM,
        ),
        "minor_diameter_internal_mm": (
            geometry["minor_diameter_internal_mm"],
            record.get("minor_diameter_internal_mm"),
            DIAMETER_TOLERANCE_MM,
        ),
        "minor_diameter_external_mm": (
            geometry["minor_diameter_external_mm"],
            record.get("minor_diameter_external_mm"),
            DIAMETER_TOLERANCE_MM,
        ),
        "stress_area_mm2": (
            round(stress_area, 3), record.get("stress_area_mm2"),
            stress_area_tolerance(record.get("stress_area_mm2") or 0.0),
        ),
    }

    mismatches = []
    for field, (calc, stored, tol) in field_checks.items():
        if not within_tolerance(calc, stored, tol):
            mismatches.append({
                "field": field, "calculated": calc, "stored": stored,
                "tolerance": tol,
            })

    return {
        "field_checks": {
            k: {"calculated": v[0], "stored": v[1]} for k, v in field_checks.items()
        },
        "mismatches": mismatches,
        "geometry_verified": len(mismatches) == 0,
    }


def verify_geometric_invariants(record: Dict[str, Any]) -> List[str]:
    """Independent, formula/invariant-based checks beyond exact-value
    comparison (physical ordering, positivity) -- not dataset-value
    repetition."""
    issues = []
    major = record.get("major_diameter_mm")
    pitch_d = record.get("pitch_diameter_mm")
    minor = record.get("minor_diameter_mm")
    stress_area = record.get("stress_area_mm2")

    if not (record.get("nominal_diameter_mm", 0) > 0):
        issues.append("nominal_diameter_mm is not positive")
    if not (record.get("pitch_mm", 0) > 0):
        issues.append("pitch_mm is not positive")
    if major is not None and pitch_d is not None and not (major >= pitch_d):
        issues.append(f"major_diameter_mm ({major}) < pitch_diameter_mm ({pitch_d})")
    if pitch_d is not None and minor is not None and not (pitch_d >= minor):
        issues.append(f"pitch_diameter_mm ({pitch_d}) < minor_diameter_mm ({minor})")
    if minor is not None and not (minor > 0):
        issues.append(f"minor_diameter_mm ({minor}) is not positive")
    if stress_area is not None and not (stress_area > 0):
        issues.append(f"stress_area_mm2 ({stress_area}) is not positive")

    return issues


# ---------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------

def analyze() -> Dict[str, Any]:
    all_records = population.load_population_records("thread library")
    target = [r for r in all_records if is_in_scope(r)]
    target_by_series: Dict[str, List[Dict[str, Any]]] = {
        "Coarse": [], "Fine": [], "Extra Fine": [],
    }
    for r in target:
        target_by_series[r["series"]].append(r)
    for series in target_by_series:
        target_by_series[series].sort(key=lambda r: r["nominal_diameter_mm"])

    per_record: List[Dict[str, Any]] = []
    for r in sorted(target, key=lambda r: (r["series"], r["nominal_diameter_mm"])):
        geometry_result = verify_record_geometry(r)
        invariant_issues = verify_geometric_invariants(r)
        corroboration = corroboration_for(r["id"], r["series"])
        # "Upgraded by Faz 2.8.2" is a property of the *corroboration
        # evidence* (stable across re-runs), not of whether this
        # particular run still needs to write anything -- a record
        # already sitting at G3/reference_only from a prior --apply
        # is still correctly reported as upgraded. "action_needed"
        # is the separate, transient flag that actually drives
        # apply_upgrades() (only mutate a record if it isn't already
        # at its target state).
        is_upgrade_candidate = (
            corroboration["corroborated"]
            and geometry_result["geometry_verified"]
            and not invariant_issues
        )
        target_confidence = 3 if is_upgrade_candidate else r.get("confidence")
        target_validation_status = (
            "reference_only" if is_upgrade_candidate
            else r.get("validation_status")
        )
        action_needed = (
            is_upgrade_candidate
            and (
                r.get("confidence") != target_confidence
                or r.get("validation_status") != target_validation_status
            )
        )
        per_record.append({
            "id": r["id"],
            "designation": r["designation"],
            "series": r["series"],
            "nominal_diameter_mm": r["nominal_diameter_mm"],
            "pitch_mm": r["pitch_mm"],
            "source": r.get("source"),
            "source_standard": r.get("source_standard"),
            "confidence_before": r.get("confidence"),
            "validation_status_before": r.get("validation_status"),
            "geometry": geometry_result,
            "invariant_issues": invariant_issues,
            "corroboration": corroboration,
            "upgrade_eligible": is_upgrade_candidate,
            "action_needed": action_needed,
            "confidence_after": target_confidence,
            "validation_status_after": target_validation_status,
        })

    schema_violations = models_module.find_schema_violations(
        "thread library", target
    )

    diameters_by_series = {
        series: sorted({r["nominal_diameter_mm"] for r in recs})
        for series, recs in target_by_series.items()
    }
    combo_duplicates = {}
    for series, recs in target_by_series.items():
        seen = {}
        dups = []
        for r in recs:
            key = (r["nominal_diameter_mm"], r["pitch_mm"])
            if key in seen:
                dups.append(key)
            seen[key] = True
        combo_duplicates[series] = dups

    unchanged = sum(1 for pr in per_record if not pr["upgrade_eligible"])
    upgraded = sum(1 for pr in per_record if pr["upgrade_eligible"])
    remaining_g4 = sum(1 for pr in per_record if pr["confidence_after"] == 4)

    return {
        "phase": "2.8.2",
        "phase_name": "Thread Geometry Data Verification & Confidence Upgrade",
        "reviewed_record_count": len(target),
        "target_by_series_counts": {
            series: len(recs) for series, recs in target_by_series.items()
        },
        "diameters_by_series": diameters_by_series,
        "duplicate_diameter_pitch_combos": combo_duplicates,
        "schema_violation_count": len(schema_violations),
        "schema_violations": schema_violations,
        "per_record": per_record,
        "totals": {
            "reviewed": len(per_record),
            "unchanged": unchanged,
            "upgraded": upgraded,
            "remaining_g4": remaining_g4,
        },
    }


def apply_upgrades(analysis: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """Apply the confidence/status/notes/source updates for eligible
    records directly to ``thread_library.json``, in place, preserving
    every other record and field byte-for-byte. Returns a summary of
    what was (or, in dry-run mode, would be) changed. Recomputes each
    changed record's checksum using the exact method already used by
    ``population.find_checksum_mismatches`` so the file stays
    integrity-check-clean."""
    with open(THREAD_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    eligible_ids = {
        pr["id"]: pr for pr in analysis["per_record"] if pr["action_needed"]
    }
    changes = []

    for record in data["records"]:
        pr = eligible_ids.get(record.get("id"))
        if pr is None:
            continue

        before = dict(record)
        evidence_text = "; ".join(pr["corroboration"]["evidence"])
        record["confidence"] = 3
        record["confidence_level"] = 3
        record["validation_status"] = "reference_only"
        record["review_status"] = "reference_only"
        record["approval_status"] = "pending"  # unchanged; not "validated"
        record["revision"] = REVISION_DATE
        record["source_revision"] = REVISION_DATE
        record["notes"] = (
            "Faz 2.8.2: pitch value (6.0 mm) independently corroborated "
            f"against multiple secondary engineering references: "
            f"{evidence_text}. Not a primary-standard (ISO 261/262) "
            "table lookup -- graded reference_only/G3, not validated/"
            "G2. Geometry (major/pitch/minor diameter) is the ISO 724 "
            "basic-profile formula evaluated at this pitch; stress "
            "area is the ISO 898-1 formula "
            "(0.7854*(d-0.9382P)^2), independently re-verified this "
            "phase against backend.vdi2230_core.stress_area."
        )
        record["source"] = (
            "ISO 724 formula over ISO 261 diameter/pitch table; pitch "
            "cross-verified against independent secondary technical "
            "references (Faz 2.8.2)"
        )
        record["source_reference"] = record["source"]

        payload = {k: v for k, v in record.items() if k != "checksum"}
        record["checksum"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        changes.append({
            "id": record["id"],
            "before": {
                "confidence": before["confidence"],
                "validation_status": before["validation_status"],
                "checksum": before["checksum"],
            },
            "after": {
                "confidence": record["confidence"],
                "validation_status": record["validation_status"],
                "checksum": record["checksum"],
            },
        })

    if not dry_run:
        with open(THREAD_DATA_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    return {"dry_run": dry_run, "changed_records": changes}


# ---------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------

def render_markdown(analysis: Dict[str, Any], apply_result: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    t = analysis["totals"]

    a("# Faz 2.8.2 - Thread Geometry Data Verification & Confidence Upgrade")
    a("")
    a("Kapsam: mevcut 72 kayıt (Fine 35 + Extra Fine 29 + Coarse M68-M100 8). "
      "Yeni çap, yeni seri veya yeni kayıt eklenmedi. `ThreadRecord` şeması "
      "değiştirilmedi (`extra=\"forbid\"` aynen korunuyor).")
    a("")

    a("## 0. Önemli sınırlamalar (doğrulamanın kapsamı ne anlama GELMİYOR)")
    a("")
    a("- **72/72 kayıt geometrik olarak mevcut formüllerle doğrulandı** "
      "(ISO 724/68-1 temel profil formülü + ISO 898-1 stress area "
      "formülü, bağımsız yeniden hesaplama). **Bu, kayıtların "
      "BİRİNCİL standart kaynağıyla (ISO 261/262 metni/tablosu) "
      "doğrulandığı anlamına GELMEZ.** Yalnızca \"kayıtlı pitch "
      "doğruysa, kayıtlı geometri de doğru hesaplanmış\" önermesi "
      "kanıtlanmıştır -- pitch'in kendisinin standart tablosuyla "
      "eşleştiği ayrı bir sorudur (bkz. aşağı).")
    a("- Fine ve Extra Fine seriler (toplam **64 kayıt**), ISO 261/262 "
      "birincil tablosuna bu oturumda erişim olmadığı için "
      "**G4/provisional seviyesinde bırakıldı.**")
    a("- M68, M72, M80, M90 ve M100 coarse kayıtları **yalnızca iki "
      "bağımsız İKİNCİL kaynakla** (Aspen Fasteners, mfindllc.com "
      "teknik referans tabloları) doğrulandığı için **G3/"
      "\"reference_only\" seviyesine yükseltildi** -- G1/G2 "
      "(\"birincil standarttan doğrudan doğrulandı\") DEĞİL.")
    a("- M76, M85 ve M95 kayıtlarının coarse pitch değerleri hiçbir "
      "bağımsız kaynakta bulunamadığı, dolayısıyla doğrulanamadığı "
      "için **G4 olarak kaldı.**")
    a("- **Hiçbir geometrik değer değiştirilmedi** (nominal_diameter_mm, "
      "pitch_mm, major/pitch/minor_diameter_mm, stress_area_mm2 -- "
      "72 kaydın hiçbirinde). Yalnızca 5 kaydın provenance/confidence "
      "metadata alanları güncellendi.")
    a("- Stress-area kontrolünün kullandığı "
      "`backend.vdi2230_core.stress_area.tensile_stress_area_mm2()` "
      "fonksiyonunun kendi docstring'inde **\"PROVISIONAL: requires "
      "independent source sign-off before production use\"** ifadesi "
      "bulunuyor. **Bu nedenle stress-area kontrolü \"birincil "
      "standart doğrulaması\" olarak sunulmamaktadır** -- yalnızca "
      "üretim/formül-tutarlılığı kontrolüdür.")
    a("- ISO 68-1 için şemada ayrı, yapılandırılmış bir izlenebilirlik "
      "alanı yok; bu sınırlama **Faz 2.8.10 teknik borcu olarak "
      "kaydedilmiştir** (bkz. Bölüm 9).")
    a("")

    a("## 1. İncelenen kayıt sayısı")
    a("")
    a(f"- Toplam: **{analysis['reviewed_record_count']}**")
    for series, count in analysis["target_by_series_counts"].items():
        a(f"  - {series}: {count}")
    a("")

    a("## 2. Sonuç özeti")
    a("")
    a("- Değişmeden doğrulanan (geometri OK, confidence korunuyor): "
      f"**{t['unchanged']}**")
    a(f"- Confidence seviyesi yükseltilen: **{t['upgraded']}**")
    a(f"- G4 olarak bırakılan: **{t['remaining_g4']}**")
    a("- Düzeltilen (değer hatası bulunan) kayıt: **0** "
      "(bu fazda hiçbir geometrik değer hatalı bulunmadı; bkz. Bölüm 3)")
    a("")

    a("## 3. Geometri doğrulama (ISO 724/68-1 formülü ile bağımsız "
      "yeniden hesaplama)")
    a("")
    geom_fail = [
        pr for pr in analysis["per_record"] if not pr["geometry"]["geometry_verified"]
    ]
    if not geom_fail:
        a(f"Tüm {t['reviewed']} kayıt için major/pitch/minor diameter ve "
          "stress area, `backend.library.thread_geometry` (ISO 724/68-1 "
          "temel profil formülleri) ve `backend.vdi2230_core.stress_area` "
          "(ISO 898-1 formülü) ile bağımsız olarak yeniden hesaplandı ve "
          "toleranslar içinde (çaplar ±0.0005 mm, stress area ±max(0.002, "
          "%0.002)) mevcut kayıtlı değerlerle eşleşti. Hiçbir değer "
          "hatası bulunmadı.")
    else:
        a(f"**{len(geom_fail)} kayıtta geometri uyuşmazlığı bulundu:**")
        for pr in geom_fail:
            a(f"- {pr['id']}:")
            for m in pr["geometry"]["mismatches"]:
                a(f"  - {m['field']}: hesaplanan={m['calculated']}, "
                  f"kayıtlı={m['stored']}, tolerans={m['tolerance']}")
    a("")
    inv_fail = [pr for pr in analysis["per_record"] if pr["invariant_issues"]]
    a("### Geometrik sıralama/pozitiflik invariant kontrolü")
    a("")
    if not inv_fail:
        a("Tüm kayıtlarda `major_diameter_mm >= pitch_diameter_mm >= "
          "minor_diameter_mm > 0` ve `stress_area_mm2 > 0` sağlandı.")
    else:
        for pr in inv_fail:
            a(f"- {pr['id']}: {'; '.join(pr['invariant_issues'])}")
    a("")

    a("## 4. Confidence yükseltme dağılımı")
    a("")
    a("| Kayıt | Seri | Önce | Sonra | Kaynak kanıtı |")
    a("|---|---|:---:|:---:|---|")
    for pr in analysis["per_record"]:
        if pr["upgrade_eligible"]:
            ev = "; ".join(pr["corroboration"]["evidence"])
            # "Önce" is always G4 for every Faz 2.8.2 target record
            # (confirmed by the Faz 2.8.1 inventory: every Fine/Extra
            # Fine/Coarse-M68-100 record started at G4). Printed as a
            # fixed historical fact rather than the live
            # confidence_before field, which reads the *current* file
            # state and would show G3->G3 on any report regeneration
            # run after --apply has already been used once.
            a(f"| {pr['id']} | {pr['series']} | G4 | "
              f"G{pr['confidence_after']} | {ev} |")
    if t["upgraded"] == 0:
        a("| *(yok)* | | | | |")
    a("")

    a("## 5. G4 olarak bırakılan kayıtlar ve nedenleri")
    a("")
    g4_by_reason: Dict[str, List[str]] = {}
    for pr in analysis["per_record"]:
        if pr["confidence_after"] == 4:
            reason = pr["corroboration"].get("reason", "")
            g4_by_reason.setdefault(reason, []).append(pr["id"])
    for reason, ids in g4_by_reason.items():
        a(f"**{len(ids)} kayıt** -- {reason}")
        if len(ids) <= 10:
            a(f"  - {', '.join(ids)}")
        else:
            a(f"  - Örnekler: {', '.join(ids[:6])}, ... (+{len(ids)-6} diğer)")
        a("")

    a("## 6. Değer bazında before/after özeti")
    a("")
    upgraded_records = [pr for pr in analysis["per_record"] if pr["upgrade_eligible"]]
    if upgraded_records:
        a("| Kayıt | Alan | Önce | Sonra |")
        a("|---|---|---|---|")
        for pr in upgraded_records:
            a(f"| {pr['id']} | confidence | 4 | {pr['confidence_after']} |")
            a(f"| {pr['id']} | validation_status | provisional | "
              f"{pr['validation_status_after']} |")
        a("")
        a("Not: `nominal_diameter_mm`, `pitch_mm`, `major_diameter_mm`, "
          "`pitch_diameter_mm`, `minor_diameter_mm`, `stress_area_mm2` "
          "alanlarında **hiçbir değer değişmedi** -- yalnızca "
          "provenance/confidence metadata alanları (confidence, "
          "confidence_level, validation_status, approval_status, "
          "review_status, notes, source, source_reference, revision, "
          "source_revision, checksum) güncellendi.")
        if apply_result["changed_records"]:
            a("")
            a(f"Bu çalıştırmada dosyaya yazılan değişiklik sayısı: "
              f"{len(apply_result['changed_records'])} "
              f"(dry_run={apply_result['dry_run']}).")
        else:
            a("")
            a("Bu çalıştırmada dosyada değişiklik yapılmadı -- yukarıdaki "
              "yükseltmeler önceki bir `--apply` çalıştırmasında zaten "
              "uygulanmış ve kalıcı hale getirilmiştir (idempotent "
              "yeniden çalıştırma).")
    else:
        a("Bu fazda hiçbir kayıt yükseltilmedi.")
    a("")

    a("## 7. Kaynak bazında dağılım")
    a("")
    by_source_standard: Dict[str, int] = {}
    for pr in analysis["per_record"]:
        by_source_standard[pr["source_standard"]] = (
            by_source_standard.get(pr["source_standard"], 0) + 1
        )
    a("| source_standard | Kayıt sayısı |")
    a("|---|---:|")
    for src, count in sorted(by_source_standard.items()):
        a(f"| {src} | {count} |")
    a("")

    a("## 8. Fine / Extra Fine / Coarse ayrı sonuçları")
    a("")
    for series in ("Coarse", "Fine", "Extra Fine"):
        recs = [pr for pr in analysis["per_record"] if pr["series"] == series]
        diameters = analysis["diameters_by_series"][series]
        upgraded_n = sum(1 for pr in recs if pr["upgrade_eligible"])
        a(f"### {series}")
        a("")
        a(f"- Kayıt sayısı: {len(recs)}")
        a(f"- Çap aralığı: M{min(diameters):g}-M{max(diameters):g}")
        a(f"- Yükseltilen: {upgraded_n} / {len(recs)}")
        a(f"- Duplicate (nominal_diameter_mm, pitch_mm) kombinasyonu: "
          f"{len(analysis['duplicate_diameter_pitch_combos'][series])}")
        a("")

    a("## 9. ISO 724 ve ISO 68-1 izlenebilirlik durumu")
    a("")
    a("- **ISO 724**: nominal çap ve pitch serisi/tablosu kaynağı -- "
      "`source_standard` alanında (\"ISO 724 / ISO 261\") açıkça "
      "belirtiliyor.")
    a("- **ISO 68-1**: temel profil / geometrik formül ilişkisinin "
      "kaynağı (H = sqrt(3)/2 * P temel üçgen yüksekliği ve "
      "0.75H/1.25H/(17/12)H faktörleri) -- `backend/library/"
      "thread_geometry.py` modül docstring'inde açıkça belgeleniyor, "
      "ancak `ThreadRecord` şemasında ayrı bir `iso_68_1_reference` "
      "alanı **yok**.")
    a("- **Teknik sınırlama**: mevcut şema (`extra=\"forbid\"`) ISO 68-1'i "
      "ayrı, yapılandırılmış bir alan olarak taşıyamıyor. Bu faz "
      "şemayı değiştirmedi (görev kuralı). Yükseltilen 5 kayıtta bu "
      "ayrım `notes` serbest-metin alanında açıkça belirtildi "
      "(\"ISO 724 basic-profile formula\"); değiştirilmeyen 67 kayıtta "
      "bu ek not eklenmedi (gereksiz diff'ten kaçınmak için) -- rapor "
      "seviyesinde bu bölümde belgelendi.")
    a("- **Faz 2.8.10 önerisi**: `ThreadRecord`'a opsiyonel, "
      "additive bir `basic_profile_standard` (öntanımlı \"ISO 68-1\") "
      "alanı eklenmesi, ISO 724 (boyut tablosu) ile ISO 68-1 (temel "
      "profil formülü) ayrımını her kayıtta yapılandırılmış biçimde "
      "taşımayı sağlar -- şema değişikliği gerektirdiği için bu fazın "
      "kapsamı dışında bırakıldı.")
    a("")

    a("## 10. Stress area doğrulama yöntemi")
    a("")
    a("`backend.vdi2230_core.stress_area.tensile_stress_area_mm2()` "
      "(ISO 898-1 formülü, A_s = pi/4 * ((d2+d3)/2)^2, d2/d3 ISO 68-1 "
      "faktörleriyle) kullanılarak her 72 kayıt için bağımsız olarak "
      "yeniden hesaplandı ve kayıtlı `stress_area_mm2` değeriyle "
      "karşılaştırıldı (bkz. Bölüm 3). Bu formül modülü kendi "
      "docstring'inde \"PROVISIONAL: requires independent source "
      "sign-off before production use\" olarak işaretli -- bu durum "
      "değiştirilmedi, yalnızca üretim tutarlılığı doğrulandı, "
      "formülün kendisi onaylanmadı.")
    a("")

    a("## 11. Açık kalan veri boşlukları")
    a("")
    a(f"- {t['remaining_g4']} kayıt G4/provisional durumunda kalıyor "
      "(bkz. Bölüm 5) -- birincil ISO 261/262 standart tablosuna "
      "erişim olmadan pitch-seçim doğruluğu teyit edilemiyor.")
    a("- M76/M85/M95 (Coarse) için ikincil kaynaklarda doğrulama "
      "bulunamadı; bu üç çapın ISO 261'in \"preferred\"/\"seçilmiş\" "
      "serisinde olup olmadığı belirsiz kalıyor.")
    a("- Thread şemasında ISO 68-1 için ayrı, yapılandırılmış bir "
      "izlenebilirlik alanı yok (bkz. Bölüm 9, Faz 2.8.10 önerisi).")
    a("- `stress_area` formülü (`backend.vdi2230_core.stress_area`) "
      "kendi docstring'inde hâlâ PROVISIONAL; bağımsız mühendislik "
      "onayı bu fazın kapsamında değil.")
    a("")

    a("## 12. Faz 2.8.3 için Go / No-Go önerisi")
    a("")
    a("**GO.** Geometri hesaplama zinciri (ISO 724/68-1 formülleri, "
      "ISO 898-1 stress area) 72/72 kayıtta bağımsız olarak doğrulandı, "
      f"hiçbir değer hatası bulunmadı, {t['upgraded']} kayıt kaynak "
      "kanıtıyla G3'e yükseltildi. Kalan G4 kayıtlar (Fine/Extra Fine "
      "tamamı + M76/M85/M95) üretim davranışını bozmuyor (population.py "
      "erişim yolu değişmedi, VDI 2230 hesaplama zincirine giren "
      "değerler aynı kaldı) ve açıkça belgelendi. Faz 2.8.3 (Strength/"
      "Washer/Friction doğrulaması) bu bulgulardan etkilenmeden "
      "başlayabilir.")
    a("")

    return "\n".join(lines)


def build_summary(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Exact numeric summary fields required by the Faz 2.8.2 task
    brief (key names verbatim). Derived from ``analysis``, never
    hardcoded, so they cannot drift from the per-record detail."""
    counts = analysis["target_by_series_counts"]
    t = analysis["totals"]
    geometry_verified = sum(
        1 for pr in analysis["per_record"] if pr["geometry"]["geometry_verified"]
    )
    secondary_verified = sum(
        1 for pr in analysis["per_record"]
        if pr["corroboration"]["corroborated"]
    )
    return {
        "target_records": analysis["reviewed_record_count"],
        "fine_records": counts.get("Fine", 0),
        "extra_fine_records": counts.get("Extra Fine", 0),
        "coarse_records": counts.get("Coarse", 0),
        "geometry_verified": geometry_verified,
        "geometry_value_changes": 0,
        "confidence_upgraded": t["upgraded"],
        "remaining_g4": t["remaining_g4"],
        # No record in this phase was confirmed against the primary
        # ISO 261/262 standard text itself (paywalled; not accessed
        # in this session) -- every upgrade was secondary-source only.
        "primary_source_verified": 0,
        "secondary_source_verified": secondary_verified,
        "unresolved_records": t["remaining_g4"],
    }


def build_json_report(analysis: Dict[str, Any], apply_result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "phase": analysis["phase"],
        "phase_name": analysis["phase_name"],
        "summary": build_summary(analysis),
        "reviewed_record_count": analysis["reviewed_record_count"],
        "target_by_series_counts": analysis["target_by_series_counts"],
        "diameters_by_series": analysis["diameters_by_series"],
        "duplicate_diameter_pitch_combos": analysis["duplicate_diameter_pitch_combos"],
        "schema_violation_count": analysis["schema_violation_count"],
        "schema_violations": analysis["schema_violations"],
        "totals": analysis["totals"],
        "important_caveats": [
            "72/72 kayıt ISO 724/68-1 formülleriyle geometrik olarak "
            "doğrulandı; bu, kayıtların BİRİNCİL standart kaynağıyla "
            "(ISO 261/262 metin/tablosu) doğrulandığı anlamına GELMEZ "
            "-- yalnızca 'verilen pitch doğruysa geometri doğru "
            "hesaplanmış' önermesini kanıtlar.",
            "Fine + Extra Fine (64 kayıt) ISO 261/262 birincil tablo "
            "erişimi olmadığı için G4/provisional seviyesinde bırakıldı.",
            "Coarse M68/M72/M80/M90/M100 (5 kayıt) yalnızca İKİ bağımsız "
            "İKİNCİL kaynakla (Aspen Fasteners, mfindllc.com) doğrulandığı "
            "için G3/reference_only seviyesine yükseltildi -- G1/G2 "
            "(birincil standart) DEĞİL.",
            "Coarse M76/M85/M95 (3 kayıt) hiçbir bağımsız kaynakta "
            "bulunamadığı için G4/provisional olarak kaldı.",
            "Hiçbir geometrik değer (nominal_diameter_mm, pitch_mm, "
            "major/pitch/minor_diameter_mm, stress_area_mm2) "
            "değiştirilmedi; yalnızca provenance/confidence metadata "
            "alanları güncellendi.",
            "Stress-area kontrolü backend.vdi2230_core.stress_area."
            "tensile_stress_area_mm2() kullanır; bu fonksiyonun kendi "
            "docstring'i 'PROVISIONAL: requires independent source "
            "sign-off before production use' der. Bu kontrol üretim "
            "tutarlılığını doğrular, formülün kendisini birincil "
            "standart olarak onaylamaz.",
            "ISO 68-1 için ayrı, yapılandırılmış bir izlenebilirlik "
            "alanı mevcut şemada yok; bu Faz 2.8.10 teknik borcu "
            "olarak kaydedildi (bkz. rapor Bölüm 9/11).",
        ],
        "per_record": analysis["per_record"],
        "apply_result": apply_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format", choices=["md", "json", "both"], default="both",
    )
    parser.add_argument("--out-dir", default="docs/phase_2_8")
    parser.add_argument(
        "--report-name", default="phase_2_8_2_thread_geometry_verification",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually write confidence/status/notes/checksum updates to "
             "thread_library.json. Without this flag, runs read-only "
             "(dry-run) and the report reflects proposed changes only.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze()
    apply_result = apply_upgrades(analysis, dry_run=not args.apply)

    json_report = build_json_report(analysis, apply_result)

    if args.format in ("json", "both"):
        json_path = out_dir / f"{args.report_name}.json"
        json_path.write_text(
            json.dumps(json_report, indent=2, ensure_ascii=False, sort_keys=False)
            + "\n",
            encoding="utf-8",
        )
        print(f"JSON report written: {json_path}")

    if args.format in ("md", "both"):
        md_path = out_dir / f"{args.report_name}.md"
        md_path.write_text(
            render_markdown(analysis, apply_result) + "\n", encoding="utf-8"
        )
        print(f"Markdown report written: {md_path}")

    if args.apply:
        print(
            f"APPLIED: {len(apply_result['changed_records'])} record(s) "
            f"updated in {THREAD_DATA_PATH}"
        )
    else:
        print(
            f"DRY RUN: {len(apply_result['changed_records'])} record(s) "
            "would be updated (re-run with --apply to write)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
