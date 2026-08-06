"""TorqPro Engineering Question Bank -- Faz 2.9.1 hybrid persistence
foundation.

Two independent storage layers, deliberately kept separate (per
Faz 2.9.0's persistence comparison analysis and ADR-0016):

  - **Canonical content** (question text, options, technical
    explanations, traceability) lives in versioned JSON
    (``backend/question_bank/data/question_bank.v1.json``), following
    the same pattern as ``backend/library/data/*.json``.
  - **Lifecycle, validation status, and append-only audit history**
    live in SQLite (``question_bank_records`` /
    ``question_bank_status_history``), following the same pattern as
    ``backend/production_validation`` and ``calculation_revisions``.

The two layers are linked by ``(question_id, content_version)``, never
by content itself -- so a lifecycle decision always points at an
exact, immutable content snapshot.
"""

from __future__ import annotations

__all__: list[str] = []
