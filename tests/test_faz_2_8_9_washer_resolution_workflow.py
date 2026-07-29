"""Faz 2.8.9 tests (Stage 1): washer resolution decision workflow --
domain model, state machine and validation layer only.

Covers: allowed/forbidden status transitions (including the terminal
and blocked_authoritative_source special cases), decision field
validation (blank note/evidence rejected), decided_at UTC ISO-8601
format enforcement, ``extra="forbid"`` schema closure, and a sanity
check that every ``WasherResolutionStatus`` member is accounted for
by the state machine.

Stage 1 deliberately does not test persistence, checksum computation,
idempotency or the API layer -- those are Stage 2/3 scope. No test in
this file writes to ``washer_resolution_ledger.json`` (Faz 2.8.5
source ledger) or changes the status of any of the real 76 records;
all transitions below are exercised against status *values* directly,
never against the real ledger's data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.library import washer_resolution as wr
from backend.library import washer_resolution_decisions as wrd


# ---------------------------------------------------------------------
# State machine: allowed transitions
# ---------------------------------------------------------------------


class TestAllowedTransitions:
    @pytest.mark.parametrize(
        "previous,new",
        [
            (wr.WasherResolutionStatus.OPEN, wr.WasherResolutionStatus.UNDER_REVIEW),
            (wr.WasherResolutionStatus.OPEN, wr.WasherResolutionStatus.RESOLVED),
            (wr.WasherResolutionStatus.OPEN, wr.WasherResolutionStatus.ACCEPTED_AS_IS),
            (wr.WasherResolutionStatus.OPEN, wr.WasherResolutionStatus.REJECTED),
            (wr.WasherResolutionStatus.UNDER_REVIEW, wr.WasherResolutionStatus.OPEN),
            (wr.WasherResolutionStatus.UNDER_REVIEW, wr.WasherResolutionStatus.RESOLVED),
            (wr.WasherResolutionStatus.UNDER_REVIEW, wr.WasherResolutionStatus.ACCEPTED_AS_IS),
            (wr.WasherResolutionStatus.UNDER_REVIEW, wr.WasherResolutionStatus.REJECTED),
        ],
    )
    def test_transition_is_allowed(self, previous, new):
        assert wrd.is_transition_allowed(previous, new) is True
        # Should not raise.
        wrd.validate_transition(previous, new, resolution_id="RES-TEST-0001")


class TestForbiddenTransitions:
    @pytest.mark.parametrize(
        "previous,new",
        [
            # Terminal statuses: no outgoing transition at all (reopen
            # is explicitly out of scope for this phase).
            (wr.WasherResolutionStatus.RESOLVED, wr.WasherResolutionStatus.OPEN),
            (wr.WasherResolutionStatus.RESOLVED, wr.WasherResolutionStatus.UNDER_REVIEW),
            (wr.WasherResolutionStatus.ACCEPTED_AS_IS, wr.WasherResolutionStatus.OPEN),
            (wr.WasherResolutionStatus.REJECTED, wr.WasherResolutionStatus.RESOLVED),
            # No self-transitions anywhere in the table.
            (wr.WasherResolutionStatus.OPEN, wr.WasherResolutionStatus.OPEN),
            (wr.WasherResolutionStatus.RESOLVED, wr.WasherResolutionStatus.RESOLVED),
        ],
    )
    def test_transition_is_forbidden(self, previous, new):
        assert wrd.is_transition_allowed(previous, new) is False
        with pytest.raises(wrd.InvalidTransitionError):
            wrd.validate_transition(previous, new, resolution_id="RES-TEST-0002")

    def test_terminal_statuses_have_empty_transition_set(self):
        for status in wr.TERMINAL_STATUSES:
            assert wrd.ALLOWED_TRANSITIONS.get(status, frozenset()) == frozenset()


class TestBlockedAuthoritativeSource:
    def test_is_blocked_source_status(self):
        assert (
            wrd.is_blocked_source_status(
                wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE
            )
            is True
        )
        assert wrd.is_blocked_source_status(wr.WasherResolutionStatus.OPEN) is False

    def test_blocked_source_has_no_transitions_in_table(self):
        assert (
            wrd.ALLOWED_TRANSITIONS.get(
                wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE, frozenset()
            )
            == frozenset()
        )

    def test_blocked_source_raises_specific_error_not_generic(self):
        with pytest.raises(wrd.BlockedRecordDecisionError) as exc_info:
            wrd.validate_transition(
                wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE,
                wr.WasherResolutionStatus.RESOLVED,
                resolution_id="RES-WASH-ISO7093-M10",
            )
        assert exc_info.value.resolution_id == "RES-WASH-ISO7093-M10"
        # Must not also be reported as InvalidTransitionError.
        assert not isinstance(exc_info.value, wrd.InvalidTransitionError)

    def test_real_blocked_ledger_records_are_rejected(self):
        """Exercises the real Faz 2.8.5 ledger's 5 blocked records
        (read-only) to confirm every one of them is rejected by the
        state machine -- without changing any of their statuses."""
        blocked = wr.resolutions_by_status(
            wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE
        )
        assert len(blocked) == 5
        for record in blocked:
            with pytest.raises(wrd.BlockedRecordDecisionError):
                wrd.validate_transition(
                    record.resolution_status,
                    wr.WasherResolutionStatus.RESOLVED,
                    resolution_id=record.resolution_id,
                )
            # Confirm this test made no persistent change.
            assert (
                record.resolution_status
                == wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE
            )


class TestStateMachineCompleteness:
    def test_every_status_is_accounted_for(self):
        accounted = set(wrd.ALLOWED_TRANSITIONS.keys()) | wr.TERMINAL_STATUSES | {
            wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE
        }
        assert accounted == set(wr.WasherResolutionStatus)


# ---------------------------------------------------------------------
# Decision field validation (note / evidence required)
# ---------------------------------------------------------------------


class TestDecisionFieldValidation:
    def test_valid_fields_pass(self):
        wrd.validate_decision_fields(
            resolution_note="Verified against manufacturer catalog page 12.",
            evidence_reference="https://example.com/catalog.pdf#page=12",
        )

    @pytest.mark.parametrize("note", ["", "   ", "\t\n"])
    def test_blank_note_rejected(self, note):
        with pytest.raises(wrd.MissingEvidenceError) as exc_info:
            wrd.validate_decision_fields(
                resolution_note=note, evidence_reference="some evidence"
            )
        assert "resolution_note" in exc_info.value.missing_fields

    @pytest.mark.parametrize("evidence", ["", "   "])
    def test_blank_evidence_rejected(self, evidence):
        with pytest.raises(wrd.MissingEvidenceError) as exc_info:
            wrd.validate_decision_fields(
                resolution_note="some note", evidence_reference=evidence
            )
        assert "evidence_reference" in exc_info.value.missing_fields

    def test_both_blank_reports_both(self):
        with pytest.raises(wrd.MissingEvidenceError) as exc_info:
            wrd.validate_decision_fields(resolution_note="", evidence_reference="")
        assert exc_info.value.missing_fields == frozenset(
            {"resolution_note", "evidence_reference"}
        )


# ---------------------------------------------------------------------
# decided_at format validation
# ---------------------------------------------------------------------


class TestDecidedAtFormat:
    @pytest.mark.parametrize(
        "value",
        [
            "2026-07-29T12:00:00Z",
            "2026-07-29T12:00:00.123456Z",
            "2026-07-29T12:00:00.1Z",
        ],
    )
    def test_valid_utc_iso8601(self, value):
        assert wrd.is_valid_utc_iso8601(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "2026-07-29T12:00:00",  # missing Z
            "2026-07-29T12:00:00+03:00",  # non-UTC offset
            "2026-07-29 12:00:00Z",  # missing 'T'
            "29-07-2026T12:00:00Z",  # wrong date order
            "not-a-date",
            "",
        ],
    )
    def test_invalid_utc_iso8601(self, value):
        assert wrd.is_valid_utc_iso8601(value) is False


# ---------------------------------------------------------------------
# WasherResolutionDecision model
# ---------------------------------------------------------------------


def _valid_decision_kwargs(**overrides):
    base = dict(
        decision_id="DEC-0001",
        resolution_id="RES-TEST-0001",
        previous_status=wr.WasherResolutionStatus.OPEN,
        new_status=wr.WasherResolutionStatus.UNDER_REVIEW,
        resolution_note="Escalated for secondary source review.",
        evidence_reference="internal-review-log#2026-07-29",
        resolved_by="ilhan",
        decided_at="2026-07-29T12:00:00Z",
        confidence_level=None,
        integrity_checksum="a" * 64,
    )
    base.update(overrides)
    return base


class TestWasherResolutionDecisionModel:
    def test_valid_decision_parses(self):
        decision = wrd.WasherResolutionDecision(**_valid_decision_kwargs())
        assert decision.decision_id == "DEC-0001"
        assert decision.previous_status == wr.WasherResolutionStatus.OPEN

    def test_extra_field_rejected(self):
        kwargs = _valid_decision_kwargs()
        kwargs["inner_diameter_mm"] = 10.5
        with pytest.raises(ValidationError):
            wrd.WasherResolutionDecision(**kwargs)

    def test_blank_resolution_note_rejected(self):
        with pytest.raises(ValidationError):
            wrd.WasherResolutionDecision(**_valid_decision_kwargs(resolution_note="  "))

    def test_blank_evidence_reference_rejected(self):
        with pytest.raises(ValidationError):
            wrd.WasherResolutionDecision(
                **_valid_decision_kwargs(evidence_reference="")
            )

    def test_non_utc_decided_at_rejected(self):
        with pytest.raises(ValidationError):
            wrd.WasherResolutionDecision(
                **_valid_decision_kwargs(decided_at="2026-07-29T12:00:00+03:00")
            )

    def test_blank_checksum_rejected(self):
        with pytest.raises(ValidationError):
            wrd.WasherResolutionDecision(**_valid_decision_kwargs(integrity_checksum=""))

    def test_confidence_level_optional(self):
        decision = wrd.WasherResolutionDecision(
            **_valid_decision_kwargs(confidence_level=wr.ConfidenceLevel.G2)
        )
        assert decision.confidence_level == wr.ConfidenceLevel.G2

    def test_to_dict_is_json_safe(self):
        decision = wrd.WasherResolutionDecision(**_valid_decision_kwargs())
        payload = decision.to_dict()
        json.dumps(payload)  # must not raise
        assert payload["previous_status"] == "open"
        assert payload["new_status"] == "under_review"


# ---------------------------------------------------------------------
# Seed ledger file (Stage 1: schema only, persistence in Stage 2)
# ---------------------------------------------------------------------


class TestSeedDecisionLedgerFile:
    def test_seed_file_exists_and_is_empty(self):
        path = (
            Path(__file__).resolve().parent.parent
            / "backend"
            / "library"
            / "data"
            / "washer_resolution_decisions.json"
        )
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["decisions"] == []
        assert payload["metadata"]["record_count"] == 0

    def test_seed_file_never_touches_source_ledger(self):
        path = (
            Path(__file__).resolve().parent.parent
            / "backend"
            / "library"
            / "data"
            / "washer_resolution_decisions.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert (
            payload["metadata"]["source_ledger"]
            == "backend/library/data/washer_resolution_ledger.json"
        )

    def test_source_ledger_untouched_76_records_same_status_counts(self):
        """Regression guard: this and every later Faz 2.8.9 stage must
        leave the Faz 2.8.5 source ledger's status distribution
        exactly as-is (71 open, 5 blocked_authoritative_source)."""
        wr.reload()
        counts = wr.count_by_status()
        assert counts[wr.WasherResolutionStatus.OPEN.value] == 71
        assert counts[wr.WasherResolutionStatus.BLOCKED_AUTHORITATIVE_SOURCE.value] == 5
        assert counts[wr.WasherResolutionStatus.RESOLVED.value] == 0
        assert counts[wr.WasherResolutionStatus.ACCEPTED_AS_IS.value] == 0
        assert counts[wr.WasherResolutionStatus.REJECTED.value] == 0
        assert counts[wr.WasherResolutionStatus.UNDER_REVIEW.value] == 0
