# Washer Resolution Decision Workflow: Append-Only Decisions, Effective
Status, Idempotent API (Faz 2.8.9)

- Status: Accepted
- Date: 2026-07-29

## Context

Faz 2.8.5 delivered `backend/library/washer_resolution.py`: a
correction/resolution ledger (`backend/library/data/washer_resolution_ledger.json`)
recording, for every washer library record that provenance flagged as
`action_needed`, an `issue_type`, a `resolution_status`
(`open` / `under_review` / `resolved` / `accepted_as_is` /
`blocked_authoritative_source` / `rejected`), and — when applicable —
`resolved_standard`/`resolved_by`/`confidence_level`. At the end of
Faz 2.8.5 the ledger held 76 records: 71 `open`, 5
`blocked_authoritative_source` (an ISO 7093 vs ISO 7093-1 identity
ambiguity — see "Alternatives considered" below). The module was
intentionally read-only: it defined the record shape and accessors
(`list_washer_resolutions`, `count_by_status`,
`unresolved_washer_resolutions`, ...) but had no write path. Deciding
those 71+5 records required real engineering judgement (a source
citation, a standard confirmation, or an explicit "accept as-is")
that no automated process may invent — see `docs/12_CLAUDE_CONTEXT.md`
§4 and the Faz 2.8.9 task brief's explicit prohibition on inventing a
standard designation, a dimensional value, or a correctness judgement.

Faz 2.8.9's task was therefore not "resolve the 71 records" but
**build the workflow mechanism** that lets a human record such a
decision, safely, auditable, and idempotently — while leaving every
one of the task brief's hard constraints intact:

1. No washer record's status may be changed automatically by this
   phase's own code.
2. No numeric value, washer dimension, or standard designation may be
   invented.
3. The 71 open / 5 blocked records must keep their original status.
4. The existing `washer_resolution_ledger.json` schema must stay
   backward compatible — ideally untouched.

## Decision

### 1. The source ledger is immutable; a second, append-only ledger
   records decisions

`washer_resolution_ledger.json` (Faz 2.8.5) is never written to by
any Faz 2.8.9 code path. A new, separate file,
`backend/library/data/washer_resolution_decisions.json`
(`backend.library.washer_resolution_decisions_store`), is the
Faz 2.8.9 audit trail: one `WasherResolutionDecision` entry per
recorded human decision (`decision_id`, `resolution_id`,
`previous_status`, `new_status`, `resolution_note`,
`evidence_reference`, `resolved_by`, `decided_at`,
`confidence_level`, `integrity_checksum`, `idempotency_key`). The
model uses `extra="forbid"` (mirroring `WasherResolutionRecord`): a
decision is a closed set of audit fields, structurally incapable of
carrying a washer geometry or standard-identity override.

Appends are atomic (temp file + `os.fsync` + `os.replace`) and
serialized by an advisory lock — `fcntl.flock` when available (POSIX),
falling back to an in-process `threading.Lock` where it is not (e.g.
Windows), so the module always imports and the single-process/
multi-thread guarantee holds everywhere; a cross-process guarantee on
non-POSIX platforms is out of scope (single-node deployment, matching
the project's existing SQLite architecture — see ADR-0006).

### 2. Effective status is computed, never written back to the source

`backend.library.washer_resolution_service.effective_status()` is the
one place the two ledgers meet: the *effective* status of a
`resolution_id` is the `new_status` of its most recent recorded
decision, or — if no decision has ever been recorded for it — the
source ledger's original `resolution_status`, read unchanged. This
overlay is what makes the workflow functionally real (a second
decision attempt must see the first decision's outcome) without ever
mutating the Faz 2.8.5 file. Every consumer (the API, the Stage 4/5
report) computes effective status through this one function or
through `resolution_queue()`, which projects it over all 76 records —
no second implementation of this logic exists anywhere in the
codebase (Stage 4/5's own rule, enforced by code review and by the
Stage 4/5 tests asserting the report never re-derives it).

### 3. A closed state machine, not free-form status assignment

`backend.library.washer_resolution_decisions.ALLOWED_TRANSITIONS` is
an explicit, closed table:

- `open -> {under_review, resolved, accepted_as_is, rejected}`
- `under_review -> {open, resolved, accepted_as_is, rejected}`
- Terminal statuses (`resolved`, `accepted_as_is`, `rejected`) have
  **no** outgoing transition in this phase — reopening a terminal
  decision is explicitly out of scope (task brief rule 9); a future
  phase may add a distinct, separately-authorized reopen workflow.
- `blocked_authoritative_source` has **no** outgoing transition
  through this table at all; it is checked first and raises a
  dedicated `BlockedRecordDecisionError` (mapped to HTTP 409) rather
  than falling through to the generic transition table — the 5
  ISO-7093-ambiguous records can never be decided through this
  workflow in this phase (task brief rule 10).

Any transition not explicitly listed is rejected (fail-closed). An
import-time assertion cross-checks that every
`WasherResolutionStatus` member is accounted for by the table, the
terminal set, or the blocked special-case, so a future new status
value cannot silently fall through unnoticed.

### 4. Idempotency is checked before state-machine validation

A decision request always carries a caller-supplied
`idempotency_key`. `decide_resolution()` checks for an existing
decision with that key **first**, before validating the requested
transition: if a matching decision already exists, its fields are
compared to the current request — same effective request returns the
original decision unchanged (`created=False`, no new ledger entry);
a key reused for a genuinely different request (different status,
note, evidence, resolved-by, confidence, or even a different
`resolution_id`) raises `IdempotencyConflictError` (HTTP 409). Doing
the idempotency check before the transition check is deliberate: a
legitimate network retry of the exact original request must never
fail state-machine validation just because the first attempt already
advanced the effective status.

### 5. Reporting is read-only and additive

`backend.library.washer_report.collect_washer_resolution_report()`
(Faz 2.8.5, extended in Stage 4) gained new fields — effective-status
counts, a `resolved` count derived **only** from real recorded
`new_status="resolved"` decisions (structurally 0 unless at least one
such decision exists — never inferred from the 71 open / 5 blocked
records), a decision-history summary, and a `report_checksum`. No
existing field was removed or renamed. `GET
/api/library/washers/resolutions/report` (Stage 5A) is GET-only,
delegates entirely to the Stage 4 collector and its existing TR
(`render_washer_resolution_report_markdown`) and new EN
(`render_washer_resolution_report_markdown_en`) renderers — it never
regenerates report content, and it cannot create or modify a
decision. The frontend (`frontend/index.html`,
`page-washerresolution`) renders only backend-supplied values through
a `wrrIsWellFormed()` guard: a response missing a required field is
treated as malformed and shown as an explicit error state, never
partially rendered with a guessed or zero-filled value.

### 6. JSON is the wire format of record; Markdown is a convenience view

The report/decision-history/queue endpoints return structured JSON by
default. `format=markdown` is additive and optional
(`?format=json|markdown`), rendering through the existing Stage 4 TR/
EN functions — no third markdown-generation code path was added in
`backend/app.py`. The JSON payload's content is language-independent
(status codes, not localized prose); `lang` only affects the Markdown
rendering and is otherwise validated and echoed back.

### 7. TR/EN parity from the start

Every new user-facing string this phase introduces — decision-history/
report labels, empty/loading/error states, integrity-warning text —
is defined as a `(code, tr, en)`-equivalent pair from day one,
following the precedent set in Faz 2.8.8 (ADR-0012). `wrr.*` keys
carry exact TR/EN parity (38/38); pre-existing, pre-2.8.8 free-text
warnings are not retrofitted (unchanged, out of scope, matches ADR-0012).

### 8. Integrity checksum

Every `WasherResolutionDecision.integrity_checksum` and the report's
`report_checksum` use the project's one canonical checksum algorithm:
`sha256(json.dumps(payload, sort_keys=True,
ensure_ascii=False)).hexdigest()` over the record's own fields minus
the checksum field itself — the same algorithm as
`backend.library.population.find_checksum_mismatches` and the
`TORQPRO_ENGINEERING` canonical-checksum rule (memory/CLAUDE.md).
`ensure_ascii=False` is load-bearing (a known project pitfall:
omitting it silently produces the wrong checksum for Turkish-
character content) and is exercised by a dedicated regression test.

## Relationship to the Faz 2.8.5 `action_needed` records

This phase does not close any of the 71 open or 5 blocked records —
it was never in scope to do so without real evidence. What it adds is
the *capability* to close them safely once evidence exists: a human
(İlhan, or a future authorized reviewer) can call `POST
/api/library/washers/resolutions/{resolution_id}/decide` with a
citation (`evidence_reference`) and a note, and the decision is
recorded, checksummed, and reflected in `effective_status` and the
report — without ever touching the Faz 2.8.5 file. The 5
`blocked_authoritative_source` records (ISO 7093 identity ambiguity)
remain explicitly un-decidable through this workflow; resolving that
ambiguity is future work requiring its own authoritative-source ADR
(see "Alternatives considered").

## Alternatives considered

1. **Mutate `washer_resolution_ledger.json` in place when a decision
   is recorded.** Rejected: this would break the Faz 2.8.5 file's
   established read-only contract, complicate every existing Faz
   2.8.5 accessor/test that assumes static content, and make an
   accidental or malicious in-place edit indistinguishable from a
   legitimate decision. The append-only overlay achieves the same
   functional result (a queryable current status) with a strictly
   additive, auditable design.
2. **Auto-resolve the 71 open records using heuristics (e.g. "no
   conflicting dimension found -> mark resolved").** Rejected outright
   — this is exactly the "invented engineering judgement" the task
   brief and `docs/12_CLAUDE_CONTEXT.md` §4 prohibit. Every decision
   this phase's code path can produce still requires a human-supplied
   `evidence_reference` and `resolution_note`; nothing is inferred.
3. **Resolve the 5 blocked ISO 7093 / ISO 7093-1 records by picking
   one interpretation.** Rejected — a standard-identity decision
   requires an authoritative source lookup this phase does not have;
   doing so would be a formula/standard-identity change requiring its
   own ADR and evidence (`docs/12_CLAUDE_CONTEXT.md` §4), not a side
   effect of building a workflow mechanism.
4. **Single mutable `resolution_status` field with a simple audit
   log table on the side (log-then-mutate), instead of the source
   ledger staying wholly read-only.** Rejected: reintroduces the same
   "who last wrote this file" ambiguity item 1 avoids, and makes the
   Faz 2.8.5 checksum/version invariants (existing tests) harder to
   reason about for no functional gain over the overlay approach.

## Consequences

- The Faz 2.8.5 source ledger's status distribution (71 `open`, 5
  `blocked_authoritative_source`) is permanent as *source* data;
  only the derived `effective_status` can move, and only through a
  recorded, evidenced decision.
- A future phase that wants to physically regenerate
  `washer_resolution_ledger.json` from a new provenance run (e.g.
  after real standard confirmations accumulate) is free to do so, but
  that is a distinct, out-of-scope operation requiring its own review
  — this ADR does not authorize it.
- The 5 blocked records remain permanently un-decidable through this
  workflow until a superseding ADR resolves the ISO 7093 / ISO
  7093-1 identity question with an authoritative source.
- Reopening a terminal decision is unsupported in this phase; a
  distinct, explicitly authorized reopen workflow is required before
  that becomes possible (task brief rule 9).
- The advisory lock's cross-process guarantee is POSIX-only; a
  multi-process deployment on a non-POSIX host would only get the
  in-process guarantee. Out of scope for this phase (single-node
  architecture, ADR-0006).
- A pre-existing, unrelated weakness was found in
  `tests/js/run_material_intelligence_tests.js` (Faz 2.8.8) during
  Stage 5 work on this phase's own JS harness: its asynchronous test
  scenarios are not awaited before the harness's process exits, so
  their assertions do not execute even though the harness reports a
  "clean" result. This phase's own harness
  (`tests/js/run_washer_resolution_report_tests.js`) was built with
  (and later refactored into) an awaited `async function main()` to
  avoid the same defect; the Faz 2.8.8 harness itself was left
  unmodified (out of scope) — see
  `docs/11_PRODUCT_BACKLOG.md` §12B for the tracked follow-up.
