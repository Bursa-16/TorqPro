# Engineering Governance Architecture: Canonical Vocabulary and
Standardization Plan for Review, Approval, Revision and Decision
Mechanisms (Faz 2.8.11)

- Status: Accepted and implemented (Stages 1–5 complete as of
  2026-07-30; see `docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md`
  for the full implementation report). This document itself is the
  Stage 1 canonical model; it is left unmodified below except for
  this status line and the "Future-stage plan" section, which now
  records what was actually delivered in Stages 2–5.
- Date: 2026-07-30

## Context

By Faz 2.8.10 the codebase had independently grown **three** working,
production-used governance mechanisms, plus one generic event log,
each solving a "who decided what, when, and is it final" problem for
a different domain object, with no shared vocabulary or shared code:

1. **Production Validation workflow** (`backend/production_validation/`,
   Faz 2.5A, `docs/adr/ADR_2.5A_JOINT_AND_CALCULATION_REVISION_LINKAGE.md`) —
   a `ValidationStudy.status` state machine (`STUDY_TRANSITIONS` in
   `backend/production_validation/enums.py`): `draft -> data_collection
   -> completed -> under_review -> approved|rejected -> archived`,
   with `approved_by`/`approved_at` columns and a `LockedError` guard
   once `approved`.
2. **Legacy calculation revision workflow** (`backend/app.py`,
   `calculation_revisions` table, pre-dating the modular
   `backend/library`/`backend/production_validation`/`backend/joints`
   split) — `draft -> review -> approved|rejected`, with
   `reviewed_by`/`reviewed_at`/`review_note`, `change_reason`,
   `is_locked`, and dedicated `/submit`, `/review`, `/approve`,
   `/reject` endpoints.
3. **Joint revision lifecycle** (`backend/joints/schema.py`,
   `docs/adr/ADR-0003-joint-revision-root.md`) — `JOINT_STATUSES =
   (draft, active, superseded, archived)`, keyed by `revision_no` and
   `current_revision_id`, treating the joint revision (not the bolt
   record) as the immutable engineering aggregate root that
   calculations and approvals attach to.
4. **Washer Resolution Decision Workflow** (Faz 2.8.9,
   `backend/library/washer_resolution_service.py`,
   `docs/adr/ADR-0013-washer-resolution-decision-workflow.md`) — an
   append-only decision ledger
   (`backend/library/data/washer_resolution_decisions.json`) layered
   over an immutable source ledger via a computed `effective_status`,
   a closed transition table with no reopening of terminal decisions,
   and an idempotency-key-first decision API.
5. A generic **`audit_log` table** (`backend/app.py`: `user_id,
   action, detail, request_id, created_at`) — a flat event log with
   no decision/revision model attached to it.

The Faz 2.8.11 task brief originally asked for a new "Engineering
Decision Audit & Approval Workflow." A repository analysis performed
before any code was written (branch `main` at `acb6f96`, working tree
clean) found no phase 2.8.11 work existed yet, but also found that
building a naive fifth mechanism would fragment governance further
rather than fix anything: `status`, `approved_by/at`,
`reviewed_by/at`, and `superseded` already carry three subtly
different meanings across the modules above. The task brief was
therefore revised, before Stage 1 began, to make Faz 2.8.11 a
**standardization phase**: document and compare the four existing
mechanisms, define one canonical vocabulary and transition model, and
explicitly defer any shared runtime implementation to a later stage.

This ADR is that canonical model. It changes no code, no table, no
JSON ledger, no API endpoint, no enum, and no transition graph. Every
mechanism inventoried above continues to operate exactly as before.

## Inventory of the existing mechanisms

| # | Mechanism | Domain object | Status field location | Terminal states | Actor/timestamp fields | Audit model |
|---|---|---|---|---|---|---|
| 1 | Production Validation | `ValidationStudy` | `production_validation` SQLite table, `status` column | `approved`, `archived` (both close via `LockedError`/no outgoing transition) | `approved_by`, `approved_at` | Mutable row; no append-only history table |
| 2 | Legacy calculation revision | `calculation_revisions` row | `backend/app.py` SQLite table, `status` column | `approved` (`is_locked=1`) | `created_by`, `reviewed_by`, `reviewed_at` (used for both approve and reject) | Mutable row; one row per revision number, no separate decision ledger |
| 3 | Joint revision lifecycle | `joints` / `joint_revisions` rows | `backend/joints/schema.py` SQLite tables, `status` column | `superseded`, `archived` | none dedicated (relies on `created_at`/revision numbering) | Mutable row per revision; supersession expressed by a *new* revision row plus `current_revision_id` pointer |
| 4 | Washer Resolution Decision Workflow | washer library record (`resolution_id`) | Two JSON ledgers: immutable source (`resolution_status`) + append-only decisions (`new_status`), reconciled by `effective_status()` | `resolved`, `accepted_as_is`, `rejected` (no outgoing transition); `blocked_authoritative_source` (no transition at all) | `resolved_by`, `decided_at` (decision-ledger fields) | True append-only ledger; source never mutated |
| 5 | Generic audit log | any (`action` free text) | n/a (event log, not a state machine) | n/a | `user_id`, `created_at` | Append-only, but carries no `decision_id`/`revision_no`/before-after state |

## Status vocabulary comparison

| Concept | Mechanism 1 | Mechanism 2 | Mechanism 3 | Mechanism 4 |
|---|---|---|---|---|
| Not yet ready | `draft` | `draft` | `draft` | `open` |
| Awaiting human judgement | `under_review` | `review` | *(none — joints don't have a review step; approval happens at the calculation/study layer)* | `under_review` |
| Confirmed / finalized positively | `approved` | `approved` | `active` | `resolved` / `accepted_as_is` |
| Confirmed / finalized negatively | `rejected` | `rejected` | *(none)* | `rejected` |
| Replaced by a newer version | *(none — a rejected study can re-enter `data_collection`; there is no "this study was superseded by that study" link)* | *(none — a new revision number is created; no field says "revision 2 supersedes revision 1")* | `superseded` | *(none — decisions are terminal, not superseded by later decisions)* |
| Retired / no longer relevant | `archived` | *(none)* | `archived` | *(none)* |
| Explicitly out of scope / cannot be decided | *(none)* | *(none)* | *(none)* | `blocked_authoritative_source` (mechanism 4 only) |

Three same-sounding words already mean three different things:

- **`approved`** in mechanism 1 means "this validation study's
  measured data is accepted as evidence"; in mechanism 2 it means
  "this calculation revision is locked and becomes the record of
  truth." Neither means "this is now the active version" the way
  mechanism 3's `active` does.
- **`superseded`** exists only in mechanism 3 and describes a
  *revision lineage* relationship (revision 2 supersedes revision 1),
  not a *decision* being overturned. Mechanisms 1, 2 and 4 have no
  equivalent — a rejected or terminal record in those mechanisms is
  not "replaced," it is simply final or resubmitted as a new entity.
- **`under_review`** (mechanism 1) and **`review`** (mechanism 2) are
  the same concept with different spellings; a canonical vocabulary
  must pick one.

## Semantic differences: review, approval, activation, resolution, revision, supersession, archival

These seven words are used loosely and interchangeably across the
codebase's docstrings and comments. Stage 1 defines them precisely so
later stages can use them without ambiguity:

- **Review**: the act of a qualified person examining a draft
  artifact (a study, a calculation revision, a decision proposal)
  before it is finalized. Review does not itself change engineering
  truth; it is a gate. Maps to mechanisms 1 and 2's `under_review`/
  `review`.
- **Approval**: a specific, positive review outcome that makes an
  artifact authoritative and — in every existing mechanism —
  triggers an immutability guarantee (`LockedError`, `is_locked=1`).
  Approval is a terminal, one-way transition in mechanisms 1 and 2.
- **Activation**: making one revision of a *versioned* artifact the
  one currently in effect, distinct from approval. Only mechanism 3
  has this concept (`active`); a joint revision can become `active`
  without an explicit "approval" step recorded elsewhere in that
  table. Activation is about *which version counts right now*, not
  *whether the content was judged correct*.
- **Resolution**: closing an open question or flagged issue about an
  existing record (mechanism 4's `resolved`/`accepted_as_is`/
  `rejected`). Resolution answers "what do we do about this specific
  flagged problem," not "is this whole artifact correct." It operates
  on a narrower object (one flagged issue) than review/approval
  (a whole study or calculation).
- **Revision**: the creation of a new, numbered version of an
  artifact that preserves the old version unchanged (mechanisms 2 and
  3 both number revisions; mechanism 1 does not — a `ValidationStudy`
  has no revision concept, only a single mutable lifecycle).
- **Supersession**: an explicit, recorded relationship stating that
  one revision has been replaced by a later one. Currently only
  mechanism 3 has a *state value* for it (`superseded`); no mechanism
  anywhere stores a `supersedes_id`/`superseded_by_id` pointer — the
  relationship is implied by revision numbering and
  `current_revision_id`, never recorded as an explicit edge.
- **Archival**: retiring an artifact from active use without deleting
  it or asserting anything about its correctness. Present in
  mechanisms 1 and 3, absent from mechanisms 2 and 4.

## Fragmentation risks

1. **Silent vocabulary collision.** A future developer adding
   `approved_by` to a fifth module would reasonably assume it means
   what it means in mechanism 1 or 2 — but nothing enforces that; nothing
   currently prevents a sixth, seventh, or eighth bespoke status
   field from being invented with no reference to the other four.
2. **No supersession record anywhere except joints.** If a Production
   Validation study is superseded by a re-run, or a washer decision
   needs correcting after new evidence arrives, there is no existing
   pattern to reuse — each would likely reinvent supersession
   differently (mechanism 3's enum value vs. a new pointer field vs.
   a new decision-ledger entry), producing a *sixth* variant.
3. **Mutable vs. append-only audit inconsistency.** Mechanisms 1–3
   overwrite their own status column in place (the history of *how*
   a study became `approved` — who reviewed it first, what was
   rejected before resubmission — is not preserved beyond
   `reviewed_at`/`approved_at` single timestamps). Mechanism 4 is the
   only one with a true append-only decision history. A future
   generic layer copying mechanisms 1–3's pattern would lose
   auditability that mechanism 4 already proved is achievable and
   valuable; copying mechanism 4's pattern into 1–3 would be a
   breaking migration this ADR explicitly does not authorize.
4. **Idempotency exists in exactly one place.** Only mechanism 4 has
   an idempotency-key contract. Mechanisms 1–3's endpoints do not
   promise safe retry behavior; a caller retrying a network failure
   against `/calculations/{id}/approve` could double-process (the
   existing code happens to be safe here because SQL `UPDATE ...
   WHERE status='review'` is naturally idempotent-ish, but this is
   incidental, not a documented contract).
5. **Terminology drift into documentation and UI strings.** Because
   `review`/`under_review`, `approved`/`active`, and `archived`/
   `superseded` are already inconsistent in code, new bilingual
   (TR/EN) UI copy for any future governance-facing screen risks
   encoding the same inconsistency into user-facing language, which
   is far more expensive to fix retroactively (translation-key churn)
   than fixing internal field names.

## Decision

Adopt a three-lifecycle canonical model, a canonical field-name set,
and a compatibility/migration strategy, all **documentation-only** in
this stage. No existing runtime artifact is touched.

### Canonical vocabulary: three separate lifecycles, never merged into one status field

A single overloaded `status` enum trying to express review state,
version state, and issue-resolution state simultaneously is the root
cause of the ambiguities above (`approved` meaning three different
things). The canonical model instead defines three **independent**
lifecycle groups. A given domain object may participate in one, two,
or all three simultaneously, each tracked by its own field:

**A. Review lifecycle** (`review_status`) — governs whether an
artifact's content has been checked and judged correct by a
qualified person:

```
draft -> under_review -> approved
                       -> rejected
```

- `draft`: not yet submitted for review.
- `under_review`: submitted, awaiting a reviewer's decision.
- `approved` / `rejected`: terminal. `approved` implies the
  artifact's content becomes immutable (mirrors every existing
  mechanism's `LockedError`/`is_locked` behavior).
- Canonical name choice: `under_review` (mechanism 1's spelling)
  wins over mechanism 2's `review`, because it cannot be confused
  with the *lifecycle's own name* ("review lifecycle" vs. a status
  literally called `review`) and matches the SQL-safe, self-
  describing convention already used for `data_collection`,
  `blocked_authoritative_source`, etc.

**B. Publication/revision lifecycle** (`publication_status`) —
governs which numbered revision of a versioned artifact is currently
in effect, independent of whether that revision was ever formally
reviewed:

```
draft -> active -> superseded
              \--> archived
```

- `draft`: a new revision exists but is not yet the effective one.
- `active`: the current, effective revision (at most one `active`
  revision per artifact lineage at a time).
- `superseded`: replaced by a later `active` revision; permanent,
  paired with an explicit `supersedes_id`/`superseded_by_id` pointer
  (see canonical fields below) rather than the implicit
  revision-numbering-only relationship mechanism 3 currently has.
- `archived`: retired from active use without being replaced by a
  newer revision (e.g. the whole artifact is discontinued).
- Canonical name choice: reuses mechanism 3's vocabulary unchanged
  (`active`/`superseded`/`archived`), since it is the only mechanism
  that already models a true version lineage — the other three
  mechanisms don't need this lifecycle group at all unless they grow
  a genuine multi-revision concept.

**C. Resolution lifecycle** (`resolution_status`) — governs whether a
specific flagged issue or open question about an artifact has been
closed, independent of the artifact's own review or publication
state:

```
open -> resolved
     -> rejected
     -> waived
```

- `open`: issue flagged, not yet decided.
- `resolved`: issue closed with a positive/corrective outcome.
- `rejected`: issue closed as invalid/not-applicable.
- `waived`: issue closed as accepted-as-is without correction —
  canonical name for what mechanism 4 currently calls
  `accepted_as_is`; `waived` is shorter, matches common QA/audit
  terminology, and avoids the word "accepted" colliding with
  lifecycle A's `approved`.
- Mechanism 4's `blocked_authoritative_source` is **not** folded into
  this three-state model; a resolution lifecycle needs a documented
  fourth "cannot be decided through this workflow" outcome, and Stage
  1 explicitly preserves that as a mechanism-4-specific extension
  rather than forcing it into the canonical vocabulary — see
  "Compatibility strategy" below.

### Canonical transition principles

1. **One lifecycle group, one field, one transition table.** No
   canonical field may encode more than one of the three lifecycle
   groups. A domain object needing two groups (e.g. a joint revision
   that is both reviewed *and* published) gets two independent
   fields, each with its own transition table, not one merged enum.
2. **Fail-closed transition tables.** Every canonical transition table
   must be an explicit adjacency map (mechanism 4's
   `ALLOWED_TRANSITIONS` pattern), not an implicit "anything not
   forbidden is allowed" check. Any transition not listed is
   rejected.
3. **Terminal states have no outgoing transition in the base model.**
   `approved`, `rejected` (lifecycle A), `superseded`, `archived`
   (lifecycle B), `resolved`, `rejected`, `waived` (lifecycle C) are
   all terminal. Reopening a terminal state is out of scope for the
   base canonical model, exactly as mechanism 4 already established
   for its own terminal states — a distinct, explicitly authorized
   reopen workflow is a future-stage concern, not a silent transition.
4. **Supersession is an edge, not just a state.** Unlike the current
   joint-revision implementation (state value only), the canonical
   model requires supersession to be recorded as an explicit pointer
   pair (`supersedes_id` / `superseded_by_id`) in addition to the
   `superseded` state value, so lineage can be queried without
   re-deriving it from revision numbers.

### Audit and immutability principles

1. **Approved/terminal records are immutable engineering data.**
   Once `review_status` reaches `approved`, no field the review
   covered may change in place — this restates, and does not modify,
   the existing guarantee already enforced by mechanisms 1
   (`LockedError`) and 2 (`is_locked`).
2. **Prefer append-only history over overwritten status columns.**
   Mechanism 4's two-ledger (immutable source + append-only decision
   overlay) pattern is the canonical audit model for any *future*
   shared implementation. This is a forward-looking principle for
   Stage 3+, not a retroactive requirement — mechanisms 1–3's
   existing mutable-row pattern is unchanged and remains compliant
   with this ADR by virtue of not being touched.
3. **A decision must be reconstructable from its own record.** Every
   canonical decision record must carry enough fields (actor,
   timestamp, previous state, new state, reason/comment) to be
   understood without consulting application logs, mirroring
   mechanism 4's `WasherResolutionDecision` shape.
4. **A canonical `decision_id` is the join key**, not a composite of
   other fields, so a decision can be referenced, audited, and
   idempotency-checked independent of which artifact or lifecycle
   group it belongs to.

### Actor and timestamp requirements

Every lifecycle transition must record who performed it and when,
using the canonical field names below. Minimum required fields per
transition (a transition missing its required actor/timestamp pair is
invalid and must be rejected by any future implementation):

| Transition | Required actor field | Required timestamp field | Optional context field |
|---|---|---|---|
| `draft -> under_review` (submit) | `submitted_by` | `submitted_at` | `change_reason` |
| `under_review -> approved` | `approved_by` | `approved_at` | `review_comment` |
| `under_review -> rejected` | `rejected_by` | `rejected_at` | `review_comment` |
| `draft -> active` / `active -> active` (new revision activated) | `submitted_by` (of the new revision) | `created_at` | `revision_no`, `supersedes_id` |
| `active -> superseded` | `submitted_by` (of the *superseding* revision, recorded on the superseded record) | `created_at` (of the superseding record) | `superseded_by_id` |
| `* -> archived` | whichever actor field applies to the lifecycle in use | `created_at` (of the archival record/event) | `change_reason` |
| `open -> resolved/rejected/waived` | `reviewed_by` (mechanism 4 currently calls this `resolved_by`; canonical name unifies with lifecycle A's reviewer terminology) | `reviewed_at` | `review_comment` |

`reviewed_by`/`reviewed_at` are defined as generic "a qualified
person looked at this and recorded an outcome" fields usable by both
lifecycle A and lifecycle C, distinct from `approved_by`/`approved_at`
which is specific to a *positive* lifecycle-A outcome.

### Idempotency requirements

Mechanism 4's idempotency-key-first pattern is adopted as the
canonical requirement for any future shared implementation:

1. Every state-changing governance request must carry a caller-
   supplied `idempotency_key`.
2. The idempotency check happens **before** transition validation: a
   retried request identical to a previously accepted one returns the
   original decision unchanged; a reused key with different content
   is rejected as a conflict. This ordering is deliberate (a
   legitimate retry must not fail transition validation just because
   the first attempt already advanced the state) and is copied
   verbatim from ADR-0013 §4's justification.
3. `idempotency_key` is scoped per `decision_id`-producing endpoint,
   not globally — the same key value used against two different
   artifacts is not a conflict.

### Revision lineage principles

1. A revision lineage is a chain of numbered records
   (`revision_no`, monotonically increasing per artifact) where
   exactly one record is `active` at any time.
2. `supersedes_id` and `superseded_by_id` are inverse pointers set
   together, in the same transaction that activates the new revision
   and marks the old one `superseded` — never set independently, to
   avoid a dangling half-updated pair.
3. `current_revision_id`-style pointers (mechanism 3's existing
   pattern) remain a valid convenience projection of "which record is
   currently active," computable from the lineage; the canonical
   model does not require removing such pointers, only that they stay
   derivable from — not a second source of truth alongside — the
   `active`/`superseded` state values.

### Canonical field names

| Field | Meaning | Used by lifecycle(s) |
|---|---|---|
| `submitted_by` | actor who moved a record out of `draft` | A, B |
| `submitted_at` | timestamp of submission | A, B |
| `reviewed_by` | actor who examined and recorded any review/resolution outcome | A, C |
| `reviewed_at` | timestamp of that examination | A, C |
| `approved_by` | actor who recorded a positive lifecycle-A outcome | A |
| `approved_at` | timestamp of approval | A |
| `rejected_by` | actor who recorded a negative outcome | A, C |
| `rejected_at` | timestamp of rejection | A, C |
| `review_comment` | free-text rationale attached to a review/resolution outcome | A, C |
| `change_reason` | free-text rationale attached to a submission (why a new draft/revision was created) | A, B |
| `revision_no` | monotonically increasing per-artifact version number | B |
| `supersedes_id` | pointer from a new revision to the one it replaces | B |
| `superseded_by_id` | inverse pointer, set on the replaced revision | B |
| `decision_id` | canonical identifier of one governance decision record, the join key for audit/idempotency | A, B, C |
| `idempotency_key` | caller-supplied key preventing duplicate processing of a retried request | A, B, C |
| `created_at` | creation timestamp of the record itself (distinct from any transition timestamp) | A, B, C |

Field names deliberately reuse mechanism 1's `approved_by`/
`approved_at` spelling (rather than inventing new ones) because it is
already the most-used pair across two of the four mechanisms and
requires no relearning.

## Compatibility strategy

- **No existing table, JSON ledger, API endpoint, enum, or transition
  graph is renamed, dropped, or altered in Stage 1 or by adopting this
  ADR.** Mechanisms 1–4 keep their current field names
  (`resolved_by`/`decided_at` in mechanism 4, `reviewed_by`/
  `reviewed_at` reused for both approve/reject in mechanism 2, etc.)
  indefinitely unless a future, separately-authorized migration ADR
  says otherwise.
- **Mechanism 4's `blocked_authoritative_source` special case is not
  forced into the canonical resolution lifecycle.** It remains a
  mechanism-4-specific extension state with no outgoing transition,
  exactly as ADR-0013 defined it. A future canonical implementation
  that wants an equivalent "cannot be decided through this workflow"
  outcome for other resolution-lifecycle consumers must define its
  own named state for that consumer rather than assuming
  `blocked_authoritative_source` generalizes verbatim.
- **This ADR is a naming and modeling reference, not a validation
  library.** Existing code is not required to import anything from a
  canonical module because no canonical module exists yet (Stage 2+).
- **New governance-facing work started after this ADR** (any new
  domain object needing review, approval, publication, or resolution
  semantics) should use the canonical vocabulary and field names from
  the start, even before a shared implementation exists in Stage 2+,
  the same way Faz 2.8.8 adopted the `(code, tr, en)` string-pair
  convention before any shared i18n tooling existed for it.

## Migration strategy

Migration of mechanisms 1–4 onto a shared implementation is
explicitly **out of scope through at least Stage 4** and is not
authorized by this ADR. When it is eventually proposed (Stage 5 or
later, per a future ADR), the following order is recommended based on
the risk/complexity of each mechanism's existing data:

1. **Mechanism 4 (washer decisions)** first — it is already
   structurally closest to the canonical model (append-only ledger,
   idempotency, closed transitions); migration would mostly be a
   field-rename/wrapper exercise.
2. **Mechanism 1 (production validation)** second — clear state
   machine already exists; migration mainly needs backfilling
   `submitted_by`/`submitted_at` (not currently tracked) and
   converting the mutable-row audit trail into an append-only
   overlay without breaking existing `LockedError` behavior.
3. **Mechanism 3 (joint revisions)** third — requires adding the new
   `supersedes_id`/`superseded_by_id` pointer pair to existing rows
   (backfill from revision-number order) before any code can rely on
   the pointer instead of implicit numbering.
4. **Mechanism 2 (legacy calculation revisions)** last — it lives in
   the pre-modular `backend/app.py` monolith; migrating it likely
   coincides with (or depends on) a broader decision about whether
   that module is refactored into `backend/library`/
   `backend/production_validation`-style packages at all, which is a
   separate, larger architectural question outside this ADR's scope.

No migration step may be taken without its own dedicated ADR, its own
test coverage, and its own clean-clone verification, per the
project's standing delivery protocol (`docs/12_CLAUDE_CONTEXT.md`,
`docs/adr/ADR-0008-immutable-calculations.md`).

## Rejected alternatives

1. **Build a fifth, brand-new generic approval workflow immediately
   (the original Faz 2.8.11 task-brief framing).** Rejected: this was
   the repository analysis's core finding — a fifth bespoke mechanism
   would add another dialect to an already-fragmented vocabulary
   rather than reduce fragmentation, and would very likely duplicate
   fields (`status`, `approved_by`) that already exist elsewhere
   under slightly different semantics.
2. **Force all four mechanisms to share one overloaded `status`
   enum covering review, publication, and resolution simultaneously.**
   Rejected: this is exactly the ambiguity already causing
   `approved` to mean three different things across mechanisms 1, 2,
   and 3. Splitting into three independent lifecycle groups (Decision,
   §"Canonical vocabulary") was chosen specifically to prevent this.
3. **Immediately migrate mechanisms 1–4 onto the canonical field
   names as part of this stage.** Rejected: the task brief's Stage 1
   scope and the project's standing rules (no existing table/ledger/
   endpoint/enum/transition graph may be modified, no data migration,
   no field renames) both explicitly forbid this. Migration is
   deferred to a future, separately-authorized stage per "Migration
   strategy" above.
4. **Treat `blocked_authoritative_source` as a fourth canonical
   resolution-lifecycle state (`open -> resolved -> rejected ->
   waived -> blocked`).** Rejected: promoting a mechanism-4-specific
   escape hatch into the shared vocabulary would make the canonical
   model implicitly aware of washer-specific standards ambiguity
   (ISO 7093 vs ISO 7093-1) that has nothing to do with, say, a
   future production-validation resolution use case. Kept as a
   documented, named extension point instead (see "Compatibility
   strategy").
5. **Do nothing / leave the task-brief's original scope unchanged.**
   Rejected: the repository analysis was performed specifically to
   avoid this outcome; proceeding with the original scope would have
   knowingly introduced the fragmentation risk this ADR exists to
   prevent.

## Consequences

- No runtime behavior changes. Mechanisms 1–4 and the generic
  `audit_log` table continue operating exactly as before this ADR.
- Future governance-facing phases have a single, precise vocabulary
  and field-name reference to design against, reducing the chance of
  a fifth bespoke dialect emerging.
- The three-lifecycle-group split (review / publication / resolution)
  is now the project's stated position on why `approved`, `active`,
  and `resolved` must never again be merged into a single status
  field — future code review can cite this ADR directly.
- Migration of any existing mechanism onto the canonical field names
  remains unauthorized until a future, dedicated migration ADR is
  written and accepted; this ADR alone does not permit touching
  mechanisms 1–4's existing schemas.
- The `blocked_authoritative_source`-equivalent "cannot decide through
  this workflow" case is explicitly left as a per-consumer extension
  point rather than a canonical state, which future stages must
  remember to design for individually rather than assuming a single
  shared enum value covers it.
- **Technical debt, carried forward at Stage 1, resolved at Stage 5:**
  a pre-existing, unrelated defect in
  `tests/js/run_material_intelligence_tests.js` (Faz 2.8.8) — its
  asynchronous test scenarios were not awaited before the harness
  process exited, so their assertions never actually ran even though
  the harness reported a clean result — was first documented in
  ADR-0013's "Consequences" section and `docs/11_PRODUCT_BACKLOG.md`
  §12B. It did not block Stage 1's documentation validation and was
  not touched at that point; it was confirmed and fixed at Stage 5
  (narrowly scoped, test-file-only, no production code touched, with
  a regression-guard test and a deliberate-failure proof) — see
  `docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md` Sec. 5.
- **Stage 1 does not claim a shared governance workflow
  implementation exists.** No code was written. `backend/`,
  `frontend/`, and `tests/` are unchanged by this phase; only `docs/`
  files were added or edited.

## Future-stage plan

- **Stage 2 — Shared governance contracts and typed domain models.**
  Define Pydantic models (`extra="forbid"`, matching the project's
  existing convention) for the three canonical lifecycle groups and
  the canonical field set, as a new, additive
  `backend/governance/` (name to be confirmed in the Stage 2 ADR)
  package. No existing mechanism imports or depends on it yet.
- **Stage 3 — Append-only governance event store and service layer.**
  Implement the append-only decision-ledger pattern (generalizing
  ADR-0013's mechanism-4 design) as a reusable service, with the
  closed transition tables, idempotency-key handling, and
  actor/timestamp enforcement defined in this ADR.
- **Stage 4 — Additive API and TR/EN governance workspace.** New,
  read/write governance endpoints and a frontend workspace, built
  additively (new routes only, nothing existing renamed or removed),
  with full TR/EN parity from the start (following the Faz 2.6.6/
  2.8.8/2.8.9 precedent of `(code, tr, en)` string pairs from day
  one).
- **Stage 5 — Compatibility adapters, tests and completion report.**
  Optional, explicitly-authorized adapters that let mechanisms 1–4
  *read through* the canonical model without migrating their
  underlying storage, full test coverage, and a completion report
  following the project's standard delivery protocol (branch → full
  suite pass → patch + bundle + SHA256SUMS verified on an independent
  clean clone).

**Delivered vs. deferred (recorded 2026-07-30, after Stage 5):**
Stages 2–4 were delivered exactly as scoped above. Stage 5 was
delivered narrowly: only the washer resolution adapter was built
(read-only, all 76 real records validated, 71 exact + 5 explicitly
unsupported mappings); Production Validation, the legacy calculation-
revision workflow, and joints were deliberately not adapted in this
stage, since each requires a live database connection this package's
"no new dependency cycle" constraint does not yet have a settled
pattern for — see
`docs/phases/PHASE_2.8.11_COMPLETION_REPORT_TR_EN.md` Sec. 5 for the
full reasoning and the follow-up scope this leaves for a future,
separately-approved phase. No mechanism's runtime data was migrated;
no field was renamed; every one of ADR-0014's compatibility
guarantees above held throughout.

Each stage required its own scoping approval before work began, per
the project's standing "plan before execution" rule; this ADR
authorized the *model*, and each stage's own scoping message
authorized that stage's implementation.
