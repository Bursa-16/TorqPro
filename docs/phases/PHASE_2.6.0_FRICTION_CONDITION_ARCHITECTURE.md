# Faz 2.6.0 — Friction Condition Module: Architecture & Specification

- **Status:** Delivered
- **Date:** 2026-07-23
- **Product owner:** İlhan Çekiç
- **Naming:** Module is "Friction Condition" (2026-07-23 rename directive). Lubrication is a subsection of it. "Lubrication Module"/"Lubrication Engineering Module" used only where the text refers specifically to lubricant data.

## 1. Documents read

`CLAUDE.md`, `docs/12_CLAUDE_CONTEXT.md`, `docs/README.md`, `docs/11_PRODUCT_BACKLOG.md`, `docs/09_LIBRARY_SPECIFICATION.md`, `docs/05_ENGINEERING_FORMULA_SPECIFICATION.md`, and the repository source: `backend/library/models.py`, `backend/library/lubrication_library.py`, `backend/library/data/lubrication_library.json`, `backend/engineering_core/friction.py`, `backend/engineering_core/torque.py`, `backend/engineering_core/joint.py`, `backend/engineering_core/validation.py`, `backend/app.py` (friction-related sections).

## 2. Current architecture/features (as found)

- FastAPI + SQLite + single-page HTML/PWA (per `docs/12_CLAUDE_CONTEXT.md`).
- `backend/library/lubrication_library.py` + `data/lubrication_library.json`: 8 lubricant-product records, single `friction_coefficient_min/max` range, `source_standard = "ISO 16047"`, `reference_only`.
- `backend/library/models.py::LubricationRecord`: existing Pydantic schema (Faz 2.4.0–2.4.2B), `extra="allow"`.
- `backend/engineering_core/friction.py` + `torque.py` + `joint.py`: already implement independent `mu_thread`/`mu_bearing` tightening-torque decomposition (`M_G` + `M_K`), fed by direct API input (`backend/app.py` `EngineeringCheck` model). Not library-sourced.
- No Faz 2.6/Friction Condition epic existed in `docs/11_PRODUCT_BACKLOG.md` prior to this phase.

## 3. Backlog item executed

`docs/11_PRODUCT_BACKLOG.md` §12, sub-phase **2.6.0 – Architecture & Specification**, approved 2026-07-23 with explicit scope: no comprehensive calculation or estimated coefficient added to production code; architecture, schema extension design, documentation and Tablo-9.4-scoped reference data only.

## 4. Architecture decision

See `docs/adr/ADR-0009-friction-condition-module.md` for full rationale. Summary:

1. Naming moved to "Friction Condition" at the documentation/architecture/UI level; no Python identifier renamed (`LubricationRecord`, `lubrication_library.py`, `lubrication_library.json` unchanged — see ADR-0009 §1 exception).
2. `LubricationRecord` extended additively with 21 new optional fields (friction/nut-factor schema, source traceability, restricted-legacy support) rather than introducing a separate `FrictionModel`/`FrictionCoefficientSet` domain model — deferred until a record needs independently-sourced-per-field traceability (see ADR-0009 §2, open need #1/#2).
3. `Status` enum gained `RESTRICTED_LEGACY` (reused existing field, not a new parallel one).
4. `LubricationType` enum gained `OILED_GENERIC`, `MOS2_WITH_OIL` (Tablo 9.4 states with no existing match; "Kuru" reuses `NO_LUBRICANT`).
5. `backend/engineering_core` (friction.py/torque.py/joint.py) — untouched. Verified by `test_engineering_core_friction_and_torque_untouched`.

## 5. Files changed

- `backend/library/models.py` — `Status.RESTRICTED_LEGACY`; `LubricationType.OILED_GENERIC`/`MOS2_WITH_OIL`; new `FrictionModelType` enum; `LubricationRecord` additive fields; `__all__` export; naming-clarification docstrings.
- `backend/library/lubrication_library.py` — naming-clarification docstring only (no behavioural change).
- `backend/library/data/lubrication_library.json` — 15 new `LUBE-SURF-*` records appended (8 → 23), metadata version bumped to `2.6.0`. No existing record modified.
- `tools/generate_faz_2_6_0_table_9_4_records.py` — new, one-off/idempotent generator for the 15 records (checksum-correct).
- `tests/test_faz2_4_2b_library_schema_completion.py` — updated 2 hardcoded record-count assertions (8 → 23) and the OEM-compatibility check scope; no other test logic changed.
- `tests/test_faz2_6_0_lubrication_architecture.py` — new, 9 tests (backward compatibility, Tablo 9.4 traceability, restricted-legacy handling, enum integrity, engineering-core non-interference).
- `docs/09_LIBRARY_SPECIFICATION.md` — new §10 "Friction Condition module (Faz 2.6)".
- `docs/05_ENGINEERING_FORMULA_SPECIFICATION.md` — new §21 "Friction Condition module linkage (Faz 2.6)".
- `docs/11_PRODUCT_BACKLOG.md` — new §12 epic (2.6.0–2.6.7 sub-phases), renumbered former §12 to §13.
- `docs/adr/ADR-0009-friction-condition-module.md` — new.
- `docs/phases/PHASE_2.6.0_FRICTION_CONDITION_ARCHITECTURE.md` — this document.

## 6. Compatibility analysis

- All 8 pre-existing lubrication records parse identically (`test_all_eight_pre_faz_2_6_0_records_unaffected`); no field renamed, removed or retyped.
- `Status` and `LubricationType` enum additions are new members only — no existing member's value changed.
- `LUBRICATION_LIBRARY` registry entry, file names and record ids predating Faz 2.6.0 are unchanged.
- No route, API schema, or `engineering_core` calculation changed.
- Checksums for the 15 new records were computed with the same algorithm `backend/library/population.py::find_checksum_mismatches` uses (SHA-256 over all fields except `checksum`, `sort_keys=True`); verified by `tests/test_data_integrity.py::test_no_checksum_mismatches_in_shipped_data`.

## 7. Tests run

```
python -m pytest -q
```

Result: **672 passed** (baseline before this phase: 663 passed; +9 new Faz 2.6.0 tests, 0 regressions).

```
flake8 --max-line-length=100 <changed .py files>
```

Result: clean (0 issues) on all changed Python files. `ruff`/`black`/`mypy` are not currently installed/configured in this repository (`requirements-dev.txt` only lists `pytest`, `httpx`) — flagged as a risk below, not silently skipped.

## 8. Known limitations / technical debt

- `ruff`, `black`, `mypy` are not part of the current dev toolchain (only `flake8` is established, per `CLAUDE.md`/prior-phase convention). The Faz 2.6 spec's acceptance criterion "Ruff, Black, MyPy and Pytest must all pass" cannot be honoured until these tools are added to `requirements-dev.txt` and a baseline run is done — this needs a decision (add now as a small separate task, or defer to Faz 2.6.7).
- Surface Condition / Coating are represented only as a free-text `surface_condition` field on `LubricationRecord`, not as independent record types cross-referencing `coating_library.py`. Open decision for Faz 2.6.1 (ADR-0009 open need #2).
- No mu_thread/mu_bearing/K/scatter/max-temperature value exists for any of the 19 lubricants named in the original Faz 2.6 request — none was invented, per project rule. This is the primary blocker for Faz 2.6.2/2.6.3 and requires a source decision from the product owner.
- Cadmium `regulatory_warning` text is a general caution, not a cited regulatory clause (deliberately, per this phase's scope) — needs sourcing in Faz 2.6.2.
- Torque-distribution percentage reporting (thread/bearing/clamp-force split as % of `M_A`) is designed for but not implemented in Faz 2.6.0; it is additive on top of the existing `M_G`/`M_K` formula and does not require a formula change, only new reporting code (Faz 2.6.3).

## 9. Risks

- Any future population of `mu_thread`/`mu_bearing` per lubricant must not reuse the Tablo 9.4 combined coefficients as if they were already split — `friction_model = combined_or_unspecified` on those 15 records exists specifically to prevent that misuse; downstream code must check this field before treating a record as a valid `M_G`/`M_K` input source.
- `LubricationRecord`'s `extra="allow"` config means a malformed future record with a typo'd field name (e.g. `overal_friction_coefficient_min`) will not be rejected by the schema; this was already true before Faz 2.6.0 and is unchanged, but the added field count increases the surface area for this class of silent error. Consider `extra="forbid"` for this record type in a later phase (as already done for `ThreadRecord`), as a separate, explicit decision.

## 10. Faz 2.6.1 acceptance criteria (proposed)

1. Explicit decision (with product owner) on whether Surface Condition and Coating become independent record types or remain fields on `LubricationRecord`; if independent, schema added additively with a superseding note to ADR-0009.
2. If a `SourcedFrictionValue`/`FrictionCoefficientSet` nested model is adopted (per ADR-0009 §2 trigger condition), it must be additive: existing flat fields (`mu_thread_min/max` etc.) either remain as a computed/derived convenience or are formally deprecated with a migration note — no record from Faz 2.6.0 may fail to load.
3. No new coefficient value added without: `source_reference`, `source_type`, `source_page_or_table`, `verification_status`, `applicability` populated (per `LubricationRecord`'s Faz 2.6.0 fields) — enforced by a new data-quality check function in `backend/library/population.py`, mirroring `find_checksum_mismatches`/`find_schema_violations` pattern.
4. Full test suite (existing + new) passes; `flake8 --max-line-length=100` clean on changed files; working tree clean.
5. `docs/11_PRODUCT_BACKLOG.md` §12 sub-phase 2.6.1 row updated with delivery date and file references.
