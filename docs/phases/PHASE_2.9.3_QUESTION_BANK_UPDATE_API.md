# Faz 2.9.3 — Question Bank Update/Edit Workflow: API Contract

- Status: complete. Depends on Faz 2.9.1 (hybrid persistence
  foundation) and Faz 2.9.2 (retrieval API).
- Branch: `feature/faz-2.9.3-question-bank-update-edit-workflow`.
- Scope: exactly one new write endpoint. No existing Faz 2.9.1/2.9.2
  behaviour, response shape, or route is modified.

## 1. Endpoint

**`PATCH /api/question-bank/questions/{question_id}`**

Partial content update. Requires `Depends(user)` auth, same as every
other question-bank route.

## 2. Request Body — editable fields

Every field of `backend.question_bank.schema.QuestionRecord` except
its identity fields (see §3), all `Optional`, `extra="forbid"`
(`backend.question_bank.patch.QuestionPatch`):

```
category, subcategory, difficulty, question_type,
question_tr, question_en, options_tr, options_en,
correct_answer, tolerance,
technical_explanation_tr, technical_explanation_en,
standard_reference, source_reference, source_locator,
traceability_level, tags, learning_objective,
engineering_risk_level, is_active
```

Only fields actually present in the JSON body are changed (Pydantic
`exclude_unset=True`); omitted fields keep the current version's
value. A field explicitly sent as `null` is a legal way to clear an
already-nullable field (e.g. `"subcategory": null`).

## 3. Immutable / forbidden fields

`question_id` and `content_version` have **no field** on the patch
model at all — sending them is a `422` (unknown-field rejection), not
a value error. No lifecycle field (`validation_status`, `reviewed_by`,
etc.) can be set through this body either: those live only in SQLite
and were never part of `QuestionRecord` to begin with.

## 4. Versioning model — append-only, never in-place

This is the central design decision (see Stage 0 report for the full
rationale): `QuestionRecord`'s own contract is that a content change
is always a new `content_version`, never a mutation of an existing
one. `PATCH` honours that contract from the outside while looking like
an ordinary partial update from the caller's side:

1. The current (latest) `content_version` is loaded.
2. The patch is merged onto it in memory.
3. If the merged result is **byte-for-byte identical** to the current
   version (excluding `content_version` itself), this is a **no-op**:
   the current record is returned unchanged, `content_version` does
   not advance, and nothing is written anywhere.
4. Otherwise a brand-new `content_version = current + 1` is appended
   to the JSON store and registered in SQLite as `draft`
   (`from_status=None -> to_status='draft'`), exactly like any other
   newly authored version. Every previously existing
   `(question_id, content_version)` row — JSON and SQLite alike — is
   left completely untouched.

## 5. Empty patch

A body with zero fields set is rejected with **`422`**
(`EmptyPatchError`), not treated as a no-op. This is deliberately
different from a patch whose fields are all already-current values
(§4.3, which returns `200` unchanged) — an empty body signals a
caller-side mistake, not "nothing to change."

## 6. JSON + SQLite consistency (no shared transaction)

JSON content and the SQLite lifecycle table are two independent
storage backends; there is no distributed transaction across them, so
true cross-store atomicity is **not technically achievable**. The
write order is forced: SQLite registration already requires the JSON
content to exist first (`register_question`'s own precondition), so
JSON is appended before SQLite is touched.

If the SQLite step (draft record + status-history insert, one SQLite
transaction) fails, `update_question` immediately performs a
best-effort **compensating delete** of the exact JSON record it just
appended
(`backend.question_bank.store._delete_question_content_version` — a
narrowly-scoped helper used from nowhere else, never a general
edit/delete capability, and never applied to a `content_version` that
ever had a completed SQLite registration):

- **Compensation succeeds (the common case):** net effect is as if the
  PATCH had never been attempted — no new `content_version` in JSON,
  no new SQLite row, the previous latest version unchanged. A `500`
  `PartialUpdateFailureError` is still raised so the caller is told the
  write did not happen, but nothing is left behind. Verified directly
  by `test_sqlite_failure_triggers_json_compensation_no_orphan_remains`
  (JSON has only the old version, `load_question_content(..., 2)`
  raises not-found, no lifecycle row, no history row, and a subsequent
  update succeeds cleanly at `v2`).
- **Compensation also fails (double failure, e.g. filesystem
  unavailable at exactly that moment):** genuinely not preventable by
  this module. The `500` response says so explicitly rather than
  hiding it, and the resulting orphan (a JSON `content_version` with no
  SQLite row) stays inert: every publishable-only read path in this
  module already excludes a `content_version` with no matching SQLite
  row by construction, so it can never surface through normal
  retrieval. Detection is a plain audit (any JSON `content_version`
  with no `question_bank_records` row is, by definition, an orphan);
  manual completion remains possible via `register_question`. Verified
  by `test_sqlite_failure_with_compensation_also_failing_is_reported_as_orphan_risk`.

## 7. Concurrency / version-collision behaviour

Two independent updates that both read the same `current` version and
both attempt to write `current + 1` cannot both succeed: the JSON
store's append-only guard (`DuplicateContentVersionError` on a
`(question_id, content_version)` that already exists) is the single
source of truth for this, and the API maps it to **`409`**. No silent
overwrite is possible. Verified by
`test_two_updates_from_same_current_version_second_raises_conflict`
(service level: a real first update advances `v1 -> v2`, a second,
independently-stale attempt also targeting `v2` raises
`DuplicateContentVersionError`; only `[1, 2]` exist afterwards, never a
silently-overwritten `v2`) and `test_api_patch_conflict_is_409` (same
scenario through the HTTP route).

## 8. HTTP status mapping

| Status | Condition |
|---|---|
| `200` | Success (including no-op — returns the unchanged current record) |
| `404` | Unknown `question_id` (`ContentNotFoundError`) |
| `409` | Concurrent-write race on the same target `content_version` (`DuplicateContentVersionError`) |
| `422` | Empty patch, structural/schema validation failure, or an unknown/immutable field in the body |
| `500` | SQLite registration failed after the JSON append (`PartialUpdateFailureError`) — see §6 |

## 9. Worked example

```
QB-X v1 exists (is_active=true, question_en="...")

PATCH /api/question-bank/questions/QB-X  {"question_en": "Updated text."}
  -> 200, content_version=2, question_en="Updated text."

GET /api/question-bank/questions/QB-X?publishable_only=false
  -> content_version=2 (latest, resolves by default)

GET /api/question-bank/questions/QB-X?content_version=1&publishable_only=false
  -> content_version=1, question_en unchanged, is_active as originally set

PATCH /api/question-bank/questions/QB-X  {"question_en": "Updated text."}  (same value again)
  -> 200, content_version=2 (no-op: no new version created)
```

See the Faz 2.9.3 final delivery report for this exact scenario run
against the live test server.

## 10. Test strategy

`tests/test_faz_2_9_3_question_bank_update.py` — same isolated
`qb_store_path`/`db` fixture pattern as Faz 2.9.1/2.9.2, plus a
per-test-unique `question_id` fixture (the shared session-scoped test
DB is never reset between tests). Covers the patch model's immutable-
field rejection, merge/no-op semantics, structural validation reuse,
not-found, the version-collision race (§7), both compensation outcomes
(§6), lifecycle/history correctness of the new draft version, and the
full HTTP contract (§8). Does not modify or extend the shipped 4-record
demo fixture. See the final delivery report for pass counts.
