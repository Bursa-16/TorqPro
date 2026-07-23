# Coating / Lubrication / Friction Data Ownership

- Status: Accepted
- Date: 2026-07-23

## Context

Faz 2.6 (Friction Condition module, ADR-0009) needs to store friction
values (overall/combined coefficient, and eventually independent
`mu_thread`/`mu_bearing`/nut factor/scatter) for many coating x
lubricant x assembly-condition combinations. Some of the items in the
original Faz 2.6 request (Geomet, Dacromet, zinc flake, phosphate,
PTFE coating, hot-dip galvanized) are coatings, not lubricants — and
`coating_library.json` already carries 10 real `CoatingRecord`
entries, including Geomet (`COAT-GEOMET`), Dacromet
(`COAT-DACROMET`), Delta Protekt zinc flake (`COAT-DELTA_PROTEKT`)
and phosphate + oil (`COAT-PHOSPHATE`). The same coating can behave
very differently depending on which lubricant is applied over it, the
surface/thread/bearing condition, and the test method (Tablo 9.4,
ADR-0009/Faz 2.6.0, is exactly this kind of data — one surface
condition x three lubrication states x different coefficients).
Storing a friction value as if it were an intrinsic, unchanging
property of a coating record (or a lubricant record) would misrepresent
the physics and encourage duplicate/conflicting data across records.

## Options considered

- **A. Everything on `LubricationRecord`.** Rejected: conflates
  coating identity (already separately and adequately modelled by
  `CoatingRecord`) with lubricant identity and with combination-
  dependent friction behaviour; this is the status quo that created
  the problem this ADR resolves (see the `LUBE-SURF-*` records, which
  already show the strain of cramming a surface/lubrication-state
  combination into a lubricant-shaped record).
- **B. New/separate `CoatingRecord` only.** Rejected as the sole
  answer: `CoatingRecord` already exists and is adequate for coating
  identity, but does nothing for the combination-dependent friction
  problem — a coating-only record still cannot express "this coating
  behaves differently with MoS2 vs. dry".
- **C. Single new `FrictionConditionRecord`** modelling coating +
  lubricant + surface condition together, replacing both
  `CoatingRecord` and `LubricationRecord`. Rejected: throws away two
  already-working, already-populated domain models (10 coating + 23
  lubrication records) for no benefit — coating and lubricant
  *identity* data (name, family, substrate, corrosion class,
  temperature range, regulatory status) is not combination-dependent
  and has no reason to move.
- **D. Hybrid (selected).** `CoatingRecord` and `LubricationRecord`
  keep owning their own product/identity data, unchanged in meaning;
  a new `FrictionConditionRecord` owns the combination-dependent
  friction values, referencing the other two by id.

## Decision

**Option D — Hybrid.**

1. **`CoatingRecord`** (`backend/library/models.py`,
   `coating_library.py`) owns a coating's own, condition-independent
   properties: name/designation, coating family, substrate
   applicability, corrosion-related metadata, temperature-related
   metadata, regulatory/status information, source traceability. It
   does **not** own a friction coefficient as an intrinsic property
   (the pre-existing `friction_coefficient_range` free-text field is
   kept, unmodified, for backward compatibility only — see
   "Backward compatibility" below — but no new numeric friction field
   is added here).

2. **`LubricationRecord`** (`lubrication_library.py`) owns a
   lubricant's own, condition-independent properties: name/type,
   lubricant family, application notes, temperature-related metadata,
   reusability/assembly notes, source traceability. Its pre-existing
   Faz 2.6.0/2.6.1 friction fields (`overall_friction_coefficient_*`,
   `mu_thread_*`, `mu_bearing_*`, `k_factor_*`, `scatter_percent`)
   are **kept for backward compatibility** (23 live records use
   them) but are not the long-term home for this data — see
   "Migration plan".

3. **`FrictionConditionRecord`** (new, `friction_condition_library.py`)
   owns friction behaviour that depends on the *combination* of
   coating + lubricant + surface/thread/bearing condition: overall/
   combined friction coefficient, and (schema-only, unpopulated)
   independent `mu_thread`/`mu_bearing`/nut factor/scatter. It
   references `CoatingRecord`/`LubricationRecord` by id
   (`coating_id`/`lubricant_id`, free-text references — this package
   has no relational-integrity layer, so these are advisory, not
   enforced foreign keys).

**Friction coefficients are explicitly not treated as an intrinsic,
unchanging property of a coating or lubricant.** The same coating can
give a different friction result depending on the paired lubricant,
surface/thread/bearing condition, and test method — see Tablo 9.4
(ADR-0009), which shows a 3x range difference for the same surface
condition depending only on lubrication state. Verified `mu_thread`,
`mu_bearing`, `K`, scatter and overall friction data will therefore
be stored on `FrictionConditionRecord` going forward, not invented as
a property of `CoatingRecord` or `LubricationRecord`.

## Domain responsibilities

| Concern | Owner | Notes |
|---|---|---|
| Coating identity (name, family, substrate, corrosion, temperature, regulatory) | `CoatingRecord` | Pre-existing, 10 live records; Faz 2.6.2A adds `coating_family`, `substrate_applicability`, `regulatory_warning`, source-traceability fields (additive, unpopulated) |
| Lubricant identity (name/type, family, application, temperature, reusability) | `LubricationRecord` | Pre-existing, 23 live records; Faz 2.6.2A adds `lubricant_family` (additive, unpopulated) |
| Combination-dependent friction behaviour (overall coefficient, future mu_thread/mu_bearing/K/scatter) | `FrictionConditionRecord` | New, Faz 2.6.2A, 0 live records (schema/decision phase only) |

## Field responsibilities on `FrictionConditionRecord`

Grouped to avoid the same concept being duplicated across two field
names (see also `docs/09_LIBRARY_SPECIFICATION.md` §10.7 for the
authoritative field list):

- **Reference fields**: `coating_id`, `lubricant_id` — which coating/
  lubricant product this friction data applies to (either may be
  empty).
- **Assembly/surface condition fields**: `surface_condition`,
  `thread_condition`, `bearing_condition` — free text, not
  duplicated on `CoatingRecord`/`LubricationRecord` (those describe
  the *product*, not the *assembly instance's* condition).
- **Friction model fields**: `friction_model`
  (`FrictionModelType` — combined vs. split, shared enum with
  `LubricationRecord`).
- **Engineering values**: `overall_friction_coefficient_min/max`,
  `mu_thread_min/max`, `mu_bearing_min/max`, `k_factor_min/max`,
  `scatter_percent`, `max_temperature_c`.
- **Applicability**: `applicability` — free text scope note (e.g.
  bolt size range, joint type), same convention as
  `LubricationRecord.applicability`.
- **Source traceability**: `source_reference`, `source_type`,
  `source_page_or_table`, `verification_status`,
  `engineering_notes` — same shape as `LubricationRecord`'s Faz
  2.6.0/2.6.1 traceability fields, not duplicated in meaning.

No field on this record duplicates a `CoatingRecord`/
`LubricationRecord` identity field (name, family, corrosion class,
etc.) — only the id reference is carried.

## Registry / population / search integration

- `LIBRARY_RECORD_MODELS["friction condition library"] = FrictionConditionRecord`.
- `population.POPULATION_SOURCES["friction condition library"] = "friction_condition_library.json"`.
- `search.CATEGORY_LIBRARY_MAP["friction_condition"] = "friction condition library"` (and `"friction condition"` alias).
- `backend/library/__init__.py` imports and re-exports the new
  `friction_condition_library` module, same convention as every
  other domain shell.
- `validator.validate_friction_condition_library()` reuses the exact
  same friction-specific checks as
  `validator.validate_lubrication_library()` (Faz 2.6.1) — both
  operate generically on raw-dict field names, and
  `FrictionConditionRecord` intentionally shares the same friction/
  nut-factor/scatter field names as `LubricationRecord` (see field
  responsibilities above) so no check logic is duplicated.
- `population.run_all_integrity_checks()` gains
  `"friction_condition_library_faz2_6_2a"`.

All of the above is wired in Faz 2.6.2A; **the data file itself ships
with zero records** — this is a deliberate design decision (see
"Empty by design"), not an oversight.

## Empty by design

`friction_condition_library.json` has `"records": []`. This is
intentional and tested (`test_friction_condition_data_file_has_zero_records`,
`test_friction_condition_library_validator_report_is_empty`,
`test_run_all_integrity_checks_includes_friction_condition_key`).
API/search calls against this library must return an empty result,
never an error — verified by
`test_friction_condition_category_searchable` (returns the registered,
empty library, not `None` or an exception) and
`test_population_sources_include_friction_condition_library`. This
mirrors the exact precedent already established by
`joint_hardware_library.json` in Faz 2.4.1C.

## Backward compatibility

- All 10 live `CoatingRecord`s and all 23 live `LubricationRecord`s
  (8 Faz 2.4.x + 15 Tablo 9.4, ADR-0009) parse unchanged; every Faz
  2.6.2A field addition is optional with a safe default.
- No field was renamed, removed or retyped on either record type.
- No route or API schema was touched.
- `CoatingRecord.friction_coefficient_range` (pre-existing, free-text
  "min..max" style string) is left exactly as-is — not reinterpreted,
  not migrated, not deprecated by this ADR. A future phase may choose
  to deprecate it in favour of `FrictionConditionRecord` once that
  record type is populated; that is an explicit, separate decision,
  not automatic.

## Migration plan (Faz 2.6.2A defines the plan; execution is Faz 2.6.2B+)

Faz 2.6.2A does **not** move any data. Rules for the eventual
migration of the 15 Tablo 9.4 (`LUBE-SURF-*`) records from
`LubricationRecord` to `FrictionConditionRecord`:

1. **Not automatic, not in this phase.** The 23 `LubricationRecord`
   records (8 Faz 2.4.x + 15 Tablo 9.4) are preserved exactly as they
   are by Faz 2.6.2A. Migration is a separately-approved, atomic
   phase (candidate: Faz 2.6.2C or later, after Faz 2.6.2B data
   population establishes real `FrictionConditionRecord` usage
   patterns).
2. **Tablo 9.4 records stay `combined_or_unspecified` reference data**
   on `LubricationRecord` until migrated — they are not reinterpreted,
   split, or upgraded to `split_thread_bearing` by this ADR.
3. **Idempotent and re-runnable.** Any migration script must be safe
   to run more than once without creating duplicate
   `FrictionConditionRecord` entries (mirrors the existing
   `MigrationEngine` convention already used elsewhere in this
   package — see `backend/library/migration.py`).
4. **Old identifiers never disappear.** `LUBE-SURF-*` ids stay valid
   and resolvable on `LubricationRecord` even after a
   `FrictionConditionRecord` counterpart exists — at minimum for a
   documented deprecation window, decided at migration time, not
   assumed here.
5. **Source traceability is carried forward exactly**, not
   re-derived: a migrated record's `source_reference`,
   `source_type`, `source_page_or_table`, `verification_status`,
   `applicability`, `engineering_notes` must be copied verbatim from
   the source `LubricationRecord`, never regenerated or reworded.
6. **No API or stored-calculation regression.** Since no current API
   route consumes `LubricationRecord`'s friction fields in production
   (confirmed in Faz 2.6.0/2.6.1 delivery reports), migration itself
   cannot regress a live endpoint by construction — but the migration
   phase must re-confirm this assumption still holds before executing,
   not assume it is still true.
7. **Verifiable.** The migration phase must ship a check (mirroring
   `population.find_checksum_mismatches`-style verification) proving
   every migrated value round-trips exactly (same numeric bounds,
   same source fields) between the old and new record.

## Risks

- Two record types (`LubricationRecord`, `FrictionConditionRecord`)
  temporarily carry overlapping-shaped friction fields
  (`overall_friction_coefficient_min/max`, `mu_thread_*`, etc.) until
  migration happens. Risk: a future contributor populates new
  friction data on `LubricationRecord` instead of
  `FrictionConditionRecord`, re-creating the problem this ADR
  resolves. Mitigation: `LubricationRecord`'s docstring (Faz 2.6.1)
  and this ADR both state the fields are kept for backward
  compatibility only; Faz 2.6.2B's acceptance criteria (below)
  require new engineering values to be entered on
  `FrictionConditionRecord`, not `LubricationRecord`.
- `coating_id`/`lubricant_id` are free-text, unenforced references.
  Risk: a typo'd id silently fails to resolve. Mitigation: deferred to
  Faz 2.6.2B — a `find_dangling_friction_condition_references`-style
  check (mirroring `find_broken_compatibility_references`) should be
  added once real records exist to check against.
- `CoatingRecord.friction_coefficient_range` (pre-existing) and
  `FrictionConditionRecord.overall_friction_coefficient_min/max`
  (new) could drift out of sync for the same coating once both are
  populated for the same product. Mitigation: not resolved by this
  ADR; flagged as an open decision below.

## Open decisions (carried to Faz 2.6.2B or later)

1. Whether/how to deprecate `CoatingRecord.friction_coefficient_range`
   once `FrictionConditionRecord` has real data for the same coatings.
2. Whether `coating_id`/`lubricant_id` should gain a referential-
   integrity check (data-quality, non-raising, same convention as
   `find_broken_compatibility_references`) before or during Faz
   2.6.2B.
3. Whether `thread_condition`/`bearing_condition` need a closed
   vocabulary (enum) once real data shows the actual range of values
   in use, or should stay free text indefinitely.
4. Exact deprecation window/policy for `LUBE-SURF-*` ids once
   migrated (see migration plan point 4).

## Consequences

Implementation and documentation must follow this decision. New
engineering friction values (mu_thread, mu_bearing, K, scatter,
overall coefficient) must be entered on `FrictionConditionRecord`
from Faz 2.6.2B onward, not on `LubricationRecord` or `CoatingRecord`.
Changes to this ownership split require a superseding ADR.
