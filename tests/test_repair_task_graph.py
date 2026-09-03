"""
Tests for scripts/repair_task_graph.py.

The repair removes task rows created by the routing-breadcrumb path mismatch: a stub
is a row where id == label, because create_task_graph always writes a 12-char sha1 id
alongside a full-text label. The bar these tests hold is that real rows are never
touched and that a stub's borrowed gate flags stop making it actionable.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import repair_task_graph as rtg  # noqa: E402


SCHEMA = """
CREATE TABLE tasks (
    id TEXT PRIMARY KEY, label TEXT NOT NULL,
    challenge_cleared INTEGER NOT NULL DEFAULT 0,
    nfr_cleared INTEGER NOT NULL DEFAULT 0,
    unblocked INTEGER NOT NULL DEFAULT 0,
    in_flight INTEGER NOT NULL DEFAULT 0,
    stale INTEGER NOT NULL DEFAULT 0,
    project TEXT, done INTEGER NOT NULL DEFAULT 0, session_id TEXT
);
CREATE TABLE edges (parent_id TEXT, child_id TEXT);
"""


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "task-graph.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    return path


def _add(db_path, id_, label, **cols):
    conn = sqlite3.connect(db_path)
    keys = ["id", "label", *cols]
    vals = [id_, label, *cols.values()]
    conn.execute(
        f"INSERT INTO tasks ({','.join(keys)}) VALUES ({','.join('?' * len(keys))})", vals
    )
    conn.commit()
    conn.close()


def _row(db_path, id_):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM tasks WHERE id = ?", (id_,)).fetchone()
    conn.close()
    return r


def _run(db_path, apply=False):
    argv = ["--db", str(db_path)] + (["--apply"] if apply else [])
    return rtg.main(argv)


class TestStubIdentification:
    def test_real_row_is_never_a_stub(self, db):
        """A sha1 id with a full-text label must survive untouched."""
        _add(db, "441a2a5d3722", "Add one function to ab_experiments.py", unblocked=1)
        assert _run(db, apply=True) == 0
        r = _row(db, "441a2a5d3722")
        assert r is not None
        assert r["unblocked"] == 1
        assert r["stale"] == 0

    def test_clean_graph_reports_nothing_to_do(self, db, capsys):
        _add(db, "441a2a5d3722", "a real task")
        _run(db, apply=True)
        assert "clean" in capsys.readouterr().out


class TestDeleteCompletedStubs:
    def test_done_stub_is_deleted(self, db):
        _add(db, "Build ceremony_sequencer.py — trac", "Build ceremony_sequencer.py — trac", done=1)
        _run(db, apply=True)
        assert _row(db, "Build ceremony_sequencer.py — trac") is None

    def test_done_real_row_is_kept(self, db):
        _add(db, "eacb9775b025", "Build ceremony_sequencer.py", done=1)
        _run(db, apply=True)
        assert _row(db, "eacb9775b025") is not None


class TestDefuseOpenStubs:
    def test_borrowed_gate_flags_are_cleared(self, db):
        """The flags belonged to whatever task was routed, not to this row."""
        sid = "Add exposure-count function to ab_ex"
        _add(db, sid, sid, challenge_cleared=1, nfr_cleared=1, unblocked=1)
        _run(db, apply=True)
        r = _row(db, sid)
        assert (r["challenge_cleared"], r["nfr_cleared"], r["unblocked"]) == (0, 0, 0)

    def test_open_stub_is_kept_and_marked_stale(self, db):
        """Deleting would lose a task that may have no real counterpart."""
        sid = "Upgrade ux-designer to L10 craft level"
        _add(db, sid, sid, project="youk")
        _run(db, apply=True)
        r = _row(db, sid)
        assert r is not None
        assert r["stale"] == 1
        assert r["project"] == "youk"

    def test_defused_stub_can_no_longer_be_next_task(self, db):
        """unblocked=0 is the field next_task selects on — this is the symptom fix."""
        sid = "Scale canopy's query engine: pooling"
        _add(db, sid, sid, unblocked=1, in_flight=0, done=0)
        _run(db, apply=True)
        conn = sqlite3.connect(db)
        actionable = conn.execute(
            "SELECT count(*) FROM tasks WHERE unblocked=1 AND in_flight=0 AND done=0"
        ).fetchone()[0]
        conn.close()
        assert actionable == 0


class TestSafety:
    def test_dry_run_changes_nothing(self, db):
        sid = "Build skill_reentry.py — reads skill"
        _add(db, sid, sid, done=1)
        assert _run(db, apply=False) == 0
        assert _row(db, sid) is not None

    def test_refuses_when_a_done_stub_has_an_edge(self, db, capsys):
        sid = "Build failure_pattern_detector.py"
        _add(db, sid, sid, done=1)
        _add(db, "child0000001", "a child task")
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO edges VALUES (?, ?)", (sid, "child0000001"))
        conn.commit()
        conn.close()
        assert _run(db, apply=True) == 1
        assert _row(db, sid) is not None
        assert "refusing to delete" in capsys.readouterr().out

    def test_apply_is_idempotent(self, db):
        sid_done = "Enroll _SEVEN_CONVERGENCE into the li"
        sid_open = "Write a doc suite for Preview"
        _add(db, sid_done, sid_done, done=1)
        _add(db, sid_open, sid_open, unblocked=1)
        _run(db, apply=True)
        first = dict(_row(db, sid_open))
        _run(db, apply=True)
        assert _row(db, sid_done) is None
        assert dict(_row(db, sid_open)) == first

    def test_snapshot_written_before_apply(self, db):
        sid = "PR-5: build_brief() reads state"
        _add(db, sid, sid, done=1)
        _run(db, apply=True)
        assert list(db.parent.glob("task-graph.db.pre-repair-*"))

    def test_missing_db_is_not_an_error(self, tmp_path, capsys):
        assert rtg.main(["--db", str(tmp_path / "absent.db")]) == 0
        assert "nothing to repair" in capsys.readouterr().out
