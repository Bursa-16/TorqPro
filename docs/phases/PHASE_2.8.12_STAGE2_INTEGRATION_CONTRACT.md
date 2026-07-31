# Phase 2.8.12 Stage 2 — Washer Resolution Integration Contract

- Status: **Stage 2 complete** (2026-07-30). Phase 2.8.12 as a whole
  is **not** complete — Stages 3–5 remain (see "Stage boundary"
  below). Do not read this document as a phase completion report.
- ADR: `docs/adr/ADR-0015-washer-resolution-governance-integration.md`
- Depends on: `docs/adr/ADR-0014-engineering-governance-architecture.md`

## 1. Approved scope

Washer resolution only. Production Validation, legacy calculation
revisions, and joint revisions are assessment-only (Stage 4, not
started). Material Intelligence, Fastener Assembly Intelligence,
Recommendation logic, report modules, the Quality Harness, and future
VDI 2230 extensions are explicitly out of scope — none has an
existing decision/approval workflow the canonical governance model
represents; no such workflow was invented for them.

## 2. Source-of-truth hierarchy

1. `backend/library/data/washer_resolution_ledger.json` — immutable
   reference population (76 records). Unaffected by this phase.
2. `backend/library/data/washer_resolution_decisions.json` (via
   `washer_resolution_decisions_store.py`) — append-only, **sole
   authoritative source** for washer business decisions and
   effective washer status. Unaffected by Stage 2 (no Stage 2 code
   path writes to it).
3. Governance event store — append-only, derived audit and lifecycle
   projection. **Never authoritative** for washer business decisions.
   Never initiates or overwrites a washer decision.

## 3. Ownership boundary

`aggregate_type="washer_resolution"` is rejected with `409` by all
nine generic governance HTTP write endpoints
(`backend/governance/api.py`'s `_run_command`, the single choke
point shared by all nine). Read endpoints (history/status) remain
available for any aggregate_type. Internal, in-process calls into
`backend.governance.service` remain the sole legitimate way a washer
resolution's governance events are written — the ownership guard is
an HTTP-surface-only protection
(`backend/governance/ownership.py`, no `backend.library` import).

## 4. Synchronization outcome model

`backend.governance.adapters.washer_resolution_sync.SyncOutcome`,
returned as a frozen `SyncResult` (never raises):

| Outcome | Meaning | `event_written` |
|---|---|---|
| `synchronized` | New governance event written | `True` |
| `already_synchronized` | Matching prior sync found, verified consistent | `False` |
| `would_synchronize` | Dry-run: eligible, not yet synced | `False` |
| `skipped_open` | Washer decision status is `open` | `False` |
| `not_representable` | `under_review` (or any future non-terminal status) | `False` |
| `governance_store_unconfigured` | Store not configured (`store=None`) | `False` |
| `failed` | See `safe_error_category` below | `False` |

`SyncResult` fields: `resolution_id`, `washer_decision_id`,
`governance_aggregate_id`, `outcome`, `event_written`,
`retry_may_help`, `safe_error_category`, `safe_message`, `metadata`.
Never contains a filesystem path, environment-variable value,
traceback, credential, or raw internal exception text (tested
directly).

`failed` sub-categories (`safe_error_category`): `idempotency_conflict`
(`retry_may_help=False`, never auto-repaired), `decision_id_collision`
(`retry_may_help=False`), `invalid_transition`
(`retry_may_help=False`, defensive — unreachable given washer's own
terminal-state enforcement), `missing_required_field`
(`retry_may_help=False`), `store_corruption`
(`retry_may_help=False`, needs manual investigation),
`store_io_error` (`retry_may_help=True`, transient),
`unexpected_error` (`retry_may_help=False`, last-resort classification).

## 5. Terminal reconciliation outcomes and counter invariant

`backend.governance.adapters.washer_resolution_reconciliation.reconcile()`
returns a `ReconciliationReport` with counters: `scanned`, `eligible`
(informational, overlapping — see below), `synchronized`,
`already_synchronized`, `would_synchronize`, `not_representable`,
`skipped_open`, `failed`, `governance_store_unconfigured`.

**Invariant (tested):**

```
scanned == synchronized + already_synchronized + would_synchronize
           + not_representable + skipped_open + failed
           + governance_store_unconfigured
```

`eligible` is the sum of every terminal outcome *except*
`not_representable`/`skipped_open` — documented as informational, not
part of the invariant sum, since it deliberately overlaps with
`synchronized`/`already_synchronized`/`would_synchronize`/`failed`/
`governance_store_unconfigured`.

Every scanned record has exactly one terminal outcome — enforced by
`sync_washer_decision`'s own control flow (each branch returns
exactly once) and verified by
`ReconciliationReport.terminal_outcome_sum()`.

## 6. Global decision-ID and idempotency uniqueness

Verified directly against `FileGovernanceEventStore.find_by_decision_id`
/ `find_by_idempotency_key` (`store.py:238-253`): both scan every
event in the store regardless of `aggregate_type` — **global**, not
aggregate-scoped.

- Washer `decision_id` (`DEC-{uuid4}`) is reused verbatim as the
  governance event's `decision_id` — never transformed. UUID origin
  already guarantees global uniqueness.
- Governance idempotency key: `washer-sync:{washer_idempotency_key}`
  — a namespace structurally distinct from any governance-native key
  or any other future adapter's namespace.
- Before treating a same-key pre-existing event as a legitimate prior
  sync, `_existing_event_matches` verifies `aggregate_type`,
  `aggregate_id`, `decision_id`, mapped canonical status, and both
  source-identifier metadata fields (`source_decision_id`,
  `source_idempotency_key`). Any mismatch → `idempotency_conflict`,
  never a silent replay, never auto-repaired. Tested explicitly
  against a foreign event belonging to an unrelated `aggregate_type`
  reusing the same key.

## 7. Non-representable state handling

Only `resolved`→`RESOLVED`, `accepted_as_is`→`WAIVED`,
`rejected`→`REJECTED` are ever synchronized — derived from the
existing Stage 5 adapter's `_STATUS_MAP` (single canonical mapping
source; `_SYNCABLE_STATUS_MAP` is a filtered view of it, not a
second, independently-defined table — enforced by
`test_sync_adapter_never_defines_its_own_status_mapping_table`).
`open` → `skipped_open`. `under_review` → `not_representable`.
`blocked_authoritative_source` is never reachable as a *decision's*
`new_status` at all (washer's own state machine has no transition
into it). Neither non-representable state is retried indefinitely,
neither is auto-repaired, neither produces a governance event, and
neither is misclassified as a generic `failed`. Both remain visible
via the existing, unmodified Stage 5 read-only adapter's own
`PARTIAL`/`UNSUPPORTED` mapping quality.

## 8. Configured / unconfigured store behaviour

`store=None` (unconfigured) is not an error. `sync_washer_decision`
still classifies `open`/`under_review` correctly before ever checking
whether a store is configured; only an otherwise-eligible record is
classified `governance_store_unconfigured`. `reconcile()` inherits
this behaviour record-by-record — a full, accurate report is produced
even with no governance store configured at all (the default
deployment state today).

## 9. Dry-run semantics

`dry_run=True` performs every read-only classification step,
including the idempotency-consistency check
(`find_by_idempotency_key` + `_existing_event_matches`), but never
calls a governance write command. An eligible, not-yet-synced record
is reported `would_synchronize` instead of `synchronized`. A
would-be conflict is still reported as `failed`/`idempotency_conflict`
in dry-run (tested) — dry-run never hides a conflict it can already
detect read-only. Neither the governance store nor any washer file is
ever written in dry-run mode (tested, including a second dry-run pass
after a real run).

## 10. Safe-error policy

`SyncResult.safe_error_category`/`safe_message` are drawn from a
closed, hand-written vocabulary — never `str(exc)` on an arbitrary
exception. No filesystem path, environment-variable value, traceback,
or credential ever appears in a `SyncResult` or in the CLI's JSON
output (tested against a store path containing a deliberately
distinctive substring).

## 11. Stage 3 integration boundary

Stage 2 implements `sync_washer_decision` and `reconcile` as
standalone, callable, fully-tested functions. Stage 3 (not started)
will wire `sync_washer_decision` into
`washer_resolution_service.decide_resolution` (or its caller in
`backend/app.py`) so a real washer API request triggers synchronous
best-effort sync. Until Stage 3, no governance event is ever written
as a side effect of the real washer decision API — the only way a
washer resolution's governance events are written today is by
calling `sync_washer_decision`/`reconcile` directly (as this stage's
own tests, and the reconciliation CLI, do).

## 12. Files Stage 2 did not modify

`backend/app.py`,
`backend/library/washer_resolution_service.py`,
`backend/library/washer_resolution_decisions.py`,
`backend/library/washer_resolution_decisions_store.py`,
`backend/library/washer_resolution.py`,
`backend/library/data/washer_resolution_ledger.json`,
`backend/library/data/washer_resolution_decisions.json`,
`backend/governance/enums.py`,
`backend/governance/events.py`,
`backend/governance/models.py`,
`backend/governance/service.py`,
`backend/governance/store.py`,
`backend/governance/transitions.py`,
`backend/governance/exceptions.py`,
`backend/governance/adapters/washer_resolution.py` (the original
Stage 5 read-only adapter).

## 13. Files Stage 2 added or modified

**Added:**
`backend/governance/ownership.py`,
`backend/governance/adapters/washer_resolution_sync.py`,
`backend/governance/adapters/washer_resolution_reconciliation.py`,
`tools/run_washer_governance_reconciliation.py`,
`docs/adr/ADR-0015-washer-resolution-governance-integration.md`,
`docs/phases/PHASE_2.8.12_STAGE2_INTEGRATION_CONTRACT.md` (this
file),
`tests/governance/test_ownership.py`,
`tests/governance/adapters/test_washer_resolution_sync.py`,
`tests/governance/adapters/test_washer_resolution_reconciliation.py`,
`tests/test_run_washer_governance_reconciliation.py`.

**Modified:**
`backend/governance/api.py` (ownership guard, one choke point:
`_run_command`),
`tests/governance/test_api.py` (9 new ownership-guard tests,
appended),
`tests/governance/test_compatibility.py` (mechanism-import allowlist
widened from 1 to 3 files per ADR-0015, with 9 new AST-based
boundary tests; 2 existing tests renamed/rescoped, none weakened —
see ADR-0015 "Compatibility boundary update"),
`docs/CHANGELOG.md`, `docs/11_PRODUCT_BACKLOG.md` (§12E added),
`docs/314_Roadmap.md`.
