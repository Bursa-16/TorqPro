# Friction Condition Module: Schema Extension and Naming

- Status: Accepted
- Date: 2026-07-23

## Context

Faz 2.6 asks TorqPro to grow from a lubricant selector into a full
engineering subsystem covering lubrication, surface condition,
coatings, independent thread/bearing friction, nut factor, scatter,
recommendation and warnings. The product owner subsequently directed
(2026-07-23) that the module be named **Friction Condition**
throughout documentation, architecture, backlog, ADRs, comments and
UI planning; "Lubrication" is a subsection of Friction Condition, not
the module itself. "Lubrication Module"/"Lubrication Engineering
Module" remain acceptable only when referring specifically to
lubricant data.

Faz 2.6.0 is architecture and specification only: no new engineering
coefficient is invented, per docs/12_CLAUDE_CONTEXT.md SS4.

## Decision

1. **Naming.** Product/architecture-level naming is "Friction
   Condition module". Code identifiers are NOT renamed in Faz 2.6.0:
   `backend.library.models.LubricationRecord`,
   `backend/library/lubrication_library.py` and
   `backend/library/data/lubrication_library.json` keep their names
   and content unchanged (see docs/09_LIBRARY_SPECIFICATION.md SS10 for
   the exception this naming rule explicitly carves out). A future
   phase may introduce genuinely new record types for Surface
   Condition / Coating / Friction Model as independent components;
   until then, `LubricationRecord` is the Lubrication subsection's
   implementation.

2. **Schema extension is additive on `LubricationRecord`, not a new
   nested domain model.** Faz 2.6.0 adds flat, optional fields
   (`overall_friction_coefficient_min/max`, `friction_model`,
   `mu_thread_min/max`, `mu_bearing_min/max`, `k_factor_min/max`,
   `scatter_percent`, `max_temperature_c`, `corrosion_resistance`,
   `reusability`, `recommended_standards`, `surface_condition`,
   `source_reference`, `source_type`, `source_page_or_table`,
   `verification_status`, `applicability`, `engineering_notes`,
   `regulatory_warning`) directly on `LubricationRecord`, all
   optional with safe defaults. Every pre-Faz-2.6.0 record (the 8
   Faz 2.4.1/2.4.2B lubricant-product records) validates unchanged.

   A separate `FrictionModel`/`FrictionCoefficientSet` domain model
   was evaluated and rejected **for this phase**: every Faz 2.6.0
   record's engineering values (all from Tablo 9.4) share one single
   source, so per-value traceability collapses to per-record
   traceability and a nested model adds indirection without benefit
   yet. This is revisited once Faz 2.6.2 introduces records whose
   `mu_thread`, `mu_bearing` and `k_factor` are independently sourced
   (e.g. one from a VDI 2230 table, another from a supplier
   datasheet) -- at that point per-value traceability becomes
   necessary and a nested `SourcedFrictionValue`-style model should be
   adopted then, additively, without breaking the flat fields added
   here.

3. **`Status` enum gains `RESTRICTED_LEGACY`.** Reused rather than
   inventing a parallel field: cadmium-plated surface records use the
   existing `LibraryRecordBase.status` field with this new member,
   plus the new `regulatory_warning` free-text field. No specific
   regulatory clause is asserted by Faz 2.6.0; that verification is
   explicitly deferred to Faz 2.6.2.

4. **`LubricationType` gains two members** (`OILED_GENERIC`,
   `MOS2_WITH_OIL`) to model Tablo 9.4's "Yagli"/"MoS2 ile Yagli"
   states, which do not match any pre-existing member. "Kuru" (Dry)
   reuses the pre-existing `NO_LUBRICANT` member; no new member added
   for it.

5. **Tablo 9.4 data is modelled as a combined coefficient, not split.**
   15 records (5 surface conditions x 3 lubrication states) were
   added with `friction_model = combined_or_unspecified`,
   `mu_thread_min/max` and `mu_bearing_min/max` left `None`. The
   source table gives one overall coefficient per condition; splitting
   it into thread/bearing components without a supporting source would
   be inventing data, which docs/12_CLAUDE_CONTEXT.md SS4 forbids.

6. **No coupling to `backend/engineering_core` in this phase.**
   `friction.py`/`torque.py` (existing `mu_thread`/`mu_bearing`
   tightening-torque calculation) are unmodified. Wiring
   library-sourced friction values into that calculation path is
   Faz 2.6.3 scope.

## Consequences

- Faz 2.6.1 onward can populate `mu_thread_min/max`,
  `mu_bearing_min/max`, `k_factor_min/max`, `scatter_percent` and
  `max_temperature_c` on new or existing records once a cited source
  is approved, without any further schema migration.
- If/when independently-sourced-per-field records appear, a nested
  `SourcedFrictionValue` model is the pre-agreed extension path (see
  point 2) -- implementation and documentation must follow this
  decision at that time. A superseding ADR is not required for that
  specific extension, since it was anticipated here, but IS required
  for any change that touches the flat fields already shipped in Faz
  2.6.0.
- Implementation and documentation must follow this decision. Changes
  require a superseding ADR.

## Open data needs (carried to Faz 2.6.1/2.6.2)

1. Approved source(s) for independent `mu_thread`/`mu_bearing`/`K`
   per lubricant (VDI 2230 table, supplier datasheet, internal
   ISO 16047 test report -- to be decided with the product owner).
2. Whether Surface Condition / Coating should become independent
   record types cross-referencing `coating_library.py`, or remain
   free-text fields on `LubricationRecord` (`surface_condition` as
   added in Faz 2.6.0 is a placeholder, not a final data model).
3. Specific regulatory citation for the cadmium `regulatory_warning`
   text (RoHS/ELV clause, customer-specific restriction list, etc.).
