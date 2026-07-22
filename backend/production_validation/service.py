"""Business logic for the production_validation module.

Route handlers (backend/api/routes/production_validation.py) call only
this module. This module owns transactions, state transitions and calls
into repository.py for SQL and joints.service for joint-side reads.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json

from backend.app import audit, conn, now_iso
from backend.production_validation import repository as repo
from backend.production_validation import validators as v
from backend.production_validation.enums import (
    APPROVAL_ROLES,
    STUDY_TRANSITIONS,
)
from backend.production_validation.exceptions import (
    ConflictError,
    CsvImportError,
    LockedError,
    NotFoundError,
    StateTransitionError,
    ValidationDataError,
)

MAX_CSV_ROWS = 20000
MAX_CSV_BYTES = 5_000_000
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_CSV_REQUIRED_COLUMNS = ("sample_id", "measured_value")
_CSV_OPTIONAL_COLUMNS = (
    "sequence_number", "subgroup_id", "measured_at", "production_date", "shift",
    "batch_number", "lot_number", "serial_number", "part_number", "station",
    "line", "machine", "tool_code", "operator_reference", "comment",
)


def _row(r):
    return dict(r) if r is not None else None


def _snapshot_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _require_role(actor: dict, roles=APPROVAL_ROLES) -> None:
    if actor.get("role") not in roles:
        raise ValidationDataError("actor role is not authorized for this operation")


# ------------------------------------------------------------------ studies

def create_study(payload, actor: dict) -> dict:
    v.validate_study_type(payload.study_type)
    v.validate_spec_limits(payload.lower_spec_limit, payload.upper_spec_limit, payload.target_value)
    v.validate_unit_present(payload.unit)

    with conn() as c:
        if c.execute("SELECT 1 FROM projects WHERE id=?", (payload.project_id,)).fetchone() is None:
            raise NotFoundError(f"project {payload.project_id} not found")
        joint = c.execute("SELECT * FROM joints WHERE id=?", (payload.joint_id,)).fetchone()
        if joint is None:
            raise NotFoundError(f"joint {payload.joint_id} not found")
        if joint["project_id"] != payload.project_id:
            raise ValidationDataError("joint.project_id must equal validation_study.project_id")
        joint_rev = c.execute(
            "SELECT * FROM joint_revisions WHERE id=?", (payload.joint_revision_id,)
        ).fetchone()
        if joint_rev is None:
            raise NotFoundError(f"joint_revision {payload.joint_revision_id} not found")
        if joint_rev["joint_id"] != payload.joint_id:
            raise ValidationDataError(
                "joint_revision.joint_id must equal validation_study.joint_id"
            )
        calc = c.execute(
            "SELECT * FROM calculations WHERE id=?", (payload.calculation_id,)
        ).fetchone()
        if calc is None:
            raise NotFoundError(f"calculation {payload.calculation_id} not found")
        calc_rev = c.execute(
            "SELECT * FROM calculation_revisions WHERE id=?", (payload.calculation_revision_id,)
        ).fetchone()
        if calc_rev is None:
            raise NotFoundError(f"calculation_revision {payload.calculation_revision_id} not found")
        if calc_rev["calculation_id"] != payload.calculation_id:
            raise ValidationDataError(
                "calculation_revision.calculation_id must equal validation_study.calculation_id"
            )
        if repo.fetch_study_by_code(c, payload.study_code) is not None:
            raise ConflictError(f"study_code '{payload.study_code}' already exists")

        ts = now_iso()
        c.execute(
            "INSERT INTO validation_studies(study_code,name,description,study_type,status,"
            "project_id,joint_id,joint_revision_id,calculation_id,calculation_revision_id,"
            "created_by,created_at,updated_at,source,notes,version) "
            "VALUES(?,?,?,?,'draft',?,?,?,?,?,?,?,?,?,?,1)",
            (
                payload.study_code, payload.name, payload.description, payload.study_type,
                payload.project_id, payload.joint_id, payload.joint_revision_id,
                payload.calculation_id, payload.calculation_revision_id,
                actor.get("id"), ts, ts, payload.source, payload.notes,
            ),
        )
        study_id = c.execute("SELECT last_insert_rowid() id").fetchone()["id"]

        snapshot_payload = {
            "validation_study_id": study_id,
            "characteristic_name": payload.characteristic_name,
            "unit": payload.unit,
            "nominal_value": payload.nominal_value,
            "lower_spec_limit": payload.lower_spec_limit,
            "upper_spec_limit": payload.upper_spec_limit,
            "target_value": payload.target_value,
            "source_standard": payload.source_standard,
            "source_document": payload.source_document,
            "source_revision": payload.source_revision,
            "rule_pack_version": payload.rule_pack_version,
            "calculation_snapshot_id": payload.calculation_revision_id,
        }
        snap_hash = _snapshot_hash(snapshot_payload)
        c.execute(
            "INSERT INTO specification_snapshots(validation_study_id,characteristic_name,unit,"
            "nominal_value,lower_spec_limit,upper_spec_limit,target_value,source_standard,"
            "source_document,source_revision,rule_pack_version,calculation_snapshot_id,"
            "created_at,snapshot_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                study_id, payload.characteristic_name, payload.unit, payload.nominal_value,
                payload.lower_spec_limit, payload.upper_spec_limit, payload.target_value,
                payload.source_standard, payload.source_document, payload.source_revision,
                payload.rule_pack_version, payload.calculation_revision_id, ts, snap_hash,
            ),
        )
        spec_id = c.execute("SELECT last_insert_rowid() id").fetchone()["id"]
        c.execute(
            "UPDATE validation_studies SET specification_id=? WHERE id=?", (spec_id, study_id)
        )
        c.commit()
        row = repo.fetch_study(c, study_id)
    audit(actor.get("id"), "validation_study_create", payload.study_code)
    return _row(row)


def get_study(study_id: int) -> dict:
    with conn() as c:
        row = repo.fetch_study(c, study_id)
    if row is None:
        raise NotFoundError(f"validation_study {study_id} not found")
    return _row(row)


def list_studies(project_id: int | None = None, status: str | None = None) -> list:
    with conn() as c:
        rows = repo.list_studies(c, project_id, status)
    return [_row(r) for r in rows]


def patch_study(study_id: int, payload, actor: dict) -> dict:
    study = get_study(study_id)
    if study["status"] == "approved":
        raise LockedError("an approved validation study cannot be modified")
    fields = payload.dict(exclude_unset=True)
    if not fields:
        return study
    with conn() as c:
        sets = ",".join(f"{k}=?" for k in fields)
        c.execute(
            f"UPDATE validation_studies SET {sets},updated_at=? WHERE id=?",
            (*fields.values(), now_iso(), study_id),
        )
        c.commit()
        row = repo.fetch_study(c, study_id)
    audit(actor.get("id"), "validation_study_patch", str(study_id))
    return _row(row)


def complete_study(study_id: int, actor: dict) -> dict:
    study = get_study(study_id)
    if "completed" not in STUDY_TRANSITIONS.get(study["status"], set()):
        raise StateTransitionError(f"cannot complete a study in status '{study['status']}'")
    with conn() as c:
        datasets = repo.list_datasets(c, study_id)
        total_valid = 0
        for ds in datasets:
            _, valid = repo.count_records(c, ds["id"])
            total_valid += valid
        if total_valid < 1:
            raise ValidationDataError(
                "study cannot be completed without at least one valid measurement"
            )
        ts = now_iso()
        c.execute(
            "UPDATE validation_studies SET status='completed',completed_at=?,updated_at=? "
            "WHERE id=?",
            (ts, ts, study_id),
        )
        c.commit()
        row = repo.fetch_study(c, study_id)
    audit(actor.get("id"), "validation_study_complete", str(study_id))
    return _row(row)


def submit_study(study_id: int, actor: dict) -> dict:
    study = get_study(study_id)
    if "under_review" not in STUDY_TRANSITIONS.get(study["status"], set()):
        raise StateTransitionError(f"cannot submit a study in status '{study['status']}'")
    with conn() as c:
        c.execute(
            "UPDATE validation_studies SET status='under_review',updated_at=? WHERE id=?",
            (now_iso(), study_id),
        )
        c.commit()
        row = repo.fetch_study(c, study_id)
    audit(actor.get("id"), "validation_study_submit", str(study_id))
    return _row(row)


def approve_study(study_id: int, actor: dict) -> dict:
    _require_role(actor)
    study = get_study(study_id)
    if "approved" not in STUDY_TRANSITIONS.get(study["status"], set()):
        raise StateTransitionError(f"cannot approve a study in status '{study['status']}'")
    if study["created_by"] == actor.get("id"):
        raise ValidationDataError("an approver cannot approve their own study")
    ts = now_iso()
    with conn() as c:
        c.execute(
            "UPDATE validation_studies SET status='approved',approved_at=?,approved_by=?,"
            "updated_at=? WHERE id=?",
            (ts, actor.get("id"), ts, study_id),
        )
        c.commit()
        row = repo.fetch_study(c, study_id)
    audit(actor.get("id"), "validation_study_approve", str(study_id))
    return _row(row)


def reject_study(study_id: int, actor: dict) -> dict:
    _require_role(actor)
    study = get_study(study_id)
    if "rejected" not in STUDY_TRANSITIONS.get(study["status"], set()):
        raise StateTransitionError(f"cannot reject a study in status '{study['status']}'")
    with conn() as c:
        c.execute(
            "UPDATE validation_studies SET status='rejected',updated_at=? WHERE id=?",
            (now_iso(), study_id),
        )
        c.commit()
        row = repo.fetch_study(c, study_id)
    audit(actor.get("id"), "validation_study_reject", str(study_id))
    return _row(row)


def archive_study(study_id: int, actor: dict) -> dict:
    study = get_study(study_id)
    if "archived" not in STUDY_TRANSITIONS.get(study["status"], set()):
        raise StateTransitionError(f"cannot archive a study in status '{study['status']}'")
    with conn() as c:
        c.execute(
            "UPDATE validation_studies SET status='archived',updated_at=? WHERE id=?",
            (now_iso(), study_id),
        )
        c.commit()
        row = repo.fetch_study(c, study_id)
    audit(actor.get("id"), "validation_study_archive", str(study_id))
    return _row(row)


# ---------------------------------------------------------------- datasets

def create_dataset(study_id: int, payload, actor: dict) -> dict:
    study = get_study(study_id)
    if study["status"] == "approved":
        raise LockedError("cannot add a dataset to an approved study")
    v.validate_characteristic_type(payload.characteristic_type)
    v.validate_spec_limits(payload.lower_spec_limit, payload.upper_spec_limit, payload.target_value)
    v.validate_unit_present(payload.unit)
    v.validate_subgroup_size(payload.subgroup_size)
    with conn() as c:
        if repo.fetch_dataset_by_code(c, study_id, payload.dataset_code) is not None:
            raise ConflictError(
                f"dataset_code '{payload.dataset_code}' already used in this study"
            )
        c.execute(
            "INSERT INTO measurement_datasets(validation_study_id,dataset_code,name,"
            "characteristic_name,characteristic_type,unit,nominal_value,lower_spec_limit,"
            "upper_spec_limit,target_value,sampling_strategy,subgroup_size,is_locked,version,"
            "metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,1,?)",
            (
                study_id, payload.dataset_code, payload.name, payload.characteristic_name,
                payload.characteristic_type, payload.unit, payload.nominal_value,
                payload.lower_spec_limit, payload.upper_spec_limit, payload.target_value,
                payload.sampling_strategy, payload.subgroup_size, payload.metadata_json,
            ),
        )
        dataset_id = c.execute("SELECT last_insert_rowid() id").fetchone()["id"]
        if study["status"] == "draft":
            c.execute(
                "UPDATE validation_studies SET status='data_collection',"
                "started_at=COALESCE(started_at,?),updated_at=? WHERE id=?",
                (now_iso(), now_iso(), study_id),
            )
        c.commit()
        row = repo.fetch_dataset(c, dataset_id)
    audit(actor.get("id"), "measurement_dataset_create", payload.dataset_code)
    return _row(row)


def get_dataset(dataset_id: int) -> dict:
    with conn() as c:
        row = repo.fetch_dataset(c, dataset_id)
    if row is None:
        raise NotFoundError(f"measurement_dataset {dataset_id} not found")
    return _row(row)


def list_datasets(study_id: int) -> list:
    get_study(study_id)
    with conn() as c:
        rows = repo.list_datasets(c, study_id)
    return [_row(r) for r in rows]


def patch_dataset(dataset_id: int, payload, actor: dict) -> dict:
    dataset = get_dataset(dataset_id)
    if dataset["is_locked"]:
        raise LockedError("dataset is locked and cannot be modified")
    fields = payload.dict(exclude_unset=True)
    if fields.get("subgroup_size") is not None:
        v.validate_subgroup_size(fields["subgroup_size"])
    if not fields:
        return dataset
    with conn() as c:
        sets = ",".join(f"{k}=?" for k in fields)
        c.execute(
            f"UPDATE measurement_datasets SET {sets} WHERE id=?", (*fields.values(), dataset_id)
        )
        c.commit()
        row = repo.fetch_dataset(c, dataset_id)
    audit(actor.get("id"), "measurement_dataset_patch", str(dataset_id))
    return _row(row)


def lock_dataset(dataset_id: int, actor: dict) -> dict:
    dataset = get_dataset(dataset_id)
    if dataset["is_locked"]:
        return dataset
    with conn() as c:
        c.execute("UPDATE measurement_datasets SET is_locked=1 WHERE id=?", (dataset_id,))
        c.commit()
        row = repo.fetch_dataset(c, dataset_id)
    audit(actor.get("id"), "measurement_dataset_lock", str(dataset_id))
    return _row(row)


# ---------------------------------------------------------------- records

def _assert_study_editable(dataset: dict) -> dict:
    study = get_study(dataset["validation_study_id"])
    if study["status"] == "approved":
        raise LockedError("cannot add measurements to an approved study")
    if dataset["is_locked"]:
        raise LockedError("dataset is locked; no new measurements can be added")
    return study


def _resolve_tool_id(c, tool_code: str | None):
    if not tool_code:
        return None
    row = c.execute("SELECT id FROM tool_references WHERE tool_code=?", (tool_code,)).fetchone()
    if row is None:
        raise NotFoundError(f"tool_reference '{tool_code}' not found")
    return row["id"]


def create_record(dataset_id: int, payload, actor: dict) -> dict:
    dataset = get_dataset(dataset_id)
    _assert_study_editable(dataset)
    v.validate_measured_value(payload.measured_value)
    with conn() as c:
        tool_id = _resolve_tool_id(c, payload.tool_code)
        device_id = _resolve_tool_id(c, payload.measurement_device_code)
        if payload.correction_of_id is not None:
            prior = c.execute(
                "SELECT * FROM measurement_records WHERE id=? AND dataset_id=?",
                (payload.correction_of_id, dataset_id),
            ).fetchone()
            if prior is None:
                raise NotFoundError(
                    f"measurement_record {payload.correction_of_id} not found in this dataset"
                )
        seq = repo.next_sequence_number(c, dataset_id)
        ts = now_iso()
        c.execute(
            "INSERT INTO measurement_records(dataset_id,sequence_number,sample_id,subgroup_id,"
            "measured_value,measured_at,production_date,shift,batch_number,lot_number,"
            "serial_number,part_number,station,line,machine,tool_id,measurement_device_id,"
            "operator_reference,environment_temperature,environment_humidity,is_valid,"
            "invalid_reason,comment,correction_of_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,NULL,?,?,?)",
            (
                dataset_id, seq, payload.sample_id, payload.subgroup_id, payload.measured_value,
                payload.measured_at, payload.production_date, payload.shift, payload.batch_number,
                payload.lot_number, payload.serial_number, payload.part_number, payload.station,
                payload.line, payload.machine, tool_id, device_id, payload.operator_reference,
                payload.environment_temperature, payload.environment_humidity, payload.comment,
                payload.correction_of_id, ts,
            ),
        )
        record_id = c.execute("SELECT last_insert_rowid() id").fetchone()["id"]
        if payload.correction_of_id is not None:
            c.execute(
                "UPDATE measurement_records SET is_valid=0,invalid_reason=? WHERE id=?",
                (f"superseded by correction record {record_id}", payload.correction_of_id),
            )
        c.commit()
        row = repo.fetch_record(c, record_id)
    audit(actor.get("id"), "measurement_record_create", str(record_id))
    return _row(row)


def list_records(dataset_id: int) -> list:
    get_dataset(dataset_id)
    with conn() as c:
        rows = repo.list_records(c, dataset_id)
    return [_row(r) for r in rows]


def invalidate_record(record_id: int, invalid_reason: str, actor: dict) -> dict:
    with conn() as c:
        row = repo.fetch_record(c, record_id)
        if row is None:
            raise NotFoundError(f"measurement_record {record_id} not found")
        dataset = repo.fetch_dataset(c, row["dataset_id"])
    _assert_study_editable(dict(dataset))
    if not invalid_reason or not invalid_reason.strip():
        raise ValidationDataError("invalid_reason is required")
    with conn() as c:
        c.execute(
            "UPDATE measurement_records SET is_valid=0,invalid_reason=? WHERE id=?",
            (invalid_reason, record_id),
        )
        c.commit()
        row = repo.fetch_record(c, record_id)
    audit(actor.get("id"), "measurement_record_invalidate", str(record_id))
    return _row(row)


# ------------------------------------------------------------------- CSV import
#
# Import behaviour is intentionally all-or-nothing per call: if any row fails a
# validation rule (missing required column, non-numeric value, NaN/Infinity,
# duplicate sample_id within the file, formula-injection pattern) the whole
# batch is rejected with a per-row error report and nothing is written. This
# keeps a dataset reproducible from its declared source file rather than a
# mix of a partially-successful and a retried import.

def _looks_like_formula(value: str) -> bool:
    return bool(value) and value[0] in _FORMULA_PREFIXES


def _parse_decimal(raw: str) -> float:
    s = raw.strip()
    if not s:
        raise ValueError("empty value")
    # Accept both '12.5' and '12,5' (comma as decimal separator).
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    return float(s)


def import_csv_records(dataset_id: int, filename: str, csv_content: str, actor: dict) -> dict:
    dataset = get_dataset(dataset_id)
    _assert_study_editable(dataset)

    raw_bytes = csv_content.encode("utf-8")
    if len(raw_bytes) > MAX_CSV_BYTES:
        raise CsvImportError(f"file exceeds maximum size of {MAX_CSV_BYTES} bytes")
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    if dataset.get("source_checksum") == checksum:
        raise ConflictError("this exact file was already imported into this dataset")

    try:
        reader = csv.DictReader(io.StringIO(csv_content))
    except csv.Error as exc:
        raise CsvImportError(f"malformed CSV: {exc}")

    fieldnames = [f.strip() for f in (reader.fieldnames or [])]
    missing = [col for col in _CSV_REQUIRED_COLUMNS if col not in fieldnames]
    if missing:
        raise CsvImportError(f"missing required column(s): {', '.join(missing)}")

    rows = list(reader)
    if len(rows) > MAX_CSV_ROWS:
        raise CsvImportError(f"file exceeds maximum of {MAX_CSV_ROWS} rows")

    row_errors: list[dict] = []
    parsed: list[dict] = []
    seen_sample_ids: set[str] = set()

    with conn() as c:
        for idx, raw_row in enumerate(rows, start=2):  # header is line 1
            errors = []
            sample_id = (raw_row.get("sample_id") or "").strip()
            if not sample_id:
                errors.append("sample_id is required")
            elif _looks_like_formula(sample_id):
                errors.append("sample_id contains a disallowed formula-injection prefix")
            elif sample_id in seen_sample_ids:
                errors.append(f"duplicate sample_id '{sample_id}' within file")

            measured_value = None
            raw_value = raw_row.get("measured_value")
            if raw_value is None or not str(raw_value).strip():
                errors.append("measured_value is required")
            else:
                try:
                    measured_value = _parse_decimal(str(raw_value))
                    v.validate_measured_value(measured_value)
                except (ValueError, ValidationDataError) as exc:
                    errors.append(f"measured_value invalid: {exc}")

            tool_id = None
            tool_code = (raw_row.get("tool_code") or "").strip() or None
            if tool_code:
                tref = c.execute(
                    "SELECT id FROM tool_references WHERE tool_code=?", (tool_code,)
                ).fetchone()
                if tref is None:
                    errors.append(f"unknown tool_code '{tool_code}'")
                else:
                    tool_id = tref["id"]

            for col in (
                "subgroup_id", "shift", "batch_number", "lot_number", "serial_number",
                "part_number", "station", "line", "machine", "operator_reference", "comment",
            ):
                val = raw_row.get(col)
                if val and _looks_like_formula(str(val)):
                    errors.append(f"column '{col}' contains a disallowed formula-injection prefix")

            if errors:
                row_errors.append({"line": idx, "errors": errors})
                continue

            seen_sample_ids.add(sample_id)
            seq_raw = (raw_row.get("sequence_number") or "").strip()
            parsed.append({
                "sample_id": sample_id,
                "sequence_number": int(seq_raw) if seq_raw else None,
                "subgroup_id": raw_row.get("subgroup_id") or None,
                "measured_value": measured_value,
                "measured_at": raw_row.get("measured_at") or None,
                "production_date": raw_row.get("production_date") or None,
                "shift": raw_row.get("shift") or None,
                "batch_number": raw_row.get("batch_number") or None,
                "lot_number": raw_row.get("lot_number") or None,
                "serial_number": raw_row.get("serial_number") or None,
                "part_number": raw_row.get("part_number") or None,
                "station": raw_row.get("station") or None,
                "line": raw_row.get("line") or None,
                "machine": raw_row.get("machine") or None,
                "tool_id": tool_id,
                "operator_reference": raw_row.get("operator_reference") or None,
                "comment": raw_row.get("comment") or None,
            })

        if row_errors:
            raise CsvImportError(
                f"{len(row_errors)} row(s) failed validation; import rejected", row_errors
            )

        ts = now_iso()
        inserted_ids = []
        for item in parsed:
            seq = item["sequence_number"] or repo.next_sequence_number(c, dataset_id)
            if c.execute(
                "SELECT 1 FROM measurement_records WHERE dataset_id=? AND sequence_number=?",
                (dataset_id, seq),
            ).fetchone():
                raise CsvImportError(
                    f"sequence_number {seq} already exists in dataset {dataset_id}"
                )
            c.execute(
                "INSERT INTO measurement_records(dataset_id,sequence_number,sample_id,"
                "subgroup_id,measured_value,measured_at,production_date,shift,batch_number,"
                "lot_number,serial_number,part_number,station,line,machine,tool_id,"
                "operator_reference,is_valid,comment,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (
                    dataset_id, seq, item["sample_id"], item["subgroup_id"],
                    item["measured_value"], item["measured_at"], item["production_date"],
                    item["shift"], item["batch_number"], item["lot_number"],
                    item["serial_number"], item["part_number"], item["station"],
                    item["line"], item["machine"], item["tool_id"], item["operator_reference"],
                    item["comment"], ts,
                ),
            )
            inserted_ids.append(c.execute("SELECT last_insert_rowid() id").fetchone()["id"])

        c.execute(
            "UPDATE measurement_datasets SET source_type='csv',source_filename=?,"
            "source_checksum=?,imported_at=?,imported_by=?,version=version+1 WHERE id=?",
            (filename, checksum, ts, actor.get("id"), dataset_id),
        )
        c.commit()

    audit(
        actor.get("id"), "measurement_csv_import",
        f"dataset={dataset_id} file={filename} rows={len(inserted_ids)}",
    )
    return {
        "imported": len(inserted_ids), "record_ids": inserted_ids,
        "checksum": checksum, "row_errors": [],
    }


__all__ = [
    "create_study", "get_study", "list_studies", "patch_study",
    "complete_study", "submit_study", "approve_study", "reject_study", "archive_study",
    "create_dataset", "get_dataset", "list_datasets", "patch_dataset", "lock_dataset",
    "create_record", "list_records", "invalidate_record", "import_csv_records",
    "NotFoundError", "ConflictError", "ValidationDataError", "LockedError",
    "StateTransitionError", "CsvImportError",
]
