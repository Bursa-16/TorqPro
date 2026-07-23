"""TorqPro Engineering Library - typed domain record schemas (Faz 2.4.0,
extended through Faz 2.4.2B).

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

Faz 2.4.2B ("Library Schema Completion") closes the gap identified by
the Faz 2.4.2A inventory (``docs/phase_2_4_2_schema_inventory.md``):
every field that was previously accepted only via
``LibraryRecordBase``'s ``extra="allow"`` is now declared explicitly
on its domain model, a shared metadata block is added to every record
type, closed-vocabulary free-text fields gain typed ``Enum``
counterparts, and every record gains ``to_dict()`` / ``from_dict()``
/ ``serialize()`` / ``deserialize()`` convenience methods. Two rules
carried over unchanged from every earlier phase governed this work:

- **Additive only.** Every field this phase adds is optional with a
  safe default. No field from an earlier phase was renamed, removed,
  retyped in a way that could reject previously-valid data, or made
  required. A record that validated before Faz 2.4.2B validates
  identically after it.
- **No invented data.** Enum member sets are derived from the actual
  values observed in ``data/*.json`` (see the inventory doc); no
  record's stored values were changed by this phase.

``extra="allow"`` remains in force on every domain model except
``ThreadRecord`` (unchanged from Faz 2.4.1A) -- Faz 2.4.2B is schema
completion, not a strict-mode migration; see inventory §8 for why a
blanket ``extra="forbid"`` switch is a separate, still-open decision.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

#: Bound so ``LibraryRecordBase.from_dict`` / ``.deserialize`` return
#: the calling subclass's own type (e.g. ``BoltRecord.from_dict(...)``
#: is typed as returning ``BoltRecord``, not the base class).
_RecordT = TypeVar("_RecordT", bound="LibraryRecordBase")


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


class Status(str, Enum):
    """Generic record lifecycle status (Faz 2.4.2B).

    Distinct from -- and does not replace -- the pre-existing
    free-text ``validation_status`` / ``approval_status`` /
    ``record_status`` / ``verification_status`` fields already carried
    by individual domain models (Faz 2.4.0/2.4.1); those keep their
    original string values unchanged. ``status`` is a new, single,
    normalized top-level field available on every record type via
    ``LibraryRecordBase``. Default is ``DRAFT`` so every pre-Faz-2.4.2B
    record -- none of which ever set this new field -- keeps
    validating unchanged.
    """

    DRAFT = "draft"
    PROVISIONAL = "provisional"
    VERIFIED = "verified"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    #: Faz 2.6.0: record describes a lubrication/coating condition that
    #: remains a physically valid reference value (e.g. cadmium
    #: plating) but whose use in new production is restricted or
    #: requires customer/regulatory sign-off. Distinct from
    #: ``DEPRECATED`` ("superseded, do not use") -- a
    #: ``RESTRICTED_LEGACY`` record stays a valid reference value, just
    #: one that must carry a ``regulatory_warning`` (see
    #: ``LubricationRecord``) and route through a compliance check
    #: before use. No specific regulatory clause is asserted by this
    #: value alone.
    RESTRICTED_LEGACY = "restricted_legacy"


class UnitSystem(str, Enum):
    """Unit system a record's numeric fields are expressed in
    (Faz 2.4.2B). Every existing TorqPro library record uses SI/metric
    units exclusively (``_mm``, ``_mpa``, ``_n``, ``_c`` suffixes
    throughout ``data/*.json``), so ``METRIC`` is a safe default for
    every pre-existing record."""

    METRIC = "metric"
    IMPERIAL = "imperial"
    MIXED = "mixed"


class ThreadDirection(str, Enum):
    """Thread handedness (Faz 2.4.2B). No existing bolt/nut record
    stores handedness today -- every record in ``data/bolt_library.json``
    / ``data/nut_library.json`` describes a standard right-hand-thread
    fastener, which is the overwhelming default for catalog fasteners
    unless a part is explicitly documented as left-hand. ``RIGHT`` is
    therefore used as the default for this new field, not as invented
    per-record data: it names the convention every existing record
    already implicitly follows."""

    RIGHT = "right"
    LEFT = "left"


class ThreadSeries(str, Enum):
    """Recognised thread series (Faz 2.4.2B). Formalizes the
    vocabulary previously held only as the ``KNOWN_THREAD_SERIES``
    tuple (see below, now derived from this enum). Does not change
    ``ThreadRecord.thread_series``, which stays free-text ``str`` for
    backward compatibility (Faz 2.4.1A; see ``ThreadRecord``
    docstring) -- this enum is the canonical, typed definition of the
    same vocabulary, and any future consumer that wants strict typing
    can validate against it directly."""

    ISO_METRIC = "ISO_METRIC"
    UNC = "UNC"
    UNF = "UNF"
    UNEF = "UNEF"
    BSP = "BSP"
    NPT = "NPT"
    TRAPEZOIDAL = "TRAPEZOIDAL"


class StandardType(str, Enum):
    """Standards body that issues/owns a fastener standard
    (Faz 2.4.2B). Replaces the free-text type of the pre-existing
    ``standard_organization`` field on ``BoltRecord`` / ``NutRecord``
    / ``WasherRecord`` / ``JointHardwareRecord`` (Faz 2.4.1B/2.4.1C).
    Every one of the 176 + 211 + 223 real records that set this field
    today uses exactly ``"ISO"``, ``"DIN"`` or ``"EN"`` (verified
    against the live data files) -- all three are covered here, plus
    ``VDI`` and ``FIAT`` (both already recognised standard bodies
    elsewhere in TorqPro, e.g. ``backend/standards``) and ``OTHER`` /
    ``UNSPECIFIED`` for forward compatibility. ``UNSPECIFIED`` (value
    ``""``) is the default, matching the pre-existing field's
    ``str = ""`` default exactly, so any record that never set
    ``standard_organization`` keeps validating unchanged."""

    ISO = "ISO"
    DIN = "DIN"
    EN = "EN"
    VDI = "VDI"
    FIAT = "FIAT"
    ASTM = "ASTM"
    OTHER = "OTHER"
    UNSPECIFIED = ""


class MaterialType(str, Enum):
    """Base material family (Faz 2.4.2B). Retypes
    ``MaterialRecord.material`` (Faz 2.4.0, previously free-text
    ``str``). All 8 real records in ``data/material_library.json``
    use exactly one of the first 8 values below (verified against the
    live data file); ``OTHER`` is provided for forward compatibility
    only and is not used by any existing record. ``material`` remains
    a *required* field, unchanged from Faz 2.4.0 -- only its type
    narrows from free-text ``str`` to this closed, fully-covered
    vocabulary."""

    STEEL = "Steel"
    ALLOY_STEEL = "Alloy Steel"
    STAINLESS_A2 = "Stainless A2"
    STAINLESS_A4 = "Stainless A4"
    TITANIUM = "Titanium"
    ALUMINIUM = "Aluminium"
    BRASS = "Brass"
    CAST_IRON = "Cast Iron"
    OTHER = "Other"


class CoatingType(str, Enum):
    """Coating/finish specification (Faz 2.4.2B). Retypes
    ``CoatingRecord.coating_type`` (Faz 2.4.0, previously free-text
    ``str``). Members reproduce, verbatim and without reinterpretation,
    the exact 10 descriptive strings already stored in
    ``data/coating_library.json`` -- these are per-standard finish
    specifications (e.g. including the governing ISO number), not a
    compressible category code, so no value here was invented or
    reclassified. ``OTHER`` and ``UNSPECIFIED`` (value ``""``, used as
    this field's default) are provided for forward/backward
    compatibility only, matching the pre-existing field's
    ``str = ""`` default; neither is used by any existing record."""

    NONE_BARE_OILED = "None (bare/oiled)"
    ELECTROLYTIC_ZINC = "Electrolytic zinc, ISO 4042"
    ZINC_NICKEL = "Zinc-nickel, ISO 4042"
    ZINC_FLAKE_GEOMET = "Zinc flake, non-electrolytic (Geomet 321/500)"
    ZINC_FLAKE = "Zinc flake, non-electrolytic"
    ZINC_FLAKE_LEGACY = "Zinc flake, non-electrolytic (legacy name for Geomet family)"
    PHOSPHATE_OIL = "Zinc or manganese phosphate + oil"
    BLACK_OXIDE_OIL = "Black oxide (gun bluing) + oil"
    MECHANICAL_ZINC = "Mechanically deposited zinc (peen plating)"
    SHERARDIZED = "Sherardizing (zinc diffusion), ISO 17668"
    OTHER = "Other"
    UNSPECIFIED = ""


class LubricationType(str, Enum):
    """Lubricant/friction-condition product type (Faz 2.4.2B). Retypes
    ``LubricationRecord.lubricant_type`` (Faz 2.4.0, previously
    free-text ``str``). Members reproduce, verbatim, the exact 8
    descriptive strings already stored in
    ``data/lubrication_library.json``; no value here was invented.
    ``OTHER`` and ``UNSPECIFIED`` (value ``""``, used as this field's
    default) are provided for forward/backward compatibility only,
    matching the pre-existing field's ``str = ""`` default; neither is
    used by any existing record."""

    NO_LUBRICANT = "No lubricant (as-coated/as-plated surface)"
    MINERAL_SYNTHETIC_OIL = "General mineral/synthetic engine oil film"
    MOLYBDENUM_DISULFIDE = "Molybdenum disulfide paste/dry-film"
    WAX_BASED = "Wax-based assembly lubricant"
    PTFE_DRY_FILM = "PTFE (Teflon) dry-film lubricant"
    GRAPHITE_PASTE = "Graphite-based paste"
    COPPER_NICKEL_ALUMINIUM_PASTE = "Copper/nickel/aluminium anti-seize style paste"
    ANTI_SEIZE_METAL_FILLED = "Anti-seize compound (metal-filled)"

    # -- Faz 2.6.0 additions ------------------------------------------
    # Added only to model the two generic lubrication states given by
    # Tablo 9.4 (Makine Elemanlari, Sekil 9.23 kaynagi) that do not
    # already have a matching member above: unspecified "oiled" ("Yagli")
    # and MoS2-with-oil ("MoS2 ile Yagli"), each distinct from the more
    # specific pre-existing members (``MINERAL_SYNTHETIC_OIL`` names a
    # concrete oil type; ``MOLYBDENUM_DISULFIDE`` names a dry MoS2
    # paste/film, not an oil-carried MoS2 film). "Kuru" ("Dry") reuses
    # the pre-existing ``NO_LUBRICANT`` member -- no new member added
    # for it.
    OILED_GENERIC = "Generic oil film (unspecified oil type)"
    MOS2_WITH_OIL = "Molybdenum disulfide with oil film"

    OTHER = "Other"
    UNSPECIFIED = ""


class FrictionModelType(str, Enum):
    """Faz 2.6.0: declares whether a ``LubricationRecord``'s friction
    value(s) represent a single combined coefficient (thread + bearing
    friction not separated by the source) or independently sourced
    ``mu_thread`` / ``mu_bearing`` values.

    Every record populated in Faz 2.6.0 (the Tablo 9.4-derived
    surface/lubrication-state records) uses
    ``COMBINED_OR_UNSPECIFIED``: the source table gives one overall
    coefficient per surface/state, with no thread/bearing split.
    ``SPLIT_THREAD_BEARING`` is reserved for Faz 2.6.2 records once an
    approved source for independent mu_thread/mu_bearing values per
    lubricant is confirmed -- see ADR-0009.
    """

    COMBINED_OR_UNSPECIFIED = "combined_or_unspecified"
    SPLIT_THREAD_BEARING = "split_thread_bearing"
    UNSPECIFIED = ""


class HeadType(str, Enum):
    """Bolt head form (Faz 2.4.2B). Retypes ``BoltRecord.head_type``
    (Faz 2.4.0, previously free-text ``str``). All 176 real records in
    ``data/bolt_library.json`` use exactly one of ``Hex``, ``Socket``,
    ``Flange`` or ``Headless`` (verified against the live data file,
    no record uses an empty/unset value); ``OTHER`` and
    ``UNSPECIFIED`` (value ``""``, used as this field's default) are
    provided for forward/backward compatibility only, matching the
    pre-existing field's ``str = ""`` default."""

    HEX = "Hex"
    SOCKET = "Socket"
    FLANGE = "Flange"
    HEADLESS = "Headless"
    OTHER = "Other"
    UNSPECIFIED = ""


class DriveType(str, Enum):
    """Bolt driving-feature type (Faz 2.4.2B). Retypes
    ``BoltRecord.drive_type`` (Faz 2.4.0, previously free-text
    ``str``). Of the 176 real records in ``data/bolt_library.json``,
    114 use ``"Hex (external)"``, 56 use ``"Hex socket (internal)"``
    and 6 use ``""`` (verified against the live data file) -- all
    three are covered; ``UNSPECIFIED`` (value ``""``) is the default,
    matching the pre-existing field's ``str = ""`` default exactly."""

    HEX_EXTERNAL = "Hex (external)"
    HEX_SOCKET_INTERNAL = "Hex socket (internal)"
    UNSPECIFIED = ""


class LockingType(str, Enum):
    """Nut prevailing-torque/locking mechanism (Faz 2.4.2B). Types the
    new ``NutRecord.locking_type`` field added by this phase (see
    inventory §2). Of the 211 real records in ``data/nut_library.json``,
    140 use the literal string ``"None"`` (not JSON ``null`` -- see
    inventory note), 54 use ``"Nylon insert"`` and 17 use
    ``"All-metal (deformed thread)"`` (verified against the live data
    file); all three are covered here."""

    NONE = "None"
    NYLON_INSERT = "Nylon insert"
    ALL_METAL_DEFORMED = "All-metal (deformed thread)"


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

    # -- Faz 2.4.2B common metadata block ----------------------------
    # All optional/defaulted -- additive only, per the phase brief.
    # ``name`` / ``standard`` / ``description`` / ``aliases`` are new,
    # independent fields; they intentionally do not replace or rename
    # any pre-existing analogue (e.g. per-domain ``designation``,
    # ``source_standard`` above). Where a domain already exposes an
    # equivalent free-text field, that field is left untouched.
    name: str = ""
    standard: str = ""
    description: str = ""
    aliases: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    #: Version of this *record's own shape/content*, distinct from the
    #: pre-existing ``version`` field above (which tracks the dataset
    #: release the record ships in -- see Faz 2.4.1 note). Defaults to
    #: "1.0" for every record that predates this field.
    record_version: str = "1.0"
    status: Status = Status.DRAFT
    unit_system: UnitSystem = UnitSystem.METRIC
    country: str = ""
    manufacturer: str = ""
    tags: List[str] = Field(default_factory=list)

    # -- Faz 2.4.2B JSON serialization convenience methods -----------
    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe ``dict`` view of this record (enums,
        datetimes etc. converted to their JSON representation, same as
        ``model_dump(mode="json")``)."""
        return self.model_dump(mode="json")

    def serialize(self) -> str:
        """Return this record serialized as a JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_dict(cls: Type[_RecordT], data: Dict[str, Any]) -> _RecordT:
        """Validate and construct a record from a plain ``dict``.
        Equivalent to ``model_validate`` but named for symmetry with
        ``to_dict``/``serialize``/``deserialize``."""
        return cls.model_validate(data)

    @classmethod
    def deserialize(cls: Type[_RecordT], data: str) -> _RecordT:
        """Validate and construct a record from a JSON string.
        Equivalent to ``model_validate_json``."""
        return cls.model_validate_json(data)


#: Recognised bolt/nut family vocabulary (Faz 2.4.1B, section 2/3 of
#: the phase brief). Advisory only -- not enforced at the Pydantic
#: layer (``bolt_family``/``nut_family`` stay free-text ``str`` so
#: pre-Faz-2.4.1B records with an empty family keep validating
#: unchanged); see ``validator.find_unknown_bolt_family`` /
#: ``find_unknown_nut_family`` for the opt-in data-quality check.
KNOWN_BOLT_FAMILIES = (
    "Hexagon head bolt",
    "Hexagon head screw",
    "Socket head cap screw",
    "Flange bolt",
    "Reduced shank bolt",
    "Structural bolt",
    "Stud bolt",
    "Set screw",
    "Shoulder bolt",
)
KNOWN_NUT_FAMILIES = (
    "Hexagon nut",
    "High nut",
    "Thin nut",
    "Flange nut",
    "Prevailing torque nut",
    "All-metal lock nut",
    "Nylon insert lock nut",
    "Structural nut",
    "Weld nut",
    "Square nut",
    "Cap nut",
)


class BoltRecord(LibraryRecordBase):
    """Bolt / screw / stud master record (see ``bolt_library.py``).

    Faz 2.4.1B additions (all optional, additive -- every Faz 2.4.0/
    2.4.1/2.4.1A bolt record that predates these fields keeps
    validating unchanged, since ``BoltRecord`` keeps
    ``LibraryRecordBase``'s ``extra="allow"``): structured
    counterparts of family/standard/thread/geometry/strength/
    provenance data requested by the Faz 2.4.1B brief. Pre-existing
    free-text fields (``designation``, ``thread``, ``property_class``,
    ``material``, ``head_type``) and the Faz 2.4.1 population fields
    (``diameter_mm``, ``head_across_flats_mm``, ...) are kept as-is,
    unrenamed -- these are new, separate fields, not replacements.
    """

    designation: str = ""
    thread: str = ""
    property_class: str = ""
    material: str = ""
    length_mm: float | None = None
    head_type: HeadType = HeadType.UNSPECIFIED

    # -- Faz 2.4.1B additions ---------------------------------------
    bolt_family: str = ""
    standard_organization: StandardType = StandardType.UNSPECIFIED
    nominal_diameter_mm: float | None = None
    pitch_mm: float | None = None
    coarse_or_fine: str = ""
    thread_tolerance_class: str = ""
    nominal_length_mm: float | None = None
    threaded_length_mm: float | None = None
    drive_type: DriveType = DriveType.UNSPECIFIED
    wrench_size_mm: float | None = None
    under_head_bearing_diameter_mm: float | None = None
    reduced_shank_diameter_mm: float | None = None
    heat_treatment: str = ""
    coating_compatibility: List[str] = Field(default_factory=list)
    lubrication_state: str = ""
    minimum_tensile_strength_mpa: float | None = None
    proof_strength_mpa: float | None = None
    yield_strength_mpa: float | None = None
    elongation_percent: float | None = None
    hardness_range: str = ""
    operating_temperature_min_c: float | None = None
    operating_temperature_max_c: float | None = None
    dimensional_tolerance_reference: str = ""
    verification_status: str = "unverified"
    record_status: str = "draft"

    # -- Faz 2.4.2B additions ----------------------------------------
    # Closes the 17-field bolt gap identified by the Faz 2.4.2A
    # inventory (docs/phase_2_4_2_schema_inventory.md §1). All 176
    # real records set every one of these fields; they are still
    # declared optional here (all-``None``/empty defaults) purely for
    # additive backward compatibility with any record or test that
    # predates this phase and never set them -- see module docstring.
    # Every field is a physical dimension or mass: ``gt=0`` rejects
    # negative/zero values (physically invalid for a fastener
    # geometry) while ``None`` (unset) stays fully permitted.
    thread_direction: ThreadDirection = ThreadDirection.RIGHT
    diameter_mm: float | None = Field(default=None, gt=0)
    pitch_coarse_mm: float | None = Field(default=None, gt=0)
    pitch_fine_mm: float | None = Field(default=None, gt=0)
    stress_area_mm2: float | None = Field(default=None, gt=0)
    minor_diameter_mm: float | None = Field(default=None, gt=0)
    pitch_diameter_mm: float | None = Field(default=None, gt=0)
    head_across_flats_mm: float | None = Field(default=None, gt=0)
    head_across_corners_mm: float | None = Field(default=None, gt=0)
    head_height_mm: float | None = Field(default=None, gt=0)
    socket_size_mm: float | None = Field(default=None, gt=0)
    washer_face_diameter_mm: float | None = Field(default=None, gt=0)
    bearing_diameter_mm: float | None = Field(default=None, gt=0)
    recommended_hole_mm: float | None = Field(default=None, gt=0)
    clearance_hole_medium_mm: float | None = Field(default=None, gt=0)
    tap_drill_mm: float | None = Field(default=None, gt=0)
    thread_engagement_mm: float | None = Field(default=None, gt=0)
    weight_kg_per_100: float | None = Field(default=None, gt=0)


class NutRecord(LibraryRecordBase):
    """Nut master record (see ``nut_library.py``).

    Faz 2.4.1B additions (all optional, additive -- see ``BoltRecord``
    docstring above for the same additive convention applied here).
    """

    designation: str = ""
    thread: str = ""
    property_class: str = ""
    height_mm: float | None = None

    # -- Faz 2.4.1B additions ---------------------------------------
    nut_family: str = ""
    standard_organization: StandardType = StandardType.UNSPECIFIED
    nominal_diameter_mm: float | None = None
    pitch_mm: float | None = None
    coarse_or_fine: str = ""
    thread_tolerance_class: str = ""
    width_across_corners_mm: float | None = None
    flange_diameter_mm: float | None = None
    bearing_surface_diameter_mm: float | None = None
    proof_load_n: float | None = None
    hardness_range: str = ""
    heat_treatment: str = ""
    coating_compatibility: List[str] = Field(default_factory=list)
    lubrication_state: str = ""
    prevailing_torque_category: str = ""
    locking_principle: str = ""
    reusable: Optional[bool] = None
    operating_temperature_min_c: float | None = None
    operating_temperature_max_c: float | None = None
    mating_bolt_requirements: str = ""
    dimensional_tolerance_reference: str = ""
    verification_status: str = "unverified"
    record_status: str = "draft"

    # -- Faz 2.4.2B additions ----------------------------------------
    # Closes the 5-field nut gap identified by the Faz 2.4.2A
    # inventory (docs/phase_2_4_2_schema_inventory.md §2). All 211
    # real records set every one of these fields; declared optional
    # here for the same additive-backward-compatibility reason as
    # ``BoltRecord`` above. ``locking_type`` uses ``LockingType``
    # rather than free ``str`` -- see that enum's docstring for the
    # ``"None"``-the-string vs. ``None``-the-null distinction flagged
    # by the inventory.
    thread_direction: ThreadDirection = ThreadDirection.RIGHT
    bearing_face: str = ""
    flange: Optional[bool] = None
    width_across_flats_mm: float | None = Field(default=None, gt=0)
    locking_type: Optional[LockingType] = None
    strength_compatibility: List[str] = Field(default_factory=list)


class WasherRecord(LibraryRecordBase):
    """Washer master record (see ``washer_library.py``).

    Faz 2.4.1C additions (all optional, additive -- every Faz 2.4.1
    plain-washer record that predates these fields keeps validating
    unchanged, since ``WasherRecord`` keeps ``LibraryRecordBase``'s
    ``extra="allow"``): structured washer-type/standard-body/material/
    finish/compatibility/service-limit fields requested by the
    Faz 2.4.1C brief. Pre-existing fields (``designation``,
    ``inner_diameter_mm``, ``outer_diameter_mm``, ``thickness_mm``,
    ``hardness``) are kept as-is, unrenamed.

    Faz 2.4.2B: ``standard_organization`` retyped ``str`` ->
    ``StandardType`` (all 223 real records use ``"ISO"`` or ``"DIN"``,
    both covered -- see ``StandardType`` docstring). Per the Faz
    2.4.2A inventory, washer library was already otherwise fully
    modelled; no other field changed.
    """

    designation: str = ""
    inner_diameter_mm: float | None = None
    outer_diameter_mm: float | None = None
    thickness_mm: float | None = None
    hardness: str = ""

    # -- Faz 2.4.1C additions -----------------------------------------
    washer_type: str = ""
    standard_organization: StandardType = StandardType.UNSPECIFIED
    material: str = ""
    surface_finish: str = ""
    coating: str = ""
    compatible_bolt_sizes: List[str] = Field(default_factory=list)
    strength_class: str = ""
    locking_principle: str = ""
    operating_temperature_min_c: float | None = None
    operating_temperature_max_c: float | None = None


#: Faz 2.4.1A thread-record schema version. Deliberately distinct
#: from ``LibraryRecordBase.version`` / ``LibraryMetadata.version``,
#: which track the *dataset* release (e.g. "2.4.1"). This constant
#: tracks the *shape* of ``ThreadRecord`` itself and only changes when
#: the thread schema changes, independent of how many times the
#: dataset content is re-released under the same shape.
THREAD_SCHEMA_VERSION = "1.0"

#: Recognised ``pitch_type`` values (coarse/fine/extra-fine only).
#: Records with no coarse/fine analogue (e.g. BSP, NPT, Trapezoidal)
#: leave ``pitch_type`` unset (``None``) rather than guessing.
ThreadPitchType = Literal["coarse", "fine", "extra_fine"]

#: Recognised ``thread_series`` values. ``ISO_METRIC`` is the only
#: series in Faz 2.4.1A's own validation/search scope; the others
#: label the pre-existing non-metric reference records so they can be
#: unambiguously excluded from that scope (see ``validator.py``
#: ``is_iso_metric_thread_record`` / ``find_non_iso_metric_series``).
#:
#: Faz 2.4.2B: derived directly from the ``ThreadSeries`` enum rather
#: than kept as its own separate literal tuple, so the vocabulary is
#: declared exactly once. Values and order are unchanged from
#: Faz 2.4.1A -- ``ThreadRecord.thread_series`` itself stays free-text
#: ``str`` (not retyped to ``ThreadSeries``): the field must keep
#: accepting whatever thread-series string an existing or future
#: record carries, including values outside this known set, per the
#: Faz 2.4.1A design (unrecognised values are flagged only as an
#: opt-in data-quality warning by
#: ``validator.find_non_iso_metric_series`` / ``find_unknown_...``
#: style checks -- never rejected at the schema layer).
KNOWN_THREAD_SERIES = tuple(member.value for member in ThreadSeries)


class ThreadRecord(LibraryRecordBase):
    """Thread geometry record (see ``thread_library.py``).

    ``designation`` is required and validated elsewhere against a
    metric thread pattern by
    ``backend.library.validator.is_valid_thread_designation`` --
    unchanged by this schema, which only checks presence/type here.

    Faz 2.4.1A additions (all optional, additive -- every Faz 2.4.0/
    2.4.1 record that predates these fields keeps validating
    unchanged):

    - ``pitch_type`` / ``thread_series``: structured counterparts of
      the pre-existing free-text ``series`` field (kept as-is for
      backward compatibility; not renamed or removed).
    - ``major_diameter_mm``: the ISO 724 *basic* (theoretical, no
      tolerance) major diameter. For the basic profile this equals
      ``nominal_diameter_mm`` for both external and internal threads
      -- it is carried as its own field for API/schema completeness,
      not because its value differs from ``nominal_diameter_mm``.
    - ``minor_diameter_external_mm`` / ``minor_diameter_internal_mm``:
      split out of the pre-existing single ``minor_diameter_mm``
      field (also kept as-is), which historically held only the
      internal (nut, sharp-root, D1) value. See
      ``backend.library.thread_geometry`` for the ISO 724 formulas.
    - ``source_reference`` / ``source_revision``: structured
      counterparts of the pre-existing free-text ``source`` /
      ``revision`` fields (kept as-is).
    - ``confidence_level``: structured counterpart of the pre-existing
      ``confidence`` field (kept as-is).
    - ``review_status``: Faz 2.4.1A review-workflow status, distinct
      from the pre-existing ``validation_status`` / ``approval_status``
      pair (kept as-is).
    - ``schema_version``: see ``THREAD_SCHEMA_VERSION`` above.

    ``model_config`` overrides ``LibraryRecordBase`` to
    ``extra="forbid"`` for this record type only (Pydantic v2 resolves
    ``model_config`` per-subclass, so the other nine domain records
    keep ``extra="allow"`` unchanged). This is a Faz 2.4.1A-scoped
    decision: unknown fields on a thread record must be rejected
    explicitly rather than silently accepted.

    Faz 2.4.2B: ``KNOWN_THREAD_SERIES`` (module level, above) is now
    derived from the new ``ThreadSeries`` enum instead of its own
    duplicated tuple literal -- values unchanged. ``thread_series``
    itself is intentionally left untyped (``str``, unchanged from
    Faz 2.4.1A): it must keep accepting any existing thread-series
    string, known or not, per the design note on that field above.
    """

    model_config = ConfigDict(extra="forbid")

    designation: str
    nominal_diameter_mm: float | None = None
    pitch_mm: float | None = None
    tolerance_class: str = ""
    stress_area_source: str = ""

    # -- Pre-existing (Faz 2.4.1) fields, made explicit for the
    # extra="forbid" override above. LibraryRecordBase's extra="allow"
    # let these pass through untyped before; forbidding extras on
    # ThreadRecord means every field the data actually carries must
    # now be declared here. Values, names and semantics unchanged.
    series: str = ""
    pitch_diameter_mm: float | None = None
    minor_diameter_mm: float | None = None
    stress_area_mm2: float | None = None

    # -- Faz 2.4.1A additions --------------------------------------
    pitch_type: Optional[ThreadPitchType] = None
    thread_series: str = ""
    major_diameter_mm: float | None = None
    minor_diameter_external_mm: float | None = None
    minor_diameter_internal_mm: float | None = None
    source_reference: str = ""
    source_revision: str = ""
    confidence_level: Optional[ConfidenceLevel] = None
    review_status: str = ""
    schema_version: str = ""


class MaterialRecord(LibraryRecordBase):
    """Material property-set record (see ``material_library.py``).

    Faz 2.4.2B: closes the 5-field gap identified by the Faz 2.4.2A
    inventory (docs/phase_2_4_2_schema_inventory.md §3).

    - ``material`` retyped ``str`` -> ``MaterialType``: all 8 real
      records use exactly one of the 8 named values (verified against
      the live data file); still required, unchanged from Faz 2.4.0.
    - ``density_kg_mm3`` / ``poisson_ratio`` / ``thermal_expansion_per_k``
      are new, genuinely unmodelled engineering fields every real
      record sets; declared optional here (default ``None``) purely
      for additive backward compatibility with any record/test that
      predates this phase, per the module-level policy above.
    - ``ultimate_mpa`` / ``yield_mpa``: the inventory flags these as
      **likely-duplicate legacy fields** -- in all 8 real records
      ``ultimate_mpa == rm_mpa`` and ``yield_mpa == rp02_mpa`` exactly
      (e.g. ``MAT-STEEL``: ``rm_mpa=500, ultimate_mpa=500``). The
      inventory's own recommendation was a *data-cleanup* decision
      (removing the legacy keys from ``data/material_library.json``),
      not a new-field modelling decision -- out of scope for a
      schema-only phase and not performed here. Both are declared as
      optional, controlled pass-through fields so records that carry
      them keep validating and round-tripping losslessly; ``rm_mpa``
      / ``rp02_mpa`` remain the single source of truth for new code.
    """

    material: MaterialType
    grade: str = ""
    rp02_mpa: float | None = Field(default=None, gt=0)
    rm_mpa: float | None = Field(default=None, gt=0)
    elastic_modulus_mpa: float | None = Field(default=None, gt=0)

    # -- Faz 2.4.2B additions ----------------------------------------
    density_kg_mm3: float | None = Field(default=None, gt=0)
    poisson_ratio: float | None = Field(default=None, gt=0, lt=0.5)
    thermal_expansion_per_k: float | None = Field(default=None, gt=0)
    #: Legacy duplicate of ``rm_mpa`` -- see class docstring.
    ultimate_mpa: float | None = Field(default=None, gt=0)
    #: Legacy duplicate of ``rp02_mpa`` -- see class docstring.
    yield_mpa: float | None = Field(default=None, gt=0)


class CoatingRecord(LibraryRecordBase):
    """Surface/coating specification record (see ``coating_library.py``).

    Faz 2.4.2B: closes the 3-field gap identified by the Faz 2.4.2A
    inventory (docs/phase_2_4_2_schema_inventory.md §4).

    - ``coating_type`` retyped ``str`` -> ``CoatingType``: all 10 real
      records use one of the 10 named values (verified against the
      live data file), each reproduced verbatim -- see ``CoatingType``
      docstring. A JSON value that does not match any known member
      (an unrecognised/legacy string) is rejected the same way any
      other invalid enum input is -- there is no silent fallback --
      but ``CoatingType.OTHER`` / ``CoatingType.UNSPECIFIED`` remain
      available as an explicit, intentional escape hatch for future
      records that genuinely don't fit an existing category.
    - ``corrosion_class`` / ``remark`` are new fields every real
      record sets (``remark`` optional per the inventory's own
      recommendation -- free text).
    - ``temperature_range_c`` is kept as ``str`` (not split into
      min/max numeric fields): the inventory flags this explicitly as
      a ``"<min>..<max>"`` range *expression*, not a single number --
      splitting it is a data-format decision explicitly deferred by
      the inventory (§4), out of scope for schema completion.
    """

    designation: str = ""
    coating_type: CoatingType = CoatingType.UNSPECIFIED
    thickness_um: float | None = Field(default=None, gt=0)
    friction_coefficient_range: str = ""

    # -- Faz 2.4.2B additions ----------------------------------------
    corrosion_class: str = ""
    remark: Optional[str] = None
    #: ``"<min>..<max>"`` range expression, e.g. ``"-40..300"`` --
    #: intentionally a string, not two numeric fields; see class
    #: docstring.
    temperature_range_c: str = ""


class LubricationRecord(LibraryRecordBase):
    """Lubricant/friction-condition record (see ``lubrication_library.py``).

    Naming note (Faz 2.6 rename, 2026-07-23): at the product/
    architecture level this record type is now the **Lubrication
    subsection** of the **Friction Condition** module -- the module
    that owns lubrication, surface condition, coatings, thread/bearing
    friction and related engineering warnings as a whole (see
    ADR-0009 and docs/09_LIBRARY_SPECIFICATION.md). The class name,
    file name (``lubrication_library.py``) and every existing field/
    record id are unchanged for backward compatibility -- only
    documentation, backlog, ADR and UI-level naming moved to
    "Friction Condition"; no code identifier was renamed.

    Faz 2.4.2B: closes the 1-field gap identified by the Faz 2.4.2A
    inventory (docs/phase_2_4_2_schema_inventory.md §5).

    - ``lubricant_type`` retyped ``str`` -> ``LubricationType``: all 8
      real records use one of the 8 named values (verified against
      the live data file), each reproduced verbatim -- see
      ``LubricationType`` docstring.
    - ``oem_compatibility`` is the new field every real record sets
      (a list of OEM names, e.g. ``["FIAT", "VW", "Ford", "GM",
      "Toyota"]``); declared optional (default empty list) for the
      same additive-backward-compatibility reason as elsewhere.

    Faz 2.6.1 concept map (ADR-0009; see also
    docs/09_LIBRARY_SPECIFICATION.md §10.2 "Module responsibilities").
    Eight concepts the Friction Condition module distinguishes,
    deliberately kept as separate field groups on this one record
    type rather than merged -- see class docstring "Schema decision"
    note below for why no nested/split model was introduced yet:

    1. **Surface condition** -- ``surface_condition`` (free text; the
       substrate/surface-treatment state a friction value was measured
       against, e.g. "Fosfatlanmis"). Distinct from *coating* below:
       a coating is an applied layer with its own spec; surface
       condition is the resulting friction-relevant state.
    2. **Coating** -- not modelled on this record. A coating
       *product* specification lives in ``CoatingRecord``
       (``coating_library.py``); Faz 2.6.0/2.6.1 do not cross-
       reference it (ADR-0009 open question #2). A future Friction
       Condition record may add a ``coating_id`` FK-style field.
    3. **Lubricant** -- ``lubricant_type`` (+ ``designation``,
       ``application``, ``oem_compatibility``): the applied lubricant
       product itself (oil, paste, dry-film, or "no lubricant").
    4. **Overall/combined friction coefficient** --
       ``overall_friction_coefficient_min/max`` +
       ``friction_model``: a single coefficient that does not
       separate thread and bearing friction. Every Faz 2.6.0 record
       (Tablo 9.4) uses only this group
       (``friction_model = combined_or_unspecified``).
    5. **Thread friction coefficient** -- ``mu_thread_min/max``.
       Schema-only in Faz 2.6.0/2.6.1: unset on every record, no
       approved source yet (ADR-0009 open need #1).
    6. **Bearing friction coefficient** -- ``mu_bearing_min/max``.
       Same status as (5); see also
       ``find_friction_one_sided_thread_bearing`` (``validator.py``),
       which requires (5) and (6) to be populated together, never one
       without the other.
    7. **Nut factor** -- ``k_factor_min/max``. Schema-only, same
       status as (5)/(6). Distinct from thread/bearing friction: `K`
       is the lumped empirical torque-preload coefficient (Section 4
       of docs/05_ENGINEERING_FORMULA_SPECIFICATION.md), not a
       friction angle component.
    8. **Scatter** -- ``scatter_percent``. Schema-only, same status.
       Distinct from the min/max *range* fields above: scatter is a
       statistical dispersion measure (e.g. process capability),
       not a physical bound.

    Every group above additionally uses the shared traceability
    fields (`source_reference`, `source_type`, `source_page_or_table`,
    `verification_status`, `applicability`, `engineering_notes`) and
    is subject to the Faz 2.6.1 validator checks in
    ``backend.library.validator`` (min<=max, no negative values, no
    one-sided min/max, no one-sided thread/bearing, no coefficient
    without a source, no ``restricted_legacy`` record without a
    ``regulatory_warning``).

    Schema decision (Faz 2.6.1, ADR-0009 §2): a separate
    ``FrictionCoefficientSet``/nested-model is NOT introduced by this
    phase. ADR-0009's trigger condition for that model -- a record
    whose different coefficients (e.g. mu_thread vs. mu_bearing) come
    from *different* sources, needing per-value rather than per-record
    traceability -- is not yet met: every populated Faz 2.6.0/2.6.1
    record uses one shared source for all its values. The flat fields
    above stay the storage shape until that trigger condition is
    actually met (Faz 2.6.2 candidate), at which point ADR-0009 §2
    requires the nested model to be added additively, without breaking
    these flat fields.
    """

    designation: str = ""
    lubricant_type: LubricationType = LubricationType.UNSPECIFIED
    friction_coefficient_min: float | None = Field(default=None, ge=0, lt=1)
    friction_coefficient_max: float | None = Field(default=None, ge=0, lt=1)
    application: str = ""

    # -- Faz 2.4.2B additions ----------------------------------------
    oem_compatibility: List[str] = Field(default_factory=list)

    # -- Faz 2.6.0/2.6.1 additions (architecture/spec phases) ---------
    # All fields below are optional with safe defaults: additive only,
    # per the same backward-compatibility rule used by every earlier
    # phase (Faz 2.4.1A/2.4.2B). Every one of the 8 pre-existing
    # records keeps validating unchanged. See ADR-0009 and the
    # concept map above for the full rationale/grouping.

    # Concept 4: overall/combined friction coefficient. Intentionally
    # kept side by side with the pre-existing Faz 2.4.0
    # ``friction_coefficient_min/max`` pair rather than merged: that
    # pair is the Faz 2.4.0 "typical range" concept (reference_only,
    # ISO 16047 methodology note, no declared source table/page); this
    # one is the Faz 2.6.0 concept of a coefficient traceable to one
    # specific, cited source (e.g. a named textbook table). Faz 2.6.0/
    # 2.6.1 do not backfill or reconcile the two on the 8 pre-existing
    # records -- that reconciliation, if wanted, is a Faz 2.6.2 data-
    # population decision, not an architecture one.
    overall_friction_coefficient_min: float | None = Field(default=None, ge=0, lt=1)
    overall_friction_coefficient_max: float | None = Field(default=None, ge=0, lt=1)
    friction_model: FrictionModelType = FrictionModelType.UNSPECIFIED

    # Concepts 5-7: independent thread/bearing friction and nut-factor
    # fields. Schema only through Faz 2.6.1 -- deliberately left unset
    # (None) on every record populated so far; no source yet approved
    # for independent mu_thread/mu_bearing/K per lubricant (ADR-0009
    # open data need #1). Populating these without a cited source
    # would violate docs/12_CLAUDE_CONTEXT.md SS4 ("do not invent
    # coefficients"); see ``validator.find_friction_coefficient_missing_source``.
    mu_thread_min: float | None = Field(default=None, ge=0, lt=1)
    mu_thread_max: float | None = Field(default=None, ge=0, lt=1)
    mu_bearing_min: float | None = Field(default=None, ge=0, lt=1)
    mu_bearing_max: float | None = Field(default=None, ge=0, lt=1)
    k_factor_min: float | None = Field(default=None, ge=0)
    k_factor_max: float | None = Field(default=None, ge=0)
    # Concept 8: scatter.
    scatter_percent: float | None = Field(default=None, ge=0)
    max_temperature_c: float | None = None
    corrosion_resistance: str = ""
    reusability: str = ""
    recommended_standards: List[str] = Field(default_factory=list)

    # Per-record source traceability, additive counterpart to the
    # generic ``source`` / ``source_standard`` / ``notes`` fields
    # already on ``LibraryRecordBase``. Kept as plain ``str`` (not
    # enums) in Faz 2.6.0/2.6.1: the only values populated so far are
    # "textbook" / "textbook_reference" / "reference_only" (see
    # ``LUBE-SURF-*`` records below); a closed vocabulary is deferred
    # until Faz 2.6.2 sees the full range of source types in use
    # (standard, supplier datasheet, internal test, ...).
    source_status: str = ""
    source_reference: str = ""
    source_type: str = ""
    source_page_or_table: str = ""
    verification_status: str = ""
    applicability: str = ""
    engineering_notes: str = ""

    # Faz 2.6.0 restricted-legacy support (e.g. cadmium plating): pairs
    # with ``LibraryRecordBase.status = Status.RESTRICTED_LEGACY``.
    # Free text, not a legal/regulatory determination -- see field
    # docstring on ``Status.RESTRICTED_LEGACY``. Faz 2.6.1 adds an
    # opt-in check (``validator.find_restricted_legacy_missing_warning``)
    # requiring this field to be non-empty whenever that status is set.
    regulatory_warning: str = ""

    # Concept 1: surface condition. Free-text substrate/surface-
    # treatment description for records where the friction value is a
    # surface-condition property rather than an applied lubricant
    # product (e.g. "Fosfatlanmis", "Galvanize" from Tablo 9.4).
    # Deliberately not modelled as a new enum or cross-reference to
    # ``CoatingType``/``coating_library.py`` in this phase -- see
    # ADR-0009 open question #2 (concept 2, coating, above).
    surface_condition: str = ""


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


class JointHardwareRecord(LibraryRecordBase):
    """Joint hardware master record (see ``joint_hardware_library.py``).

    Faz 2.4.1C shell schema for non-washer joint hardware: spacers,
    sleeves, bushings, dowel pins, thread inserts and retaining
    rings. Introduced with an empty dataset -- see the Faz 2.4.1C
    delivery report for why no record has been populated yet (no
    verified, fully-sourced dimension table was gathered for any of
    these families in this phase). All fields optional/additive,
    ``extra="allow"`` inherited from ``LibraryRecordBase``.

    Faz 2.4.2B: ``standard_organization`` retyped ``str`` ->
    ``StandardType`` for consistency with ``BoltRecord`` / ``NutRecord``
    / ``WasherRecord``. Zero-risk: this shell still has no populated
    records (see docstring above), so there is no existing data to
    validate against.
    """

    designation: str = ""
    hardware_type: str = ""
    standard_organization: StandardType = StandardType.UNSPECIFIED
    inner_diameter_mm: float | None = None
    outer_diameter_mm: float | None = None
    length_mm: float | None = None
    material: str = ""
    surface_finish: str = ""
    coating: str = ""
    compatible_bolt_sizes: List[str] = Field(default_factory=list)
    load_rating_n: float | None = None
    operating_temperature_min_c: float | None = None
    operating_temperature_max_c: float | None = None


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
    "joint hardware library": JointHardwareRecord,
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
    "Status",
    "UnitSystem",
    "ThreadDirection",
    "ThreadSeries",
    "StandardType",
    "MaterialType",
    "CoatingType",
    "LubricationType",
    "FrictionModelType",
    "HeadType",
    "DriveType",
    "LockingType",
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
