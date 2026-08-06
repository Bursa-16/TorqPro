# Question Bank Persistence: Hybrid SQLite Lifecycle + Versioned JSON Content

- Status: Accepted
- Date: 2026-08-06

## Context

Faz 2.9.0's Engineering Question Bank scope/schema analysis identified
two data characters that do not share the same operational
requirements: (a) large, TR/EN-paired, comparatively static question
content, and (b) frequently-changing lifecycle state
(`draft`/`technical_review`/`validated`/`rejected`/`deprecated`)
requiring atomic transitions, append-only audit history, and unique-
key integrity. ADR-0006 (SQLite Local, PostgreSQL Evolution) and the
existing `backend/library/data/*.json` (static reference content) /
`calculations`+`calculation_revisions` (SQLite, transactional
lifecycle) pair already demonstrate proven, separate handling of each
character -- but no existing module cross-references the two the way
the Question Bank needs to.

A dedicated comparison (14 criteria: architectural fit, schema
evolution, TR/EN handling, traceability, workflow support, revision
history, integrity constraints, testability, growth, import/export,
UI query performance, PostgreSQL migration path, bundle/patch
delivery, and Windows-compatible operation) found SQLite structurally
superior for lifecycle/state concerns and JSON structurally superior
for content-authoring and delivery concerns, with no single option
winning on every axis.

## Decision

Question content (`question_tr`/`en`, `options_tr`/`en`,
`technical_explanation_tr`/`en`, `standard_reference`,
`source_reference`, `traceability_level`, `tags`,
`learning_objective`, `unit_system`-equivalent fields, `category`,
`difficulty`, `question_type`, `engineering_risk_level`) is stored in
versioned JSON (`backend/question_bank/data/question_bank.v1.json`),
following the same shape and checksum discipline as
`backend/library/data/*.json`.

Lifecycle state, review metadata, and append-only audit history are
stored in two new SQLite tables (`question_bank_records`,
`question_bank_status_history`), following the same
`CREATE TABLE IF NOT EXISTS` / `UNIQUE` / append-only pattern as
`calculation_revisions` and the sub-module `migrate(c)` wiring
pattern already used by `backend.production_validation.repository`.

The two layers are linked exclusively by `(question_id,
content_version)` -- never by content itself, so a lifecycle decision
always points at an exact, immutable content snapshot. The service
layer (`backend/question_bank/service.py`) rejects any operation whose
`(question_id, content_version)` has no matching JSON content
(JSON/SQLite mismatch rejection) and any attempt to write an already-
existing `(question_id, content_version)` pair to either layer
(silent-overwrite prohibition, enforced at both the JSON store's
application-level check and SQLite's `UNIQUE` constraint as a
backstop).

Authorization is a small, explicit, injectable callback
(`AuthorizationCallback = Callable[[str, str], bool]`), not a new
role/user system. A reference implementation
(`default_role_authorization`) reuses TorqPro's existing
`admin`/`engineer`/`viewer` role vocabulary verbatim (see
`backend/api/dependencies.py`, `backend/app.py`); the service layer
itself has no FastAPI/JWT dependency, so it remains trivially testable
with allow/deny stubs.

`technical_review -> draft` (and `rejected -> draft`) require: a
`revision_reason` of at least 20 characters after trimming; a
successful authorization check; and a strictly different
`content_version_after` from `content_version_before`. All three are
enforced in `backend/question_bank/service.py::return_to_draft`
before any write occurs.

`technical_review -> validated` and `validated -> deprecated` also
require a successful authorization check.

Persistence explicitly avoids `fcntl`-based file locking (used by
`backend/library/washer_resolution_decisions_store.py`, which is
itself documented as non-functional on Windows). The JSON store uses
an in-process `threading.Lock` plus atomic replace (temp file +
`os.replace`, atomic on both POSIX and Windows) instead; true
multi-process concurrency protection for lifecycle decisions is
delegated to SQLite's own locking, not to the JSON layer.

`TraceabilityLevel` reuses `backend.engineering_core.trace`'s five-
value vocabulary (`APPROVED`/`PROVISIONAL`/`EXPERIMENTAL`/
`DEPRECATED`/`UNVERIFIED`) verbatim, asserted equal at import time
rather than re-declared, so the two vocabularies cannot silently
diverge.

Standard content is referenced (name, edition/year, clause/table),
never reproduced at length, matching ADR-0007. TR/EN parity
(non-empty question text and technical explanation in both languages,
matching option counts) is enforced structurally by
`backend/question_bank/schema.py` and cross-checked by
`backend/question_bank/validator.py`.

## Consequences

- Bundle/patch delivery (`git bundle`, SHA256SUMS, clean-clone
  verification -- the project's existing delivery discipline)
  automatically includes the JSON content file. SQLite's `CREATE
  TABLE` DDL travels as code (in `backend/question_bank/store.py`);
  populated lifecycle/audit *data* does not travel in the bundle and
  is expected to be freshly created (via `migrate()`, already wired
  into `backend/app.py`'s central `migrate()`) in every environment
  that runs the application.
- This is the first module in the repository that cross-references a
  SQLite lifecycle record against a JSON content file by composite
  key. `formula_reference`-style code-catalog cross-references
  (`backend.engineering_core.trace`) exist as precedent for
  "reference, don't duplicate," but not for a SQLite-to-JSON link of
  this shape; future modules with a similar content/lifecycle split
  may reuse this pattern.
- PostgreSQL migration (ADR-0006's eventual target) only needs to
  carry `question_bank_records` and `question_bank_status_history`;
  the JSON content layer can continue to be treated like any other
  `backend/library/data/*.json` file, independently of that migration.
- Windows-local development (Anaconda/Spyder) is unaffected by any
  `fcntl` non-portability; the only accepted trade-off is that the
  JSON content file's write path does not protect against two
  separate OS processes writing simultaneously -- acceptable because
  content authoring is expected to be a low-concurrency, largely
  single-actor workflow, unlike lifecycle decisions (which do need,
  and get, real concurrency protection via SQLite).

Implementation and documentation must follow this decision. Changes
require a superseding ADR.
