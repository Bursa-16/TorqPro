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
    "joint hardware library": "joint_hardware_library.json",
    "friction condition library": "friction_condition_library.json",
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


def validate_thread_library_records() -> List[str]:
    """Run the Faz 2.4.1A thread-specific checks
    (``validator.validate_thread_library``) over the live thread
    library data file. Kept separate from
    ``validate_all_population_sources`` above -- that function's
    Faz 2.4.1 semantics (duplicate-id + typed-schema only) are
    unchanged; this is an additional, thread-only entry point."""
    records = load_population_records("thread library")
    report = validator_module.validate_thread_library(records)
    return [issue.message for issue in report.issues]


def validate_bolt_library_records() -> List[str]:
    """Run the Faz 2.4.1B bolt-specific checks
    (``validator.validate_bolt_library``) over the live bolt library
    data file. Additional, bolt-only entry point -- does not replace
    ``validate_all_population_sources``."""
    records = load_population_records("bolt library")
    report = validator_module.validate_bolt_library(records)
    return [issue.message for issue in report.issues]


def validate_nut_library_records() -> List[str]:
    """Run the Faz 2.4.1B nut-specific checks
    (``validator.validate_nut_library``) over the live nut library
    data file. Additional, nut-only entry point -- does not replace
    ``validate_all_population_sources``."""
    records = load_population_records("nut library")
    report = validator_module.validate_nut_library(records)
    return [issue.message for issue in report.issues]


def validate_lubrication_library_records() -> List[str]:
    """Run the Faz 2.6.1 Friction Condition (Lubrication subsection)
    checks (``validator.validate_lubrication_library``) over the live
    lubrication library data file. Additional, lubrication-only entry
    point -- does not replace ``validate_all_population_sources``."""
    records = load_population_records("lubrication library")
    report = validator_module.validate_lubrication_library(records)
    return [issue.message for issue in report.issues]


def validate_friction_condition_library_records() -> List[str]:
    """Run the Faz 2.6.2A Friction Condition Library checks
    (``validator.validate_friction_condition_library``) over the live
    data file. Currently always returns an empty list -- the file has
    no records yet (see ``friction_condition_library.py``, ADR-0010)."""
    records = load_population_records("friction condition library")
    report = validator_module.validate_friction_condition_library(records)
    return [issue.message for issue in report.issues]


def validate_washer_library_records() -> List[str]:
    """Run the Faz 2.4.1C washer-specific checks
    (``validator.validate_washer_library``) over the live washer
    library data file. Additional, washer-only entry point -- does
    not replace ``validate_all_population_sources``."""
    records = load_population_records("washer library")
    report = validator_module.validate_washer_library(records)
    return [issue.message for issue in report.issues]


def validate_joint_hardware_library_records() -> List[str]:
    """Run the Faz 2.4.1C joint-hardware checks
    (``validator.validate_joint_hardware_library``) over the live
    joint hardware library data file. Currently always returns an
    empty list -- the data file has no records yet (see
    ``joint_hardware_library.py``)."""
    records = load_population_records("joint hardware library")
    report = validator_module.validate_joint_hardware_library(records)
    return [issue.message for issue in report.issues]


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
    # -- Faz 2.4.1B additions --
    "nominal_length_mm", "threaded_length_mm", "wrench_size_mm",
    "under_head_bearing_diameter_mm", "reduced_shank_diameter_mm",
    "width_across_corners_mm", "flange_diameter_mm",
    "bearing_surface_diameter_mm", "proof_load_n",
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


def find_broken_friction_condition_references() -> List[str]:
    """Flag ``friction condition library`` records whose non-empty
    ``coating_id``/``lubricant_id`` is not present in the live
    Coating Library / Lubrication Library (Faz 2.6.2B, ADR-0010). An
    empty reference is not a violation -- see
    ``validator.find_dangling_coating_references`` /
    ``find_dangling_lubricant_references`` docstrings."""
    coating_ids = {r["id"] for r in load_population_records("coating library")}
    lubricant_ids = {r["id"] for r in load_population_records("lubrication library")}
    records = load_population_records("friction condition library")
    issues = validator_module.find_dangling_coating_references(records, coating_ids)
    issues += validator_module.find_dangling_lubricant_references(records, lubricant_ids)
    return [issue.message for issue in issues]


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
        "broken_friction_condition_references": find_broken_friction_condition_references(),
        "invalid_status_values": find_invalid_status_values(),
        "checksum_mismatches": find_checksum_mismatches(),
        "bolt_library_faz2_4_1b": validate_bolt_library_records(),
        "nut_library_faz2_4_1b": validate_nut_library_records(),
        "lubrication_library_faz2_6_1": validate_lubrication_library_records(),
        "friction_condition_library_faz2_6_2a": validate_friction_condition_library_records(),
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
    nominal_diameter_mm: Optional[float] = None,
    pitch_mm: Optional[float] = None,
    pitch_type: Optional[str] = None,
    thread_series: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Look up thread geometry records, optionally filtered by any
    combination of the arguments below (all filters given are
    intersected -- AND, not OR):

    - ``designation``: exact match (e.g. "M8").
    - ``series``: pre-existing free-text field (e.g. "Coarse",
      "Fine", "Extra Fine", "UNC", ...), case-insensitive. Kept for
      backward compatibility -- not deprecated.
    - ``nominal_diameter_mm`` / ``pitch_mm``: exact match (Faz
      2.4.1A).
    - ``pitch_type``: Faz 2.4.1A structured field ("coarse", "fine",
      "extra_fine"), case-insensitive. Acts as an alias of ``series``
      for the records that have a coarse/fine analogue -- either can
      be used, and combining both further narrows the result.
    - ``thread_series``: Faz 2.4.1A structured field ("ISO_METRIC",
      "UNC", "UNF", "UNEF", "BSP", "NPT", "TRAPEZOIDAL"),
      case-insensitive.
    """
    records = load_population_records("thread library")
    if designation is not None:
        records = [r for r in records if r.get("designation") == designation]
    if series is not None:
        records = [r for r in records if r.get("series", "").lower() == series.lower()]
    if nominal_diameter_mm is not None:
        records = [
            r for r in records if r.get("nominal_diameter_mm") == nominal_diameter_mm
        ]
    if pitch_mm is not None:
        records = [r for r in records if r.get("pitch_mm") == pitch_mm]
    if pitch_type is not None:
        records = [
            r for r in records
            if (r.get("pitch_type") or "").lower() == pitch_type.lower()
        ]
    if thread_series is not None:
        records = [
            r for r in records
            if r.get("thread_series", "").lower() == thread_series.lower()
        ]
    return records


def count_iso_metric_thread_records() -> int:
    """Number of thread records in Faz 2.4.1A's own scope
    (``thread_series == "ISO_METRIC"``)."""
    return len(find_thread(thread_series="ISO_METRIC"))


def count_non_iso_metric_thread_records() -> int:
    """Number of pre-existing thread records outside Faz 2.4.1A's
    scope (UNC/UNF/UNEF/BSP/NPT/Trapezoidal)."""
    records = load_population_records("thread library")
    return len([r for r in records if r.get("thread_series") != "ISO_METRIC"])


def find_bolt(
    diameter_mm: Optional[float] = None,
    property_class: Optional[str] = None,
    head_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Look up bolt master records, optionally filtered by nominal
    ``diameter_mm``, ``property_class`` and/or ``head_type`` (e.g.
    "Hex", "Socket"). Pre-existing Faz 2.4.1 API -- unchanged; see
    :func:`search_bolts` for the Faz 2.4.1B extended filter set."""
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
    ``standard`` (e.g. "ISO 4032"). Pre-existing Faz 2.4.1 API --
    unchanged; see :func:`search_nuts` for the Faz 2.4.1B extended
    filter set."""
    records = load_population_records("nut library")
    if standard is not None:
        records = [r for r in records if r.get("source_standard") == standard]
    if diameter_mm is not None:
        needle = f"M{diameter_mm:g}"
        records = [
            r for r in records if r.get("thread", "").split("x")[0] == needle
        ]
    return records


def search_bolts(
    *,
    standard: Optional[str] = None,
    family: Optional[str] = None,
    nominal_diameter: Optional[float] = None,
    pitch: Optional[float] = None,
    strength_class: Optional[str] = None,
    coating: Optional[str] = None,
    material_family: Optional[str] = None,
    coarse_or_fine: Optional[str] = None,
    verified_only: bool = False,
    designation: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Faz 2.4.1B extended bolt search: every filter given is
    intersected (AND, not OR); omitted filters are not applied.

    - ``standard``: exact match on ``source_standard`` (e.g. "ISO 4017").
    - ``family``: case-insensitive exact match on ``bolt_family``
      (e.g. "Hexagon head bolt").
    - ``nominal_diameter`` / ``pitch``: exact match on
      ``nominal_diameter_mm`` / ``pitch_mm``.
    - ``strength_class``: exact match on ``property_class`` (e.g. "10.9").
    - ``coating``: case-insensitive substring match against any entry
      in ``coating_compatibility``.
    - ``material_family``: case-insensitive substring match on ``material``.
    - ``coarse_or_fine``: case-insensitive exact match on ``coarse_or_fine``.
    - ``verified_only``: when True, keep only
      ``verification_status == "verified"`` records.
    - ``designation``: case-insensitive substring match on ``designation``.
    """
    records = load_population_records("bolt library")
    if standard is not None:
        records = [r for r in records if r.get("source_standard") == standard]
    if family is not None:
        records = [
            r for r in records if r.get("bolt_family", "").lower() == family.lower()
        ]
    if nominal_diameter is not None:
        records = [
            r for r in records
            if r.get("nominal_diameter_mm", r.get("diameter_mm")) == nominal_diameter
        ]
    if pitch is not None:
        records = [
            r for r in records if r.get("pitch_mm", r.get("pitch_coarse_mm")) == pitch
        ]
    if strength_class is not None:
        records = [r for r in records if r.get("property_class") == strength_class]
    if coating is not None:
        needle = coating.strip().lower()
        records = [
            r for r in records
            if any(needle in c.lower() for c in r.get("coating_compatibility", []))
        ]
    if material_family is not None:
        needle = material_family.strip().lower()
        records = [r for r in records if needle in r.get("material", "").lower()]
    if coarse_or_fine is not None:
        records = [
            r for r in records
            if r.get("coarse_or_fine", "").lower() == coarse_or_fine.lower()
        ]
    if verified_only:
        records = [r for r in records if r.get("verification_status") == "verified"]
    if designation is not None:
        needle = designation.strip().lower()
        records = [r for r in records if needle in r.get("designation", "").lower()]
    return records


def search_nuts(
    *,
    standard: Optional[str] = None,
    family: Optional[str] = None,
    nominal_diameter: Optional[float] = None,
    pitch: Optional[float] = None,
    strength_class: Optional[str] = None,
    coating: Optional[str] = None,
    locking_principle: Optional[str] = None,
    coarse_or_fine: Optional[str] = None,
    verified_only: bool = False,
    designation: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Faz 2.4.1B extended nut search -- same filter-intersection
    convention as :func:`search_bolts`.

    - ``standard``: exact match on ``source_standard`` (e.g. "ISO 4032").
    - ``family``: case-insensitive exact match on ``nut_family``
      (e.g. "Nylon insert lock nut").
    - ``nominal_diameter`` / ``pitch``: exact match on
      ``nominal_diameter_mm`` / ``pitch_mm``.
    - ``strength_class``: exact match on ``property_class`` (e.g. "10").
    - ``coating``: case-insensitive substring match against any entry
      in ``coating_compatibility``.
    - ``locking_principle``: case-insensitive substring match on
      ``locking_principle``.
    - ``coarse_or_fine``: case-insensitive exact match on ``coarse_or_fine``.
    - ``verified_only``: when True, keep only
      ``verification_status == "verified"`` records.
    - ``designation``: case-insensitive substring match on ``designation``.
    """
    records = load_population_records("nut library")
    if standard is not None:
        records = [r for r in records if r.get("source_standard") == standard]
    if family is not None:
        records = [
            r for r in records if r.get("nut_family", "").lower() == family.lower()
        ]
    if nominal_diameter is not None:
        records = [
            r for r in records if r.get("nominal_diameter_mm") == nominal_diameter
        ]
    if pitch is not None:
        records = [r for r in records if r.get("pitch_mm") == pitch]
    if strength_class is not None:
        records = [r for r in records if r.get("property_class") == strength_class]
    if coating is not None:
        needle = coating.strip().lower()
        records = [
            r for r in records
            if any(needle in c.lower() for c in r.get("coating_compatibility", []))
        ]
    if locking_principle is not None:
        needle = locking_principle.strip().lower()
        records = [r for r in records if needle in r.get("locking_principle", "").lower()]
    if coarse_or_fine is not None:
        records = [
            r for r in records
            if r.get("coarse_or_fine", "").lower() == coarse_or_fine.lower()
        ]
    if verified_only:
        records = [r for r in records if r.get("verification_status") == "verified"]
    if designation is not None:
        needle = designation.strip().lower()
        records = [r for r in records if needle in r.get("designation", "").lower()]
    return records


def find_washer_by_standard(standard: str) -> List[Dict[str, Any]]:
    """Faz 2.4.1C washer search -- exact (case-sensitive) match on
    ``source_standard`` (e.g. "ISO 7089", "DIN 127 B")."""
    records = load_population_records("washer library")
    return [r for r in records if r.get("source_standard") == standard]


def find_washer_by_size(
    nominal_size_mm: Optional[float] = None,
    designation: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Faz 2.4.1C washer search -- filter by nominal bolt size, via
    ``nominal_size_mm`` (matched against the numeric part of any
    ``compatible_bolt_sizes`` entry, e.g. 3.5 matches "M3.5") and/or a
    case-insensitive substring match on ``designation``."""
    records = load_population_records("washer library")
    if nominal_size_mm is not None:
        needle = f"M{nominal_size_mm:g}"
        records = [
            r for r in records
            if needle in r.get("compatible_bolt_sizes", [])
        ]
    if designation is not None:
        needle = designation.strip().lower()
        records = [r for r in records if needle in r.get("designation", "").lower()]
    return records


def find_washer_by_material(material: str) -> List[Dict[str, Any]]:
    """Faz 2.4.1C washer search -- case-insensitive substring match
    on ``material``. Records with no ``material`` set (most
    pre-existing flat-washer records -- see the Faz 2.4.1C generator
    docstring) are excluded rather than matched."""
    needle = material.strip().lower()
    records = load_population_records("washer library")
    return [r for r in records if needle in r.get("material", "").lower()]


def find_washer_for_bolt(bolt_size: str) -> List[Dict[str, Any]]:
    """Faz 2.4.1C washer search -- washers whose ``compatible_bolt_sizes``
    contains ``bolt_size`` exactly (e.g. "M8"). Case-insensitive."""
    needle = bolt_size.strip().upper()
    records = load_population_records("washer library")
    return [
        r for r in records
        if needle in [s.upper() for s in r.get("compatible_bolt_sizes", [])]
    ]


def find_washer_locking(locking: Optional[str] = None) -> List[Dict[str, Any]]:
    """Faz 2.4.1C washer search -- washers with a non-empty
    ``locking_principle`` (i.e. lock washers, as opposed to plain
    flat washers), optionally filtered further by a case-insensitive
    substring match on ``locking_principle`` itself."""
    records = load_population_records("washer library")
    records = [r for r in records if r.get("locking_principle")]
    if locking is not None:
        needle = locking.strip().lower()
        records = [r for r in records if needle in r.get("locking_principle", "").lower()]
    return records


def find_washer_temperature(
    min_c: Optional[float] = None,
    max_c: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Faz 2.4.1C washer search -- washers whose declared operating
    range covers ``[min_c, max_c]`` (either bound optional). Records
    with no declared temperature range are excluded -- none of the
    currently-populated washer records has a verified temperature
    limit (see the Faz 2.4.1C generator docstring), so this currently
    returns an empty list until such a record is added with a real
    source."""
    records = load_population_records("washer library")
    result = []
    for r in records:
        rec_min = r.get("operating_temperature_min_c")
        rec_max = r.get("operating_temperature_max_c")
        if rec_min is None or rec_max is None:
            continue
        if min_c is not None and rec_min > min_c:
            continue
        if max_c is not None and rec_max < max_c:
            continue
        result.append(r)
    return result


def find_joint_hardware_by_type(hardware_type: str) -> List[Dict[str, Any]]:
    """Faz 2.4.1C joint hardware search -- case-insensitive exact
    match on ``hardware_type`` (e.g. "Dowel pin", "Bushing"). Returns
    an empty list against the current (unpopulated) data file --
    that is correct, not an error; see
    ``joint_hardware_library.py``."""
    needle = hardware_type.strip().lower()
    records = load_population_records("joint hardware library")
    return [r for r in records if r.get("hardware_type", "").lower() == needle]


def find_joint_hardware_by_standard(standard: str) -> List[Dict[str, Any]]:
    """Faz 2.4.1C joint hardware search -- exact match on
    ``source_standard``. Returns an empty list against the current
    (unpopulated) data file -- that is correct, not an error."""
    records = load_population_records("joint hardware library")
    return [r for r in records if r.get("source_standard") == standard]


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
    "find_broken_friction_condition_references",
    "run_all_integrity_checks",
    "find_thread",
    "count_iso_metric_thread_records",
    "count_non_iso_metric_thread_records",
    "validate_thread_library_records",
    "validate_bolt_library_records",
    "validate_nut_library_records",
    "validate_lubrication_library_records",
    "validate_friction_condition_library_records",
    "validate_washer_library_records",
    "validate_joint_hardware_library_records",
    "find_bolt",
    "find_nut",
    "search_bolts",
    "search_nuts",
    "find_washer_by_standard",
    "find_washer_by_size",
    "find_washer_by_material",
    "find_washer_for_bolt",
    "find_washer_locking",
    "find_washer_temperature",
    "find_joint_hardware_by_type",
    "find_joint_hardware_by_standard",
    "find_material",
    "find_coating",
    "find_lubrication",
    "list_strength_classes",
    "list_oems",
]
