# ADR-0015 — Washer Governance Synchronization and Reconciliation
(Faz 2.8.12 Stage 2)

- Status: Accepted (Stage 2 implemented as of 2026-07-30; production
  endpoint wiring is Stage 3, not yet done — see "Stage boundary"
  below).
- Date: 2026-07-30
- Depends on: `docs/adr/ADR-0014-engineering-governance-architecture.md`
  (canonical governance model, read-only compatibility adapter for
  washer resolution).

## Context

ADR-0014 (Faz 2.8.11) deliberately scoped washer-resolution
integration to a **read-only** compatibility adapter
(`backend/governance/adapters/washer_resolution.py`) and explicitly
deferred any write-path integration to "a future, separately-scoped
phase" (Completion Report §6, §16). Faz 2.8.12 Stage 1 (repository
assessment, approved) confirmed that write integration is now in
scope for washer resolution specifically, and identified a genuine
architectural gap this ADR resolves: the canonical governance
resolution lifecycle (`open -> resolved|rejected|waived`, one hop) is
a strict subset of the washer resolution decision workflow's own
state machine (`open`/`under_review` -> `resolved`/
`accepted_as_is`/`rejected`/blocked, two hops possible, with a
permanently-blocked branch) — see
`backend/library/washer_resolution_decisions.py`'s
`ALLOWED_TRANSITIONS`. No cross-store transaction is possible: the
washer decision ledger and the governance event store are two
independent, file-backed, append-only stores with their own atomic
single-file write guarantees but no shared transaction boundary.

## Decision

### 1. Single authoritative source of truth

`backend/library/data/washer_resolution_decisions.json` (via
`washer_resolution_decisions_store.py`) remains the **sole**
authoritative record of a washer resolution business decision. The
governance event store is a **derived, append-only audit and
lifecycle projection** — it never decides anything, never overwrites
a washer decision, and its absence, corruption, or temporary
unavailability never affects the correctness of a washer decision
that has already been recorded.

`backend/library/data/washer_resolution_ledger.json` (the Faz 2.8.5
source ledger, 76 immutable records) is unaffected by this ADR in any
way — Stage 2 introduces no code path that reads or writes it beyond
what already existed.

### 2. Synchronization pattern: authoritative-write-then-synchronous-best-effort-sync

1. A washer resolution decision is validated and recorded in the
   washer decision store — this is the completed, authoritative
   business transaction. (Stage 3 will wire this step to the
   synchronization call below; Stage 2 implements the synchronization
   function itself, unwired.)
2. Only after that write succeeds, a governance synchronization is
   attempted **synchronously, within the same request execution** —
   no background worker, scheduler, message broker, queue, or daemon
   is introduced anywhere in this phase.
3. Governance synchronization is **best-effort**: it never rolls
   back, invalidates, or alters the already-successful washer
   decision, and any governance-layer failure never changes the
   washer API's success result (Stage 3 concern; the function
   implemented in Stage 2, `sync_washer_decision`, is designed to
   never raise, specifically so a future Stage 3 caller can invoke it
   inline without a `try`/`except` of its own).
4. A **mandatory** (not optional), explicitly-invoked, idempotent
   reconciliation mechanism
   (`backend/governance/adapters/washer_resolution_reconciliation.py`,
   `tools/run_washer_governance_reconciliation.py`) recovers every
   case the synchronous best-effort step could miss: store
   unconfigured, store temporarily unavailable, process termination
   between the two writes, and any pre-existing washer decision
   recorded before this integration existed at all.

### 3. Non-representable washer states

Only the three washer decision statuses the existing Stage 5
read-only adapter already maps with `MappingQuality.EXACT` are ever
synchronized:

| Washer `new_status`   | Governance `ResolutionStatus` |
|---|---|
| `resolved`             | `RESOLVED` |
| `accepted_as_is`       | `WAIVED` |
| `rejected`              | `REJECTED` |

No governance event is ever written for:

- `open` — classified `skipped_open`. This is not a synchronization
  failure; it is the expected, permanent classification for a washer
  decision (or, in the reconciliation scan, a governed record with no
  decision yet) that has not reached a synchronizable state.
- `under_review` — classified `not_representable`. The canonical
  governance resolution lifecycle has no analogous intermediate
  state (see Context); inventing one would violate ADR-0014's closed,
  three-lifecycle-group vocabulary. This decision remains visible via
  the existing Stage 5 read-only adapter's own `PARTIAL` mapping
  quality, unchanged.
- `blocked_authoritative_source` — never reachable as a *decision's*
  `new_status` at all (the washer state machine's `ALLOWED_TRANSITIONS`
  has no transition into it — it is only ever the *source ledger's*
  original status for 5 of the 76 records). This module's
  classification logic therefore never needs to special-case it as a
  decision outcome; it remains visible via the Stage 5 adapter's
  `UNSUPPORTED` mapping quality, unchanged.

Neither state is retried indefinitely, neither is auto-repaired, and
neither is misclassified as a generic `failed` outcome — both have
their own dedicated, deterministic classification.

### 4. Aggregate ownership

The generic governance HTTP write endpoints
(`POST /api/governance/{review,publication,resolution}/...`) must not
become a second, independent way to write a washer resolution
decision. A narrow, additive guard is added at the single choke point
already shared by all nine write endpoints
(`backend.governance.api._run_command`):
`aggregate_type="washer_resolution"` is rejected with `409` (the same
conflict status code and generic-message convention every other
write-rejection in that module already uses — no new response
convention is introduced). This is enforced **only** on the HTTP
surface. Internal, in-process calls into
`backend.governance.service` (the synchronization adapter's own call
path) are unaffected — they are the legitimate, sole way a washer
resolution's governance events are ever written.

`"washer_resolution"` was not used as an `aggregate_type` value by any
existing test or caller before this ADR (verified by repository
search), so this is not a breaking change for any current caller.

### 5. Event identity and global uniqueness

Governance `decision_id`/`idempotency_key` uniqueness is **global**,
not aggregate-scoped — verified directly against
`FileGovernanceEventStore.find_by_decision_id`/
`find_by_idempotency_key`, both of which scan every event in the
store regardless of `aggregate_type`. Consequently:

- The washer decision's own `decision_id` (a server-generated
  `DEC-{uuid4}`) is reused **verbatim** as the governance event's
  `decision_id` — never truncated, transformed, or regenerated. Its
  UUID origin already guarantees global uniqueness.
- The governance idempotency key uses a collision-safe namespace:
  `washer-sync:{original_washer_idempotency_key}` — structurally
  distinct from any governance-native idempotency key and from any
  other future adapter's namespace.
- Before treating a same-key pre-existing event as a legitimate prior
  sync, the synchronization function verifies `aggregate_type`,
  `aggregate_id`, `decision_id`, the mapped canonical status, and the
  two source-identifier metadata fields all match. Any mismatch is
  classified `idempotency_conflict` (a `failed` sub-category), never
  silently treated as a replay, and never auto-repaired.

### 6. Lineage via optional metadata, not a schema change

No required field is added to
`backend.governance.events.GovernanceEvent`. Lineage information is
carried entirely inside that model's existing, already-optional
`metadata: Dict[str, Any]` field: `source_system`,
`source_decision_id`, `source_idempotency_key`, `source_aggregate_id`,
`source_event_timestamp`, `sync_version`, `causation_id`, and
`synchronized_at` (the wall-clock time of the sync attempt itself,
kept separate from `occurred_at`, which always carries the washer
decision's own `decided_at` unchanged). No `correlation_id` is
fabricated — washer resolution decisions carry no correlation
identifier today, so the key is simply omitted rather than populated
with a guessed value.

Optional metadata is chosen over a breaking event-schema change
because: (a) it requires zero changes to `GovernanceEvent`, `store.py`,
or `service.py` — all three remain exactly as Faz 2.8.11 left them;
(b) every existing event (written before this ADR) remains valid
under the unchanged schema; (c) a future second adapter can define its
own metadata shape without any coordination with this one.

### 7. Configured / unconfigured governance-store behaviour

An unconfigured governance store (the default —
`TORQPRO_GOVERNANCE_EVENT_STORE_PATH` unset, matching ADR-0014's own
default) is not an error condition for washer synchronization or
reconciliation. Reconciliation still reads and accurately classifies
every washer decision (`scanned`, `skipped_open`,
`not_representable` are always accurate); only records that would
otherwise be eligible for a write are classified
`governance_store_unconfigured` — never conflated with a `failed`
(I/O or corruption) outcome, and never blocking the tool from running
or producing a complete report.

### 8. Failure and recovery semantics

| Failure mode | Recorded washer decision | Governance projection |
|---|---|---|
| Governance store unconfigured | Unaffected | `governance_store_unconfigured`; corrected by a later reconciliation run once configured |
| Governance store I/O error | Unaffected | `failed` / `store_io_error`, `retry_may_help=True`; corrected by a later reconciliation run |
| Governance store corrupted | Unaffected | `failed` / `store_corruption`, `retry_may_help=False`; requires manual investigation, never auto-repaired |
| Process terminates between washer write and sync attempt | Unaffected (already durably written) | Recovered by reconciliation, which finds it via `list_decisions()` |
| Idempotency-key content mismatch | Unaffected | `failed` / `idempotency_conflict`; never auto-repaired, never silently treated as a replay |

### 9. Why no background infrastructure

A background worker, scheduler, message broker, or daemon would
require new infrastructure, new operational surface area, and a new
failure mode (the worker itself) disproportionate to this phase's
scope. The synchronous-best-effort-plus-mandatory-reconciliation
pattern gives the same eventual-consistency guarantee — every washer
decision that is ever recorded is either synchronized inline or
recoverable by an idempotent, explicitly-invoked reconciliation run —
without introducing anything beyond what Faz 2.8.9's and Faz
2.8.11's own file-backed, single-process architecture already
established.

## Stage boundary (this ADR's own scope)

Implemented in Stage 2:
`backend/governance/ownership.py`,
`backend/governance/adapters/washer_resolution_sync.py`,
`backend/governance/adapters/washer_resolution_reconciliation.py`,
`tools/run_washer_governance_reconciliation.py`, the ownership guard
in `backend/governance/api.py`, and this ADR.

**Not** implemented in Stage 2 (explicitly deferred to Stage 3):
wiring `sync_washer_decision` into
`backend.library.washer_resolution_service.decide_resolution` or the
`POST /api/library/washers/resolutions/{resolution_id}/decide`
endpoint. `backend/app.py` and every washer production module are
unchanged by this ADR.

## Compatibility boundary update

Faz 2.8.11's stated compatibility contract
(`backend/governance/__init__.py`) said "no governance module imports
an existing mechanism except the one Stage 5-approved adapter file."
This ADR explicitly widens that to **two** files:
`adapters/washer_resolution.py` (Stage 5, read-only) and
`adapters/washer_resolution_sync.py` +
`adapters/washer_resolution_reconciliation.py` (Stage 2, write-path,
best-effort). `backend/governance/ownership.py`,
`backend/governance/api.py`, `backend/governance/service.py`, and
`backend/governance/store.py` remain exactly as narrow as before —
none of them imports `backend.library`.

## Phase 2.8.12 Stage 3–5 consolidation note (recorded 2026-07-30)

Stage 3 implemented exactly the write integration this ADR describes
in Sec. "Not implemented in Stage 2" above: `sync_washer_decision_and_
log` wired into `washer_resolution_decide_endpoint`, immediately after
the authoritative washer decision succeeds, via two local imports
(never module-level) inside that one endpoint function. This widened
`backend/app.py`'s governance-import allowlist from one line (the
Stage 4/2.8.11 router mount) to three (the router mount plus these two
sync-call-site imports) — a different direction of coupling
(mechanism → governance) than the one this ADR's "Compatibility
boundary update" section above describes (governance → mechanism);
both directions are now closed, exact, and mechanically enforced by
`tests/governance/test_compatibility.py`.

Stage 4.2 added a fourth mechanism-importing file,
`adapters/joint_revision.py` (read-only, `joint_revisions.status` →
`ReviewStatus` only), governed by its own, separate circular-import
rationale (Stage 4.1 spike) rather than this ADR's washer-specific
reasoning — see
`docs/phases/PHASE_2.8.12_STAGE4_2_JOINT_REVISION_READ_ONLY_ADAPTER.md`.
This ADR's own scope (washer resolution synchronization and
reconciliation) is unaffected by that addition; it is recorded here
only so a reader of this ADR knows the "two files" count above is no
longer the current total (see `backend/governance/__init__.py`'s own
"Current compatibility boundary" docstring section for the up-to-date
count).
