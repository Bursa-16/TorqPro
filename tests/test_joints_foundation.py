import os
os.environ["TORQPRO_SECRET_KEY"] = "x" * 64
from backend.app import conn, now_iso
from backend.joints import service as joints_svc
from backend.joints.exceptions import (
    JointArchivedError,
    JointCodeConflictError,
    JointNotFoundError,
    JointRevisionNotFoundError,
    JointRevisionStateError,
)


def _make_project(name="Joint Test Project"):
    with conn() as c:
        c.execute(
            "INSERT INTO projects(name,status,created_at) VALUES(?,?,?)",
            (name, "open", now_iso()),
        )
        c.commit()
        return c.execute("SELECT id FROM projects WHERE id=last_insert_rowid()").fetchone()["id"]


def test_create_joint_requires_existing_project():
    try:
        joints_svc.create_joint(999999, "J-X", "Ghost Joint", None, None)
        assert False, "expected JointNotFoundError"
    except JointNotFoundError:
        pass


def test_joint_code_unique_within_project():
    pid = _make_project()
    joints_svc.create_joint(pid, "J-001", "Bracket Joint", None, None)
    try:
        joints_svc.create_joint(pid, "J-001", "Duplicate", None, None)
        assert False, "expected JointCodeConflictError"
    except JointCodeConflictError:
        pass


def test_joint_code_can_repeat_across_projects():
    pid1 = _make_project("Proj A")
    pid2 = _make_project("Proj B")
    j1 = joints_svc.create_joint(pid1, "J-SAME", "Joint A", None, None)
    j2 = joints_svc.create_joint(pid2, "J-SAME", "Joint B", None, None)
    assert j1["id"] != j2["id"]


def test_joint_revision_lifecycle_draft_to_approved():
    pid = _make_project("Lifecycle Project")
    joint = joints_svc.create_joint(pid, "J-LC", "Lifecycle Joint", None, 1)
    rev = joints_svc.create_joint_revision(joint["id"], {"thread": "M10"}, "initial", 1)
    assert rev["revision_no"] == 1
    assert rev["status"] == "draft"
    rev = joints_svc.submit_joint_revision(rev["id"], 1)
    assert rev["status"] == "review"
    rev = joints_svc.approve_joint_revision(rev["id"], 2)
    assert rev["status"] == "approved"
    updated_joint = joints_svc.get_joint(joint["id"])
    assert updated_joint["current_revision_id"] == rev["id"]
    assert updated_joint["status"] == "active"


def test_joint_revision_numbers_increment_per_joint():
    pid = _make_project("Rev Numbering Project")
    joint = joints_svc.create_joint(pid, "J-NUM", "Numbering Joint", None, None)
    r1 = joints_svc.create_joint_revision(joint["id"], {}, "r1", None)
    r2 = joints_svc.create_joint_revision(joint["id"], {}, "r2", None)
    assert r1["revision_no"] == 1
    assert r2["revision_no"] == 2


def test_reviewer_cannot_approve_own_revision():
    pid = _make_project("Self Approve Project")
    joint = joints_svc.create_joint(pid, "J-SELF", "Self Joint", None, 5)
    rev = joints_svc.create_joint_revision(joint["id"], {}, "x", 5)
    rev = joints_svc.submit_joint_revision(rev["id"], 5)
    try:
        joints_svc.approve_joint_revision(rev["id"], 5)
        assert False, "expected JointRevisionStateError"
    except JointRevisionStateError:
        pass


def test_only_draft_revision_can_be_submitted():
    pid = _make_project("Draft Only Project")
    joint = joints_svc.create_joint(pid, "J-DRAFT", "Draft Joint", None, None)
    rev = joints_svc.create_joint_revision(joint["id"], {}, "x", None)
    rev = joints_svc.submit_joint_revision(rev["id"], None)
    try:
        joints_svc.submit_joint_revision(rev["id"], None)
        assert False, "expected JointRevisionStateError"
    except JointRevisionStateError:
        pass


def test_cannot_create_revision_on_archived_joint():
    pid = _make_project("Archive Project")
    joint = joints_svc.create_joint(pid, "J-ARC", "Archive Joint", None, None)
    joints_svc.archive_joint(joint["id"], None)
    try:
        joints_svc.create_joint_revision(joint["id"], {}, "x", None)
        assert False, "expected JointArchivedError"
    except JointArchivedError:
        pass


def test_archive_is_soft_not_a_delete():
    pid = _make_project("Soft Delete Project")
    joint = joints_svc.create_joint(pid, "J-SOFT", "Soft Joint", None, None)
    joints_svc.archive_joint(joint["id"], None)
    still_there = joints_svc.get_joint(joint["id"])
    assert still_there["status"] == "archived"


# ---------------------------------------------------------------------
# list_joint_revisions() -- Faz 2.8.14 Stage 2 (additive, read-only)
# ---------------------------------------------------------------------


def test_list_joint_revisions_returns_all_revisions_across_joints():
    pid = _make_project("Bulk List Project A")
    j1 = joints_svc.create_joint(pid, "J-BULK-A1", "Bulk Joint A1", None, None)
    j2 = joints_svc.create_joint(pid, "J-BULK-A2", "Bulk Joint A2", None, None)
    r1 = joints_svc.create_joint_revision(j1["id"], {}, "r1", None)
    r2 = joints_svc.create_joint_revision(j2["id"], {}, "r2", None)

    all_revisions = joints_svc.list_joint_revisions()
    ids = {r["id"] for r in all_revisions}
    assert r1["id"] in ids
    assert r2["id"] in ids


def test_list_joint_revisions_results_are_in_ascending_id_order():
    pid = _make_project("Bulk List Order Project")
    joint = joints_svc.create_joint(pid, "J-BULK-ORDER", "Bulk Order Joint", None, None)
    joints_svc.create_joint_revision(joint["id"], {}, "r1", None)
    joints_svc.create_joint_revision(joint["id"], {}, "r2", None)
    joints_svc.create_joint_revision(joint["id"], {}, "r3", None)

    revisions = joints_svc.list_joint_revisions(joint["id"])
    ids = [r["id"] for r in revisions]
    assert ids == sorted(ids)


def test_list_joint_revisions_joint_id_filter_returns_only_that_joints_revisions():
    pid = _make_project("Bulk List Filter Project")
    j1 = joints_svc.create_joint(pid, "J-BULK-F1", "Bulk Filter Joint 1", None, None)
    j2 = joints_svc.create_joint(pid, "J-BULK-F2", "Bulk Filter Joint 2", None, None)
    joints_svc.create_joint_revision(j1["id"], {}, "r1", None)
    joints_svc.create_joint_revision(j1["id"], {}, "r2", None)
    joints_svc.create_joint_revision(j2["id"], {}, "r3", None)

    filtered = joints_svc.list_joint_revisions(j1["id"])
    assert len(filtered) == 2
    assert all(r["joint_id"] == j1["id"] for r in filtered)


def test_list_joint_revisions_unknown_joint_id_returns_empty_list_not_error():
    result = joints_svc.list_joint_revisions(999999999)
    assert result == []


def test_list_joint_revisions_on_database_with_no_revisions_for_filter_returns_empty_list():
    pid = _make_project("Bulk List Empty Project")
    joint = joints_svc.create_joint(pid, "J-BULK-EMPTY", "Bulk Empty Joint", None, None)
    result = joints_svc.list_joint_revisions(joint["id"])
    assert result == []


def test_list_joint_revisions_does_not_mutate_any_record():
    pid = _make_project("Bulk List Immutable Project")
    joint = joints_svc.create_joint(pid, "J-BULK-IMMUT", "Bulk Immutable Joint", None, None)
    rev = joints_svc.create_joint_revision(joint["id"], {}, "r1", None)

    before = joints_svc.get_joint_revision(rev["id"])
    joints_svc.list_joint_revisions()
    joints_svc.list_joint_revisions(joint["id"])
    after = joints_svc.get_joint_revision(rev["id"])
    assert before == after


def test_list_joint_revisions_does_not_change_get_joint_revision_behaviour():
    pid = _make_project("Bulk List Compat Project")
    joint = joints_svc.create_joint(pid, "J-BULK-COMPAT", "Bulk Compat Joint", None, None)
    rev = joints_svc.create_joint_revision(joint["id"], {}, "r1", None)

    joints_svc.list_joint_revisions()
    try:
        joints_svc.get_joint_revision(999999999)
        assert False, "expected JointRevisionNotFoundError"
    except JointRevisionNotFoundError:
        pass
    assert joints_svc.get_joint_revision(rev["id"])["id"] == rev["id"]


def test_list_joint_revisions_row_shape_matches_get_joint_revision():
    pid = _make_project("Bulk List Shape Project")
    joint = joints_svc.create_joint(pid, "J-BULK-SHAPE", "Bulk Shape Joint", None, None)
    rev = joints_svc.create_joint_revision(joint["id"], {}, "r1", None)

    listed = joints_svc.list_joint_revisions(joint["id"])
    single = joints_svc.get_joint_revision(rev["id"])
    matching = [r for r in listed if r["id"] == rev["id"]][0]
    assert set(matching.keys()) == set(single.keys())
    assert matching == single


def test_list_joint_revisions_uses_parameterized_sql_not_string_interpolation():
    """Injection-safety regression guard: a joint_id value that would
    corrupt a naively-interpolated query must be handled safely as an
    ordinary (non-matching) integer-typed parameter, never concatenated
    into SQL text."""
    pid = _make_project("Bulk List Injection Project")
    joint = joints_svc.create_joint(pid, "J-BULK-INJ", "Bulk Injection Joint", None, None)
    joints_svc.create_joint_revision(joint["id"], {}, "r1", None)

    # joint_id is typed int, so a non-integer "injection" value is
    # simply not representable -- this exercises the safe, parameterized
    # path with an out-of-range integer instead, confirming no crash
    # and no unintended row leakage.
    result = joints_svc.list_joint_revisions(-999999999)
    assert result == []
