# Faz 2.4.1 – Engineering Database Population

Status: delivered. Populates the Faz 2.4.0 Engineering Library shells
(`backend/library/*_library.py`) with real records. **No calculation
algorithm was touched** — `backend.engineering_core`,
`backend.vdi2230_core` and `backend.calculation_engine` are untouched.

## 1. Veri kategorileri ve kayıt sayıları

| Domain | File | Records | validated | reference_only | provisional | metadata_only |
|---|---|---:|---:|---:|---:|---:|
| Thread Library | `thread_library.json` | 134 | 34 | 28 | 72 | 0 |
| Bolt Library | `bolt_library.json` | 54 | 0 | 54 | 0 | 0 |
| Nut Library | `nut_library.json` | 135 | 10 | 125 | 0 | 0 |
| Washer Library | `washer_library.json` | 189 | 10 | 179 | 0 | 0 |
| Strength Class Library | `strength_class_library.json` | 15 | 15 | 0 | 0 | 0 |
| Material Library | `material_library.json` | 8 | 0 | 8 | 0 | 0 |
| Coating Library | `coating_library.json` | 10 | 0 | 10 | 0 | 0 |
| Lubrication Library | `lubrication_library.json` | 8 | 0 | 8 | 0 | 0 |
| Compatibility Library | `compatibility_library.json` | 9 | 9 | 0 | 0 | 0 |
| OEM Library (catalog only) | `oem_library.json` | 18 | 0 | 0 | 0 | 18 |
| **Total** | | **580** | **78 (13%)** | **412 (71%)** | **72 (12%)** | **18 (3%)** |

(Run `python -c "from backend.library import population as p; import
json; print(json.dumps({k: len(p.load_population_records(k)) for k in
p.POPULATION_SOURCES}, indent=2))"` to reproduce the per-domain counts;
`p.total_population_record_count()` returns 580.)

## 2. Kullanılan kaynaklar (per category, honestly attributed)

**ISO 724 is used for exactly one thing: metric thread base-profile
geometry** (pitch diameter, minor diameter, tensile stress area) —
nothing else in this dataset is derived from ISO 724.

| Category | Primary source | Notes |
|---|---|---|
| Thread geometry (Coarse, ISO 261 diameters M1–M64) | **ISO 724** formula over the **ISO 261** standard diameter/pitch table | `validated` |
| Thread geometry (Coarse, extrapolated M68–M100) | ISO 724 formula, pitch **extrapolated** (no cited standard table beyond M64) | `provisional` |
| Thread geometry (Fine / Extra Fine) | ISO 724 formula; **pitch chosen programmatically**, not looked up from ISO 261/262 | `provisional` |
| Thread geometry (UNC/UNF/UNEF) | **ASME B1.1** | `reference_only` |
| Thread geometry (BSP) | **ISO 228-1** | `reference_only` |
| Thread geometry (NPT) | **ASME B1.20.1** | `reference_only` |
| Thread geometry (Trapezoidal) | **ISO 2904** | `reference_only` |
| Bolt head geometry | **ISO 4017** (hex) / **ISO 4762** (socket) | Only `head_across_flats_mm` is a verified standard-table value; every other geometric field (`head_height_mm`, `socket_size_mm`, `washer_face_diameter_mm`, `bearing_diameter_mm`, hole/tap-drill/engagement/weight) is **ratio-estimated**, not looked up — see per-record `metadata.verified_fields` / `metadata.estimated_fields`. Whole record: `reference_only`. Clearance/tap-drill values are indicative only; consult **ISO 273** for exact per-fit-class clearance-hole diameters. |
| Nut geometry | **ISO 4032 / 4033 / 8673 / 7040 / 10511** | `width_across_flats_mm` always from the standard ISO 4017-family table. `height_mm` is a **verified** ISO 4032 standard-table value only for M3, M4, M5, M6, M8, M10, M12, M16, M20, M24 (`validated`); every other size/standard combination is ratio-estimated (`reference_only`). |
| Washer geometry | **ISO 7089/7090/7091/7093/8738**, **DIN 125/9021** | Fully **verified** standard-table values (ID/OD/thickness) only for ISO 7089 at M3, M4, M5, M6, M8, M10, M12, M16, M20, M24 (`validated`); all other records are ratio-estimated (`reference_only`). |
| Strength classes | **ISO 898-1** (bolts), **ISO 898-2** (nuts) | Verified textbook property-class values. `validated`. |
| Bolt/nut compatibility | **ISO 898-2** (nut proof load ≥ bolt Rm principle) | `validated`. |
| Material properties | Stainless A2/A4: **ISO 3506-1**. Others: named national/ASTM/EN standard (see `source_standard` per record) | Representative property sets, not lot-specific mill-certificate data. Always `reference_only`. |
| Coating friction | **ISO 16047** (test methodology) / **ISO 4042** (electroplated coatings) | Typical ranges, not a specific coating-batch test report. Always `reference_only`. |
| Lubrication friction | **ISO 16047** | Typical ranges, not a specific test report. Always `reference_only`. |
| OEM catalog | TorqPro internal identity list | No technical rule asserted. Always `metadata_only`, never stored on the registered OEM Library object (see §3). |

## 3. Veri üretim yöntemi

`generate` step (not part of the runtime app — a one-off script used
to produce the shipped JSON, kept for reproducibility):

1. ISO 724 base-profile formulas (`d2 = d - 0.6495·P`,
   `d1 = d - 1.0825·P`, `As = 0.7854·(d - 0.9382·P)²`) applied to the
   ISO 261 standard coarse diameter/pitch table for Thread Library.
2. Fine/extra-fine pitches are **picked programmatically** from the
   ISO standard pitch series (nearest allowed pitch below coarse) —
   this pitch *choice* is not independently verified, so those
   records are `provisional` even though the ISO 724 arithmetic on
   top of the chosen pitch is sound.
3. Bolt/nut/washer dimensions combine one verified field (width
   across flats from the well-known ISO 4014/4017 hex table) with
   ratio-estimated fields, **except** for the small set of common
   sizes hardcoded from directly-recalled standard-table values (see
   `VERIFIED_ISO4032_HEIGHT` / `VERIFIED_ISO7089` in the generator) —
   those specific records are promoted to `validated`.
4. Strength classes and the bolt→nut compatibility rule reproduce
   well-known ISO 898-1/898-2 textbook values.
5. Material/coating/lubrication values are representative,
   named-standard-family figures, deliberately kept `reference_only`.
6. Every record gets a SHA-256 `checksum` computed over every field
   except `checksum` itself (see §6), plus `id`, `revision`, `source`,
   `version`, `validation_status`, `approval_status`, `metadata`.

Runtime population (`backend/library/population.py`) is a **separate,
explicit, opt-in step** — see §7.

## 4. Doğrulanmış / provisional ayrımı (status vocabulary)

| `validation_status` | Meaning | May be `approved`? |
|---|---|---|
| `validated` | Independently verifiable standard data (ISO 724 output on an ISO 261 diameter; ISO 898-1/898-2 property class; the specific hardcoded ISO 4032/ISO 7089 sizes) | Yes, if `confidence <= 2` |
| `reference_only` | Sourced from the named standard family but not verbatim-verified against the full table in this exercise; not a direct design input | No — always `pending` |
| `provisional` | Not verified at all (programmatic fine/extra-fine pitch choice; diameters extrapolated past M64) | No — always `pending` |
| `metadata_only` | Catalog/identity entry, no technical content (OEM) | No — always `pending` |

Enforced invariant, checked by
`population.find_invalid_status_values()` and
`tests/test_metadata.py::test_only_validated_records_may_be_approved`:
**`approval_status == "approved"` implies `validation_status ==
"validated"`.** No exceptions exist in the shipped dataset (verified:
0 violations).

## 5. Hukuki ve teknik kullanım sınırlamaları

- This dataset is an **engineering reference aid**, not a substitute
  for the primary standard text. `reference_only` and `provisional`
  records must be checked against the cited standard (or a
  coating/lubrication-specific ISO 16047 test report) before being
  used as a production design input.
- Material property sets are representative of the named grade, not a
  specific heat/lot — do not use in place of a mill certificate.
- Coating/lubrication friction ranges are typical figures; production
  torque-tension calculations must be backed by a joint- and
  batch-specific ISO 16047 test.
- OEM records carry no technical rule; do not infer an OEM-specific
  torque/tolerance value from the mere presence of an OEM name in this
  catalog.
- No record here has been submitted through TorqPro's own engineering
  sign-off process; `approval_status` in this dataset reflects
  *source-verifiability*, not organizational approval.

## 6. Kayıt güncelleme ve onay süreci

1. Data lives in `backend/library/data/*.json`, one file per domain,
   each with a top-level `metadata` block (`name`, `version`,
   `description`, `primary_source`) and a `records` list.
2. To add/correct a record: edit the JSON directly (or extend the
   generator script and re-run it), then recompute that record's
   `checksum` as SHA-256 over the record's own fields *excluding*
   `checksum` (canonical form: `json.dumps(payload, sort_keys=True,
   ensure_ascii=False)`).
3. Set `validation_status` honestly per §4 — do not set `validated`
   without an independently-checked standard-table value, and do not
   set `approval_status="approved"` unless `validation_status ==
   "validated"`.
4. Run the full Faz 2.4.1 integrity suite before merging:
   `population.run_all_integrity_checks()` (also exercised by
   `tests/test_data_integrity.py`) plus `pytest`, `flake8`, `mypy`.
5. A record's `revision` field should be bumped (free-form
   date/tag) whenever its numeric content changes.
6. The OEM Library stays adapter-only by architectural decision (see
   `backend/library/oem_library.py`): do not add a code path that
   calls `OEM_LIBRARY.replace_records(...)`.

## 7. Runtime population — explicit, opt-in, idempotent

`backend/library/population.py`:

- `populate_library(library)` / `populate_all()` copy a data file's
  records into a registered `BaseLibrary` via `replace_records`
  (never `append`), so **repeated calls are idempotent** — no
  duplicate records are ever created (verified by
  `tests/test_data_integrity.py::test_populate_all_called_twice_is_idempotent`).
- **Nothing runs at import time.** Importing `backend.library`
  (which imports `population`) does not populate any library — this
  mirrors the existing Faz 1.4 `migration.py`/`loader.py` convention
  and is asserted by
  `tests/test_registry.py::test_registry_libraries_remain_empty_before_any_explicit_population`
  and `tests/test_data_integrity.py::test_importing_population_module_has_no_registry_side_effects`.
- `find_bolt` / `find_nut` / `find_material` / `find_thread` /
  `find_coating` / `find_lubrication` / `list_strength_classes` /
  `list_oems` read the data files directly (lazily cached) and never
  mutate the registry, so the search API works regardless of whether
  `populate_all()` was ever called.
- The OEM Library never receives records via `populate_library`/
  `populate_all` (raises `KeyError` if attempted) — its catalog is
  read-only via `oem_catalog()` / `list_oems()`.

## 8. Bilinen veri boşlukları / provisional kayıtlar

- All Fine/Extra-Fine thread pitches (72 records) — pitch *selection*
  is programmatic, not looked up from ISO 261/262. Needs a proper
  fine-pitch table lookup in a follow-up phase.
- Thread diameters M68–M100 (16 records) — extrapolated past the
  cited ISO 261 range at a flat 6.0 mm pitch.
- All bolt records (54) — only `head_across_flats_mm` is verified;
  every other geometric field is ratio-estimated (see per-record
  `metadata.estimated_fields`).
- Nut records other than the 10 hardcoded ISO 4032 common sizes (125
  of 135 records) — `height_mm` is ratio-estimated.
- Washer records other than the 10 hardcoded ISO 7089 common sizes
  (179 of 189 records) — dimensions are ratio-estimated.
- All material/coating/lubrication records — representative values,
  not lot/batch-specific.
- OEM catalog — identity only, no technical content.

None of the above are asserted as golden-record values in
`tests/test_golden_records.py`; only genuinely cross-checked values
are asserted there (M6/M10 coarse thread, M10 fine thread pitch
selection caveat included, ISO 4032 M10 nut, ISO 7089 M10 washer,
8.8/10.9/12.9 strength classes).
