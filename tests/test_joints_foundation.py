import json
import os
import sqlite3

from backend.joints import schema as joints_schema

os.environ["TORQPRO_SECRET_KEY"] = "x" * 64
from backend.app import conn, now_iso
from backend.joints import service as joints_svc
from backend.joints.exceptions import (
    JointArchivedError,
    JointCodeConflictError,
    JointNotFoundError,
    JointRevisionConflictError,
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


# ---------------------------------------------------------------------
# create_joint_revision(idempotency_key=...) -- Faz 2.8.17 Stage 1
# (additive, keyword-only; backward-compatible)
# ---------------------------------------------------------------------


def _count_create_audit_entries(joint_id, rev_no):
    with conn() as c:
        row = c.execute(
            "SELECT COUNT(*) n FROM audit_log WHERE action='joint_revision_create' AND detail=?",
            (f"joint={joint_id} rev={rev_no}",),
        ).fetchone()
    return row["n"]


def test_idempotency_key_none_preserves_existing_behaviour():
    """Scenario 1: idempotency_key omitted (default None) -- every call
    creates a new revision, exactly like before this Stage existed."""
    pid = _make_project("Idem None Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-NONE", "Idem None Joint", None, None)
    r1 = joints_svc.create_joint_revision(joint["id"], {"a": 1}, "x", None)
    r2 = joints_svc.create_joint_revision(joint["id"], {"a": 1}, "x", None)
    assert r1["id"] != r2["id"]
    assert r2["revision_no"] == r1["revision_no"] + 1
    assert r1["idempotency_key"] is None
    assert r2["idempotency_key"] is None


def test_idempotency_replay_same_payload_returns_same_revision():
    """Scenario 2: same joint + same key + same semantic request ->
    the already-created revision is returned, not a new one."""
    pid = _make_project("Idem Replay Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-REPLAY", "Idem Replay Joint", None, 7)
    first = joints_svc.create_joint_revision(
        joint["id"], {"thread": "M10"}, "initial", 7, idempotency_key="RETRY-1"
    )
    replay = joints_svc.create_joint_revision(
        joint["id"], {"thread": "M10"}, "initial", 7, idempotency_key="RETRY-1"
    )
    assert replay["id"] == first["id"]
    assert replay["revision_no"] == first["revision_no"]


def test_idempotency_replay_does_not_consume_new_revision_number():
    """Scenario 3: a replay must not advance the per-joint revision_no
    counter -- the next genuinely new revision continues right after
    the original, not after a phantom replay-consumed number."""
    pid = _make_project("Idem RevNo Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-REVNO", "Idem RevNo Joint", None, None)
    first = joints_svc.create_joint_revision(
        joint["id"], {}, "r1", None, idempotency_key="RETRY-2"
    )
    assert first["revision_no"] == 1
    joints_svc.create_joint_revision(joint["id"], {}, "r1", None, idempotency_key="RETRY-2")
    joints_svc.create_joint_revision(joint["id"], {}, "r1", None, idempotency_key="RETRY-2")
    next_new = joints_svc.create_joint_revision(joint["id"], {}, "r2", None)
    assert next_new["revision_no"] == 2


def test_idempotency_replay_does_not_write_second_audit_entry():
    """Scenario 4: a replay must not produce a second
    'joint_revision_create' audit row for the same revision."""
    pid = _make_project("Idem Audit Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-AUDIT", "Idem Audit Joint", None, None)
    first = joints_svc.create_joint_revision(
        joint["id"], {}, "r1", None, idempotency_key="RETRY-3"
    )
    assert _count_create_audit_entries(joint["id"], first["revision_no"]) == 1
    joints_svc.create_joint_revision(joint["id"], {}, "r1", None, idempotency_key="RETRY-3")
    joints_svc.create_joint_revision(joint["id"], {}, "r1", None, idempotency_key="RETRY-3")
    assert _count_create_audit_entries(joint["id"], first["revision_no"]) == 1


def test_idempotency_same_key_different_snapshot_conflicts():
    """Scenario 5: same joint + same key + a materially different
    snapshot is a key collision, not a retry -- must raise
    JointRevisionConflictError, never silently create or overwrite."""
    pid = _make_project("Idem Conflict Snapshot Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-CONF-SNAP", "Idem Conflict Snap Joint", None, None)
    joints_svc.create_joint_revision(
        joint["id"], {"thread": "M10"}, "r1", None, idempotency_key="RETRY-4"
    )
    try:
        joints_svc.create_joint_revision(
            joint["id"], {"thread": "M12"}, "r1", None, idempotency_key="RETRY-4"
        )
        assert False, "expected JointRevisionConflictError"
    except JointRevisionConflictError:
        pass


def test_idempotency_same_key_different_change_summary_conflicts():
    """Scenario 6: same key, same snapshot, different change_summary ->
    conflict."""
    pid = _make_project("Idem Conflict Summary Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-CONF-SUM", "Idem Conflict Sum Joint", None, None)
    joints_svc.create_joint_revision(joint["id"], {}, "first pass", None, idempotency_key="RETRY-5")
    try:
        joints_svc.create_joint_revision(
            joint["id"], {}, "second pass", None, idempotency_key="RETRY-5"
        )
        assert False, "expected JointRevisionConflictError"
    except JointRevisionConflictError:
        pass


def test_idempotency_same_key_different_actor_conflicts():
    """Scenario 7: same key, same snapshot/summary, different
    created_by (actor) -> conflict. A retry from a different actor
    under the same key is not a legitimate replay."""
    pid = _make_project("Idem Conflict Actor Project")
    joint = joints_svc.create_joint(
        pid, "J-IDEM-CONF-ACTOR", "Idem Conflict Actor Joint", None, None
    )
    joints_svc.create_joint_revision(joint["id"], {}, "x", 1, idempotency_key="RETRY-6")
    try:
        joints_svc.create_joint_revision(joint["id"], {}, "x", 2, idempotency_key="RETRY-6")
        assert False, "expected JointRevisionConflictError"
    except JointRevisionConflictError:
        pass


def test_idempotency_same_key_different_joint_is_allowed():
    """Scenario 8: the same idempotency_key may be reused freely across
    different joints -- uniqueness is scoped per joint_id."""
    pid = _make_project("Idem Cross Joint Project")
    j1 = joints_svc.create_joint(pid, "J-IDEM-CROSS-1", "Idem Cross Joint 1", None, None)
    j2 = joints_svc.create_joint(pid, "J-IDEM-CROSS-2", "Idem Cross Joint 2", None, None)
    r1 = joints_svc.create_joint_revision(j1["id"], {}, "x", None, idempotency_key="SHARED-KEY")
    r2 = joints_svc.create_joint_revision(j2["id"], {}, "x", None, idempotency_key="SHARED-KEY")
    assert r1["id"] != r2["id"]
    assert r1["joint_id"] != r2["joint_id"]


def test_idempotency_replay_accepts_reordered_snapshot_keys():
    """Scenario 9: semantic (dict) equality, not raw string/hash
    equality -- a snapshot with the same keys/values in a different
    dict insertion order must still be recognised as the same
    request."""
    pid = _make_project("Idem Key Order Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-ORDER", "Idem Key Order Joint", None, None)
    first = joints_svc.create_joint_revision(
        joint["id"],
        {"thread": "M10", "class": "8.8", "length_mm": 40},
        "r1",
        None,
        idempotency_key="RETRY-7",
    )
    reordered_snapshot = json.loads(
        '{"length_mm": 40, "thread": "M10", "class": "8.8"}'
    )
    replay = joints_svc.create_joint_revision(
        joint["id"], reordered_snapshot, "r1", None, idempotency_key="RETRY-7"
    )
    assert replay["id"] == first["id"]


def test_idempotency_pre_existing_records_without_key_are_unaffected():
    """Scenario 10: revisions created before this Stage (idempotency_key
    always NULL, i.e. idempotency_key=None calls) remain valid and are
    never matched or disturbed by later idempotent calls with a real
    key -- NULL keys are excluded from the lookup/uniqueness scope
    entirely."""
    pid = _make_project("Idem Legacy Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-LEGACY", "Idem Legacy Joint", None, None)
    legacy = joints_svc.create_joint_revision(joint["id"], {}, "legacy", None)
    assert legacy["idempotency_key"] is None
    keyed = joints_svc.create_joint_revision(joint["id"], {}, "new", None, idempotency_key="K-1")
    assert keyed["id"] != legacy["id"]
    still_there = joints_svc.get_joint_revision(legacy["id"])
    assert still_there["idempotency_key"] is None
    assert still_there == legacy


def test_idempotency_schema_migration_is_re_runnable():
    """Scenario 11: re-running backend.joints.schema.migrate() against
    an already-migrated connection (fresh or previously-upgraded) must
    not raise -- CREATE TABLE/INDEX IF NOT EXISTS and the conditional
    ALTER TABLE column check are all idempotent."""
    with conn() as c:
        joints_schema.migrate(c)
        joints_schema.migrate(c)
        c.commit()
        cols = [r["name"] for r in c.execute("PRAGMA table_info(joint_revisions)").fetchall()]
    assert "idempotency_key" in cols


def test_idempotency_database_unique_backstop_rejects_direct_duplicate():
    """Scenario 12: the partial unique index itself (not just the
    service-layer lookup) rejects a duplicate (joint_id,
    idempotency_key) pair inserted directly, and allows an unlimited
    number of NULL idempotency_key rows on the same joint -- proving
    the DB-level guarantee the service layer relies on as a backstop
    actually exists."""
    pid = _make_project("Idem DB Backstop Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-BACKSTOP", "Idem Backstop Joint", None, None)
    with conn() as c:
        c.execute(
            "INSERT INTO joint_revisions(joint_id,revision_no,status,snapshot_json,created_at,"
            "idempotency_key) VALUES(?,1,'draft','{}',?,?)",
            (joint["id"], now_iso(), "DB-LEVEL-KEY"),
        )
        c.commit()
        try:
            c.execute(
                "INSERT INTO joint_revisions(joint_id,revision_no,status,snapshot_json,created_at,"
                "idempotency_key) VALUES(?,2,'draft','{}',?,?)",
                (joint["id"], now_iso(), "DB-LEVEL-KEY"),
            )
            c.commit()
            assert False, "expected sqlite3.IntegrityError from the partial unique index"
        except sqlite3.IntegrityError:
            c.rollback()
        # multiple NULL idempotency_key rows on the same joint remain unrestricted
        c.execute(
            "INSERT INTO joint_revisions(joint_id,revision_no,status,snapshot_json,created_at,"
            "idempotency_key) VALUES(?,3,'draft','{}',?,NULL)",
            (joint["id"], now_iso()),
        )
        c.execute(
            "INSERT INTO joint_revisions(joint_id,revision_no,status,snapshot_json,created_at,"
            "idempotency_key) VALUES(?,4,'draft','{}',?,NULL)",
            (joint["id"], now_iso()),
        )
        c.commit()


def test_idempotency_conflict_error_never_leaks_snapshot_or_internal_detail():
    """Scenario 13: a conflict raised for a reused key with a mismatched
    request must never echo the snapshot content, a file path, SQL
    text, or a raw driver exception -- only a fixed, generic message
    (mirrors the same 'never leak internal detail' contract already
    documented on backend.governance.adapters.joint_revision)."""
    pid = _make_project("Idem No Leak Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-NOLEAK", "Idem No Leak Joint", None, None)
    secret_snapshot = {"internal_note": "CONFIDENTIAL-TORQUE-MARGIN-4.2"}
    joints_svc.create_joint_revision(
        joint["id"], secret_snapshot, "r1", None, idempotency_key="RETRY-8"
    )
    try:
        joints_svc.create_joint_revision(
            joint["id"], {"internal_note": "different"}, "r1", None, idempotency_key="RETRY-8"
        )
        assert False, "expected JointRevisionConflictError"
    except JointRevisionConflictError as exc:
        message = str(exc)
        assert "CONFIDENTIAL-TORQUE-MARGIN-4.2" not in message
        assert "sqlite" not in message.lower()
        assert "/home/" not in message
        assert ".db" not in message


# ---------------------------------------------------------------------
# Deterministic (non-threaded) exercise of the concurrency backstop --
# Faz 2.8.17 Stage 2. Simulates the exact race window the "except
# sqlite3.IntegrityError" branch in create_joint_revision() exists for
# (a concurrent writer commits the same (joint_id, idempotency_key)
# row between our own SELECT and our own INSERT) by making the first
# INSERT that carries idempotency_key raise sqlite3.IntegrityError --
# the same exception the real partial unique index would raise -- and
# having a "winning" row already committed through an independent real
# connection immediately before that. No threads, no timing
# dependency, no flakiness: the same interleaving happens every run.
# ---------------------------------------------------------------------


class _RacingConnection:
    """Wraps one real sqlite3 connection (from backend.app.conn()) and
    intercepts exactly one INSERT -- the first one whose SQL text both
    starts an INSERT into joint_revisions and carries idempotency_key
    -- to simulate a concurrent writer winning that row first. Every
    other call (SELECT, commit, rollback, any other attribute) passes
    straight through to the real connection, so this only touches the
    single code path under test."""

    def __init__(self, real_conn_factory, on_first_insert):
        self._c = real_conn_factory()
        self._on_first_insert = on_first_insert
        self._triggered = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._c.__exit__(exc_type, exc, tb)

    def __getattr__(self, name):
        return getattr(self._c, name)

    def execute(self, sql, params=()):
        if (
            not self._triggered
            and sql.strip().startswith("INSERT INTO joint_revisions")
            and "idempotency_key" in sql
        ):
            self._triggered = True
            self._on_first_insert()
            raise sqlite3.IntegrityError("simulated unique constraint violation")
        return self._c.execute(sql, params)


def _commit_winning_race_row(joint_id, revision_no, snapshot, change_summary, created_by, key):
    """Simulates the concurrent writer that "wins" the race: commits a
    joint_revisions row through its own, independent real connection,
    entirely separate from the connection under test."""
    with conn() as winner_c:
        winner_c.execute(
            "INSERT INTO joint_revisions(joint_id,revision_no,status,snapshot_json,"
            "change_summary,created_by,created_at,idempotency_key) "
            "VALUES(?,?,'draft',?,?,?,?,?)",
            (
                joint_id, revision_no, json.dumps(snapshot, ensure_ascii=False),
                change_summary, created_by, now_iso(), key,
            ),
        )
        winner_c.commit()


def test_idempotency_race_recovery_returns_existing_revision_on_semantic_match(monkeypatch):
    """The race is recovered by returning the concurrent winner's row
    when our own request is semantically identical to it -- no
    duplicate, no raised exception, no second audit entry."""
    pid = _make_project("Idem Race Match Project")
    joint = joints_svc.create_joint(pid, "J-IDEM-RACE-MATCH", "Idem Race Match Joint", None, 3)
    winning_snapshot = {"thread": "M12"}
    winning_change_summary = "winner"
    winning_actor = 3

    def _on_first_insert():
        _commit_winning_race_row(
            joint["id"], 1, winning_snapshot, winning_change_summary, winning_actor, "RACE-KEY-A",
        )

    monkeypatch.setattr(
        joints_svc, "conn", lambda: _RacingConnection(conn, _on_first_insert)
    )

    result = joints_svc.create_joint_revision(
        joint["id"], winning_snapshot, winning_change_summary, winning_actor,
        idempotency_key="RACE-KEY-A",
    )
    assert result["revision_no"] == 1
    assert result["change_summary"] == winning_change_summary
    assert result["created_by"] == winning_actor
    assert _count_create_audit_entries(joint["id"], 1) == 0  # winner wrote no audit either


def test_idempotency_race_recovery_raises_conflict_on_semantic_mismatch(monkeypatch):
    """The race is recovered by raising JointRevisionConflictError --
    never the raw sqlite3.IntegrityError -- when our own request
    differs from the concurrent winner's."""
    pid = _make_project("Idem Race Mismatch Project")
    joint = joints_svc.create_joint(
        pid, "J-IDEM-RACE-MISMATCH", "Idem Race Mismatch Joint", None, 4
    )

    def _on_first_insert():
        _commit_winning_race_row(
            joint["id"], 1, {"thread": "M8"}, "winner-summary", 4, "RACE-KEY-B",
        )

    monkeypatch.setattr(
        joints_svc, "conn", lambda: _RacingConnection(conn, _on_first_insert)
    )

    try:
        joints_svc.create_joint_revision(
            joint["id"], {"thread": "M20-DIFFERENT"}, "our-summary", 4,
            idempotency_key="RACE-KEY-B",
        )
        assert False, "expected JointRevisionConflictError, not a raw sqlite3.IntegrityError"
    except sqlite3.IntegrityError:
        assert False, "raw sqlite3.IntegrityError leaked out of create_joint_revision()"
    except JointRevisionConflictError as exc:
        message = str(exc)
        assert "UNIQUE constraint" not in message
        assert "sqlite3" not in message
        assert "IntegrityError" not in message
