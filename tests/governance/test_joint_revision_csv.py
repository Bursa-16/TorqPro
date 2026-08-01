"""Faz 2.8.16 Stage 3 tests: backend.governance.joint_revision_csv.

Domain/service-layer tests only -- no HTTP, no TestClient. Mirrors
``tests/governance/test_joint_revision_query.py``'s two fixture
styles: directly-constructed ``JointRevisionProjection`` instances
for serializer-only tests (no DB involved at all -- these test
``serialize_joint_revision_projections_csv`` directly), and
monkeypatched ``project_joint_revisions_bulk`` (patched at the point
``backend.governance.joint_revision_query`` imported it -- the same
choke point Stage 1's own tests patch) for query-reuse scenarios that
exercise ``export_joint_revision_projections_csv``'s full pipeline.
"""

from __future__ import annotations

import csv
import io

import pytest

from backend.governance import joint_revision_query as jrq
from backend.governance.adapters.joint_revision import JointRevisionProjection
from backend.governance.enums import LifecycleGroup
from backend.governance.joint_revision_csv import (
    CSV_COLUMNS,
    UTF8_BOM,
    export_joint_revision_projections_csv,
    serialize_joint_revision_projections_csv,
)
from backend.governance.joint_revision_query import JointRevisionQueryValidationError


def _projection(
    joint_revision_id,
    outcome="supported",
    source_status=None,
    canonical_status=None,
    lifecycle_group=None,
    safe_reason=None,
):
    return JointRevisionProjection(
        joint_revision_id=joint_revision_id,
        outcome=outcome,
        source_status=source_status,
        canonical_status=canonical_status,
        lifecycle_group=lifecycle_group,
        safe_reason=safe_reason,
    )


def _patch_bulk(monkeypatch, projections):
    def _fake_bulk(joint_id=None):
        return list(projections)

    monkeypatch.setattr(jrq, "project_joint_revisions_bulk", _fake_bulk)


def _decode_rows(csv_bytes: bytes):
    text = csv_bytes.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


# ---------------------------------------------------------------------
# Header and basic serialization
# ---------------------------------------------------------------------


def test_header_row_matches_csv_columns_exactly():
    csv_bytes = serialize_joint_revision_projections_csv([])
    rows = _decode_rows(csv_bytes)
    assert rows[0] == list(CSV_COLUMNS)


def test_empty_result_is_header_only():
    csv_bytes = serialize_joint_revision_projections_csv([])
    rows = _decode_rows(csv_bytes)
    assert len(rows) == 1


def test_single_record_serializes_correctly():
    p = _projection(
        1, outcome="supported", source_status="approved", canonical_status="approved",
        lifecycle_group=LifecycleGroup.REVIEW,
    )
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1] == ["1", "joint_revision", "approved", "review", "approved", "supported", ""]


def test_multiple_records_serialize_in_given_order():
    p1 = _projection(1)
    p2 = _projection(2)
    p3 = _projection(3)
    csv_bytes = serialize_joint_revision_projections_csv([p1, p2, p3])
    rows = _decode_rows(csv_bytes)
    ids = [row[0] for row in rows[1:]]
    assert ids == ["1", "2", "3"]


def test_output_ends_with_rfc4180_line_terminator():
    csv_bytes = serialize_joint_revision_projections_csv([_projection(1)])
    text = csv_bytes.decode("utf-8-sig")
    assert text.endswith("\r\n")


def test_row_line_terminator_is_crlf():
    csv_bytes = serialize_joint_revision_projections_csv([_projection(1), _projection(2)])
    text = csv_bytes.decode("utf-8-sig")
    assert "\r\n" in text
    # every physical line break in this document is \r\n (no lone \n)
    body = text.replace("\r\n", "")
    assert "\n" not in body


def test_integer_field_renders_as_plain_decimal_string():
    csv_bytes = serialize_joint_revision_projections_csv([_projection(12345)])
    rows = _decode_rows(csv_bytes)
    assert rows[1][0] == "12345"


def test_none_fields_render_as_empty_string():
    p = _projection(1, source_status=None, canonical_status=None, safe_reason=None)
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][2] == ""
    assert rows[1][4] == ""
    assert rows[1][6] == ""


def test_none_fields_never_render_as_literal_none_text():
    p = _projection(1, safe_reason=None)
    csv_bytes = serialize_joint_revision_projections_csv([p])
    text = csv_bytes.decode("utf-8-sig")
    assert "None" not in text


# ---------------------------------------------------------------------
# Quoting
# ---------------------------------------------------------------------


def test_comma_in_safe_reason_is_quoted_correctly():
    p = _projection(1, outcome="not_found", safe_reason="reason, with a comma")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == "reason, with a comma"


def test_double_quote_in_safe_reason_is_escaped_correctly():
    p = _projection(1, outcome="not_found", safe_reason='reason with "quotes"')
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == 'reason with "quotes"'


def test_newline_in_safe_reason_is_quoted_correctly():
    p = _projection(1, outcome="not_found", safe_reason="line one\nline two")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == "line one\nline two"


def test_carriage_return_in_safe_reason_is_quoted_correctly():
    p = _projection(1, outcome="not_found", safe_reason="line one\rline two")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == "line one\rline two"


def test_comma_and_quote_together_are_quoted_correctly():
    p = _projection(1, outcome="not_found", safe_reason='has, a comma and "quotes"')
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == 'has, a comma and "quotes"'


def test_unicode_turkish_characters_are_preserved():
    p = _projection(1, outcome="not_found", safe_reason="Onaylı revizyon bulunamadı, çözülemedi")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == "Onaylı revizyon bulunamadı, çözülemedi"


# ---------------------------------------------------------------------
# CSV injection protection
# ---------------------------------------------------------------------


@pytest.mark.parametrize("trigger", ["=", "+", "-", "@"])
def test_formula_trigger_characters_are_guarded(trigger):
    p = _projection(1, outcome="not_found", safe_reason=f"{trigger}HYPERLINK(\"evil\")")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == f"'{trigger}HYPERLINK(\"evil\")"


def test_leading_whitespace_plus_formula_prefix_is_guarded():
    p = _projection(1, outcome="not_found", safe_reason="   =SUM(1,1)")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == "'   =SUM(1,1)"


def test_leading_tab_bypass_is_guarded():
    p = _projection(1, outcome="not_found", safe_reason="\t=SUM(1,1)")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6].startswith("'")


def test_leading_carriage_return_bypass_is_guarded():
    p = _projection(1, outcome="not_found", safe_reason="\r=SUM(1,1)")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6].startswith("'")


def test_normal_text_is_not_altered():
    p = _projection(1, outcome="not_found", safe_reason="a perfectly normal reason")
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][6] == "a perfectly normal reason"


def test_numeric_joint_revision_id_is_never_guarded():
    p = _projection(1)
    csv_bytes = serialize_joint_revision_projections_csv([p])
    rows = _decode_rows(csv_bytes)
    assert rows[1][0] == "1"
    assert not rows[1][0].startswith("'")


def test_serialization_does_not_mutate_original_projection():
    p = _projection(1, outcome="not_found", safe_reason="=SUM(1,1)")
    before = p.model_copy()
    serialize_joint_revision_projections_csv([p])
    assert p == before


# ---------------------------------------------------------------------
# Query reuse
# ---------------------------------------------------------------------


_SUPPORTED_APPROVED = _projection(
    1, outcome="supported", source_status="approved", canonical_status="approved",
)
_SUPPORTED_DRAFT = _projection(
    2, outcome="supported", source_status="draft", canonical_status="draft",
)


def test_export_applies_search(monkeypatch):
    _patch_bulk(monkeypatch, [_SUPPORTED_APPROVED, _SUPPORTED_DRAFT])
    csv_bytes = export_joint_revision_projections_csv(search="approved")
    rows = _decode_rows(csv_bytes)
    assert len(rows) == 2  # header + 1 match
    assert rows[1][0] == "1"


def test_export_applies_ascending_sort(monkeypatch):
    projections = [_projection(3), _projection(1), _projection(2)]
    _patch_bulk(monkeypatch, projections)
    csv_bytes = export_joint_revision_projections_csv(sort_by="joint_revision_id", sort_order="asc")
    rows = _decode_rows(csv_bytes)
    ids = [row[0] for row in rows[1:]]
    assert ids == ["1", "2", "3"]


def test_export_applies_descending_sort(monkeypatch):
    projections = [_projection(3), _projection(1), _projection(2)]
    _patch_bulk(monkeypatch, projections)
    csv_bytes = export_joint_revision_projections_csv(
        sort_by="joint_revision_id", sort_order="desc"
    )
    rows = _decode_rows(csv_bytes)
    ids = [row[0] for row in rows[1:]]
    assert ids == ["3", "2", "1"]


def test_export_applies_joint_id_filter(monkeypatch):
    calls = {}

    def _fake_bulk(joint_id=None):
        calls["joint_id"] = joint_id
        return []

    monkeypatch.setattr(jrq, "project_joint_revisions_bulk", _fake_bulk)
    export_joint_revision_projections_csv(joint_id=55)
    assert calls["joint_id"] == 55


def test_export_applies_search_and_sort_together(monkeypatch):
    projections = [
        _projection(3, outcome="supported", source_status="approved"),
        _projection(1, outcome="supported", source_status="approved"),
        _projection(2, outcome="supported", source_status="draft"),
    ]
    _patch_bulk(monkeypatch, projections)
    csv_bytes = export_joint_revision_projections_csv(
        search="approved", sort_by="joint_revision_id", sort_order="asc"
    )
    rows = _decode_rows(csv_bytes)
    ids = [row[0] for row in rows[1:]]
    assert ids == ["1", "3"]


def test_export_is_not_limited_by_pagination_defaults(monkeypatch):
    projections = [_projection(i) for i in range(1, 51)]
    _patch_bulk(monkeypatch, projections)
    csv_bytes = export_joint_revision_projections_csv()
    rows = _decode_rows(csv_bytes)
    assert len(rows) - 1 == 50  # header + 50 data rows, default page_size=25 would truncate


def test_export_exceeds_max_page_size_without_truncation(monkeypatch):
    projections = [_projection(i) for i in range(1, jrq.MAX_PAGE_SIZE + 51)]
    _patch_bulk(monkeypatch, projections)
    csv_bytes = export_joint_revision_projections_csv()
    rows = _decode_rows(csv_bytes)
    assert len(rows) - 1 == jrq.MAX_PAGE_SIZE + 50


def test_export_invalid_sort_by_raises_validation_error(monkeypatch):
    _patch_bulk(monkeypatch, [])
    with pytest.raises(JointRevisionQueryValidationError):
        export_joint_revision_projections_csv(sort_by="not_a_field")


def test_export_invalid_sort_order_raises_validation_error(monkeypatch):
    _patch_bulk(monkeypatch, [])
    with pytest.raises(JointRevisionQueryValidationError):
        export_joint_revision_projections_csv(sort_order="sideways")


def test_export_source_unavailable_produces_header_only_csv(monkeypatch):
    import backend.joints.service as joints_service_module

    def _boom(joint_id=None):
        raise RuntimeError("simulated sqlite3.OperationalError: disk I/O error at /secret/path")

    monkeypatch.setattr(joints_service_module, "list_joint_revisions", _boom)

    csv_bytes = export_joint_revision_projections_csv()
    rows = _decode_rows(csv_bytes)
    assert len(rows) == 1
    assert rows[0] == list(CSV_COLUMNS)
    text = csv_bytes.decode("utf-8-sig")
    assert "/secret/path" not in text
    assert "OperationalError" not in text


# ---------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------


def test_same_input_produces_identical_bytes_twice():
    projections = [_projection(1), _projection(2)]
    first = serialize_joint_revision_projections_csv(projections)
    second = serialize_joint_revision_projections_csv(projections)
    assert first == second


def test_same_filtered_set_in_different_source_order_yields_same_csv(monkeypatch):
    ordered_a = [_projection(1), _projection(2), _projection(3)]
    ordered_b = [_projection(3), _projection(1), _projection(2)]

    _patch_bulk(monkeypatch, ordered_a)
    csv_a = export_joint_revision_projections_csv(sort_by="joint_revision_id", sort_order="asc")

    _patch_bulk(monkeypatch, ordered_b)
    csv_b = export_joint_revision_projections_csv(sort_by="joint_revision_id", sort_order="asc")

    assert csv_a == csv_b


def test_column_order_is_stable_across_calls():
    csv_bytes_1 = serialize_joint_revision_projections_csv([])
    csv_bytes_2 = serialize_joint_revision_projections_csv([_projection(1)])
    rows_1 = _decode_rows(csv_bytes_1)
    rows_2 = _decode_rows(csv_bytes_2)
    assert rows_1[0] == rows_2[0] == list(CSV_COLUMNS)


def test_output_begins_with_utf8_bom():
    csv_bytes = serialize_joint_revision_projections_csv([])
    assert csv_bytes.startswith(UTF8_BOM)


def test_bom_appears_exactly_once():
    csv_bytes = serialize_joint_revision_projections_csv([_projection(1)])
    assert csv_bytes.count(UTF8_BOM) == 1
