from backend.production_validation.models import (
    MeasurementDataset,
    MeasurementRecord,
    SpecificationSnapshot,
    ToolReference,
    ValidationStudy,
)


def test_validation_study_model_round_trip():
    row = {
        "id": 1, "study_code": "VS-1", "name": "Study", "description": None,
        "study_type": "torque_validation", "status": "draft", "project_id": 1,
        "joint_id": 1, "joint_revision_id": 1, "calculation_id": 1,
        "calculation_revision_id": 1, "specification_id": None, "created_by": 1,
        "created_at": "2026-07-22T00:00:00Z", "updated_at": None, "started_at": None,
        "completed_at": None, "approved_at": None, "approved_by": None,
        "source": None, "notes": None, "version": 1,
    }
    model = ValidationStudy(**row)
    assert model.study_code == "VS-1"
    assert model.version == 1


def test_measurement_dataset_model_requires_spec_limits():
    row = {
        "id": 1, "validation_study_id": 1, "dataset_code": "DS-1", "name": "DS",
        "characteristic_name": "torque", "characteristic_type": "tightening_torque",
        "unit": "Nm", "nominal_value": None, "lower_spec_limit": 40.0,
        "upper_spec_limit": 50.0, "target_value": 45.0, "sampling_strategy": None,
        "subgroup_size": None, "source_type": None, "source_filename": None,
        "source_checksum": None, "imported_at": None, "imported_by": None,
        "is_locked": False, "version": 1, "metadata_json": None,
    }
    model = MeasurementDataset(**row)
    assert model.lower_spec_limit < model.upper_spec_limit


def test_measurement_record_model_defaults_valid():
    row = {
        "id": 1, "dataset_id": 1, "sequence_number": 1, "sample_id": "S-1",
        "subgroup_id": None, "measured_value": 45.0, "measured_at": None,
        "production_date": None, "shift": None, "batch_number": None,
        "lot_number": None, "serial_number": None, "part_number": None,
        "station": None, "line": None, "machine": None, "tool_id": None,
        "measurement_device_id": None, "operator_reference": None,
        "environment_temperature": None, "environment_humidity": None,
        "is_valid": True, "invalid_reason": None, "comment": None,
        "correction_of_id": None, "created_at": "2026-07-22T00:00:00Z",
    }
    model = MeasurementRecord(**row)
    assert model.is_valid is True


def test_specification_snapshot_model_requires_calculation_snapshot_id():
    row = {
        "id": 1, "validation_study_id": 1, "characteristic_name": "torque",
        "unit": "Nm", "nominal_value": None, "lower_spec_limit": 40.0,
        "upper_spec_limit": 50.0, "target_value": 45.0, "source_standard": None,
        "source_document": None, "source_revision": None, "rule_pack_version": None,
        "calculation_snapshot_id": 7, "created_at": "2026-07-22T00:00:00Z",
        "snapshot_hash": "abc123",
    }
    model = SpecificationSnapshot(**row)
    assert model.calculation_snapshot_id == 7


def test_tool_reference_model_defaults_active():
    row = {
        "id": 1, "tool_code": "T-1", "name": "Torque Wrench", "manufacturer": None,
        "model": None, "serial_number": None, "tool_type": None, "unit": "Nm",
        "range_min": None, "range_max": None, "calibration_status": None,
        "last_calibration_date": None, "next_calibration_date": None,
        "certificate_reference": None, "active": True,
    }
    model = ToolReference(**row)
    assert model.active is True
