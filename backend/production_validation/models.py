"""Pydantic read models mirroring the production_validation SQLite rows.

These are output/representation models, not ORM classes. Rows are read via
backend.production_validation.repository as sqlite3.Row/dict and adapted
into these models where a typed shape is useful (tests, internal service
consumers). API responses may return the raw dict for compatibility with
the rest of the codebase's convention (see backend/app.py).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ValidationStudy(BaseModel):
    id: int
    study_code: str
    name: str
    description: Optional[str] = None
    study_type: str
    status: str
    project_id: int
    joint_id: int
    joint_revision_id: int
    calculation_id: int
    calculation_revision_id: int
    specification_id: Optional[int] = None
    created_by: Optional[int] = None
    created_at: str
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    approved_at: Optional[str] = None
    approved_by: Optional[int] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    version: int = 1


class MeasurementDataset(BaseModel):
    id: int
    validation_study_id: int
    dataset_code: str
    name: str
    characteristic_name: str
    characteristic_type: str
    unit: str
    nominal_value: Optional[float] = None
    lower_spec_limit: float
    upper_spec_limit: float
    target_value: Optional[float] = None
    sampling_strategy: Optional[str] = None
    subgroup_size: Optional[int] = None
    source_type: Optional[str] = None
    source_filename: Optional[str] = None
    source_checksum: Optional[str] = None
    imported_at: Optional[str] = None
    imported_by: Optional[int] = None
    is_locked: bool = False
    version: int = 1
    metadata_json: Optional[str] = None


class MeasurementRecord(BaseModel):
    id: int
    dataset_id: int
    sequence_number: int
    sample_id: str
    subgroup_id: Optional[str] = None
    measured_value: float
    measured_at: Optional[str] = None
    production_date: Optional[str] = None
    shift: Optional[str] = None
    batch_number: Optional[str] = None
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    part_number: Optional[str] = None
    station: Optional[str] = None
    line: Optional[str] = None
    machine: Optional[str] = None
    tool_id: Optional[int] = None
    measurement_device_id: Optional[int] = None
    operator_reference: Optional[str] = None
    environment_temperature: Optional[float] = None
    environment_humidity: Optional[float] = None
    is_valid: bool = True
    invalid_reason: Optional[str] = None
    comment: Optional[str] = None
    correction_of_id: Optional[int] = None
    created_at: str


class SpecificationSnapshot(BaseModel):
    id: int
    validation_study_id: int
    characteristic_name: str
    unit: str
    nominal_value: Optional[float] = None
    lower_spec_limit: float
    upper_spec_limit: float
    target_value: Optional[float] = None
    source_standard: Optional[str] = None
    source_document: Optional[str] = None
    source_revision: Optional[str] = None
    rule_pack_version: Optional[str] = None
    calculation_snapshot_id: int
    created_at: str
    snapshot_hash: str


class ToolReference(BaseModel):
    id: int
    tool_code: str
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    tool_type: Optional[str] = None
    unit: Optional[str] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    calibration_status: Optional[str] = None
    last_calibration_date: Optional[str] = None
    next_calibration_date: Optional[str] = None
    certificate_reference: Optional[str] = None
    active: bool = True
