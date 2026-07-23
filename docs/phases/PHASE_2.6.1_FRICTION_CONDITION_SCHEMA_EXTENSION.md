# Faz 2.6.1 — Friction Condition Schema Extension (Lubrication Subsection)

- **Status:** Delivered
- **Date:** 2026-07-23
- **Product owner:** İlhan Çekiç
- **Scope:** production-level clarification of the Faz 2.6.0 additive schema, concept separation, stronger data-quality validation. No recommendation engine, torque-correction engine, torque decomposition reporting, UI or PDF reporting in this phase (explicitly out of scope per directive).

## 1. Architecture decision applied (ADR-0009)

Re-evaluated ADR-0009 §2's trigger condition for a separate `FrictionCoefficientSet`/nested domain model (a record whose different coefficient fields are independently sourced). **Not met**: every one of the 23 live records still uses one shared source per record. Decision: **flat additive fields on `LubricationRecord` stand unchanged**; no nested model introduced in Faz 2.6.1. See `docs/adr/ADR-0009-friction-condition-module.md` "Faz 2.6.1 addendum".

## 2. Concept separation (item 2 of the directive)

Documented directly on `LubricationRecord`'s docstring (`backend/library/models.py`) — 8 concepts, each mapped to its field group:

| Concept | Field(s) | Status |
|---|---|---|
| Surface condition | `surface_condition` | Free text (Faz 2.6.0) |
| Coating | *(none — see `CoatingRecord`)* | Not cross-referenced; open (ADR-0009 #2) |
| Lubricant | `lubricant_type`, `designation`, `application`, `oem_compatibility` | Faz 2.4.0/2.4.2B |
| Overall/combined friction coefficient | `overall_friction_coefficient_min/max`, `friction_model` | Faz 2.6.0, populated (Tablo 9.4) |
| Thread friction coefficient | `mu_thread_min/max` | Schema only, unpopulated |
| Bearing friction coefficient | `mu_bearing_min/max` | Schema only, unpopulated |
| Nut factor | `k_factor_min/max` | Schema only, unpopulated |
| Scatter | `scatter_percent` | Schema only, unpopulated |

## 3. Validation strengthened (item 7 of the directive)

New in `backend/library/validator.py`, all non-raising/opt-in (consistent with every other domain's checks in this file — no Pydantic-level raising validator added to `LubricationRecord`):

- `find_friction_min_max_violations` — min <= max for `friction_coefficient`, `overall_friction_coefficient`, `mu_thread`, `mu_bearing`, `k_factor` pairs.
- `find_friction_negative_values` — defense-in-depth negative-value check on raw dicts (Pydantic `Field(ge=0)` already rejects these at typed-parse time; this catches the same on the `population.find_lubrication` raw-dict path).
- `find_friction_asymmetric_min_max` — rejects a min set without its max (or vice versa).
- `find_friction_one_sided_thread_bearing` — rejects `mu_thread` populated without `mu_bearing`, or vice versa.
- `find_friction_coefficient_missing_source` — rejects any Faz 2.6.0 engineering-value field (`overall_friction_coefficient_*`, `mu_thread_*`, `mu_bearing_*`, `k_factor_*`, `scatter_percent`, `max_temperature_c`) populated without `source_reference`.
- `find_restricted_legacy_missing_warning` — rejects `status = restricted_legacy` without a `regulatory_warning`.

Composed into `validate_lubrication_library()` and exposed via `population.validate_lubrication_library_records()` / `population.run_all_integrity_checks()["lubrication_library_faz2_6_1"]`.

## 4. Backward compatibility (items 4, 9)

- All 23 live records (8 Faz 2.4.x + 15 Tablo 9.4) pass every new check with **zero issues** (`test_live_lubrication_data_has_zero_validator_issues`).
- No field renamed, removed or retyped; `LubricationRecord`'s Pydantic shape is unchanged from Faz 2.6.0 (only docstrings/comments reorganized).
- `backend/app.py` does not call `load_typed`/`find_schema_violations` for the lubrication library in any route today, so no API/service-layer behaviour could regress; confirmed by import/smoke check (`backend.app` imports and constructs its `FastAPI` app unchanged).
- Item 6 confirmed: all 15 Tablo 9.4 records still carry only `overall_friction_coefficient_min/max` + `friction_model = combined_or_unspecified` — untouched by this phase.
- Item 5 confirmed: zero `mu_thread`/`mu_bearing`/`k_factor`/`scatter_percent`/`max_temperature_c`/`corrosion_resistance` values exist anywhere in the data file after this phase (`test_faz_2_6_1_no_new_coefficient_values_populated`).

## 5. Loader/model conversion (item 8)

No change was needed to `backend/library/loader.py` (`load_typed`, `parse_typed_records`) — the new checks are data-quality functions operating on raw dicts (same pattern as every other `find_*` in `validator.py`), not schema-level Pydantic constraints, so the typed-parse path is unaffected by design. `population.py` gained one new wrapper (`validate_lubrication_library_records`) and one new key in `run_all_integrity_checks()`, following the exact pattern already used for bolt/nut/washer/joint-hardware libraries.

## 6. Files changed

- `backend/library/models.py` — `LubricationRecord` docstring restructured with explicit 8-concept map and ADR-0009 §2 re-affirmation; inline field-group comments updated; no field added/removed/retyped.
- `backend/library/validator.py` — 6 new `find_*` functions + `validate_lubrication_library()`.
- `backend/library/population.py` — `validate_lubrication_library_records()`; `run_all_integrity_checks()` gains `"lubrication_library_faz2_6_1"`; `__all__` updated.
- `tests/test_faz2_6_0_lubrication_architecture.py` — 15 new tests (`TestFaz261LubricationValidators` class + `test_faz_2_6_1_no_new_coefficient_values_populated`).
- `docs/adr/ADR-0009-friction-condition-module.md` — "Faz 2.6.1 addendum" section appended.
- `docs/09_LIBRARY_SPECIFICATION.md` — new §10.6 status note.
- `docs/11_PRODUCT_BACKLOG.md` — §12 sub-phase 2.6.1 row updated with delivery status.
- `docs/phases/PHASE_2.6.1_FRICTION_CONDITION_SCHEMA_EXTENSION.md` — this document.

No data file (`lubrication_library.json`) was modified — item 4/5/6 compliance.

## 7. Tests run

```
python -m pytest -q
```
Result: **687 passed** (Faz 2.6.0 baseline: 672 passed; +15 new Faz 2.6.1 tests, 0 regressions).

```
flake8 --max-line-length=100 backend/library/models.py backend/library/population.py \
  backend/library/validator.py tests/test_faz2_6_0_lubrication_architecture.py
```
Result: clean (0 issues).

```
git diff --check
```
Result: clean (0 whitespace/conflict-marker issues).

```
python -c "import backend.app; from backend.library import population, validator, models; ..."
```
Result: `backend.app` imports and constructs its `FastAPI` app; `LubricationRecord` minimal-record smoke-construct succeeds; `run_all_integrity_checks()` returns the expected key set including `lubrication_library_faz2_6_1`.

Verified in a clean clone from the delivered bundle (see repository root for patch/bundle/checksum files) — same 687-pass / flake8-clean result reproduced independently of the working sandbox.

## 8. Faz 2.6.2 — missing verified data sources (explicit gap list)

None of the following exist yet, for any of the 19 originally-requested lubricants (Dry steel, Light oil, Engine oil, Assembly oil, MoS₂ paste, Graphite grease, Copper anti-seize, Nickel anti-seize, Zinc flake coating, Geomet, Dacromet, PTFE coating, Wax coating, Phosphate+oil, Cadmium coating, Zinc plated, Hot dip galvanized, Stainless dry, Stainless lubricated):

1. **Independent `mu_thread`/`mu_bearing` values** — no approved source (VDI 2230 table, ISO 16047 test report, or supplier datasheet) has been selected. This is the single largest blocker for Faz 2.6.2/2.6.3.
2. **`k_factor_min/max`** — no approved nut-factor source per lubricant.
3. **`scatter_percent`** — no approved statistical-scatter source (would typically come from an internal ISO 16047 test series, not a textbook table).
4. **`max_temperature_c`** — no approved thermal-limit source per lubricant/coating.
5. **`corrosion_resistance` / `reusability`** — no approved qualitative rating scale or source has been defined yet (needs a decision: free text vs. closed enum vs. numeric rating).
6. **`recommended_standards`** — no approved mapping of lubricant -> applicable standards list exists yet.
7. **Geomet, Dacromet, PTFE coating (as a coating, not the existing `PTFE_DRY_FILM` lubricant type), copper/nickel anti-seize (as distinct products, beyond the existing combined `COPPER_NICKEL_ALUMINIUM_PASTE` enum member), zinc flake, hot-dip galvanized, stainless dry/lubricated** — none of these has any record at all yet (Tablo 9.4 only covered 5 surface conditions, not this list).
8. **Coating cross-reference** — whether these coating-type lubricants should link to `coating_library.py`'s existing `CoatingRecord`/`CoatingType` (which already lists Zinc flake, Geomet-adjacent, Dacromet-adjacent members — needs verification) instead of being duplicated inside `LubricationRecord`, remains an open architecture question (ADR-0009 #2) that should be resolved before Faz 2.6.2 populates data, to avoid creating duplicate/conflicting coating definitions across two libraries.

**Recommendation for Faz 2.6.2 kickoff:** resolve gap #8 first (coating cross-reference decision), then obtain and cite sources for gaps #1–#6 per lubricant before any value is entered — per `docs/12_CLAUDE_CONTEXT.md` §4 and the `find_friction_coefficient_missing_source` check added in this phase, no value will pass validation without a populated `source_reference` regardless.
