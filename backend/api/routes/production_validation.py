"""Production Validation API (Faz 2.5A).

Thin FastAPI routes. All business logic lives in
backend.production_validation.service; SQL lives in
backend.production_validation.repository.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(tags=["production_validation"])

# `router` is intentionally assigned before these imports: if backend.app ends up
# re-entering this module while it is still mid-import (see backend/api/dependencies.py
# docstring), the partially-initialized module already exposes a usable `router`
# attribute, which breaks the circular-import failure instead of propagating it.
from backend.api.dependencies import user  # noqa: E402
from backend.production_validation import schemas as s  # noqa: E402
from backend.production_validation import service as svc  # noqa: E402
from backend.production_validation.exceptions import (  # noqa: E402
    ConflictError,
    CsvImportError,
    LockedError,
    NotFoundError,
    StateTransitionError,
    ValidationDataError,
)


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc))
    except ConflictError as exc:
        raise HTTPException(409, str(exc))
    except LockedError as exc:
        raise HTTPException(400, str(exc))
    except StateTransitionError as exc:
        raise HTTPException(400, str(exc))
    except CsvImportError as exc:
        raise HTTPException(422, {"message": str(exc), "row_errors": exc.row_errors})
    except ValidationDataError as exc:
        raise HTTPException(422, str(exc))


# ------------------------------------------------------------------ studies

@router.post("/api/validation-studies")
def create_validation_study(x: s.ValidationStudyCreate, u=Depends(user)):
    return _handle(svc.create_study, x, u)


@router.get("/api/validation-studies")
def list_validation_studies(
    project_id: int | None = None, status: str | None = None, u=Depends(user)
):
    return svc.list_studies(project_id, status)


@router.get("/api/validation-studies/{study_id}")
def get_validation_study(study_id: int, u=Depends(user)):
    return _handle(svc.get_study, study_id)


@router.patch("/api/validation-studies/{study_id}")
def patch_validation_study(study_id: int, x: s.ValidationStudyPatch, u=Depends(user)):
    return _handle(svc.patch_study, study_id, x, u)


@router.post("/api/validation-studies/{study_id}/complete")
def complete_validation_study(study_id: int, u=Depends(user)):
    return _handle(svc.complete_study, study_id, u)


@router.post("/api/validation-studies/{study_id}/submit")
def submit_validation_study(study_id: int, u=Depends(user)):
    return _handle(svc.submit_study, study_id, u)


@router.post("/api/validation-studies/{study_id}/approve")
def approve_validation_study(study_id: int, u=Depends(user)):
    return _handle(svc.approve_study, study_id, u)


@router.post("/api/validation-studies/{study_id}/reject")
def reject_validation_study(study_id: int, u=Depends(user)):
    return _handle(svc.reject_study, study_id, u)


@router.post("/api/validation-studies/{study_id}/archive")
def archive_validation_study(study_id: int, u=Depends(user)):
    return _handle(svc.archive_study, study_id, u)


# ---------------------------------------------------------------- datasets

@router.post("/api/validation-studies/{study_id}/datasets")
def create_measurement_dataset(study_id: int, x: s.MeasurementDatasetCreate, u=Depends(user)):
    return _handle(svc.create_dataset, study_id, x, u)


@router.get("/api/validation-studies/{study_id}/datasets")
def list_measurement_datasets(study_id: int, u=Depends(user)):
    return _handle(svc.list_datasets, study_id)


@router.get("/api/measurement-datasets/{dataset_id}")
def get_measurement_dataset(dataset_id: int, u=Depends(user)):
    return _handle(svc.get_dataset, dataset_id)


@router.patch("/api/measurement-datasets/{dataset_id}")
def patch_measurement_dataset(dataset_id: int, x: s.MeasurementDatasetPatch, u=Depends(user)):
    return _handle(svc.patch_dataset, dataset_id, x, u)


@router.post("/api/measurement-datasets/{dataset_id}/lock")
def lock_measurement_dataset(dataset_id: int, u=Depends(user)):
    return _handle(svc.lock_dataset, dataset_id, u)


# ----------------------------------------------------------------- records

@router.post("/api/measurement-datasets/{dataset_id}/records")
def create_measurement_record(dataset_id: int, x: s.MeasurementRecordCreate, u=Depends(user)):
    return _handle(svc.create_record, dataset_id, x, u)


@router.post("/api/measurement-datasets/{dataset_id}/records/bulk")
def bulk_import_measurement_records(
    dataset_id: int, x: s.MeasurementRecordBulkImport, u=Depends(user)
):
    return _handle(svc.import_csv_records, dataset_id, x.filename, x.csv_content, u)


@router.get("/api/measurement-datasets/{dataset_id}/records")
def list_measurement_records(dataset_id: int, u=Depends(user)):
    return _handle(svc.list_records, dataset_id)


@router.post("/api/measurement-records/{record_id}/invalidate")
def invalidate_measurement_record(record_id: int, x: s.RecordInvalidateIn, u=Depends(user)):
    return _handle(svc.invalidate_record, record_id, x.invalid_reason, u)
