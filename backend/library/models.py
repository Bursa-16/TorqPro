"""TorqPro Engineering Library - typed domain record schemas (Faz 2.4.0).

Adds an additive, Pydantic-based typed layer on top of the existing
Phase 1.3/1.4 infrastructure (``registry.py``, ``loader.py``,
``migration.py``, ``validator.py``). Nothing here changes existing
behaviour:

- ``BaseLibrary`` still stores raw ``Dict[str, Any]`` records; this
  module only *validates a view* of those records against a typed
  schema, on demand.
- No record is migrated, loaded or mutated by importing this module.
- No engineering formula, no calculation logic, no API/GUI coupling.
- Independent from ``backend.engineering_core``, ``backend.standards``
  and ``backend.calculation_engine``.

Ten record schemas are defined: one per existing domain shell
(bolt, nut, washer, thread, material, coating, lubrication,
strength_class, compatibility) plus ``OEMRecord`` for the
adapter-only OEM shell (see ``backend/library/oem_library.py``).
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Dict, List, Sequence, Tuple, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ConfidenceLevel(IntEnum):
    """Source-traceability confidence grade for a library record.

    Values match the ``"confidence"`` integer already used by the
    existing JSON reference files under ``data/`` (e.g.
    ``data/Civata_Somun_Uyumluluk.json``, ``data/Teknik_Kaynak_Kayitlari.json``):
    G1 is the highest-confidence, directly-sourced grade; G4 is the
    lowest (provisional / unverified).
    """

    G1 = 1
    G2 = 2
    G3 = 3
    G4 = 4


class LibraryRecordBase(BaseModel):
    """Common shape shared by every typed domain record.

    ``model_config`` allows extra fields: the existing JSON reference
    files may carry additional descriptive keys that no domain schema
    below models explicitly yet, and this phase must not reject a
    record purely for carrying an unmodelled field. Extra fields are
    preserved on the instance but not type-checked.
    """

    model_config = ConfigDict(extra="allow")

    id: str = ""
    source_standard: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.G4
    notes: str = ""

    # Faz 2.4.1: engineering-database provenance fields. All optional
    # with safe defaults so every existing record/test from Faz 2.4.0
    # and earlier (which never set these) keeps validating unchanged.
    revision: str = ""
    source: str = ""
    version: str = ""
    validation_status: str = "provisional"
    approval_status: str = "pending"
    checksum: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BoltRecord(LibraryRecordBase):
    """Bolt / screw / stud master record (see ``bolt_library.py``)."""

    designation: str = ""
    thread: str = ""
    property_class: str = ""
    material: str = ""
    length_mm: float | None = None
    head_type: str = ""


class NutRecord(LibraryRecordBase):
    """Nut master record (see ``nut_library.py``)."""

    designation: str = ""
    thread: str = ""
    property_class: str = ""
    height_mm: float | None = None


class WasherRecord(LibraryRecordBase):
    """Washer master record (see ``washer_library.py``)."""

    designation: str = ""
    inner_diameter_mm: float | None = None
    outer_diameter_mm: float | None = None
    thickness_mm: float | None = None
    hardness: str = ""


class ThreadRecord(LibraryRecordBase):
    """Thread geometry record (see ``thread_library.py``).

    ``designation`` is required and validated elsewhere against a
    metric thread pattern by
    ``backend.library.validator.is_valid_thread_designation`` --
    unchanged by this schema, which only checks presence/type here.
    """

    designation: str
    nominal_diameter_mm: float | None = None
    pitch_mm: float | None = None
    tolerance_class: str = ""
    stress_area_source: str = ""


class MaterialRecord(LibraryRecordBase):
    """Material property-set record (see ``material_library.py``)."""

    material: str
    grade: str = ""
    rp02_mpa: float | None = None
    rm_mpa: float | None = None
    elastic_modulus_mpa: float | None = None


class CoatingRecord(LibraryRecordBase):
    """Surface/coating specification record (see ``coating_library.py``)."""

    designation: str = ""
    coating_type: str = ""
    thickness_um: float | None = None
    friction_coefficient_range: str = ""


class LubricationRecord(LibraryRecordBase):
    """Lubricant/friction-condition record (see ``lubrication_library.py``)."""

    designation: str = ""
    lubricant_type: str = ""
    friction_coefficient_min: float | None = None
    friction_coefficient_max: float | None = None
    application: str = ""


class StrengthClassRecord(LibraryRecordBase):
    """Bolt/nut property-class reference record
    (see ``strength_class_library.py``)."""

    designation: str = ""
    category: str = ""
    rp02_mpa: float | None = None
    rm_mpa: float | None = None
    hardness_range: str = ""


class CompatibilityRecord(LibraryRecordBase):
    """Bolt/nut/washer compatibility rule record (see
    ``compatibility.py``). Field names match
    ``backend.library.validator.find_broken_compatibility`` unchanged.
    """

    bolt_class: str
    minimum_nut_class: str


class OEMRecord(LibraryRecordBase):
    """Adapter-only record describing a reference into
    ``backend.standards`` (see ``oem_library.py``).

    Carries no engineering data of its own: ``standard_reference``
    names the ``backend.standards`` entry this record adapts, and no
    field here duplicates that standard's content.
    """

    oem_name: str = ""
    standard_reference: str
    supported_calculations: Tuple[str, ...] = ()


#: Canonical mapping from a registered library's ``metadata.key``
#: (see ``backend.library.search.CATEGORY_LIBRARY_MAP`` for the
#: parallel category-name mapping) to its typed record schema.
LIBRARY_RECORD_MODELS: Dict[str, Type[LibraryRecordBase]] = {
    "bolt library": BoltRecord,
    "nut library": NutRecord,
    "washer library": WasherRecord,
    "thread library": ThreadRecord,
    "material library": MaterialRecord,
    "coating library": CoatingRecord,
    "lubrication library": LubricationRecord,
    "strength class library": StrengthClassRecord,
    "compatibility library": CompatibilityRecord,
    "oem library": OEMRecord,
}


def get_record_model(library_key: str) -> Type[LibraryRecordBase]:
    """Return the typed schema registered for ``library_key``, or the
    generic ``LibraryRecordBase`` if no domain-specific schema is
    mapped (never raises)."""
    return LIBRARY_RECORD_MODELS.get(library_key, LibraryRecordBase)


def parse_typed_records(
    library_key: str, records: Sequence[Dict[str, Any]]
) -> List[LibraryRecordBase]:
    """Validate and parse ``records`` against ``library_key``'s typed
    schema. Raises ``pydantic.ValidationError`` on the first invalid
    record (strict variant -- see ``find_schema_violations`` for a
    non-raising report)."""
    model = get_record_model(library_key)
    return [model.model_validate(raw) for raw in records]


def find_schema_violations(
    library_key: str, records: Sequence[Dict[str, Any]]
) -> List[str]:
    """Validate ``records`` against ``library_key``'s typed schema and
    return human-readable violation messages instead of raising.

    An empty list means every record satisfies the schema. Does not
    mutate ``records`` or any registered library."""
    model = get_record_model(library_key)
    violations: List[str] = []
    for index, raw in enumerate(records):
        try:
            model.model_validate(raw)
        except ValidationError as exc:
            for error in exc.errors():
                location = ".".join(str(part) for part in error["loc"]) or "<record>"
                violations.append(f"[{index}] {location}: {error['msg']}")
    return violations


__all__ = [
    "ConfidenceLevel",
    "LibraryRecordBase",
    "BoltRecord",
    "NutRecord",
    "WasherRecord",
    "ThreadRecord",
    "MaterialRecord",
    "CoatingRecord",
    "LubricationRecord",
    "StrengthClassRecord",
    "CompatibilityRecord",
    "OEMRecord",
    "LIBRARY_RECORD_MODELS",
    "get_record_model",
    "parse_typed_records",
    "find_schema_violations",
]
