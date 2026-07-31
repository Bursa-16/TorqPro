# Phase 2.8.12 Stage 3 — Washer Controlled Write Integration

- Status: **Stage 3 complete** (2026-07-30). Phase 2.8.12 as a whole
  is **not** complete — Stage 4 (Production Validation / legacy
  calculation-revision / joint-revision assessment) and Stage 5
  (final release pass) remain.
- ADR: `docs/adr/ADR-0015-washer-resolution-governance-integration.md`
  (no amendment required — Stage 3 is a routine implementation of the
  pattern the ADR already formalized; the only genuinely new
  architectural fact discovered during implementation, the widened
  `backend/app.py` → `backend.governance` coupling, is recorded in
  `tests/governance/test_compatibility.py`'s own allowlist docstrings
  rather than a new ADR section, per the "no new ADR for routine
  implementation details" instruction).

## 1. Exact production integration point

`backend/app.py`, `washer_resolution_decide_endpoint`
(`POST /api/library/washers/resolutions/{resolution_id}/decide`),
immediately after `svc.decide_resolution(...)` succeeds and before
the function's `return` statement. Two local imports (matching this
endpoint's existing style — every washer-module import in this
endpoint is already local), one call:

```python
from backend.governance.adapters.washer_resolution_sync import (
    sync_washer_decision_and_log,
)
from backend.governance.api import resolve_governance_store

sync_washer_decision_and_log(decision, resolve_governance_store())
```

wrapped in a `try`/`except Exception` whose `except` body only logs
(`log.exception(...)`) — never re-raises, never alters the response.
This is defense-in-depth on top of
`sync_washer_decision_and_log`'s/`sync_washer_decision`'s own
never-raise guarantee (tested directly: a monkeypatched
`sync_washer_decision_and_log` that raises `RuntimeError` still
yields a `200` washer response).

## 2. Authoritative transaction sequence

1. `svc.decide_resolution(...)` validates and appends to
   `washer_resolution_decisions.json` — **the complete, successful,
   authoritative business transaction**. Unchanged from Faz 2.8.9;
   Stage 3 adds no parameter, no new validation, no new exception.
2. Only if step 1 raised no exception (i.e. execution reached past
   the existing `try`/`except` block) is governance synchronization
   attempted — synchronously, in the same request, same process, no
   background worker/queue/scheduler (per ADR-0015).
3. `resolve_governance_store()` resolves the existing
   `TORQPRO_GOVERNANCE_EVENT_STORE_PATH` mechanism (no new
   environment variable) — returns `None`, never raises, if
   unconfigured.
4. `sync_washer_decision_and_log` (Stage 2, now with Stage 3's
   logging addition) runs `sync_washer_decision` and never raises.
5. The washer decision's response is built and returned exactly as
   it was before Stage 3 existed, regardless of step 2–4's outcome.

## 3. Public API compatibility evidence

Verified directly (tests, not assumption):

- Same URL: `POST /api/library/washers/resolutions/{resolution_id}/decide`.
- Same request schema: `WasherResolutionDecisionRequest` unchanged;
  Stage 3 adds no field.
- Same response schema: `{"decision": ..., "created": ...}` — tested
  (`test_response_schema_unchanged_when_governance_configured`) that
  the response's top-level keys are exactly `{"decision", "created"}`
  even when governance is configured and a sync succeeds. No
  governance field was added to the public response (the "preferred
  behaviour" instruction — kept, not merely satisfied by default).
- Same success status code (`200`).
- Same error semantics: every existing `except` clause
  (`ResolutionNotFoundError`→404, `BlockedRecordDecisionError`→409,
  `InvalidTransitionError`→409, `IdempotencyConflictError`→409,
  `DuplicateDecisionIdError`→409, `MissingEvidenceError`→422,
  `MissingIdempotencyKeyError`→400) is untouched — governance sync
  code runs only *after* that block, so no error path can ever reach
  it. All pre-existing error-mapping tests in
  `tests/test_faz_2_8_9_stage3_api.py::TestDecideErrorMapping` pass
  unchanged.
- Same idempotency behaviour: `TestDecideIdempotency` (Faz 2.8.9's
  own suite) passes unchanged; no second idempotency mechanism was
  added at the HTTP layer (governance sync reuses its own,
  namespaced `washer-sync:` key exclusively inside the sync adapter,
  never exposed to or checked by the washer endpoint itself).

## 4. Logging behaviour

`sync_washer_decision_and_log` (Stage 2 module, `logging.getLogger
("torqpro")` — the exact logger `backend/app.py` already uses; no new
logging framework) emits one `INFO` line per sync attempt:

```
washer_governance_sync resolution_id=<id> decision_id=<id> outcome=<outcome>
event_written=<bool> retry_may_help=<bool> safe_error_category=<category|None>
```

Never includes: filesystem paths, environment-variable values,
credentials, tracebacks, or the decision's own free-text fields
(`resolution_note`/`evidence_reference`) — tested directly
(`test_and_log_emits_safe_fields_only`, using two deliberately
distinctive substrings planted in those fields and asserting their
absence from the emitted log line). The log call itself is wrapped in
its own `try`/`except Exception: pass` — a broken logging handler
cannot break the washer response either (tested by monkeypatching the
module's logger with one that always raises).

## 5. Failure isolation (tested, not assumed)

| Scenario | Washer response | Governance side |
|---|---|---|
| Store unconfigured (default) | `200`, unchanged | `governance_store_unconfigured` |
| Store I/O failure | `200`, unchanged | `failed`/`store_io_error` (Stage 2 coverage, reused) |
| Store corruption | `200`, unchanged | `failed`/`store_corruption` (Stage 2 coverage, reused) |
| `sync_washer_decision_and_log` itself raises unexpectedly (simulated) | `200`, unchanged | Caught by the endpoint's own outer `try`/`except`, logged via `log.exception` |
| Logging handler itself raises | Sync result still returned correctly | Caught inside `sync_washer_decision_and_log`'s own `try`/`except` |

## 6. Retry / idempotency results

1. First terminal decision (`resolved`/`accepted_as_is`/`rejected`),
   store configured → one washer decision appended, exactly one
   governance event written (tested).
2. Exact washer retry (same `idempotency_key`) → existing washer
   idempotency behaviour unchanged (`created=False`, same decision
   returned); governance sync runs again on the replayed decision and
   is itself idempotent (`already_synchronized`, no duplicate
   governance event) — tested end-to-end through the real endpoint
   (`test_repeated_terminal_decision_does_not_duplicate_governance_event`):
   two identical `POST` requests → one governance event.
3. Governance event already exists (simulated pre-existing state) →
   `already_synchronized`, washer response unaffected (Stage 2
   coverage, reused by construction — the sync function is unchanged
   by Stage 3).
4. Store unavailable/unconfigured → washer decision succeeds, no
   exception escapes, reconciliation can recover later — tested
   directly and via the reconciliation-recovery test below.
5. Process-gap equivalent: a washer decision recorded with the store
   unconfigured has no governance event; a later `reconcile()` call
   (store now configured) recovers it without special-casing — tested
   end-to-end through the real endpoint plus `reconcile()`
   (`test_governance_event_recoverable_via_reconciliation_after_unconfigured_decide`).

## 7. Reconciliation relationship

Unchanged from Stage 2: `reconcile()` and
`tools/run_washer_governance_reconciliation.py` remain the mandatory
recovery mechanism for anything the Stage 3 synchronous best-effort
call missed (store unconfigured/unavailable at decision time, process
termination between the two writes, or any washer decision recorded
before this integration existed). Stage 3 introduces no second,
independent idempotency or recovery mechanism — the reconciliation
tool and the Stage 3 call site both delegate to the same
`sync_washer_decision` function.

## 8. Files intentionally unchanged

`backend/library/washer_resolution_service.py`,
`backend/library/washer_resolution_decisions.py`,
`backend/library/washer_resolution_decisions_store.py`,
`backend/library/washer_resolution.py`,
`backend/library/data/washer_resolution_ledger.json`,
`backend/library/data/washer_resolution_decisions.json` (SHA256-
verified before/after — see completion report),
`backend/governance/adapters/washer_resolution_reconciliation.py`,
`backend/governance/ownership.py`,
`backend/governance/enums.py`, `events.py`, `models.py`, `service.py`,
`store.py`, `transitions.py`, `exceptions.py`.

## 9. Compatibility-boundary note (not a new ADR)

`backend/app.py`'s governance-import allowlist
(`tests/governance/test_compatibility.py`) is widened from one line
(Stage 4's router mount) to three: the router mount plus Stage 3's
two washer-sync-call-site imports. This is the same
existing-mechanism-widens-its-coupling-to-governance direction Stage
4 already established (not the opposite, Stage 2/5
governance-imports-a-mechanism direction, which ADR-0015 already
covers). `washer_resolution_service.py` and every other washer
library module remain fully decoupled from `backend.governance` —
the coupling exists only at the HTTP route layer, and only as two
narrowly-scoped, explicitly-allowlisted import lines plus one call,
enforced by `test_app_py_calls_the_washer_sync_call_site_exactly_once`
and `test_no_existing_mechanism_imports_governance_package_except_the_approved_lines`.
