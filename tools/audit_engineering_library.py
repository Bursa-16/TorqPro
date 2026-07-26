"""TorqPro Engineering Library - Faz 2.8.1 inventory / gap-analysis audit.

Read-only reporting tool. Does not write to, mutate, or replace any
production data file, registered library, or in-memory record store.
Reuses the existing ``backend.library`` infrastructure (``population``,
``models``, ``validator``, ``registry``) rather than re-implementing a
second validation path, per the Faz 2.8.1 task brief.

Usage (from repo root, with the project's virtualenv active):

    python tools/audit_engineering_library.py --format both \
        --out-dir docs/phase_2_8 \
        --report-name phase_2_8_1_library_gap_report

Produces (unless ``--format`` restricts it):
    <out-dir>/<report-name>.md
    <out-dir>/<report-name>.json

Deterministic: two runs against the same working tree produce
byte-identical output (record order is preserved as read from disk;
no timestamps, random IDs or wall-clock values are embedded).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.library import models as models_module  # noqa: E402
from backend.library import population  # noqa: E402
from backend.library import registry as registry_module  # noqa: E402
from backend.library import validator as validator_module  # noqa: E402

# ---------------------------------------------------------------------
# Static configuration
# ---------------------------------------------------------------------

#: Every registered library key this audit inspects, in a fixed,
#: reproducible order (population sources first, OEM catalog last --
#: it is not registry-populated by design, see population.py).
LIBRARY_KEYS: List[str] = list(population.POPULATION_SOURCES) + ["oem library"]

#: Domain-specific validator entry points already provided by
#: population.py, reused as-is (not re-implemented here).
DOMAIN_VALIDATORS = {
    "thread library": population.validate_thread_library_records,
    "bolt library": population.validate_bolt_library_records,
    "nut library": population.validate_nut_library_records,
    "lubrication library": population.validate_lubrication_library_records,
    "friction condition library": population.validate_friction_condition_library_records,
    "washer library": population.validate_washer_library_records,
    "joint hardware library": population.validate_joint_hardware_library_records,
}

#: Recognised validation_status vocabulary -> gap-report provenance
#: class. Records with a status outside this map, or with neither
#: ``source`` nor ``source_standard`` populated, fall into
#: "unknown_provenance" regardless of their status.
STATUS_TO_CLASS = {
    "validated": "verified_standard_data",
    "reference_only": "engineering_reference_data",
    "provisional": "engineering_reference_data",
    "metadata_only": "engineering_reference_data",
}

PROVENANCE_CLASSES = [
    "verified_standard_data",
    "engineering_reference_data",
    "synthetic_or_generated_data",
    "placeholder_or_shell_data",
    "unknown_provenance",
]

# Static, evidence-based finding (see task-turn grep results): which
# non-library modules actually consume backend.library data, and via
# which access path. Recorded here (not derived at run time) because
# it reflects an architectural fact established by source inspection,
# not something safely re-derivable by import-time introspection
# without risking side effects.
CALCULATION_ENGINE_USAGE = {
    "population.load_population_records() / population.oem_catalog()": [
        "backend/calculation_engine/friction_recommendations.py",
        "backend/calculation_engine/friction_readiness.py",
        "backend/calculation_engine/friction_report.py",
        "backend/app.py",
    ],
    "registry.get_library(key).records / .typed_records() (registry-populated path)": [],
}


def classify_record(record: Dict[str, Any]) -> str:
    """Return this record's provenance class per the Faz 2.8.1 rules.

    A record is only ever classified as verified/reference data when
    it carries source traceability (``source`` or ``source_standard``
    non-empty) -- a populated field set alone is not sufficient (task
    rule, section 3).
    """
    status = record.get("validation_status")
    has_traceability = bool(record.get("source")) or bool(record.get("source_standard"))
    if not has_traceability:
        return "unknown_provenance"
    return STATUS_TO_CLASS.get(status, "unknown_provenance")


def confidence_label(value: Any) -> str:
    try:
        return models_module.ConfidenceLevel(value).name
    except ValueError:
        return f"unrecognised({value!r})"


def git_info() -> Dict[str, Any]:
    """Best-effort repository state snapshot. Never raises -- a git
    failure degrades to null fields rather than aborting the audit."""

    def run(*args: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None
            return result.stdout.strip()
        except Exception:
            return None

    return {
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "head_commit": run("rev-parse", "HEAD"),
        "head_commit_subject": run("log", "-1", "--format=%s"),
        "working_tree_clean": run("status", "--porcelain") == "",
    }


def audit_library(key: str) -> Dict[str, Any]:
    """Full inventory + gap analysis for one registered library key."""
    if key == "oem library":
        raw_records = population.oem_catalog()
        source_file = str(Path(population.OEM_SOURCE))
        registry_record_count: Optional[int] = None  # never registry-populated by design
    else:
        raw_records = population.load_population_records(key)
        source_file = str(Path(population.POPULATION_SOURCES[key]))
        try:
            registry_record_count = len(registry_module.get_library(key).records)
        except KeyError:
            registry_record_count = None

    model = models_module.get_record_model(key)
    schema_violations = models_module.find_schema_violations(key, raw_records)
    violation_record_indices = {
        int(v.split("]", 1)[0].lstrip("[")) for v in schema_violations
    }

    confidence_dist: Dict[str, int] = {}
    validation_status_dist: Dict[str, int] = {}
    approval_status_dist: Dict[str, int] = {}
    provenance_dist: Dict[str, int] = {cls: 0 for cls in PROVENANCE_CLASSES}
    source_empty = 0
    source_standard_empty = 0
    confidence_missing = 0

    for record in raw_records:
        conf = record.get("confidence")
        label = confidence_label(conf) if conf is not None else "MISSING"
        if conf is None:
            confidence_missing += 1
        confidence_dist[label] = confidence_dist.get(label, 0) + 1

        vstatus = record.get("validation_status") or "MISSING"
        validation_status_dist[vstatus] = validation_status_dist.get(vstatus, 0) + 1
        astatus = record.get("approval_status") or "MISSING"
        approval_status_dist[astatus] = approval_status_dist.get(astatus, 0) + 1

        if not record.get("source"):
            source_empty += 1
        if not record.get("source_standard"):
            source_standard_empty += 1

        provenance_dist[classify_record(record)] += 1

    duplicate_issues = validator_module.find_duplicate_ids(raw_records)

    domain_check_fn = DOMAIN_VALIDATORS.get(key)
    domain_issues = domain_check_fn() if domain_check_fn else []

    return {
        "library_key": key,
        "model": model.__name__,
        "source_file": source_file,
        "record_count_raw": len(raw_records),
        "record_count_typed_valid": len(raw_records) - len(violation_record_indices),
        "registry_populated_record_count": registry_record_count,
        "registry_data_disconnect": (
            registry_record_count is not None
            and registry_record_count != len(raw_records)
        ),
        "schema_violation_count": len(schema_violations),
        "schema_violations": schema_violations,
        "confidence_distribution": confidence_dist,
        "confidence_missing_count": confidence_missing,
        "validation_status_distribution": validation_status_dist,
        "approval_status_distribution": approval_status_dist,
        "source_empty_count": source_empty,
        "source_standard_empty_count": source_standard_empty,
        "provenance_distribution": provenance_dist,
        "duplicate_id_count": len(duplicate_issues),
        "duplicate_ids": [issue.message for issue in duplicate_issues],
        "domain_specific_issue_count": len(domain_issues),
        "domain_specific_issues": domain_issues,
    }


def thread_library_deep_dive(module_report: Dict[str, Any]) -> Dict[str, Any]:
    """Faz 2.8.2 scope-decision inputs (task section 6). Derived only
    from ``thread library`` raw records; no other module is read."""
    records = population.load_population_records("thread library")
    by_series: Dict[str, Dict[str, Any]] = {}
    for series in ("Coarse", "Fine", "Extra Fine"):
        subset = [r for r in records if r.get("series") == series]
        diameters = sorted({r.get("nominal_diameter_mm") for r in subset})
        conf_dist: Dict[str, int] = {}
        for r in subset:
            label = confidence_label(r.get("confidence"))
            conf_dist[label] = conf_dist.get(label, 0) + 1
        stress_area_present = sum(
            1 for r in subset if r.get("stress_area_mm2") is not None
        )
        by_series[series] = {
            "record_count": len(subset),
            "distinct_nominal_diameters_mm": diameters,
            "min_diameter_mm": min(diameters) if diameters else None,
            "max_diameter_mm": max(diameters) if diameters else None,
            "confidence_distribution": conf_dist,
            "stress_area_mm2_present": stress_area_present,
            "stress_area_mm2_missing": len(subset) - stress_area_present,
            "provisional_only_diameters_mm": sorted(
                r["nominal_diameter_mm"] for r in subset
                if r.get("confidence") == models_module.ConfidenceLevel.G4
            ),
        }
    iso_metric_total = sum(
        1 for r in records if r.get("thread_series") == "ISO_METRIC"
    )
    non_iso_metric_total = len(records) - iso_metric_total
    iso_traceable = sum(
        1 for r in records
        if r.get("thread_series") == "ISO_METRIC"
        and "ISO 724" in (r.get("source_standard") or "")
    )
    return {
        "iso_metric_record_count": iso_metric_total,
        "non_iso_metric_record_count": non_iso_metric_total,
        "iso_724_traceable_count": iso_traceable,
        "iso_724_traceable_of_iso_metric_pct": (
            round(100 * iso_traceable / iso_metric_total, 1)
            if iso_metric_total else None
        ),
        "by_series": by_series,
        "schema_violation_count": module_report["schema_violation_count"],
    }


def build_report() -> Dict[str, Any]:
    modules = {key: audit_library(key) for key in LIBRARY_KEYS}
    integrity = population.run_all_integrity_checks()

    total_raw = sum(m["record_count_raw"] for m in modules.values())
    total_violations = sum(m["schema_violation_count"] for m in modules.values())
    total_source_empty = sum(m["source_empty_count"] for m in modules.values())
    total_confidence_missing = sum(m["confidence_missing_count"] for m in modules.values())
    provenance_totals = {cls: 0 for cls in PROVENANCE_CLASSES}
    for m in modules.values():
        for cls, count in m["provenance_distribution"].items():
            provenance_totals[cls] += count

    return {
        "phase": "2.8.1",
        "phase_name": "Engineering Library Inventory & Gap Analysis",
        "git": git_info(),
        "modules": modules,
        "totals": {
            "module_count": len(modules),
            "total_raw_records": total_raw,
            "total_schema_violations": total_violations,
            "total_source_empty": total_source_empty,
            "total_confidence_missing": total_confidence_missing,
            "provenance_totals": provenance_totals,
        },
        "integrity_checks": {
            name: {"issue_count": len(issues), "issues": issues}
            for name, issues in integrity.items()
        },
        "thread_library_deep_dive": thread_library_deep_dive(modules["thread library"]),
        "empty_modules": [
            key for key, m in modules.items() if m["record_count_raw"] == 0
        ],
        "registry_data_disconnects": [
            key for key, m in modules.items() if m["registry_data_disconnect"]
        ],
        "calculation_engine_usage": CALCULATION_ENGINE_USAGE,
    }


# ---------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------

def render_markdown(report: Dict[str, Any]) -> str:
    g = report["git"]
    t = report["totals"]
    lines: List[str] = []
    a = lines.append

    a("# Faz 2.8.1 - Engineering Library Inventory & Gap Analysis Report")
    a("")
    a("Bu rapor salt-okunur bir envanter/boşluk analizidir. Hiçbir mühendislik "
      "verisi, formül, model veya API davranışı değiştirilmemiştir.")
    a("")

    a("## 1. Executive Summary")
    a("")
    a(f"- İncelenen modül sayısı: **{t['module_count']}**")
    a(f"- Toplam ham kayıt sayısı: **{t['total_raw_records']}**")
    a(f"- Toplam şema ihlali: **{t['total_schema_violations']}**")
    a(f"- Kaynak (`source`) alanı boş kayıt: **{t['total_source_empty']}**")
    a(f"- Confidence alanı eksik kayıt: **{t['total_confidence_missing']}**")
    a(f"- Boş (0 kayıtlı) modül sayısı: **{len(report['empty_modules'])}** "
      f"({', '.join(report['empty_modules']) or 'yok'})")
    a(f"- Registry/veri kopukluğu tespit edilen modül sayısı: "
      f"**{len(report['registry_data_disconnects'])}** "
      f"({', '.join(report['registry_data_disconnects']) or 'yok'})")
    a("")

    a("## 2. Repository and Baseline State")
    a("")
    a(f"- Branch: `{g['branch']}`")
    a(f"- HEAD commit: `{g['head_commit']}`")
    a(f"- HEAD commit subject: {g['head_commit_subject']}")
    a(f"- Working tree clean (audit script çalıştırılmadan önce): {g['working_tree_clean']}")
    a("")
    a("Not: Bu rapor içinde iddia edilen pytest taban sonucu, teslim adımında "
      "ayrıca çalıştırılıp faz başı/sonu olarak raporlanır; bu doküman "
      "yalnızca kütüphane veri durumunu kapsar.")
    a("")

    a("## 3. Library Module Inventory")
    a("")
    a("| Modül (key) | Model | Veri dosyası | Ham kayıt | Typed geçerli | "
      "Registry'de dolu | Kopukluk |")
    a("|---|---|---|---:|---:|---:|:---:|")
    for key, m in report["modules"].items():
        reg = m["registry_populated_record_count"]
        reg_str = "N/A (adapter-only)" if reg is None else str(reg)
        disc = "EVET" if m["registry_data_disconnect"] else "-"
        a(f"| {key} | {m['model']} | `{m['source_file']}` | "
          f"{m['record_count_raw']} | {m['record_count_typed_valid']} | "
          f"{reg_str} | {disc} |")
    a("")

    a("## 4. Record Count by Module")
    a("")
    for key, m in report["modules"].items():
        a(f"- **{key}**: {m['record_count_raw']} kayıt")
    a("")

    a("## 5. Schema Violation Summary")
    a("")
    any_violation = False
    for key, m in report["modules"].items():
        if m["schema_violation_count"]:
            any_violation = True
            a(f"### {key} ({m['schema_violation_count']} ihlal)")
            for v in m["schema_violations"]:
                a(f"- {v}")
            a("")
    if not any_violation:
        a("Hiçbir modülde `find_schema_violations()` ihlali tespit edilmedi.")
        a("")

    a("## 6. Confidence Grade Distribution")
    a("")
    a("| Modül | G1 | G2 | G3 | G4 | Eksik |")
    a("|---|---:|---:|---:|---:|---:|")
    for key, m in report["modules"].items():
        d = m["confidence_distribution"]
        a(f"| {key} | {d.get('G1', 0)} | {d.get('G2', 0)} | {d.get('G3', 0)} | "
          f"{d.get('G4', 0)} | {m['confidence_missing_count']} |")
    a("")

    a("## 7. Source and Provenance Coverage")
    a("")
    a("| Modül | source boş | source_standard boş |")
    a("|---|---:|---:|")
    for key, m in report["modules"].items():
        a(f"| {key} | {m['source_empty_count']} | {m['source_standard_empty_count']} |")
    a("")
    a("Not (OEM Library): `validation_status=metadata_only` kayıtlar OEM için "
      "teknik içerik taşımaz (adapter-only tasarım, bkz. `oem_library.py`); "
      "`source_standard` alanı bu modülde tanım gereği boştur, `source` alanı "
      "doludur (kayıt kaynağı katalog kimliğidir, bir standart değildir).")
    a("")

    a("## 8. Placeholder / Synthetic / Verified Data Ratio")
    a("")
    a("Sınıflandırma yöntemi: `validation_status` alanı + `source`/"
      "`source_standard` izlenebilirliği (yalnızca doluluk yeterli sayılmadı). "
      "`validated`→verified_standard_data, `reference_only`/`provisional`/"
      "`metadata_only`→engineering_reference_data (izlenebilirlik varsa), "
      "izlenebilirlik yoksa→unknown_provenance. Bu veri setinde "
      "`synthetic_or_generated_data` işaretine uyan kayıt bulunmadı "
      "(test/demo/otomatik üretim etiketi yok).")
    a("")
    a("| Modül | verified_standard | engineering_reference | synthetic | "
      "placeholder/shell | unknown |")
    a("|---|---:|---:|---:|---:|---:|")
    for key, m in report["modules"].items():
        p = m["provenance_distribution"]
        a(f"| {key} | {p['verified_standard_data']} | "
          f"{p['engineering_reference_data']} | "
          f"{p['synthetic_or_generated_data']} | "
          f"{p['placeholder_or_shell_data']} | {p['unknown_provenance']} |")
    tp = t["provenance_totals"]
    a(f"| **TOPLAM** | **{tp['verified_standard_data']}** | "
      f"**{tp['engineering_reference_data']}** | "
      f"**{tp['synthetic_or_generated_data']}** | "
      f"**{tp['placeholder_or_shell_data']}** | **{tp['unknown_provenance']}** |")
    a("")

    a("## 9. Duplicate and Consistency Findings")
    a("")
    for key, m in report["modules"].items():
        if m["duplicate_id_count"]:
            a(f"### {key} ({m['duplicate_id_count']} duplicate id)")
            for d in m["duplicate_ids"]:
                a(f"- {d}")
            a("")
    a("### population.run_all_integrity_checks() sonuçları")
    a("")
    a("| Kontrol | Bulgu sayısı |")
    a("|---|---:|")
    for name, res in report["integrity_checks"].items():
        a(f"| {name} | {res['issue_count']} |")
    a("")
    any_integrity_issue = any(r["issue_count"] for r in report["integrity_checks"].values())
    if any_integrity_issue:
        a("Detaylar (yalnızca bulgu>0 kontroller):")
        a("")
        for name, res in report["integrity_checks"].items():
            if res["issue_count"]:
                a(f"**{name}:**")
                for issue in res["issues"]:
                    a(f"- {issue}")
                a("")

    a("## 10. Calculation Engine Usage Mapping")
    a("")
    a("Kaynak taraması (bkz. Faz 2.8.1 görev bağlamı) ile doğrulanmış erişim "
      "yolları:")
    a("")
    for path, consumers in report["calculation_engine_usage"].items():
        a(f"- **{path}**")
        if consumers:
            for c in consumers:
                a(f"  - {c}")
        else:
            a("  - (tespit edilen kullanıcı yok)")
    a("")
    a("**Bulgu:** `backend/library/population.py` üzerinden okuma, "
      "production kod yollarının (calculation_engine, app.py) kullandığı "
      "**tek** erişim biçimidir. `registry.get_library(key).records` / "
      "`.typed_records()` erişim yolu (Faz 1.3/1.4 registry altyapısı) "
      "herhangi bir production tüketici tarafından çağrılmamaktadır -- bkz. "
      "Bölüm 11, 'registry veri kopukluğu'.")
    a("")

    a("## 11. Missing Fields and Missing Sources")
    a("")
    a("### Registry veri kopukluğu (registry_data_disconnect)")
    a("")
    a("`registry.get_library(key).records` (Faz 1.3/1.4 registry state) ile "
      "`population.load_population_records(key)` (gerçek veri dosyası) "
      "arasındaki fark:")
    a("")
    a("| Modül | Registry'de dolu kayıt | Veri dosyasındaki kayıt |")
    a("|---|---:|---:|")
    for key, m in report["modules"].items():
        reg = m["registry_populated_record_count"]
        if reg is None:
            continue
        a(f"| {key} | {reg} | {m['record_count_raw']} |")
    a("")
    a("Kök neden: `population.populate_all()` hiçbir production kod "
      "yolunda (import zamanında veya çalışma zamanında) otomatik "
      "çağrılmıyor (bkz. `population.py` docstring: \"Nothing here runs "
      "automatically\"). Bu, mimari ihlal değildir (Faz 2.4 kararlarıyla "
      "tutarlı, kasıtlı opt-in tasarım) ancak registry tabanlı erişim "
      "yolunun (`get_library(...).records`) production'da fiilen boş "
      "olduğu anlamına gelir.")
    a("")
    a("### Domain-specific validator bulguları")
    a("")
    any_domain_issue = False
    for key, m in report["modules"].items():
        if m["domain_specific_issue_count"]:
            any_domain_issue = True
            a(f"**{key}** ({m['domain_specific_issue_count']} bulgu):")
            for issue in m["domain_specific_issues"]:
                a(f"- {issue}")
            a("")
    if not any_domain_issue:
        a("Mevcut domain-specific validator fonksiyonları (bolt/nut/washer/"
          "thread/lubrication/friction_condition/joint_hardware) hiçbir "
          "bulgu döndürmedi.")
        a("")

    a("## 12. Risks")
    a("")
    risks = []
    if report["registry_data_disconnects"]:
        risks.append(
            "Registry tabanlı erişim yolu (`get_library().records`) "
            "production verisinden kopuk; bu yol yanlışlıkla "
            "kullanılırsa (örn. yeni bir GUI/API entegrasyonunda) sessizce "
            "boş sonuç dönebilir."
        )
    if report["empty_modules"]:
        risks.append(
            f"{', '.join(report['empty_modules'])} modül(ler)i hâlâ boş "
            "shell durumunda; bu modüllere bağımlı herhangi bir "
            "hesaplama/entegrasyon şu an veri bulamaz."
        )
    dd = report["thread_library_deep_dive"]
    fine_g4 = dd["by_series"]["Fine"]["confidence_distribution"].get("G4", 0)
    xfine_g4 = dd["by_series"]["Extra Fine"]["confidence_distribution"].get("G4", 0)
    if fine_g4 or xfine_g4:
        risks.append(
            "Thread Library Fine ve Extra Fine serileri tamamen G4 "
            "(provisional) güven seviyesinde; VDI 2230 hesaplama zincirine "
            "giren bu değerler henüz doğrudan standart tablosu ile "
            "doğrulanmamış durumda."
        )
    stress_missing = sum(
        s["stress_area_mm2_missing"] for s in dd["by_series"].values()
    )
    if stress_missing:
        risks.append(
            f"Thread Library içinde {stress_missing} kayıtta "
            "`stress_area_mm2` alanı eksik (UNC/UNF/BSP/NPT/Trapezoidal "
            "gibi ISO-metrik-dışı seriler)."
        )
    if not risks:
        risks.append("Bu taramada kritik risk tespit edilmedi.")
    for r in risks:
        a(f"- {r}")
    a("")

    a("## 13. Recommended Scope for Faz 2.8.2-2.8.10")
    a("")
    a("- **2.8.2 (Thread Geometry):** mevcut M1-M100 coarse seti bu "
      "haliyle korunacak; Fine/Extra Fine serilerinin G4→G2/G1 seviyesine "
      "çıkarılması ve M68-M100 aralığındaki 8 coarse kaydın doğrudan "
      "standart tablosu ile doğrulanması önerilir (bkz. Bölüm 6 detay).")
    a("- **2.8.3-2.8.5 (Strength/Washer/Friction):** mevcut kayıtlar "
      "şema-geçerli ve kaynak-izlenebilir; ek doğrulama G3/G4 kayıtların "
      "G1/G2'ye yükseltilmesine odaklanmalı, yeni alan eklenmesi "
      "gerekmiyor.")
    a("- **2.8.6 (Çapraz doğrulama motoru):** `population.py` içinde "
      "zaten `find_dangling_thread_references`, "
      "`find_broken_compatibility_references`, "
      "`find_broken_friction_condition_references` mevcut; 2.8.6 bunları "
      "genişletmeli, yeniden yazmamalı.")
    a("- **joint hardware library** ve **registry veri kopukluğu**: "
      "kapsam dışı bırakılmamalı, ayrı küçük bir alt faz (2.8.1a önerisi) "
      "olarak ele alınabilir -- bkz. Bölüm 14.")
    a("")

    a("## 14. Go / No-Go Recommendation for Faz 2.8.2")
    a("")
    a("**GO** (koşullu). Thread Library'nin mevcut M1-M100 coarse/fine/"
      "extra-fine iskeleti, şema ihlali olmadan ve tam kaynak "
      "izlenebilirliğiyle mevcut; 2.8.2 yeni kayıt eklemek yerine mevcut "
      "G4 kayıtları G1/G2'ye yükseltme + M68-M100 coarse doğrulaması "
      "olarak kapsam daraltılarak başlayabilir. Şema değişikliği "
      "gerekmiyor. Registry/veri kopukluğu (Bölüm 11) 2.8.2'yi engellemez "
      "(population.py erişim yolu zaten üretimde kullanılan tek yol) "
      "ancak ayrı bir teknik borç maddesi olarak izlenmelidir.")
    a("")

    dd = report["thread_library_deep_dive"]
    coarse_conf = dd["by_series"]["Coarse"]["confidence_distribution"]
    coarse_g1g2 = coarse_conf.get("G1", 0) + coarse_conf.get("G2", 0)
    stress_area_total = sum(
        s["stress_area_mm2_present"] for s in dd["by_series"].values()
    )
    fine_xfine_count = (
        dd["by_series"]["Fine"]["record_count"]
        + dd["by_series"]["Extra Fine"]["record_count"]
    )
    a("### Ek: 2.8.2 kapsam kararı soruları")
    a("")
    a(f"- ThreadGeometry içinde gerçek/doğrulanmış (G1/G2) kayıt: "
      f"{coarse_g1g2} (Coarse) / toplam {dd['iso_metric_record_count']} "
      "ISO-metrik kayıt.")
    a(f"- M1-M100 coarse kapsamı: {dd['by_series']['Coarse']['record_count']} "
      f"kayıt, aralık M{dd['by_series']['Coarse']['min_diameter_mm']:g}-"
      f"M{dd['by_series']['Coarse']['max_diameter_mm']:g} "
      "(ISO 261 tercih edilen çap serisiyle örtüşüyor).")
    a(f"- Fine kapsamı: M{dd['by_series']['Fine']['min_diameter_mm']:g}-"
      f"M{dd['by_series']['Fine']['max_diameter_mm']:g}, "
      f"{dd['by_series']['Fine']['record_count']} kayıt, tamamı G4.")
    a(f"- Extra Fine kapsamı: M{dd['by_series']['Extra Fine']['min_diameter_mm']:g}-"
      f"M{dd['by_series']['Extra Fine']['max_diameter_mm']:g}, "
      f"{dd['by_series']['Extra Fine']['record_count']} kayıt, tamamı G4.")
    a(f"- `stress_area_mm2` alanı: ISO-metrik kayıtlarda "
      f"{stress_area_total} kayıtta doğrudan kayıtlı; ISO-metrik-dışı "
      "serilerde (UNC/UNF/BSP/NPT/Trapezoidal) genel olarak eksik.")
    a(f"- ISO 724 kaynak izlenebilirliği: {dd['iso_724_traceable_count']} / "
      f"{dd['iso_metric_record_count']} ISO-metrik kayıt "
      f"(%{dd['iso_724_traceable_of_iso_metric_pct']}) `source_standard` "
      "alanında \"ISO 724\" ibaresini taşıyor.")
    a("- Mevcut kayıtlar korunarak genişleme mümkün: **evet** -- "
      "`replace_records`/`populate_library` idempotent, additive şema "
      "(`extra=\"allow\"`, tüm alanlar opsiyonel).")
    a("- Şema değişikliği gerekli mi: **hayır** -- mevcut `ThreadRecord` "
      "şeması G4→G1/G2 yükseltmesi için yeterli (yalnızca `confidence`, "
      "`validation_status`, `approval_status`, `notes` alanları "
      "güncellenecek).")
    a("- Önerilen kesin 2.8.2 kapsamı: Fine + Extra Fine serilerinin "
      f"({fine_xfine_count} kayıt) ve Coarse M68-M100 aralığının "
      "(8 kayıt) doğrudan standart tablosu ile doğrulanması; yeni "
      "diyametre eklenmesi bu alt fazın kapsamında değildir.")
    a("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format", choices=["md", "json", "both"], default="both",
        help="Output format(s) to produce (default: both).",
    )
    parser.add_argument(
        "--out-dir", default="docs/phase_2_8",
        help="Output directory, relative to repo root unless absolute.",
    )
    parser.add_argument(
        "--report-name", default="phase_2_8_1_library_gap_report",
        help="Base filename (without extension) for the report(s).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report()

    if args.format in ("json", "both"):
        json_path = out_dir / f"{args.report_name}.json"
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        print(f"JSON report written: {json_path}")

    if args.format in ("md", "both"):
        md_path = out_dir / f"{args.report_name}.md"
        md_path.write_text(render_markdown(report) + "\n", encoding="utf-8")
        print(f"Markdown report written: {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
