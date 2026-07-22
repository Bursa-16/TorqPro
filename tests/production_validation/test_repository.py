from backend.app import conn
from backend.production_validation import repository as repo
from tests.production_validation.conftest import create_dataset, create_study


def test_fetch_study_and_by_code():
    study = create_study()
    with conn() as c:
        row = repo.fetch_study(c, study["id"])
        assert row is not None
        assert row["id"] == study["id"]
        by_code = repo.fetch_study_by_code(c, study["study_code"])
        assert by_code["id"] == study["id"]


def test_fetch_study_missing_returns_none():
    with conn() as c:
        assert repo.fetch_study(c, 999999999) is None
        assert repo.fetch_study_by_code(c, "NO-SUCH-CODE") is None


def test_list_studies_filters():
    study = create_study()
    with conn() as c:
        rows = repo.list_studies(c, project_id=study["project_id"])
        assert any(r["id"] == study["id"] for r in rows)
        rows_status = repo.list_studies(c, status="draft")
        assert any(r["id"] == study["id"] for r in rows_status)
        rows_other = repo.list_studies(c, status="approved")
        assert all(r["status"] == "approved" for r in rows_other)


def test_dataset_lookup_and_listing():
    study = create_study()
    dataset = create_dataset(study["id"])
    with conn() as c:
        row = repo.fetch_dataset(c, dataset["id"])
        assert row["dataset_code"] == dataset["dataset_code"]
        by_code = repo.fetch_dataset_by_code(c, study["id"], dataset["dataset_code"])
        assert by_code["id"] == dataset["id"]
        listed = repo.list_datasets(c, study["id"])
        assert any(d["id"] == dataset["id"] for d in listed)


def test_sequence_number_and_record_counts():
    study = create_study()
    dataset = create_dataset(study["id"])
    with conn() as c:
        assert repo.next_sequence_number(c, dataset["id"]) == 1
        total, valid = repo.count_records(c, dataset["id"])
        assert total == 0 and valid == 0
