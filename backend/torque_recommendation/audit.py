"""TorqPro Torque Recommendation Engine - traceability/audit
persistence (v3.0.0-beta.1, scope item 8).

**Reuses the existing, repository-wide ``audit_log`` table**
(``backend.app``'s own ``audit_log(id, user_id, action, detail,
request_id, created_at)``, already used by every other module --
joints, question_bank, governance, calculations, users, releases,
...) rather than introducing a dedicated
``torque_recommendation_audit`` table. A dedicated table was
considered and rejected: ``audit_log.detail`` is an unconstrained
``TEXT`` column with no existing precedent restricting it to
single-line human text, so the full minimum-reproducibility bundle
this phase requires (normalized request inputs, the deterministic
result, validation outcome, confidence, warnings/critical findings,
the recommended-or-withheld torque, and the audit id itself) fits
cleanly as one canonical JSON payload -- there is no technical
obstacle that would justify a second table purely for architectural
symmetry with e.g. ``backend.ai_gateway.store``'s dedicated
``ai_audit_records`` table (that table exists because
``backend.ai_gateway`` is a package deliberately isolated behind a
one-way dependency guard with its own privacy/hashing rules; this
module has no such constraint and sits squarely inside the same
authenticated-request/audit_log convention every other domain module
already uses).

This module performs **no schema migration of its own** -- it writes
into ``audit_log``, which ``backend.app.migrate()`` already creates
unconditionally before any request is served. There is nothing here
for :func:`backend.app.migrate` to call.

Append-only by construction: the only mutating function in this
module is :func:`record_recommendation`, a single ``INSERT`` -- no
``UPDATE``/``DELETE`` statement appears anywhere here, matching
``backend.app.audit()``'s own append-only contract for every other
caller of ``audit_log``.

A fixed ``action`` value, ``"torque_recommendation"``, distinguishes
these rows from every other module's ``audit_log`` entries -- the
same discriminator convention ``"joint_create"``/
``"calculation_create"``/``"user_create"`` etc. already establish,
and the same rows are visible for free through the existing admin
audit-log view (``backend/app.py``'s own ``audit_log`` listing), no
new endpoint required.

Privacy (scope item 8, "avoid storing unnecessary sensitive data"):
the caller-supplied free-text ``engineering_context`` is never
persisted verbatim -- only its length is recorded, so a reader can see
that context was supplied without recovering its content. Every other
persisted value is a plain engineering number/label already validated
by ``backend.torque_recommendation.models.TorqueRecommendationRequest``
-- none of this is proprietary/OEM-identifying (see
``tests/torque_recommendation/test_beta1_engine.py``'s no-OEM-leak
guard).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional

#: Fixed ``audit_log.action`` discriminator for every row this module
#: writes -- lets a reader filter ``audit_log`` for exactly this
#: module's entries without a schema change.
ACTION = "torque_recommendation"


def _canonical_json(payload: Dict[str, Any]) -> str:
    """Same canonical serialization convention used throughout this
    repository (``sort_keys=True``, ``ensure_ascii=False``) -- keeps
    Turkish-character request/result content byte-stable rather than
    escaped, matching the project-wide checksum discipline."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def record_recommendation(
    c: sqlite3.Connection,
    *,
    user_id: int,
    request_dict: Dict[str, Any],
    result_dict: Dict[str, Any],
    created_at: str,
    request_id: str = "",
    provider_involved: bool = False,
) -> int:
    """Append one recommendation trace record into ``audit_log`` and
    return its new ``id`` (the ``trace_id`` this module's callers
    expose). Never updates or removes any prior row.

    ``request_dict``/``result_dict`` are expected to already be the
    plain, JSON-serializable shapes
    ``TorqueRecommendationRequest.model_dump()`` /
    ``TorqueRecommendationResult.to_dict()`` produce. The stored
    ``detail`` payload is the minimum reproducibility bundle scope
    item 8/4 requires: normalized request inputs (with
    ``engineering_context`` popped -- see module docstring, Privacy),
    the full deterministic result (status, confidence, readiness,
    warnings, critical_findings, recommended/calculated torque,
    explanation), and whether any AI provider was involved (always
    ``False`` in this phase).
    """
    request_to_store = dict(request_dict)
    engineering_context = request_to_store.pop("engineering_context", None)
    context_length: Optional[int] = (
        len(engineering_context) if isinstance(engineering_context, str) else None
    )

    detail_payload = {
        "request": request_to_store,
        "engineering_context_length": context_length,
        "result": result_dict,
        "provider_involved": provider_involved,
    }

    cur = c.execute(
        "INSERT INTO audit_log(user_id,action,detail,request_id,created_at) "
        "VALUES(?,?,?,?,?)",
        (user_id, ACTION, _canonical_json(detail_payload), request_id, created_at),
    )
    c.commit()
    return int(cur.lastrowid)


def get_recommendation_audit(c: sqlite3.Connection, audit_id: int) -> Optional[Dict[str, Any]]:
    """Read-only lookup of one recommendation audit record by
    ``audit_log.id``, or ``None`` if it does not exist or is not a
    ``torque_recommendation`` row. Never mutates any row."""
    row = c.execute(
        "SELECT * FROM audit_log WHERE id=? AND action=?", (audit_id, ACTION)
    ).fetchone()
    if row is None:
        return None
    record = dict(row)
    detail = json.loads(record["detail"])
    record["request_json"] = detail["request"]
    record["engineering_context_length"] = detail["engineering_context_length"]
    record["result_json"] = detail["result"]
    record["provider_involved"] = 1 if detail["provider_involved"] else 0
    record["status"] = detail["result"].get("status")
    record["confidence"] = detail["result"].get("confidence")
    record["readiness"] = detail["result"].get("readiness")
    return record


__all__ = ["ACTION", "record_recommendation", "get_recommendation_audit"]
