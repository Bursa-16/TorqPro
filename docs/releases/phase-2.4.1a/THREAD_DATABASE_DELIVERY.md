# Faz 2.4.1A – ISO Metric Thread Database (field extension)

Status: delivered. Extends the pre-existing `backend/library/data/
thread_library.json` (134 records, shipped as part of Faz 2.4.1's
"populate engineering database" delivery, commit `fc33d4d` / merge
`e5816ac`) with the Faz 2.4.1A `ThreadRecord` schema fields. No
pre-existing record value was changed — see §5. No bolt/nut/washer/
strength-class/coating/lubrication/OEM database, GUI, API, service
layer, or VDI 2230 formula was touched.

## 0. Context note (read before the rest of this document)

The original Faz 2.4.1A brief assumed the thread database did not
exist yet. Analysis at the start of this branch (see conversation
record) found it had already been delivered under Faz 2.4.1, under a
different field naming scheme and mixed metric/non-metric scope. The
approved plan was: **keep the existing schema and all 106 ISO-metric
records' numeric values as-is; add the missing Faz 2.4.1A fields
alongside them; explicitly separate the 28 pre-existing non-metric
records from this phase's own validation/search scope rather than
deleting them.** Everything below reflects that plan, not the
original from-scratch brief.

## 1. Veri kapsamı ve toplam kayıt sayısı

| Scope | Records |
|---|---:|
| ISO Metric (`thread_series == "ISO_METRIC"`) | **106** |
| Non-metric (UNC/UNF/UNEF/BSP/NPT/Trapezoidal, pre-existing, out of this phase's scope) | **28** |
| **Total** | **134** |

ISO Metric coarse/fine/extra-fine breakdown (unchanged from Faz
2.4.1, `pitch_type` now labels the same split explicitly):

| `pitch_type` | Records |
|---|---:|
| coarse | 42 |
| fine | 35 |
| extra_fine | 29 |
| **Total ISO Metric** | **106** |

Non-metric breakdown, by `thread_series`:

| `thread_series` | `pitch_type` | Records |
|---|---|---:|
| UNC | coarse | 5 |
| UNF | fine | 5 |
| UNEF | extra_fine | 3 |
| BSP | *(none — no coarse/fine analogue)* | 5 |
| NPT | *(none)* | 4 |
| TRAPEZOIDAL | *(none)* | 6 |
| **Total non-metric** | | **28** |

(Exact split reproducible via `population.find_thread(thread_series=...)`.)

## 2. Alan tanımları (Faz 2.4.1A additions)

All new fields are optional/additive; every pre-existing field (`id`,
`designation`, `nominal_diameter_mm`, `pitch_mm`, `tolerance_class`,
`stress_area_source`, `series`, `pitch_diameter_mm`,
`minor_diameter_mm`, `stress_area_mm2`, `source_standard`,
`confidence`, `notes`, `revision`, `source`, `version`,
`validation_status`, `approval_status`, `checksum`, `metadata`) is
kept unchanged, unrenamed.

| Field | Type / unit | Meaning |
|---|---|---|
| `pitch_type` | `"coarse" \| "fine" \| "extra_fine" \| null` | Structured counterpart of `series`. `null` where no coarse/fine analogue exists (BSP/NPT/Trapezoidal). |
| `thread_series` | str, one of `KNOWN_THREAD_SERIES` | `"ISO_METRIC"` for the 106 metric records; `"UNC"/"UNF"/"UNEF"/"BSP"/"NPT"/"TRAPEZOIDAL"` for the 28 non-metric records. **This is the field that defines Faz 2.4.1A's own scope** — see `validator.is_iso_metric_thread_record`. |
| `major_diameter_mm` | mm | ISO 724 basic (theoretical, no tolerance) major diameter. Equal to `nominal_diameter_mm` for both external and internal threads in the basic profile — carried as its own field for schema completeness, not because the value differs (see docstring in `models.py`). Set for all 134 records (major-diameter = nominal-diameter is a standard-independent definition, true for UN/BSP/NPT/Trapezoidal too). |
| `minor_diameter_external_mm` | mm | External (bolt) minor diameter, rounded root, ISO 724 `d3 = D − 1.226869·P`. Set for the 106 ISO-metric records only; `null` for the 28 non-metric records (ASME B1.1/ISO 228-1/ASME B1.20.1/ISO 2904 use different root-rounding conventions — no value invented). |
| `minor_diameter_internal_mm` | mm | Internal (nut) minor diameter, sharp root, ISO 724 `D1 = D − 1.082532·P`. For the 106 metric records this is a direct copy of the pre-existing `minor_diameter_mm` value (verified to already be the D1 formula result, e.g. M6 → 4.9175 mm). `null` for the 28 non-metric records, same reasoning as above. |
| `source_reference` | str | Mirrors the pre-existing `source` field 1:1. |
| `source_revision` | str | Mirrors the pre-existing `revision` field 1:1. |
| `confidence_level` | `ConfidenceLevel` (int 1–4) | Mirrors the pre-existing `confidence` field 1:1. |
| `review_status` | str | Mirrors the pre-existing `validation_status` field 1:1 (distinct from `validation_status`/`approval_status`, which are kept as the Faz 2.4.1 pair). |
| `schema_version` | str, constant | `"1.0"` for every thread record (`THREAD_SCHEMA_VERSION` in `models.py`). Deliberately distinct from the dataset-level `version` field (`"2.4.1"`), which tracks the data *release*, not the record *shape*. |

## 3. Türetilmiş alan formülleri (ISO 724 basic profile)

Central helper: `backend/library/thread_geometry.py` (pure functions,
no I/O). Constants duplicated — not imported — from
`backend.vdi2230_core.stress_area`'s existing ISO 68-1 constants,
matching that module's own package-isolation pattern; `backend.library`
stays independent of `backend.vdi2230_core` / `backend.calculation_engine`
(Faz 2.4 Option C architecture decision — no VDI 2230 formula was read,
imported, or changed).

With `H = sqrt(3)/2 · P` (ISO 68-1 basic triangle height):

```
major diameter (basic, external & internal) = D          (nominal)
pitch diameter  d2 = D2                      = D − 0.75·H       = D − 0.649519·P
minor diameter, external (bolt, rounded root) d3 = D − (17/12)·H = D − 1.226869·P
minor diameter, internal (nut, sharp root)   D1 = D − 1.25·H    = D − 1.082532·P
```

Verified against the existing data before use: M6 (`P=1.0`) →
computed `d2=5.3505`, `D1=4.9175`, matching the pre-existing
`pitch_diameter_mm`/`minor_diameter_mm` exactly; M10 (`P=1.5`) →
`d2=9.0257`, `D1=8.3762`, matching to the data's own rounding.

## 4. Doğrulama kuralları (`validator.py`, Faz 2.4.1A section)

All opt-in via `validate_thread_library()`; the metric-geometry checks
(designation↔diameter, pitch_type↔series, minor-diameter tolerance,
stress-area tolerance) only ever run against
`thread_series == "ISO_METRIC"` records — non-metric records are
always skipped by those four, never flagged for not matching ISO 724:

- `find_duplicate_thread_designation_pitch` — duplicate `(designation, pitch_mm)`.
- `find_non_positive_thread_dimensions` — `nominal_diameter_mm`/`pitch_mm` must be > 0.
- `find_thread_designation_diameter_mismatches` — parses `"M10"`/`"M10x1.25"` and checks against `nominal_diameter_mm` (ISO_METRIC only).
- `find_thread_pitch_type_classification_mismatches` — `pitch_type` must agree with `series` (ISO_METRIC only).
- `find_thread_schema_version_issues` — `schema_version` must equal `THREAD_SCHEMA_VERSION`.
- `find_thread_unknown_fields` — batch report of any field not declared on `ThreadRecord` (alongside the `extra="forbid"` Pydantic layer, which raises on the first violation instead).
- `find_thread_series_scope_issues` — `thread_series` must be one of `KNOWN_THREAD_SERIES`.
- `find_thread_minor_diameter_tolerance_violations` — recomputes `minor_diameter_external_mm`/`minor_diameter_internal_mm` via `thread_geometry.py`, tolerance 0.001 mm (ISO_METRIC only).
- `find_thread_stress_area_tolerance_violations` — recomputes `stress_area_mm2` via the ISO 898-1 formula already named in each record's own `stress_area_source`, tolerance 0.05 mm² (ISO_METRIC only).

Result over the live 134-record dataset: **zero issues** on every
check (`validate_thread_library_records() == []`).

### Unknown-field rejection: two layers, documented choice

`ThreadRecord.model_config` overrides `LibraryRecordBase`'s
`extra="allow"` to `extra="forbid"` **for `ThreadRecord` only**
(Pydantic v2 resolves `model_config` per-subclass, verified in a
scratch test before use — the other nine domain records are
untouched). This required explicitly declaring the four pre-existing
fields that were previously passing through untyped
(`series`, `pitch_diameter_mm`, `minor_diameter_mm`,
`stress_area_mm2`) — without that, `extra="forbid"` would have
rejected all 134 existing records. `find_thread_unknown_fields` exists
as a second, non-raising layer so a caller can see every unknown
field across a whole batch in one report instead of stopping at the
first `ValidationError`.

## 5. Veri değişikliği: kesin diff garantisi

The augmentation script (`/home/claude/scratch/augment_thread_data.py`,
not shipped — one-off, out-of-repo) only ever *added* keys to each of
the 134 record dicts. Verified before commit:

```
old = {record['id']: record for record in <pre-change JSON>}
for record in <post-change JSON>:
    for key, value in old[record['id']].items():
        assert record[key] == value   # zero violations
```

The **only** genuinely new *numeric* values introduced are
`minor_diameter_external_mm` for the 106 ISO-metric records (no
external-minor-diameter field existed in any form before). Everything
else copies or mirrors a pre-existing value under a new field name.

**Side effect found and corrected during this phase:** each record's
`checksum` is a SHA-256 hash over every field except `checksum`
itself (`population.find_checksum_mismatches`). Adding fields changes
that hash, so all 134 checksums were recomputed with the same
algorithm to match the new field set — this is an integrity-hash
update, not an engineering-value change, and is included in the same
commit as the field additions (see commit list, §9).

## 6. Bilinen eksikler / kapsam dışı bırakılanlar

- `minor_diameter_external_mm` / `minor_diameter_internal_mm` are
  `null` for all 28 non-metric records — ISO 724 does not apply to
  UNC/UNF/UNEF/BSP/NPT/Trapezoidal, and deriving their national-
  standard-specific minor-diameter formulas was out of this phase's
  scope. `review_status` on those records is `"reference_only"`
  (mirrored from `validation_status`), signalling they need
  standard-specific work before promotion.
- `pitch_type` is `null` for BSP/NPT/Trapezoidal — no coarse/fine
  analogue exists for these series; not guessed.
- Static shell metadata in `thread_library.py`
  (`version="0.1"`, `status="draft"`, `record_count=0`) was
  **deliberately left unchanged** — this is the same declared
  pre-population initial state used uniformly across all nine other
  domain shells (verified by inspection), and `record_count` is
  already single-sourced at runtime (`BaseLibrary.replace_records`
  syncs `metadata.record_count = len(records)` on every populate
  call — see `test_registry_record_count_matches_loaded_total_after_populate`).
  Changing only the thread shell would have created an unrequested
  inconsistency versus the other eight.
- Faz 2.4.1B (bolt/nut/washer/strength-class/coating/friction
  database, OEM torque presets, GUI, API, Service Layer, VDI 2230
  changes, torque recommendation engine) is explicitly out of scope
  and was not started.

## 7. Test sonucu

- New file: `tests/test_thread_database_faz2_4_1a.py` — 22 tests
  (golden records M12/fine/extra-fine, 106+28 count split, registry
  parity, search filters incl. backward-compat alias, one negative
  fixture per validation check, non-metric skip confirmation, clean
  validation over the live dataset).
- Full suite: **375/375 passing** (353 pre-existing + 22 new), zero
  regressions.

## 8. Komut sırası ve mimari kararlar (özet)

1. `models.py` — `ThreadRecord` field extension + `extra="forbid"` override.
2. `thread_geometry.py` — central ISO 724 basic-profile helper.
3. `data/thread_library.json` — field population (incl. checksum recompute).
4. `population.py` — `find_thread()` filter extension + count helpers.
5. `validator.py` — thread-specific validation section.
6. `population.py` — `validate_thread_library_records()` wrapper.
7. `tests/test_thread_database_faz2_4_1a.py` — test suite.
8. This document.

## 9. Kalite kontrolleri ve commit/teslim bilgileri

See the delivery report in the conversation for the full pytest/
flake8/mypy/clean-clone output and the final commit hash / patch /
bundle / SHA256SUMS.txt / ZIP filenames (generated after this
document, so this section intentionally does not duplicate hashes
that would go stale the moment this file itself is committed).
