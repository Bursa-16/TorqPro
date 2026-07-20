"""TorqPro Engineering Library - database population (Faz 2.4.1).

Populates the Faz 2.4.0 library shells with real engineering records
read from ``backend/library/data/*.json``. Nothing here runs
automatically:

- Importing this module reads no file and mutates no registered
  library (mirrors the ``migration.py`` / ``loader.py`` "explicit,
  opt-in" convention already established in this package).
- ``populate_library`` / ``populate_all`` must be called explicitly to
  copy a data file's records into a registered :class:`BaseLibrary`.
  Both are idempotent: ``replace_records`` always overwrites a
  library's in-memory store rather than appending, so calling them
  again re-applies the same records without creating duplicates.
- The OEM Library stays adapter-only by design (see
  ``oem_library.py``): this module never calls ``replace_records`` on
  it. Its dataset is exposed read-only via ``oem_catalog`` /
  ``list_oems`` instead.
- ``find_bolt`` / ``find_nut`` / ``find_material`` / ``find_thread`` /
  ``find_coating`` / ``find_lubrication`` / ``list_strength_classes`` /
  ``list_oems`` read the population data files directly (lazily
  cached), independent of whether the registry itself has been
  populated -- this keeps the search API usable without requiring a
  prior, order-sensitive call to ``populate_all``, and never mutates
  any registered library's own record store.

Per-record provenance vocabulary (Faz 2.4.1):
    validation_status: "validated" | "reference_only" | "provisional"
                        | "metadata_only"
    approval_status:   "approved" (only when validation_status ==
                        "validated") | "pending"

No engineering formula, calculation logic or API/GUI coupling is
introduced by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from . import loader as loader_module
from . import validator as validator_module
from .registry import BaseLibrary, get_library

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

#: Maps a registered library's ``metadata.key`` to its Faz 2.4.1 data
#: file. The OEM Library is intentionally absent -- see module
#: docstring: it never receives records via ``replace_records``.
POPULATION_SOURCES: Dict[str, str] = {
    "bolt library": "bolt_library.json",
    "nut library": "nut_library.json",
    "washer library": "washer_library.json",
    "thread library": "thread_library.json",
    "material library": "material_library.json",
    "coating library": "coating_library.json",
    "lubrication library": "lubrication_library.json",
    "strength class library": "strength_class_library.json",
    "compatibility library": "compatibility_library.json",
}

OEM_SOURCE = "oem_library.json"

KNOWN_VALIDATION_STATUS = {
    "validated", "reference_only", "provisional", "metadata_only",
}
KNOWN_APPROVAL_STATUS = {"approved", "pending"}

_FILE_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def _data_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def load_population_records(library_key: str) -> List[Dict[str, Any]]:
    """Read (and lazily cache) the raw records for ``library_key``'s
    Faz 2.4.1 data file.

    Raises ``KeyError`` if ``library_key`` has no mapped population
    source (e.g. "oem library" -- use :func:`oem_catalog` instead).
    """
    key = library_key.strip().lower()
    if key not in POPULATION_SOURCES:
        raise KeyError(f"No population data source mapped for: {library_key}")
    if key in _FILE_CACHE:
        return list(_FILE_CACHE[key])
    payload = loader_module.read_source_payload(_data_path(POPULATION_SOURCES[key]))
    records = loader_module.extract_records(payload)
    _FILE_CACHE[key] = records
    return list(records)


def oem_catalog() -> List[Dict[str, Any]]:
    """Return the Faz 2.4.1 OEM metadata records, read-only.

    Never stored on ``OEM_LIBRARY`` (adapter-only by design -- see
    ``oem_library.py``).
    """
    key = "__oem__"
    if key not in _FILE_CACHE:
        payload = loader_module.read_source_payload(_data_path(OEM_SOURCE))
        _FILE_CACHE[key] = loader_module.extract_records(payload)
    return list(_FILE_CACHE[key])


def clear_cache() -> None:
    """Drop every cached population read (files are re-read on next
    access). Does not touch any registered library's records."""
    _FILE_CACHE.clear()


# ---------------------------------------------------------------------
# Population engine
# ---------------------------------------------------------------------

def populate_library(library: BaseLibrary) -> int:
    """Copy ``library``'s Faz 2.4.1 data-file records into it via
    ``replace_records`` and return how many records were applied.

    Idempotent: ``replace_records`` overwrites the library's record
    store rather than appending, so calling this again re-applies the
    same records without duplicating them.

    Raises ``KeyError`` if the library has no mapped population
    source (including the OEM Library -- always adapter-only).
    """
    records = load_population_records(library.metadata.key)
    library.replace_records(records)
    return len(records)


def populate_all(libraries: Optional[List[BaseLibrary]] = None) -> Dict[str, int]:
    """Populate every library that has a mapped Faz 2.4.1 data source.

    ``libraries`` defaults to the nine mapped registered libraries
    (resolved via ``get_library``); pass an explicit list (e.g. of
    fresh, unregistered ``BaseLibrary`` instances) for isolated,
    non-mutating tests. Must be called explicitly -- never invoked by
    package import. Idempotent -- see :func:`populate_library`.
    Returns a ``{library_name: record_count}`` dict.
    """
    targets = libraries
    if targets is None:
        targets = [get_library(key) for key in POPULATION_SOURCES]
    results: Dict[str, int] = {}
    for library in targets:
        if library.metadata.key not in POPULATION_SOURCES:
            continue
        results[library.metadata.name] = populate_library(library)
    return results


def total_population_record_count() -> int:
    """Sum of records across every Faz 2.4.1 data file, including the
    OEM catalog (which is never written into a registered library)."""
    total = sum(len(load_population_records(key)) for key in POPULATION_SOURCES)
    return total + len(oem_catalog())


# ---------------------------------------------------------------------
# Validation / data-integrity checks
# ---------------------------------------------------------------------

def validate_population_source(library_key: str) -> List[str]:
    """Run structural (duplicate-id) and typed-schema validation over
    a data file's raw records, without touching any registered
    library. Returns human-readable violation messages (empty list
    means the data file is clean)."""
    from . import models as models_module

    records = load_population_records(library_key)
    issues = [
        issue.message for issue in validator_module.find_duplicate_ids(records)
    ]
    issues.extend(models_module.find_schema_violations(library_key, records))
    return issues


def validate_all_population_sources() -> Dict[str, List[str]]:
    """Run :func:`validate_population_source` over every mapped data
    file. Returns ``{library_key: [violation, ...]}``."""
    return {key: validate_population_source(key) for key in POPULATION_SOURCES}


def find_invalid_status_values() -> List[str]:
    """Flag any record (across all domains, including the OEM
    catalog) whose ``validation_status``/``approval_status`` is
    outside the Faz 2.4.1 vocabulary, or whose
    ``approval_status == "approved"`` while
    ``validation_status != "validated"`` (never allowed)."""
    issues: List[str] = []
    for key in list(POPULATION_SOURCES) + ["oem catalog"]:
        records = oem_catalog() if key == "oem catalog" else load_population_records(key)
        for record in records:
            vstatus = record.get("validation_status")
            astatus = record.get("approval_status")
            rid = record.get("id", "<no id>")
            if vstatus not in KNOWN_VALIDATION_STATUS:
                issues.append(f"{key}/{rid}: unknown validation_status {vstatus!r}")
            if astatus not in KNOWN_APPROVAL_STATUS:
                issues.append(f"{key}/{rid}: unknown approval_status {astatus!r}")
            if astatus == "approved" and vstatus != "validated":
                issues.append(
                    f"{key}/{rid}: approved while validation_status={vstatus!r}"
                )
    return issues


def find_checksum_mismatches() -> List[str]:
    """Recompute each record's checksum (over every field except
    ``checksum`` itself) and flag any record whose stored checksum
    does not match -- i.e. tamper/corruption detection."""
    issues: List[str] = []
    for key in list(POPULATION_SOURCES) + ["oem catalog"]:
        records = oem_catalog() if key == "oem catalog" else load_population_records(key)
        for record in records:
            stored = record.get("checksum", "")
            payload = {k: v for k, v in record.items() if k != "checksum"}
            expected = hashlib.sha256(
                json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            if stored != expected:
                issues.append(f"{key}/{record.get('id')}: checksum mismatch")
    return issues


def find_duplicate_standard_size_variant() -> List[str]:
    """Flag any (standard, size/designation, variant) combination that
    repeats within a domain -- each combination should be unique.
    Uses ``id`` as the combination key, since every generator encodes
    standard+size+variant into ``id`` (e.g. "NUT-ISO4032-M10")."""
    issues: List[str] = []
    for key in POPULATION_SOURCES:
        records = load_population_records(key)
        seen: Dict[str, int] = {}
        for index, record in enumerate(records):
            rid = str(record.get("id", ""))
            if rid in seen:
                issues.append(f"{key}: duplicate id {rid!r} (first at {seen[rid]})")
            else:
                seen[rid] = index
    return issues


_GEOMETRIC_FIELDS = (
    "diameter_mm", "nominal_diameter_mm", "pitch_mm", "pitch_diameter_mm",
    "minor_diameter_mm", "stress_area_mm2", "head_across_flats_mm",
    "head_across_corners_mm", "head_height_mm", "socket_size_mm",
    "washer_face_diameter_mm", "bearing_diameter_mm", "recommended_hole_mm",
    "clearance_hole_medium_mm", "tap_drill_mm", "thread_engagement_mm",
    "weight_kg_per_100", "height_mm", "width_across_flats_mm",
    "inner_diameter_mm", "outer_diameter_mm", "thickness_mm",
)


def find_non_positive_geometric_values() -> List[str]:
    """Flag any record where a known geometric field is present and
    numeric but <= 0 (``None`` fields -- not applicable to that
    record shape -- are skipped, not flagged)."""
    issues: List[str] = []
    for key in POPULATION_SOURCES:
        records = load_population_records(key)
        for record in records:
            for field in _GEOMETRIC_FIELDS:
                if field not in record:
                    continue
                value = record[field]
                if value is None:
                    continue
                if isinstance(value, (int, float)) and value <= 0:
                    issues.append(
                        f"{key}/{record.get('id')}: {field}={value} <= 0"
                    )
    return issues


def find_strength_class_range_violations() -> List[str]:
    """Flag strength-class records where rp02_mpa > rm_mpa (yield
    must not exceed ultimate)."""
    issues: List[str] = []
    for record in load_population_records("strength class library"):
        rp02 = record.get("rp02_mpa")
        rm = record.get("rm_mpa")
        if rp02 is not None and rm is not None and rp02 > rm:
            issues.append(f"{record.get('id')}: rp02_mpa {rp02} > rm_mpa {rm}")
    return issues


def find_material_range_violations() -> List[str]:
    """Flag material records where yield_mpa > ultimate_mpa."""
    issues: List[str] = []
    for record in load_population_records("material library"):
        yld = record.get("yield_mpa")
        ult = record.get("ultimate_mpa")
        if yld is not None and ult is not None and yld > ult:
            issues.append(f"{record.get('id')}: yield_mpa {yld} > ultimate_mpa {ult}")
    return issues


def find_pitch_series_violations() -> List[str]:
    """Flag thread records where a Fine/Extra Fine pitch is not
    strictly smaller than the Coarse pitch for the same nominal
    diameter."""
    issues: List[str] = []
    threads = load_population_records("thread library")
    coarse_by_dia: Dict[float, float] = {
        r["nominal_diameter_mm"]: r["pitch_mm"]
        for r in threads if r.get("series") == "Coarse"
    }
    for record in threads:
        series = record.get("series")
        if series not in ("Fine", "Extra Fine"):
            continue
        dia = record.get("nominal_diameter_mm")
        if not isinstance(dia, (int, float)):
            continue
        coarse_pitch = coarse_by_dia.get(dia)
        if coarse_pitch is not None and not (record["pitch_mm"] < coarse_pitch):
            issues.append(
                f"{record.get('id')}: {series} pitch {record['pitch_mm']} "
                f"not < coarse pitch {coarse_pitch} for M{dia:g}"
            )
    return issues


def find_dangling_thread_references() -> List[str]:
    """Flag bolt-library records whose ``thread`` designation does not
    exist as a Coarse (or matching) entry in the Thread Library."""
    known_designations = {
        r["designation"] for r in load_population_records("thread library")
    }
    issues: List[str] = []
    for record in load_population_records("bolt library"):
        thread = record.get("thread")
        if thread and thread not in known_designations:
            issues.append(
                f"{record.get('id')}: references unknown thread {thread!r}"
            )
    return issues


def find_broken_compatibility_references() -> List[str]:
    """Flag compatibility-library rules whose bolt_class/
    minimum_nut_class are not present in the Strength Class Library."""
    strength = load_population_records("strength class library")
    known_bolt = {r["designation"] for r in strength if r["category"] == "Bolt"}
    known_nut = {r["designation"] for r in strength if r["category"] == "Nut"}
    issues: List[str] = []
    for record in load_population_records("compatibility library"):
        bolt_class = record.get("bolt_class")
        nut_class = record.get("minimum_nut_class")
        if bolt_class not in known_bolt:
            issues.append(f"{record.get('id')}: unknown bolt_class {bolt_class!r}")
        if nut_class not in known_nut:
            issues.append(f"{record.get('id')}: unknown minimum_nut_class {nut_class!r}")
    return issues


def run_all_integrity_checks() -> Dict[str, List[str]]:
    """Run every Faz 2.4.1 data-integrity check and return a
    ``{check_name: [issue, ...]}`` report. An empty list for a check
    means it found nothing to flag."""
    return {
        "schema_and_duplicates": [
            issue
            for issues in validate_all_population_sources().values()
            for issue in issues
        ],
        "duplicate_ids": find_duplicate_standard_size_variant(),
        "non_positive_geometry": find_non_positive_geometric_values(),
        "strength_class_ranges": find_strength_class_range_violations(),
        "material_ranges": find_material_range_violations(),
        "pitch_series": find_pitch_series_violations(),
        "dangling_thread_references": find_dangling_thread_references(),
        "broken_compatibility_references": find_broken_compatibility_references(),
        "invalid_status_values": find_invalid_status_values(),
        "checksum_mismatches": find_checksum_mismatches(),
    }


# ---------------------------------------------------------------------
# Search API (spec: find_bolt / find_nut / find_material / find_thread
# / find_coating / find_lubrication / list_strength_classes /
# list_oems). Reads population data files directly -- independent of
# registry population state, never mutates a registered library.
# ---------------------------------------------------------------------

def find_thread(
    designation: Optional[str] = None,
    series: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Look up thread geometry records, optionally filtered by exact
    ``designation`` (e.g. "M8") and/or ``series`` (e.g. "Coarse",
    "Fine", "Extra Fine", "UNC", ...)."""
    records = load_population_records("thread library")
    if designation is not None:
        records = [r for r in records if r.get("designation") == designation]
    if series is not None:
        records = [r for r in records if r.get("series", "").lower() == series.lower()]
    return records


def find_bolt(
    diameter_mm: Optional[float] = None,
    property_class: Optional[str] = None,
    head_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Look up bolt master records, optionally filtered by nominal
    ``diameter_mm``, ``property_class`` and/or ``head_type`` (e.g.
    "Hex", "Socket")."""
    records = load_population_records("bolt library")
    if diameter_mm is not None:
        records = [r for r in records if r.get("diameter_mm") == diameter_mm]
    if property_class is not None:
        records = [r for r in records if r.get("property_class") == property_class]
    if head_type is not None:
        records = [
            r for r in records if r.get("head_type", "").lower() == head_type.lower()
        ]
    return records


def find_nut(
    diameter_mm: Optional[float] = None,
    standard: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Look up nut master records, optionally filtered by thread
    diameter (parsed from ``designation``/``thread``) and/or
    ``standard`` (e.g. "ISO 4032")."""
    records = load_population_records("nut library")
    if standard is not None:
        records = [r for r in records if r.get("source_standard") == standard]
    if diameter_mm is not None:
        needle = f"M{diameter_mm:g}"
        records = [
            r for r in records if r.get("thread", "").split("x")[0] == needle
        ]
    return records


def find_material(name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Look up material property-set records, optionally filtered by
    a case-insensitive substring match on ``material``."""
    records = load_population_records("material library")
    if name is not None:
        needle = name.strip().lower()
        records = [r for r in records if needle in r.get("material", "").lower()]
    return records


def find_coating(name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Look up coating records, optionally filtered by a
    case-insensitive substring match on ``designation``."""
    records = load_population_records("coating library")
    if name is not None:
        needle = name.strip().lower()
        records = [r for r in records if needle in r.get("designation", "").lower()]
    return records


def find_lubrication(name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Look up lubrication records, optionally filtered by a
    case-insensitive substring match on ``designation``."""
    records = load_population_records("lubrication library")
    if name is not None:
        needle = name.strip().lower()
        records = [r for r in records if needle in r.get("designation", "").lower()]
    return records


def list_strength_classes(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return strength class records, optionally filtered by
    ``category`` ("Bolt" or "Nut")."""
    records = load_population_records("strength class library")
    if category is not None:
        records = [
            r for r in records if r.get("category", "").lower() == category.lower()
        ]
    return records


def list_oems() -> List[str]:
    """Return the canonical OEM names in the Faz 2.4.1 OEM catalog."""
    return [record["oem_name"] for record in oem_catalog()]


__all__ = [
    "DATA_DIR",
    "POPULATION_SOURCES",
    "OEM_SOURCE",
    "KNOWN_VALIDATION_STATUS",
    "KNOWN_APPROVAL_STATUS",
    "load_population_records",
    "oem_catalog",
    "clear_cache",
    "populate_library",
    "populate_all",
    "total_population_record_count",
    "validate_population_source",
    "validate_all_population_sources",
    "find_invalid_status_values",
    "find_checksum_mismatches",
    "find_duplicate_standard_size_variant",
    "find_non_positive_geometric_values",
    "find_strength_class_range_violations",
    "find_material_range_violations",
    "find_pitch_series_violations",
    "find_dangling_thread_references",
    "find_broken_compatibility_references",
    "run_all_integrity_checks",
    "find_thread",
    "find_bolt",
    "find_nut",
    "find_material",
    "find_coating",
    "find_lubrication",
    "list_strength_classes",
    "list_oems",
]
