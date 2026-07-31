"""TorqPro washer-resolution governance reconciliation -- Faz 2.8.12
Stage 2.

    python tools/run_washer_governance_reconciliation.py [--apply]

Deterministic, explicitly-invoked, idempotent reconciliation between
the Faz 2.8.9 washer resolution decision ledger (authoritative) and
the Faz 2.8.11 governance event store (derived, best-effort). Reuses
``backend.governance.adapters.washer_resolution_reconciliation.
reconcile``, which itself reuses
``backend.governance.adapters.washer_resolution_sync.
sync_washer_decision`` -- this script contains no synchronization
logic of its own, only argument parsing and deterministic JSON
reporting.

Safe by default: runs in **dry-run** mode unless ``--apply`` is
passed explicitly. Dry-run never writes to the governance event
store and never writes to any washer file. ``--apply`` still never
writes to any washer file (this tool has no washer write path at
all, by construction -- see
``washer_resolution_reconciliation``'s module docstring).

The governance event store path is resolved from the same
``TORQPRO_GOVERNANCE_EVENT_STORE_PATH`` environment variable the
governance API uses (single source of configuration truth). If it is
unset or blank, the tool still runs and still produces a complete,
accurate report -- every eligible record is classified
``governance_store_unconfigured`` rather than the tool refusing to
run (ADR-0015, "Store-Unconfigured Behaviour"). The unset/blank
variable's *value* (there is none) is never printed; only the fact
that it is unconfigured is reported.

Exit code: 0 if the run completed and no record was classified
``failed``; 1 otherwise. This mirrors ``run_quality_gate.py``'s
"clear single signal" convention -- it is not itself a pytest-style
assertion tool.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.governance.adapters.washer_resolution_reconciliation import (  # noqa: E402
    ReconciliationReport,
    reconcile,
)
from backend.governance.store import FileGovernanceEventStore  # noqa: E402

GOVERNANCE_EVENT_STORE_PATH_ENV = "TORQPRO_GOVERNANCE_EVENT_STORE_PATH"


def _resolve_store():
    raw_path = os.environ.get(GOVERNANCE_EVENT_STORE_PATH_ENV, "")
    if not raw_path.strip():
        return None
    return FileGovernanceEventStore(Path(raw_path))


def _report_to_json(report: ReconciliationReport) -> dict:
    return {
        "dry_run": report.dry_run,
        "counters": dict(sorted(report.counters.items())),
        "invariant_holds": report.counters["scanned"] == report.terminal_outcome_sum(),
        "records": [
            {
                "resolution_id": r.resolution_id,
                "washer_decision_id": r.washer_decision_id,
                "governance_aggregate_id": r.governance_aggregate_id,
                "outcome": r.outcome.value,
                "event_written": r.event_written,
                "retry_may_help": r.retry_may_help,
                "safe_error_category": r.safe_error_category,
                "safe_message": r.safe_message,
            }
            for r in report.records
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write missing governance events (default: dry-run only).",
    )
    args = parser.parse_args(argv)

    store = _resolve_store()
    report = reconcile(store, dry_run=not args.apply)
    payload = _report_to_json(report)

    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))

    if not payload["invariant_holds"]:
        print(
            "ERROR: reconciliation counter invariant does not hold "
            "(scanned != sum of terminal outcomes).",
            file=sys.stderr,
        )
        return 1

    return 1 if report.counters["failed"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
