# Faz 2.4.1B – Bolt & Nut Engineering Database

Status: delivered. Extends the Faz 2.4.1 Bolt/Nut Library population
(`backend/library/data/bolt_library.json` / `nut_library.json`) with
new bolt/nut families, new standards, a structured field set, a
Faz 2.4.1B-specific validator suite, an extended search API, and a
structured bolt↔nut compatibility service. **No calculation algorithm
was touched** — `backend.engineering_core`, `backend.vdi2230_core`
and `backend.calculation_engine` are untouched. No existing Faz 2.4.0
/ 2.4.1 / 2.4.1A architecture (registry, loader, validator, search,
facade, source_manager, compatibility, migration) was replaced; this
phase is purely additive on top of it.

All record counts and distributions below were produced by
`tools/generate_faz2_4_1b_bolt_nut_records.py`'s own report (see
`main()`'s print output) and cross-checked with the reproduction
snippet at the end of §1 — not estimated by hand.

## 1. Mimari entegrasyon

No new parallel infrastructure was introduced. Faz 2.4.1B integrates
directly into the existing `backend/library/` package:

- **Data files**: appended in place to the existing
  `backend/library/data/bolt_library.json` /
  `.../nut_library.json` — the pre-existing `POPULATION_SOURCES`
  single-file-per-domain loader (`population.py`) already expects
  exactly this shape, so no new `data/bolts/` / `data/nuts/`
  directory split was introduced (the phase brief allowed this when
  the existing loader expects a different format).
- **Schema**: `BoltRecord` / `NutRecord` in `models.py` gained ~25
  new optional, additive fields each (`extra="allow"` preserved, so
  every pre-Faz-2.4.1B record keeps validating unchanged).
- **Validation**: a new, opt-in section in `validator.py`
  (`validate_bolt_library` / `validate_nut_library` + 16 constituent
  `find_*` checks), mirroring the Faz 2.4.1A thread-validation
  pattern. Wired into `population.run_all_integrity_checks()` via two
  new keys (`bolt_library_faz2_4_1b`, `nut_library_faz2_4_1b`).
- **Search**: `population.search_bolts` / `population.search_nuts`
  added alongside the pre-existing `find_bolt` / `find_nut` (which
  are unchanged — no backward-compatibility break). Exposed on the
  `LibraryRegistry` facade as `search_bolts` / `search_nuts`.
- **Compatibility**: a new module, `compatibility_engine.py`, sits
  next to (does not modify) the pre-existing, deliberately
  metadata-only `compatibility.py` shell.
- **Data generation**: `tools/generate_faz2_4_1b_bolt_nut_records.py`,
  a one-off, explicitly-invoked script (not imported by the runtime
  package), following the same "controlled generation script"
  convention the Faz 2.4.1 population data itself used.

## 2. Değişen veri modelleri

`backend/library/models.py`:

- `BoltRecord` — added `bolt_family`, `standard_organization`,
  `nominal_diameter_mm`, `pitch_mm`, `coarse_or_fine`,
  `thread_tolerance_class`, `nominal_length_mm`, `threaded_length_mm`,
  `drive_type`, `wrench_size_mm`, `under_head_bearing_diameter_mm`,
  `reduced_shank_diameter_mm`, `heat_treatment`,
  `coating_compatibility`, `lubrication_state`,
  `minimum_tensile_strength_mpa`, `proof_strength_mpa`,
  `yield_strength_mpa`, `elongation_percent`, `hardness_range`,
  `operating_temperature_min_c`, `operating_temperature_max_c`,
  `dimensional_tolerance_reference`, `verification_status`,
  `record_status`.
- `NutRecord` — added `nut_family`, `standard_organization`,
  `nominal_diameter_mm`, `pitch_mm`, `coarse_or_fine`,
  `thread_tolerance_class`, `width_across_corners_mm`,
  `flange_diameter_mm`, `bearing_surface_diameter_mm`,
  `proof_load_n`, `hardness_range`, `heat_treatment`,
  `coating_compatibility`, `lubrication_state`,
  `prevailing_torque_category`, `locking_principle`, `reusable`,
  `operating_temperature_min_c`, `operating_temperature_max_c`,
  `mating_bolt_requirements`, `dimensional_tolerance_reference`,
  `verification_status`, `record_status`.

Both keep `LibraryRecordBase`'s `extra="allow"` (unlike
`ThreadRecord`, which Faz 2.4.1A deliberately switched to
`extra="forbid"`) — the union of pre-existing free-text fields
(`diameter_mm`, `head_across_flats_mm`, `pitch_coarse_mm`, ...) across
11 bolt families and 11 nut families is too heterogeneous to safely
enumerate exhaustively in this phase without risking false rejections
on legitimate family-specific fields.

## 3. Kayıt sayıları (gerçek veriden, programatik)

Reproduce with:

```python
from backend.library import population
print(len(population.load_population_records("bolt library")))  # 176
print(len(population.load_population_records("nut library")))   # 211
```

**Bolt Library: 176 total** (54 pre-existing Faz 2.4.1 + 122 new)

| source_standard | count |
|---|---:|
| ISO 4017 | 33 |
| ISO 4762 | 27 |
| ISO 4014 | 17 |
| DIN 931 | 17 |
| DIN 933 | 17 |
| DIN 912 | 17 |
| ISO 4162 | 17 |
| EN 14399-3 | 7 |
| DIN 7968 | 6 |
| ISO 4026 | 6 |
| ISO 7379 | 6 |
| ISO 898-1 | 6 |
| **Total** | **176** |

| bolt_family | count |
|---|---:|
| Hexagon head screw | 44 |
| Socket head cap screw | 44 |
| Hexagon head bolt | 34 |
| Flange bolt | 17 |
| Structural bolt | 7 |
| Hexagon head screw (fine thread) | 6 |
| Reduced shank bolt | 6 |
| Set screw | 6 |
| Shoulder bolt | 6 |
| Stud bolt | 6 |
| **Total** | **176** |

**Nut Library: 211 total** (135 pre-existing Faz 2.4.1 + 76 new)

| source_standard | count |
|---|---:|
| ISO 4032 | 27 |
| ISO 4033 | 27 |
| ISO 8673 | 27 |
| ISO 7040 | 27 |
| ISO 10511 | 27 |
| ISO 4035 | 17 |
| ISO 4161 | 17 |
| ISO 7042 | 17 |
| EN 14399-4 | 7 |
| DIN 1587 | 6 |
| DIN 557 | 6 |
| DIN 929 | 6 |
| **Total** | **211** |

| nut_family | count |
|---|---:|
| Hexagon nut | 54 |
| High nut | 27 |
| Nylon insert lock nut | 27 |
| Prevailing torque nut | 27 |
| All-metal lock nut | 17 |
| Flange nut | 17 |
| Thin nut | 17 |
| Structural nut | 7 |
| Cap nut | 6 |
| Square nut | 6 |
| Weld nut | 6 |
| **Total** | **211** |

Both totals match the phase brief's stated report (176 bolts, 211
nuts) exactly — no discrepancy to reconcile.

## 4. Doğrulanmış/draft/unverified dağılımı

| | Bolt Library | Nut Library |
|---|---:|---:|
| `validation_status=validated` | 0 | 10 |
| `validation_status=reference_only` | 129 | 125 |
| `validation_status=provisional` | 47 | 76 |
| `verification_status=verified` | 0 | 10 |
| `verification_status=unverified` | 176 | 201 |
| `record_status=approved` | 0 | 10 |
| `record_status=draft` | 176 | 201 |

The 10 `validated`/`verified`/`approved` nut records are the
pre-existing ISO 4032 (hexagon nut) records at the M3–M24 sizes where
the original Faz 2.4.1 population work had directly verified the
standard table's `height_mm` value; every other bolt and nut record
(including all Faz 2.4.1B additions) is honestly marked
`reference_only`/`provisional` and `unverified`/`draft` — see §11.

## 5. Legacy kayıt backfill yaklaşımı

The 54 pre-existing bolt records (ISO 4017, ISO 4762) and 135
pre-existing nut records (ISO 4032/4033/8673/7040/10511) predate the
Faz 2.4.1B field set. Rather than leave them without the new
structured fields, `backfill_legacy_bolt_records()` /
`backfill_legacy_nut_records()` populate the new fields **in place**,
purely as a deterministic function of each record's own pre-existing
core fields (`diameter_mm`/`thread`, `property_class`,
`source_standard`, ...). Their `id`, and every pre-existing Faz 2.4.1
field, is left untouched — only the new fields are added and the
`checksum` is recomputed over the enlarged record. Re-running the
backfill on unchanged input recomputes the same values and the same
checksum every time (see §6).

## 6. Generator idempotency yaklaşımı

`tools/generate_faz2_4_1b_bolt_nut_records.py` is safe to re-run:

1. `_strip_previous_generation()` removes any record this script
   generated on a prior run (tagged `version == "2.4.1B"`) before
   appending a fresh set — this is what prevents duplication on a
   second run.
2. Every generated record is a pure function of the live Thread
   Library + the fixed per-standard/family tables in the script, so
   the freshly-generated set is byte-identical across runs.
3. Records with any other `version` value (pre-existing Faz 2.4.1
   records, or anything a person added by hand) are never touched by
   `_strip_previous_generation()` — they persist across re-runs
   untouched (verified by
   `test_generator_preserves_manually_added_foreign_records` and
   `test_generator_preserves_faz_2_4_1a_legacy_records`).

Verified idempotent by running the script twice against temporary
copies of the data files and diffing the output byte-for-byte (see
`test_generator_is_byte_for_byte_idempotent`) — the real repository
data files are never touched by the test suite.

## 7. Checksum yöntemi

Unchanged from the Faz 2.4.1 convention already used by
`population.find_checksum_mismatches()`: SHA-256 over
`json.dumps({k: v for k, v in record.items() if k != "checksum"},
sort_keys=True, ensure_ascii=False)`. Every one of the 176 bolt and
211 nut records' stored `checksum` was recomputed and verified to
match its own content (`test_every_bolt_record_checksum_matches_content`
/ `..._nut_...`).

## 8. Validator listesi (Faz 2.4.1B, `validator.py`)

`validate_bolt_library()` / `validate_nut_library()` each run:

| Check | Function |
|---|---|
| Duplicate record ID | `find_duplicate_ids` (pre-existing, reused) |
| Duplicate designation+standard+dimension | `find_duplicate_designation_standard_dimension` |
| Nominal diameter > 0 | `find_non_positive_nominal_diameter` |
| Thread pitch > 0 | `find_non_positive_pitch` |
| Pitch/designation consistency | `find_pitch_designation_mismatches` |
| Strength/property class format | `find_invalid_bolt_strength_class_format` / `find_invalid_nut_strength_class_format` |
| Tensile stress area > 0 | `find_non_positive_stress_area` (bolt only) |
| Head/nut geometry consistency | `find_bolt_head_geometry_inconsistencies` / `find_nut_width_geometry_inconsistencies` |
| Proof/yield/tensile ordering | `find_strength_ordering_violations` (bolt only) |
| Hardness range min ≤ max | `find_hardness_range_violations` |
| Temperature range min ≤ max | `find_temperature_range_violations` |
| Source required | `find_missing_source` |
| Verified ⇒ revision required | `find_verified_missing_revision` |
| Lock nut ⇒ locking principle required | `find_lock_nut_missing_locking_principle` (nut only) |
| Prevailing torque nut ⇒ reuse info required | `find_prevailing_torque_nut_missing_reuse_info` (nut only) |

Running both over the live 176+211 records currently returns **0
issues** (`population.validate_bolt_library_records() == []`,
`population.validate_nut_library_records() == []`).

## 9. Search API örnekleri

```python
from backend.library import population

population.search_bolts(
    nominal_diameter=10, strength_class="10.9", standard="ISO 4017",
)
population.search_nuts(
    nominal_diameter=10, strength_class="10",
    locking_principle="all-metal",
)
population.search_bolts(coating="zinc flake", coarse_or_fine="coarse")
population.search_bolts(verified_only=True)
population.search_bolts(designation="M10")
```

Pre-existing `population.find_bolt(diameter_mm=..., property_class=...,
head_type=...)` and `population.find_nut(diameter_mm=..., standard=...)`
are unchanged.

## 10. Facade örnekleri

```python
from backend.library.facade import library_registry

library_registry.search_bolts(nominal_diameter=12, standard="EN 14399-3")
library_registry.search_nuts(nominal_diameter=12, standard="EN 14399-4")
```

## 11. Compatibility API örneği ve hata/warning/note davranışı

```python
from backend.library import population
from backend.library.compatibility_engine import check_bolt_nut_compatibility

bolt = population.search_bolts(standard="ISO 4017", designation="M10")[0]
nut = population.search_nuts(standard="ISO 4032", nominal_diameter=10)[0]
result = check_bolt_nut_compatibility(bolt, nut)
# CompatibilityResult(compatible=True, warnings=[], errors=[],
#   engineering_notes=["Nominal thread size: M10.",
#                       "Bolt class 8.8 paired with nut class 8."])
```

The result is never boolean-only. `errors` (diameter/pitch/coarse-fine
mismatch, or a nut property class below the ISO 898-2 minimum for the
bolt's class) force `compatible = False`; everything else that's
merely worth a second look — no temperature-range overlap, no shared
coating, a non-reusable lock nut, a cross-standard-family pairing, a
lubrication-state mismatch — goes into `warnings` without blocking
the pair; `engineering_notes` carries pure informational context
(thread size, class pairing) with no bearing on pass/fail.

## 12. Kaynak izlenebilirliği ve telif politikası

Every record carries `source` / `source_standard` (never empty — see
`find_missing_source` in §8) and a `revision` date. No standard's
copyrighted dimensional table text was reproduced anywhere in this
phase. New records fall into two provenance categories:

- **Reused geometry** (`validation_status="reference_only"`): ISO
  4014, DIN 931, DIN 933, DIN 912, EN 14399-3 reuse the
  already-in-library ISO 4017 (hex head) / ISO 4762 (socket head)
  geometry, on the basis of the documented dimensional correspondence
  between those standard pairs (ISO 4014/4017 share one head table;
  DIN 931/933 are the historical DIN equivalents of ISO 4014/4017;
  DIN 912 is the DIN equivalent of ISO 4762) — not a lookup into any
  new copyrighted table.
- **Ratio-based estimate** (`validation_status="provisional"`): ISO
  4162 (flange bolts), stud bolts, set screws, shoulder bolts,
  reduced-shank bolts, and all seven new nut families/standards use
  engineering ratio estimates (documented per-field in each record's
  `notes` / `metadata.estimated_fields`), explicitly **not** read
  from any standard's dimension table — consistent with the phase
  brief's instruction not to record estimates as certain data.

## 13. Bilinen sınırlamalar

- **Single representative length per diameter.** Bolt
  `nominal_length_mm` / `threaded_length_mm` are one representative
  value per diameter, not the full length range a real catalog would
  carry.
- **No bolt record reaches `validated`.** Every bolt record — legacy
  and new — is `reference_only` or `provisional`; none has been
  independently checked against a primary standard text in this
  phase.
- **Nut `hardness_range` for classes "8"/"9" is a single shared
  estimate** (`170-302 HV`), not size-specific.
- **`compatibility_engine.py`'s strength-pairing table
  (`MINIMUM_NUT_CLASS_FOR_BOLT_CLASS`) is a simplified ISO 898-2
  minimum-class rule**, not the full standard's size- and
  coating-dependent proof-load table.
- **Shoulder bolt shoulder diameter** is stored only in
  `metadata.shoulder_diameter_mm_estimated`, not as a first-class
  schema field.
- **`BoltRecord`/`NutRecord` remain `extra="allow"`** (see §2) rather
  than switching to `extra="forbid"` the way `ThreadRecord` did in
  Faz 2.4.1A.

## 14. Faz 2.4.1C'ye devredilen işler

- Independently verify a meaningful subset of the `reference_only` /
  `provisional` records against primary standard texts and promote
  them to `validated`/`verified`/`approved`.
- Multi-length product tables per diameter (replacing the single
  representative length).
- Size-specific nut hardness ranges for classes 8/9.
- A full ISO 898-2 proof-load table (replacing the simplified
  minimum-class rule in `compatibility_engine.py`).
- Consider promoting `BoltRecord`/`NutRecord` to `extra="forbid"`
  once every family's full field set has been explicitly enumerated
  (mirroring the `ThreadRecord` precedent).
- Washer/bolt/nut three-way compatibility (this phase is bolt↔nut
  only).
