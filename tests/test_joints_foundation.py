import os
os.environ["TORQPRO_SECRET_KEY"] = "x" * 64
from backend.app import conn, now_iso
from backend.joints import service as joints_svc
from backend.joints.exceptions import (
    JointArchivedError,
    JointCodeConflictError,
    JointNotFoundError,
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
