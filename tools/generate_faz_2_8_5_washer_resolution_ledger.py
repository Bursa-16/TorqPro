"""TorqPro Engineering Library - Faz 2.8.5 washer resolution ledger
generator.

One-time *authoring* script (mirrors the convention already
established by ``tools/generate_faz_2_8_4_washer_provenance_manifest.py``
and ``tools/generate_faz2_4_1c_washer_records.py``): it writes
``backend/library/data/washer_resolution_ledger.json``, which then
becomes the single source of truth for washer correction/resolution
tracking. ``backend.library.washer_resolution`` never re-derives
issue classification -- it only reads this ledger.

Scope (Faz 2.8.5 task brief): open exactly one resolution record for
each of the 76 ``action_needed`` records already identified by Faz
2.8.4 (``docs/phase_2_8/phase_2_8_4_washer_provenance_report.json``),
re-classified into the Faz 2.8.5 ``issue_type`` vocabulary
(``source_missing``, ``source_ambiguous``, ``standard_identity_ambiguous``,
``dimensional_conflict``, ``duplicate_or_alias``, ``verification_pending``,
``other``).

This script invents **no new engineering finding** and estimates
**no** geometric or mechanical value. It only re-labels the four Faz
2.8.4 ``reason_code`` values already assigned into the broader Faz
2.8.5 category vocabulary, and decides -- deterministically, from
repository evidence only -- an initial ``resolution_status``:

  - ``standard_identity_requires_review`` (ISO 7093 / ISO 7093-1,
    5 records): the identity question cannot be settled without an
    authoritative ISO source, per the Faz 2.8.4 finding. These start
    ``blocked_authoritative_source`` (``requires_authoritative_source
    = true``). No standard is assigned or guessed.
  - Every other reason code (71 records): starts ``open`` -- flagged
    for engineering review, not resolved, not estimated.

No record's ``resolution_status`` starts as ``resolved``,
``accepted_as_is`` or ``rejected`` -- this script performs
classification only, never resolution. Reaching those terminal
statuses is a deliberate, separate, human/engineering action recorded
later through ``backend.library.washer_resolution``.

Usage::

    python -m tools.generate_faz_2_8_5_washer_resolution_ledger \
        [--check]

Default mode (no arguments): writes the ledger deterministically to
``backend/library/data/washer_resolution_ledger.json``.

``--check``: does not write; exits non-zero if the freshly computed
ledger would differ from the file already on disk (drift check, used
in CI-style verification -- mirrors the ``--output-dir``-less "print
only" mode convention of ``tools/washer_provenance_report_faz_2_8_4.py``).

Exit codes:
  0  ledger written (or, with --check, matches the file on disk)
  1  Faz 2.8.4 report / washer_library.json inconsistency detected,
     or (with --check) the on-disk ledger is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
WASHER_LIBRARY_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_library.json"
PROVENANCE_REPORT_PATH = (
    REPO_ROOT / "docs" / "phase_2_8" / "phase_2_8_4_washer_provenance_report.json"
)
LEDGER_PATH = REPO_ROOT / "backend" / "library" / "data" / "washer_resolution_ledger.json"

#: Faz 2.8.4 reason_code -> Faz 2.8.5 issue_type. Every key below is
#: one of the exact four reason codes Faz 2.8.4 produced (see
#: ``ALLOWED_REASON_CODES`` in ``tools/washer_provenance_report_faz_2_8_4.py``);
#: an unrecognised reason code is a hard error, not silently dropped.
REASON_CODE_TO_ISSUE_TYPE: Dict[str, str] = {
    "standard_identity_requires_review": "standard_identity_ambiguous",
    "estimated_value_diverges_from_secondary_source": "dimensional_conflict",
    "confidence_metadata_contradiction": "verification_pending",
    "high_internal_confidence_lacks_external_evidence": "source_missing",
}

#: Reason codes whose identity/value question cannot be settled from
#: repository evidence alone (Faz 2.8.4's own finding) -- these start
#: blocked rather than open. Deliberately a small, explicit allow-list
#: rather than an inferred rule, so adding a future reason code never
#: silently changes this behaviour.
REASON_CODES_BLOCKED_ON_AUTHORITATIVE_SOURCE = frozenset(
    {"standard_identity_requires_review"}
)

ALL_ISSUE_TYPES = (
    "source_missing",
    "source_ambiguous",
    "standard_identity_ambiguous",
    "dimensional_conflict",
    "duplicate_or_alias",
    "verification_pending",
    "other",
)


class LedgerGenerationError(RuntimeError):
    """Raised when the Faz 2.8.4 report and washer_library.json are
    inconsistent in a way that would force this script to guess."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_inputs() -> "tuple[Dict[str, Any], Dict[str, Any]]":
    library_payload = _load_json(WASHER_LIBRARY_PATH)
    report_payload = _load_json(PROVENANCE_REPORT_PATH)
    return library_payload, report_payload


def build_ledger_records(
    library_payload: Dict[str, Any], report_payload: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Deterministically derive one resolution record per Faz 2.8.4
    ``action_needed`` record. Raises :class:`LedgerGenerationError`
    if a referenced washer record is missing from the live library,
    or an unknown reason code is encountered -- this script never
    fabricates a fallback classification."""
    by_id = {r["id"]: r for r in library_payload.get("records", [])}
    action_needed = report_payload.get("action_needed_records", [])

    records: List[Dict[str, Any]] = []
    for entry in action_needed:
        washer_record_id = entry["record_id"]
        reason_code = entry["reason_code"]

        if washer_record_id not in by_id:
            raise LedgerGenerationError(
                f"action_needed record {washer_record_id!r} not found in "
                "washer_library.json"
            )
        if reason_code not in REASON_CODE_TO_ISSUE_TYPE:
            raise LedgerGenerationError(
                f"unrecognised Faz 2.8.4 reason_code: {reason_code!r}"
            )

        issue_type = REASON_CODE_TO_ISSUE_TYPE[reason_code]
        blocked = reason_code in REASON_CODES_BLOCKED_ON_AUTHORITATIVE_SOURCE
        library_record = by_id[washer_record_id]

        records.append(
            {
                "resolution_id": f"RES-{washer_record_id}",
                "washer_record_id": washer_record_id,
                "issue_type": issue_type,
                "reason_code": reason_code,
                "resolution_status": (
                    "blocked_authoritative_source" if blocked else "open"
                ),
                "resolution_note": entry.get("notes", ""),
                "evidence_reference": (
                    "docs/phase_2_8/phase_2_8_4_washer_provenance_report.json"
                    f"#action_needed_records[record_id={washer_record_id}]"
                ),
                "resolved_standard": None,
                "resolved_by": "",
                "resolved_at": "",
                "confidence_level": library_record.get("confidence"),
                "requires_authoritative_source": blocked,
            }
        )

    records.sort(key=lambda r: r["washer_record_id"])
    return records


def render_ledger(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "metadata": {
            "name": "Washer Resolution Ledger",
            "version": "2.8.5",
            "description": (
                "Faz 2.8.5 correction/resolution tracking for washer "
                "records flagged action_needed by the Faz 2.8.4 "
                "provenance report. Additive: never mutates "
                "washer_library.json."
            ),
            "generated_from": (
                "docs/phase_2_8/phase_2_8_4_washer_provenance_report.json"
            ),
            "record_count": len(records),
        },
        "records": records,
    }


def _dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def run(check_only: bool) -> int:
    try:
        library_payload, report_payload = load_inputs()
        records = build_ledger_records(library_payload, report_payload)
    except (LedgerGenerationError, KeyError, FileNotFoundError) as exc:
        print(f"FAIL: cannot generate washer resolution ledger: {exc}", file=sys.stderr)
        return 1

    ledger = render_ledger(records)
    text = _dumps(ledger)

    if check_only:
        if not LEDGER_PATH.exists():
            print(f"FAIL: {LEDGER_PATH} does not exist", file=sys.stderr)
            return 1
        current = LEDGER_PATH.read_text(encoding="utf-8")
        if current != text:
            print(f"FAIL: {LEDGER_PATH} is stale relative to its inputs", file=sys.stderr)
            return 1
        print(f"OK: {LEDGER_PATH} matches its deterministic inputs ({len(records)} records)")
        return 0

    LEDGER_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {LEDGER_PATH} ({len(records)} records)")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail if the on-disk ledger is stale relative to its inputs.",
    )
    args = parser.parse_args(argv)
    return run(args.check)


if __name__ == "__main__":
    sys.exit(main())
