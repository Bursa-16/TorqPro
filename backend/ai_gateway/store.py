"""TorqPro AI Gateway - persistent audit store.

Faz v3.0.0-alpha.5 (Persistent Audit), per ADR-0020, superseding
``backend.ai_gateway.audit``'s own module docstring note that SQLite
persistence was "explicitly deferred to a later, separately-approved
phase once this in-process pipeline is proven." This is that phase.

Schema (``ai_audit_records``, additive/idempotent, ``CREATE TABLE IF
NOT EXISTS``/``CREATE INDEX IF NOT EXISTS`` throughout -- matching
``backend.question_bank.store.migrate``'s and
``backend.production_validation.repository.migrate``'s exact pattern,
safe to call on every startup and any number of times in the same
process, never breaks an existing pre-alpha.5 database):

    id, user_id, user_role, correlation_id, query_text_hash,
    response_text_hash, evidence_source_ids_json,
    calculation_formula_ids_json, model_name, had_sufficient_evidence,
    created_at, retrieval_source_types_queried_json,
    evidence_count_by_source_type_json, evidence_status, result_label,
    latency_ms, success, error_category

``user_role``/``correlation_id``/``response_text_hash`` are additive,
all-nullable columns (ADR-0020's "mümkün olduğunca" field list):
``user_role`` mirrors ``backend.ai_gateway.permission.UserContext.
role`` verbatim; ``correlation_id`` mirrors the caller's own
``X-Request-ID`` when supplied; ``response_text_hash`` is a
``sha256`` digest of ``ComposedAnswer.text``, computed by the HTTP
route layer the same way ``query_text_hash`` already is -- never the
raw response text itself (see Privacy note below).

Privacy (ADR-0020, carrying forward ``backend.ai_gateway.audit``'s own
rule verbatim): this table never has a column for raw prompt/response
text, and no code path in this module ever writes one -- only
``query_text_hash`` (a caller-supplied digest) and structured,
already-hashed/enumerated metadata. No column exists for a secret, API
key, token, or HTTP header of any kind, and none is ever written here.

Append-only by construction, mirroring
``backend.ai_gateway.audit.AuditSink``'s own contract: every method on
:class:`SQLiteAuditSink` is an ``INSERT`` -- no ``UPDATE``/``DELETE``
statement appears anywhere in this module.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from backend.ai_gateway.audit import AIInteractionRecord, AuditSink

DDL = """
CREATE TABLE IF NOT EXISTS ai_audit_records(
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  user_role TEXT,
  correlation_id TEXT,
  query_text_hash TEXT NOT NULL,
  response_text_hash TEXT,
  evidence_source_ids_json TEXT NOT NULL,
  calculation_formula_ids_json TEXT NOT NULL,
  model_name TEXT,
  had_sufficient_evidence INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  retrieval_source_types_queried_json TEXT NOT NULL,
  evidence_count_by_source_type_json TEXT NOT NULL,
  evidence_status TEXT NOT NULL,
  result_label TEXT,
  latency_ms INTEGER,
  success INTEGER NOT NULL DEFAULT 1,
  error_category TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_audit_records_created_at
  ON ai_audit_records(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_audit_records_user_id
  ON ai_audit_records(user_id);
"""


def migrate(c: sqlite3.Connection) -> None:
    """Additive, idempotent. Safe to call on every startup and any
    number of times in the same process/test run -- matches
    ``backend.question_bank.store.migrate``'s exact pattern. Never
    alters or drops any existing table; a pre-alpha.5 database opens
    exactly as before, with this one new table added alongside its
    existing ones."""
    c.executescript(DDL)


@dataclass(frozen=True)
class PersistedAuditRecord:
    """Read-shape returned by :func:`list_audit_records` /
    :func:`get_audit_record` -- a plain, JSON-serializable snapshot of
    one ``ai_audit_records`` row. Deliberately a separate type from
    ``AIInteractionRecord`` (that one is the in-process, write-side
    contract; this one is the persisted, read-side contract, and the
    two are not required to stay structurally identical -- this type
    additionally carries ``id``/``latency_ms``/``success``/
    ``error_category``, which ``AIInteractionRecord`` does not)."""

    id: int
    user_id: int
    user_role: Optional[str]
    correlation_id: Optional[str]
    query_text_hash: str
    response_text_hash: Optional[str]
    evidence_source_ids: Tuple[Tuple[str, str], ...]
    calculation_formula_ids: Tuple[str, ...]
    model_name: Optional[str]
    had_sufficient_evidence: bool
    created_at: str
    retrieval_source_types_queried: Tuple[str, ...]
    evidence_count_by_source_type: Tuple[Tuple[str, int], ...]
    evidence_status: str
    result_label: Optional[str]
    latency_ms: Optional[int]
    success: bool
    error_category: Optional[str]


def _row_to_record(row: sqlite3.Row) -> PersistedAuditRecord:
    return PersistedAuditRecord(
        id=row["id"],
        user_id=row["user_id"],
        user_role=row["user_role"],
        correlation_id=row["correlation_id"],
        query_text_hash=row["query_text_hash"],
        response_text_hash=row["response_text_hash"],
        evidence_source_ids=tuple(
            tuple(pair) for pair in json.loads(row["evidence_source_ids_json"])
        ),
        calculation_formula_ids=tuple(json.loads(row["calculation_formula_ids_json"])),
        model_name=row["model_name"],
        had_sufficient_evidence=bool(row["had_sufficient_evidence"]),
        created_at=row["created_at"],
        retrieval_source_types_queried=tuple(
            json.loads(row["retrieval_source_types_queried_json"])
        ),
        evidence_count_by_source_type=tuple(
            tuple(pair) for pair in json.loads(row["evidence_count_by_source_type_json"])
        ),
        evidence_status=row["evidence_status"],
        result_label=row["result_label"],
        latency_ms=row["latency_ms"],
        success=bool(row["success"]),
        error_category=row["error_category"],
    )


class SQLiteAuditSink(AuditSink):
    """Persistent, append-only ``AuditSink`` backed by
    ``ai_audit_records``.

    Requires an already-migrated connection (see :func:`migrate`).
    :meth:`record` implements the exact ``AuditSink`` abstract-method
    signature (one required positional ``entry``) so this class stays
    a drop-in substitute for
    ``backend.ai_gateway.audit.InMemoryAuditSink`` anywhere an
    ``AuditSink`` is expected -- ``backend.ai_gateway.orchestrator``
    itself needs no change to accept this class.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, entry: AIInteractionRecord) -> None:
        """Persist a successful-pipeline ``AIInteractionRecord``
        (``success=1``, ``error_category=NULL``, ``latency_ms=NULL``,
        ``user_role``/``correlation_id``/``response_text_hash=NULL`` --
        this call site never measures latency or carries that extra,
        route-layer-only metadata itself; a caller that wants those
        captured should use :meth:`record_with_latency` instead, which
        wraps this same ``INSERT`` with the additional column values)."""
        self._insert(
            entry,
            latency_ms=None,
            success=True,
            error_category=None,
            user_role=None,
            correlation_id=None,
            response_text_hash=None,
        )

    def record_with_latency(
        self,
        entry: AIInteractionRecord,
        *,
        latency_ms: int,
        user_role: Optional[str] = None,
        correlation_id: Optional[str] = None,
        response_text_hash: Optional[str] = None,
    ) -> None:
        """Same as :meth:`record`, additionally recording
        ``latency_ms`` and the optional, route-layer-only
        ``user_role``/``correlation_id``/``response_text_hash`` fields
        (ADR-0020's "mümkün olduğunca" audit field list -- all three
        default to ``None`` and are never required). Not part of the
        ``AuditSink`` ABC contract -- an optional, additive convenience
        for callers (the HTTP route layer) that already measure
        wall-clock time around ``orchestrator.handle_query`` and have
        access to the requesting user's role / ``X-Request-ID`` /
        response text."""
        self._insert(
            entry,
            latency_ms=latency_ms,
            success=True,
            error_category=None,
            user_role=user_role,
            correlation_id=correlation_id,
            response_text_hash=response_text_hash,
        )

    def record_failure(
        self,
        *,
        user_id: int,
        query_text_hash: str,
        model_name: Optional[str],
        created_at: str,
        error_category: str,
        latency_ms: Optional[int] = None,
        user_role: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Persist a minimal audit record for a request that failed
        *before* ``orchestrator.handle_query`` could produce a
        ``ComposedAnswer`` (e.g. ``ModelUnavailableError``,
        ``PermissionDeniedError``).

        Deliberately **not** part of the ``AuditSink`` ABC and
        deliberately **not** wired into ``backend.ai_gateway.
        orchestrator`` itself: ``handle_query``'s own, already-tested
        contract (``tests/ai/test_orchestrator_boundary.py::
        test_model_failure_is_normalized_to_model_unavailable_error``
        and ``test_calculation_input_error_propagates_and_model_is_
        never_called``, both asserting ``sink.all_entries() == ()`` on
        failure) is left completely unchanged by this phase. This
        method exists purely so the HTTP route layer's *persistent*
        audit trail can still capture "attempted but failed"
        interactions (ADR-0020) without touching that orchestrator
        contract.

        ``error_category`` is always a short, non-fabricated class-name
        style token (e.g. ``"ModelUnavailableError"``) -- never the
        exception's own message string, so no provider error detail
        (which could carry a header/token/URL fragment) ever reaches
        this table (see module docstring, Privacy).
        """
        with self._conn:
            self._conn.execute(
                "INSERT INTO ai_audit_records("
                "user_id, user_role, correlation_id, query_text_hash, "
                "response_text_hash, evidence_source_ids_json, "
                "calculation_formula_ids_json, model_name, had_sufficient_evidence, "
                "created_at, retrieval_source_types_queried_json, "
                "evidence_count_by_source_type_json, evidence_status, result_label, "
                "latency_ms, success, error_category) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    user_id,
                    user_role,
                    correlation_id,
                    query_text_hash,
                    None,
                    "[]",
                    "[]",
                    model_name,
                    0,
                    created_at,
                    "[]",
                    "[]",
                    "FAIL",
                    None,
                    latency_ms,
                    0,
                    error_category,
                ),
            )

    def _insert(
        self,
        entry: AIInteractionRecord,
        *,
        latency_ms: Optional[int],
        success: bool,
        error_category: Optional[str],
        user_role: Optional[str],
        correlation_id: Optional[str],
        response_text_hash: Optional[str],
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO ai_audit_records("
                "user_id, user_role, correlation_id, query_text_hash, "
                "response_text_hash, evidence_source_ids_json, "
                "calculation_formula_ids_json, model_name, had_sufficient_evidence, "
                "created_at, retrieval_source_types_queried_json, "
                "evidence_count_by_source_type_json, evidence_status, result_label, "
                "latency_ms, success, error_category) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry.user_id,
                    user_role,
                    correlation_id,
                    entry.query_text_hash,
                    response_text_hash,
                    json.dumps(list(entry.evidence_source_ids)),
                    json.dumps(list(entry.calculation_formula_ids)),
                    entry.model_name,
                    1 if entry.had_sufficient_evidence else 0,
                    entry.created_at,
                    json.dumps(list(entry.retrieval_source_types_queried)),
                    json.dumps(list(entry.evidence_count_by_source_type)),
                    entry.evidence_status,
                    entry.result_label,
                    latency_ms,
                    1 if success else 0,
                    error_category,
                ),
            )


def list_audit_records(c: sqlite3.Connection, *, limit: int) -> Sequence[PersistedAuditRecord]:
    """Most-recent-first page of persisted audit records.

    ``limit`` is applied exactly as given -- this layer performs no
    clamping/validation of its own (no default value either). Bounds
    checking (a sane range, a sane default) is the HTTP route layer's
    responsibility (``backend/api/routes/ai_gateway.py``, via FastAPI's
    own ``Query(ge=..., le=...)`` convention), deliberately kept out of
    ``backend.ai_gateway`` itself: this package's automated numeric-
    literal guard (``tests/ai/test_safety_and_validation.py::
    test_no_engineering_numeric_literal_anywhere_in_ai_gateway``) bans
    every bare int/float literal outside ``{-1, 0, 1}`` anywhere under
    this package on principle, specifically so no one has to judge
    case-by-case whether a given number "looks like" an engineering
    constant -- a pagination bound is exactly the kind of value that
    guard is written to push out of this package, not around."""
    rows = c.execute(
        "SELECT * FROM ai_audit_records ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return tuple(_row_to_record(row) for row in rows)


def get_audit_record(c: sqlite3.Connection, audit_id: int) -> Optional[PersistedAuditRecord]:
    """Single record by id, or ``None`` if it does not exist -- never
    raises for a missing id (the HTTP route layer maps ``None`` to
    ``404``)."""
    row = c.execute("SELECT * FROM ai_audit_records WHERE id=?", (audit_id,)).fetchone()
    return _row_to_record(row) if row is not None else None


__all__ = [
    "DDL",
    "migrate",
    "PersistedAuditRecord",
    "SQLiteAuditSink",
    "list_audit_records",
    "get_audit_record",
]
