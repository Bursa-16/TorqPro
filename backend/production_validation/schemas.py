"""Pydantic request schemas for the production_validation API layer."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ValidationStudyCreate(BaseModel):
    study_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: Optional[str] = None
    study_type: str
    project_id: int
    joint_id: int
    joint_revision_id: int
    calculation_id: int
    calculation_revision_id: int
    source: Optional[str] = None
    notes: Optional[str] = None
    # Specification snapshot captured at study creation time (section 4.4 / ADR 2.5A §3).
    characteristic_name: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    nominal_value: Optional[float] = None
    lower_spec_limit: float
    upper_spec_limit: float
    target_value: Optional[float] = None
    source_standard: Optional[str] = None
    source_document: Optional[str] = None
    source_revision: Optional[str] = None
    rule_pack_version: Optional[str] = None


class ValidationStudyPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class MeasurementDatasetCreate(BaseModel):
    dataset_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    characteristic_name: str = Field(min_length=1)
    characteristic_type: str
    unit: str = Field(min_length=1)
    nominal_value: Optional[float] = None
    lower_spec_limit: float
    upper_spec_limit: float
    target_value: Optional[float] = None
    sampling_strategy: Optional[str] = None
    subgroup_size: Optional[int] = None
    metadata_json: Optional[str] = None


class MeasurementDatasetPatch(BaseModel):
    name: Optional[str] = None
    sampling_strategy: Optional[str] = None
    subgroup_size: Optional[int] = None
    metadata_json: Optional[str] = None


class MeasurementRecordCreate(BaseModel):
    sample_id: str = Field(min_length=1)
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
    tool_code: Optional[str] = None
    measurement_device_code: Optional[str] = None
    operator_reference: Optional[str] = None
    environment_temperature: Optional[float] = None
    environment_humidity: Optional[float] = None
    comment: Optional[str] = None
    correction_of_id: Optional[int] = None


class MeasurementRecordBulkImport(BaseModel):
    filename: str = Field(min_length=1)
    csv_content: str = Field(min_length=1)


class RecordInvalidateIn(BaseModel):
    invalid_reason: str = Field(min_length=1)


class StudyReviewIn(BaseModel):
    notes: Optional[str] = None
