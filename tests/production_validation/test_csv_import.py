from backend.production_validation import service as svc
from backend.production_validation.exceptions import ConflictError, CsvImportError
from tests.production_validation.conftest import create_dataset, create_study

ACTOR = {"id": 1, "role": "admin"}


def _csv(rows, header="sample_id,measured_value"):
    lines = [header] + rows
    return "\n".join(lines) + "\n"


def test_bulk_import_valid_csv():
    study = create_study()
    dataset = create_dataset(study["id"])
    csv_content = _csv(["S-1,45.1", "S-2,44.8", "S-3,45.6"])
    result = svc.import_csv_records(dataset["id"], "batch1.csv", csv_content, ACTOR)
    assert result["imported"] == 3
    records = svc.list_records(dataset["id"])
    assert len(records) == 3
    reloaded = svc.get_dataset(dataset["id"])
    assert reloaded["source_filename"] == "batch1.csv"
    assert reloaded["source_checksum"] == result["checksum"]


def test_missing_required_column_rejected():
    study = create_study()
    dataset = create_dataset(study["id"])
    csv_content = "sample_id\nS-1\n"
    try:
        svc.import_csv_records(dataset["id"], "bad.csv", csv_content, ACTOR)
        assert False, "expected CsvImportError"
    except CsvImportError as exc:
        assert "measured_value" in str(exc)


def test_row_level_errors_reported_and_import_rejected_atomically():
    study = create_study()
    dataset = create_dataset(study["id"])
    csv_content = _csv(["S-1,45.1", "S-2,not-a-number", "S-3,45.6"])
    try:
        svc.import_csv_records(dataset["id"], "partial.csv", csv_content, ACTOR)
        assert False, "expected CsvImportError"
    except CsvImportError as exc:
        assert len(exc.row_errors) == 1
        assert exc.row_errors[0]["line"] == 3
    # Atomic: nothing from this batch was written.
    assert svc.list_records(dataset["id"]) == []


def test_duplicate_sample_id_within_file_rejected():
    study = create_study()
    dataset = create_dataset(study["id"])
    csv_content = _csv(["S-1,45.1", "S-1,45.2"])
    try:
        svc.import_csv_records(dataset["id"], "dupe.csv", csv_content, ACTOR)
        assert False, "expected CsvImportError"
    except CsvImportError as exc:
        assert any("duplicate" in e["errors"][0] for e in exc.row_errors)


def test_reimporting_identical_file_is_rejected():
    study = create_study()
    dataset = create_dataset(study["id"])
    csv_content = _csv(["S-1,45.1"])
    svc.import_csv_records(dataset["id"], "same.csv", csv_content, ACTOR)
    try:
        svc.import_csv_records(dataset["id"], "same.csv", csv_content, ACTOR)
        assert False, "expected ConflictError"
    except ConflictError:
        pass


def test_different_content_can_be_imported_after_first_batch():
    study = create_study()
    dataset = create_dataset(study["id"])
    svc.import_csv_records(dataset["id"], "batch1.csv", _csv(["S-1,45.1"]), ACTOR)
    result = svc.import_csv_records(dataset["id"], "batch2.csv", _csv(["S-2,44.9"]), ACTOR)
    assert result["imported"] == 1
    assert len(svc.list_records(dataset["id"])) == 2


def test_formula_injection_prefix_rejected():
    study = create_study()
    dataset = create_dataset(study["id"])
    csv_content = _csv(["=cmd|'/c calc',45.1"])
    try:
        svc.import_csv_records(dataset["id"], "inject.csv", csv_content, ACTOR)
        assert False, "expected CsvImportError"
    except CsvImportError as exc:
        assert any("formula" in e["errors"][0] for e in exc.row_errors)


def test_unknown_tool_code_reported_as_row_error():
    study = create_study()
    dataset = create_dataset(study["id"])
    csv_content = _csv(["S-1,45.1,,NOPE"], header="sample_id,measured_value,subgroup_id,tool_code")
    try:
        svc.import_csv_records(dataset["id"], "tool.csv", csv_content, ACTOR)
        assert False, "expected CsvImportError"
    except CsvImportError as exc:
        assert any("tool_code" in e["errors"][0] for e in exc.row_errors)


def test_locked_dataset_blocks_bulk_import():
    study = create_study()
    dataset = create_dataset(study["id"])
    svc.lock_dataset(dataset["id"], ACTOR)
    from backend.production_validation.exceptions import LockedError
    try:
        svc.import_csv_records(dataset["id"], "late.csv", _csv(["S-1,45.1"]), ACTOR)
        assert False, "expected LockedError"
    except LockedError:
        pass


def test_decimal_parser_normalizes_comma_separator():
    # The CSV delimiter itself is a comma, so comma-as-decimal-separator only
    # applies to a single numeric token (e.g. a semicolon- or tab-delimited
    # export); this exercises the underlying parser directly.
    assert svc._parse_decimal("45,2") == 45.2
    assert svc._parse_decimal("45.2") == 45.2
    assert svc._parse_decimal(" 45.2 ") == 45.2
